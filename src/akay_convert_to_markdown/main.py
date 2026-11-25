"""Backward-compatible mixed worker; use dedicated queues for the new entries."""

from __future__ import annotations

import logging

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.config.docling_settings import DoclingSettings
from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.audio_processor import AudioProcessor
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from akay_convert_to_markdown.processing.video_processor import VideoProcessor
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from akay_convert_to_markdown.worker_runtime import ProcessorResources, run_main


def build_processor(settings: Settings, storage: BlobStorage, webhook: WebhookClient,
                    logger: logging.Logger) -> ProcessorResources:
    models = DoclingSettings()
    converter = DoclingDocumentConverter(artifacts_path=models.artifacts_path)
    ffmpeg = FfmpegService(settings)
    transcription = FastTranscriptionService(settings)
    processor = DocumentProcessor(
        settings,
        storage,
        converter,
        webhook,
        logger,
        audio_processor=AudioProcessor(settings, ffmpeg, transcription),
        video_processor=VideoProcessor(settings, ffmpeg, transcription),
    )

    return processor, transcription.aclose


def main() -> int:
    return run_main(Settings(), build_processor, "akay.convert_to_markdown")


if __name__ == "__main__":
    raise SystemExit(main())
