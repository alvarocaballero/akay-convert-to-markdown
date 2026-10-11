"""Audio/Video processor tests (services faked)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from akay_convert_to_markdown.errors.exceptions import (
    MediaTooLongError,
    NoAudioTrackError,
)
from akay_convert_to_markdown.models.transcription import TranscriptionResult, TranscriptionSegment
from akay_convert_to_markdown.processing.audio_processor import AudioProcessor
from akay_convert_to_markdown.processing.video_processor import VideoProcessor
from akay_convert_to_markdown.services.ffmpeg_service import MediaInfo
from tests.helpers import make_request, make_settings


class FakeFfmpeg:
    def __init__(self, duration: float | None = 60.0, codecs: tuple[str, ...] = ("aac",)) -> None:
        self.duration = duration
        self.codecs = codecs
        self.prepare_error: Exception | None = None
        self.prepare_calls: list[Path] = []
        self.probe_calls: list[Path] = []

    async def probe_media(self, path) -> MediaInfo:
        self.probe_calls.append(path)
        return MediaInfo(duration_seconds=self.duration, audio_codecs=self.codecs)

    async def prepare_audio(self, input_path, output_dir, *, media=None):
        self.prepare_calls.append(input_path)
        if self.prepare_error:
            raise self.prepare_error
        codecs = media.audio_codecs if media is not None else self.codecs
        if not codecs:
            raise NoAudioTrackError("no audio")
        output = output_dir / "audio.m4a"
        output.write_bytes(b"audio")
        return output


class FakeTranscription:
    def __init__(self, text: str = "Hello there.") -> None:
        self.text = text
        self.error: Exception | None = None
        self.calls: list[Path] = []

    async def transcribe(self, audio_path):
        self.calls.append(audio_path)
        if self.error:
            raise self.error
        return TranscriptionResult(
            text=self.text,
            segments=[TranscriptionSegment(start_seconds=12.0, duration_seconds=3.0, text=self.text)],
        )


def _log() -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger("test"), {})


async def test_audio_processor_transcribes(tmp_path):
    ffmpeg = FakeFfmpeg()
    transcription = FakeTranscription()
    processor = AudioProcessor(make_settings(), ffmpeg, transcription)
    source = tmp_path / "a.mp3"
    source.write_bytes(b"audio")

    markdown = await processor.to_markdown(make_request(), source, tmp_path, _log())

    assert transcription.calls == [source]
    assert markdown.startswith("# Transcripción")
    assert "Hello there." in markdown


async def test_audio_processor_probes_once(tmp_path):
    ffmpeg = FakeFfmpeg()
    transcription = FakeTranscription()
    processor = AudioProcessor(make_settings(), ffmpeg, transcription)
    source = tmp_path / "a.mp3"
    source.write_bytes(b"audio")

    await processor.to_markdown(make_request(), source, tmp_path, _log())

    assert len(ffmpeg.probe_calls) == 1
    assert len(ffmpeg.prepare_calls) == 0  # audio needs no extraction


async def test_audio_processor_enforces_duration_limit(tmp_path):
    ffmpeg = FakeFfmpeg(duration=100000)
    transcription = FakeTranscription()
    processor = AudioProcessor(make_settings(max_media_duration_minutes=60), ffmpeg, transcription)

    with pytest.raises(MediaTooLongError):
        await processor.to_markdown(make_request(), tmp_path / "a.mp3", tmp_path, _log())


async def test_video_processor_extracts_audio_then_transcribes(tmp_path):
    ffmpeg = FakeFfmpeg()
    transcription = FakeTranscription()
    processor = VideoProcessor(make_settings(), ffmpeg, transcription)
    source = tmp_path / "a.mp4"
    source.write_bytes(b"video")

    markdown = await processor.to_markdown(make_request(), source, tmp_path, _log())

    assert ffmpeg.prepare_calls == [source]
    assert len(transcription.calls) == 1
    assert transcription.calls[0].suffix == ".m4a"
    assert "Hello there." in markdown


async def test_video_processor_probes_once_and_reuses_media(tmp_path):
    ffmpeg = FakeFfmpeg()
    transcription = FakeTranscription()
    processor = VideoProcessor(make_settings(), ffmpeg, transcription)
    source = tmp_path / "a.mp4"
    source.write_bytes(b"video")

    await processor.to_markdown(make_request(), source, tmp_path, _log())

    # A single ffprobe serves both the duration check and the audio extraction.
    assert len(ffmpeg.probe_calls) == 1


async def test_video_processor_without_audio_raises(tmp_path):
    ffmpeg = FakeFfmpeg(codecs=())
    transcription = FakeTranscription()
    processor = VideoProcessor(make_settings(), ffmpeg, transcription)

    with pytest.raises(NoAudioTrackError):
        await processor.to_markdown(make_request(), tmp_path / "a.mp4", tmp_path, _log())
