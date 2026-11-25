"""Edited Markdown is authoritative; only its derived artifacts may be mutated."""

import json
import logging
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from akay_convert_to_markdown.config.settings import DocumentWorkerSettings
from akay_convert_to_markdown.contracts.artifacts import parse_review
from akay_convert_to_markdown.contracts.events import parse_event
from akay_convert_to_markdown.errors.exceptions import BlobStorageError, WebhookError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.published_document_processor import PublishedDocumentProcessor
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from tests.helpers import FakeWebhook, make_settings
from tests.unit.test_artifact_publication import MemoryBlob, MemoryBlobs
from tests.unit.test_reviewed_content import original_review, rebuild_request


PREFIX = "shared/extracted.artifacts/"
MD = "shared/extracted.md"
REVIEW = PREFIX + "review.json"
JSON = PREFIX + "document.docling.json"
KEEP = PREFIX + "images/figure-001.png"
REMOVE = PREFIX + "images/figure-002.png"
OTHER = PREFIX + "images/unrelated.png"


@pytest.fixture
async def runtime(tmp_path):
    settings = DocumentWorkerSettings(**make_settings().model_dump(exclude={"servicebus_queue_name"}),
                                      DOCUMENT_SERVICEBUS_QUEUE_NAME="documents", publication_state_container_name="technical",
                                      publication_state_prefix="processing")
    settings.temp_directory = tmp_path
    # Exercise the same physical Markdown Blob for reading and artifact naming.
    settings.source_container_name = settings.destination_container_name
    blobs, webhook, engine = MemoryBlobs(), FakeWebhook(), AsyncMock()
    engine.extract.side_effect = AssertionError("An artifact rebuild must not run extraction")
    processor = PublishedDocumentProcessor(settings, BlobStorage(blobs), engine, webhook, logging.getLogger("rebuild"))

    async def put(name, data):
        await blobs.get_blob_client(settings.source_container_name, name).upload_blob(data, overwrite=True)

    raw = b'\xef\xbb\xbf# Edited heading\r\n\r\nCorrected body.\r\n\r\n![Keep](extracted.artifacts/images/figure-001.png)\r\n'
    await put(MD, raw)
    review = original_review()
    review["images"].append({"id": "figure-002", "blobName": REMOVE})
    review["summary"]["imageCount"] = 2
    await put(REVIEW, json.dumps(review).encode())
    await put(JSON, b'{"old":"data"}')
    for name in (KEEP, REMOVE, OTHER):
        await put(name, name.encode())
    return settings, blobs, webhook, engine, processor, put


async def test_replaces_artifacts_prunes_only_unused_inventory_and_never_writes_markdown(runtime):
    settings, blobs, webhook, engine, processor, _ = runtime
    container = settings.destination_container_name
    before = dict(blobs.data)
    start = len(blobs.calls)
    job = rebuild_request(callback="topic-content")
    assert "destinationBlobName" not in job.model_dump(mode="json", by_alias=True)
    assert "extractionReviewBlobName" not in job.model_dump(mode="json", by_alias=True)
    assert await processor.process(job) == ProcessingResult.COMPLETED
    assert blobs.data[(container, MD)] == before[(container, MD)]  # bytes, ETag and metadata
    assert blobs.data[(container, KEEP)] == before[(container, KEEP)]
    assert blobs.data[(container, OTHER)] == before[(container, OTHER)]
    assert (container, REMOVE) not in blobs.data
    assert not any(call[1] == (container, MD) for call in blobs.calls[start:])
    review = parse_review(blobs.data[(container, REVIEW)][0])
    assert [s.title for s in review.sections] == ["Edited heading"]
    assert [i.blob_name for i in review.images] == [KEEP]
    assert review.extraction_review_blob_name is None and review.confidence.pages == []
    assert b"Corrected body" in blobs.data[(container, JSON)][0]
    event = webhook.calls[-1][1]
    assert event["destinationBlobName"] == MD
    assert event["artifacts"] == {"doclingJsonBlobName": JSON, "reviewBlobName": REVIEW}
    parse_event(json.dumps(event))
    assert not any("extraction" in key[1] or "quarantine" in key[1] for key in blobs.data)
    engine.extract.assert_not_called()


async def test_next_edit_overwrites_same_json_and_review_without_replaying_old_writes(runtime):
    settings, blobs, webhook, engine, processor, put = runtime
    first = rebuild_request(callback="topic-content")
    await processor.process(first)
    await put(MD, b"# Second edit\n\nNew body, no image.\n")
    second = first.model_copy(update={"request_id": uuid4()})
    await processor.process(second)
    snapshot = {key: value for key, value in blobs.data.items() if key[0] == settings.destination_container_name}
    assert b"Second edit" in snapshot[(settings.destination_container_name, JSON)][0]
    assert parse_review(snapshot[(settings.destination_container_name, REVIEW)][0]).images == []
    assert (settings.destination_container_name, KEEP) not in snapshot
    await processor.process(first)
    assert snapshot == {key: value for key, value in blobs.data.items() if key[0] == settings.destination_container_name}
    engine.extract.assert_not_called()


@pytest.mark.parametrize("failure", ["callback", "json", "review", "lost-write-response", "receipt"])
async def test_retry_uses_frozen_artifacts_without_source_or_old_review(runtime, monkeypatch, failure):
    from akay_convert_to_markdown.conversion import markdown_rebuild

    settings, blobs, webhook, _, processor, _ = runtime
    job = rebuild_request(callback="topic-content")
    if failure == "callback":
        webhook.error = WebhookError("lost acknowledgement")
    elif failure == "lost-write-response":
        blobs.fail_after_write = JSON
    elif failure == "receipt":
        blobs.fail_receipt_status = "complete"
    else:
        blobs.fail_name = JSON if failure == "json" else REVIEW
    with pytest.raises((BlobStorageError, WebhookError)):
        await processor.process(job)
    del blobs.data[(settings.source_container_name, MD)]
    if failure != "callback":
        blobs.data.pop((settings.destination_container_name, REVIEW), None)
    monkeypatch.setattr(markdown_rebuild, "_parse_document", lambda *args: pytest.fail("Must not parse on retry"))
    webhook.error = None
    assert await processor.process(job) == ProcessingResult.COMPLETED
    assert b"Corrected body" in blobs.data[(settings.destination_container_name, JSON)][0]
    assert parse_review(blobs.data[(settings.destination_container_name, REVIEW)][0]).images[0].blob_name == KEEP
    assert (settings.destination_container_name, REMOVE) not in blobs.data
    assert not blobs.leases


async def test_lost_image_delete_response_is_safe_to_retry(runtime, monkeypatch):
    settings, blobs, _, _, processor, _ = runtime
    delete = MemoryBlob.delete_blob
    lost = False

    async def delete_with_lost_response(self, **kwargs):
        nonlocal lost
        await delete(self, **kwargs)
        if self.key[1] == REMOVE and not lost:
            lost = True
            raise OSError("delete response lost")

    monkeypatch.setattr(MemoryBlob, "delete_blob", delete_with_lost_response)
    job = rebuild_request(callback="topic-content")
    with pytest.raises(BlobStorageError):
        await processor.process(job)
    assert await processor.process(job) == ProcessingResult.COMPLETED
    assert (settings.destination_container_name, REMOVE) not in blobs.data


async def test_foreign_inventory_cannot_delete_or_replace_existing_files(runtime):
    settings, blobs, webhook, _, processor, put = runtime
    review = original_review()
    review["images"][0]["blobName"] = "another-content/images/figure-001.png"
    await put(REVIEW, json.dumps(review).encode())
    snapshot = dict(blobs.data)
    assert await processor.process(rebuild_request(callback="topic-content")) == ProcessingResult.FAILED_PERMANENT
    for key, value in snapshot.items():
        assert blobs.data[key] == value
    assert webhook.calls[-1][1]["destinationBlobName"] == MD


async def test_markdown_without_existing_review_can_create_json_artifacts(runtime):
    settings, blobs, webhook, _, processor, put = runtime
    await put(MD, b"# New Markdown\n\nPlain text.\n")
    blobs.data.pop((settings.destination_container_name, REVIEW))
    assert await processor.process(rebuild_request(callback="topic-content")) == ProcessingResult.COMPLETED
    review = parse_review(blobs.data[(settings.destination_container_name, REVIEW)][0])
    assert review.images == []
    # Unknown files are not owned merely because they share a prefix.
    assert (settings.destination_container_name, KEEP) in blobs.data
    assert (settings.destination_container_name, OTHER) in blobs.data


@pytest.mark.parametrize("image", [
    '![Keep][figure]\n\n[figure]: <extracted.artifacts/images/figure-001.png> "Edited caption"',
    '<img src="extracted.artifacts/images/figure-001.png" alt="Edited caption">',
    '![Keep](extracted.artifacts/images/figure%2D001.png)',
])
async def test_reference_html_and_encoded_image_paths_keep_the_existing_crop(runtime, image):
    settings, blobs, _, _, processor, put = runtime
    await put(MD, ("# Edited\n\nBody\n\n" + image).encode())
    assert await processor.process(rebuild_request(callback="topic-content")) == ProcessingResult.COMPLETED
    assert parse_review(blobs.data[(settings.destination_container_name, REVIEW)][0]).images[0].blob_name == KEEP


async def test_image_syntax_inside_code_does_not_retain_unused_crops(runtime):
    settings, blobs, _, _, processor, put = runtime
    raw = b'# Edited\n\n```md\n![not an image](extracted.artifacts/images/figure-001.png)\n```\n'
    await put(MD, raw)
    assert await processor.process(rebuild_request(callback="topic-content")) == ProcessingResult.COMPLETED
    assert parse_review(blobs.data[(settings.destination_container_name, REVIEW)][0]).images == []
    assert (settings.destination_container_name, KEEP) not in blobs.data
    assert blobs.data[(settings.destination_container_name, MD)][0] == raw
