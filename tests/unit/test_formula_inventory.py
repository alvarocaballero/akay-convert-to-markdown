"""Supplemental review inventory: real Core items and pinned model-free reconstruction."""

import json

import pytest
from docling_core.types.doc import (
    BoundingBox, ContentLayer, DocItemLabel, DoclingDocument, ProvenanceItem,
)

from akay_convert_to_markdown.contracts.artifacts import parse_review
from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts
from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts
from akay_convert_to_markdown.errors.exceptions import InvalidMessageError
from tests.unit.test_document_artifacts import extracted, request
from tests.unit.test_reviewed_content import original_review, rebuild_request


def provenance():
    return ProvenanceItem(page_no=3, charspan=(0, 5), bbox=BoundingBox(l=0, t=0, r=50, b=10))


@pytest.mark.parametrize("enrichment", [False, True])
@pytest.mark.parametrize("decoded,raw,expected_text,expected_latex", [
    (r"\frac{a}{b}", "a over b", "a over b", r"\frac{a}{b}"),
    ("", "x plus unreadable", "x plus unreadable", None),
    ("   ", "raw formula", "raw formula", None),
    ("x^2", None, "x^2", "x^2"),
    ("", None, "", None),
])
async def test_formula_values_follow_items_not_enrichment_flag(tmp_path, enrichment, decoded, raw,
                                                              expected_text, expected_latex):
    doc = DoclingDocument(name="formula")
    doc.add_text(label=DocItemLabel.TEXT, text="Body")
    item = doc.add_formula(text=decoded, orig=raw, prov=provenance())
    job = request()
    job = job.model_copy(update={"document_options": job.document_options.model_copy(
        update={"formula_enrichment": enrichment})})
    before = doc.export_to_dict()
    result = await export_document_artifacts(extracted(doc), job, tmp_path / "out")
    formula, = result.review.formulas
    assert formula.text == expected_text and formula.latex == expected_latex
    assert formula.docling_item_ref == item.self_ref and formula.page_number == 3
    assert formula.section_id is None and result.review.summary.formula_count == 1
    assert doc.export_to_dict() == before
    wire = (tmp_path / "out/document.artifacts/review.json").read_bytes()
    assert parse_review(wire) == result.review
    assert json.loads(wire)["formulas"][0]["latex"] == expected_latex
    if decoded.startswith("\\frac"):
        assert b"\\\\frac" in wire  # JSON escapes, not removed/doubled in the expression.


@pytest.mark.parametrize("sections", [False, True])
async def test_repeated_occurrences_sections_and_retry_identity(tmp_path, sections):
    doc = DoclingDocument(name="repeated")
    formulas = [doc.add_formula(text="x^2")]
    doc.add_heading("Repeated", level=1)
    formulas.append(doc.add_formula(text="x^2"))
    doc.add_heading("Nested", level=2)
    group = doc.add_inline_group()
    formulas.append(doc.add_formula(text="x^2", parent=group))
    doc.add_heading("Repeated", level=1)
    formulas.append(doc.add_formula(text="x^2"))
    furniture = doc.add_heading("Not a section", level=1)
    furniture.content_layer = ContentLayer.FURNITURE
    formula = doc.add_formula(text="footer")
    formula.content_layer = ContentLayer.FURNITURE
    formulas.append(formula)
    first = await export_document_artifacts(extracted(doc), request(sections=sections), tmp_path / "first")
    again = await export_document_artifacts(extracted(doc), request(sections=sections), tmp_path / "again")
    inventory = first.review.formulas
    assert first == again and first.review.summary.formula_count == 5
    assert [f.docling_item_ref for f in inventory] == [f.self_ref for f in formulas]
    assert len({f.id for f in inventory}) == 5
    expected = [None, *[s.id for s in first.review.sections], None] if sections else [None] * 5
    assert [f.section_id for f in inventory] == expected
    reloaded = DoclingDocument.model_validate(first.docling_json)
    assert [reloaded.texts[int(f.docling_item_ref.rsplit("/", 1)[1])].text for f in inventory] == ["x^2"] * 4 + ["footer"]


async def test_no_formulas_and_legacy_reviews_default_to_empty(tmp_path):
    doc = DoclingDocument(name="plain")
    doc.add_text(label=DocItemLabel.TEXT, text="An equation mentioned in prose is not a formula item.")
    doc.add_code(text=r"equation = '\\frac{a}{b}'")
    result = await export_document_artifacts(extracted(doc), request(), tmp_path / "out")
    wire = result.review.model_dump(mode="json", by_alias=True)
    assert wire["formulas"] == [] and wire["summary"]["formulaCount"] == 0
    assert "equation =" in result.markdown
    assert "codeBlocks" not in wire and "codeBlockCount" not in wire["summary"]
    del wire["formulas"], wire["summary"]["formulaCount"]
    legacy = parse_review(json.dumps(wire))
    assert legacy.formulas == [] and legacy.summary.formula_count == 0
    assert legacy == result.review


def formula_review():
    data = original_review()
    data["formulas"] = [{"id": "formula-001", "doclingItemRef": "#/texts/99", "sectionId": None,
                         "text": "old source", "latex": "old", "pageNumber": 3}]
    data["summary"]["formulaCount"] = 1
    return data


@pytest.mark.parametrize("change", ["count", "count_type", "duplicate", "foreign_section", "rebuild_page", "media"])
def test_formula_contract_invariants(change):
    data = formula_review()
    if change == "count":
        data["summary"]["formulaCount"] = 0
    elif change == "count_type":
        data["summary"]["formulaCount"] = "1"
    elif change == "duplicate":
        data["formulas"] *= 2
        data["summary"]["formulaCount"] = 2
    elif change == "foreign_section":
        data["formulas"][0]["sectionId"] = "00000000-0000-0000-0000-000000000001"
    elif change == "rebuild_page":
        data.update(extractionReviewBlobName="shared/extracted.artifacts/review.json", confidence={})
        data["processing"]["operation"] = "rebuildFromMarkdown"
        data["summary"]["pageCount"] = None
    else:
        data.update(contentType="audio", images=[], confidence={})
        data["summary"].update(pageCount=None, imageCount=0)
    with pytest.raises(InvalidMessageError):
        parse_review(json.dumps(data))


async def test_real_markdown_parser_recomputes_inventory_without_guessing_math(tmp_path):
    original = json.dumps(formula_review())
    for i, expression in enumerate([r"$$\frac{edited}{b}$$", r"$$added^2$$", "Deleted equation."]):
        draft = "# Edited\n\n" + expression + "\n\n```python\nx = 1\n```\n"
        result = await rebuild_document_artifacts(draft, original, rebuild_request(), tmp_path / str(i))
        doc = DoclingDocument.model_validate(result.docling_json)
        # Docling 2.141.0's Marko/GFM backend retains dollar expressions as text,
        # not FormulaItems. Do not copy stale inventory or infer from prose/code.
        assert not any(item.label == DocItemLabel.FORMULA for item in doc.texts)
        assert result.review.formulas == [] and result.review.summary.formula_count == 0
        assert expression in result.markdown and "x = 1" in result.markdown
        assert all(not item.prov for item in doc.texts)


async def test_rebuild_collects_only_current_backend_formula_items(tmp_path, monkeypatch):
    from docling.backend.md_backend import MarkdownDocumentBackend

    doc = DoclingDocument(name="backend-result")
    doc.add_title("Edited")
    doc.add_formula(text=r"\frac{edited}{b}", prov=provenance())
    doc.add_formula(text="added^2", prov=provenance())
    non_body = doc.add_formula(text="note^2", prov=provenance())
    non_body.content_layer = ContentLayer.NOTES
    # Controlled backend-result seam, not a claim that the pinned Markdown
    # grammar recognizes math. Exercise real reconstruction/export/validation.
    monkeypatch.setattr(MarkdownDocumentBackend, "convert", lambda self: doc.model_copy(deep=True))
    job = rebuild_request()
    draft = "# Edited\n\nCurrent content.\n"
    original = json.dumps(formula_review())
    first = await rebuild_document_artifacts(draft, original, job, tmp_path / "first")
    again = await rebuild_document_artifacts(draft, original, job, tmp_path / "again")
    assert first == again
    assert [f.latex for f in first.review.formulas] == [r"\frac{edited}{b}", "added^2", "note^2"]
    assert first.review.summary.formula_count == 3
    assert all(f.page_number is None for f in first.review.formulas)
    assert [f.section_id for f in first.review.formulas] == [first.review.sections[0].id] * 2 + [None]
    assert all(not item.prov for item in DoclingDocument.model_validate(first.docling_json).texts)
    assert "#/texts/99" not in {f.docling_item_ref for f in first.review.formulas}
    assert parse_review((tmp_path / "first/extracted.artifacts/review.json").read_bytes()) == first.review


@pytest.mark.parametrize("extension", ["mp3", "mp4"])
async def test_media_never_infers_formulas_from_transcript(tmp_path, extension):
    from akay_convert_to_markdown.processing.media_artifacts import export_media_artifacts
    from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
    from tests.unit.test_media_artifacts import job

    result = FastTranscriptionService._parse({"phrases": [{"text": r"Equation $$\frac{a}{b}$$ equals one."}]})
    bundle = await export_media_artifacts(result, job(extension), tmp_path / "out", api_version="2025-10-15")
    wire = json.loads((tmp_path / "out/lesson.artifacts/review.json").read_bytes())
    assert bundle.review.formulas == [] and wire["formulas"] == []
    assert wire["summary"]["formulaCount"] == 0
    assert r"\frac{a}{b}" in bundle.transcript.segments[0].text
