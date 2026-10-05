"""Idempotency tests: reprocessing the same request is deterministic."""

from __future__ import annotations

from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from tests.helpers import make_request, make_logger


async def test_processing_twice_is_deterministic(settings, fake_storage, fake_converter, fake_webhook):
    processor = DocumentProcessor(settings, fake_storage, fake_converter, fake_webhook, make_logger())
    request = make_request()

    first = await processor.process(request)
    second = await processor.process(request)

    assert first is ProcessingResult.COMPLETED
    assert second is ProcessingResult.COMPLETED

    blob_names = [upload[1] for upload in fake_storage.uploads]
    assert blob_names == [f"{request.context_id}/{request.document_id}/document.md"] * 2

    callbacks = [call[0] for call in fake_webhook.calls]
    idempotency_keys = [call[2] for call in fake_webhook.calls]
    assert callbacks == [request.callback] * 2
    assert idempotency_keys == [f"convert-to-markdown:{request.document_id}:completed"] * 2


async def test_numeric_ids_keep_deterministic_paths_and_keys(settings, fake_storage, fake_converter, fake_webhook):
    processor = DocumentProcessor(settings, fake_storage, fake_converter, fake_webhook, make_logger())
    request = make_request(document_id=987, context_id=654)

    await processor.process(request)

    _, blob_name, _ = fake_storage.uploads[0]
    assert blob_name == "654/987/document.md"
    assert fake_webhook.calls[0][2] == "convert-to-markdown:987:completed"
