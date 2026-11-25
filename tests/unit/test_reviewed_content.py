"""N9A: reviewed artifacts through real Markdown/Core APIs and durable local doubles."""

import importlib
import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from docling_core.types.doc import DocItemLabel, DoclingDocument, ImageRef

from akay_convert_to_markdown.contracts.artifacts import parse_review
from akay_convert_to_markdown.contracts.events import conversion_completed, request_failed
from akay_convert_to_markdown.contracts.requests import DocumentRequest, parse_request
from akay_convert_to_markdown.errors.exceptions import InvalidMessageError, PermanentError, WebhookError, BlobStorageError
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from tests.unit.test_artifact_publication import MemoryBlobs, request as base_request
from tests.unit.test_content_chunking import CharacterTokenizer, request as index_request, transcript

FIXTURES = Path(__file__).parents[1] / "fixtures/content_processing"


def rebuild_request(**updates):
    data = base_request().model_dump(mode="json", by_alias=True)
    data.pop("destinationBlobName")
    data.update(operation="rebuildFromMarkdown", source={"type": "blob", "blobName": "shared/extracted.md"},
                documentOptions={"extractSections": True})
    data.update(updates)
    return parse_request(json.dumps(data), worker="document", callbacks={"local", "topic-content"})


def original_review():
    return {"schemaVersion": 1, "contentKey": "opaque:á", "contentType": "document",
            "source": {"type": "blob", "blobName": "original/source.pdf"},
            "summary": {"pageCount": 7, "imageCount": 1}, "sections": [], "tables": [],
            "images": [{"id": "figure-001", "blobName": "shared/extracted.artifacts/images/figure-001.png", "pageNumber": 4}],
            "confidence": {"meanGrade": "good", "pages": [{"pageNumber": 4, "ocrScore": 0.9}]},
            "processing": {"engine": "docling", "engineVersion": "2.141.0"}}


@pytest.fixture
def api(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Reconstruction must not open image resources or network connections")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(ImageRef, "pil_image", property(forbidden))
    from docling.backend.utils.image_resource_loader import ImageResourceLoader
    monkeypatch.setattr(ImageResourceLoader, "load_image_ref", forbidden)
    return importlib.import_module("akay_convert_to_markdown.conversion.markdown_rebuild")


def test_default_convert_and_document_callbacks_include_operation():
    request = base_request()
    assert request.operation == "convert"
    from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout
    event = conversion_completed(request, ArtifactLayout.for_destination(request.destination_blob_name).document_refs())
    assert event.model_dump(by_alias=True)["operation"] == "convert"
    assert request_failed(request, code="TEST", message="Safe").model_dump(by_alias=True)["operation"] == "convert"


@pytest.mark.parametrize("updates", [
    {"operation": None}, {"operation": "unknown"}, {"operation": 1},
    {"extractionReviewBlobName": "shared/extracted.artifacts/review.json"},
    {"operation": "convert"}, {"source": {"type": "blob", "blobName": "source.pdf"}},
    {"source": {"type": "blob", "blobName": "shared/extracted.artifacts/document.md"}},
    {"destinationBlobName": "shared/extracted.md"},
    {"documentOptions": {"codeEnrichment": True}}, {"documentOptions": {"formulaEnrichment": True}},
    {"documentOptions": {"ocrLanguage": None}}, {"documentOptions": {"ocrLanguage": " es"}},
])
def test_invalid_rebuild_contracts(updates):
    with pytest.raises(InvalidMessageError):
        rebuild_request(**updates)


@pytest.mark.parametrize("language", ["es", "eu", "gl", "ca", "fr", "en", "de"])
def test_rebuild_retains_valid_ocr_contract_without_inference(language):
    assert rebuild_request(documentOptions={"ocrLanguage": language}).document_options.ocr_language == language


async def test_rebuild_preserves_markdown_and_images_but_regenerates_structure(api, tmp_path):
    request = rebuild_request()
    raw = (FIXTURES / "reviewed-draft.md").read_bytes()
    review_raw = json.dumps(original_review())
    result = await api.rebuild_document_artifacts(raw, review_raw, request, tmp_path / "one")
    again = await api.rebuild_document_artifacts(raw, review_raw, request, tmp_path / "two")
    assert result == again
    review = result.review
    assert review.processing.operation == "rebuildFromMarkdown"
    assert review.extraction_review_blob_name is None
    assert review.source == request.source
    assert review.images == parse_review(review_raw).images
    assert review.summary.image_count == 1 and review.summary.page_count is None
    assert review.confidence.mean_grade is None and review.confidence.low_grade is None and review.confidence.pages == []
    assert [s.title for s in review.sections] == ["Renamed", "Repeated", "Added", "Repeated"]
    assert len({s.id for s in review.sections}) == 4
    assert all(s.page_number is None for s in review.sections)
    assert len(review.tables) == 1 and all(t.page_number is None for t in review.tables)
    assert result.markdown == raw.decode()
    assert '<!-- akay-section:start id="literal-code" -->' in result.markdown
    assert not list((tmp_path / "one").glob("*.md"))
    assert "extracted.artifacts/images/figure-001.png" in result.markdown
    assert "https://unreachable.invalid/never-fetch.png" in result.markdown and "does-not-exist.png" in result.markdown
    without_markers = re.sub(r'<!-- akay-section:start id="[0-9a-f-]{36}" -->\n', "", result.markdown)
    expected = re.sub(r'<!-- akay-section:start id="[0-9a-f-]{36}" -->\n', "", raw.decode())
    assert without_markers == expected
    doc = DoclingDocument.model_validate(result.docling_json)
    assert "E=mc^2" in doc.export_to_markdown() and 'print("keep code")' in doc.export_to_markdown()
    assert not doc.pages and all(not item.prov for item in doc.texts + doc.tables + doc.pictures)
    assert all(item.image is None for item in doc.pictures)
    assert not list((tmp_path / "one").rglob("*.png"))
    assert parse_review((tmp_path / "one/extracted.artifacts/review.json").read_bytes()) == review

    from akay_convert_to_markdown.indexing.chunking import chunk_content
    req = index_request(mode="fromReview", budget=400,
                        source={"type": "blob", "format": "docling", "blobName": result.artifacts.docling_json_blob_name},
                        sectionContext={"mode": "fromReview", "reviewBlobName": result.artifacts.review_blob_name})
    chunks = chunk_content(req, json.dumps(result.docling_json), review_raw=review.model_dump_json(by_alias=True),
                           tokenizer=CharacterTokenizer(limit=400), tokenizer_id="test-character-v1")
    text = "\n".join(c.contextualized_text for c in chunks)
    assert "Corrected main text" in text and "Moved second body" in text and "Edited" in text
    assert "Not a heading" in text  # code remains content, never a domain section
    assert all(c.provenance.pages == [] for c in chunks)
    assert {c.section_id for c in chunks if c.section_id} == {s.id for s in review.sections}


@pytest.mark.parametrize("change", ["foreign", "media", "image_path", "malformed"])
async def test_unrelated_or_invalid_extraction_report_fails_safely(api, tmp_path, change):
    data = original_review()
    if change == "foreign":
        data["contentKey"] = "foreign"
    elif change == "media":
        data["contentType"] = "video"
    elif change == "image_path":
        data["images"][0]["blobName"] = "foreign/image.png"
    raw = "invalid private payload" if change == "malformed" else json.dumps(data)
    with pytest.raises(PermanentError) as error:
        await api.rebuild_document_artifacts(b"# Edited\n\nBody", raw, rebuild_request(), tmp_path / "out")
    assert "private payload" not in str(error.value)


@pytest.mark.parametrize("budget", [55, 400])
def test_corrected_transcript_changes_chunks_without_changing_citations(budget):
    from akay_convert_to_markdown.indexing.chunking import chunk_content
    corrected = json.loads((FIXTURES / "corrected-transcript.json").read_text(encoding="utf-8"))
    original = transcript()
    for a, b in zip(original["segments"], corrected["segments"]):
        assert {k: v for k, v in a.items() if k != "text"} == {k: v for k, v in b.items() if k != "text"}
    req = index_request(format="transcript", budget=budget)
    def chunks(data):
        return chunk_content(req, json.dumps(data), tokenizer=CharacterTokenizer(limit=budget), tokenizer_id="test-character-v1")
    before, after = chunks(original), chunks(corrected)
    if budget == 55:
        assert len(after) > 1
    else:
        assert len(after) == 1
    assert "Corrected" not in " ".join(c.text for c in before)
    assert "Corrected first phrase." in " ".join(c.text for c in after)
    assert "Corrected second phrase." in " ".join(c.text for c in after)
    citations = {s.id: s for c in after for s in c.provenance.segments}
    assert list(citations) == ["s1", "s2"]
    assert (citations["s1"].start_milliseconds, citations["s1"].end_milliseconds) == (1000, 2500)
    assert (citations["s2"].start_milliseconds, citations["s2"].end_milliseconds) == (3000, 6000)
    assert all(c.origin.url == corrected["origin"]["url"] and c.token_count <= budget for c in after)


@pytest.mark.parametrize("failure", ["callback", "partial"])
async def test_document_runtime_rebuild_recovery_needs_no_extraction_or_inputs(api, tmp_path, failure):
    from akay_convert_to_markdown.config.settings import DocumentWorkerSettings
    from akay_convert_to_markdown.processing.published_document_processor import PublishedDocumentProcessor
    from tests.helpers import make_settings, FakeWebhook

    settings = DocumentWorkerSettings(**make_settings().model_dump(exclude={"servicebus_queue_name"}),
                                      DOCUMENT_SERVICEBUS_QUEUE_NAME="documents", publication_state_container_name="technical",
                                      publication_state_prefix="processing")
    settings.temp_directory = tmp_path
    job = rebuild_request(callback="topic-content")
    blobs = MemoryBlobs()
    storage, webhook = BlobStorage(blobs), FakeWebhook()
    await blobs.get_blob_client(settings.source_container_name, job.source.blob_name).upload_blob((FIXTURES / "reviewed-draft.md").read_bytes())
    review_name = "shared/extracted.artifacts/review.json"
    await blobs.get_blob_client(settings.destination_container_name, review_name).upload_blob(json.dumps(original_review()).encode())
    image_name = original_review()["images"][0]["blobName"]
    await blobs.get_blob_client(settings.destination_container_name, image_name).upload_blob(b"original crop")
    original_image = blobs.data[(settings.destination_container_name, image_name)]
    engine = AsyncMock()
    engine.extract.side_effect = AssertionError("Rebuild must not extract the original")
    processor = PublishedDocumentProcessor(settings, storage, engine, webhook, logging.getLogger("n9a"))
    if failure == "callback":
        webhook.error = WebhookError("retry")
    else:
        blobs.fail_name = review_name
    with pytest.raises((WebhookError, BlobStorageError)):
        await processor.process(job)
    del blobs.data[(settings.source_container_name, job.source.blob_name)]
    webhook.error = None
    await processor.process(job)
    await processor.process(job)
    event = webhook.calls[-1][1]
    assert event["eventType"] == "document.conversion.completed" and event["operation"] == "rebuildFromMarkdown"
    assert event["destinationBlobName"] == job.source.blob_name
    assert "images" not in event and "imagesPrefix" not in event
    final = parse_review(blobs.data[(settings.destination_container_name, event["artifacts"]["reviewBlobName"])][0])
    assert final.images[0].blob_name == image_name
    assert blobs.data[(settings.destination_container_name, image_name)] == original_image
    assert final.confidence.mean_grade is None and final.extraction_review_blob_name is None
    engine.extract.assert_not_called()
    assert not list(tmp_path.iterdir())


async def test_extraction_to_edited_final_chunks_uses_no_old_json(api, tmp_path):
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
    from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts
    source = tmp_path / "initial.md"
    source.write_text("# Original title\n\nUncorrected content.\n\n## Repeated\n\nFirst body.\n\n"
                      "## Deleted\n\nRemove this.\n\n## Repeated\n\nSecond body.", encoding="utf-8")
    initial_job = base_request(source={"type": "blob", "blob_name": "original/initial.md"},
                               destination_blob_name="shared/extracted.md", document_options={"extract_sections": True})
    initial = await export_document_artifacts(await DoclingDocumentConverter().extract(source, initial_job.document_options),
                                              initial_job, tmp_path / "initial")
    final = await api.rebuild_document_artifacts(b"# Renamed\n\nCorrected content.\n\n## Repeated\n\nMoved second body.\n\n"
                                                 b"## New\n\nNew body.\n\n## Repeated\n\nMoved first body.",
                                                 initial.review.model_dump_json(by_alias=True), rebuild_request(), tmp_path / "final")
    from akay_convert_to_markdown.indexing.chunking import chunk_content
    req = index_request(mode="fromReview", budget=200,
                        source={"type": "blob", "format": "docling", "blobName": final.artifacts.docling_json_blob_name},
                        sectionContext={"mode": "fromReview", "reviewBlobName": final.artifacts.review_blob_name})
    chunks = chunk_content(req, json.dumps(final.docling_json), review_raw=final.review.model_dump_json(by_alias=True),
                           tokenizer=CharacterTokenizer(limit=200), tokenizer_id="test-character-v1")
    text = "\n".join(c.contextualized_text for c in chunks)
    assert "Corrected content." in text and "New body." in text
    assert all(old not in text for old in ["Original title", "Uncorrected", "Deleted", "Remove this"])
    assert [s.title for s in final.review.sections] == ["Renamed", "Repeated", "New", "Repeated"]
    assert text.index("Moved second body.") < text.index("New body.") < text.index("Moved first body.")
    repeated = [s for s in final.review.sections if s.title == "Repeated"]
    assert repeated[0].id != repeated[1].id


@pytest.mark.parametrize("sections", [True, False])
async def test_structural_markers_setext_inline_and_literal_code(api, tmp_path, sections):
    text = ('<!-- akay-section:start id="stale" -->\n**Formatted** heading\n=====================\n\n'
            'Keep `<!-- akay-section:start id="inline-code" -->` literally.\n\n'
            '    # Indented code\n    <!-- akay-section:start id="indented-code" -->\n\n'
            '~~~text\n## Fenced heading\n~~~\n\n## Last\n\nFinal body.\n')
    result = await api.rebuild_document_artifacts(text, json.dumps(original_review()),
                                                 rebuild_request(documentOptions={"extractSections": sections}), tmp_path / "out")
    assert result.markdown == text
    assert 'id="inline-code"' in result.markdown and 'id="indented-code"' in result.markdown
    assert "**Formatted** heading\n=====================" in result.markdown
    assert [s.title for s in result.review.sections] == (["**Formatted** heading", "Last"] if sections else [])
    assert result.markdown.count('id="') == 3


@pytest.mark.parametrize("link", ["removed", "reference", "local", "remote", "data", "malformed"])
async def test_only_referenced_inventory_images_are_retained_without_resource_reads(api, tmp_path, link):
    content = {"removed": "", "reference": '![Original][pic]\n\n[pic]: <extracted.artifacts/images/figure-001.png> "caption"',
               "local": "![New](file:///private/secret.png)", "remote": "![New](https://invalid.example/image.png)",
               "data": "![New](data:image/png;base64,bm90YW5pbWFnZQ==)", "malformed": "![New](https://[broken/image.png)"}[link]
    result = await api.rebuild_document_artifacts("# Text\n\nKeep body.\n\n" + content, json.dumps(original_review()),
                                                 rebuild_request(), tmp_path / "out")
    assert result.review.images == (parse_review(json.dumps(original_review())).images if link == "reference" else [])
    if link == "reference":
        assert '[pic]: <extracted.artifacts/images/figure-001.png> "caption"' in result.markdown
    else:
        assert content in result.markdown


async def test_notification_of_invalid_document_recovers_operation(tmp_path):
    from akay_convert_to_markdown.processing.published_document_processor import PublishedDocumentProcessor
    from akay_convert_to_markdown.models.conversion_request import recover_invalid_message_identity
    from tests.helpers import make_settings, FakeWebhook, make_logger

    raw = json.dumps({"schemaVersion": 1, "requestId": str(uuid4()), "contentKey": "opaque",
                      "operation": "rebuildFromMarkdown", "contentType": "document", "callback": "topic-content"})
    webhook = FakeWebhook()
    processor = PublishedDocumentProcessor(make_settings(), None, None, webhook, make_logger())
    await processor.notify_invalid_message(recover_invalid_message_identity(raw), logging.LoggerAdapter(make_logger(), {}))
    assert webhook.calls[-1][1]["operation"] == "rebuildFromMarkdown"


async def test_pre_n9a_convert_receipt_replays_without_rebuild(tmp_path):
    from tests.unit.test_artifact_publication import PackageBuilder, Notifications, publisher
    api = importlib.import_module("akay_convert_to_markdown.storage.artifact_publication")
    blobs, job = MemoryBlobs(), base_request()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(blobs)
    await publisher(blobs).deliver(job, build, notify)
    key = next(key for key in blobs.data if "/publications/" in key[1])
    raw, etag, metadata = blobs.data[key]
    receipt = json.loads(raw)
    identity = json.loads(receipt["requests"][str(job.request_id)])
    identity.pop("operation")
    identity.pop("extractionReviewBlobName")
    receipt["requests"][str(job.request_id)] = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    blobs.data[key] = (json.dumps(receipt).encode(), etag, metadata)
    await publisher(blobs).deliver(job, build, notify)
    assert build.count == 1 and len(notify.events) == 1


def test_fresh_rebuild_cannot_import_extraction_models_pipelines_or_fetch_resources(tmp_path):
    script = '''
import asyncio, builtins, json, socket, sys
from pathlib import Path
original = builtins.__import__
def guarded(name, globals=None, locals=None, fromlist=(), level=0):
    extraction = name.startswith(("docling.models.stages", "docling.models.layout_model", "docling.models.table_structure_model",
                                 "docling.models.rapid_ocr_model", "docling.models.code_formula_model"))
    if level == 0 and (extraction or name.startswith(("docling.pipeline", "docling.document_converter"))):
        raise AssertionError("Forbidden reconstruction import: " + name)
    if level == 0 and name.startswith(("azure", "yt_dlp")):
        raise ImportError("Optional foreign service package unavailable")
    return original(name, globals, locals, fromlist, level)
builtins.__import__ = guarded
def forbidden(*args, **kwargs):
    raise AssertionError("No resource fetch")
socket.create_connection = socket.getaddrinfo = forbidden
from akay_convert_to_markdown.contracts.requests import DocumentRequest
from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts
from docling_core.types.doc import ImageRef
ImageRef.pil_image = property(forbidden)
data = json.loads(sys.stdin.read())
job = DocumentRequest.model_validate_json(json.dumps(data["request"]))
result = asyncio.run(rebuild_document_artifacts("# Edited\\n\\nBody.", json.dumps(data["review"]), job, Path(sys.argv[1])))
assert result.review.sections[0].title == "Edited"
print("PASS: model-free offline reconstruction")
'''
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "PATH") if key in os.environ}
    environment["PYTHONPATH"] = str(Path(__file__).parents[2] / "src")
    environment["USERPROFILE"] = environment["HOME"] = str(tmp_path)
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "out")],
                            input=json.dumps({"request": rebuild_request().model_dump(mode="json", by_alias=True), "review": original_review()}),
                            text=True, capture_output=True, env=environment, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "PASS: model-free offline reconstruction" in result.stdout


async def test_foreign_report_failure_is_replayed_with_operation(api, tmp_path):
    from akay_convert_to_markdown.config.settings import DocumentWorkerSettings
    from akay_convert_to_markdown.processing.published_document_processor import PublishedDocumentProcessor
    from tests.helpers import make_settings, FakeWebhook

    settings = DocumentWorkerSettings(**make_settings().model_dump(exclude={"servicebus_queue_name"}),
                                      DOCUMENT_SERVICEBUS_QUEUE_NAME="documents", publication_state_container_name="technical",
                                      publication_state_prefix="processing")
    settings.temp_directory = tmp_path
    blobs, webhook, engine = MemoryBlobs(), FakeWebhook(), AsyncMock()
    job = rebuild_request(callback="topic-content")
    await blobs.get_blob_client(settings.source_container_name, job.source.blob_name).upload_blob(b"# Edited\n\nBody")
    report = original_review()
    report["contentKey"] = "other"
    await blobs.get_blob_client(settings.destination_container_name, "shared/extracted.artifacts/review.json").upload_blob(json.dumps(report).encode())
    processor = PublishedDocumentProcessor(settings, BlobStorage(blobs), engine, webhook, logging.getLogger("n9a"))
    webhook.send = AsyncMock(side_effect=WebhookError("retry failure callback"))
    with pytest.raises(WebhookError):
        await processor.process(job)
    first = webhook.send.call_args.args[1]
    assert first["eventType"] == "document.conversion.failed" and first["operation"] == "rebuildFromMarkdown"
    assert "other" not in json.dumps(first)
    del blobs.data[(settings.source_container_name, job.source.blob_name)]
    webhook.send.side_effect = None
    await processor.process(job)
    assert webhook.send.call_args.args[1] == first
    assert not any(key == (settings.destination_container_name, job.destination_blob_name) for key in blobs.data)
    engine.extract.assert_not_called()


async def test_repeated_cancellation_drains_rebuild_before_return(api, monkeypatch, tmp_path):
    entered, finish = threading.Event(), threading.Event()
    parse = api._parse_document
    def blocked(*args):
        entered.set()
        assert finish.wait(10)
        return parse(*args)
    monkeypatch.setattr(api, "_parse_document", blocked)
    task = asyncio.create_task(api.rebuild_document_artifacts(b"# Edited\n\nBody", json.dumps(original_review()),
                                                              rebuild_request(), tmp_path / "out"))
    try:
        while not entered.is_set():
            await asyncio.sleep(0.005)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()  # event loop advances, caller still owns the writer
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (tmp_path / "out/extracted.artifacts/review.json").is_file()


async def test_rebuild_rejects_changed_parameters_under_same_request_id(api, tmp_path):
    from tests.unit.test_artifact_publication import publisher
    from akay_convert_to_markdown.storage.artifact_publication import ArtifactPackage
    blobs, job, notify = MemoryBlobs(), rebuild_request(), AsyncMock()
    result = await api.rebuild_document_artifacts("# Text\n\nBody", None, job, tmp_path / "out")
    build = AsyncMock(return_value=ArtifactPackage(files={
        result.artifacts.docling_json_blob_name: tmp_path / "out/extracted.artifacts/document.docling.json",
        result.artifacts.review_blob_name: tmp_path / "out/extracted.artifacts/review.json"}))
    await publisher(blobs).deliver(job, build, notify)
    changed = job.model_copy(update={"payload": {"changed": True}})
    with pytest.raises(PermanentError):
        await publisher(blobs).deliver(changed, build, notify)
    assert build.await_count == 1


async def test_rebuild_accepts_current_review_from_previous_rebuild(api, tmp_path):
    job = rebuild_request()
    first = await api.rebuild_document_artifacts("# First\n\nBody", json.dumps(original_review()), job, tmp_path / "first")
    second = await api.rebuild_document_artifacts("# Second\n\nNew body", first.review.model_dump_json(by_alias=True),
                                                 job, tmp_path / "second")
    assert second.review.sections[0].title == "Second"
    assert second.review.extraction_review_blob_name is None
