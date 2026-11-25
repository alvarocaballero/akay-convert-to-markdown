"""N4: real Core serialization/reload, principal sections and local review packages."""

import asyncio
import importlib
import json
import threading
from types import SimpleNamespace
from urllib.parse import unquote
from uuid import UUID

import pytest
from PIL import Image
from docling.datamodel.base_models import ConfidenceReport, ConversionStatus, PageConfidenceScores
from docling_core.types.doc import (
    BoundingBox, ContentLayer, DocItemLabel, DoclingDocument, DocumentOrigin,
    ImageRef, ProvenanceItem, RichTableCell, Size, TableCell, TableData,
)

from akay_convert_to_markdown.contracts.artifacts import parse_review
from akay_convert_to_markdown.contracts.requests import parse_request
from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter, ExtractedDocument
from akay_convert_to_markdown.errors.exceptions import DocumentConversionError


@pytest.fixture
def exporter():
    return importlib.import_module("akay_convert_to_markdown.conversion.document_artifacts")


def request(*, sections=True, content_key="topic-content:501", destination="topics/25/document.md"):
    return parse_request(json.dumps({"schemaVersion": 1, "requestId": "b1ad362f-0911-4773-8651-1508d94ca001",
                                     "contentKey": content_key, "source": {"type": "blob", "blobName": "inputs/source.pdf"},
                                     "destinationBlobName": destination, "contentType": "document", "callback": "fixture",
                                     "documentOptions": {"extractSections": sections}}),
                         worker="document", callbacks={"fixture"})


def extracted(doc, confidence=None):
    return ExtractedDocument(SimpleNamespace(document=doc, confidence=confidence or ConfidenceReport(),
                                             status=ConversionStatus.SUCCESS, errors=[]))


def structure():
    doc = DoclingDocument(name="fixture")
    doc.add_text(label=DocItemLabel.TEXT, text="Preamble remains general.")
    title = doc.add_title("Manual")
    first = doc.add_heading("Repeated", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text="First section body.")
    child = doc.add_heading("Nested", level=3)
    doc.add_text(label=DocItemLabel.TEXT, text="Nested section body.")
    second = doc.add_heading("Repeated", level=1)
    doc.add_text(label=DocItemLabel.TEXT, text="Second section body.")
    doc.add_text(label=DocItemLabel.PAGE_HEADER, text="Page header")
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="Page footer")
    furniture_heading = doc.add_heading("Furniture heading", level=1)
    furniture_heading.content_layer = ContentLayer.FURNITURE
    return doc, [title, first, child, second]


@pytest.mark.parametrize("key,ref,expected", [
    ("topic-content:501", "#/texts/0", "c1a3cc1f-4beb-5058-ba1e-51af764fccd7"),
    ("topic-content:501", "#/texts/1", "7172ce0f-1a0b-5376-a8ed-871bbb1227fc"),
    ("manual:á", "#/texts/0", "59db2df5-39db-5dad-abdf-677402b8512d"),
])
def test_frozen_section_vectors(exporter, key, ref, expected):
    assert str(exporter.section_id(key, ref)) == expected


async def test_nested_repeated_headings_match_markers_and_reload(exporter, tmp_path):
    doc, headings = structure()
    result = await exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    sections = result.review.sections
    assert [s.docling_item_ref for s in sections] == [h.self_ref for h in headings]
    assert [s.level for s in sections] == [1, 2, 4, 2]
    assert [s.order for s in sections] == [0, 1, 2, 3]
    assert [s.parent_id for s in sections] == [None, sections[0].id, sections[1].id, sections[0].id]
    assert len({s.id for s in sections}) == 4
    assert result.markdown.startswith("Preamble remains general.")
    assert result.markdown.index("Preamble remains general.") < result.markdown.index("akay-section:start")
    assert result.markdown.count("akay-section:start") == 4 and "akay-section:end" not in result.markdown
    for section in sections:
        assert f'<!-- akay-section:start id="{section.id}" -->\n' + "#" * section.level + " " in result.markdown
    assert "Page header" not in result.markdown and "Furniture heading" not in result.markdown
    assert all(s.page_number is None for s in sections)
    reloaded = DoclingDocument.model_validate(result.docling_json)
    for section in sections:
        assert reloaded.texts[int(section.docling_item_ref.rsplit("/", 1)[1])].text == section.title
    assert "akay-section" not in reloaded.export_to_markdown()
    assert (tmp_path / "out/document.md").read_text(encoding="utf-8") == result.markdown
    review = parse_review((tmp_path / "out/document.artifacts/review.json").read_bytes())
    assert review == result.review and review.summary.section_count == 4
    assert review.summary.page_count is None and review.confidence.pages == []
    assert review.processing.engine == "docling" and review.processing.engine_version == "2.141.0"


async def test_retries_and_request_ids_do_not_change_sections(exporter, tmp_path):
    doc, _ = structure()
    source = extracted(doc)
    before = doc.export_to_dict()
    req = request()
    retry = req.model_copy(update={"request_id": UUID("b1ad362f-0911-4773-8651-1508d94ca099")})
    first = await exporter.export_document_artifacts(source, req, tmp_path / "first")
    second = await exporter.export_document_artifacts(source, retry, tmp_path / "second")
    assert first == second
    assert source.document.export_to_dict() == before
    other = await exporter.export_document_artifacts(source, request(content_key="other"), tmp_path / "other")
    assert {s.id for s in first.review.sections}.isdisjoint(s.id for s in other.review.sections)


@pytest.mark.parametrize("with_headings", [False, True])
async def test_additional_documents_and_headingless_principals(exporter, tmp_path, with_headings):
    doc, _ = structure() if with_headings else (DoclingDocument(name="plain"), [])
    if not with_headings:
        doc.add_text(label=DocItemLabel.TEXT, text="General content only.")
    result = await exporter.export_document_artifacts(extracted(doc), request(sections=not with_headings), tmp_path / "out")
    assert result.review.sections == [] and result.review.summary.section_count == 0
    assert "akay-section" not in result.markdown
    if with_headings:
        assert "# Manual" in result.markdown and "## Repeated" in result.markdown and "#### Nested" in result.markdown


async def test_confidence_preserves_upstream_grades_and_nulls(exporter, tmp_path):
    doc, headings = structure()
    doc.add_page(page_no=1, size=Size(width=100, height=100))
    headings[0].prov = [ProvenanceItem(page_no=1, charspan=(0, 6), bbox=BoundingBox(l=0, t=0, r=80, b=10))]
    confidence = ConfidenceReport(pages={2: PageConfidenceScores(),
                                         1: PageConfidenceScores(layout_score=0.95, ocr_score=0.0, parse_score=0.85)})
    result = await exporter.export_document_artifacts(extracted(doc, confidence), request(), tmp_path / "out")
    review = result.review
    assert review.summary.page_count == 1 and review.sections[0].page_number == 1
    assert review.confidence.mean_grade == confidence.pages[1].mean_grade.value
    assert review.confidence.low_grade == confidence.pages[1].low_grade.value
    page, missing = review.confidence.pages
    assert [page.page_number, missing.page_number] == [1, 2]
    assert (page.layout_score, page.layout_grade, page.ocr_score, page.ocr_grade) == (0.95, "excellent", 0.0, "poor")
    assert (page.parse_score, page.parse_grade, page.table_score, page.table_grade) == (0.85, "good", None, None)
    assert page.mean_score == confidence.pages[1].mean_score
    assert missing.mean_score is None and missing.mean_grade is None and missing.low_grade is None
    json.dumps(review.model_dump(mode="json", by_alias=True), allow_nan=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
async def test_nonfinite_confidence_never_fabricates_a_grade(exporter, tmp_path, value):
    doc, _ = structure()
    report = ConfidenceReport(layout_score=value, pages={1: PageConfidenceScores(layout_score=value)})
    result = await exporter.export_document_artifacts(extracted(doc, report), request(), tmp_path / "out")
    data = result.review.model_dump(mode="json", by_alias=True)["confidence"]
    assert data["meanGrade"] is None and data["lowGrade"] is None
    assert all(v is None for k, v in data["pages"][0].items() if k != "pageNumber")
    json.dumps(result.model_dump(mode="json", by_alias=True), allow_nan=False)


async def test_flat_upstream_aggregate_confidence_is_retained(exporter, tmp_path):
    doc, _ = structure()
    confidence = ConfidenceReport(mean_score=0.92, low_score=0.72)
    result = await exporter.export_document_artifacts(extracted(doc, confidence), request(), tmp_path / "out")
    assert result.review.confidence.mean_grade == "excellent"
    assert result.review.confidence.low_grade == "fair" and result.review.confidence.pages == []


async def test_figures_tables_and_private_references_are_portable(exporter, tmp_path, monkeypatch):
    doc, _ = structure()
    doc.origin = DocumentOrigin(mimetype="application/pdf", binary_hash=0, filename=str(tmp_path / "private.pdf"),
                                uri=(tmp_path / "private.pdf").as_uri())
    doc.add_page(page_no=1, size=Size(width=100, height=100), image=ImageRef.from_pil(Image.new("RGB", (100, 100)), dpi=72))
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Figure caption")
    pic = doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (20, 20), "red"), dpi=72), caption=caption)
    table = doc.add_table(data=TableData(num_rows=1, num_cols=1,
                                        table_cells=[TableCell(text="Cell <unsafe>", start_row_offset_idx=0,
                                                              end_row_offset_idx=1, start_col_offset_idx=0, end_col_offset_idx=1)]))
    table.image = ImageRef.from_pil(Image.new("RGB", (20, 10), "blue"), dpi=72)
    table_caption = doc.add_text(label=DocItemLabel.CAPTION, text="Table caption")
    table.captions.append(table_caption.get_ref())
    doc.add_text(label=DocItemLabel.TEXT, text="Private link", hyperlink=tmp_path / "secret.txt")
    doc.add_text(label=DocItemLabel.TEXT, text="Web link", hyperlink="https://example.org/manual")
    before = doc.export_to_dict()
    result = await exporter.export_document_artifacts(extracted(doc), request(destination="same parent/manual.v2 (final).md"),
                                                       tmp_path / "out")
    assert doc.export_to_dict() == before and pic.image is not None
    assert result.review.summary.image_count == 2 and result.review.summary.table_count == 1
    assert result.review.images[0].caption == "Figure caption"
    assert result.review.tables[0].caption == "Table caption"
    assert result.review.tables[0].docling_item_ref == table.self_ref
    assert result.review.tables[0].cells[0]["text"] == "Cell <unsafe>"
    assert result.review.tables[0].blob_name in {image.blob_name for image in result.review.images}
    for image in result.review.images:
        local = tmp_path / "out" / image.blob_name.removeprefix("same parent/")
        assert local.is_file() and Image.open(local).format == "PNG"
    assert "manual.v2%20%28final%29.artifacts/images/figure-001.png" in result.markdown
    wire = json.dumps(result.model_dump(mode="json", by_alias=True))
    assert "https://example.org/manual" in result.markdown and str(tmp_path).replace("\\", "\\\\") not in wire
    assert "file:" not in wire and "data:image" not in wire
    data = json.loads((tmp_path / "out/manual.v2 (final).artifacts/document.docling.json").read_text(encoding="utf-8"))
    assert data == result.docling_json and not data["pages"]["1"].get("image")
    assert data["pictures"][0]["image"]["uri"] == "images/figure-001.png"

    def no_open(*args, **kwargs):
        pytest.fail("Reload must not open any local image reference")

    with monkeypatch.context() as blocked:
        blocked.setattr(Image, "open", no_open)
        reloaded = DoclingDocument.model_validate(data)
        assert reloaded.export_to_markdown() and reloaded.pictures[0].image.uri
    assert len(list((tmp_path / "out").rglob("*.png"))) == 2


@pytest.mark.parametrize("uri", ["../../secret.png", "/private/secret.png", "C:/private/secret.png",
                                 "file:///private/secret.png", "https://127.0.0.1/secret.png"])
async def test_unmaterialized_images_are_not_read_or_leaked(exporter, tmp_path, monkeypatch, uri):
    doc, _ = structure()
    pic = doc.add_picture(image=ImageRef(mimetype="image/png", dpi=72, size=Size(width=10, height=10), uri=uri))

    def no_open(*args, **kwargs):
        pytest.fail("Source image reference was dereferenced")

    with monkeypatch.context() as blocked:
        blocked.setattr(Image, "open", no_open)
        result = await exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    assert pic.image is not None and result.review.images == []
    assert not result.docling_json["pictures"][0].get("image")
    assert any(w.code == "IMAGE_NOT_MATERIALIZED" for w in result.review.warnings)
    assert "secret.png" not in json.dumps(result.model_dump(mode="json", by_alias=True))
    assert not list((tmp_path / "out").rglob("*.png"))


async def test_real_html_extraction_exports_sections_and_retains_warnings(exporter, tmp_path):
    source = tmp_path / "source.html"
    source.write_text("<html><body><p>General</p><h1>Title</h1><h2>Repeated</h2><p>Body</p>"
                      "<h2>Repeated</h2><img src='https://example.invalid/no-fetch.png'></body></html>", encoding="utf-8")
    req = request()
    req = req.model_copy(update={"document_options": req.document_options.model_copy(update={"code_enrichment": True})})
    extraction = await DoclingDocumentConverter().extract(source, req.document_options)
    result = await exporter.export_document_artifacts(extraction, req, tmp_path / "out")
    assert len(result.review.sections) == 3 and result.markdown.count("akay-section:start") == 3
    assert set(extraction.warnings).issubset(result.review.warnings)
    assert any(w.code == "ENRICHMENT_NOT_APPLICABLE" for w in result.review.warnings)


@pytest.mark.parametrize("destination", ["notes%20literal.md", "notes (final).md", "notes_á.md"])
async def test_markdown_image_links_resolve_literal_destination_names(exporter, tmp_path, destination):
    import re

    doc, _ = structure()
    doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (10, 10), "red"), dpi=72))
    result = await exporter.export_document_artifacts(extracted(doc), request(destination=destination), tmp_path / "out")
    link = re.search(r"!\[Image\]\(([^)]+)\)", result.markdown).group(1)
    local = tmp_path / "out" / unquote(link)
    assert local.is_file()
    assert unquote(link) == destination[:-3] + ".artifacts/images/figure-001.png"


async def test_body_content_cannot_spoof_structural_markers(exporter, tmp_path):
    doc, _ = structure()
    spoof = '<!-- akay-section:start id="00000000-0000-0000-0000-000000000000" -->'
    doc.add_text(label=DocItemLabel.TEXT, text=spoof + "\n# Not a structural heading")
    result = await exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    assert len(result.review.sections) == 4
    assert result.markdown.count("<!-- akay-section:start") == 4
    assert "&lt;!-- akay-section:start" in result.markdown


async def test_inline_heading_text_and_table_cell_headings(exporter, tmp_path):
    doc = DoclingDocument(name="rich")
    heading = doc.add_heading("", level=1)
    inline = doc.add_inline_group(parent=heading)
    doc.add_text(label=DocItemLabel.TEXT, text="Rich heading", parent=inline)
    table = doc.add_table(data=TableData(num_rows=1, num_cols=1))
    cell_heading = doc.add_heading("Cell heading is not a section", parent=table)
    table.data.table_cells.append(RichTableCell(text="", ref=cell_heading.get_ref(),
                                                start_row_offset_idx=0, end_row_offset_idx=1,
                                                start_col_offset_idx=0, end_col_offset_idx=1))
    result = await exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    assert len(result.review.sections) == 1
    assert result.review.sections[0].docling_item_ref == heading.self_ref
    assert result.review.sections[0].title == "Rich heading"
    assert result.markdown.count("akay-section:start") == 1 and "Cell heading is not a section" in result.markdown


async def test_windows_drive_url_is_not_a_public_hyperlink(exporter, tmp_path):
    doc, _ = structure()
    doc.add_text(label=DocItemLabel.TEXT, text="Local link", hyperlink="C:/private/secret.txt")
    result = await exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    assert "secret.txt" not in json.dumps(result.model_dump(mode="json", by_alias=True))
    assert "Local link" in result.markdown


@pytest.mark.parametrize("status,errors", [(ConversionStatus.PARTIAL_SUCCESS, []),
                                          (ConversionStatus.FAILURE, []),
                                          (ConversionStatus.SUCCESS, ["private parser error"])])
async def test_incomplete_result_cannot_be_exported_as_a_review(exporter, tmp_path, status, errors):
    doc, _ = structure()
    extraction = extracted(doc)
    extraction.conversion_result.status = status
    extraction.conversion_result.errors = errors
    with pytest.raises(DocumentConversionError):
        await exporter.export_document_artifacts(extraction, request(), tmp_path / "out")
    assert not list((tmp_path / "out").rglob("review.json"))


async def test_export_uses_safe_errors_and_refuses_existing_output(exporter, tmp_path, monkeypatch):
    doc, _ = structure()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    sentinel = occupied / "document.md"
    sentinel.write_text("Existing user work", encoding="utf-8")
    with pytest.raises(FileExistsError):
        await exporter.export_document_artifacts(extracted(doc), request(), occupied)
    assert sentinel.read_text(encoding="utf-8") == "Existing user work"

    def fail(*args, **kwargs):
        raise RuntimeError(f"secret {tmp_path}")

    monkeypatch.setattr(DoclingDocument, "export_to_dict", fail)
    with pytest.raises(DocumentConversionError) as error:
        await exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    assert str(tmp_path) not in error.value.message and "secret" not in error.value.message


async def test_export_cancellation_drains_the_local_writer(exporter, tmp_path, monkeypatch):
    doc, _ = structure()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = DoclingDocument.export_to_dict

    def delayed(self, *args, **kwargs):
        started.set()
        assert release.wait(5)
        try:
            return original(self, *args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(DoclingDocument, "export_to_dict", delayed)
    task = asyncio.create_task(exporter.export_document_artifacts(extracted(doc), request(), tmp_path / "out"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0.03)
        assert not task.done() and not finished.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
