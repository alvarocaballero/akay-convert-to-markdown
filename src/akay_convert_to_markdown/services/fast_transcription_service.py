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
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from akay_convert_to_markdown.config.settings import MediaSettings
from akay_convert_to_markdown.contracts.artifacts import Warning
from akay_convert_to_markdown.errors.exceptions import (
    InvalidMediaError,
    SpeechRateLimitedError,
    SpeechTranscriptionError,
)
from akay_convert_to_markdown.models.transcription import TranscriptionResult, TranscriptionSegment

_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class _Phrase(BaseModel):
    """Only the pinned REST fields we consume; unrelated word/confidence data stays private."""

    model_config = ConfigDict(strict=True)
    text: str
    offset: int | None = Field(default=None, alias="offsetMilliseconds", ge=0)
    duration: int | None = Field(default=None, alias="durationMilliseconds", ge=0)
    locale: str | None = Field(default=None, min_length=1, pattern=r"\S")
    speaker: int | None = Field(default=None, ge=0)


class _SpeechResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    duration: int | None = Field(default=None, alias="durationMilliseconds", ge=0)
    phrases: list[_Phrase] = Field(default_factory=list)
    combined: list[_Phrase] = Field(default_factory=list, alias="combinedPhrases")


class FastTranscriptionService:
    """Fast Transcription REST client with a small transient-only retry policy."""

    def __init__(self, settings: MediaSettings, client: httpx.AsyncClient | None = None) -> None:
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
                    try:
                        payload = response.json()
                    except ValueError:
                        raise SpeechTranscriptionError("Azure Speech returned an invalid JSON response.") from None
                    return self._parse(payload)
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

    @staticmethod
    def _parse(payload: dict) -> TranscriptionResult:
        try:
            response = _SpeechResponse.model_validate(payload)
            phrases = [phrase for phrase in response.phrases if phrase.text.strip()]
            combined = [phrase for phrase in response.combined if phrase.text.strip()]
            warnings = []
            if phrases and combined:
                phrase_text = " ".join(phrase.text for phrase in phrases).split()
                combined_text = " ".join(phrase.text for phrase in combined).split()
                if phrase_text != combined_text:
                    warnings.append(Warning(code="SPEECH_COMBINED_TEXT_DIFFERS",
                                            message="Combined text differs from phrase text; phrase content is retained in both artifacts."))
            # Combined-only text has no measured phrase boundaries. Preserve it
            # as untimed content instead of inventing a zero start/full-file end.
            segments = [TranscriptionSegment(start_seconds=None if phrase.offset is None else phrase.offset / 1000,
                                              duration_seconds=None if phrase.duration is None else phrase.duration / 1000,
                                              text=phrase.text.strip(), language=phrase.locale,
                                              speaker=None if phrase.speaker is None else str(phrase.speaker))
                        for phrase in (phrases or combined)]
            if not segments:
                raise ValueError("No transcribed content.")
            languages = {segment.language for segment in segments}
            language = next(iter(languages)) if len(languages) == 1 else None
            return TranscriptionResult(text=" ".join(segment.text for segment in segments), segments=segments,
                                       duration_milliseconds=response.duration, language=language, warnings=warnings)
        except (ValidationError, ValueError, OverflowError):
            raise SpeechTranscriptionError("Azure Speech returned an invalid or unexpected transcription response.") from None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
