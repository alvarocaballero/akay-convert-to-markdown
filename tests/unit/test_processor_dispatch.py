"""DocumentProcessor orchestration and dispatch tests."""

from __future__ import annotations

import asyncio

import pytest

from akay_convert_to_markdown.errors.exceptions import DocumentConversionError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from tests.helpers import FakeStorage, make_logger, make_request, make_settings


class FakeMediaProcessor:
    def __init__(self, result: str = "# Transcripción\n") -> None:
        self.result = result
        self.calls: list = []
        self.error: Exception | None = None

    async def to_markdown(self, request, source_path, temp_dir, log):
        self.calls.append((request, source_path, temp_dir))
        if self.error:
            raise self.error
        return self.result


def _processor(settings, storage, converter, webhook, *, audio=None, video=None):
    return DocumentProcessor(
        settings,
        storage,
        converter,
        webhook,
        make_logger(),
        audio_processor=audio,
        video_processor=video,
    )


async def test_pdf_dispatch_uses_document_converter(settings, fake_storage, fake_converter, fake_webhook):
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook)
    request = make_request(file_name="a.pdf")

    result = await processor.process(request)

    assert result is ProcessingResult.COMPLETED
    assert len(fake_converter.calls) == 1


async def test_mp3_dispatch_uses_audio_processor(settings, fake_storage, fake_converter, fake_webhook):
    audio = FakeMediaProcessor()
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook, audio=audio)
    request = make_request(file_name="a.mp3")

    result = await processor.process(request)

    assert result is ProcessingResult.COMPLETED
    assert len(audio.calls) == 1
    assert len(fake_converter.calls) == 0
    assert len(fake_webhook.calls) == 1


async def test_mp4_dispatch_uses_video_processor(settings, fake_storage, fake_converter, fake_webhook):
    video = FakeMediaProcessor()
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook, video=video)
    request = make_request(file_name="a.mp4")

    result = await processor.process(request)

    assert result is ProcessingResult.COMPLETED
    assert len(video.calls) == 1
    assert video.calls[0][1].suffix == ".mp4"


async def test_unsupported_extension_still_fails_as_document(settings, fake_storage, fake_converter, fake_webhook):
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook)
    result = await processor.process(make_request(file_name="a.xyz"))

    assert result is ProcessingResult.FAILED_PERMANENT
    assert fake_webhook.calls[0][1]["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


async def test_processing_timeout_sends_failed_event(settings, fake_storage, fake_webhook):
    class HangingConverter:
        async def convert(self, source_path):
            await asyncio.sleep(3600)
            return "# md"

    settings.process_timeout_minutes = 0
    processor = _processor(settings, fake_storage, HangingConverter(), fake_webhook)

    result = await processor.process(make_request(file_name="a.pdf"))

    assert result is ProcessingResult.FAILED_PERMANENT
    assert fake_webhook.calls[0][1]["error"]["code"] == "PROCESSING_TIMEOUT"


async def test_existing_output_is_skipped(settings, fake_storage, fake_converter, fake_webhook):
    request = make_request(file_name="a.pdf")
    fake_storage.existing_blobs[f"{request.context_id}/{request.document_id}/document.md"] = True
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook)

    result = await processor.process(request)

    assert result is ProcessingResult.COMPLETED
    assert len(fake_converter.calls) == 0
    assert len(fake_storage.downloads) == 0
    assert len(fake_storage.uploads) == 0
    assert len(fake_webhook.calls) == 1
    assert fake_webhook.calls[0][1]["eventType"] == "document.conversion.completed"


async def test_media_failure_sends_failed_event_with_sanitized_message(
    settings, fake_storage, fake_converter, fake_webhook
):
    audio = FakeMediaProcessor()
    audio.error = DocumentConversionError("generic failure", detail="sensitive ffmpeg stderr")
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook, audio=audio)
    request = make_request(file_name="a.mp3")

    result = await processor.process(request)

    assert result is ProcessingResult.FAILED_PERMANENT
    error = fake_webhook.calls[0][1]["error"]
    assert error["code"] == "DOCUMENT_CONVERSION_FAILED"
    assert "sensitive" not in error["message"]


async def test_media_temp_files_removed(settings, fake_storage, fake_converter, fake_webhook):
    audio = FakeMediaProcessor()
    processor = _processor(settings, fake_storage, fake_converter, fake_webhook, audio=audio)
    request = make_request(file_name="a.mp3")

    await processor.process(request)

    base = settings.temp_directory / str(request.context_id) / str(request.document_id)
    assert not base.exists()
