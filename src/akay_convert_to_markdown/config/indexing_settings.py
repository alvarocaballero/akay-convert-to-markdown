"""Explicit Azure embedding configuration, loaded only when constructing its adapter."""

import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from akay_convert_to_markdown.contracts.requests import IndexProfile
from akay_convert_to_markdown.contracts.base import blob_name


class AzureOpenAISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AZURE_OPENAI_", extra="forbid", frozen=True,
                                      hide_input_in_errors=True, env_file=None)

    endpoint: str
    deployment: str
    auth_mode: Literal["apiKey", "entra"]
    api_key: SecretStr | None = Field(default=None, repr=False)
    api_version: Literal["2024-10-21"] = "2024-10-21"
    timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    retry_count: int = Field(default=3, ge=1, le=10)
    retry_delay_seconds: float = Field(default=1, ge=0, le=30, allow_inf_nan=False)
    batch_size: int = Field(default=32, ge=1, le=2048)
    max_batch_tokens: int = Field(default=65536, ge=8192, le=300000)
    max_response_bytes: int = Field(default=16 * 1024 * 1024, ge=1024, le=128 * 1024 * 1024)

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, value):
        parsed = urlsplit(value)
        if (value != value.strip() or parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or "%" in parsed.netloc or "\\" in value or any(c.isspace() for c in value)):
            raise ValueError("Endpoint must be an explicit HTTPS resource origin.")
        parsed.port  # Reject malformed port syntax rather than deferring to HTTPX.
        return value.rstrip("/")

    @field_validator("deployment")
    @classmethod
    def _deployment(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
            raise ValueError("An explicit deployment name is required.")
        return value

    @model_validator(mode="after")
    def _authentication(self):
        key = self.api_key.get_secret_value() if self.api_key else None
        if self.auth_mode == "apiKey" and (not key or not key.strip() or key != key.strip()):
            raise ValueError("API-key authentication requires an explicit nonblank key.")
        if self.auth_mode == "entra" and self.api_key is not None:
            raise ValueError("Entra authentication must not also configure an API key.")
        return self


class IndexRuntimeSettings(BaseSettings):
    """Required only by the ordered index runtime, never another worker's startup."""

    model_config = SettingsConfigDict(env_prefix="INDEX_", extra="forbid", env_file=None,
                                      frozen=True, hide_input_in_errors=True)
    state_container: str = Field(min_length=1)
    state_prefix: str = Field(min_length=1)
    profiles: list[IndexProfile] = Field(min_length=1)
    tokenizer_path: Path
    qdrant_url: str
    qdrant_auth_mode: Literal["none", "apiKey"]
    qdrant_api_key: SecretStr | None = Field(default=None, repr=False)
    qdrant_timeout_seconds: int = Field(default=30, ge=1, le=300)
    batch_size: int = Field(default=32, ge=1, le=2048)
    max_chunks: int = Field(default=10000, ge=1, le=100000)
    max_state_bytes: int = Field(default=128 * 1024 * 1024, ge=1024)

    @field_validator("state_container", "state_prefix")
    @classmethod
    def _state(cls, value):
        return blob_name(value)

    @field_validator("qdrant_url")
    @classmethod
    def _qdrant_url(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or "%" in parsed.netloc
                or "\\" in value or any(c.isspace() for c in value)):
            raise ValueError("An explicit Qdrant HTTP(S) origin without credentials is required.")
        parsed.port
        return value.rstrip("/")

    @model_validator(mode="after")
    def _qdrant_auth(self):
        key = self.qdrant_api_key.get_secret_value() if self.qdrant_api_key else None
        if self.qdrant_auth_mode == "apiKey":
            if not key or not key.strip() or key != key.strip() or not self.qdrant_url.startswith("https://"):
                raise ValueError("Qdrant API-key mode requires HTTPS and an explicit nonblank key.")
        elif key is not None:
            raise ValueError("Unauthenticated Qdrant mode must not configure an API key.")
        return self
