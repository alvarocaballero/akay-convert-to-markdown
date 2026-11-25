"""N3 extraction contracts, real model-free formats and inference lifecycle."""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
from PIL import Image
from docling.datamodel.base_models import ConfidenceReport, ConversionStatus, InputFormat
from docling_core.types.doc import DoclingDocument, ImageRef, Size

from akay_convert_to_markdown.contracts.requests import DocumentOptions
from akay_convert_to_markdown.errors.exceptions import DocumentConversionError


def test_document_entry_has_replaced_markitdown():
    from akay_convert_to_markdown import document_main

    assert hasattr(document_main, "DoclingDocumentConverter")


@pytest.fixture
def adapter():
    return importlib.import_module("akay_convert_to_markdown.conversion.docling_converter")


def successful_result(text="Fixture body"):
    doc = DoclingDocument(name="fixture")
    doc.add_heading("Repeated", level=1)
    doc.add_heading("Repeated", level=2)
    doc.add_text(label="text", text=text)
    return SimpleNamespace(status=ConversionStatus.SUCCESS, document=doc,
                           confidence=ConfidenceReport(), errors=[])


@pytest.mark.parametrize("code,formula", [(False, False), (True, False), (False, True), (True, True)])
def test_pinned_pdf_configuration_and_independent_flags(adapter, tmp_path, code, formula):
    from docling.datamodel.pipeline_options import OcrMode, TableFormerMode

    converter = adapter.build_docling_converter(DocumentOptions(code_enrichment=code, formula_enrichment=formula),
                                               artifacts_path=tmp_path)
    assert set(converter.allowed_formats) == {InputFormat.PDF, InputFormat.DOCX, InputFormat.PPTX,
                                              InputFormat.HTML, InputFormat.MD}
    pdf = converter.format_to_options[InputFormat.PDF]
    assert pdf.pipeline_cls.__name__ == "StandardPdfPipeline"
    assert pdf.backend.__name__ == "ThreadedDoclingParseDocumentBackend"
    options = pdf.pipeline_options
    assert options.do_code_enrichment is code and options.do_formula_enrichment is formula
    assert options.do_ocr and options.do_table_structure
    assert options.ocr_options.backend == "onnxruntime"
    assert options.ocr_options.lang == ["iso:es-Latn"]
    assert options.ocr_options.mode == OcrMode.PDF_AWARE_LAYOUT_REGIONS
    assert options.table_structure_options.mode == TableFormerMode.ACCURATE
    assert options.heading_hierarchy_options.enabled and options.generate_parsed_pages
    assert options.generate_picture_images and not options.generate_page_images
    assert str(options.accelerator_options.device) in {"cpu", "AcceleratorDevice.CPU"}
    for format_options in converter.format_to_options.values():
        pipeline = format_options.pipeline_options
        assert not pipeline.enable_remote_services and not pipeline.allow_external_plugins
        assert not pipeline.do_picture_classification and not pipeline.do_picture_description
        assert not pipeline.do_chart_extraction
        backend = format_options.backend_options
        assert not backend.enable_remote_fetch and not backend.enable_local_fetch
    assert not converter.format_to_options[InputFormat.HTML].backend_options.fetch_images
    assert not converter.format_to_options[InputFormat.MD].backend_options.fetch_images


@pytest.mark.parametrize("language", ["es", "eu", "gl", "ca", "fr", "en", "de"])
async def test_request_ocr_selection_reaches_the_pinned_engine(adapter, tmp_path, monkeypatch, language):
    from akay_convert_to_markdown.contracts import parse_request
    from docling.models.stages.ocr.rapid_ocr_model import _resolve_rapidocr

    monkeypatch.setenv("DOCLING_OCR_LANGUAGE", "de")  # Retired global setting must not override the request.
    request = parse_request(json.dumps({"schemaVersion": 1,
                                       "requestId": "b1ad362f-0911-4773-8651-1508d94ca001",
                                       "contentKey": "fixture", "source": {"type": "blob", "blobName": "fixture.pdf"},
                                       "destinationBlobName": "fixture.md", "contentType": "document",
                                       "callback": "fixture", "documentOptions": {"ocrLanguage": language}}),
                            worker="document", callbacks={"fixture"})
    build = adapter.build_docling_converter
    captured = []

    def factory(options, **kwargs):
        engine = build(options, **kwargs)
        pdf = engine.format_to_options[InputFormat.PDF].pipeline_options
        assert pdf.ocr_options.lang == [f"iso:{language}-Latn"]
        resolved = _resolve_rapidocr(pdf.ocr_options.lang[0], pdf.ocr_options.backend)
        assert resolved.rapidocr_code == language  # No substituted language or Chinese default.
        captured.append(pdf.ocr_options.lang)
        return SimpleNamespace(initialize_pipeline=lambda *_: None, convert=lambda *_a, **_k: successful_result())

    monkeypatch.setattr(adapter, "build_docling_converter", factory)
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"controlled inference double")
    await adapter.DoclingDocumentConverter(artifacts_path=tmp_path).extract(source, request.document_options)
    assert captured == [[f"iso:{language}-Latn"]]


@pytest.mark.parametrize("status,errors,text", [
    (ConversionStatus.PARTIAL_SUCCESS, [], "Partial text"),
    (ConversionStatus.FAILURE, [], "Some text"),
    (ConversionStatus.SUCCESS, ["parser failure with private source text"], "Some text"),
    (ConversionStatus.SUCCESS, [], "   "),
])
async def test_incomplete_and_empty_results_never_complete(adapter, tmp_path, status, errors, text):
    result = successful_result(text)
    if not text.strip():
        result.document = DoclingDocument(name="empty")
    result.status, result.errors = status, errors
    source = tmp_path / "source.pdf"
    source.write_bytes(b"controlled PDF fixture")
    converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=lambda *_a, **_k: result))
    with pytest.raises(DocumentConversionError) as failure:
        await converter.extract(source, DocumentOptions())
    assert "private" not in failure.value.message and str(tmp_path) not in failure.value.message


async def test_conversion_exception_is_safe(adapter, tmp_path):
    def fail(*args, **kwargs):
        raise RuntimeError("secret-token " + str(tmp_path))

    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=fail))
    with pytest.raises(DocumentConversionError) as failure:
        await converter.convert(source)
    assert failure.value.message == "The document could not be converted."


@pytest.mark.parametrize("suffix", [".md", ".txt", ".html", ".htm", ".docx", ".pptx"])
async def test_real_model_free_formats_preserve_structure_without_fetching(adapter, monkeypatch, tmp_path, suffix):
    # Both remote and local resources are traps; input parsing must never open them.
    import socket
    import requests

    def forbidden(*args, **kwargs):
        pytest.fail("Extraction attempted a network request")

    source = tmp_path / ("fixture" + suffix)
    if suffix in {".md", ".txt"}:
        source.write_text("Preamble text\n\n# Repeated\n\nFixture body\n\n## Repeated\n\n"
                          "| A | B |\n| --- | --- |\n| one | two |\n\n"
                          "![remote](https://metadata.invalid/image.png)\n"
                          "![local](file:///not-allowed/private.png)", encoding="utf-8")
    elif suffix in {".html", ".htm"}:
        source.write_text('<html><body><p>Preamble text</p><h1>Repeated</h1><p>Fixture body</p>'
                          '<h2>Repeated</h2><table><tr><td>one</td><td>two</td></tr></table>'
                          '<img src="https://metadata.invalid/image.png">'
                          '<img src="file:///not-allowed/private.png"></body></html>', encoding="utf-8")
    elif suffix == ".docx":
        from docx import Document
        doc = Document()
        doc.add_paragraph("Preamble text")
        doc.add_heading("Repeated", level=1)
        doc.add_paragraph("Fixture body")
        doc.add_heading("Repeated", level=2)
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text, table.cell(0, 1).text = "one", "two"
        doc.save(source)
    else:
        from pptx import Presentation
        doc = Presentation()
        slide = doc.slides.add_slide(doc.slide_layouts[1])
        slide.shapes.title.text = "Repeated"
        slide.placeholders[1].text = "Fixture body"
        doc.save(source)
    with monkeypatch.context() as blocked:
        blocked.setattr(socket.socket, "connect", forbidden)
        blocked.setattr(requests.sessions.Session, "request", forbidden)
        extraction = await adapter.DoclingDocumentConverter().extract(source, DocumentOptions())
    markdown = extraction.document.export_to_markdown()
    assert "Fixture body" in markdown and "Repeated" in markdown
    assert "akay-section" not in markdown
    if suffix != ".pptx":
        assert "Preamble text" in markdown
        assert extraction.document.tables
        headings = [item for item in extraction.document.texts if item.label in {"title", "section_header"}]
        if suffix == ".docx":
            assert [item.level for item in headings] == [1, 2]
        else:
            # Pinned web backends represent h1 as TITLE and h2 as SECTION_HEADER(1).
            assert [item.label for item in headings] == ["title", "section_header"]
            assert headings[1].level == 1
            assert "# Repeated" in markdown and "## Repeated" in markdown
        assert headings[0].self_ref != headings[1].self_ref
    assert extraction.confidence is not None


async def test_referenced_figures_exclude_page_images_and_reload(adapter, tmp_path):
    result = successful_result()
    image = ImageRef.from_pil(Image.new("RGB", (8, 8), "red"), dpi=72)
    result.document.add_picture(image=image)
    result.document.add_page(page_no=1, size=Size(width=50, height=50), image=image)
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"fixture")
    converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=lambda *_a, **_k: result))
    extraction = await converter.extract(source, DocumentOptions())
    output = tmp_path / "export"
    await extraction.export_referenced(output)
    loaded = DoclingDocument.load_from_json(output / "document.docling.json")
    assert loaded.pages[1].image is None
    assert len(loaded.pictures) == 1
    saved = json.loads((output / "document.docling.json").read_text(encoding="utf-8"))
    uri = saved["pictures"][0]["image"]["uri"]
    assert uri.startswith("images/") and "\\" not in uri
    assert Path(str(loaded.pictures[0].image.uri)).as_posix() == uri
    assert (output / uri).is_file()
    assert uri in (output / "document.md").read_text(encoding="utf-8")
    assert len(list(output.rglob("*.png"))) == 1
    assert result.document.pages[1].image is image  # Export must not mutate extraction state.


@pytest.mark.parametrize("cancel_twice,fail_after_cancel", [(False, False), (True, False), (True, True)])
async def test_cancellation_drains_inference_before_caller_cleanup(adapter, tmp_path, cancel_twice, fail_after_cancel):
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"fixture")

    def infer(*args, **kwargs):
        started.set()
        assert release.wait(timeout=5)
        assert source.is_file()
        finished.set()
        if fail_after_cancel:
            raise RuntimeError("private failure")
        return successful_result()

    converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=infer))
    cleaned = False

    async def run():
        nonlocal cleaned
        try:
            await converter.convert(source)
        finally:
            source.unlink()
            cleaned = True

    task = asyncio.create_task(run())
    try:
        async with asyncio.timeout(3):
            while not started.is_set():
                await asyncio.sleep(0.005)
        task.cancel()
        await asyncio.sleep(0.02)
        if cancel_twice:
            task.cancel()
            await asyncio.sleep(0.02)
        assert not task.done() and not cleaned and not finished.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set() and cleaned


async def test_pdf_without_explicit_local_assets_fails_before_pipeline(adapter, tmp_path, monkeypatch):
    # A PDF must not trigger downloads or reuse an ambient model cache.
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(adapter, "build_docling_converter", lambda *_a, **_k: pytest.fail("Pipeline created"))
    with pytest.raises(adapter.DocumentModelConfigurationError):
        await adapter.DoclingDocumentConverter().convert(source)


async def test_legacy_interface_uses_docling(adapter, tmp_path):
    source = tmp_path / "fixture.md"
    source.write_text("# Heading\n\nFixture body", encoding="utf-8")
    text = await adapter.DoclingDocumentConverter().convert(source)
    assert "Heading" in text and "Fixture body" in text


async def test_processor_timeout_waits_for_inference_before_cleanup_or_notification(adapter, tmp_path, monkeypatch):
    from akay_convert_to_markdown.models.conversion_result import ProcessingResult
    from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
    from tests.helpers import FakeStorage, FakeWebhook, make_logger, make_request, make_settings

    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def infer(source, **kwargs):
        started.set()
        assert release.wait(5)
        assert source.is_file()
        finished.set()
        return successful_result()

    converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=infer))
    settings = make_settings(temp_directory=tmp_path)
    monkeypatch.setattr(type(settings), "process_timeout_seconds", property(lambda _: 0.06))
    storage, webhook = FakeStorage(), FakeWebhook()
    processor = DocumentProcessor(settings, storage, converter, webhook, make_logger())
    task = asyncio.create_task(processor.process(make_request()))
    try:
        async with asyncio.timeout(3):
            while not started.is_set():
                await asyncio.sleep(0.005)
        await asyncio.sleep(0.1)  # The processing timeout has fired, but inference still owns the source.
        assert not task.done() and not webhook.calls and not storage.uploads
        assert storage.downloads[0][2].is_file()
    finally:
        release.set()
    assert await task == ProcessingResult.FAILED_PERMANENT
    assert finished.is_set() and not list(tmp_path.iterdir())
    assert webhook.calls[0][1]["error"]["code"] == "PROCESSING_TIMEOUT"
    assert not storage.uploads


async def test_partial_result_cannot_upload_or_send_completed(adapter, tmp_path):
    from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
    from tests.helpers import FakeStorage, FakeWebhook, make_logger, make_request, make_settings

    result = successful_result()
    result.status = ConversionStatus.PARTIAL_SUCCESS
    converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=lambda *_a, **_k: result))
    storage, webhook = FakeStorage(), FakeWebhook()
    processor = DocumentProcessor(make_settings(temp_directory=tmp_path), storage, converter, webhook, make_logger())
    await processor.process(make_request())
    assert not storage.uploads
    assert webhook.calls[0][1]["eventType"] == "document.conversion.failed"
    assert webhook.calls[0][1]["error"]["code"] == "DOCUMENT_CONVERSION_FAILED"


async def test_export_does_not_resolve_local_or_remote_image_references(adapter, tmp_path, monkeypatch):
    result = successful_result()
    result.document.add_picture(image=ImageRef(mimetype="image/png", dpi=72, size=Size(width=1, height=1),
                                              uri=Path("not-allowed.png")))
    result.document.add_picture(image=ImageRef(mimetype="image/png", dpi=72, size=Size(width=1, height=1),
                                              uri="https://metadata.invalid/private.png"))
    # If export ever tries to dereference either, even a nonexistent path, fail.
    monkeypatch.setattr(Image, "open", lambda *_a, **_k: pytest.fail("Image reference was dereferenced"))
    extraction = adapter.ExtractedDocument(result)
    await extraction.export_referenced(tmp_path / "export")
    saved = json.loads((tmp_path / "export/document.docling.json").read_text(encoding="utf-8"))
    assert all(item.get("image") is None for item in saved["pictures"])


async def test_non_pdf_enrichment_limitation_is_explicit(adapter, tmp_path):
    source = tmp_path / "fixture.md"
    source.write_text("# Heading\n\n```python\nx = 1\n```", encoding="utf-8")
    extraction = await adapter.DoclingDocumentConverter().extract(source, DocumentOptions(code_enrichment=True))
    assert "x = 1" in extraction.document.export_to_markdown()
    assert "ENRICHMENT_NOT_APPLICABLE" in {warning.code for warning in extraction.warnings}


@pytest.mark.parametrize("suffix", [".md", ".txt", ".html", ".docx", ".pptx"])
async def test_real_invalid_or_empty_documents_fail_safely(adapter, tmp_path, suffix):
    source = tmp_path / ("empty" + suffix)
    source.write_bytes(b"<html><body></body></html>" if suffix == ".html" else b"")
    converter = adapter.DoclingDocumentConverter(artifacts_path=tmp_path)
    with pytest.raises(DocumentConversionError):
        await converter.convert(source)


async def test_new_engine_per_request_and_request_options_do_not_leak(adapter, tmp_path):
    instances, captured = [], []

    def factory(options):
        captured.append(options)
        engine = SimpleNamespace(convert=lambda *_a, **_k: successful_result())
        instances.append(engine)
        return engine

    converter = adapter.DoclingDocumentConverter(factory=factory)
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"fixture")
    first, second = DocumentOptions(code_enrichment=True), DocumentOptions(formula_enrichment=True)
    await asyncio.gather(converter.extract(source, first), converter.extract(source, second))
    assert len(instances) == 2 and instances[0] is not instances[1]
    assert set(captured) == {first, second}


async def test_incomplete_local_model_directory_is_retryable_without_downloads(adapter, tmp_path, monkeypatch):
    import socket
    from tests.docling_fixtures import write_text_pdf

    source = tmp_path / "fixture.pdf"
    write_text_pdf(source)

    def no_network(*args, **kwargs):
        pytest.fail("Missing local models caused a download")

    with monkeypatch.context() as blocked:
        blocked.setattr(socket.socket, "connect", no_network)
        with pytest.raises(adapter.DocumentModelConfigurationError):
            await adapter.DoclingDocumentConverter(artifacts_path=tmp_path).convert(source)


async def test_runner_shutdown_does_not_orphan_inference(adapter, tmp_path):
    started, release, finished, cleaned = (threading.Event() for _ in range(4))
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"fixture")

    def infer(*args, **kwargs):
        started.set()
        assert release.wait(5)
        assert source.is_file()
        finished.set()
        return successful_result()

    async def convert():
        try:
            converter = adapter.DoclingDocumentConverter(factory=lambda *_: SimpleNamespace(convert=infer))
            await converter.convert(source)
        finally:
            assert finished.is_set()
            source.unlink()
            cleaned.set()

    async def main():
        asyncio.create_task(convert())
        while not started.is_set():
            await asyncio.sleep(0.005)
        # Return with extraction still running: asyncio.run cancels ALL pending Tasks.

    runner = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(main())))
    try:
        async with asyncio.timeout(3):
            while not started.is_set():
                await asyncio.sleep(0.005)
        await asyncio.sleep(0.05)
        assert not cleaned.is_set() and not runner.done()
    finally:
        release.set()
    await runner
    assert finished.is_set() and cleaned.is_set()


async def test_disguised_pdf_cannot_bypass_local_model_policy(adapter, tmp_path, monkeypatch):
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    from tests.docling_fixtures import write_text_pdf

    source = tmp_path / "disguised.md"
    write_text_pdf(source)
    monkeypatch.setattr(StandardPdfPipeline, "__init__",
                        lambda *_a, **_k: pytest.fail("Disguised PDF reached model initialization"))
    with pytest.raises(DocumentConversionError):
        await adapter.DoclingDocumentConverter().convert(source)


async def test_model_initialization_precedes_native_pdf_open(adapter, tmp_path, monkeypatch):
    def missing_models(*args, **kwargs):
        raise FileNotFoundError("private model path")

    def must_not_parse(*args, **kwargs):
        pytest.fail("Native PDF backend opened before the model configuration was verified")

    engine = SimpleNamespace(initialize_pipeline=missing_models, convert=must_not_parse)
    monkeypatch.setattr(adapter, "build_docling_converter", lambda *_a, **_k: engine)
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"fixture")
    with pytest.raises(adapter.DocumentModelConfigurationError):
        await adapter.DoclingDocumentConverter(artifacts_path=tmp_path).convert(source)


async def test_document_entry_converts_and_delivers_with_real_docling(tmp_path, monkeypatch):
    from akay_convert_to_markdown import document_main
    from akay_convert_to_markdown.models.conversion_result import ProcessingResult
    from tests.helpers import FakeStorage, FakeWebhook, make_logger, make_request, make_settings

    class LocalStorage(FakeStorage):
        markdown = None

        async def download_to_file(self, container, blob_name, destination):
            destination.write_text("# Runtime heading\n\nRuntime body", encoding="utf-8")

        async def upload_file(self, container, blob_name, source, *, overwrite=False):
            self.markdown = source.read_text(encoding="utf-8")
            await super().upload_file(container, blob_name, source, overwrite=overwrite)

    # Never load an ambient model directory/configuration in this local harness.
    monkeypatch.setattr(document_main, "DoclingSettings",
                        lambda: SimpleNamespace(artifacts_path=None))
    storage, webhook = LocalStorage(), FakeWebhook()
    processor, close = document_main.build_processor(make_settings(temp_directory=tmp_path),
                                                     storage, webhook, make_logger())
    request = make_request(file_name="runtime.md", payload={"opaque": [1, "value"]})
    try:
        assert await processor.process(request) == ProcessingResult.COMPLETED
    finally:
        await close()
    assert "Runtime heading" in storage.markdown and "Runtime body" in storage.markdown
    assert len(storage.uploads) == 1 and not list(tmp_path.iterdir())
    payload = webhook.calls[0][1]
    assert payload["eventType"] == "document.conversion.completed"
    assert payload["payload"] == request.payload
    assert "artifacts" not in payload  # Legacy, not an invented version-one publication.
