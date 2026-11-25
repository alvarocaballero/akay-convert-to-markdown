"""Check the selected T0 APIs in an isolated environment, without inference."""

from __future__ import annotations

import math
import warnings
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from docling.datamodel.base_models import ConfidenceReport, PageConfidenceScores, QualityGrade
from docling.datamodel.pipeline_options import (
    HeadingHierarchyOptions,
    OcrMode,
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
)
from docling.document_converter import PdfFormatOption
from docling_core.types.doc import DoclingDocument, ImageRef, ImageRefMode


def main() -> None:
    assert version("docling-slim") == "2.141.0"
    assert version("docling-core") == "2.99.0"
    options = PdfPipelineOptions()
    options.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)
    options.generate_parsed_pages = True
    options.ocr_options = RapidOcrOptions(backend="onnxruntime", mode=OcrMode.PDF_AWARE_LAYOUT_REGIONS)
    options.generate_picture_images = True
    options.generate_page_images = False
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    assert options.do_ocr and options.heading_hierarchy_options.enabled
    assert options.ocr_options.mode is not OcrMode.FULL_PAGE
    assert not options.do_code_enrichment and not options.do_formula_enrichment
    assert not options.do_picture_classification and not options.do_picture_description
    assert not options.enable_remote_services and not options.allow_external_plugins
    assert "replace_broken_text_layer" not in PdfPipelineOptions.model_fields
    assert PdfFormatOption.model_fields["pipeline_cls"].default.__name__ == "StandardPdfPipeline"
    assert PdfFormatOption.model_fields["backend"].default.__name__ == "ThreadedDoclingParseDocumentBackend"

    confidence = ConfidenceReport(pages={1: PageConfidenceScores(parse_score=0.95)})
    assert confidence.mean_grade is QualityGrade.EXCELLENT
    # An unmeasured score is NaN, not zero. The upstream aggregate warns about it.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
        assert math.isnan(PageConfidenceScores().mean_score)
        assert PageConfidenceScores().mean_grade is QualityGrade.UNSPECIFIED

    with TemporaryDirectory(prefix="docling-t0-") as directory:
        root = Path(directory)
        document = DoclingDocument(name="t0-synthetic")
        first = document.add_heading("Repeated heading", level=1)
        second = document.add_heading("Repeated heading", level=2)
        document.add_picture(image=ImageRef.from_pil(Image.new("RGB", (8, 8), "red"), dpi=72))
        assert first.self_ref != second.self_ref
        document.save_as_markdown(root / "document.md", artifacts_dir=Path("images"), image_mode=ImageRefMode.REFERENCED)
        document.save_as_json(root / "document.docling.json", artifacts_dir=Path("images"), image_mode=ImageRefMode.REFERENCED)
        loaded = DoclingDocument.load_from_json(root / "document.docling.json")
        assert loaded.texts[0].self_ref == first.self_ref
        assert loaded.texts[1].level == 2
        assert not loaded.pages
        assert len(loaded.pictures) == 1
        uri = str(loaded.pictures[0].image.uri)
        assert not Path(uri).is_absolute()
        assert not uri.startswith(("/", "file:", "http:", "https:", "data:"))
        assert ".." not in Path(uri).parts
        assert (root / uri).is_file()
        # The Windows JSON serializer uses backslashes; Markdown uses URI slashes.
        assert uri.replace("\\", "/") in (root / "document.md").read_text(encoding="utf-8")

    print("PASS: pinned API options, confidence, distinct heading references, referenced picture and JSON reload")


if __name__ == "__main__":
    main()
