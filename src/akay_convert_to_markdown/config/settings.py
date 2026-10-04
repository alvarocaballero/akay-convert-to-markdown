"""Typed application settings backed by environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    webhook_url: str
    webhook_api_key: str
    webhook_timeout_seconds: float = 10.0
    webhook_retry_count: int = 3
    webhook_retry_delay_seconds: float = 2.0

    # Processing -----------------------------------------------------------
    max_document_size_mb: int = 100
    temp_directory: Path = Path("/tmp/akay")

    # Observability --------------------------------------------------------
    log_level: str = "INFO"

    @property
    def max_document_size_bytes(self) -> int:
        return self.max_document_size_mb * 1024 * 1024
