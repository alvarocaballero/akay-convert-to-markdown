"""Contract checks across the consumer, processor and webhook HTTP boundary."""
import json

import httpx
import pytest

from akay_convert_to_markdown.errors.exceptions import DocumentConversionError
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from tests.helpers import FakeConverter, FakeStorage, make_logger, make_settings
from tests.unit.test_consumer import FakeMessage, FakeReceiver, _make_consumer


REQUEST = {
    "requestId": "e0a01a4c-1234-4567-8901-123456789abc",
    "source": {"type": "blob", "blobName": "subjects/3/topics/5/sources/550e8400-e29b-41d4-a716-446655440000.pdf"},
    "destinationBlobName": "subjects/3/topics/5/content/550e8400-e29b-41d4-a716-446655440000.md",
    "contentType": "document",
    "overwriteDestination": True,
    "callback": "topic-content",
    "payload": {"topicContentId": 15, "topicId": 5, "userId": 1234},
}


@pytest.mark.parametrize("failure", [False, True])
async def test_akay_message_to_webhook(failure, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    class TrackingStorage(FakeStorage):
        def __init__(self):
            super().__init__()
            self.overwrites = []

        async def upload_file(self, container, blob_name, source, *, overwrite=False):
            self.overwrites.append(overwrite)
            await super().upload_file(container, blob_name, source, overwrite=overwrite)

    settings = make_settings(temp_directory=tmp_path, source_container_name="sources",
                             destination_container_name="content",
                             webhook_callbacks={"topic-content": "http://localhost:5246/api/webhooks/topic-content-converted"})
    converter = FakeConverter()
    if failure:
        converter.error = DocumentConversionError("conversion failed")
    storage = TrackingStorage()
    storage.existing_blobs[REQUEST["destinationBlobName"]] = True
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        webhook = WebhookClient(settings, http)
        processor = DocumentProcessor(settings, storage, converter, webhook, make_logger())
        receiver = FakeReceiver()
        message = FakeMessage(iter([json.dumps(REQUEST).encode()]))
        await _make_consumer(settings, processor)._handle_message(receiver, message)

    assert receiver.completed == [message]
    assert not receiver.abandoned
    assert len(calls) == 1
    assert str(calls[0].url) == "http://localhost:5246/api/webhooks/topic-content-converted"
    assert calls[0].headers["X-Api-Key"] == "test-secret"
    event = json.loads(calls[0].content)
    assert event["eventType"] == ("document.conversion.failed" if failure else "document.conversion.completed")
    for field in ("requestId", "source", "destinationBlobName", "contentType", "payload"):
        assert event[field] == REQUEST[field]
    assert all(type(value) is int for value in event["payload"].values())
    assert storage.downloads[0][:2] == ("sources", REQUEST["source"]["blobName"])
    if failure:
        assert event["error"] == {"code": "DOCUMENT_CONVERSION_FAILED", "message": "conversion failed"}
    else:
        assert storage.uploads[0][:2] == ("content", REQUEST["destinationBlobName"])
        assert storage.overwrites == [True]
    assert calls[0].headers["Idempotency-Key"] == f"convert-to-markdown:{REQUEST['requestId']}:{'failed' if failure else 'completed'}"


async def test_redelivery_with_overwrite_reconverts_and_sends_webhook_again(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200)

    settings = make_settings(temp_directory=tmp_path)
    converter = FakeConverter()
    storage = FakeStorage()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        processor = DocumentProcessor(settings, storage, converter, WebhookClient(settings, http), make_logger())
        consumer = _make_consumer(settings, processor)
        receiver = FakeReceiver()
        await consumer._handle_message(receiver, FakeMessage(json.dumps(REQUEST)))
        await consumer._handle_message(receiver, FakeMessage(json.dumps(REQUEST)))

    assert len(converter.calls) == 2
    assert len(storage.uploads) == 2
    assert len(calls) == 2
    assert len(receiver.completed) == 2
    assert calls[0].headers["Idempotency-Key"] == calls[1].headers["Idempotency-Key"]
