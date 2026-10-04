"""Webhook client retry and callback resolution behaviour tests."""

from __future__ import annotations

import httpx
import pytest

from akay_convert_to_markdown.errors.exceptions import CallbackNotConfiguredError, WebhookError
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from tests.helpers import make_settings


def _client(handler, settings=None) -> WebhookClient:
    transport = httpx.MockTransport(handler)
    return WebhookClient(settings or make_settings(), httpx.AsyncClient(transport=transport))


async def test_success_2xx():
    webhook = _client(lambda request: httpx.Response(200, json={"ok": True}))
    await webhook.send("subject-topic", {"eventType": "x"}, "key-1")
    await webhook.aclose()


async def test_sends_expected_headers():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request):
        seen["key"] = request.headers.get("X-Akay-Webhook-Key")
        seen["idem"] = request.headers.get("Idempotency-Key")
        return httpx.Response(200)

    webhook = _client(handler)
    await webhook.send("subject-topic", {"a": 1}, "key-1")
    await webhook.aclose()
    assert seen["key"] == "test-secret"
    assert seen["idem"] == "key-1"


async def test_two_callbacks_resolve_to_different_urls():
    settings = make_settings(
        webhook_callbacks={
            "subject-topic": "https://example.com/subject-topic",
            "student-document": "https://example.com/student-document",
        }
    )
    urls: list[str] = []

    def handler(request: httpx.Request):
        urls.append(str(request.url))
        return httpx.Response(200)

    webhook = _client(handler, settings)
    await webhook.send("subject-topic", {"a": 1}, "k1")
    await webhook.send("student-document", {"a": 1}, "k2")
    await webhook.aclose()

    assert urls == ["https://example.com/subject-topic", "https://example.com/student-document"]


async def test_unknown_callback_raises_without_http():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200)

    webhook = _client(handler)
    with pytest.raises(CallbackNotConfiguredError):
        await webhook.send("some-unknown-callback", {}, "key")
    await webhook.aclose()
    assert calls == []


async def test_arbitrary_url_cannot_bypass_config():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200)

    webhook = _client(handler)
    with pytest.raises(CallbackNotConfiguredError):
        await webhook.send("https://evil.example.com", {}, "key")
    await webhook.aclose()
    assert calls == []


@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_client_errors_are_not_retried(status):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(status)

    webhook = _client(handler)
    with pytest.raises(WebhookError):
        await webhook.send("subject-topic", {}, "key")
    await webhook.aclose()
    assert len(calls) == 1


@pytest.mark.parametrize("status", [429, 500])
async def test_transient_status_is_retried_then_succeeds(status):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) < 2:
            return httpx.Response(status)
        return httpx.Response(200)

    webhook = _client(handler)
    await webhook.send("subject-topic", {}, "key")
    await webhook.aclose()
    assert len(calls) == 2


async def test_timeout_is_retried():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        if len(calls) < 2:
            raise httpx.ReadTimeout("timed out")
        return httpx.Response(200)

    webhook = _client(handler)
    await webhook.send("subject-topic", {}, "key")
    await webhook.aclose()
    assert len(calls) == 2


async def test_retries_exhausted():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(500)

    webhook = _client(handler)
    with pytest.raises(WebhookError):
        await webhook.send("subject-topic", {}, "key")
    await webhook.aclose()
    assert len(calls) == 3  # default WEBHOOK_RETRY_COUNT
