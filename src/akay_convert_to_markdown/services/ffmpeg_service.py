"""FFmpeg / FFprobe integration.

Wraps the ``ffmpeg`` and ``ffprobe`` executables behind a small async API. It is
used to probe media, detect audio tracks and prepare an audio file compatible
with Azure Fast Transcription (preferring a lossless stream copy, falling back
to MP3 re-encoding only when the source codec is not supported).

A single ``ffprobe`` invocation (:meth:`FfmpegService.probe_media`) produces a
:class:`MediaInfo` snapshot that callers reuse across a single processing run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import FfmpegError, NoAudioTrackError
from akay_convert_to_markdown.services.process_runner import (
    ProcessResult,
    ProcessTimeoutError,
    run_process,
)

# Codec name -> (output extension, ffmpeg -acodec argument).
# ``copy`` preserves the original timeline and quality; anything else is
# re-encoded to MP3 (the documented fallback format).
_CODEC_TARGETS: dict[str, tuple[str, str]] = {
    "aac": (".m4a", "copy"),
    "mp3": (".mp3", "copy"),
    "flac": (".flac", "copy"),
    "opus": (".ogg", "copy"),
    "vorbis": (".ogg", "copy"),
    "pcm_s16le": (".wav", "copy"),
    "pcm_s24le": (".wav", "copy"),
    "pcm_s32le": (".wav", "copy"),
}

_FALLBACK_TARGET = (".mp3", "libmp3lame")


@dataclass(frozen=True)
class MediaInfo:
    """Normalized ``ffprobe`` snapshot for a single media file."""

    duration_seconds: float | None
    audio_codecs: tuple[str, ...]

    @property
    def audio_codec(self) -> str | None:
        """The first audio codec, or ``None`` when there is no audio stream."""
        return self.audio_codecs[0] if self.audio_codecs else None


def _parse_media(probe: dict) -> MediaInfo:
    """Extract the fields the worker needs from a raw ``ffprobe`` payload."""
    raw_duration = probe.get("format", {}).get("duration")
    try:
        duration = float(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        duration = None

    codecs = tuple(
        stream.get("codec_name")
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio" and stream.get("codec_name")
    )
    return MediaInfo(duration_seconds=duration, audio_codecs=codecs)


class FfmpegService:
    """FFmpeg/FFprobe wrapper with injectable subprocess runner."""

    def __init__(
        self,
        settings: Settings,
        runner: Callable[..., object] = run_process,
    ) -> None:
        self._settings = settings
        self._runner = runner

    async def _run(self, command: list[str], operation: str) -> ProcessResult:
        try:
            return await self._runner(
                command,
                timeout_seconds=self._settings.ffmpeg_timeout_seconds,
                max_log_bytes=self._settings.ffmpeg_max_log_bytes,
            )
        except ProcessTimeoutError as exc:
            raise FfmpegError(
                f"{command[0]} timed out during {operation} "
                f"(timeout {self._settings.ffmpeg_timeout_seconds}s)."
            ) from exc

    async def probe(self, path: Path) -> dict:
        """Return the raw ``ffprobe`` JSON for ``path``."""
        result = await self._run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
            ],
            operation="probe",
        )
        if result.returncode != 0:
            raise FfmpegError("ffprobe failed.", detail=result.stderr)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise FfmpegError("ffprobe returned invalid JSON.") from exc

    async def probe_media(self, path: Path) -> MediaInfo:
        """Return a :class:`MediaInfo` snapshot with a single ``ffprobe`` call."""
        return _parse_media(await self.probe(path))

    async def prepare_audio(
        self,
        input_path: Path,
        output_dir: Path,
        *,
        media: MediaInfo | None = None,
    ) -> Path:
        """Prepare a transcription-ready audio file, returning its path.

        Extracts the audio track (``-vn``) and copies it unchanged when the
        codec is supported by Azure Fast Transcription; otherwise re-encodes it
        to MP3. Raises :class:`NoAudioTrackError` when there is no audio stream.

        ``media`` may carry a previously obtained :class:`MediaInfo` snapshot so
        a single ``ffprobe`` call is reused across the whole processing run.
        """
        info = media if media is not None else await self.probe_media(input_path)
        codec = info.audio_codec
        if codec is None:
            raise NoAudioTrackError(f"No audio track found in '{input_path.name}'.")

        extension, acodec = _CODEC_TARGETS.get(codec, _FALLBACK_TARGET)
        output_path = output_dir / f"audio{extension}"

        # ``-map 0:a:0`` selects the first audio stream explicitly, avoiding
        # ambiguous multi-track selection and keeping the timeline intact.
        result = await self._run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-map",
                "0:a:0",
                "-vn",
                "-acodec",
                acodec,
                str(output_path),
            ],
            operation="audio extraction",
        )
        if result.returncode != 0:
            raise FfmpegError("FFmpeg failed to prepare audio.", detail=result.stderr)
        return output_path
