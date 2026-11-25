"""Rebuild frozen Markdown without extraction pipelines or resource resolution."""

from __future__ import annotations

import json
import posixpath
import re
from importlib.metadata import version
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import marko
from marko import block, inline
from docling.backend.md_backend import MarkdownDocumentBackend
from docling.datamodel.backend_options import MarkdownBackendOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import InputDocument
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams
from docling_core.types.doc import ContentLayer, DocItemLabel, DoclingDocument, ImageRefMode

from akay_convert_to_markdown.contracts.artifacts import (
    ArtifactLayout, DocumentArtifactResult, Processing, Review, ReviewSummary, ReviewTable, Warning, parse_review,
)
from akay_convert_to_markdown.contracts.requests import DocumentRequest
from akay_convert_to_markdown.conversion.document_artifacts import _portable_json
from akay_convert_to_markdown.conversion.formulas import collect_formulas
from akay_convert_to_markdown.conversion.sections import SectionTextSerializer
from akay_convert_to_markdown.errors.exceptions import DocumentConversionError
from akay_convert_to_markdown.processing.blocking import drain_on_cancel

_MARKER = re.compile(r"<!--\s*akay-section:(?:start|end)\b.*?-->", re.DOTALL)


def _walk(node):
    yield node
    # Never interpret literal code content as Markdown/HTML syntax.
    if isinstance(node, (block.CodeBlock, block.FencedCode, inline.CodeSpan)):
        return
    children = getattr(node, "children", [])
    if isinstance(children, list):
        for child in children:
            yield from _walk(child)


def _replace_spans(text, changes):
    for (start, end), replacement in sorted(changes.items(), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def _tree(text):
    return marko.Markdown(extensions=["gfm"]).parse(text)


def _current_review(raw, request):
    if raw is None:
        return None
    review = parse_review(raw)
    prefix = ArtifactLayout.for_destination(request.source.blob_name).prefix + "images/"
    if review.content_type != "document" or review.content_key != request.content_key:
        raise DocumentConversionError("The current review does not belong to this content.")
    for image in review.images:
        name = image.blob_name.removeprefix(prefix)
        if (not image.blob_name.startswith(prefix) or "/" in name
                or not re.fullmatch(r"(?:figure|table)-[0-9]+\.png", name)):
            raise DocumentConversionError("The image inventory is outside its artifact destination.")
    return review


def _image_target(target, request, inventory):
    try:
        parsed = urlsplit(target)
    except ValueError:
        return None  # Malformed user-edited links are content, not fetch targets.
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or target.startswith("/"):
        return None
    source_parent = str(PurePosixPath(request.source.blob_name).parent)
    resolved = posixpath.normpath(posixpath.join(source_parent, unquote(parsed.path)))
    if resolved not in inventory:
        return None  # Edited/missing links remain verbatim, never validated by I/O.
    return resolved


def _prepare_markdown(raw):
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw.removeprefix("\ufeff")
    # Marko source spans refer to its normalized line endings. Keep every other
    # source character; never regenerate the teacher's Markdown from a serializer.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    if "\x00" in text:
        raise DocumentConversionError("The Markdown contains unsupported control characters.")
    changes = {}
    for node in _walk(_tree(text)):
        if isinstance(node, (block.HTMLBlock, inline.InlineHTML)):
            start, end = node.source_span
            for match in _MARKER.finditer(text[start:end]):
                first, last = start + match.start(), start + match.end()
                line_start = text.rfind("\n", 0, first) + 1
                if not text[line_start:first].strip() and text[last:last + 1] == "\n":
                    last += 1
                changes[(first, last)] = ""
    text = _replace_spans(text, changes)
    return text


class _HtmlImageLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.targets = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.targets.extend(value for name, value in attrs if name == "src" and value is not None)


def _active_images(markdown, request, review):
    images = review.images if review is not None else []
    inventory = {image.blob_name for image in images}
    targets = []
    for node in _walk(_tree(markdown)):
        if isinstance(node, inline.Image):
            targets.append(node.dest)
        elif isinstance(node, (block.HTMLBlock, inline.InlineHTML)):
            parser = _HtmlImageLinks()
            start, end = node.source_span
            parser.feed(markdown[start:end])
            targets.extend(parser.targets)
    referenced = {_image_target(target, request, inventory) for target in targets}
    return [image for image in images if image.blob_name in referenced]


def _parse_document(text, request):
    # The pinned backend's SetextHeading branch does not attach rich inline
    # groups to the heading. Feed equivalent ATX syntax to that backend only;
    # the teacher's source spelling remains untouched in the final Markdown.
    changes = {}
    for node in _walk(_tree(text)):
        if isinstance(node, block.SetextHeading):
            start, end = node.source_span
            prefix = text[text.rfind("\n", 0, start) + 1:start]
            lines = text[start:end].splitlines()[:-1]
            title = " ".join(line.removeprefix(prefix).strip() for line in lines)
            changes[(start, end)] = "#" * node.level + " " + title + "\n"
    parser_text = _replace_spans(text, changes)
    options = MarkdownBackendOptions(fetch_images=False, enable_local_fetch=False, enable_remote_fetch=False)
    stream = BytesIO(parser_text.encode("utf-8"))
    input_doc = InputDocument(path_or_stream=stream, format=InputFormat.MD, backend=MarkdownDocumentBackend,
                               backend_options=options, filename=PurePosixPath(request.source.blob_name).name)
    # The pinned declarative backend builds Core structure directly. Constructing
    # DocumentConverter would unnecessarily load extraction pipeline configuration.
    backend = input_doc._backend
    try:
        if not input_doc.valid or not isinstance(backend, MarkdownDocumentBackend) or not backend.is_valid():
            raise DocumentConversionError("The Markdown could not be parsed.")
        document = backend.convert()
    finally:
        if backend is not None:
            backend.unload()
    document.name = PurePosixPath(request.source.blob_name).name
    if document.origin is not None:
        document.origin.filename = document.name
        document.origin.uri = None
    document.pages.clear()
    for item, _ in document.iterate_items(traverse_pictures=True, included_content_layers=set(ContentLayer)):
        if hasattr(item, "prov"):
            item.prov = []
        if hasattr(item, "image"):
            item.image = None
        link = getattr(item, "hyperlink", None)
        scheme = getattr(link, "scheme", "")
        if link is not None and (isinstance(link, Path) or scheme == "file" or len(scheme) == 1):
            item.hyperlink = None
    if not (any(item.text.strip() for item in document.texts) or document.tables):
        raise DocumentConversionError("The Markdown contains no structured text.")
    return document


def _rebuild(markdown_raw, review_raw, request, output):
    # Revalidate even for local callers using Pydantic's unchecked model_copy.
    request = DocumentRequest.model_validate_json(request.model_dump_json())
    if request.operation != "rebuildFromMarkdown":
        raise DocumentConversionError("A reconstruction request is required.")
    original = _current_review(review_raw, request)
    markdown = _prepare_markdown(markdown_raw)
    document = _parse_document(markdown, request)
    collector = SectionTextSerializer(content_key=request.content_key if request.document_options.extract_sections else None)
    params = MarkdownParams(layers={ContentLayer.BODY}, image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="")
    params.labels -= {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
    MarkdownDocSerializer(doc=document, text_serializer=collector, params=params).serialize()
    if request.document_options.extract_sections:
        headings = [node for node in _walk(_tree(markdown)) if isinstance(node, (block.Heading, block.SetextHeading))]
        if len(headings) != len(collector.sections) or any(h.level != s.level for h, s in zip(headings, collector.sections)):
            raise DocumentConversionError("The Markdown heading structure could not be mapped completely.")
    images = _active_images(markdown, request, original)
    tables = [ReviewTable(id=f"table-{i:03d}", docling_item_ref=table.self_ref,
                           caption=table.caption_text(document) or None,
                           cells=_portable_json([cell.model_dump(mode="json") for cell in table.data.table_cells]))
              for i, table in enumerate(document.tables, 1)]
    formulas = collect_formulas(document, collector.sections)
    review = Review(schema_version=1, content_key=request.content_key, content_type="document", source=request.source,
                    summary=ReviewSummary(section_count=len(collector.sections), table_count=len(tables), image_count=len(images),
                                          formula_count=len(formulas)),
                    sections=collector.sections, tables=tables, images=images, formulas=formulas,
                    processing=Processing(operation="rebuildFromMarkdown", engine="docling", engine_version=version("docling-slim")),
                    warnings=[Warning(code="MARKDOWN_STRUCTURE_REBUILT",
                                      message="Structure was rebuilt from Markdown without extraction page measurements; parser normalization may differ from original layout.")])
    data = _portable_json(document.export_to_dict())
    DoclingDocument.model_validate(data)
    layout = ArtifactLayout.for_destination(request.source.blob_name)
    # Preserve the caller's text verbatim in the result; only the parser sees normalized text.
    original_markdown = markdown_raw.decode("utf-8") if isinstance(markdown_raw, bytes) else markdown_raw
    result = DocumentArtifactResult(markdown=original_markdown, docling_json=data, review=review, artifacts=layout.document_refs())
    output.mkdir(parents=True, exist_ok=False)
    destination = PurePosixPath(request.source.blob_name).name
    artifacts = output / (destination[:-3] + ".artifacts")
    artifacts.mkdir()
    (artifacts / "document.docling.json").write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (artifacts / "review.json").write_text(review.model_dump_json(by_alias=True), encoding="utf-8")
    return result


async def rebuild_document_artifacts(markdown_raw: str | bytes, current_review_raw: str | bytes | None,
                                     request: DocumentRequest, output_directory: Path) -> DocumentArtifactResult:
    """Caller supplies frozen bytes from configured Blob containers; no Blob I/O here."""
    def rebuild():
        try:
            return _rebuild(markdown_raw, current_review_raw, request, output_directory)
        except DocumentConversionError:
            raise
        except Exception:
            raise DocumentConversionError("The reviewed Markdown artifacts could not be rebuilt.") from None

    return await drain_on_cancel(rebuild)
