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
        webhook_callbacks={"topic-content": "https://webhook.example.com/akay"},
        webhook_api_key="test-secret",
    )
    values.update(overrides)
    return Settings(**values)


def test_https_callback_url_is_accepted():
    settings = _settings(webhook_callbacks={"topic-content": "https://webhook.example.com/akay"})
    assert settings.webhook_callbacks == {"topic-content": "https://webhook.example.com/akay"}


def test_http_callback_url_is_accepted():
    settings = _settings(webhook_callbacks={"topic-content": "http://localhost:8080/akay"})
    assert settings.webhook_callbacks == {"topic-content": "http://localhost:8080/akay"}


def test_file_scheme_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"topic-content": "file:///etc/passwd"})


def test_ftp_scheme_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"topic-content": "ftp://example.com/akay"})


def test_missing_scheme_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"topic-content": "webhook.example.com/akay"})


def test_malformed_url_is_rejected():
    with pytest.raises(ValidationError):
        _settings(webhook_callbacks={"topic-content": "https://[::1"})


def test_multiple_callbacks_parsed_from_environment(monkeypatch):
    monkeypatch.delenv("SERVICEBUS_CONNECTION_STRING", raising=False)
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
                "topic-content": "https://example.com/topic-content",
                "student-document": "http://localhost:8080/student-document",
            }
        ),
    )

    settings = Settings()

    assert settings.webhook_callbacks == {
        "topic-content": "https://example.com/topic-content",
        "student-document": "http://localhost:8080/student-document",
    }


@pytest.mark.parametrize("connection,namespace,valid", [
    ("Endpoint=sb://localhost;SharedAccessKey=example", None, True),
    (None, "namespace.servicebus.windows.net", True),
    ("Endpoint=sb://localhost;SharedAccessKey=example", "namespace.servicebus.windows.net", True),
    (None, None, False),
    ("   ", "namespace.servicebus.windows.net", True),
    ("Endpoint=sb://localhost;SharedAccessKey=example", "  ", True),
    ("  ", "", False),
])
def test_servicebus_authentication_modes(connection, namespace, valid):
    values = dict(servicebus_connection_string=connection, servicebus_fully_qualified_namespace=namespace)
    if valid:
        settings = _settings(**values)
        assert bool(settings.servicebus_connection_string) or bool(settings.servicebus_fully_qualified_namespace)
    else:
        with pytest.raises(ValidationError) as exc:
            _settings(**values)
        assert "SharedAccessKey=example" not in str(exc.value)


@pytest.mark.parametrize("queue", ["", "   "])
def test_servicebus_queue_must_not_be_blank(queue):
    with pytest.raises(ValidationError):
        _settings(servicebus_queue_name=queue)


def test_servicebus_queue_is_required(monkeypatch):
    monkeypatch.delenv("SERVICEBUS_QUEUE_NAME", raising=False)
    with pytest.raises(ValidationError):
        _settings(servicebus_queue_name=None)


@pytest.mark.parametrize("mode", ["connection_string", "namespace", "both", "blank_namespace"])
def test_servicebus_authentication_loaded_from_environment(monkeypatch, mode):
    monkeypatch.delenv("SERVICEBUS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://fakeaccount.blob.core.windows.net")
    monkeypatch.setenv("SOURCE_CONTAINER_NAME", "source")
    monkeypatch.setenv("DESTINATION_CONTAINER_NAME", "markdown")
    monkeypatch.setenv("SERVICEBUS_QUEUE_NAME", "convert-to-markdown")
    monkeypatch.setenv("WEBHOOK_API_KEY", "test-secret")
    monkeypatch.setenv("WEBHOOK_CALLBACKS", '{"topic-content":"http://localhost:5246/api/webhooks/topic-content-converted"}')
    if mode in ("connection_string", "both", "blank_namespace"):
        monkeypatch.setenv("SERVICEBUS_CONNECTION_STRING", "Endpoint=sb://localhost;UseDevelopmentEmulator=true")
    if mode in ("namespace", "both"):
        monkeypatch.setenv("SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", "example.servicebus.windows.net")
    elif mode == "blank_namespace":
        monkeypatch.setenv("SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", "  ")
    settings = Settings()
    assert settings.servicebus_queue_name == "convert-to-markdown"
    assert bool(settings.servicebus_connection_string) == (mode in ("connection_string", "both", "blank_namespace"))
    assert bool(settings.servicebus_fully_qualified_namespace) == (mode in ("namespace", "both"))


def test_connection_string_omitted_from_settings_repr():
    settings = _settings(servicebus_fully_qualified_namespace=None,
                         servicebus_connection_string="Endpoint=sb://localhost;SharedAccessKey=example")
    assert "SharedAccessKey=example" not in repr(settings)


def test_blank_authentication_environment_is_invalid(monkeypatch):
    monkeypatch.setenv("SERVICEBUS_CONNECTION_STRING", "  ")
    monkeypatch.setenv("SERVICEBUS_FULLY_QUALIFIED_NAMESPACE", " ")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://fakeaccount.blob.core.windows.net")
    monkeypatch.setenv("SOURCE_CONTAINER_NAME", "source")
    monkeypatch.setenv("DESTINATION_CONTAINER_NAME", "markdown")
    monkeypatch.setenv("SERVICEBUS_QUEUE_NAME", "convert-to-markdown")
    monkeypatch.setenv("WEBHOOK_API_KEY", "test-secret")
    monkeypatch.setenv("WEBHOOK_CALLBACKS", '{"topic-content":"http://localhost:5246/api/webhooks/topic-content-converted"}')
    with pytest.raises(ValidationError, match="at least one"):
        Settings()


@pytest.mark.parametrize("token,expected", [(None, None), ("", None), ("   ", None),
                                           ("sv=1&sig=secret", "sv=1&sig=secret"),
                                           (" ?sv=1&sig=secret ", "sv=1&sig=secret")])
def test_storage_sas_normalization(token, expected):
    settings = _settings(azure_storage_sas_token=token)
    assert settings.azure_storage_sas_token == expected
    assert "sig=secret" not in repr(settings)


def test_storage_sas_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_SAS_TOKEN", "?sv=1&sig=secret")
    assert _settings().azure_storage_sas_token == "sv=1&sig=secret"


@pytest.mark.parametrize("token", ["?", " ?  "])
def test_storage_sas_requires_token_after_prefix(token):
    with pytest.raises(ValidationError, match="AZURE_STORAGE_SAS_TOKEN"):
        _settings(azure_storage_sas_token=token)


def test_storage_url_query_is_rejected_without_exposing_secret():
    with pytest.raises(ValidationError) as exc:
        _settings(azure_storage_account_url="https://fake.blob.core.windows.net/?sig=secret")
    assert "AZURE_STORAGE_ACCOUNT_URL" in str(exc.value)
    assert "sig=secret" not in str(exc.value)


def test_storage_sas_not_exposed_in_other_validation_errors():
    with pytest.raises(ValidationError) as exc:
        _settings(azure_storage_sas_token="sv=1&sig=secret", servicebus_queue_name=" ")
    assert "sig=secret" not in str(exc.value)
