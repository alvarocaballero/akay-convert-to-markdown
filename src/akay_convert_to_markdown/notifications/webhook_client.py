"""HTTP webhook client with a small local retry policy."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import CallbackNotConfiguredError, WebhookError

_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class WebhookClient:
    """Sends JSON webhook notifications to the configured callback URLs.

    Only transient conditions (timeouts, network errors, HTTP 408/429/5xx) are
    retried. Normal client errors such as 400/401/403/404 fail immediately.

    The destination URL is resolved exclusively from the callback identifier
    mapping; Service Bus messages never supply a URL.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()
        self._callbacks = settings.webhook_callbacks

    def resolve_url(self, callback: str) -> str | None:
        """Return the configured URL for a callback, or ``None`` if unknown."""
        return self._callbacks.get(callback)

    def is_configured(self, callback: str) -> bool:
        """Whether a callback identifier is present in configuration."""
        return callback in self._callbacks

    async def send(self, callback: str, payload: dict[str, Any], idempotency_key: str) -> None:
        url = self.resolve_url(callback)
        if url is None:
            raise CallbackNotConfiguredError(f"Callback '{callback}' is not configured.")

        headers = {
            "Content-Type": "application/json",
            "X-Akay-Webhook-Key": self._settings.webhook_api_key,
            "Idempotency-Key": idempotency_key,
        }

        last_error: Exception | None = None
        for attempt in range(1, self._settings.webhook_retry_count + 1):
            try:
                response = await self._client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._settings.webhook_timeout_seconds,
                )
            except httpx.RequestError as exc:
                last_error = exc
            else:
                if 200 <= response.status_code < 300:
                    return
                if response.status_code in _TRANSIENT_STATUS_CODES:
                    last_error = WebhookError(f"Webhook returned transient status {response.status_code}.")
                else:
                    raise WebhookError(f"Webhook returned {response.status_code}.")

            if attempt < self._settings.webhook_retry_count:
                await asyncio.sleep(self._settings.webhook_retry_delay_seconds)

        raise WebhookError("Webhook delivery failed after retries.") from last_error

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
