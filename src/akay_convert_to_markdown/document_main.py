"""Document-only entry point using the pinned Docling extraction adapter."""

from __future__ import annotations

import logging

from akay_convert_to_markdown.config.settings import DocumentWorkerSettings
from akay_convert_to_markdown.config.docling_settings import DoclingSettings
from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
from akay_convert_to_markdown.models.content_type import ContentType
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.published_document_processor import PublishedDocumentProcessor
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from akay_convert_to_markdown.worker_runtime import ProcessorResources, run_main


async def _close_processor() -> None:
    """The current document adapter owns no persistent client."""


def build_processor(settings: DocumentWorkerSettings, storage: BlobStorage, webhook: WebhookClient,
                    logger: logging.Logger) -> ProcessorResources:
    models = DoclingSettings()
    converter = DoclingDocumentConverter(artifacts_path=models.artifacts_path)
    processor = PublishedDocumentProcessor(settings, storage, converter, webhook, logger,
                                           allowed_content_types=frozenset({ContentType.DOCUMENT}))
    return processor, _close_processor


def main() -> int:
    return run_main(DocumentWorkerSettings(), build_processor, "akay.convert_document")


if __name__ == "__main__":
    raise SystemExit(main())
