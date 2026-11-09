"""Service Bus conversion request and invalid-message recovery."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from akay_convert_to_markdown.errors.exceptions import InvalidMessageError, UnsupportedDocumentTypeError

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".pptx", ".html", ".htm", ".txt", ".md"})


class BlobSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["blob"]
    blob_name: str = Field(alias="blobName", min_length=1)


class ConversionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    request_id: UUID = Field(alias="requestId")
    source: BlobSource
    destination_blob_name: str = Field(alias="destinationBlobName", min_length=1)
    content_type: str | None = Field(default=None, alias="contentType", min_length=1)
    overwrite_destination: StrictBool = Field(default=False, alias="overwriteDestination")
    callback: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def file_name(self) -> str:
        return PurePosixPath(self.source.blob_name).name


def parse_conversion_request(raw: str | bytes) -> ConversionRequest:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Message body must be a JSON object")
        return ConversionRequest.model_validate(data)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
        raise InvalidMessageError("Message has missing or invalid required fields.") from exc


def validate_extension(file_name: str) -> str:
    extension = PurePosixPath(file_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentTypeError(f"Document type '{extension}' is not supported.")
    return extension


def recover_invalid_message_identity(raw: str | bytes) -> dict | None:
    """Recover a request ID, callback and safe JSON fields for failure notification."""
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        request_id = str(UUID(str(data.get("requestId"))))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    identity = {"requestId": request_id}
    for field in ("callback", "source", "destinationBlobName", "contentType", "payload"):
        if field in data:
            identity[field] = data[field]
    return identity
