"""Pinned Docling extraction behind the existing Markdown conversion boundary.

The rich extraction result is local only. Review/section generation and coherent
Blob publication are separate tasks; a legacy conversion still returns Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from akay_convert_to_markdown.contracts.artifacts import Warning
from akay_convert_to_markdown.contracts.requests import DocumentOptions
from akay_convert_to_markdown.errors.exceptions import DocumentConversionError, TransientError
from akay_convert_to_markdown.models.conversion_request import validate_extension
from akay_convert_to_markdown.processing.blocking import drain_on_cancel as _drain_on_cancel

if TYPE_CHECKING:
    from docling.datamodel.base_models import ConfidenceReport, InputFormat
    from docling.datamodel.document import ConversionResult
    from docling_core.types.doc import DoclingDocument

class DocumentModelConfigurationError(TransientError):
    """An operator must supply the local model assets, not change the source."""


def build_docling_converter(options: DocumentOptions, *, artifacts_path: Path | None,
                            input_format: InputFormat | None = None):
    """Construct a fresh engine; imports/model construction stay off the event loop."""
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.backend_options import (
        HTMLBackendOptions, MarkdownBackendOptions, MsPowerpointBackendOptions,
        MsWordBackendOptions, ThreadedDoclingParseBackendOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        ConvertPipelineOptions, HeadingHierarchyOptions, OcrMode, PdfPipelineOptions,
        RapidOcrOptions, TableFormerMode,
    )
    from docling.document_converter import (
        DocumentConverter, HTMLFormatOption, MarkdownFormatOption, PdfFormatOption,
        PowerpointFormatOption, WordFormatOption,
    )

    common = dict(enable_remote_services=False, allow_external_plugins=False,
                  do_picture_classification=False, do_picture_description=False,
                  do_chart_extraction=False, artifacts_path=artifacts_path,
                  accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU))
    pdf = PdfPipelineOptions(**common)
    pdf.do_ocr = True
    # The ISO prefix avoids ambiguous native OCR codes; exactly one selection.
    pdf.ocr_options = RapidOcrOptions(backend="onnxruntime", lang=[f"iso:{options.ocr_language}"],
                                     mode=OcrMode.PDF_AWARE_LAYOUT_REGIONS)
    pdf.do_table_structure = True
    pdf.table_structure_options.mode = TableFormerMode.ACCURATE
    pdf.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)
    pdf.generate_parsed_pages = True
    pdf.generate_picture_images = True
    pdf.generate_page_images = False
    pdf.do_code_enrichment = options.code_enrichment
    pdf.do_formula_enrichment = options.formula_enrichment
    simple = ConvertPipelineOptions(**common)
    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pdf,
                                         backend_options=ThreadedDoclingParseBackendOptions()),
        InputFormat.DOCX: WordFormatOption(pipeline_options=simple, backend_options=MsWordBackendOptions()),
        InputFormat.PPTX: PowerpointFormatOption(pipeline_options=simple, backend_options=MsPowerpointBackendOptions()),
        # Keep the preamble in the body rather than classifying it as page furniture.
        InputFormat.HTML: HTMLFormatOption(pipeline_options=simple,
                                           backend_options=HTMLBackendOptions(fetch_images=False,
                                                                              infer_furniture=False)),
        InputFormat.MD: MarkdownFormatOption(pipeline_options=simple,
                                             backend_options=MarkdownBackendOptions(fetch_images=False)),
    }
    allowed = [input_format] if input_format is not None else list(format_options)
    return DocumentConverter(allowed_formats=allowed, format_options=format_options)


@dataclass(frozen=True)
class ExtractedDocument:
    """Retain ConversionResult confidence as well as the structured document."""

    conversion_result: ConversionResult
    warnings: tuple[Warning, ...] = ()

    @property
    def document(self) -> DoclingDocument:
        return self.conversion_result.document

    @property
    def confidence(self) -> ConfidenceReport:
        return self.conversion_result.confidence

    async def export_referenced(self, output_directory: Path) -> None:
        """Export into a fresh, attempt-owned local directory, never Blob storage.

        Only in-memory picture crops are exported. Page renders and unmaterialized
        source references must not turn into public screenshots or local reads.
        N4 will map these local exports to the final artifact layout/review.
        """
        def export() -> None:
            import json
            from docling_core.types.doc import ImageRefMode

            document = self.document.model_copy(deep=True)
            for page in document.pages.values():
                page.image = None
            for item in [*document.pictures, *document.tables]:
                image = item.image
                if image is not None and not str(image.uri).startswith("data:image/"):
                    item.image = None
            output_directory.mkdir(parents=True, exist_ok=False)
            json_path = output_directory / "document.docling.json"
            document.save_as_json(json_path, artifacts_dir=Path("images"), image_mode=ImageRefMode.REFERENCED)
            document.save_as_markdown(output_directory / "document.md", artifacts_dir=Path("images"),
                                      image_mode=ImageRefMode.REFERENCED)
            # Core 2.99 emits platform-native separators in JSON on Windows.
            data = json.loads(json_path.read_text(encoding="utf-8"))
            for item in [*data.get("pictures", []), *data.get("tables", [])]:
                if item.get("image"):
                    item["image"]["uri"] = item["image"]["uri"].replace("\\", "/")
            json_path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")

        await _drain_on_cancel(export)


class DoclingDocumentConverter:
    """Fresh pinned engines, local sources only, strict complete-result policy."""

    def __init__(self, *, artifacts_path: Path | None = None, factory: Callable | None = None) -> None:
        self._artifacts_path = artifacts_path
        self._factory = factory

    async def extract(self, source_path: Path, options: DocumentOptions) -> ExtractedDocument:
        extension = validate_extension(source_path.name)

        def extract() -> ExtractedDocument:
            from docling.datamodel.base_models import ConversionStatus, InputFormat

            if self._factory is None and extension == ".pdf":
                if self._artifacts_path is None or not self._artifacts_path.is_dir():
                    raise DocumentModelConfigurationError("PDF extraction requires local Docling assets.")
            try:
                engine = (self._factory(options) if self._factory else
                          build_docling_converter(options, artifacts_path=self._artifacts_path,
                                                   input_format={".pdf": InputFormat.PDF, ".docx": InputFormat.DOCX,
                                                                 ".pptx": InputFormat.PPTX, ".html": InputFormat.HTML,
                                                                 ".htm": InputFormat.HTML, ".md": InputFormat.MD,
                                                                 ".txt": InputFormat.MD}[extension]))
                if self._factory is None and extension == ".pdf":
                    try:
                        # Validate model availability before starting native parser
                        # threads. Failed initialization after parsing can crash
                        # docling-parse's unload path on Windows.
                        engine.initialize_pipeline(InputFormat.PDF)
                    except Exception:
                        raise DocumentModelConfigurationError("The local PDF pipeline could not be initialized.") from None
                # Restrict sniffing to this extension's backend: a renamed PDF
                # must not bypass the explicit local-model configuration policy.
                result = engine.convert(source_path, raises_on_error=False)
                if result.status != ConversionStatus.SUCCESS or result.errors:
                    raise DocumentConversionError("The document could not be converted completely.")
                document = result.document
                if not (any(item.text.strip() for item in document.texts)
                        or any(table.data.table_cells for table in document.tables)
                        or any(picture.image is not None and str(picture.image.uri).startswith("data:image/")
                               for picture in document.pictures)):
                    raise DocumentConversionError("The document contains no extractable content.")
                warnings = []
                if extension != ".pdf" and (options.code_enrichment or options.formula_enrichment):
                    warnings.append(Warning(code="ENRICHMENT_NOT_APPLICABLE",
                                            message="Specialized code/formula recognition applies to PDF regions only; native content is retained."))
                if any(picture.image is None for picture in document.pictures):
                    warnings.append(Warning(code="IMAGE_NOT_MATERIALIZED",
                                            message="An image has no local crop; linked resources were not fetched."))
                return ExtractedDocument(result, tuple(warnings))
            except (DocumentConversionError, DocumentModelConfigurationError):
                raise
            except FileNotFoundError:
                # Missing prefetched assets are configuration/retry failures, not bad source content.
                raise DocumentModelConfigurationError("Required local document resources are unavailable.") from None
            except Exception:
                raise DocumentConversionError("The document could not be converted.") from None

        return await _drain_on_cancel(extract)

    async def convert(self, source_path: Path) -> str:
        """Legacy Markdown-only interface; version-one jobs still fail closed."""
        extraction = await self.extract(source_path, DocumentOptions())
        return await _drain_on_cancel(extraction.document.export_to_markdown)
