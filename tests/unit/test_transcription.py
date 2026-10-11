"""Azure Fast Transcription service tests (HTTP faked)."""

from __future__ import annotations

import json

import httpx
import pytest

from akay_convert_to_markdown.errors.exceptions import (
    InvalidMediaError,
    SpeechRateLimitedError,
    SpeechTranscriptionError,
)
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from tests.helpers import make_settings

_RESPONSE = {
    "durationMilliseconds": 3000,
    "combinedPhrases": [{"text": "Hello world. Goodbye."}],
    "phrases": [
        {"offsetMilliseconds": 0, "durationMilliseconds": 1000, "text": "Hello world."},
        {"offsetMilliseconds": 2000, "durationMilliseconds": 1000, "text": "Goodbye."},
    ],
}


def _service(handler, **overrides) -> FastTranscriptionService:
    values = dict(
        speech_resource_key="key",
        speech_endpoint="https://speech.example.com",
        speech_retry_count=2,
        speech_retry_delay_seconds=0.0,
    )
    values.update(overrides)
    settings = make_settings(**values)
    return FastTranscriptionService(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_transcribes_and_maps_response(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")

    def handler(request: httpx.Request):
        assert request.headers["Ocp-Apim-Subscription-Key"] == "key"
        return httpx.Response(200, json=_RESPONSE)

    service = _service(handler)
    result = await service.transcribe(audio)

    assert result.text == "Hello world. Goodbye."
    assert len(result.segments) == 2
    assert result.segments[0].start_seconds == 0.0
    assert result.segments[0].duration_seconds == 1.0
    assert result.segments[0].text == "Hello world."
    assert result.segments[1].start_seconds == 2.0
    assert result.segments[1].text == "Goodbye."


async def test_retries_transient_status_then_succeeds(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) < 2:
            return httpx.Response(429)
        return httpx.Response(200, json=_RESPONSE)

    service = _service(handler)
    result = await service.transcribe(audio)

    assert len(calls) == 2
    assert result.text == "Hello world. Goodbye."


async def test_rate_limit_exhausted_is_transient(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")

    def handler(request: httpx.Request):
        return httpx.Response(429)

    service = _service(handler)
    with pytest.raises(SpeechRateLimitedError):
        await service.transcribe(audio)


@pytest.mark.parametrize("status", [500, 503])
async def test_retries_transient_5xx_then_succeeds(tmp_path, status):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) < 2:
            return httpx.Response(status)
        return httpx.Response(200, json=_RESPONSE)

    service = _service(handler)
    result = await service.transcribe(audio)

    assert len(calls) == 2
    assert result.text == "Hello world. Goodbye."


@pytest.mark.parametrize("status", [500, 503])
async def test_transient_5xx_exhausted_is_transient(tmp_path, status):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")

    def handler(request: httpx.Request):
        return httpx.Response(status)

    service = _service(handler)
    with pytest.raises(SpeechRateLimitedError):
        await service.transcribe(audio)


async def test_auth_error_is_permanent_and_not_retried(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(401)

    service = _service(handler)
    with pytest.raises(SpeechTranscriptionError):
        await service.transcribe(audio)

    assert len(calls) == 1


async def test_bad_request_maps_to_invalid_media(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")

    def handler(request: httpx.Request):
        return httpx.Response(400, json={"error": "unsupported"})

    service = _service(handler)
    with pytest.raises(InvalidMediaError):
        await service.transcribe(audio)


async def test_missing_config_is_permanent(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    service = _service(lambda r: httpx.Response(200, json=_RESPONSE), speech_resource_key=None)

    with pytest.raises(SpeechTranscriptionError):
        await service.transcribe(audio)


async def test_builds_text_from_segments_when_combined_missing(tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"audio")
    payload = {
        "phrases": [{"offsetMilliseconds": 0, "durationMilliseconds": 500, "text": "Only phrases."}]
    }

    def handler(request: httpx.Request):
        return httpx.Response(200, json=payload)

    service = _service(handler)
    result = await service.transcribe(audio)

    assert result.text == "Only phrases."
    assert len(result.segments) == 1
