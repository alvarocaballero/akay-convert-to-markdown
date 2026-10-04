"""Service Bus consumer (PeekLock).

The consumer is responsible for receiving, deserializing and dispatching one
message at a time to :class:`DocumentProcessor`, then settling the message:

* completed outcome  -> ``complete_message``
* permanent failure   -> ``complete_message`` (after the failed webhook 2xx)
* transient failure   -> ``abandon_message``

Azure Service Bus controls redelivery and dead-lettering through the queue's
``MaxDeliveryCount``; no application-level retry loop exists here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

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

    async def run(self) -> None:
        client = ServiceBusClient(
            self._settings.servicebus_fully_qualified_namespace,
            credential=self._credential,
        )
        async with client:
            receiver = client.get_queue_receiver(
                self._settings.servicebus_queue_name,
                prefetch_count=1,
            )
            async with receiver:
                await self._receive_loop(receiver)

    async def _receive_loop(self, receiver: ServiceBusReceiver) -> None:
        while not self._stop_event.is_set():
            messages = await receiver.receive_messages(max_message_count=1, max_wait_time=5)
            if not messages:
                continue
            for message in messages:
                await self._handle_message(receiver, message)

    async def _handle_message(self, receiver: ServiceBusReceiver, message: ServiceBusReceivedMessage) -> None:
        renewer = self._lock_renewer_factory()
        try:
            delivery_count = message.delivery_count
            raw: str | bytes = message.body

            try:
                request = parse_conversion_request(raw)
            except InvalidMessageError as exc:
                await self._handle_invalid_message(receiver, message, raw, exc, delivery_count)
                return

            request_log = context_logger(
                self._logger,
                document_id=str(request.document_id),
                context_id=str(request.context_id),
                user_id=str(request.user_id),
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
        finally:
            await renewer.close()

    async def _handle_invalid_message(
        self,
        receiver: ServiceBusReceiver,
        message: ServiceBusReceivedMessage,
        raw: str | bytes,
        exc: InvalidMessageError,
        delivery_count: int,
    ) -> None:
        log = context_logger(self._logger, delivery_count=delivery_count)
        identity = recover_invalid_message_identity(raw)

        if identity is None:
            log.error(
                "document.processing.failed",
                extra={"error_code": exc.code, "reason": "invalid message"},
            )
            await receiver.complete_message(message)
            return

        log = context_logger(
            self._logger,
            document_id=identity["documentId"],
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
