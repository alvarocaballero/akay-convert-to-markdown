"""Optional media integration tests.

Disabled by default. Set ``RUN_AZURE_INTEGRATION_TESTS=true`` to enable the
suite; individual tests additionally skip when their external tool is missing
(``ffmpeg``/``ffprobe`` on PATH) or when no Azure Speech credentials are set
(``SPEECH_RESOURCE_KEY`` + ``SPEECH_ENDPOINT``).
"""

from __future__ import annotations

import os
import shutil
import struct
import wave
from pathlib import Path

import pytest

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown

RUN = os.environ.get("RUN_AZURE_INTEGRATION_TESTS", "").strip().lower() == "true"

pytestmark = pytest.mark.skipif(
    not RUN,
    reason="Set RUN_AZURE_INTEGRATION_TESTS=true to run media integration tests.",
)

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_SPEECH = bool(os.environ.get("SPEECH_RESOURCE_KEY")) and bool(os.environ.get("SPEECH_ENDPOINT"))


def _make_wav(path: Path, seconds: float = 0.5) -> Path:
    """Write a tiny silent mono 16-bit PCM WAV file."""
    frame_rate = 16000
    n_frames = int(frame_rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(frame_rate)
        wav.writeframes(struct.pack("<h", 0) * n_frames)
    return path


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH.")
async def test_ffmpeg_probes_and_prepares_wav(tmp_path):
    wav = _make_wav(tmp_path / "sample.wav")
    settings = Settings(temp_directory=tmp_path)
    ffmpeg = FfmpegService(settings)

    media = await ffmpeg.probe_media(wav)
    assert media.audio_codec is not None
    assert media.duration_seconds is not None and media.duration_seconds > 0

    prepared = await ffmpeg.prepare_audio(wav, tmp_path)
    assert prepared.exists()


@pytest.mark.skipif(not HAS_SPEECH, reason="SPEECH_RESOURCE_KEY/SPEECH_ENDPOINT not set.")
async def test_fast_transcription_round_trip(tmp_path):
    wav = _make_wav(tmp_path / "sample.wav")
    service = FastTranscriptionService(Settings())

    result = await service.transcribe(wav)
    await service.aclose()

    assert isinstance(result.text, str)
    markdown = build_transcription_markdown(result)
    assert markdown.startswith("# Transcripción")
