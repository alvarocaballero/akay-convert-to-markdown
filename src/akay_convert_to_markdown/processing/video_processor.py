"""Video content strategy: FFmpeg extracts audio, then Fast Transcription."""

from __future__ import annotations

import logging
from pathlib import Path

from akay_convert_to_markdown.config.settings import MediaSettings
from akay_convert_to_markdown.models.conversion_request import ConversionRequest
from akay_convert_to_markdown.models.transcription import TranscriptionResult
from akay_convert_to_markdown.processing._media import check_duration
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown


class VideoProcessor:
    """Extract a video's audio track and transcribe it."""

    def __init__(
        self,
        settings: MediaSettings,
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
        return build_transcription_markdown(await self.transcribe(source_path, temp_dir))

    async def transcribe(self, source_path: Path, temp_dir: Path) -> TranscriptionResult:
        """Reuse one probe and the existing audio-only FFmpeg preparation."""
        media = await self._ffmpeg.probe_media(source_path)
        check_duration(media, self._settings)
        audio_path = await self._ffmpeg.prepare_audio(source_path, temp_dir, media=media)
        return await self._transcription.transcribe(audio_path)
