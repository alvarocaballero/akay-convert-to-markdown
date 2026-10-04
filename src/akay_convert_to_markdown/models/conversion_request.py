"""Service Bus message contract and its validation.

``contextId`` is opaque metadata from the worker's point of view. The worker
never interprets it as a Subject, Topic, Course, Center or any other Akay
domain entity.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from akay_convert_to_markdown.errors.exceptions import (
    InvalidMessageError,
    UnsupportedDocumentTypeError,
)

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".html", ".htm"})


class ConversionRequest(BaseModel):
    """A validated document conversion request."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    document_id: UUID = Field(alias="documentId")
    context_id: UUID = Field(alias="contextId")
    user_id: UUID = Field(alias="userId")
    file_name: str = Field(alias="fileName", min_length=1)
    source_blob_name: str = Field(alias="sourceBlobName", min_length=1)


def parse_conversion_request(raw: str | bytes) -> ConversionRequest:
    """Parse and validate a raw Service Bus message body.

    Raises :class:`InvalidMessageError` when the body is not valid JSON or any
    required field is missing or malformed.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvalidMessageError("Message body is not valid JSON.") from exc

    if not isinstance(data, dict):
        raise InvalidMessageError("Message body must be a JSON object.")

    try:
        return ConversionRequest.model_validate(data)
    except ValidationError as exc:
        raise InvalidMessageError("Message has missing or invalid required fields.") from exc


def validate_extension(file_name: str) -> str:
    """Return the lowercase extension if supported, otherwise raise.

    Raises :class:`UnsupportedDocumentTypeError` for any extension outside the
    initial supported set.
    """
    extension = Path(file_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentTypeError(f"Document type '{extension}' is not supported.")
    return extension


def recover_invalid_message_identity(raw: str | bytes) -> dict | None:
    """Best-effort recovery of identity fields from an invalid message.

    Used to build a ``document.conversion.failed`` webhook when strict
    validation fails. Returns ``None`` when the message cannot be identified
    well enough to build a meaningful failure webhook (i.e. no valid
    ``documentId``).
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    document_id = data.get("documentId")
    try:
        UUID(str(document_id))
    except (ValueError, TypeError, AttributeError):
        return None

    identity: dict = {"documentId": str(document_id)}
    for field in ("contextId", "userId", "fileName"):
        value = data.get(field)
        if value is not None:
            identity[field] = value
    return identity
