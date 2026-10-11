"""FFmpeg/FFprobe service tests (subprocess runner faked)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akay_convert_to_markdown.errors.exceptions import FfmpegError, NoAudioTrackError
from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService, MediaInfo
from akay_convert_to_markdown.services.process_runner import ProcessResult, ProcessTimeoutError
from tests.helpers import make_settings


class FakeRunner:
    def __init__(self, probe_json: dict | None = None) -> None:
        self.calls: list[list[str]] = []
        self.probe_json = probe_json or {"streams": [], "format": {}}
        self.ffmpeg_returncode = 0
        self.ffmpeg_stderr = ""
        self.timeout_command: str | None = None

    async def __call__(self, command, *, timeout_seconds, max_log_bytes):
        self.calls.append(command)
        if command[0] == "ffprobe":
            return ProcessResult(0, json.dumps(self.probe_json), "")
        if command[0] == self.timeout_command:
            raise ProcessTimeoutError("timed out")
        return ProcessResult(self.ffmpeg_returncode, "", self.ffmpeg_stderr)


def _service(runner) -> FfmpegService:
    return FfmpegService(make_settings(), runner)


async def test_probe_returns_parsed_json():
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "aac"}], "format": {"duration": "12.5"}})
    service = _service(runner)

    probe = await service.probe(Path("a.mp4"))

    assert probe["streams"][0]["codec_name"] == "aac"
    assert runner.calls[0][0] == "ffprobe"


async def test_probe_failure_raises_ffmpeg_error():
    runner = FakeRunner()
    runner.probe_json = None

    async def _runner(command, *, timeout_seconds, max_log_bytes):
        return ProcessResult(1, "", "probe failed")

    service = FfmpegService(make_settings(), _runner)
    with pytest.raises(FfmpegError):
        await service.probe(Path("a.mp4"))


async def test_probe_media_duration_unknown_is_none():
    runner = FakeRunner({"streams": [], "format": {}})
    service = _service(runner)

    media = await service.probe_media(Path("a.mp4"))

    assert media.duration_seconds is None


async def test_prepare_audio_copies_compatible_codec(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "aac"}]})
    service = _service(runner)

    output = await service.prepare_audio(Path("a.mp4"), tmp_path)

    assert output.suffix == ".m4a"
    ffmpeg_cmd = [c for c in runner.calls if c[0] == "ffmpeg"][0]
    assert "-acodec" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-acodec") + 1] == "copy"


async def test_prepare_audio_converts_unsupported_codec(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "wmav2"}]})
    service = _service(runner)

    output = await service.prepare_audio(Path("a.wmv"), tmp_path)

    assert output.suffix == ".mp3"
    ffmpeg_cmd = [c for c in runner.calls if c[0] == "ffmpeg"][0]
    assert ffmpeg_cmd[ffmpeg_cmd.index("-acodec") + 1] == "libmp3lame"


async def test_prepare_audio_without_audio_raises(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "video", "codec_name": "h264"}]})
    service = _service(runner)

    with pytest.raises(NoAudioTrackError):
        await service.prepare_audio(Path("a.mp4"), tmp_path)


async def test_prepare_audio_failure_raises(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "aac"}]})
    runner.ffmpeg_returncode = 1
    runner.ffmpeg_stderr = "boom"
    service = _service(runner)

    with pytest.raises(FfmpegError) as exc_info:
        await service.prepare_audio(Path("a.mp4"), tmp_path)
    assert "boom" in exc_info.value.detail


async def test_timeout_maps_to_ffmpeg_error(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "aac"}]})
    runner.timeout_command = "ffmpeg"
    service = _service(runner)

    with pytest.raises(FfmpegError):
        await service.prepare_audio(Path("a.mp4"), tmp_path)


async def test_probe_media_returns_normalized_info():
    runner = FakeRunner(
        {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
                {"codec_type": "audio", "codec_name": "mp3"},
            ],
            "format": {"duration": "30.0"},
        }
    )
    service = _service(runner)

    media = await service.probe_media(Path("a.mp4"))

    assert media.duration_seconds == 30.0
    assert media.audio_codecs == ("aac", "mp3")
    assert media.audio_codec == "aac"


async def test_probe_media_runs_ffprobe_once():
    runner = FakeRunner({"streams": [], "format": {}})
    service = _service(runner)

    await service.probe_media(Path("a.mp4"))

    assert len(runner.calls) == 1


async def test_prepare_audio_selects_first_audio_stream(tmp_path):
    runner = FakeRunner(
        {"streams": [{"codec_type": "audio", "codec_name": "aac"}]}
    )
    service = _service(runner)

    await service.prepare_audio(Path("a.mp4"), tmp_path)

    ffmpeg_cmd = [c for c in runner.calls if c[0] == "ffmpeg"][0]
    assert "-map" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-map") + 1] == "0:a:0"


async def test_prepare_audio_reuses_provided_media_without_reprobing(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "aac"}]})
    service = _service(runner)
    media = MediaInfo(duration_seconds=30.0, audio_codecs=("aac",))

    output = await service.prepare_audio(Path("a.mp4"), tmp_path, media=media)

    # No ffprobe call happens when media is supplied.
    assert all(c[0] == "ffmpeg" for c in runner.calls)
    assert output.suffix == ".m4a"


async def test_timeout_error_does_not_leak_command_path(tmp_path):
    runner = FakeRunner({"streams": [{"codec_type": "audio", "codec_name": "aac"}]})
    runner.timeout_command = "ffmpeg"
    service = _service(runner)

    with pytest.raises(FfmpegError) as exc_info:
        await service.prepare_audio(Path("secret-path.mp4"), tmp_path)

    assert "secret-path" not in str(exc_info.value)
    assert "ffmpeg" in str(exc_info.value)
