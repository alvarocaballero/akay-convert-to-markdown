"""Audio content strategy: Fast Transcription straight to Markdown."""

from __future__ import annotations

import logging
from pathlib import Path

from akay_convert_to_markdown.config.settings import MediaSettings
from akay_convert_to_markdown.errors.exceptions import NoAudioTrackError
from akay_convert_to_markdown.models.conversion_request import ConversionRequest
from akay_convert_to_markdown.models.transcription import TranscriptionResult
from akay_convert_to_markdown.processing._media import check_duration
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown


class AudioProcessor:
    """Transcribe an audio file with Azure Fast Transcription."""

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
        """Retain the normalized Speech result for the artifact-capable worker."""
        media = await self._ffmpeg.probe_media(source_path)
        check_duration(media, self._settings)
        if not media.audio_codecs:
            raise NoAudioTrackError("The media contains no audio track.")
        return await self._transcription.transcribe(source_path)
