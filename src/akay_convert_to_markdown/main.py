"""Entry point for the Akay.ConvertToMarkdown worker."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from azure.identity.aio import DefaultAzureCredential

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.conversion.markitdown_converter import MarkItDownDocumentConverter
from akay_convert_to_markdown.logging import configure_logging
from akay_convert_to_markdown.messaging.service_bus_consumer import ServiceBusConsumer
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from akay_convert_to_markdown.storage.blob_storage import BlobStorage


def _build_credential(settings: Settings) -> DefaultAzureCredential:
    kwargs: dict[str, Any] = {}
    if settings.azure_client_id:
        kwargs["managed_identity_client_id"] = settings.azure_client_id
    return DefaultAzureCredential(**kwargs)


async def _run(settings: Settings, logger: logging.Logger) -> None:
    credential = _build_credential(settings)

    storage = BlobStorage.from_settings(settings, credential)
    converter = MarkItDownDocumentConverter()
    webhook = WebhookClient(settings)
    processor = DocumentProcessor(settings, storage, converter, webhook, logger)

    stop_event = asyncio.Event()
    consumer = ServiceBusConsumer(settings, processor, credential, logger, stop_event)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, ValueError):
            pass

    async with credential:
        try:
            await consumer.run()
        finally:
            await webhook.aclose()
            await storage.aclose()


def main() -> int:
    settings = Settings()  # fails fast when mandatory configuration is missing
    configure_logging(settings.log_level)
    logger = logging.getLogger("akay.convert_to_markdown")
    logger.info("worker.starting", extra={"log_level": settings.log_level})

    try:
        asyncio.run(_run(settings, logger))
    except KeyboardInterrupt:
        pass

    logger.info("worker.stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
