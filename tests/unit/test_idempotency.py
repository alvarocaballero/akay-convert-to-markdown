"""Destination reuse and overwrite semantics."""
from azure.core.exceptions import ResourceExistsError
from unittest.mock import AsyncMock, MagicMock

import pytest

from akay_convert_to_markdown.errors.exceptions import WebhookError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from tests.helpers import make_request, make_logger


async def test_redelivery_reuses_destination(settings, fake_storage, fake_converter, fake_webhook):
    processor = DocumentProcessor(settings, fake_storage, fake_converter, fake_webhook, make_logger())
    request = make_request()
    assert await processor.process(request) is ProcessingResult.COMPLETED
    assert await processor.process(request) is ProcessingResult.COMPLETED
    assert len(fake_converter.calls) == 1
    assert len(fake_storage.uploads) == 1
    assert [call[2] for call in fake_webhook.calls] == [f"convert-to-markdown:{request.request_id}:completed"] * 2


async def test_failed_webhook_redelivery_does_not_reconvert(settings, fake_storage, fake_converter, fake_webhook):
    processor = DocumentProcessor(settings, fake_storage, fake_converter, fake_webhook, make_logger())
    request = make_request(payload={"id": 42})
    fake_webhook.error = WebhookError("unavailable")
    with pytest.raises(WebhookError):
        await processor.process(request)
    fake_webhook.error = None
    assert await processor.process(request) is ProcessingResult.COMPLETED
    assert len(fake_converter.calls) == 1
    assert fake_webhook.calls[0][1]["payload"] == {"id": 42}


async def test_overwrite_reconverts_existing_destination(settings, fake_storage, fake_converter, fake_webhook):
    request = make_request(overwrite_destination=True)
    fake_storage.existing_blobs[request.destination_blob_name] = True
    processor = DocumentProcessor(settings, fake_storage, fake_converter, fake_webhook, make_logger())
    assert await processor.process(request) is ProcessingResult.COMPLETED
    assert len(fake_converter.calls) == 1
    assert len(fake_storage.uploads) == 1


async def test_concurrent_create_conflict_is_reused(tmp_path):
    blob = MagicMock()
    blob.upload_blob = AsyncMock(side_effect=ResourceExistsError("already exists"))
    client = MagicMock()
    client.get_blob_client.return_value = blob
    source = tmp_path / "result.md"
    source.write_text("result")
    await BlobStorage(client).upload_file("destination", "result.md", source, overwrite=False)
    assert blob.upload_blob.await_args.kwargs["overwrite"] is False
