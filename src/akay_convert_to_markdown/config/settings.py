"""Typed application settings backed by environment variables."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
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

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore")

    # Azure identity -------------------------------------------------------
    azure_client_id: str | None = None

    # Azure Blob Storage ---------------------------------------------------
    azure_storage_account_url: str
    source_container_name: str
    destination_container_name: str

    # Azure Service Bus ----------------------------------------------------
    servicebus_fully_qualified_namespace: str
    servicebus_queue_name: str
    servicebus_max_lock_renewal_seconds: int = 900

    # Webhook --------------------------------------------------------------
    webhook_callbacks: dict[str, str]
    webhook_api_key: str
    webhook_timeout_seconds: float = 10.0
    webhook_retry_count: int = 3
    webhook_retry_delay_seconds: float = 2.0

    # Processing -----------------------------------------------------------
    max_document_size_mb: int = 100
    temp_directory: Path = Path("/tmp/akay")

    # Observability --------------------------------------------------------
    log_level: str = "INFO"

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
    def max_document_size_bytes(self) -> int:
        return self.max_document_size_mb * 1024 * 1024
