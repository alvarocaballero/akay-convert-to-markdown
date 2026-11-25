"""N10: synthetic configuration/embeddings, real persistent local Qdrant."""

import importlib
import json
import socket
from pathlib import Path
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import httpx
import pytest
from qdrant_client import AsyncQdrantClient, models

from akay_convert_to_markdown.contracts.requests import IndexProfile
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError
from tests.unit.test_content_chunking import CharacterTokenizer, request as base_request, transcript


def profile(**updates):
    data = dict(id="synthetic-profile", provider="AzureOpenAI", model="text-embedding-3-small",
                deployment="synthetic-deployment", dimensions=1536, tokenizer="cl100k_base",
                max_chunk_tokens=160, distance="Cosine", collection="synthetic-content")
    data.update(updates)
    return IndexProfile(**data)


def request(**updates):
    data = base_request(format="transcript").model_dump(mode="json", by_alias=True)
    data["indexProfile"] = profile().model_dump(mode="json", by_alias=True)
    data.update(updates)
    return base_request(**{k: v for k, v in data.items()})


@pytest.fixture
def api(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("N10 tests must not contact application services")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    return importlib.import_module("akay_convert_to_markdown.indexing.point_sets")


@pytest.fixture
def settings():
    from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings
    return AzureOpenAISettings(_env_file=None, endpoint="https://synthetic.openai.azure.com",
                               deployment="synthetic-deployment", auth_mode="apiKey", api_key="synthetic-key",
                               retry_delay_seconds=0, batch_size=2)


class StubEmbeddings:
    """Explicit deterministic test double, never used by a runtime entry."""

    def __init__(self):
        self.calls = []
        self.error = None

    def binding(self, configured):
        return dict(provider=configured.provider, model=configured.model, modelRevision=configured.model_revision,
                    deployment=configured.deployment, dimensions=configured.dimensions, tokenizer=configured.tokenizer,
                    endpoint="https://synthetic.openai.azure.com", preprocessing="contextualized-v1")

    async def embed(self, texts, configured):
        self.calls.append(list(texts))
        if self.error:
            raise self.error
        # Nonzero, bounded, deterministic; not semantic embeddings.
        return [[float(len(text) % 11 + 1), *([0.01] * 1535)] for text in texts]


async def make_indexer(api, path, *, profiles=None, embedder=None, batch_size=2):
    client = AsyncQdrantClient(path=str(path))
    store = api.QdrantPointStore(client, retry_count=2, retry_delay_seconds=0)
    indexer = api.PointSetIndexer(api.ProfileCatalog(profiles or [profile()]), embedder or StubEmbeddings(), store,
                                  tokenizer=CharacterTokenizer(limit=8192), tokenizer_id="cl100k_base",
                                  batch_size=batch_size)
    return client, store, indexer


@pytest.mark.parametrize("updates", [dict(provider="Other"), dict(model="text-embedding-3-large"),
    dict(dimensions=3), dict(tokenizer="o200k_base"), dict(max_chunk_tokens=8193), dict(model_revision="unapproved"),
    dict(deployment=None)])
def test_only_selected_model_and_supported_limits_are_accepted(api, updates):
    with pytest.raises(PermanentError):
        api.ProfileCatalog([profile(**updates)])


def test_catalog_snapshots_full_profiles_and_rejects_mutations(api):
    configured = profile()
    catalog = api.ProfileCatalog([configured])
    original = profile()
    object.__setattr__(configured, "max_chunk_tokens", 500)
    assert catalog.resolve(original) == original
    for change in [dict(max_chunk_tokens=159), dict(collection="another"), dict(distance="Dot"), dict(id="unknown")]:
        with pytest.raises(PermanentError):
            catalog.resolve(profile(**change))
    with pytest.raises(PermanentError):
        api.ProfileCatalog([profile(), profile(max_chunk_tokens=100)])


async def test_real_local_replacement_is_scoped_repeatable_and_carries_citations(api, tmp_path):
    client, store, indexer = await make_indexer(api, tmp_path / "qdrant")
    try:
        first = request()
        event = await indexer.index(first, json.dumps(transcript()))
        points, _ = await client.scroll(profile().collection, limit=100, with_vectors=True)
        assert event.index.chunk_count == len(points) > 0 and event.index.profile_id == profile().id
        assert all(UUID(p.id) and len(p.vector) == 1536 for p in points)
        ids = {p.id for p in points}
        p = points[0].payload
        assert p["scopeKey"] == first.scope_key and p["contentKey"] == first.content_key
        assert p["metadata"] == first.metadata and p["profileId"] == profile().id
        assert p["source"]["blobName"].endswith("transcript.json")
        assert p["origin"]["url"] == transcript()["origin"]["url"]
        assert {s["id"] for s in p["provenance"]["segments"]} == {"s1", "s2"}
        again = request(requestId=str(uuid4()), operationSequence=2)
        await indexer.index(again, json.dumps(transcript()))
        assert {p.id for p in (await client.scroll(profile().collection, limit=100))[0]} == ids
        # Same content in another scope must survive cleanup of the first scope.
        await indexer.index(request(scopeKey="other"), json.dumps(transcript()))
        long = transcript([dict(id="s1", text="word " * 170, startMilliseconds=1000, endMilliseconds=6000)])
        await indexer.index(again, json.dumps(long))
        assert (await client.count(profile().collection)).count > len(ids) * 2
        fixed = request(operationSequence=3, sectionContext={"mode": "fixed", "sectionId": str(uuid4()), "headingPath": ["New"]})
        await indexer.index(fixed, json.dumps(transcript()))
        all_points, _ = await client.scroll(profile().collection, limit=100)
        own = [p for p in all_points if p.payload["scopeKey"] == first.scope_key]
        assert len(own) == 1 and own[0].payload["headingPath"] == ["New"]
        assert own[0].payload["sectionId"] == str(fixed.section_context.section_id)
        assert len([p for p in all_points if p.payload["scopeKey"] == "other"]) == len(ids)
    finally:
        await client.close()


async def test_collection_binding_survives_reopen_and_rejects_equal_dimension_different_space(api, tmp_path):
    path = tmp_path / "qdrant"
    client, _, indexer = await make_indexer(api, path)
    await indexer.index(request(), json.dumps(transcript()))
    await client.close()
    client, store, _ = await make_indexer(api, path)
    wrong = StubEmbeddings()
    binding = wrong.binding
    wrong.binding = lambda p: dict(binding(p), endpoint="https://other-synthetic.openai.azure.com")
    indexer = api.PointSetIndexer(api.ProfileCatalog([profile()]), wrong, store,
                                  tokenizer=CharacterTokenizer(limit=8192), tokenizer_id="cl100k_base")
    try:
        with pytest.raises(PermanentError):
            await indexer.index(request(), json.dumps(transcript()))
        assert wrong.calls == []
        # Immutability is checked against durable collection metadata as well.
        changed = profile(max_chunk_tokens=100)
        second = api.PointSetIndexer(api.ProfileCatalog([changed]), StubEmbeddings(), store,
                                     tokenizer=CharacterTokenizer(limit=8192), tokenizer_id="cl100k_base")
        with pytest.raises(PermanentError):
            await second.index(request(indexProfile=changed.model_dump(mode="json", by_alias=True)), json.dumps(transcript()))
    finally:
        await client.close()


@pytest.mark.parametrize("bad", [[], [[0.1] * 3], [[float("nan")] * 1536], [[float("inf")] * 1536],
                                 [[True] * 1536], [[0.0] * 1536], [[1e30] * 1536], [[1e-40] * 1536],
                                 [[10**1000] * 1536]])
async def test_invalid_vectors_never_mutate_content(api, tmp_path, bad):
    embedder = StubEmbeddings()
    embedder.embed = AsyncMock(return_value=bad)
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant", embedder=embedder)
    try:
        with pytest.raises((PermanentError, TransientError)):
            await indexer.index(request(), json.dumps(transcript()))
        assert (await client.count(profile().collection)).count == 0
    finally:
        await client.close()


async def test_partial_batches_retry_converges_and_cleanup_requires_completed_writes(api, tmp_path):
    client, store, indexer = await make_indexer(api, tmp_path / "qdrant", batch_size=1)
    original = client.upsert
    calls = []
    async def interrupted(*args, **kwargs):
        assert kwargs["wait"] is True
        calls.append(kwargs["points"])
        if len(calls) in [2, 3]:
            raise httpx.ReadTimeout("synthetic failure")
        return await original(*args, **kwargs)
    client.upsert = interrupted
    data = transcript([dict(id="s1", text="word " * 140, startMilliseconds=1000, endMilliseconds=6000)])
    try:
        with pytest.raises(TransientError):
            await indexer.index(request(), json.dumps(data))
        assert (await client.count(profile().collection)).count == 1
        client.upsert = original
        event = await indexer.index(request(), json.dumps(data))
        assert event.index.chunk_count > 1
        assert (await client.count(profile().collection)).count == event.index.chunk_count
        # Acknowledged/unknown writes are not successful completion.
        client.delete = AsyncMock(return_value=models.UpdateResult(operation_id=1, status=models.UpdateStatus.ACKNOWLEDGED))
        with pytest.raises(TransientError):
            await indexer.index(request(), json.dumps(transcript()))
    finally:
        await client.close()


async def test_wrong_collection_schema_rejected_before_embeddings(api, tmp_path):
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    try:
        await client.create_collection(profile().collection, vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
        with pytest.raises(PermanentError):
            await indexer.index(request(), json.dumps(transcript()))
        assert indexer.embeddings.calls == []
    finally:
        await client.close()


async def test_input_snapshot_metadata_and_token_limits_revalidated(api, tmp_path):
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    try:
        job = request()
        job.metadata["text"] = "reserved"
        with pytest.raises(PermanentError):
            await indexer.index(job, json.dumps(transcript()))
        indexer.tokenizer_id = "wrong-tokenizer"
        with pytest.raises(PermanentError):
            await indexer.index(request(), json.dumps(transcript()))
        assert (await client.get_collections()).collections == []
    finally:
        await client.close()


async def test_nonfinite_unchecked_metadata_is_not_silently_serialized_to_null(api, tmp_path):
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    try:
        job = request()
        job.metadata["unchecked"] = float("nan")
        with pytest.raises(PermanentError):
            await indexer.index(job, json.dumps(transcript()))
        assert (await client.get_collections()).collections == []
    finally:
        await client.close()


@pytest.mark.parametrize("updates", [dict(endpoint="http://localhost"), dict(endpoint="https://host/path"),
    dict(endpoint="https://user:pass@host"), dict(deployment="../bad"), dict(api_key=""),
    dict(auth_mode="automatic"), dict(batch_size=0), dict(timeout_seconds=float("nan"))])
def test_real_call_configuration_rejects_invalid_or_ambiguous_values(settings, updates):
    with pytest.raises(ValueError):
        type(settings)(**(settings.model_dump() | updates))
    assert "synthetic-key" not in repr(settings)


async def test_azure_request_batching_auth_and_response_order(api, settings):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    seen = []
    def handle(req):
        assert req.url == "https://synthetic.openai.azure.com/openai/deployments/synthetic-deployment/embeddings?api-version=2024-10-21"
        assert req.headers["api-key"] == "synthetic-key" and "authorization" not in req.headers
        body = json.loads(req.content)
        assert body["dimensions"] == 1536 and body["encoding_format"] == "float"
        seen.append(body["input"])
        return httpx.Response(200, json={"model": "text-embedding-3-small", "data": [
            {"index": i, "embedding": [float(len(text)), *([0.01] * 1535)]}
            for i, text in reversed(list(enumerate(body["input"]))) ]})
    async with AzureOpenAIEmbeddings(settings, tokenizer=CharacterTokenizer(limit=8192),
                                     transport=httpx.MockTransport(handle)) as adapter:
        result = await adapter.embed(["one", "two!", "three"], profile())
        assert [v[0] for v in result] == [3.0, 4.0, 5.0] and seen == [["one", "two!"], ["three"]]
        with pytest.raises(PermanentError):
            await adapter.embed(["x" * 161], profile())
        assert len(seen) == 2


@pytest.mark.parametrize("status,attempts,transient", [(429, 3, True), (503, 3, True), (408, 3, True),
    (400, 1, False), (401, 1, True), (403, 1, True), (404, 1, True), (302, 1, False)])
async def test_embedding_status_retry_is_bounded_and_safe(api, settings, status, attempts, transient):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    seen = []
    def handle(req):
        seen.append(req)
        return httpx.Response(status, text="private input synthetic-key", headers={"Location": "https://private.invalid/"})
    async with AzureOpenAIEmbeddings(settings, tokenizer=CharacterTokenizer(limit=8192), transport=httpx.MockTransport(handle)) as adapter:
        with pytest.raises(TransientError if transient else PermanentError) as error:
            await adapter.embed(["content"], profile())
    assert len(seen) == attempts and "private" not in str(error.value) and "synthetic-key" not in str(error.value)


async def test_entra_auth_is_explicit_and_has_no_ambient_fallback(api, settings):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    entra = type(settings)(**(settings.model_dump() | dict(auth_mode="entra", api_key=None)))
    seen = []
    def handle(req):
        seen.append(req)
        assert req.headers["Authorization"] == "Bearer synthetic-token" and "api-key" not in req.headers
        return httpx.Response(200, json={"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [0.1] * 1536}]})
    async with AzureOpenAIEmbeddings(entra, tokenizer=CharacterTokenizer(limit=8192), transport=httpx.MockTransport(handle)) as adapter:
        with pytest.raises(TransientError):
            await adapter.embed(["content"], profile())
        assert seen == []
    token = AsyncMock(return_value="synthetic-token")
    async with AzureOpenAIEmbeddings(entra, tokenizer=CharacterTokenizer(limit=8192), token_provider=token,
                                     transport=httpx.MockTransport(handle)) as adapter:
        await adapter.embed(["content"], profile())
    token.assert_awaited_once()


@pytest.mark.parametrize("data", [dict(model="other", data=[]), dict(model="text-embedding-3-small", data=[]),
    dict(model="text-embedding-3-small", data=[dict(index=1, embedding=[0.1] * 1536)]),
    dict(model="text-embedding-3-small", data=[dict(index=0, embedding=[0.1] * 3)]),
    dict(model="text-embedding-3-small", data=[dict(index=0, embedding=[float("nan")] * 1536)])])
async def test_embedding_response_is_validated_before_return(api, settings, data):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    async with AzureOpenAIEmbeddings(settings, tokenizer=CharacterTokenizer(limit=8192),
                                     transport=httpx.MockTransport(lambda req: httpx.Response(200, content=json.dumps(data)))) as adapter:
        with pytest.raises(TransientError):
            await adapter.embed(["content"], profile())


async def test_corrected_transcript_and_actual_n9a_final_artifacts_reach_qdrant(api, tmp_path):
    from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts
    from tests.unit.test_reviewed_content import original_review, rebuild_request
    fixtures = Path(__file__).parents[1] / "fixtures/content_processing"
    final = await rebuild_document_artifacts((fixtures / "reviewed-draft.md").read_bytes(), json.dumps(original_review()),
                                              rebuild_request(), tmp_path / "final")
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    try:
        job = request(source={"type": "blob", "format": "docling", "blobName": final.artifacts.docling_json_blob_name},
                      sectionContext={"mode": "fromReview", "reviewBlobName": final.artifacts.review_blob_name})
        await indexer.index(job, json.dumps(final.docling_json), review_raw=final.review.model_dump_json(by_alias=True))
        points, _ = await client.scroll(profile().collection, limit=100)
        text = "\n".join(p.payload["text"] for p in points)
        assert "Corrected main text" in text and "Moved second body" in text
        assert {p.payload["sectionId"] for p in points if p.payload["sectionId"]} == {str(s.id) for s in final.review.sections}
        assert all(p.payload["provenance"]["pages"] == [] for p in points)
        await indexer.index(request(), (fixtures / "corrected-transcript.json").read_bytes())
        points, _ = await client.scroll(profile().collection, limit=100)
        assert "Corrected first phrase" in " ".join(p.payload["text"] for p in points)
        segments = {s["id"]: s for p in points for s in p.payload["provenance"]["segments"]}
        assert (segments["s1"]["startMilliseconds"], segments["s2"]["endMilliseconds"]) == (1000, 6000)
    finally:
        await client.close()


def test_missing_or_corrupt_tokenizer_assets_never_download(api, tmp_path):
    from akay_convert_to_markdown.indexing.tokenizer import Cl100kTokenizer
    with pytest.raises(TransientError):
        Cl100kTokenizer.from_file(tmp_path / "absent")
    corrupt = tmp_path / "corrupt.tiktoken"
    corrupt.write_text("invalid private tokenizer data", encoding="utf-8")
    with pytest.raises(TransientError) as error:
        Cl100kTokenizer.from_file(corrupt)
    assert "private" not in str(error.value) and str(tmp_path) not in str(error.value)


async def test_compatible_profiles_share_space_without_cross_profile_cleanup(api, tmp_path):
    second = profile(id="synthetic-second", max_chunk_tokens=100)
    client, store, indexer = await make_indexer(api, tmp_path / "qdrant", profiles=[profile(), second])
    original = client.create_payload_index
    indexes = []
    async def observe(**kwargs):
        indexes.append(kwargs)
        return await original(**kwargs)
    client.create_payload_index = observe
    try:
        first = request()
        await indexer.index(first, json.dumps(transcript()))
        await indexer.index(request(indexProfile=second.model_dump(mode="json", by_alias=True)), json.dumps(transcript()))
        info = await client.get_collection(profile().collection)
        assert set(info.config.metadata["akayIndexV1"]["profiles"]) == {profile().id, second.id}
        assert {i["field_name"] for i in indexes} == {"scopeKey", "contentKey", "profileId", "sectionId", "chunkIndex", "operationSequence"}
        assert all(i["wait"] for i in indexes)
        await indexer.index(first, json.dumps(transcript([dict(id="s1", text="Short.")])))
        points, _ = await client.scroll(profile().collection, limit=100)
        assert {p.payload["profileId"] for p in points} == {profile().id, second.id}
        assert len({p.id for p in points}) == len(points)
    finally:
        await client.close()


async def test_embedding_transport_retries_and_total_token_batching(api, settings):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    configured = type(settings)(**(settings.model_dump() | dict(batch_size=10, max_batch_tokens=8192)))
    calls = []
    def handle(req):
        body = json.loads(req.content)
        calls.append(body["input"])
        if len(calls) == 1:
            raise httpx.ReadTimeout("synthetic-key private source", request=req)
        return httpx.Response(200, json={"model": "text-embedding-3-small", "data": [
            dict(index=i, embedding=[0.1] * 1536) for i in range(len(body["input"]))]})
    async with AzureOpenAIEmbeddings(configured, tokenizer=CharacterTokenizer(limit=8192),
                                     transport=httpx.MockTransport(handle)) as adapter:
        vectors = await adapter.embed(["x" * 5000, "y" * 5000], profile(max_chunk_tokens=8192))
    assert len(vectors) == 2 and [len(c) for c in calls] == [1, 1, 1]


async def test_auth_missing_configuration_and_profile_mismatch_never_send(api, settings, monkeypatch):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings
    # Only explicit empty synthetic values; never depend on developer env secrets.
    with pytest.raises(ValueError):
        AzureOpenAISettings(endpoint="", deployment="", auth_mode="apiKey", api_key="")
    transport = httpx.MockTransport(lambda req: pytest.fail("Mismatched deployment must not send HTTP"))
    async with AzureOpenAIEmbeddings(settings, tokenizer=CharacterTokenizer(limit=8192), transport=transport) as adapter:
        with pytest.raises(PermanentError):
            await adapter.embed(["content"], profile(deployment="different-synthetic"))


async def test_oversized_and_duplicate_response_fields_are_rejected(api, settings):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    configured = type(settings)(**(settings.model_dump() | dict(max_response_bytes=1024)))
    for content in [b"x" * 1025, b'{"model":"text-embedding-3-small","model":"other","data":[]}']:
        async with AzureOpenAIEmbeddings(configured, tokenizer=CharacterTokenizer(limit=8192),
                                         transport=httpx.MockTransport(lambda req: httpx.Response(200, content=content))) as adapter:
            with pytest.raises(TransientError):
                await adapter.embed(["content"], profile())


async def test_lost_upsert_response_retries_same_points_without_duplicates(api, tmp_path):
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    original = client.upsert
    seen = []
    async def uncertain(**kwargs):
        seen.append([point.id for point in kwargs["points"]])
        result = await original(**kwargs)
        if len(seen) == 1:
            raise httpx.ReadTimeout("Response lost after local commit")
        return result
    client.upsert = uncertain
    try:
        event = await indexer.index(request(), json.dumps(transcript()))
        assert seen[0] == seen[1]
        assert (await client.count(profile().collection)).count == event.index.chunk_count == 1
    finally:
        await client.close()


async def test_unconfirmed_upsert_does_not_prune_or_report_completion(api, tmp_path):
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    client.upsert = AsyncMock(return_value=models.UpdateResult(operation_id=1, status=models.UpdateStatus.ACKNOWLEDGED))
    client.delete = AsyncMock()
    try:
        with pytest.raises(TransientError):
            await indexer.index(request(), json.dumps(transcript()))
        client.delete.assert_not_called()
    finally:
        await client.close()


@pytest.mark.parametrize("size,distance,named", [(3, "Cosine", False), (1536, "Dot", False), (1536, "Cosine", True)])
async def test_collection_vector_config_is_checked_independently_of_binding(api, tmp_path, size, distance, named):
    client, _, indexer = await make_indexer(api, tmp_path / "qdrant")
    vector = models.VectorParams(size=size, distance=models.Distance(distance))
    binding = dict(space=indexer.embeddings.binding(profile()), profiles={profile().id: profile().model_dump(mode="json", by_alias=True)})
    try:
        await client.create_collection(profile().collection, vectors_config={"named": vector} if named else vector,
                                         metadata={"akayIndexV1": binding})
        with pytest.raises(PermanentError):
            await indexer.index(request(), json.dumps(transcript()))
        assert indexer.embeddings.calls == []
    finally:
        await client.close()


@pytest.mark.parametrize("texts", [None, "text", [], [None], [" "], ["valid", 7]])
async def test_invalid_embedding_inputs_fail_safely_before_tokenization_or_http(api, settings, texts):
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    transport = httpx.MockTransport(lambda req: pytest.fail("Invalid inputs must not send HTTP"))
    async with AzureOpenAIEmbeddings(settings, tokenizer=CharacterTokenizer(limit=8192), transport=transport) as adapter:
        with pytest.raises(PermanentError):
            await adapter.embed(texts, profile())
