"""Document-model configuration, loaded only by document-capable entries."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DoclingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCLING_", extra="ignore")

    artifacts_path: Path | None = None

    @field_validator("artifacts_path", mode="before")
    @classmethod
    def _empty_is_absent(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value
