"""Service Bus consumer (PeekLock).

The consumer is responsible for receiving, deserializing and dispatching
messages to :class:`DocumentProcessor`, then settling each message:

* completed outcome  -> ``complete_message``
* permanent failure   -> ``complete_message`` (after the failed webhook 2xx)
* transient failure   -> ``abandon_message``

Up to ``MAX_CONCURRENT_JOBS`` messages are processed concurrently, bounded by a
semaphore. Azure Service Bus controls redelivery and dead-lettering through the
queue's ``MaxDeliveryCount``; no application-level retry loop exists here.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusReceivedMessage
from azure.servicebus.aio import AutoLockRenewer, ServiceBusClient, ServiceBusReceiver

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import InvalidMessageError, TransientError
from akay_convert_to_markdown.logging import context_logger
from akay_convert_to_markdown.models.conversion_request import (
    parse_conversion_request,
    recover_invalid_message_identity,
)
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor


def _normalize_body(body: object) -> str | bytes:
    """Materialize transport data sections once, without decoding individual chunks."""
    if isinstance(body, (str, bytes)):
        return body
    if not isinstance(body, Iterable) or isinstance(body, Mapping):
        raise InvalidMessageError("Unsupported message body type.")
    try:
        chunks = []
        for chunk in body:
            if not isinstance(chunk, bytes):
                raise InvalidMessageError("Message body sections must be bytes.")
            chunks.append(chunk)
        return b"".join(chunks)
    except InvalidMessageError:
        raise
    except Exception as exc:
        raise InvalidMessageError("Unable to read message body sections.") from exc


class ServiceBusConsumer:
    def __init__(
        self,
        settings: Settings,
        processor: DocumentProcessor,
        credential: DefaultAzureCredential,
        logger: logging.Logger,
        stop_event: asyncio.Event,
        lock_renewer_factory: object | None = None,
    ) -> None:
        self._settings = settings
        self._processor = processor
        self._credential = credential
        self._logger = logger
        self._stop_event = stop_event
        self._lock_renewer_factory = lock_renewer_factory or AutoLockRenewer
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    async def run(self) -> None:
        if self._settings.servicebus_fully_qualified_namespace:
            client = ServiceBusClient(
                self._settings.servicebus_fully_qualified_namespace,
                credential=self._credential,
            )
        else:
            client = ServiceBusClient.from_connection_string(self._settings.servicebus_connection_string)
        async with client:
            receiver = client.get_queue_receiver(
                self._settings.servicebus_queue_name,
                prefetch_count=self._settings.max_concurrent_jobs,
            )
            async with receiver:
                await self._receive_loop(receiver)

    async def _receive_loop(self, receiver: ServiceBusReceiver) -> None:
        while not self._stop_event.is_set():
            messages = await receiver.receive_messages(
                max_message_count=self._settings.max_concurrent_jobs,
                max_wait_time=5,
            )
            if not messages:
                continue
            await asyncio.gather(
                *(asyncio.create_task(self._handle_message(receiver, message)) for message in messages)
            )

    async def _handle_message(self, receiver: ServiceBusReceiver, message: ServiceBusReceivedMessage) -> None:
        renewer = self._lock_renewer_factory()
        try:
            async with self._semaphore:
                await self._process_message(receiver, message, renewer)
        finally:
            await renewer.close()

    async def _process_message(
        self,
        receiver: ServiceBusReceiver,
        message: ServiceBusReceivedMessage,
        renewer,
    ) -> None:
        delivery_count = message.delivery_count
        raw: str | bytes | None = None
        try:
            raw = _normalize_body(message.body)
            request = parse_conversion_request(raw)
        except InvalidMessageError as exc:
            await self._handle_invalid_message(receiver, message, raw, exc, delivery_count)
            return

        request_log = context_logger(
            self._logger,
            request_id=str(request.request_id),
            file_name=request.file_name,
            callback=request.callback,
            delivery_count=delivery_count,
        )
        request_log.info("document.received")

        renewer.register(
            receiver,
            message,
            max_lock_renewal_duration=self._settings.servicebus_max_lock_renewal_seconds,
        )

        try:
            await self._processor.process(request)
        except TransientError as exc:
            request_log.error(
                "document.processing.failed",
                extra={"error_code": "TRANSIENT", "reason": str(exc)},
                exc_info=True,
            )
            await receiver.abandon_message(message)
            return
        except Exception as exc:
            # Unexpected exceptions must never terminate the receive loop.
            # asyncio.CancelledError inherits from BaseException (not
            # Exception), so shutdown cancellation is not swallowed here.
            request_log.error(
                "document.processing.failed",
                extra={"error_code": "UNEXPECTED", "reason": str(exc)},
                exc_info=True,
            )
            await receiver.abandon_message(message)
            return

        await receiver.complete_message(message)

    async def _handle_invalid_message(
        self,
        receiver: ServiceBusReceiver,
        message: ServiceBusReceivedMessage,
        raw: str | bytes | None,
        exc: InvalidMessageError,
        delivery_count: int,
    ) -> None:
        log = context_logger(self._logger, delivery_count=delivery_count)
        identity = recover_invalid_message_identity(raw) if raw is not None else None

        if identity is None:
            log.error(
                "document.processing.failed",
                extra={"error_code": exc.code, "reason": "invalid message"},
            )
            await receiver.complete_message(message)
            return

        log = context_logger(
            self._logger,
            request_id=identity["requestId"],
            callback=identity.get("callback"),
            delivery_count=delivery_count,
        )
        log.error(
            "document.processing.failed",
            extra={"error_code": exc.code, "reason": "invalid message"},
        )

        try:
            await self._processor.notify_invalid_message(identity, log)
        except TransientError:
            await receiver.abandon_message(message)
            return

        await receiver.complete_message(message)
