"""Content type classification.

Determines which processing strategy handles a request: ``Document`` (the
Docling path), ``Audio`` (Fast Transcription) or ``Video`` (FFmpeg audio
extraction + Fast Transcription).

Detection is deliberately simple and deterministic, in this order:

1. an explicit ``contentType`` value carried by the message, when present;
2. the file extension.

The message contract carries no MIME type, so extension detection is the final
fallback. Unknown extensions fall back to ``Document`` so the existing document
validation (``validate_extension``) can reject them with the original error.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class ContentType(Enum):
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"


# Audio formats sent directly to Azure Fast Transcription (no conversion).
AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".opus", ".flac"}
)

# Video formats routed through FFmpeg audio extraction. A ``.webm`` container
# may hold either audio or video; the video path (FFmpeg ``-vn``) correctly
# handles audio-only WebM as well.
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv"}
)

_EXPLICIT_TYPES = {
    "document": ContentType.DOCUMENT,
    "audio": ContentType.AUDIO,
    "video": ContentType.VIDEO,
}


def detect_content_type(
    *,
    file_name: str | None,
    explicit_type: str | None = None,
) -> ContentType:
    """Return the :class:`ContentType` for a request.

    Detection is driven by the explicit type or the file extension only; it
    never inspects Blob paths or URLs.

    Unknown content defaults to :class:`ContentType.DOCUMENT` so the existing
    document extension validation keeps producing the original
    ``UNSUPPORTED_DOCUMENT_TYPE`` error.
    """
    if explicit_type:
        normalized = explicit_type.strip().lower()
        if normalized in _EXPLICIT_TYPES:
            return _EXPLICIT_TYPES[normalized]

    extension = Path(file_name or "").suffix.lower()
    if extension in AUDIO_EXTENSIONS:
        return ContentType.AUDIO
    if extension in VIDEO_EXTENSIONS:
        return ContentType.VIDEO
    return ContentType.DOCUMENT
