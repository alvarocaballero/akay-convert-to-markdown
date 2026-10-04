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

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class TransientError(AkayConvertError):
    """An error that may succeed on a later delivery attempt."""


class InvalidMessageError(PermanentError):
    code = "INVALID_MESSAGE"


class UnsupportedDocumentTypeError(PermanentError):
    code = "UNSUPPORTED_DOCUMENT_TYPE"


class DocumentTooLargeError(PermanentError):
    code = "DOCUMENT_TOO_LARGE"


class SourceBlobNotFoundError(PermanentError):
    code = "SOURCE_BLOB_NOT_FOUND"


class DocumentConversionError(PermanentError):
    code = "DOCUMENT_CONVERSION_FAILED"


class WebhookError(TransientError):
    """Webhook delivery failed; the message should be redelivered."""


class BlobStorageError(TransientError):
    """Transient Blob Storage failure."""


class ServiceBusError(TransientError):
    """Transient Service Bus failure."""
