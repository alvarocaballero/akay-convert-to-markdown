"""Error classification.

Errors are split into two families:

* ``PermanentError`` — the request will never succeed on retry. The worker
  reports it through the ``document.conversion.failed`` webhook and the Service
  Bus message is completed afterwards.
* ``TransientError`` — the request may succeed on a later delivery. The Service
  Bus message is abandoned so Azure Service Bus redelivers it.
"""

from __future__ import annotations


class AkayConvertError(Exception):
    """Base class for every worker error."""


class PermanentError(AkayConvertError):
    """An error that will not succeed on retry."""

    code = "PROCESSING_FAILED"

    def __init__(self, message: str, *, code: str | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        # ``detail`` carries internal diagnostics (e.g. bounded subprocess
        # stderr) that are logged but never sent through the webhook.
        self.detail = detail
        if code is not None:
            self.code = code


class TransientError(AkayConvertError):
    """An error that may succeed on a later delivery attempt."""


class InvalidMessageError(PermanentError):
    code = "INVALID_MESSAGE"


class UnsupportedDocumentTypeError(PermanentError):
    code = "UNSUPPORTED_DOCUMENT_TYPE"


class UnsupportedContentTypeError(PermanentError):
    code = "UNSUPPORTED_CONTENT_TYPE"


class DocumentTooLargeError(PermanentError):
    code = "DOCUMENT_TOO_LARGE"


class MediaTooLongError(PermanentError):
    """The media exceeds the configured maximum duration."""

    code = "MEDIA_TOO_LONG"


class SourceBlobNotFoundError(PermanentError):
    code = "SOURCE_BLOB_NOT_FOUND"


class DocumentConversionError(PermanentError):
    code = "DOCUMENT_CONVERSION_FAILED"


class InvalidMediaError(PermanentError):
    """The media file is corrupt or cannot be processed."""

    code = "INVALID_MEDIA"


class NoAudioTrackError(PermanentError):
    """The video contains no audio track to transcribe."""

    code = "NO_AUDIO_TRACK"


class FfmpegError(PermanentError):
    """FFmpeg/FFprobe failed to process the media."""

    code = "FFMPEG_FAILED"


class SpeechTranscriptionError(PermanentError):
    """Azure Fast Transcription failed permanently."""

    code = "SPEECH_TRANSCRIPTION_FAILED"


class ProcessingTimeoutError(PermanentError):
    """The whole processing exceeded its configured time budget."""

    code = "PROCESSING_TIMEOUT"


class SpeechRateLimitedError(TransientError):
    """Azure Fast Transcription is rate limiting; retry later."""

    code = "SPEECH_RATE_LIMITED"


class ProcessingCancelledError(TransientError):
    """Processing was cancelled before completion."""

    code = "CANCELLED"


class WebhookError(TransientError):
    """Webhook delivery failed; the message should be redelivered."""


class CallbackNotConfiguredError(TransientError):
    """The requested callback identifier is not present in configuration."""


class BlobStorageError(TransientError):
    """Transient Blob Storage failure."""


class ServiceBusError(TransientError):
    """Transient Service Bus failure."""
