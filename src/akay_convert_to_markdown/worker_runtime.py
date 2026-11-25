"""Shared technical lifecycle, without document or media strategy imports."""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack

from azure.identity.aio import DefaultAzureCredential

from akay_convert_to_markdown.config.settings import CommonSettings
from akay_convert_to_markdown.logging import configure_logging
from akay_convert_to_markdown.messaging.service_bus_consumer import ServiceBusConsumer
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.request_processor import RequestProcessor
from akay_convert_to_markdown.storage.blob_storage import BlobStorage

ProcessorResources = tuple[RequestProcessor, Callable[[], Awaitable[None]]]
ProcessorBuilder = Callable[..., ProcessorResources]


def build_credential(settings: CommonSettings) -> DefaultAzureCredential:
    kwargs: dict[str, str] = {}
    if settings.azure_client_id:
        kwargs["managed_identity_client_id"] = settings.azure_client_id
    return DefaultAzureCredential(**kwargs)


def install_stop_handlers(loop, stop_event, resources) -> None:
    """Stop admission and drain jobs; restore handlers when this runtime exits."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, ValueError):
            # Windows event loops do not implement add_signal_handler.
            try:
                previous = signal.getsignal(sig)
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop_event.set))
            except (OSError, ValueError):
                continue  # Signal registration is restricted to the main thread.
            resources.callback(signal.signal, sig, previous)
        else:
            resources.callback(loop.remove_signal_handler, sig)


async def run_worker(settings: CommonSettings, logger: logging.Logger, build_processor: ProcessorBuilder) -> None:
    async with AsyncExitStack() as resources:
        credential = build_credential(settings)
        await resources.enter_async_context(credential)
        storage = BlobStorage.from_settings(settings, credential)
        resources.push_async_callback(storage.aclose)
        webhook = WebhookClient(settings)
        resources.push_async_callback(webhook.aclose)
        processor, close_processor = build_processor(settings, storage, webhook, logger)
        resources.push_async_callback(close_processor)

        stop_event = asyncio.Event()
        consumer = ServiceBusConsumer(settings, processor, credential, logger, stop_event)
        loop = asyncio.get_running_loop()
        install_stop_handlers(loop, stop_event, resources)
        await consumer.run()


def run_main(settings: CommonSettings, build_processor: ProcessorBuilder, logger_name: str) -> int:
    configure_logging(settings.log_level)
    logger = logging.getLogger(logger_name)
    logger.info("worker.starting", extra={"log_level": settings.log_level})
    try:
        asyncio.run(run_worker(settings, logger, build_processor))
    except KeyboardInterrupt:
        pass
    logger.info("worker.stopped")
    return 0
