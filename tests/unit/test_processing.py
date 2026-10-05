"""DocumentProcessor orchestration tests."""

from __future__ import annotations

import httpx
import pytest

from akay_convert_to_markdown.errors.exceptions import (
    BlobStorageError,
    CallbackNotConfiguredError,
    DocumentConversionError,
    WebhookError,
)
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from tests.helpers import FakeStorage, FakeWebhook, make_request, make_settings, make_logger


def _make_processor(settings, storage, converter, webhook) -> DocumentProcessor:
    return DocumentProcessor(settings, storage, converter, webhook, make_logger())


async def test_success_uploads_and_notifies(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request()

    result = await processor.process(request)

    assert result is ProcessingResult.COMPLETED
    assert len(fake_storage.uploads) == 1
    container, blob_name, _ = fake_storage.uploads[0]
    assert container == "markdown"
    assert blob_name == f"{request.context_id}/{request.document_id}/document.md"

    assert len(fake_webhook.calls) == 1
    callback, payload, idempotency_key = fake_webhook.calls[0]
    assert callback == request.callback
    assert payload["eventType"] == "document.conversion.completed"
    assert payload["callback"] == request.callback
    assert idempotency_key == f"convert-to-markdown:{request.document_id}:completed"


async def test_permanent_failure_sends_failed_event(settings, fake_storage, fake_converter, fake_webhook):
    fake_converter.error = DocumentConversionError("corrupt document")
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request()

    result = await processor.process(request)

    assert result is ProcessingResult.FAILED_PERMANENT
    assert len(fake_webhook.calls) == 1
    callback, payload, idempotency_key = fake_webhook.calls[0]
    assert callback == request.callback
    assert payload["eventType"] == "document.conversion.failed"
    assert payload["callback"] == request.callback
    assert payload["error"]["code"] == "DOCUMENT_CONVERSION_FAILED"
    assert idempotency_key == f"convert-to-markdown:{request.document_id}:failed"


async def test_unsupported_extension_sends_failed_event(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request(file_name="tema-1.xyz")

    result = await processor.process(request)

    assert result is ProcessingResult.FAILED_PERMANENT
    callback, payload, _ = fake_webhook.calls[0]
    assert callback == request.callback
    assert payload["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


async def test_source_missing_sends_failed_event(settings, fake_storage, fake_converter, fake_webhook):
    request = make_request()
    fake_storage.missing.add(request.source_blob_name)
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)

    result = await processor.process(request)

    assert result is ProcessingResult.FAILED_PERMANENT
    assert fake_webhook.calls[0][1]["error"]["code"] == "SOURCE_BLOB_NOT_FOUND"


async def test_maximum_size_exceeded(tmp_path, fake_converter, fake_webhook):
    storage = FakeStorage()
    settings = make_settings(temp_directory=tmp_path, max_document_size_mb=1)
    request = make_request()
    storage.blob_sizes[request.source_blob_name] = 2 * 1024 * 1024
    processor = _make_processor(settings, storage, fake_converter, fake_webhook)

    result = await processor.process(request)

    assert result is ProcessingResult.FAILED_PERMANENT
    assert fake_webhook.calls[0][1]["error"]["code"] == "DOCUMENT_TOO_LARGE"


async def test_transient_storage_error_propagates(tmp_path, fake_converter, fake_webhook):
    storage = FakeStorage()
    storage.download_error = BlobStorageError("temporary outage")
    settings = make_settings(temp_directory=tmp_path)
    processor = _make_processor(settings, storage, fake_converter, fake_webhook)

    with pytest.raises(BlobStorageError):
        await processor.process(make_request())


async def test_webhook_failure_propagates_as_transient(tmp_path, fake_storage, fake_converter):
    fake_webhook = FakeWebhook()
    fake_webhook.error = WebhookError("webhook down")
    settings = make_settings(temp_directory=tmp_path)
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)

    with pytest.raises(WebhookError):
        await processor.process(make_request())


async def test_unknown_callback_is_transient_and_makes_no_http(tmp_path, fake_storage, fake_converter):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request):
        calls.append(request)
        return httpx.Response(200)

    settings = make_settings(temp_directory=tmp_path)
    webhook = WebhookClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    processor = DocumentProcessor(settings, fake_storage, fake_converter, webhook, make_logger())

    with pytest.raises(CallbackNotConfiguredError):
        await processor.process(make_request(callback="unknown-callback"))

    assert calls == []


async def test_temp_files_removed_after_success(tmp_path, fake_converter, fake_webhook):
    storage = FakeStorage()
    settings = make_settings(temp_directory=tmp_path / "akay")
    processor = _make_processor(settings, storage, fake_converter, fake_webhook)
    request = make_request()

    await processor.process(request)

    assert not (settings.temp_directory / str(request.document_id)).exists()


async def test_temp_files_removed_after_failure(tmp_path, fake_converter, fake_webhook):
    storage = FakeStorage()
    fake_converter.error = DocumentConversionError("corrupt")
    settings = make_settings(temp_directory=tmp_path / "akay")
    processor = _make_processor(settings, storage, fake_converter, fake_webhook)
    request = make_request()

    await processor.process(request)

    assert not (settings.temp_directory / str(request.document_id)).exists()


async def test_notify_invalid_message_payload(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    document_id = "47cd79ca-0000-0000-0000-000000000000"
    identity = {"documentId": document_id, "fileName": "a.pdf", "callback": "subject-topic"}

    await processor.notify_invalid_message(identity, make_logger())

    assert len(fake_webhook.calls) == 1
    callback, payload, idempotency_key = fake_webhook.calls[0]
    assert callback == "subject-topic"
    assert payload["eventType"] == "document.conversion.failed"
    assert payload["callback"] == "subject-topic"
    assert payload["documentId"] == document_id
    assert payload["error"]["code"] == "INVALID_MESSAGE"
    assert idempotency_key == f"convert-to-markdown:{document_id}:failed"


async def test_notify_invalid_message_unknown_callback_is_poison(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    identity = {"documentId": "47cd79ca-0000-0000-0000-000000000000", "callback": "unknown-callback"}

    await processor.notify_invalid_message(identity, make_logger())

    assert fake_webhook.calls == []


async def test_completed_webhook_preserves_int_ids(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request(document_id=123, context_id=456, user_id=789)

    await processor.process(request)

    _, payload, _ = fake_webhook.calls[0]
    assert payload["documentId"] == 123
    assert payload["contextId"] == 456
    assert payload["userId"] == 789
    assert isinstance(payload["documentId"], int)


async def test_completed_webhook_preserves_uuid_ids(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request()

    await processor.process(request)

    _, payload, _ = fake_webhook.calls[0]
    assert payload["documentId"] == str(request.document_id)
    assert payload["contextId"] == str(request.context_id)
    assert isinstance(payload["documentId"], str)


async def test_completed_webhook_preserves_mixed_ids(settings, fake_storage, fake_converter, fake_webhook):
    processor = _make_processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request(document_id=123)

    await processor.process(request)

    _, payload, _ = fake_webhook.calls[0]
    assert payload["documentId"] == 123
    assert isinstance(payload["documentId"], int)
    assert isinstance(payload["contextId"], str)
