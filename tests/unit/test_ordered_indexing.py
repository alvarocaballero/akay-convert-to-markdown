"""N11: durable Blob doubles, independent coordinators and persistent local Qdrant."""

import asyncio
import importlib
import json
import socket
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from qdrant_client import AsyncQdrantClient

from akay_convert_to_markdown.contracts.requests import DeleteRequest
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError, WebhookError
from tests.unit.test_artifact_publication import MemoryBlobs
from tests.unit.test_content_indexing import make_indexer, profile, request, transcript


def deletion(job, sequence=2, **changes):
    data = dict(schema_version=1, request_id=uuid4(), operation="delete", operation_sequence=sequence,
                scope_key=job.scope_key, content_key=job.content_key,
                index_target=dict(profile_id=job.index_profile.id, collection=job.index_profile.collection),
                callback=job.callback, payload=job.payload)
    data.update(changes)
    return DeleteRequest(**data)


@pytest.fixture
def api(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("N11 must remain offline")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    return importlib.import_module("akay_convert_to_markdown.indexing.ordered")


async def harness(api, tmp_path, *, profiles=None):
    points = importlib.import_module("akay_convert_to_markdown.indexing.point_sets")
    client, store, indexer = await make_indexer(points, tmp_path / "qdrant", profiles=profiles)
    blobs = MemoryBlobs()
    load = AsyncMock(return_value=(json.dumps(transcript()), None))
    notify = AsyncMock()

    def coordinator():
        return api.OrderedIndexer(blobs, indexer, state_container="technical", state_prefix="index-state",
                                  source_container="artifacts", target_identity="synthetic-qdrant")

    return client, store, indexer, blobs, load, notify, coordinator


async def test_index_delete_stale_reassignment_and_persistent_replay(api, tmp_path):
    client, _, indexer, blobs, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    try:
        await coordinator().deliver(job, load, notify)
        calls = len(indexer.embeddings.calls)
        await coordinator().deliver(job, load, notify)
        assert len(indexer.embeddings.calls) == calls and notify.await_count == 1
        await coordinator().deliver(deletion(job), load, notify)
        assert (await client.count(profile().collection)).count == 0
        await coordinator().deliver(job, load, notify)
        assert notify.call_args.args[1]["eventType"] == "content.index.operation.superseded"
        assert notify.call_args.args[1]["currentOperationSequence"] == 2
        assert len(indexer.embeddings.calls) == calls
        fixed = request(requestId=str(uuid4()), operationSequence=3,
                        sectionContext=dict(mode="fixed", sectionId=str(uuid4()), headingPath=["Reassigned"]))
        await coordinator().deliver(fixed, load, notify)
        points, _ = await client.scroll(profile().collection)
        assert points and all(p.payload["headingPath"] == ["Reassigned"] for p in points)
        assert all(p.payload["operationSequence"] == 3 for p in points)
        assert not [call for call in blobs.calls if call[0] == "delete"]
    finally:
        await client.close()
    # Actual point persistence plus newly constructed coordination objects.
    client = AsyncQdrantClient(path=str(tmp_path / "qdrant"))
    try:
        assert (await client.count(profile().collection)).count > 0
    finally:
        await client.close()


@pytest.mark.parametrize("change", [dict(requestId=str(uuid4())), dict(metadata={"different": True}),
                                     dict(operationSequence=3)])
async def test_conflicting_sequence_or_reused_request_never_mutates(api, tmp_path, change):
    client, _, indexer, _, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    try:
        await coordinator().deliver(job, load, notify)
        calls = len(indexer.embeddings.calls)
        changed = request(**(job.model_dump(mode="json", by_alias=True) | change))
        await coordinator().deliver(changed, load, notify)
        assert notify.call_args.args[1]["error"]["code"] == "INDEX_OPERATION_CONFLICT"
        assert len(indexer.embeddings.calls) == calls
    finally:
        await client.close()


async def test_callback_failure_and_completed_receipt_failure_do_not_repeat_embeddings(api, tmp_path):
    client, _, indexer, blobs, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    notify.side_effect = [WebhookError("unavailable"), None]
    try:
        with pytest.raises(WebhookError):
            await coordinator().deliver(job, load, notify)
        count = len(indexer.embeddings.calls)
        load.side_effect = AssertionError("ready replay must not reload artifacts")
        await coordinator().deliver(job, load, notify)
        assert len(indexer.embeddings.calls) == count
        assert notify.call_args_list[0].args == notify.call_args_list[1].args
        assert notify.call_args.args[2] == f"{job.request_id}:content.indexing.completed"
    finally:
        await client.close()


async def test_delete_is_exact_and_repeated_absent_delete_succeeds(api, tmp_path):
    other_profile = profile(id="second", collection="second-collection")
    client, _, _, _, load, notify, coordinator = await harness(api, tmp_path, profiles=[profile(), other_profile])
    job = request()
    try:
        for item in [job, request(requestId=str(uuid4()), scopeKey="other-scope"),
                     request(requestId=str(uuid4()), contentKey="other-content")]:
            if item.content_key == "other-content":
                artifact = transcript()
                artifact["contentKey"] = item.content_key
                load.return_value = (json.dumps(artifact), None)
            else:
                load.return_value = (json.dumps(transcript()), None)
            await coordinator().deliver(item, load, notify)
        load.return_value = (json.dumps(transcript()), None)
        # A second target for the same content is retained for explicit cleanup.
        migrated = request(requestId=str(uuid4()), operationSequence=2,
                           indexProfile=other_profile.model_dump(mode="json", by_alias=True))
        await coordinator().deliver(migrated, load, notify)
        await coordinator().deliver(deletion(job, 3), load, notify)
        await coordinator().deliver(deletion(job, 4), load, notify)
        points, _ = await client.scroll(profile().collection, limit=100)
        assert points and all((p.payload["scopeKey"], p.payload["contentKey"]) != (job.scope_key, job.content_key) for p in points)
        assert (await client.count(other_profile.collection)).count > 0
        await coordinator().deliver(job, load, notify)
        assert notify.call_args.args[1]["eventType"].endswith("superseded")
        bad = deletion(job, 5, index_target=dict(profile_id="unknown", collection=profile().collection))
        await coordinator().deliver(bad, load, notify)
        assert notify.call_args.args[1]["eventType"] == "content.index.deletion.failed"
    finally:
        await client.close()


async def test_lease_takeover_cannot_admit_delete_while_old_qdrant_write_runs(api, tmp_path):
    client, _, _, blobs, load, notify, coordinator = await harness(api, tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.upsert

    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)

    client.upsert = delayed
    job = request()
    first = asyncio.create_task(coordinator().deliver(job, load, notify))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        # Simulate expiry and a different replica acquiring the leases.
        blobs.leases.clear()
        with pytest.raises(TransientError):
            await coordinator().deliver(deletion(job), load, notify)
        assert not notify.await_count
        release.set()
        with pytest.raises(TransientError):
            await first
        await coordinator().deliver(deletion(job), load, notify)
        await coordinator().deliver(job, load, notify)
        assert (await client.count(profile().collection)).count == 0
        assert notify.call_args.args[1]["eventType"].endswith("superseded")
    finally:
        release.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await client.close()


async def test_ambiguous_qdrant_response_blocks_takeover_instead_of_resurrecting(api, tmp_path):
    client, _, _, _, load, notify, coordinator = await harness(api, tmp_path)
    original = client.upsert

    async def lost_response(**kwargs):
        await original(**kwargs)
        raise TimeoutError("response lost")

    client.upsert = lost_response
    job = request()
    try:
        with pytest.raises(TransientError):
            await coordinator().deliver(job, load, notify)
        client.upsert = original
        for item in [job, deletion(job)]:
            with pytest.raises(TransientError, match="uncertain"):
                await coordinator().deliver(item, load, notify)
        assert notify.await_count == 0
    finally:
        await client.close()


async def test_permanent_preparation_failure_is_frozen_for_callback_retry(api, tmp_path):
    client, _, _, _, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    load.side_effect = PermanentError("Safe input failure.", code="INVALID_ARTIFACT")
    notify.side_effect = [WebhookError("unavailable"), None]
    try:
        with pytest.raises(WebhookError):
            await coordinator().deliver(job, load, notify)
        await coordinator().deliver(job, load, notify)
        assert load.await_count == 1
        assert notify.call_args.args[1]["error"]["code"] == "INVALID_ARTIFACT"
    finally:
        await client.close()


@pytest.mark.parametrize("after_commit", [False, True])
async def test_final_receipt_failure_recovers_confirmed_commands_without_reembedding(api, tmp_path, after_commit):
    client, _, indexer, blobs, load, notify, coordinator = await harness(api, tmp_path)
    original = blobs.get_blob_client
    failed = False

    def get_blob(container, name):
        blob = original(container, name)
        upload = blob.upload_blob

        async def intercepted(data, **kwargs):
            nonlocal failed
            if "/contents/" in name and json.loads(data).get("event") and not failed:
                failed = True
                if after_commit:
                    await upload(data, **kwargs)
                raise OSError("final receipt unavailable")
            return await upload(data, **kwargs)
        blob.upload_blob = intercepted
        return blob

    blobs.get_blob_client = get_blob
    job = request()
    try:
        with pytest.raises(TransientError):
            await coordinator().deliver(job, load, notify)
        calls = len(indexer.embeddings.calls)
        load.side_effect = AssertionError("frozen input must be reused")
        upsert = client.upsert
        client.upsert = AsyncMock(side_effect=AssertionError("confirmed point writes must be reused"))
        await coordinator().deliver(job, load, notify)
        assert len(indexer.embeddings.calls) == calls
        assert notify.await_count == 1
        client.upsert = upsert
    finally:
        await client.close()


async def test_cancelled_writer_drains_before_delete_and_never_sends_success(api, tmp_path):
    client, _, _, blobs, load, notify, coordinator = await harness(api, tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.upsert

    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)

    client.upsert = delayed
    job = request()
    task = asyncio.create_task(coordinator().deliver(job, load, notify))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        assert not task.done() and blobs.leases
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not notify.await_count and not blobs.leases
        await coordinator().deliver(deletion(job), load, notify)
        assert (await client.count(profile().collection)).count == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()


async def test_processor_consumes_strict_index_contract_and_settles_after_callback(api, tmp_path):
    from akay_convert_to_markdown.storage.blob_storage import BlobStorage
    from tests.helpers import FakeWebhook, make_settings
    from tests.unit.test_consumer import FakeMessage, FakeReceiver, _make_consumer

    processor_api = importlib.import_module("akay_convert_to_markdown.processing.index_processor")
    client, _, _, blobs, _, _, coordinator = await harness(api, tmp_path)
    job = request()
    settings = make_settings(source_container_name="artifacts", webhook_callbacks={job.callback: "https://callback.invalid"})
    await blobs.get_blob_client("artifacts", job.source.blob_name).upload_blob(json.dumps(transcript()).encode())
    webhook = FakeWebhook(settings.webhook_callbacks)
    processor = processor_api.IndexProcessor(settings, BlobStorage(blobs), coordinator(), webhook)
    try:
        assert processor.parse_message(job.model_dump_json()) == job
        message = FakeMessage(job.model_dump_json().encode())
        receiver = FakeReceiver()
        consumer = _make_consumer(settings, processor)
        await consumer._handle_message(receiver, message)
        assert receiver.completed == [message] and not receiver.abandoned
        assert webhook.calls[0][1]["eventType"] == "content.indexing.completed"
    finally:
        await client.close()


def test_runtime_configuration_is_explicit_and_separate_from_other_workers():
    from akay_convert_to_markdown.config.indexing_settings import IndexRuntimeSettings
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        IndexRuntimeSettings(_env_file=None)
    values = dict(state_container="technical", state_prefix="index-state", profiles=[profile()],
                  tokenizer_path="synthetic.tiktoken", qdrant_url="http://localhost:6333", qdrant_auth_mode="none")
    assert IndexRuntimeSettings(**values).profiles == [profile()]
    with pytest.raises(ValidationError):
        IndexRuntimeSettings(**(values | dict(qdrant_auth_mode="apiKey")))
    with pytest.raises(ValidationError):
        IndexRuntimeSettings(**(values | dict(qdrant_url="https://user:secret@target.invalid")))


async def test_used_profile_cannot_move_collection_and_old_target_remains_deletable(api, tmp_path):
    from akay_convert_to_markdown.indexing.profiles import ProfileCatalog

    client, _, indexer, _, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    try:
        await coordinator().deliver(job, load, notify)
        changed = profile(collection="illegal-rebind")
        indexer.catalog = ProfileCatalog([changed])
        await coordinator().deliver(request(requestId=str(uuid4()), operationSequence=2,
                                             indexProfile=changed.model_dump(mode="json", by_alias=True)), load, notify)
        assert notify.call_args.args[1]["error"]["code"] == "INDEX_PROFILE_INCOMPATIBLE"
        assert not await client.collection_exists(changed.collection)
        # Even if the old profile is retired from current configuration, its
        # recorded destination must still permit explicit cleanup.
        indexer.catalog = ProfileCatalog([profile(id="new", collection="new-collection")])
        await coordinator().deliver(deletion(job, 3), load, notify)
        assert (await client.count(profile().collection)).count == 0
    finally:
        await client.close()


async def test_partial_batch_resume_reuses_frozen_input_and_confirmed_embeddings(api, tmp_path):
    client, _, indexer, blobs, load, notify, coordinator = await harness(api, tmp_path)
    indexer.batch_size = 1
    load.return_value = (json.dumps(transcript([dict(id="s1", text="word " * 150,
                                                    startMilliseconds=1000, endMilliseconds=6000)])), None)
    original = client.upsert
    writes = 0

    async def expire_after_first(**kwargs):
        nonlocal writes
        writes += 1
        result = await original(**kwargs)
        if writes == 1:
            blobs.leases.clear()
        return result

    client.upsert = expire_after_first
    job = request()
    try:
        with pytest.raises(TransientError):
            await coordinator().deliver(job, load, notify)
        confirmed_embeddings = len(indexer.embeddings.calls)
        assert confirmed_embeddings == 1 and writes == 1
        load.side_effect = AssertionError("artifact content must stay frozen")
        await coordinator().deliver(job, load, notify)
        assert writes >= len(indexer.embeddings.calls) > 1
        assert len({json.dumps(texts) for texts in indexer.embeddings.calls}) == len(indexer.embeddings.calls)
        assert (await client.count(profile().collection)).count == writes
        assert notify.await_count == 1
    finally:
        await client.close()


@pytest.mark.parametrize("operation", ["index", "delete"])
async def test_invalid_index_jobs_notify_only_recoverable_index_fields(api, tmp_path, operation):
    from akay_convert_to_markdown.processing.index_processor import IndexProcessor
    from akay_convert_to_markdown.storage.blob_storage import BlobStorage
    from tests.helpers import FakeWebhook, make_settings
    from tests.unit.test_consumer import FakeMessage, FakeReceiver, _make_consumer

    client, _, _, blobs, _, _, coordinator = await harness(api, tmp_path)
    job = request() if operation == "index" else deletion(request())
    fields = job.model_dump(mode="json", by_alias=True)
    fields["unexpected"] = True
    settings = make_settings(webhook_callbacks={job.callback: "https://callback.invalid"})
    webhook = FakeWebhook(settings.webhook_callbacks)
    processor = IndexProcessor(settings, BlobStorage(blobs), coordinator(), webhook)
    try:
        message, receiver = FakeMessage(json.dumps(fields)), FakeReceiver()
        await _make_consumer(settings, processor)._handle_message(receiver, message)
        event = webhook.calls[0][1]
        assert event["eventType"] == ("content.indexing.failed" if operation == "index" else "content.index.deletion.failed")
        assert event["operationSequence"] == job.operation_sequence and event["scopeKey"] == job.scope_key
        assert event["contentKey"] == job.content_key and event["payload"] == job.payload
        assert "source" not in event and receiver.completed == [message]
        assert not blobs.data
    finally:
        await client.close()


async def test_delete_before_first_index_is_idempotent_without_creating_collection(api, tmp_path):
    client, _, indexer, _, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    try:
        delete = deletion(job)
        await coordinator().deliver(delete, load, notify)
        await coordinator().deliver(delete, load, notify)
        await coordinator().deliver(job, load, notify)
        assert not await client.collection_exists(profile().collection)
        assert not indexer.embeddings.calls and not load.await_count
        assert notify.await_count == 2
    finally:
        await client.close()


async def test_real_entry_composition_uses_only_explicit_index_configuration(api, tmp_path, monkeypatch):
    from akay_convert_to_markdown import index_main
    from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings, IndexRuntimeSettings
    from akay_convert_to_markdown.indexing import azure_embeddings, tokenizer
    from akay_convert_to_markdown.storage.blob_storage import BlobStorage
    from tests.helpers import FakeWebhook, make_settings, make_logger
    from tests.unit.test_content_chunking import CharacterTokenizer
    import qdrant_client

    client, _, indexer, blobs, _, _, _ = await harness(api, tmp_path)
    embeddings = indexer.embeddings
    embeddings.__aexit__ = AsyncMock()
    captured = {}

    def qdrant(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr(qdrant_client, "AsyncQdrantClient", qdrant)
    monkeypatch.setattr(tokenizer.Cl100kTokenizer, "from_file", lambda _: CharacterTokenizer(limit=8192))
    monkeypatch.setattr(azure_embeddings, "AzureOpenAIEmbeddings", lambda *args, **kwargs: embeddings)
    config = IndexRuntimeSettings(state_container="technical", state_prefix="index-state", profiles=[profile()],
                                  tokenizer_path=tmp_path / "explicit.tiktoken", qdrant_url="http://localhost:6333",
                                  qdrant_auth_mode="none")
    azure = AzureOpenAISettings(endpoint="https://synthetic.openai.azure.com", deployment="synthetic-deployment",
                                auth_mode="apiKey", api_key="synthetic-key")
    job = request()
    settings = make_settings(source_container_name="artifacts", webhook_callbacks={job.callback: "https://callback.invalid"})
    storage, webhook = BlobStorage(blobs), FakeWebhook(settings.webhook_callbacks)
    await blobs.get_blob_client("artifacts", job.source.blob_name).upload_blob(json.dumps(transcript()).encode())
    processor, close = index_main.build_processor(settings, storage, webhook, make_logger(), config=config, embedding_settings=azure)
    try:
        await processor.process(job)
        assert webhook.calls[-1][1]["eventType"] == "content.indexing.completed"
        assert captured["url"] == config.qdrant_url and captured["trust_env"] is False
        assert captured["check_compatibility"] is False and captured["api_key"] is None
    finally:
        await close()
    embeddings.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("lie_about_size", [False, True])
async def test_saved_artifact_download_bounds_declared_and_actual_bytes(api, lie_about_size):
    from akay_convert_to_markdown.storage.blob_storage import BlobStorage
    from akay_convert_to_markdown.errors.exceptions import DocumentTooLargeError

    blobs = MemoryBlobs()
    await blobs.get_blob_client("artifacts", "source.json").upload_blob(b"x" * 11)
    if lie_about_size:
        get_blob = blobs.get_blob_client

        def misleading(*args):
            blob = get_blob(*args)
            download = blob.download_blob

            async def altered(**kwargs):
                result = await download(**kwargs)
                result.properties.size = 1
                return result
            blob.download_blob = altered
            return blob
        blobs.get_blob_client = misleading
    with pytest.raises(DocumentTooLargeError):
        await BlobStorage(blobs).read_bytes("artifacts", "source.json", max_bytes=10)


async def test_main_activates_only_after_explicit_runtime_validation(monkeypatch):
    from akay_convert_to_markdown import index_main, worker_runtime
    from akay_convert_to_markdown.config import indexing_settings
    from tests.helpers import make_settings

    settings = make_settings()
    config = object()
    azure = indexing_settings.AzureOpenAISettings(endpoint="https://synthetic.openai.azure.com",
                                                  deployment="synthetic-deployment", auth_mode="apiKey", api_key="synthetic")
    monkeypatch.setattr(index_main, "IndexerSettings", lambda: settings)
    monkeypatch.setattr(indexing_settings, "IndexRuntimeSettings", lambda: config)
    monkeypatch.setattr(indexing_settings, "AzureOpenAISettings", lambda: azure)
    called = []

    def run(settings, build, name):
        called.append((settings, build, name))
        return 0
    monkeypatch.setattr(worker_runtime, "run_main", run)
    assert index_main.main() == 0
    assert called[0][1].keywords == dict(config=config, embedding_settings=azure)


async def test_request_id_cannot_be_reused_for_a_different_content_in_same_target(api, tmp_path):
    client, _, indexer, _, load, notify, coordinator = await harness(api, tmp_path)
    job = request()
    try:
        await coordinator().deliver(job, load, notify)
        count = len(indexer.embeddings.calls)
        changed = request(**(job.model_dump(mode="json", by_alias=True) | dict(contentKey="different-content")))
        await coordinator().deliver(changed, load, notify)
        assert notify.call_args.args[1]["error"]["code"] == "INDEX_OPERATION_CONFLICT"
        assert len(indexer.embeddings.calls) == count
    finally:
        await client.close()


async def test_lost_pending_receipt_response_before_dispatch_does_not_quarantine_safe_work(api, tmp_path):
    client, _, indexer, blobs, load, notify, coordinator = await harness(api, tmp_path)
    original = blobs.get_blob_client
    failed = False

    def get_blob(container, name):
        blob = original(container, name)
        upload = blob.upload_blob

        async def intercepted(data, **kwargs):
            nonlocal failed
            if "/lanes/" in name and json.loads(data).get("pending") and not failed:
                failed = True
                await upload(data, **kwargs)
                raise OSError("pending receipt response lost before dispatch")
            return await upload(data, **kwargs)
        blob.upload_blob = intercepted
        return blob

    blobs.get_blob_client = get_blob
    job = request()
    try:
        with pytest.raises(TransientError):
            await coordinator().deliver(job, load, notify)
        assert not await client.collection_exists(profile().collection)
        await coordinator().deliver(job, load, notify)
        assert notify.await_count == 1
    finally:
        await client.close()


@pytest.mark.parametrize("kind", ["throttled", "permanent"])
async def test_explicit_qdrant_rejections_are_not_uncertain_mutations(api, tmp_path, kind):
    import httpx
    from qdrant_client.common.client_exceptions import ResourceExhaustedResponse
    from qdrant_client.http.exceptions import UnexpectedResponse

    client, _, _, _, load, notify, coordinator = await harness(api, tmp_path)
    original = client.upsert
    failure = (ResourceExhaustedResponse("safe test throttle", 1) if kind == "throttled" else
               UnexpectedResponse(400, "Bad Request", b"private rejected response", httpx.Headers()))
    client.upsert = AsyncMock(side_effect=failure)
    job = request()
    try:
        if kind == "throttled":
            with pytest.raises(TransientError):
                await coordinator().deliver(job, load, notify)
            client.upsert = original
            await coordinator().deliver(job, load, notify)
            assert notify.call_args.args[1]["eventType"] == "content.indexing.completed"
        else:
            await coordinator().deliver(job, load, notify)
            assert notify.call_args.args[1]["error"]["code"] == "INDEX_TARGET_REJECTED"
            assert "private rejected response" not in json.dumps(notify.call_args.args)
    finally:
        await client.close()
