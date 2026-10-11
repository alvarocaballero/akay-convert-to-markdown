"""Normalized transcription models.

Azure Fast Transcription's raw REST DTOs never leak outside the transcription
service. The rest of the application works with these plain models.
"""

from __future__ import annotations

from pydantic import BaseModel


class TranscriptionSegment(BaseModel):
    """A single timed segment of a transcription."""

    start_seconds: float
    duration_seconds: float
    text: str


class TranscriptionResult(BaseModel):
    """A normalized transcription result."""

    text: str
    segments: list[TranscriptionSegment]
