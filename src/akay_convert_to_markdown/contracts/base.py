"""Strict, service-independent primitives for the version-one wire contracts."""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from pydantic.alias_generators import to_camel

from akay_convert_to_markdown.errors.exceptions import InvalidMessageError

T = TypeVar("T")


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("A nonblank value is required.")
    return value  # Opaque identities are never trimmed or normalized.


NonEmpty = Annotated[str, Field(min_length=1), AfterValidator(nonblank)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Version = Annotated[int, Field(strict=True, ge=1, le=1)]
Uuid = Annotated[UUID, Field(strict=False)]


def blob_name(value: str) -> str:
    """Portable names only; these references are neither local paths nor URLs."""
    nonblank(value)
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or any(char in value for char in "\\:?#"):
        raise ValueError("A portable relative Blob name is required.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Control characters are not allowed in Blob names.")
    return value


BlobName = Annotated[NonEmpty, AfterValidator(blob_name)]


def markdown_destination(value: str) -> str:
    blob_name(value)
    if not value.lower().endswith(".md") or any(part.endswith(".artifacts") for part in value.split("/")[:-1]):
        raise ValueError("A Markdown destination outside reserved artifact directories is required.")
    return value


MarkdownDestination = Annotated[NonEmpty, AfterValidator(markdown_destination)]


def require_finite_json(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite JSON numbers are not allowed.")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings.")
            require_finite_json(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            require_finite_json(item)
    return value


class Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid",
                              strict=True, frozen=True, allow_inf_nan=False, hide_input_in_errors=True)

    @model_validator(mode="before")
    @classmethod
    def _finite_json(cls, value: Any) -> Any:
        return require_finite_json(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def validate_wire(adapter: TypeAdapter[T], raw: str | bytes) -> T:
    """Expose only a safe error; never send validation input back to a callback."""
    try:
        # Check duplicate keys and non-standard JSON before Pydantic's JSON-mode
        # validation (which accepts UUID strings while retaining strict numbers).
        require_finite_json(json.loads(raw, object_pairs_hook=_unique_object))
        return adapter.validate_json(raw)
    except (ValidationError, ValueError, TypeError, UnicodeDecodeError, RecursionError) as exc:
        raise InvalidMessageError("Message has missing or invalid contract fields.") from exc
