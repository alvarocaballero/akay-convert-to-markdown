"""Webhook callback configuration validation tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from akay_convert_to_markdown.config.settings import Settings


def _settings(**overrides) -> Settings:
    values: dict = dict(
        azure_storage_account_url="https://fakeaccount.blob.core.windows.net",
        source_container_name="source",
        destination_container_name="markdown",
        servicebus_fully_qualified_namespace="fake.servicebus.windows.net",
        servicebus_queue_name="conversion",
        webhook_callbacks={"subject-topic": "https://webhook.example.com/akay"},
        webhook_api_key="test-secret",
    )
    values.update(overrides)
    return Settings(**values)


def test_https_callback_url_is_accepted():
    settings = _settings(webhook_callbacks={"subject-topic": "https://webhook.example.com/akay"})
    assert settings.webhook_callbacks == {"subject-topic": "https://webhook.example.com/akay"}


def test_http_callback_url_is_accepted():
    settings = _settings(webhook_callbacks={"subject-topic": "http://localhost:8080/akay"})
    assert settings.webhook_callbacks == {"subject-topic": "http://localhost:8080/akay"}


def test_file_scheme_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"subject-topic": "file:///etc/passwd"})


def test_ftp_scheme_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"subject-topic": "ftp://example.com/akay"})


def test_missing_scheme_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"subject-topic": "webhook.example.com/akay"})


def test_malformed_url_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"subject-topic": "https://[::1"})


def test_multiple_callbacks_parsed_from_environment(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://fakeaccount.blob.core.windows.net")
    monkeypatch.setenv("SOURCE_CONTAINER_NAME", "source")
    monkeypatch.setenv("DESTINATION_CONTAINER_NAME", "markdown")
    monkeypatch.setenv("SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", "fake.servicebus.windows.net")
    monkeypatch.setenv("SERVICEBUS_QUEUE_NAME", "conversion")
    monkeypatch.setenv("WEBHOOK_API_KEY", "test-secret")
    monkeypatch.setenv(
        "WEBHOOK_CALLBACKS",
        json.dumps(
            {
                "subject-topic": "https://example.com/subject-topic",
                "student-document": "http://localhost:8080/student-document",
            }
        ),
    )

    settings = Settings()

    assert settings.webhook_callbacks == {
        "subject-topic": "https://example.com/subject-topic",
        "student-document": "http://localhost:8080/student-document",
    }
