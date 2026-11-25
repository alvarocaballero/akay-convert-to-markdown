"""Offline N10: actual approved tokenizer, final artifacts and persistent local Qdrant.

Requires an explicit prefetched public cl100k_base asset. Never downloads it,
loads credentials or contacts Azure/application services. Temporary data is owned
by the probe and removed on exit; the supplied tokenizer file is read-only.
"""

import argparse
import asyncio
import json
import inspect
import socket
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


async def verify(asset):
    from akay_convert_to_markdown.indexing.tokenizer import Cl100kTokenizer
    from akay_convert_to_markdown.indexing.point_sets import PointSetIndexer, ProfileCatalog, QdrantPointStore
    from akay_convert_to_markdown.indexing.azure_embeddings import AzureOpenAIEmbeddings
    from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings
    from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts
    from tests.unit.test_content_indexing import StubEmbeddings, profile, request
    from tests.unit.test_reviewed_content import original_review, rebuild_request
    from qdrant_client import AsyncQdrantClient
    import httpx
    import tiktoken
    import tiktoken_ext.openai_public as public

    for package, expected in {"qdrant-client": "1.19.1", "tiktoken": "0.12.0", "httpx": "0.28.1",
                              "docling-core": "2.99.0"}.items():
        assert version(package) == expected
    for method in [AsyncQdrantClient.create_collection, AsyncQdrantClient.update_collection]:
        assert "metadata" in inspect.signature(method).parameters
    for method in [AsyncQdrantClient.upsert, AsyncQdrantClient.delete, AsyncQdrantClient.create_payload_index]:
        assert "wait" in inspect.signature(method).parameters
    tokenizer = Cl100kTokenizer.from_file(asset)
    # Compare the copied pattern/IDs with the pinned upstream constructor, while
    # supplying the already hash-verified ranks instead of enabling its downloader.
    with patch.object(public, "load_tiktoken_bpe", return_value=tokenizer.encoding._mergeable_ranks):
        reference = tiktoken.Encoding(**public.cl100k_base())
    for text in ["hello world", "Fotosíntesis y energía", "中文\n\t", "🙂 E=mc^2", "<|endoftext|>", "a\r\n  b"]:
        assert tokenizer.encoding.encode_ordinary(text) == reference.encode_ordinary(text)
    assert tokenizer.count_tokens("hello world") == 2
    print("PASS: hash-verified cl100k_base, pinned upstream token equivalence, no tokenizer downloads")

    fixtures = ROOT / "tests/fixtures/content_processing"
    with TemporaryDirectory(prefix="akay-n10-") as directory:
        root = Path(directory)
        final = await rebuild_document_artifacts((fixtures / "reviewed-draft.md").read_bytes(), json.dumps(original_review()),
                                                  rebuild_request(), root / "final")
        client = AsyncQdrantClient(path=str(root / "qdrant"))
        embedder = StubEmbeddings()
        indexer = PointSetIndexer(ProfileCatalog([profile()]), embedder, QdrantPointStore(client),
                                   tokenizer=tokenizer, tokenizer_id="cl100k_base", batch_size=2)
        try:
            job = request(source={"type": "blob", "format": "docling", "blobName": final.artifacts.docling_json_blob_name},
                          sectionContext={"mode": "fromReview", "reviewBlobName": final.artifacts.review_blob_name})
            event = await indexer.index(job, json.dumps(final.docling_json), review_raw=final.review.model_dump_json(by_alias=True))
            assert event.index.chunk_count >= 4
            points, _ = await client.scroll(profile().collection, limit=100, with_vectors=True)
            assert {p.payload["sectionId"] for p in points if p.payload["sectionId"]} == {str(s.id) for s in final.review.sections}
            assert all(not p.payload["provenance"]["pages"] for p in points)
            assert "Corrected main text" in " ".join(p.payload["text"] for p in points)
            corrected = (fixtures / "corrected-transcript.json").read_bytes()
            await indexer.index(request(), corrected)
            await indexer.index(request(), corrected)
            points, _ = await client.scroll(profile().collection, limit=100)
            assert len(points) == 1  # replacement prunes all prior document chunks
            assert "Corrected first phrase" in points[0].payload["text"]
            assert [s["id"] for s in points[0].payload["provenance"]["segments"]] == ["s1", "s2"]
            assert points[0].payload["provenance"]["endMilliseconds"] == 6000
            assert all(tokenizer.count_tokens(t) <= profile().max_chunk_tokens for batch in embedder.calls for t in batch)
        finally:
            await client.close()
        reopened = AsyncQdrantClient(path=str(root / "qdrant"))
        try:
            assert (await reopened.count(profile().collection)).count == 1
            assert (await reopened.get_collection(profile().collection)).config.metadata["akayIndexV1"]["space"]["model"] == profile().model
        finally:
            await reopened.close()
        print("PASS: real-tokenizer N9A final JSON/review and corrected transcript -> stub vectors -> persistent local Qdrant")

    settings = AzureOpenAISettings(endpoint="https://synthetic.openai.azure.com", deployment="synthetic-deployment",
                                    auth_mode="apiKey", api_key="synthetic-key")
    def mock(req):
        texts = json.loads(req.content)["input"]
        assert all(tokenizer.count_tokens(t) <= profile().max_chunk_tokens for t in texts)
        return httpx.Response(200, json={"model": profile().model, "data": [dict(index=i, embedding=[0.1] * 1536)
                                                                                        for i in range(len(texts))]})
    async with AzureOpenAIEmbeddings(settings, tokenizer=tokenizer, transport=httpx.MockTransport(mock)) as azure:
        assert len((await azure.embed(["Fotosíntesis y energía"], profile()))[0]) == 1536
    print("PASS: actual tokenizer with Azure REST MockTransport; production integration NOT verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, required=True)
    args = parser.parse_args()
    def forbidden(*args, **kwargs):
        raise AssertionError("N10 probe forbids network access")
    with patch.object(socket, "create_connection", forbidden), patch.object(socket, "getaddrinfo", forbidden):
        asyncio.run(verify(args.tokenizer))


if __name__ == "__main__":
    main()
