"""Audio content strategy: Fast Transcription straight to Markdown."""

from __future__ import annotations

import logging
from pathlib import Path

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.models.conversion_request import ConversionRequest
from akay_convert_to_markdown.processing._media import check_duration
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown


class AudioProcessor:
    """Transcribe an audio file with Azure Fast Transcription."""

    def __init__(
        self,
        settings: Settings,
        ffmpeg: FfmpegService,
        transcription: FastTranscriptionService,
    ) -> None:
        self._settings = settings
        self._ffmpeg = ffmpeg
        self._transcription = transcription

    async def to_markdown(
        self,
        request: ConversionRequest,
        source_path: Path | None,
        temp_dir: Path,
        log: logging.LoggerAdapter,
    ) -> str:
        assert source_path is not None
        media = await self._ffmpeg.probe_media(source_path)
        check_duration(media, self._settings)
        result = await self._transcription.transcribe(source_path)
        return build_transcription_markdown(result)
