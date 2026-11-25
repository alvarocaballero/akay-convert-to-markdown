"""Normalized transcription models.

Azure Fast Transcription's raw REST DTOs never leak outside the transcription
service. The rest of the application works with these plain models.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from akay_convert_to_markdown.contracts.artifacts import Warning


class TranscriptionSegment(BaseModel):
    """A single timed segment of a transcription."""

    start_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    text: str
    speaker: str | None = None
    language: str | None = None


class TranscriptionResult(BaseModel):
    """A normalized transcription result."""

    text: str
    segments: list[TranscriptionSegment]
    duration_milliseconds: int | None = Field(default=None, ge=0, strict=True)
    language: str | None = None
    warnings: list[Warning] = Field(default_factory=list)

    @model_validator(mode="after")
    def _measured_ranges(self):
        previous = None
        for segment in self.segments:
            start, duration = segment.start_seconds, segment.duration_seconds
            if start is not None:
                if previous is not None and start < previous:
                    raise ValueError("Transcription phrases must retain chronological order.")
                previous = start
            if self.duration_milliseconds is not None:
                limit = self.duration_milliseconds
                for time in (start, None if start is None or duration is None else start + duration):
                    if time is not None and round(time * 1000) > limit:
                        raise ValueError("Transcription phrase exceeds the measured duration.")
        return self
