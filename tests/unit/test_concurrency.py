"""Concurrency tests: independent temporary directories per execution."""

from __future__ import annotations

import asyncio
from pathlib import Path

from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from tests.helpers import FakeStorage, FakeWebhook, make_logger, make_request, make_settings


class RecordingConverter:
    """Records the parent directory of each converted source path."""

    def __init__(self, *, delay: float = 0.0) -> None:
        self.execution_dirs: list[Path] = []
        self.delay = delay

    async def convert(self, source_path) -> str:
        self.execution_dirs.append(source_path.parent)
        if self.delay:
            await asyncio.sleep(self.delay)
        return "# markdown"


def _processor(settings, converter) -> DocumentProcessor:
    return DocumentProcessor(
        settings,
        FakeStorage(),
        converter,
        FakeWebhook(),
        make_logger(),
    )


async def test_same_document_id_concurrent_runs_use_distinct_temp_dirs(tmp_path):
    settings = make_settings(temp_directory=tmp_path / "akay")
    converter = RecordingConverter(delay=0.05)
    processor = _processor(settings, converter)
    request = make_request()

    results = await asyncio.gather(
        processor.process(request),
        processor.process(request),
    )

    assert all(result is ProcessingResult.COMPLETED for result in results)
    assert len(converter.execution_dirs) == 2
    assert converter.execution_dirs[0] != converter.execution_dirs[1]

    base = settings.temp_directory / str(request.request_id)
    assert not base.exists()


async def test_same_document_id_different_context_ids_are_independent(tmp_path):
    settings = make_settings(temp_directory=tmp_path / "akay")
    converter = RecordingConverter(delay=0.05)
    processor = _processor(settings, converter)
    request_a = make_request()
    request_b = make_request(destination_blob_name="other/document.md")

    await asyncio.gather(
        processor.process(request_a),
        processor.process(request_b),
    )

    assert len(converter.execution_dirs) == 2
    assert converter.execution_dirs[0] != converter.execution_dirs[1]
    # Neither context's base directory survives.
    for request in (request_a, request_b):
        base = settings.temp_directory / str(request.request_id)
        assert not base.exists()
