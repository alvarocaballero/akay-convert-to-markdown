"""Typed application settings backed by environment variables."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_WEBHOOK_URL_SCHEMES = frozenset({"http", "https"})


def _is_valid_webhook_url(url: str) -> bool:
    """Whether ``url`` is an absolute HTTP(S) URL with a host."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in _ALLOWED_WEBHOOK_URL_SCHEMES and bool(parsed.netloc)


class Settings(BaseSettings):
    """Environment-driven configuration.

    Mandatory fields have no default and therefore make startup fail fast when
    they are absent. Secrets never carry a default value.
    """

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore", hide_input_in_errors=True)

    # Azure identity -------------------------------------------------------
    azure_client_id: str | None = None

    # Azure Blob Storage ---------------------------------------------------
    azure_storage_account_url: str
    azure_storage_sas_token: str | None = Field(default=None, repr=False)
    source_container_name: str
    destination_container_name: str

    # Azure Service Bus ----------------------------------------------------
    servicebus_fully_qualified_namespace: str | None = None
    servicebus_connection_string: str | None = Field(default=None, repr=False)
    servicebus_queue_name: str
    servicebus_max_lock_renewal_seconds: int = 900

    # Webhook --------------------------------------------------------------
    webhook_callbacks: dict[str, str]
    webhook_api_key: str
    webhook_timeout_seconds: float = 10.0
    webhook_retry_count: int = 3
    webhook_retry_delay_seconds: float = 2.0

    # Processing -----------------------------------------------------------
    max_input_size_mb: int = 100
    max_media_duration_minutes: int = 240
    process_timeout_minutes: int = 60
    max_concurrent_jobs: int = 2
    temp_directory: Path = Path("/tmp/akay")

    # Azure Speech (Fast Transcription) ------------------------------------
    speech_resource_key: str | None = None
    speech_endpoint: str | None = None
    speech_api_version: str = "2025-10-15"
    speech_locales: list[str] = []
    speech_timeout_seconds: float = 600.0
    speech_retry_count: int = 2
    speech_retry_delay_seconds: float = 1.0

    # FFmpeg / FFprobe ------------------------------------------------------
    ffmpeg_timeout_seconds: float = 300.0
    ffmpeg_max_log_bytes: int = 8192

    # Observability --------------------------------------------------------
    log_level: str = "INFO"

    @field_validator("azure_storage_account_url")
    @classmethod
    def _validate_storage_account_url(cls, value: str) -> str:
        if "?" in value:
            raise ValueError("AZURE_STORAGE_ACCOUNT_URL must not contain a query string; configure SAS separately.")
        return value

    @field_validator("azure_storage_sas_token", mode="before")
    @classmethod
    def _normalize_storage_sas_token(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if value.startswith("?"):
                value = value[1:].strip()
                if not value:
                    raise ValueError("AZURE_STORAGE_SAS_TOKEN must contain a token after '?'.")
        return value

    @field_validator("servicebus_fully_qualified_namespace", "servicebus_connection_string", mode="before")
    @classmethod
    def _normalize_servicebus_connection(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("servicebus_queue_name")
    @classmethod
    def _validate_servicebus_queue_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("SERVICEBUS_QUEUE_NAME must not be empty.")
        return value

    @model_validator(mode="after")
    def _validate_servicebus_authentication(self) -> "Settings":
        if not self.servicebus_connection_string and not self.servicebus_fully_qualified_namespace:
            raise ValueError("Configure at least one of SERVICEBUS_CONNECTION_STRING or "
                             "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE.")
        return self

    @field_validator("speech_locales", mode="before")
    @classmethod
    def _parse_speech_locales(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("webhook_callbacks", mode="before")
    @classmethod
    def _parse_webhook_callbacks(cls, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"WEBHOOK_CALLBACKS is not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("WEBHOOK_CALLBACKS must be a JSON object mapping callback names to URLs.")
        for key, url in value.items():
            if not isinstance(key, str) or not isinstance(url, str) or not key or not url:
                raise ValueError("WEBHOOK_CALLBACKS keys and values must be non-empty strings.")
            if not _is_valid_webhook_url(url):
                raise ValueError(
                    f"WEBHOOK_CALLBACKS URL for '{key}' must be an absolute http:// or https:// URL."
                )
        return value

    @property
    def max_input_size_bytes(self) -> int:
        return self.max_input_size_mb * 1024 * 1024

    @property
    def process_timeout_seconds(self) -> float:
        return self.process_timeout_minutes * 60.0

    @property
    def max_media_duration_seconds(self) -> float:
        return self.max_media_duration_minutes * 60.0
