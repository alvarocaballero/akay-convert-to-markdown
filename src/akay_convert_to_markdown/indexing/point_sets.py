"""N10 point-set primitive. Callers MUST serialize mutations; N11 owns receipts.

No queue, Blob, callback delivery or index/delete ordering is implemented here.
Partial writes can be visible before completion. A successful call confirms the
entire set; replay after a partial batch converges under serialized ownership.
"""

import asyncio
import json
import warnings
from uuid import UUID, uuid5

import httpx
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException

from akay_convert_to_markdown.contracts.events import index_completed
from akay_convert_to_markdown.contracts.base import require_finite_json
from akay_convert_to_markdown.contracts.requests import IndexRequest
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError
from akay_convert_to_markdown.indexing.chunking import chunk_content
from akay_convert_to_markdown.indexing.profiles import IndexProfileError, ProfileCatalog, validate_vectors
from akay_convert_to_markdown.processing.blocking import drain_on_cancel

POINT_NAMESPACE = uuid5(UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8"), "urn:akay:content-indexer:point:v1")
_BINDING = "akayIndexV1"


def point_id(scope_key: str, content_key: str, profile_id: str, chunk_index: int) -> str:
    name = json.dumps(["point-v1", scope_key, content_key, profile_id, chunk_index], ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False)
    return str(uuid5(POINT_NAMESPACE, name))


class QdrantPointStore:
    def __init__(self, client: AsyncQdrantClient, *, retry_count=3, retry_delay_seconds=1):
        if not 1 <= retry_count <= 10 or not 0 <= retry_delay_seconds <= 30:
            raise ValueError("Invalid bounded Qdrant retry policy.")
        self.client = client
        self.retry_count = retry_count
        self.retry_delay_seconds = retry_delay_seconds

    async def _call(self, method, **kwargs):
        for attempt in range(self.retry_count):
            try:
                return await method(**kwargs)
            except UnexpectedResponse as error:
                if error.status_code not in {408, 429} and error.status_code < 500:
                    if error.status_code in {401, 403, 404}:
                        raise TransientError("The Qdrant target needs configuration.") from None
                    raise PermanentError("The Qdrant operation was rejected.", code="INDEX_TARGET_REJECTED") from None
            except (httpx.TransportError, ResponseHandlingException, TimeoutError):
                pass
            except Exception:
                raise TransientError("The Qdrant operation could not be confirmed.") from None
            if attempt + 1 < self.retry_count:
                await asyncio.sleep(min(30, self.retry_delay_seconds * 2 ** attempt))
        raise TransientError("Qdrant is temporarily unavailable.")

    async def ensure_profile(self, profile, space):
        snapshot = profile.model_dump(mode="json", by_alias=True)
        if not await self._call(self.client.collection_exists, collection_name=profile.collection):
            created = await self._call(self.client.create_collection, collection_name=profile.collection,
                                       vectors_config=models.VectorParams(size=profile.dimensions, distance=models.Distance(profile.distance)),
                                       metadata={_BINDING: {"space": space, "profiles": {profile.id: snapshot}}})
            if not created:
                raise TransientError("Collection creation was not confirmed.")
        info = await self._call(self.client.get_collection, collection_name=profile.collection)
        vectors = info.config.params.vectors
        stored = (info.config.metadata or {}).get(_BINDING)
        if (not isinstance(vectors, models.VectorParams) or vectors.size != profile.dimensions
                or vectors.distance != models.Distance(profile.distance) or not isinstance(stored, dict)
                or stored.get("space") != space or not isinstance(stored.get("profiles"), dict)):
            raise IndexProfileError("The collection is not bound to the configured embedding space.")
        previous = stored["profiles"].get(profile.id)
        if previous is not None and previous != snapshot:
            raise IndexProfileError("A used profile cannot change its effective configuration.")
        if previous is None:
            metadata = dict(info.config.metadata)
            metadata[_BINDING] = dict(space=space, profiles=stored["profiles"] | {profile.id: snapshot})
            if not await self._call(self.client.update_collection, collection_name=profile.collection, metadata=metadata):
                raise TransientError("Profile registration was not confirmed.")
        # Local Qdrant intentionally has no payload-index acceleration. Still call
        # the API so the same adapter prepares actual indexes on a server.
        for field in ["scopeKey", "contentKey", "profileId", "sectionId", "chunkIndex", "operationSequence"]:
            schema = models.PayloadSchemaType.INTEGER if field in {"chunkIndex", "operationSequence"} else models.PayloadSchemaType.KEYWORD
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Payload indexes have no effect in the local Qdrant.*")
                result = await self._call(self.client.create_payload_index, collection_name=profile.collection,
                                           field_name=field, field_schema=schema, wait=True)
            self._confirmed(result)

    @staticmethod
    def _confirmed(result):
        if result.status != models.UpdateStatus.COMPLETED:
            raise TransientError("The Qdrant write has not been confirmed complete.")

    async def upsert(self, profile, points):
        result = await self._call(self.client.upsert, collection_name=profile.collection, points=points, wait=True)
        self._confirmed(result)

    async def prune(self, request, count):
        conditions = [models.FieldCondition(key=key, match=models.MatchValue(value=value))
                      for key, value in [("scopeKey", request.scope_key), ("contentKey", request.content_key),
                                         ("profileId", request.index_profile.id)]]
        conditions.append(models.FieldCondition(key="chunkIndex", range=models.Range(gte=count)))
        result = await self._call(self.client.delete, collection_name=request.index_profile.collection,
                                   points_selector=models.Filter(must=conditions), wait=True)
        self._confirmed(result)


class PointSetIndexer:
    def __init__(self, catalog: ProfileCatalog, embeddings, store: QdrantPointStore, *, tokenizer,
                 tokenizer_id: str, batch_size: int = 32, max_chunks: int = 10000):
        if not 1 <= batch_size <= 2048 or not 1 <= max_chunks <= 100000:
            raise ValueError("Invalid indexing batch or chunk limit.")
        self.catalog, self.embeddings, self.store = catalog, embeddings, store
        self.tokenizer, self.tokenizer_id = tokenizer, tokenizer_id
        self.batch_size, self.max_chunks = batch_size, max_chunks

    async def index(self, request: IndexRequest, source_raw: str | bytes, *, review_raw: str | bytes | None = None):
        try:
            # Frozen Pydantic models are shallow; snapshot nested metadata/context
            # before the first await and reject unchecked model_copy mutations.
            data = require_finite_json(request.model_dump(mode="json", by_alias=True))
            request = IndexRequest.model_validate_json(json.dumps(data, allow_nan=False))
        except Exception:
            raise PermanentError("The indexing request is invalid.", code="INVALID_MESSAGE") from None
        profile = self.catalog.resolve(request.index_profile)
        space = self.embeddings.binding(profile)
        chunks = await drain_on_cancel(lambda: chunk_content(request, source_raw, review_raw=review_raw,
                                                              tokenizer=self.tokenizer, tokenizer_id=self.tokenizer_id))
        if len(chunks) > self.max_chunks:
            raise PermanentError("The artifact exceeds the configured chunk limit.", code="INDEX_CONTENT_TOO_LARGE")
        await self.store.ensure_profile(profile, space)
        for offset in range(0, len(chunks), self.batch_size):
            batch = chunks[offset:offset + self.batch_size]
            texts = [chunk.contextualized_text for chunk in batch]
            vectors = validate_vectors(await self.embeddings.embed(texts, profile), len(batch), profile.dimensions)
            points = []
            for chunk, vector in zip(batch, vectors):
                data = chunk.model_dump(mode="json", by_alias=True)
                payload = dict(scopeKey=request.scope_key, contentKey=request.content_key, profileId=profile.id,
                               operationSequence=request.operation_sequence, chunkIndex=chunk.chunk_index,
                               sectionId=data["sectionId"], headingPath=data["headingPath"], text=chunk.text,
                               contextualizedText=chunk.contextualized_text, source=data["source"], origin=data["origin"],
                               provenance=data["provenance"], metadata=request.metadata,
                               internalHeadings=data["internalHeadings"], resourceName=chunk.resource_name)
                points.append(models.PointStruct(id=point_id(request.scope_key, request.content_key, profile.id, chunk.chunk_index),
                                                  vector=vector, payload=payload))
            await self.store.upsert(profile, points)
        await self.store.prune(request, len(chunks))
        return index_completed(request, chunk_count=len(chunks))
