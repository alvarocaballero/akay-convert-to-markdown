"""Shared helpers for media processors."""

from __future__ import annotations

from akay_convert_to_markdown.config.settings import MediaSettings
from akay_convert_to_markdown.errors.exceptions import MediaTooLongError
from akay_convert_to_markdown.services.ffmpeg_service import MediaInfo


def check_duration(media: MediaInfo, settings: MediaSettings) -> None:
    """Reject media longer than ``MAX_MEDIA_DURATION_MINUTES``.

    Unknown durations (``None``) are allowed through; the overall
    ``PROCESS_TIMEOUT_MINUTES`` remains the safety net for those cases.
    """
    duration = media.duration_seconds
    if duration is not None and duration > settings.max_media_duration_seconds:
        raise MediaTooLongError(
            f"Media duration {int(duration)}s exceeds the maximum of "
            f"{settings.max_media_duration_minutes} minutes."
        )
