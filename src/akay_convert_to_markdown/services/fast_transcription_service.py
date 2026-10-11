"""Azure AI Speech Fast Transcription integration.

Uses the official REST API (``transcriptions:transcribe``) directly: a single
multipart request carries the whole audio file and returns the complete
transcription in the response. No batch jobs, no polling.

The raw Azure REST DTOs never leave this module — callers receive a normalized
:class:`TranscriptionResult`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import (
    InvalidMediaError,
    SpeechRateLimitedError,
    SpeechTranscriptionError,
)
from akay_convert_to_markdown.models.transcription import TranscriptionResult, TranscriptionSegment

_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class FastTranscriptionService:
    """Fast Transcription REST client with a small transient-only retry policy."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()

    def _endpoint_url(self) -> str:
        base = (self._settings.speech_endpoint or "").rstrip("/")
        return f"{base}/speechtotext/transcriptions:transcribe?api-version={self._settings.speech_api_version}"

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe a complete audio file and return the normalized result."""
        if not self._settings.speech_resource_key or not self._settings.speech_endpoint:
            raise SpeechTranscriptionError("Azure Speech is not configured (key or endpoint missing).")

        url = self._endpoint_url()
        headers = {"Ocp-Apim-Subscription-Key": self._settings.speech_resource_key}
        definition = json.dumps({"locales": self._settings.speech_locales})

        last_error: Exception | None = None
        for attempt in range(1, self._settings.speech_retry_count + 1):
            try:
                with audio_path.open("rb") as stream:
                    response = await self._client.post(
                        url,
                        headers=headers,
                        data={"definition": definition},
                        files={"audio": (audio_path.name, stream, "application/octet-stream")},
                        timeout=self._settings.speech_timeout_seconds,
                    )
            except httpx.TimeoutException as exc:
                last_error = exc
            except httpx.RequestError as exc:
                last_error = exc
            else:
                if response.status_code == 200:
                    return self._parse(response.json())
                if response.status_code == 400:
                    raise InvalidMediaError("Azure Speech rejected the audio as invalid media.")
                if response.status_code in (401, 403):
                    raise SpeechTranscriptionError("Azure Speech authentication failed.")
                if response.status_code == 404:
                    raise SpeechTranscriptionError("Azure Speech endpoint not found.")
                if response.status_code in _TRANSIENT_STATUS_CODES:
                    last_error = SpeechRateLimitedError(
                        f"Azure Speech returned transient status {response.status_code}."
                    )
                else:
                    raise SpeechTranscriptionError(
                        f"Azure Speech returned status {response.status_code}."
                    )

            if attempt < self._settings.speech_retry_count:
                await asyncio.sleep(self._settings.speech_retry_delay_seconds)

        raise SpeechRateLimitedError("Azure Speech is temporarily unavailable.") from last_error

    def _parse(self, payload: dict) -> TranscriptionResult:
        if "phrases" not in payload and "combinedPhrases" not in payload:
            raise SpeechTranscriptionError("Azure Speech returned an unexpected response.")

        segments = [
            TranscriptionSegment(
                start_seconds=float(phrase.get("offsetMilliseconds", 0)) / 1000.0,
                duration_seconds=float(phrase.get("durationMilliseconds", 0)) / 1000.0,
                text=str(phrase.get("text") or ""),
            )
            for phrase in payload.get("phrases", [])
            if phrase.get("text") is not None
        ]

        combined = payload.get("combinedPhrases") or []
        text = " ".join(str(item.get("text") or "") for item in combined).strip()
        if not text:
            text = " ".join(segment.text for segment in segments).strip()

        return TranscriptionResult(text=text, segments=segments)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
