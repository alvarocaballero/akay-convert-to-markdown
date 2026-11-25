"""N4 local artifact generation. Publication, reuse and Blob ownership belong to N5."""

from __future__ import annotations

import json
import math
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
import warnings

from docling.datamodel.base_models import ConfidenceReport, ConversionStatus, PageConfidenceScores
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams
from docling_core.types.doc import ContentLayer, DocItemLabel, DoclingDocument, ImageRefMode

from akay_convert_to_markdown.contracts.artifacts import (
    ArtifactLayout, Confidence, DocumentArtifactResult, PageConfidence, Processing,
    Review, ReviewImage, ReviewSummary, ReviewTable, Warning,
)
from akay_convert_to_markdown.contracts.requests import DocumentRequest
from akay_convert_to_markdown.conversion.docling_converter import ExtractedDocument, _drain_on_cancel
from akay_convert_to_markdown.conversion.formulas import collect_formulas
from akay_convert_to_markdown.conversion.sections import (
    SECTION_NAMESPACE, SectionTextSerializer as _SectionTextSerializer, section_id,
)
from akay_convert_to_markdown.errors.exceptions import DocumentConversionError


def _page_number(item) -> int | None:
    return item.prov[0].page_no if item.prov else None


def _finite(value: float | None) -> float | None:
    return float(value) if value is not None and math.isfinite(value) else None


def _grade(scores: PageConfidenceScores, value: float | None) -> str | None:
    # Pinned 2.141.0 exposes component scores, but no component-grade properties.
    # Reuse its exact grading helper instead of copying/calibrating thresholds.
    return scores._score_to_grade(value).value if value is not None else None


def _aggregate(scores: PageConfidenceScores, name: str) -> float | None:
    # Missing upstream components use NaN and NumPy warns for empty aggregates.
    # Preserve the upstream aggregate/override, normalizing only the final value.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
        warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        warnings.filterwarnings("ignore", message="invalid value encountered", category=RuntimeWarning)
        return _finite(getattr(scores, name))


def _confidence(report: ConfidenceReport) -> Confidence:
    pages = []
    for number, scores in sorted(report.pages.items()):
        fields = {}
        for component in ("layout", "ocr", "parse", "table"):
            value = _finite(getattr(scores, f"{component}_score"))
            fields[f"{component}_score"] = value
            fields[f"{component}_grade"] = _grade(scores, value)
        mean, low = _aggregate(scores, "mean_score"), _aggregate(scores, "low_score")
        pages.append(PageConfidence(page_number=number, **fields, mean_score=mean,
                                    mean_grade=_grade(scores, mean), low_grade=_grade(scores, low)))
    return Confidence(mean_grade=_grade(report, _aggregate(report, "mean_score")),
                      low_grade=_grade(report, _aggregate(report, "low_score")), pages=pages)


def _portable_json(value: Any) -> Any:
    """Normalize absent measurements, not document text or consumer identities."""
    if isinstance(value, float):
        return _finite(value)
    if isinstance(value, dict):
        return {key: _portable_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable_json(item) for item in value]
    return value


def _prepare_document(extraction: ExtractedDocument, request: DocumentRequest) -> DoclingDocument:
    document = extraction.document.model_copy(deep=True)
    source_name = PurePosixPath(request.source.blob_name).name
    document.name = source_name
    if document.origin is not None:
        document.origin.filename = source_name
        document.origin.uri = None
    for page in document.pages.values():
        page.image = None
    # Retain normal web links as content, but never expose private local paths.
    for text in document.texts:
        link = text.hyperlink
        scheme = getattr(link, "scheme", "")
        if link is not None and (isinstance(link, Path) or scheme == "file" or len(scheme) == 1):
            text.hyperlink = None
    return document


def _export_images(document: DoclingDocument, artifact_directory: Path,
                   layout: ArtifactLayout, notices: list[Warning]) -> tuple[list[ReviewImage], dict[str, str]]:
    images, table_images = [], {}
    for kind, items in (("figure", document.pictures), ("table", document.tables)):
        for number, item in enumerate(items, 1):
            image = item.image
            item.image = None
            if image is None or not str(image.uri).startswith("data:image/"):
                if kind == "figure" or image is not None:
                    notice = Warning(code="IMAGE_NOT_MATERIALIZED",
                                     message="An image has no local crop; linked resources were not fetched.",
                                     page_number=_page_number(item))
                    if notice not in notices:
                        notices.append(notice)
                continue
            # Reading data-image bytes is allowed; Path/file/HTTP URIs never reach PIL.
            crop = image.pil_image
            if crop is None:
                raise DocumentConversionError("A document image could not be exported.")
            identity = f"{kind}-{number:03d}"
            relative = f"images/{identity}.png"
            path = artifact_directory / relative
            path.parent.mkdir(exist_ok=True)
            crop.save(path, format="PNG")
            image.uri = Path(relative)
            item.image = image
            blob_name = layout.prefix + relative
            images.append(ReviewImage(id=identity, blob_name=blob_name,
                                      caption=item.caption_text(document) or None, page_number=_page_number(item)))
            if kind == "table":
                table_images[item.self_ref] = blob_name
    return images, table_images


def _export(extraction: ExtractedDocument, request: DocumentRequest,
            output_directory: Path) -> DocumentArtifactResult:
    layout = ArtifactLayout.for_destination(request.destination_blob_name)
    destination = PurePosixPath(request.destination_blob_name).name
    artifact_name = destination[:-3] + ".artifacts"
    artifact_directory = output_directory / artifact_name
    document = _prepare_document(extraction, request)
    notices = list(extraction.warnings)
    artifact_directory.mkdir()
    images, table_images = _export_images(document, artifact_directory, layout, notices)
    data = _portable_json(document.export_to_dict())
    for item in [*data.get("pictures", []), *data.get("tables", [])]:
        if item.get("image"):
            item["image"]["uri"] = item["image"]["uri"].replace("\\", "/")
    # Validate reload without resolving any image URI. The indexer can use this
    # structured data without the original source or a local image-file read.
    DoclingDocument.model_validate(data)
    for item in [*document.pictures, *document.tables]:
        if item.image is not None:
            # Core preserves existing '%' escapes. Encode literal Blob-name '%' too.
            relative_uri = (PurePosixPath(artifact_name) / str(item.image.uri).replace("\\", "/")).as_posix()
            item.image.uri = Path(quote(relative_uri, safe="/"))
    text_serializer = _SectionTextSerializer(content_key=request.content_key if request.document_options.extract_sections else None)
    params = MarkdownParams(layers={ContentLayer.BODY}, image_mode=ImageRefMode.REFERENCED)
    params.labels -= {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
    serializer = MarkdownDocSerializer(doc=document, text_serializer=text_serializer,
                                       params=params)
    markdown = serializer.serialize().text
    tables = [ReviewTable(id=f"table-{i:03d}", docling_item_ref=table.self_ref,
                           caption=table.caption_text(document) or None, page_number=_page_number(table),
                           cells=_portable_json([cell.model_dump(mode="json") for cell in table.data.table_cells]),
                           blob_name=table_images.get(table.self_ref)) for i, table in enumerate(document.tables, 1)]
    formulas = collect_formulas(document, text_serializer.sections)
    review = Review(schema_version=1, content_key=request.content_key, content_type="document", source=request.source,
                    summary=ReviewSummary(page_count=len(document.pages) if document.pages else None,
                                          section_count=len(text_serializer.sections), table_count=len(tables), image_count=len(images),
                                          formula_count=len(formulas)),
                    sections=text_serializer.sections, tables=tables, images=images, formulas=formulas,
                    confidence=_confidence(extraction.confidence),
                    warnings=notices, processing=Processing(operation="convert", engine="docling", engine_version=version("docling-slim")))
    result = DocumentArtifactResult(markdown=markdown, docling_json=data, review=review, artifacts=layout.document_refs())
    (output_directory / destination).write_text(markdown, encoding="utf-8", newline="\n")
    (artifact_directory / "document.docling.json").write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (artifact_directory / "review.json").write_text(json.dumps(review.model_dump(mode="json", by_alias=True),
                                                              ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return result


async def export_document_artifacts(extraction: ExtractedDocument, request: DocumentRequest,
                                     output_directory: Path) -> DocumentArtifactResult:
    """Generate a fresh local package rooted at the destination's parent directory.

    The caller owns the new directory and any incomplete files after failure.
    This function performs no Blob writes, callbacks, reuse or publication claims.
    Cancellation retains ownership until the synchronous writer has stopped.
    """
    def export() -> DocumentArtifactResult:
        output_directory.mkdir(parents=True, exist_ok=False)
        try:
            if extraction.conversion_result.status != ConversionStatus.SUCCESS or extraction.conversion_result.errors:
                raise DocumentConversionError("The document could not be converted completely.")
            return _export(extraction, request, output_directory)
        except DocumentConversionError:
            raise
        except Exception:
            raise DocumentConversionError("The document artifacts could not be generated.") from None

    return await _drain_on_cancel(export)
