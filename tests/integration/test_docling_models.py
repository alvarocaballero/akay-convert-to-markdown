"""Opt-in actual local PDF/OCR inference, with downloads/network blocked."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import socket

import pytest

from akay_convert_to_markdown.contracts.requests import DocumentOptions
from tests.docling_fixtures import SPANISH_SCAN_LINES, write_spanish_scan_pdf, write_structured_pdf


@pytest.fixture
def model_assets():
    if os.environ.get("RUN_DOCLING_MODEL_TESTS") != "true":
        pytest.skip("Set RUN_DOCLING_MODEL_TESTS=true with explicit local model assets.")
    assets = os.environ.get("DOCLING_TEST_ARTIFACTS_PATH")
    assert assets and Path(assets).is_dir(), "Explicit local test assets are required."
    return Path(assets)


@contextmanager
def offline(monkeypatch):
    import requests

    def forbidden(*args, **kwargs):
        pytest.fail("Local model verification attempted network access")

    # Restore sockets before pytest creates/tears down the Windows event loop.
    with monkeypatch.context() as blocked:
        blocked.setenv("HF_HUB_OFFLINE", "1")
        blocked.setenv("TRANSFORMERS_OFFLINE", "1")
        blocked.setattr(socket.socket, "connect", forbidden)
        blocked.setattr(socket.socket, "connect_ex", forbidden)
        blocked.setattr(requests.sessions.Session, "request", forbidden)
        yield


@pytest.mark.parametrize("language", ["es", "eu", "gl", "ca", "fr", "en", "de"])
def test_local_ocr_resources_initialize_for_selected_language(model_assets, monkeypatch, language):
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
    from akay_convert_to_markdown.conversion.docling_converter import build_docling_converter
    from docling.datamodel.base_models import InputFormat

    options = build_docling_converter(DocumentOptions(ocr_language=language), artifacts_path=model_assets,
                                      input_format=InputFormat.PDF).format_to_options[InputFormat.PDF].pipeline_options
    with offline(monkeypatch):
        model = RapidOcrModel(enabled=True, artifacts_path=model_assets, options=options.ocr_options,
                              accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU))
    assert model._native_codes == [language]
    # Initialization is real; this does NOT measure language-specific OCR quality.


@pytest.mark.parametrize("broken_text_layer", [False, True])
async def test_local_spanish_scan_integration(model_assets, tmp_path, monkeypatch, broken_text_layer):
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
    from docling_core.types.doc import DoclingDocument

    source = tmp_path / "spanish-scan.pdf"
    write_spanish_scan_pdf(source, broken_text_layer=broken_text_layer)
    with offline(monkeypatch):
        extraction = await DoclingDocumentConverter(artifacts_path=model_assets).extract(source, DocumentOptions())
        await extraction.export_referenced(tmp_path / "export")
        loaded = DoclingDocument.load_from_json(tmp_path / "export/document.docling.json")
    markdown = " ".join(extraction.document.export_to_markdown().split())
    assert "plantas" in markdown.casefold()  # Raster content reached OCR, not just the corrupt overlay.
    assert [item.text for item in loaded.texts] == [item.text for item in extraction.document.texts]
    assert all(page.image is None for page in loaded.pages.values())
    assert (tmp_path / "export/document.md").read_text(encoding="utf-8").strip()
    assert extraction.confidence.pages
    assert "akay-section" not in markdown


@pytest.mark.parametrize("code,formula", [(False, False), (True, False), (False, True), (True, True)])
async def test_local_pdf_inference(model_assets, tmp_path, monkeypatch, code, formula):
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
    from docling_core.types.doc import DoclingDocument

    source = tmp_path / "structured-spanish.pdf"
    write_structured_pdf(source)
    with offline(monkeypatch):
        extraction = await DoclingDocumentConverter(artifacts_path=model_assets).extract(
            source, DocumentOptions(code_enrichment=code, formula_enrichment=formula))
        await extraction.export_referenced(tmp_path / "export")
        loaded = DoclingDocument.load_from_json(tmp_path / "export/document.docling.json")
    markdown = extraction.document.export_to_markdown()
    assert "Fotosíntesis" in markdown and "energía luminosa" in markdown
    assert "Agua" in markdown and "Plantas" in markdown
    assert "energia" in markdown
    assert loaded.tables and loaded.pictures
    assert any(item.label == "code" for item in loaded.texts)
    assert any(item.label == "formula" for item in loaded.texts)
    if code:
        assert any(item.label == "code" and "\n" in item.text for item in loaded.texts)
    if formula:
        # Formula recognition is optional; native extraction alone exports a placeholder.
        assert any(item.label == "formula" and "E=mc^2" in re.sub(r"[\s{}]", "", item.text)
                   for item in loaded.texts)
    else:
        assert "<!-- formula-not-decoded -->" in markdown
    assert all(page.image is None for page in loaded.pages.values())
    saved = json.loads((tmp_path / "export/document.docling.json").read_text(encoding="utf-8"))
    for item in saved["pictures"]:
        assert item["image"] is not None
        uri = item["image"]["uri"]
        assert uri.startswith("images/") and "\\" not in uri
        assert (tmp_path / "export" / uri).is_file()
        assert uri in (tmp_path / "export/document.md").read_text(encoding="utf-8")


@pytest.mark.skipif(os.environ.get("RUN_DOCLING_QUALITY_DIAGNOSTICS") != "true",
                    reason="Optical-quality diagnostic, outside N3 integration acceptance.")
@pytest.mark.parametrize("broken_text_layer", [False, True])
async def test_local_spanish_ocr_quality_diagnostic(model_assets, tmp_path, monkeypatch, broken_text_layer):
    from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter

    source = tmp_path / "broken-layer.pdf"
    write_spanish_scan_pdf(source, broken_text_layer=broken_text_layer)
    with offline(monkeypatch):
        extraction = await DoclingDocumentConverter(artifacts_path=model_assets).extract(source, DocumentOptions())
    markdown = " ".join(extraction.document.export_to_markdown().split())
    for line in SPANISH_SCAN_LINES:
        assert line in markdown
    if broken_text_layer:
        assert "ZZZZ WRONG TEXT LAYER" not in markdown
