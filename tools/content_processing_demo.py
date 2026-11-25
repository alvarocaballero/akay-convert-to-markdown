"""Offline N16 handoff using actual processors/consumer and explicit service doubles.

Development checkout/test dependencies required. No cloud client, credentials or
remote services are constructed. Generated fixture evidence is not a deployment.
"""

import argparse
import asyncio
from collections import Counter
import json
import logging
import os
from pathlib import Path
import socket
from unittest.mock import patch
from uuid import uuid5, NAMESPACE_URL

ROOT = Path(__file__).resolve().parents[1]


def examples():
    return json.loads((ROOT / "tests/fixtures/content_processing/handoff-requests.json").read_text(encoding="utf-8"))


def forbidden(*args, **kwargs):
    raise AssertionError("The N16 fixture harness cannot contact services, discover credentials or fetch resources.")


async def run_demo(directory, *, tokenizer):
    """Own a new local directory; restore environment/socket guards even on failure."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    home = directory / "empty-home"
    home.mkdir()
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP") if key in os.environ}
    environment.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), XDG_CACHE_HOME=str(home),
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    # The caller's event loop already exists (Windows needs its internal socketpair).
    with patch.dict(os.environ, environment, clear=True), patch.object(socket, "create_connection", forbidden), \
            patch.object(socket, "getaddrinfo", forbidden), patch.object(socket.socket, "connect", forbidden), \
            patch.object(socket.socket, "connect_ex", forbidden):
        return await _run(directory, tokenizer)


async def _run(directory, tokenizer):
    import httpx
    from azure.identity.aio import DefaultAzureCredential
    from docling_core.types.doc import ImageRef
    from qdrant_client import AsyncQdrantClient
    from akay_convert_to_markdown.config.settings import DocumentWorkerSettings, MediaWorkerSettings, IndexerSettings
    from akay_convert_to_markdown.contracts import parse_request, parse_review, parse_transcript
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
    from akay_convert_to_markdown.indexing.point_sets import PointSetIndexer, QdrantPointStore
    from akay_convert_to_markdown.indexing.profiles import ProfileCatalog
    from akay_convert_to_markdown.messaging.service_bus_consumer import ServiceBusConsumer
    from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
    from akay_convert_to_markdown.processing.published_document_processor import PublishedDocumentProcessor
    from akay_convert_to_markdown.processing.published_media_processor import PublishedMediaProcessor
    from akay_convert_to_markdown.processing.index_processor import IndexProcessor
    from akay_convert_to_markdown.processing.audio_processor import AudioProcessor
    from akay_convert_to_markdown.processing.video_processor import VideoProcessor
    from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
    from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
    from akay_convert_to_markdown.services.process_runner import ProcessResult
    from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown
    from akay_convert_to_markdown.models.transcription import TranscriptionResult, TranscriptionSegment
    from akay_convert_to_markdown.storage.blob_storage import BlobStorage
    from tools.callback_receiver import CallbackInbox
    # Reuse the already-tested conditional/lease/transport doubles, not another SDK.
    from tests.unit.test_artifact_publication import MemoryBlobs
    from tests.unit.test_content_indexing import StubEmbeddings
    from tests.unit.test_consumer import FakeMessage, FakeReceiver, FakeLockRenewerFactory

    requests = examples()
    counts, settlements = Counter(), Counter()
    checks = []
    blobs = MemoryBlobs()
    storage = BlobStorage(blobs)
    inbox = CallbackInbox("n16-fixture-key")
    logger = logging.getLogger("n16-fixture")
    common = dict(azure_storage_account_url="https://fixture.blob.core.windows.net", source_container_name="sources",
                  servicebus_fully_qualified_namespace="fixture.servicebus.windows.net",
                  webhook_callbacks={"local": "https://callback.invalid/callbacks"}, webhook_api_key="n16-fixture-key",
                  webhook_retry_count=1, webhook_retry_delay_seconds=0, temp_directory=directory / "temporary")
    publication = dict(destination_container_name="artifacts", publication_state_container_name="technical",
                       publication_state_prefix="publication")
    document_settings = DocumentWorkerSettings(**common, **publication, DOCUMENT_SERVICEBUS_QUEUE_NAME="fixture-document")
    media_settings = MediaWorkerSettings(**common, **publication, MEDIA_SERVICEBUS_QUEUE_NAME="fixture-media",
                                         speech_endpoint="https://speech.invalid", speech_resource_key="n16-fixture-key")
    index_settings = IndexerSettings(**(common | {"source_container_name": "artifacts"}),
                                     INDEX_SERVICEBUS_QUEUE_NAME="fixture-index")

    async def put(container, name, raw):
        await blobs.get_blob_client(container, name).upload_blob(raw.encode() if isinstance(raw, str) else raw, overwrite=True)

    def read(name):
        return blobs.data[("artifacts", name)][0]

    def callback(request):
        event = json.loads(request.content)
        if event["eventType"] == "document.conversion.completed":
            # Completion must follow the entire published set, not just Markdown.
            names = list(event["artifacts"].values())
            if event.get("operation") != "rebuildFromMarkdown":
                names.append(event["destinationBlobName"])
            for name in names:
                assert ("artifacts", name) in blobs.data
            assert not {"images", "imagesPrefix"} & event.keys()
        return httpx.Response(inbox.accept(request.content, request.headers.get("X-Api-Key"),
                                          request.headers.get("Idempotency-Key")))

    class CountingConverter:
        async def extract(self, path, options):
            counts["extraction"] += 1
            return await DoclingDocumentConverter().extract(path, options)

    async def ffmpeg_runner(command, **kwargs):
        counts[command[0]] += 1
        if command[0] == "ffprobe":
            return ProcessResult(0, json.dumps({"format": {"duration": "6"},
                                                "streams": [{"codec_type": "audio", "codec_name": "opus"}]}), "")
        assert "-vn" in command and command[command.index("-map") + 1] == "0:a:0"
        Path(command[-1]).write_bytes(b"fixture audio, not codec evidence")
        return ProcessResult(0, "", "")

    def speech_response(request):
        counts["speech"] += 1
        assert request.url.host == "speech.invalid" and "multipart/form-data" in request.headers["Content-Type"]
        return httpx.Response(200, json={"durationMilliseconds": 6000, "phrases": [
            {"text": "Original first phrase.", "offsetMilliseconds": 1000, "durationMilliseconds": 1500, "locale": "es-ES"},
            {"text": "Original second phrase.", "offsetMilliseconds": 3000, "durationMilliseconds": 3000, "locale": "es-ES"}]})

    class FixtureYouTube:
        async def download(self, source, output):
            counts["youtube"] += 1
            assert source.url == requests["youtube"]["source"]["url"]
            output.mkdir()
            path = output / "audio.webm"
            path.write_bytes(b"fixture YouTube audio")
            return path, dict(videoId="abcdefghijk", canonicalUrl="https://www.youtube.com/watch?v=abcdefghijk", title="Fixture video")

    async def deliver(settings, processor, raw, *, completed=True):
        message, receiver = FakeMessage(json.dumps(raw).encode()), FakeReceiver()
        consumer = ServiceBusConsumer(settings, processor, None, logger, asyncio.Event(),
                                      lock_renewer_factory=FakeLockRenewerFactory())
        await consumer._handle_message(receiver, message)
        assert (receiver.completed == [message]) == completed
        assert (receiver.abandoned == [message]) != completed
        settlements["completed"] += len(receiver.completed)
        settlements["abandoned"] += len(receiver.abandoned)

    # No fallback credentials/image access, even if a future seam accidentally tries.
    with patch.object(DefaultAzureCredential, "__init__", forbidden), patch.object(ImageRef, "pil_image", property(forbidden)):
        async with httpx.AsyncClient(transport=httpx.MockTransport(callback), trust_env=False) as http, \
                httpx.AsyncClient(transport=httpx.MockTransport(speech_response), trust_env=False) as speech_http:
            webhook = WebhookClient(document_settings, http)
            document = PublishedDocumentProcessor(document_settings, storage, CountingConverter(), webhook, logger)
            ffmpeg = FfmpegService(media_settings, runner=ffmpeg_runner)
            speech = FastTranscriptionService(media_settings, speech_http)
            media = PublishedMediaProcessor(media_settings, storage, None, webhook, logger,
                                             audio_processor=AudioProcessor(media_settings, ffmpeg, speech),
                                             video_processor=VideoProcessor(media_settings, ffmpeg, speech), youtube_service=FixtureYouTube())
            await put("sources", "principal/original.md", "# Original principal\n\nObsolete original body.\n\n## Removed\n\nOld section.\n")
            await deliver(document_settings, document, requests["principal"])
            assert not any(event["eventType"].startswith("content.index") for event in inbox.events)
            edited_markdown = "# Corrected principal\n\nCorrected final body.\n\n## Repeated\n\nFirst final detail.\n\n## Repeated\n\nSecond final detail.\n\n![edited](https://never-fetch.invalid/missing.png)\n"
            await put("sources", "principal/extracted.md", edited_markdown)
            await put("artifacts", "principal/extracted.md", edited_markdown)
            markdown_snapshot = blobs.data[("artifacts", "principal/extracted.md")]
            inbox.lose_next_acknowledgement()
            await deliver(document_settings, document, requests["rebuild"], completed=False)
            # Callback-only replay needs no Markdown read or reconstruction.
            frozen_draft = blobs.data.pop(("sources", "principal/extracted.md"))
            await deliver(document_settings, document, requests["rebuild"])
            blobs.data[("sources", "principal/extracted.md")] = frozen_draft
            assert blobs.data[("artifacts", "principal/extracted.md")] == markdown_snapshot
            final_review = parse_review(read("principal/extracted.artifacts/review.json"))
            assert len(final_review.sections) == 3 and len({section.id for section in final_review.sections}) == 3
            assert final_review.confidence.pages == [] and final_review.summary.page_count is None
            assert b"Corrected final body" in read("principal/extracted.md") and b"Obsolete" not in read("principal/extracted.md")
            checks.append("reviewed-principal")

            await put("sources", "additional/original.md", "# Internal additional heading\n\nAdditional body.\n")
            await deliver(document_settings, document, requests["additional"])
            assert parse_review(read("additional/document.artifacts/review.json")).sections == []
            assert b"Internal additional heading" in read("additional/document.md")
            assert b"akay-section:start" not in read("additional/document.md")
            checks.append("additional-document")
            for name in ("audio", "video", "youtube"):
                if name != "youtube":
                    await put("sources", requests[name]["source"]["blobName"], b"fixture media")
                await deliver(media_settings, media, requests[name])
                event = next(event for event in inbox.events if event["requestId"] == requests[name]["requestId"])
                transcript = parse_transcript(read(event["artifacts"]["transcriptJsonBlobName"]))
                assert transcript.origin.model_dump(mode="json", by_alias=True) == requests[name]["source"]
                assert all(segment.text.encode() in read(event["destinationBlobName"]) for segment in transcript.segments)
                review = parse_review(read(event["artifacts"]["reviewBlobName"]))
                assert not review.sections and not review.confidence.pages
            checks.append("blob-audio-video-youtube-doubles")

            # Simulated consumer action, not a Python editor/approval/persistence API.
            corrected = json.loads(read("media/audio.artifacts/transcript.json"))
            original_segments = [dict(segment) for segment in corrected["segments"]]
            for segment in corrected["segments"]:
                segment["text"] = segment["text"].replace("Original", "Corrected")
            assert all({k: v for k, v in a.items() if k != "text"} == {k: v for k, v in b.items() if k != "text"}
                       for a, b in zip(original_segments, corrected["segments"]))
            await put("artifacts", "media/corrected/transcript.json", json.dumps(corrected))
            normalized = TranscriptionResult(text=" ".join(s["text"] for s in corrected["segments"]), language=corrected["language"],
                duration_milliseconds=corrected["durationMilliseconds"], segments=[TranscriptionSegment(
                    text=s["text"], speaker=s["speaker"], language=s["language"], start_seconds=s["startMilliseconds"] / 1000,
                    duration_seconds=(s["endMilliseconds"] - s["startMilliseconds"]) / 1000) for s in corrected["segments"]])
            await put("artifacts", "media/corrected/document.md", build_transcription_markdown(normalized))
            counts_before_index = counts.copy()
            jobs = {name: parse_request(json.dumps(raw), worker="index", callbacks={"local"}) for name, raw in requests.items()
                    if name.startswith(("index", "delete")) or name == "reassign"}
            profile = jobs["indexPrincipal"].index_profile
            embedder = StubEmbeddings()
            client = AsyncQdrantClient(path=str(directory / "qdrant"))
            indexer = PointSetIndexer(ProfileCatalog([profile]), embedder, QdrantPointStore(client), tokenizer=tokenizer,
                                      tokenizer_id="cl100k_base", batch_size=2)

            def index_processor():
                ordered = storage.ordered_indexer(indexer, state_container="technical", state_prefix="index",
                                                   source_container="artifacts", target_identity="n16-local-qdrant")
                return IndexProcessor(index_settings, storage, ordered, webhook)

            async def points():
                result, offset = await client.scroll(profile.collection, limit=1000, with_payload=True, with_vectors=False)
                assert offset is None
                return result

            try:
                final_section = str(final_review.sections[0].id)
                for name in ("indexAdditional", "indexTranscript"):
                    requests[name]["sectionContext"]["sectionId"] = final_section
                inbox.lose_next_acknowledgement()
                await deliver(index_settings, index_processor(), requests["indexPrincipal"], completed=False)
                embedding_count = len(embedder.calls)
                json_key = ("artifacts", requests["indexPrincipal"]["source"]["blobName"])
                frozen_json = blobs.data.pop(json_key)
                await deliver(index_settings, index_processor(), requests["indexPrincipal"])
                blobs.data[json_key] = frozen_json
                assert len(embedder.calls) == embedding_count
                principal_points = await points()
                assert {p.payload["sectionId"] for p in principal_points} == {str(s.id) for s in final_review.sections}
                assert all(not p.payload["provenance"]["pages"] and "Obsolete" not in p.payload["text"] for p in principal_points)
                for name in ("indexAdditional", "indexTranscript"):
                    await deliver(index_settings, index_processor(), requests[name])
                transcript_points = [p for p in await points() if p.payload["contentKey"] == "fixture:audio"]
                assert transcript_points and "Corrected first phrase" in " ".join(p.payload["text"] for p in transcript_points)
                citations = [s for p in transcript_points for s in p.payload["provenance"]["segments"]]
                assert {s["id"] for s in citations} == {s["id"] for s in corrected["segments"]}
                assert min(s["startMilliseconds"] for s in citations) == 1000 and max(s["endMilliseconds"] for s in citations) == 6000
                checks.extend(["corrected-transcript", "callback-only-replay"])
                saved_artifacts = {key: value for key, value in blobs.data.items() if key[0] in {"sources", "artifacts"}}
                # Retire principal, explicitly detach audio. Neither delete touches files/other contents.
                await deliver(index_settings, index_processor(), requests["deletePrincipal"])
                assert any(p.payload["contentKey"] == "fixture:additional" for p in await points())
                await deliver(index_settings, index_processor(), requests["deleteTranscript"])
                remaining = await points()
                assert remaining and all(p.payload["contentKey"] == "fixture:additional" for p in remaining)
                await deliver(index_settings, index_processor(), requests["indexTranscript"])
                assert inbox.events[-1]["eventType"] == "content.index.operation.superseded"
                assert [p.id for p in await points()] == [p.id for p in remaining]
                checks.append("scoped-delete-and-stale-rejection")
                # Explicit synthetic replacement context; never automatic title matching.
                await deliver(index_settings, index_processor(), requests["reassign"])
                reassigned = [p for p in await points() if p.payload["contentKey"] == "fixture:audio"]
                assert reassigned and all(p.payload["headingPath"] == ["Reassigned fixture"] and p.payload["operationSequence"] == 3
                                          for p in reassigned)
                assert all(blobs.data[key] == value for key, value in saved_artifacts.items())
                assert counts == counts_before_index and counts["extraction"] == 2 and counts["speech"] == 3
                assert all(tokenizer.count_tokens(text) <= profile.max_chunk_tokens for batch in embedder.calls for text in batch)
                checks.append("detach-and-reassign-without-reconversion")
                expected_count = len(await points())
            finally:
                await client.close()
            reopened = AsyncQdrantClient(path=str(directory / "qdrant"))
            try:
                assert (await reopened.count(profile.collection)).count == expected_count
            finally:
                await reopened.close()
            checks.append("persistent-local-qdrant")
    assert not blobs.leases
    assert not list((directory / "temporary").glob("*"))
    assert len(inbox.events) == 13 and inbox.deliveries == 15
    assert not any(event["eventType"].endswith("failed") for event in inbox.events)
    for (container, name), (raw, _, _) in blobs.data.items():
        if container in {"sources", "artifacts"}:
            output = directory / container / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
    (directory / "events.json").write_text(json.dumps(inbox.events, indent=2, ensure_ascii=False), encoding="utf-8")
    (directory / "requests.json").write_text(json.dumps(requests, indent=2), encoding="utf-8")
    report = dict(status="passed-local-only", semanticEmbeddings=False, externalServices=False, checks=checks,
                  settlements=dict(settlements), serviceDoubleCalls=dict(counts), uniqueEvents=len(inbox.events),
                  callbackDeliveries=inbox.deliveries, finalPointCount=expected_count)
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, required=True, help="Explicit existing hash-verified cl100k_base asset")
    parser.add_argument("--output", type=Path, required=True, help="New directory for synthetic local evidence")
    args = parser.parse_args()
    from akay_convert_to_markdown.indexing.tokenizer import Cl100kTokenizer

    # Vocabulary loading is strictly local/hash-verified; no upstream registry/cache.
    tokenizer = Cl100kTokenizer.from_file(args.tokenizer)
    print(json.dumps(asyncio.run(run_demo(args.output, tokenizer=tokenizer)), indent=2))


if __name__ == "__main__":
    main()
