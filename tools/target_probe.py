"""Exercise installed worker composition and its real local engine, with sockets blocked."""

import argparse
import asyncio
from importlib import import_module
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock


def forbidden(*args, **kwargs):
    raise AssertionError("Installed-target probes cannot access application services or download assets.")


async def local_document(directory):
    from akay_convert_to_markdown.contracts.requests import DocumentOptions, DocumentRequest
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
    from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts
    from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts

    request = DocumentRequest.model_validate_json(json.dumps({
        "schemaVersion": 1, "requestId": "b1ad362f-0911-4773-8651-1508d94ca001", "contentKey": "fixture",
        "source": {"type": "blob", "blobName": "source.md"}, "destinationBlobName": "extracted.md",
        "contentType": "document", "callback": "fixture", "documentOptions": {"extractSections": True}}))
    source = directory / "source.md"
    source.write_text("# Installed original\n\nOriginal body.\n", encoding="utf-8")
    extraction = await DoclingDocumentConverter().extract(source, DocumentOptions(extract_sections=True))
    original = await export_document_artifacts(extraction, request, directory / "extracted")
    data = request.model_dump(mode="json", by_alias=True)
    data.pop("destinationBlobName")
    data.update(operation="rebuildFromMarkdown", source={"type": "blob", "blobName": "extracted.md"})
    final = await rebuild_document_artifacts("# Installed corrected\n\nCorrected body.\n",
                                             original.review.model_dump_json(by_alias=True),
                                             DocumentRequest.model_validate_json(json.dumps(data)), directory / "final")
    assert "Corrected body" in final.markdown and "Original body" not in final.markdown
    assert final.review.sections and final.review.processing.engine_version == "2.141.0"
    from docling_core.types.doc import DoclingDocument
    DoclingDocument.model_validate(final.docling_json)
    import torch
    assert torch.version.cuda is None
    print("PASS installed convert + rebuildFromMarkdown + Core reload; CPU-only Torch")


async def local_index(tokenizer_file):
    from akay_convert_to_markdown.indexing.tokenizer import Cl100kTokenizer
    from akay_convert_to_markdown.indexing.chunking import chunk_content
    from akay_convert_to_markdown.contracts.requests import IndexRequest
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance

    tokenizer = Cl100kTokenizer.from_file(tokenizer_file)
    request = IndexRequest.model_validate_json(json.dumps({
        "schemaVersion": 1, "requestId": "b1ad362f-0911-4773-8651-1508d94ca003", "operationSequence": 1,
        "operation": "index", "contentKey": "fixture", "scopeKey": "fixture", "callback": "fixture",
        "source": {"type": "blob", "format": "transcript", "blobName": "out/transcript.json"},
        "sectionContext": {"mode": "none"}, "indexProfile": {
            "id": "fixture", "provider": "AzureOpenAI", "model": "text-embedding-3-small", "deployment": "fixture",
            "dimensions": 1536, "tokenizer": "cl100k_base", "maxChunkTokens": 100, "distance": "Cosine", "collection": "fixture"}}))
    transcript = {"schemaVersion": 1, "contentKey": "fixture", "origin": {"type": "blob", "blobName": "a.mp3"},
                  "language": "es-ES", "durationMilliseconds": 1000,
                  "segments": [{"id": "segment-0001", "startMilliseconds": 0, "endMilliseconds": 1000,
                                "speaker": None, "text": "Corrected installed transcript."}]}
    chunks = chunk_content(request, json.dumps(transcript), tokenizer=tokenizer, tokenizer_id="cl100k_base")
    assert chunks and "Corrected installed transcript" in chunks[0].text
    with tempfile.TemporaryDirectory() as directory:
        client = AsyncQdrantClient(path=directory)
        await client.create_collection("fixture", vectors_config=VectorParams(size=3, distance=Distance.COSINE))
        await client.upsert("fixture", points=[PointStruct(id=1, vector=[1.0, 0.0, 0.0], payload={"text": chunks[0].text})], wait=True)
        assert (await client.count("fixture")).count == 1
        await client.close()
    print("PASS installed HybridChunker + local tokenizer + persistent local Qdrant")


def local_models(directory):
    from akay_convert_to_markdown.contracts.requests import DocumentOptions
    from akay_convert_to_markdown.conversion.docling_converter import build_docling_converter
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel

    for language in ("es", "eu", "gl", "ca", "fr", "en", "de"):
        engine = build_docling_converter(DocumentOptions(ocr_language=language), artifacts_path=directory,
                                         input_format=InputFormat.PDF)
        options = engine.format_to_options[InputFormat.PDF].pipeline_options
        model = RapidOcrModel(enabled=True, artifacts_path=directory, options=options.ocr_options,
                              accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU))
        assert model._native_codes == [language]
    engine = build_docling_converter(DocumentOptions(code_enrichment=True, formula_enrichment=True),
                                     artifacts_path=directory, input_format=InputFormat.PDF)
    engine.initialize_pipeline(InputFormat.PDF)
    print("PASS installed seven-language OCR + layout/accurate-table/code/formula local initialization (not quality)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["document", "media", "index"])
    parser.add_argument("--tokenizer-file", type=Path, required=True)
    parser.add_argument("--document-models", type=Path)
    parser.add_argument("--scratch-dir", type=Path, help="Explicit writable probe directory (container tmpfs)")
    args = parser.parse_args()
    original_connect, original_socketpair = socket.socket.connect, socket.socketpair

    def local_socketpair(*arguments, **keywords):
        # Windows implements asyncio's self-pipe using a loopback socketpair.
        # Permit that synchronous stdlib operation, not application connections.
        socket.socket.connect = original_connect
        try:
            return original_socketpair(*arguments, **keywords)
        finally:
            socket.socket.connect = forbidden

    socket.socketpair = local_socketpair
    socket.create_connection = socket.getaddrinfo = socket.socket.connect = forbidden
    systemroot = os.environ.get("SYSTEMROOT")
    home = tempfile.TemporaryDirectory(dir=args.scratch_dir or Path(__file__).resolve().parents[1] / ".local/n12")
    os.environ.clear()
    os.environ.update(HOME=home.name, USERPROFILE=home.name, APPDATA=home.name, XDG_CACHE_HOME=home.name)
    if args.scratch_dir is not None:
        os.environ.update(TMPDIR=str(args.scratch_dir), TEMP=str(args.scratch_dir), TMP=str(args.scratch_dir))
    if systemroot:
        os.environ["SYSTEMROOT"] = systemroot
    os.environ.update(AZURE_STORAGE_ACCOUNT_URL="https://fixture.blob.core.windows.net", SOURCE_CONTAINER_NAME="source",
                      DESTINATION_CONTAINER_NAME="output", SERVICEBUS_FULLY_QUALIFIED_NAMESPACE="fixture.servicebus.windows.net",
                      WEBHOOK_CALLBACKS='{"fixture":"https://callback.invalid/result"}', WEBHOOK_API_KEY="fixture",
                      HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    target = args.target
    queue = {"document": "DOCUMENT", "media": "MEDIA", "index": "INDEX"}[target] + "_SERVICEBUS_QUEUE_NAME"
    os.environ[queue] = "fixture"
    if target == "media":
        os.environ.update(SPEECH_RESOURCE_KEY="fixture", SPEECH_ENDPOINT="https://speech.invalid")
    names = {dist.metadata["Name"].lower().replace("_", "-") for dist in distributions()}
    assert not any("whisper" in name or name.startswith(("nvidia-", "cuda-")) for name in names)
    assert not {"markitdown", "onnxruntime-gpu", "docling"} & names
    foreign = {"document": {"qdrant-client", "yt-dlp", "deno"},
               "media": {"docling-core", "docling-slim", "torch", "qdrant-client"},
               "index": {"docling-slim", "torch", "transformers", "rapidocr", "yt-dlp", "deno"}}[target]
    assert not foreign & names, foreign & names
    entry = import_module("akay_convert_to_markdown." + {"document": "document_main", "media": "media_main", "index": "index_main"}[target])
    runtime = import_module("akay_convert_to_markdown.worker_runtime")
    runtime.build_credential = MagicMock(return_value=AsyncMock())
    runtime.BlobStorage.from_settings = MagicMock(return_value=AsyncMock())
    runtime.WebhookClient = MagicMock(return_value=AsyncMock())
    runtime.ServiceBusConsumer = MagicMock(return_value=AsyncMock())
    if target == "index":
        # Validate the fail-closed CLI with no configured adapter, then compose
        # the actual adapter below using explicit synthetic configuration.
        assert entry.main() == 2
        from akay_convert_to_markdown.config.indexing_settings import AzureOpenAISettings, IndexRuntimeSettings
        from akay_convert_to_markdown.config.settings import IndexerSettings
        from akay_convert_to_markdown.worker_runtime import run_worker
        profile = dict(id="fixture", provider="AzureOpenAI", model="text-embedding-3-small", deployment="fixture",
                       dimensions=1536, tokenizer="cl100k_base", maxChunkTokens=100, distance="Cosine", collection="fixture")
        config = IndexRuntimeSettings(profiles=[profile], tokenizer_path=args.tokenizer_file, qdrant_url="https://qdrant.invalid",
                                      qdrant_auth_mode="none",
                                      state_container="fixture", state_prefix="fixture")
        azure = AzureOpenAISettings(endpoint="https://fixture.openai.azure.com", deployment="fixture", auth_mode="apiKey", api_key="fixture")
        from functools import partial
        asyncio.run(run_worker(IndexerSettings(), __import__("logging").getLogger("fixture"),
                               partial(entry.build_processor, config=config, embedding_settings=azure)))
        asyncio.run(local_index(args.tokenizer_file))
    else:
        assert entry.main() == 0
        if target == "document":
            with tempfile.TemporaryDirectory() as directory:
                asyncio.run(local_document(Path(directory)))
            if args.document_models is not None:
                local_models(args.document_models.resolve())
        else:
            from deno import find_deno_bin
            import yt_dlp
            import yt_dlp_ejs
            assert Path(find_deno_bin()).is_file()
            assert yt_dlp.version.__version__ == "2025.11.12"
    runtime.ServiceBusConsumer.return_value.run.assert_awaited_once()
    loaded = sorted(name for name in sys.modules if name.split(".")[0] in
                    {"docling", "docling_core", "torch", "transformers", "qdrant_client", "yt_dlp"})
    print(json.dumps({"target": target, "distributions": sorted(names), "importRoots": sorted({name.split('.')[0] for name in loaded})}))
    print("PASS isolated installed startup " + target)


if __name__ == "__main__":
    main()
