"""Azure OpenAI's pinned REST embeddings API over the existing HTTPX dependency."""

import asyncio
from collections.abc import Awaitable, Callable

import httpx
from pydantic import TypeAdapter

from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings
from akay_convert_to_markdown.contracts.base import validate_wire
from akay_convert_to_markdown.contracts.requests import IndexProfile
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError
from akay_convert_to_markdown.indexing.profiles import (
    MAX_INPUT_TOKENS, MODEL, IndexProfileError, supported_profile, validate_vectors,
)
from akay_convert_to_markdown.processing.blocking import drain_on_cancel


class AzureOpenAIEmbeddings:
    """Owns one HTTP client; Entra tokens come from an explicit async provider.

    Does not construct DefaultAzureCredential or inspect credential caches. The
    caller owns token acquisition/refresh and must configure the authorized
    resource audience. No authentication mode falls back to another mode.
    """

    def __init__(self, settings: AzureOpenAISettings, *, tokenizer,
                 token_provider: Callable[[], Awaitable[str]] | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.tokenizer = tokenizer
        self._token_provider = token_provider
        self._client = httpx.AsyncClient(timeout=settings.timeout_seconds, trust_env=False,
                                         follow_redirects=False, transport=transport)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    def binding(self, profile: IndexProfile) -> dict:
        supported_profile(profile)
        if profile.deployment != self.settings.deployment:
            raise IndexProfileError("The profile deployment does not match controlled configuration.")
        return dict(provider=profile.provider, model=profile.model, modelRevision=profile.model_revision,
                    deployment=profile.deployment, dimensions=profile.dimensions, tokenizer=profile.tokenizer,
                    endpoint=self.settings.endpoint, preprocessing="contextualized-v1")

    async def embed(self, texts: list[str], profile: IndexProfile) -> list[list[float]]:
        self.binding(profile)
        if not isinstance(texts, list) or not texts or any(not isinstance(t, str) or not t.strip() for t in texts):
            raise PermanentError("Embedding inputs must be a nonempty list of nonblank text.", code="INVALID_EMBEDDING_INPUT")
        texts = list(texts)
        counts = await drain_on_cancel(lambda: [self.tokenizer.count_tokens(text) for text in texts])
        if any(c <= 0 or c > min(profile.max_chunk_tokens, MAX_INPUT_TOKENS) for c in counts):
            raise PermanentError("Embedding inputs exceed the configured token budget.", code="CHUNK_TOKEN_LIMIT")
        # Validate the WHOLE call before sending its first batch.
        result, batch, total = [], [], 0
        for text, count in zip(texts, counts):
            if batch and (len(batch) >= self.settings.batch_size or total + count > self.settings.max_batch_tokens):
                result.extend(await self._request(batch, profile))
                batch, total = [], 0
            batch.append(text)
            total += count
        result.extend(await self._request(batch, profile))
        return result

    async def _headers(self):
        if self.settings.auth_mode == "apiKey":
            return {"api-key": self.settings.api_key.get_secret_value()}
        if self._token_provider is None:
            raise TransientError("Entra authentication requires an explicitly configured token provider.")
        try:
            token = await self._token_provider()
            if not isinstance(token, str) or not token.strip() or any(c.isspace() for c in token):
                raise ValueError()
            return {"Authorization": f"Bearer {token}"}
        except Exception:
            raise TransientError("Embedding authentication could not be obtained.") from None

    async def _request(self, texts, profile):
        url = f"{self.settings.endpoint}/openai/deployments/{self.settings.deployment}/embeddings"
        for attempt in range(self.settings.retry_count):
            headers = await self._headers()
            retry = False
            try:
                async with self._client.stream("POST", url, params={"api-version": self.settings.api_version},
                                                headers=headers,
                                                json={"input": texts, "dimensions": profile.dimensions,
                                                      "encoding_format": "float"}) as response:
                    status = response.status_code
                    if status in {408, 429} or status >= 500:
                        retry = True
                    elif status in {401, 403, 404}:
                        raise TransientError("Embedding endpoint, deployment or authentication needs configuration.")
                    elif status != 200:
                        raise PermanentError("The embedding request was rejected.", code="EMBEDDING_REQUEST_REJECTED")
                    else:
                        raw = bytearray()
                        async for data in response.aiter_bytes():
                            raw.extend(data)
                            if len(raw) > self.settings.max_response_bytes:
                                raise TransientError("The embedding response exceeded its size limit.")
                        return self._decode(bytes(raw), len(texts), profile.dimensions)
            except httpx.TransportError:
                retry = True
            if retry and attempt + 1 < self.settings.retry_count:
                await asyncio.sleep(min(30, self.settings.retry_delay_seconds * 2 ** attempt))
        raise TransientError("The embedding service is temporarily unavailable.")

    @staticmethod
    def _decode(raw, count, dimensions):
        try:
            body = validate_wire(TypeAdapter(dict), raw)
            if body["model"] != MODEL or not isinstance(body["data"], list) or len(body["data"]) != count:
                raise ValueError()
            items = body["data"]
            indices = [item["index"] for item in items]
            if any(type(i) is not int for i in indices) or sorted(indices) != list(range(count)):
                raise ValueError()
            return validate_vectors([item["embedding"] for item in sorted(items, key=lambda i: i["index"])], count, dimensions)
        except Exception:
            raise TransientError("The embedding response is incompatible with the configured model.") from None
