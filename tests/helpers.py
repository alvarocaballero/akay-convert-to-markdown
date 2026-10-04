"""Shared test helpers and fakes."""

from __future__ import annotations

import logging
from uuid import uuid4

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import SourceBlobNotFoundError
from akay_convert_to_markdown.models.conversion_request import ConversionRequest


def make_settings(**overrides) -> Settings:
    values: dict = dict(
        azure_storage_account_url="https://fakeaccount.blob.core.windows.net",
        source_container_name="source",
        destination_container_name="markdown",
        servicebus_fully_qualified_namespace="fake.servicebus.windows.net",
        servicebus_queue_name="conversion",
        webhook_callbacks={"subject-topic": "https://webhook.example.com/akay"},
        webhook_api_key="test-secret",
        webhook_retry_delay_seconds=0.0,
    )
    values.update(overrides)
    return Settings(**values)


def make_request(**overrides) -> ConversionRequest:
    values: dict = dict(
        document_id=uuid4(),
        context_id=uuid4(),
        user_id=uuid4(),
        file_name="tema-1.pdf",
        source_blob_name="ctx/doc/tema-1.pdf",
        callback="subject-topic",
    )
    values.update(overrides)
    return ConversionRequest(**values)


def make_logger() -> logging.Logger:
    return logging.getLogger("test")


class FakeStorage:
    def __init__(self) -> None:
        self.blob_sizes: dict[str, int] = {}
        self.missing: set[str] = set()
        self.downloads: list[tuple[str, str, object]] = []
        self.uploads: list[tuple[str, str, object]] = []
        self.download_error = None
        self.upload_error = None

    async def get_blob_size(self, container: str, blob_name: str) -> int:
        if blob_name in self.missing:
            raise SourceBlobNotFoundError(f"blob {blob_name} not found")
        return self.blob_sizes.get(blob_name, 12345)

    async def download_to_file(self, container: str, blob_name: str, destination) -> None:
        if self.download_error:
            raise self.download_error
        if blob_name in self.missing:
            raise SourceBlobNotFoundError(f"blob {blob_name} not found")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"dummy document content")
        self.downloads.append((container, blob_name, destination))

    async def upload_file(self, container: str, blob_name: str, source) -> None:
        if self.upload_error:
            raise self.upload_error
        self.uploads.append((container, blob_name, source))

    async def aclose(self) -> None:
        pass


class FakeConverter:
    def __init__(self, result: str = "# Markdown") -> None:
        self.result = result
        self.calls: list[object] = []
        self.error = None

    async def convert(self, source_path) -> str:
        self.calls.append(source_path)
        if self.error:
            raise self.error
        return self.result


class FakeWebhook:
    def __init__(self, callbacks: dict[str, str] | None = None) -> None:
        self._callbacks = callbacks or {"subject-topic": "https://webhook.example.com/akay"}
        self.calls: list[tuple[str, dict, str]] = []
        self.error = None

    def is_configured(self, callback: str) -> bool:
        return callback in self._callbacks

    def resolve_url(self, callback: str) -> str | None:
        return self._callbacks.get(callback)

    async def send(self, callback: str, payload: dict, idempotency_key: str) -> None:
        if self.error:
            raise self.error
        self.calls.append((callback, payload, idempotency_key))

    async def aclose(self) -> None:
        pass
