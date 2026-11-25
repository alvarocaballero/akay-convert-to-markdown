"""Blob/YouTube entry point reusing the existing Speech/FFmpeg implementations."""

from __future__ import annotations

import logging

from akay_convert_to_markdown.config.settings import MediaWorkerSettings
from akay_convert_to_markdown.models.content_type import ContentType
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.audio_processor import AudioProcessor
from akay_convert_to_markdown.processing.published_media_processor import PublishedMediaProcessor
from akay_convert_to_markdown.processing.video_processor import VideoProcessor
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
from akay_convert_to_markdown.services.youtube_service import YouTubeService
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from akay_convert_to_markdown.worker_runtime import ProcessorResources, run_main


def build_processor(settings: MediaWorkerSettings, storage: BlobStorage, webhook: WebhookClient,
                    logger: logging.Logger) -> ProcessorResources:
    ffmpeg = FfmpegService(settings)
    transcription = FastTranscriptionService(settings)
    processor = PublishedMediaProcessor(settings, storage, None, webhook, logger,
                                  youtube_service=YouTubeService(settings),
                                  audio_processor=AudioProcessor(settings, ffmpeg, transcription),
                                  video_processor=VideoProcessor(settings, ffmpeg, transcription),
                                  allowed_content_types=frozenset({ContentType.AUDIO, ContentType.VIDEO}))
    return processor, transcription.aclose


def main() -> int:
    return run_main(MediaWorkerSettings(), build_processor, "akay.transcribe_media")


if __name__ == "__main__":
    raise SystemExit(main())
