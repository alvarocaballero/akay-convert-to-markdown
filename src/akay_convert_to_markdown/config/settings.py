"""Typed application settings backed by environment variables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar
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


class _QueueAssignments(BaseSettings):
    """Known local routing assignments, never discovered from remote resources."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    legacy: str | None = Field(default=None, validation_alias="SERVICEBUS_QUEUE_NAME")
    document: str | None = Field(default=None, validation_alias="DOCUMENT_SERVICEBUS_QUEUE_NAME")
    media: str | None = Field(default=None, validation_alias="MEDIA_SERVICEBUS_QUEUE_NAME")
    index: str | None = Field(default=None, validation_alias="INDEX_SERVICEBUS_QUEUE_NAME")


class CommonSettings(BaseSettings):
    """Environment-driven configuration.

    Mandatory fields have no default and therefore make startup fail fast when
    they are absent. Secrets never carry a default value.
    """

    model_config = SettingsConfigDict(env_file=None, case_sensitive=False, extra="ignore", hide_input_in_errors=True)
    queue_assignment: ClassVar[str] = "legacy"

    # Azure identity -------------------------------------------------------
    azure_client_id: str | None = None

    # Azure Blob Storage ---------------------------------------------------
    azure_storage_account_url: str
    azure_storage_sas_token: str | None = Field(default=None, repr=False)
    source_container_name: str

    # Azure Service Bus ----------------------------------------------------
    servicebus_fully_qualified_namespace: str | None = None
    servicebus_connection_string: str | None = Field(default=None, repr=False)
    servicebus_queue_name: str
    servicebus_max_lock_renewal_seconds: int = Field(default=4500, gt=0)

    # Webhook --------------------------------------------------------------
    webhook_callbacks: dict[str, str]
    webhook_api_key: str = Field(repr=False)
    webhook_timeout_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)
    webhook_retry_count: int = Field(default=3, gt=0)
    webhook_retry_delay_seconds: float = Field(default=2.0, ge=0, allow_inf_nan=False)

    # Processing -----------------------------------------------------------
    max_input_size_mb: int = 100
    process_timeout_minutes: int = 60
    workflow_timeout_seconds: float = Field(default=4200, gt=0, allow_inf_nan=False)
    max_concurrent_jobs: int = Field(default=2, gt=0)
    temp_directory: Path = Path("/tmp/akay")

    # Observability --------------------------------------------------------
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _validate_workflow_budgets(self):
        callback_budget = (self.webhook_timeout_seconds * self.webhook_retry_count
                           + self.webhook_retry_delay_seconds * (self.webhook_retry_count - 1))
        if self.workflow_timeout_seconds < self.process_timeout_seconds + callback_budget + 60:
            raise ValueError("WORKFLOW_TIMEOUT_SECONDS must cover processing, callback retries and at least 60 seconds for publication.")
        if self.servicebus_max_lock_renewal_seconds < self.workflow_timeout_seconds + 60:
            raise ValueError("SERVICEBUS_MAX_LOCK_RENEWAL_SECONDS must cover the workflow plus at least 60 seconds of drain/settlement margin.")
        return self

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
    def _validate_servicebus_authentication(self) -> "CommonSettings":
        if not self.servicebus_connection_string and not self.servicebus_fully_qualified_namespace:
            raise ValueError("Configure at least one of SERVICEBUS_CONNECTION_STRING or "
                             "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE.")
        return self

    @model_validator(mode="after")
    def _validate_queue_isolation(self) -> "CommonSettings":
        for target, queue in _QueueAssignments().model_dump().items():
            if (target != self.queue_assignment and queue
                    and queue.strip().casefold() == self.servicebus_queue_name.casefold()):
                raise ValueError("Worker queues must be distinct, including the legacy mixed queue.")
        return self

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


class ConversionSettings(CommonSettings):
    """Blob-to-Markdown publication settings shared by the two conversion paths."""

    destination_container_name: str


class MediaSettings(ConversionSettings):
    """Existing media options; legacy mixed mode keeps Speech optional."""

    max_media_duration_minutes: int = 240
    speech_resource_key: str | None = Field(default=None, repr=False)
    speech_endpoint: str | None = None
    speech_api_version: str = "2025-10-15"
    speech_locales: list[str] = []
    speech_timeout_seconds: float = 600.0
    speech_retry_count: int = 2
    speech_retry_delay_seconds: float = 1.0
    ffmpeg_timeout_seconds: float = 300.0
    ffmpeg_max_log_bytes: int = 8192

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

    @property
    def max_media_duration_seconds(self) -> float:
        return self.max_media_duration_minutes * 60.0


class Settings(MediaSettings):
    """Backward-compatible configuration for the existing mixed worker."""


class PublicationSettings(ConversionSettings):
    """Explicit complete-set storage settings for the dedicated artifact workers."""

    publication_state_container_name: str | None = Field(default=None, min_length=1)
    publication_state_prefix: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _publication_configuration(self):
        values = (self.publication_state_container_name, self.publication_state_prefix)
        if any(value is not None for value in values):
            if not all(value and value.strip() for value in values):
                raise ValueError("Configure both publication state container and prefix.")
            from akay_convert_to_markdown.contracts.base import blob_name

            blob_name(self.publication_state_prefix)
        return self


class DocumentWorkerSettings(PublicationSettings):
    queue_assignment: ClassVar[str] = "document"
    servicebus_queue_name: str = Field(validation_alias="DOCUMENT_SERVICEBUS_QUEUE_NAME")
    max_concurrent_jobs: int = 1


class MediaWorkerSettings(MediaSettings, PublicationSettings):
    queue_assignment: ClassVar[str] = "media"
    servicebus_queue_name: str = Field(validation_alias="MEDIA_SERVICEBUS_QUEUE_NAME")
    speech_resource_key: str = Field(min_length=1, repr=False)
    speech_endpoint: str = Field(min_length=1)
    youtube_timeout_seconds: float = Field(default=300, gt=0, allow_inf_nan=False)
    youtube_max_temp_mb: int = Field(default=256, gt=0)

    @field_validator("speech_resource_key", "speech_endpoint", mode="before")
    @classmethod
    def _strip_required_speech_settings(cls, value):
        return value.strip() if isinstance(value, str) else value


class IndexerSettings(CommonSettings):
    """Common index-worker settings; adapter/state configuration is loaded separately."""

    queue_assignment: ClassVar[str] = "index"
    servicebus_queue_name: str = Field(validation_alias="INDEX_SERVICEBUS_QUEUE_NAME")
