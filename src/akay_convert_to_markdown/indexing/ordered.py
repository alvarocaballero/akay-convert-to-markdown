"""Durable ordered index/delete delivery over the N10 point-set API.

Blob leases do NOT fence Qdrant. An immutable acknowledgement of each in-flight
mutation is required before another lease holder can advance. Ambiguous transport
outcomes remain quarantined instead of making an unsafe automatic takeover.
"""

import asyncio
from contextlib import asynccontextmanager, suppress
from hashlib import sha256
import json
from uuid import uuid4

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from pydantic import Field
from qdrant_client import models
from qdrant_client.common.client_exceptions import ResourceExhaustedResponse
from qdrant_client.http.exceptions import UnexpectedResponse

from akay_convert_to_markdown.contracts.base import Contract, blob_name, require_finite_json
from akay_convert_to_markdown.contracts.events import idempotency_key, index_completed, index_superseded, request_failed
from akay_convert_to_markdown.contracts.ordering import IndexReceipt, RequestIdentity, index_admission
from akay_convert_to_markdown.contracts.requests import DeleteRequest, IndexRequest, REQUEST_ADAPTERS
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError
from akay_convert_to_markdown.indexing.point_sets import PointSetIndexer, QdrantPointStore
from akay_convert_to_markdown.indexing.profiles import IndexProfileError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.blocking import await_cleanup, drain_task


def canonical(value):
    require_finite_json(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


class _ContentState(Contract):
    key: list[str]
    source_container: str
    receipt: IndexReceipt | None = None
    inputs: str | None = None
    event: dict | None = None
    notified: list[str] = Field(default_factory=list)
    targets: dict[str, str] = Field(default_factory=dict)


class _Lane(Contract):
    target: str
    pending: str | None = None
    profiles: dict[str, str] = Field(default_factory=dict)
    requests: dict[str, str] = Field(default_factory=dict)


@asynccontextmanager
async def ownership(blob, renewal_seconds=20):
    """Finite lease, retained until all owned work has drained."""
    lease = await blob.acquire_lease(lease_duration=60)
    stop, lost = asyncio.Event(), asyncio.Event()

    async def guard():
        if lost.is_set():
            raise TransientError("Index coordination ownership was lost.")
        try:
            await lease.renew()
        except Exception:
            lost.set()
            raise TransientError("Index coordination ownership was lost.") from None

    async def renew():
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), renewal_seconds)
            except TimeoutError:
                try:
                    await guard()
                except TransientError:
                    return

    heartbeat = asyncio.create_task(renew())
    try:
        yield lease, guard
    finally:
        async def release():
            stop.set()
            await drain_task(heartbeat)
            with suppress(Exception):
                await lease.release()
        await await_cleanup(release())


class _JournalStore(QdrantPointStore):
    """All mutating N10 client calls go through the durable lane; no write retries."""

    mutations = {"create_collection", "update_collection", "create_payload_index", "upsert", "delete"}

    def __init__(self, original, command):
        super().__init__(original.client, retry_count=original.retry_count,
                         retry_delay_seconds=original.retry_delay_seconds)
        self.command = command

    async def _call(self, method, **kwargs):
        operation = next((name for name in self.mutations if method == getattr(self.client, name)), None)
        if operation is None:
            return await super()._call(method, **kwargs)
        if operation in {"upsert", "delete", "create_payload_index"}:
            kwargs["ordering"] = models.WriteOrdering.STRONG
        return await self.command(operation, method, kwargs)


class _CachedEmbeddings:
    def __init__(self, original, read, write, prefix, guard):
        self.original, self.read, self.write, self.prefix, self.guard = original, read, write, prefix, guard

    def binding(self, profile):
        return self.original.binding(profile)

    async def embed(self, texts, profile):
        key = f"{self.prefix}/embeddings/{digest([self.binding(profile), texts])}.json"
        cached = await self.read(key)
        if cached is not None:
            return cached["vectors"]
        await self.guard()
        from akay_convert_to_markdown.indexing.profiles import validate_vectors

        vectors = validate_vectors(await self.original.embed(texts, profile), len(texts), profile.dimensions)
        await self.guard()
        await self.write(key, {"vectors": vectors})
        return vectors


class OrderedIndexer:
    """One explicit Qdrant target/state namespace shared by ALL cooperating writers.

    A target-wide finite leased lane serializes metadata and point mutations. Each
    scope/content has a separate leased, conditional admission receipt, independent
    of profile. This conservative lane favors correctness over parallel throughput.
    """

    renewal_seconds = 20

    def __init__(self, client, indexer: PointSetIndexer, *, state_container: str, state_prefix: str,
                 source_container: str, target_identity: str, max_record_bytes=128 * 1024 * 1024):
        if not all(isinstance(v, str) and v.strip() for v in
                   (state_container, state_prefix, source_container, target_identity)):
            raise ValueError("Explicit shared index state and target configuration is required.")
        blob_name(state_prefix)
        self.client, self.indexer = client, indexer
        self.container, self.prefix, self.source = state_container, state_prefix, source_container
        self.target, self.max_bytes = target_identity, max_record_bytes

    def _blob(self, name):
        return self.client.get_blob_client(self.container, name)

    async def _read_blob(self, blob, **kwargs):
        download = await blob.download_blob(**kwargs)
        if download.properties.size > self.max_bytes:
            raise TransientError("Index technical state exceeds its configured limit.")
        raw = bytearray()
        async for part in download.chunks():
            raw.extend(part)
            if len(raw) > self.max_bytes:
                raise TransientError("Index technical state exceeds its configured limit.")
        # Technical records are written by this component, never caller URLs.
        return bytes(raw), download.properties.etag

    async def _read(self, name):
        try:
            raw, _ = await self._read_blob(self._blob(name))
            value = json.loads(raw)
            require_finite_json(value)
            return value
        except ResourceNotFoundError:
            return None

    async def _immutable(self, name, value):
        raw = canonical(value).encode()
        if len(raw) > self.max_bytes:
            raise PermanentError("The index preparation exceeds its configured size limit.", code="INDEX_CONTENT_TOO_LARGE")
        # Lost Blob responses are recovered by an exact read, not another mutation
        # of Qdrant. Only owned technical keys are ever written; none are deleted.
        for _ in range(3):
            try:
                await self._blob(name).upload_blob(raw, overwrite=False)
                return
            except Exception:
                existing = await self._read(name)
                if existing is not None:
                    if canonical(existing) != raw.decode():
                        raise TransientError("Immutable index preparation conflicts with its stored identity.")
                    return
        raise TransientError("Index mutation acknowledgement could not be stored.")

    async def _create(self, blob, model):
        try:
            await blob.upload_blob(model.model_dump_json().encode(), overwrite=False)
        except ResourceExistsError:
            pass

    async def deliver(self, request, load, notify):
        # Reject unchecked/nonfinite nested mutations before the first await.
        snapshot = RequestIdentity.capture(request)
        request = REQUEST_ADAPTERS["index"].validate_json(snapshot.canonical_request)
        try:
            return await self._deliver(request, load, notify)
        except (PermanentError, TransientError):
            raise
        except Exception:
            raise TransientError("Index coordination could not be completed.") from None

    async def _deliver(self, request, load, notify):
        lane_blob = self._blob(f"{self.prefix}/lanes/{digest(self.target)}.json")
        await self._create(lane_blob, _Lane(target=self.target))
        async with ownership(lane_blob, self.renewal_seconds) as (lane_lease, lane_guard):
            raw, lane_etag = await self._read_blob(lane_blob, lease=lane_lease)
            lane = _Lane.model_validate_json(raw)
            if lane.target != self.target:
                raise TransientError("Index state belongs to another target.")

            async def save_lane(**changes):
                nonlocal lane, lane_etag
                await lane_guard()
                updated = lane.model_copy(update=changes)
                response = await lane_blob.upload_blob(updated.model_dump_json().encode(), overwrite=True,
                                                       lease=lane_lease, etag=lane_etag,
                                                       match_condition=MatchConditions.IfNotModified)
                lane, lane_etag = updated, response["etag"]

            if lane.pending:
                settled = await self._read(lane.pending)
                if settled != {"settled": True}:
                    raise TransientError("A previous Qdrant mutation has an uncertain outcome; recovery is required.")
                await save_lane(pending=None)

            key = [self.target, request.scope_key, request.content_key]
            content_blob = self._blob(f"{self.prefix}/contents/{digest(key)}.json")
            await self._create(content_blob, _ContentState(key=key, source_container=self.source))
            async with ownership(content_blob, self.renewal_seconds) as (lease, content_guard):
                raw, etag = await self._read_blob(content_blob, lease=lease)
                state = _ContentState.model_validate_json(raw)
                if state.key != key or state.source_container != self.source:
                    raise TransientError("Index state does not match the configured content source/target.")

                async def guard():
                    await lane_guard()
                    await content_guard()

                async def save(**changes):
                    nonlocal state, etag
                    await guard()
                    updated = state.model_copy(update=changes)
                    response = await content_blob.upload_blob(updated.model_dump_json().encode(), overwrite=True,
                                                              lease=lease, etag=etag,
                                                              match_condition=MatchConditions.IfNotModified)
                    state, etag = updated, response["etag"]

                identity = RequestIdentity.capture(request)
                registered = lane.requests.get(str(request.request_id))
                admission = ("conflict" if registered is not None and registered != identity.canonical_request
                             else index_admission(request, state.receipt))
                if admission == "conflict":
                    event = request_failed(request, code="INDEX_OPERATION_CONFLICT",
                                           message="The operation identity or sequence conflicts with an admitted request.")
                    await guard()
                    await notify(request.callback, event.model_dump(mode="json", by_alias=True), idempotency_key(event))
                    return ProcessingResult.FAILED_PERMANENT
                if admission == "superseded":
                    event = index_superseded(request, current_operation_sequence=state.receipt.request().operation_sequence)
                    notification = idempotency_key(event)
                    if notification not in state.notified:
                        await guard()
                        await notify(request.callback, event.model_dump(mode="json", by_alias=True), notification)
                        await save(notified=[*state.notified, notification])
                    return ProcessingResult.COMPLETED
                if admission == "admit":
                    await save_lane(requests=lane.requests | {str(request.request_id): identity.canonical_request})
                    previous = [] if state.receipt is None else [*state.receipt.previous_requests, state.receipt.identity]
                    receipt = IndexReceipt(identity=RequestIdentity.capture(request), status="admitted", previous_requests=previous)
                    await save(receipt=receipt, inputs=None, event=None)

                prefix = f"{self.prefix}/operations/{digest([key, state.receipt.identity.canonical_request])}"

                async def command(operation, method, kwargs):
                    serialized = {k: v.model_dump(mode="json") if hasattr(v, "model_dump") else
                                  [p.model_dump(mode="json") for p in v] if k == "points" else v
                                  for k, v in kwargs.items()}
                    name = f"{prefix}/commands/{digest([operation, serialized])}.json"
                    cached = await self._read(name)
                    if cached is not None:
                        return models.UpdateResult.model_validate(cached["result"]) if cached["kind"] == "update" else cached["result"]
                    await guard()
                    pending = f"{self.prefix}/inflight/{uuid4()}.json"
                    try:
                        await save_lane(pending=pending)
                    except BaseException:
                        # Dispatch has not begun. Even a lost Blob response cannot
                        # make this intent dangerous: no Qdrant call was started.
                        await await_cleanup(self._immutable(pending, {"settled": True}))
                        raise

                    async def execute():
                        try:
                            # The durable pending marker closes the check/send race:
                            # a successor cannot advance even if this guard expires.
                            await guard()
                        except BaseException:
                            await self._immutable(pending, {"settled": True})
                            raise
                        try:
                            result = await method(**kwargs)
                        except ResourceExhaustedResponse:
                            await self._immutable(pending, {"settled": True})
                            raise TransientError("Qdrant rejected the mutation due to throttling.") from None
                        except UnexpectedResponse as error:
                            status = error.status_code
                            if status is not None and 400 <= status < 500 and status != 408:
                                await self._immutable(pending, {"settled": True})
                                if status not in {401, 403, 404, 429}:
                                    raise PermanentError("The Qdrant mutation was rejected.", code="INDEX_TARGET_REJECTED") from None
                            raise TransientError("The Qdrant mutation could not be confirmed.") from None
                        # Any other exception/cancellation/WAIT_TIMEOUT is uncertain.
                        # Never retry a possibly delayed write after a successor.
                        if isinstance(result, models.UpdateResult):
                            QdrantPointStore._confirmed(result)
                            cached_result = dict(kind="update", result=result.model_dump(mode="json"))
                        elif result is True:
                            cached_result = dict(kind="bool", result=True)
                        else:
                            raise TransientError("The Qdrant mutation could not be confirmed.")
                        await self._immutable(name, cached_result)
                        await self._immutable(pending, {"settled": True})
                        return result

                    result = await await_cleanup(execute())
                    await save_lane(pending=None)
                    return result

                if state.event is None:
                    try:
                        if isinstance(request, IndexRequest):
                            self.indexer.catalog.resolve(request.index_profile)
                            # Bind embedding cache to the exact effective space.
                            space = self.indexer.embeddings.binding(request.index_profile)
                            profile_id = request.index_profile.id
                            binding = canonical([request.index_profile.model_dump(mode="json", by_alias=True), space])
                            previous = lane.profiles.get(profile_id)
                            if previous is not None and previous != binding:
                                raise IndexProfileError("A used profile cannot change its effective configuration or space.")
                            if previous is None:
                                await save_lane(profiles=lane.profiles | {profile_id: binding})
                            await save(targets=state.targets | {request.index_profile.id: request.index_profile.collection})
                            if state.inputs is None:
                                await guard()
                                source, review = await load(request)
                                values = dict(source=source.decode("utf-8") if isinstance(source, bytes) else source,
                                              review=review.decode("utf-8") if isinstance(review, bytes) else review)
                                name = f"{prefix}/inputs.json"
                                await guard()
                                await self._immutable(name, values)
                                await save(inputs=name)
                            values = await self._read(state.inputs)
                            store = _JournalStore(self.indexer.store, command)
                            embeddings = _CachedEmbeddings(self.indexer.embeddings, self._read, self._immutable, prefix, guard)
                            indexer = PointSetIndexer(self.indexer.catalog, embeddings, store, tokenizer=self.indexer.tokenizer,
                                                      tokenizer_id=self.indexer.tokenizer_id, batch_size=self.indexer.batch_size,
                                                      max_chunks=self.indexer.max_chunks)
                            event = await indexer.index(request, values["source"], review_raw=values["review"])
                            targets = state.targets | {request.index_profile.id: request.index_profile.collection}
                        else:
                            target = request.index_target
                            self.indexer.catalog.resolve_target(target, previous=state.targets)
                            store = _JournalStore(self.indexer.store, command)
                            if await store._call(store.client.collection_exists, collection_name=target.collection):
                                conditions = [models.FieldCondition(key=k, match=models.MatchValue(value=v))
                                              for k, v in [("scopeKey", request.scope_key), ("contentKey", request.content_key),
                                                           ("profileId", target.profile_id)]]
                                result = await store._call(store.client.delete, collection_name=target.collection,
                                                            points_selector=models.Filter(must=conditions), wait=True)
                                store._confirmed(result)
                            event, targets = index_completed(request), state.targets
                    except PermanentError as error:
                        event = request_failed(request, code=error.code, message=error.message)
                        targets = state.targets
                    await save(receipt=state.receipt.model_copy(update={"status": "completed"}),
                               event=event.model_dump(mode="json", by_alias=True), targets=targets)

                notification = f"{request.request_id}:{state.event['eventType']}"
                if notification not in state.notified:
                    await guard()
                    await notify(request.callback, state.event, notification)
                    await save(notified=[*state.notified, notification])
                return (ProcessingResult.FAILED_PERMANENT if state.event["eventType"].endswith("failed")
                        else ProcessingResult.COMPLETED)
