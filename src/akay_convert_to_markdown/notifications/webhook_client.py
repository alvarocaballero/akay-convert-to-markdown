"""HTTP webhook client with a small local retry policy."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.errors.exceptions import WebhookError

_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class WebhookClient:
    """Sends JSON webhook notifications to Akay.Be.

    Only transient conditions (timeouts, network errors, HTTP 408/429/5xx) are
    retried. Normal client errors such as 400/401/403/404 fail immediately.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient()

    async def send(self, payload: dict[str, Any], idempotency_key: str) -> None:
        headers = {
            "Content-Type": "application/json",
            "X-Akay-Webhook-Key": self._settings.webhook_api_key,
            "Idempotency-Key": idempotency_key,
        }

        last_error: Exception | None = None
        for attempt in range(1, self._settings.webhook_retry_count + 1):
            try:
                response = await self._client.post(
                    self._settings.webhook_url,
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
