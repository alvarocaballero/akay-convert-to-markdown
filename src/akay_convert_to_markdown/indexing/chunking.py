"""Prepare bounded chunks from saved artifacts using the pinned Core APIs only."""

from pathlib import Path, PurePosixPath

from pydantic import Field, TypeAdapter
from docling_core.transforms.chunker import DocChunk
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer, ChunkingSerializerProvider
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams
from docling_core.types.doc import ContentLayer, DocItemLabel, DoclingDocument, ImageRefMode, InlineGroup

from akay_convert_to_markdown.contracts.artifacts import parse_review, parse_transcript
from akay_convert_to_markdown.contracts.base import blob_name, validate_wire
from akay_convert_to_markdown.contracts.requests import IndexRequest
from akay_convert_to_markdown.conversion.sections import SectionTextSerializer
from akay_convert_to_markdown.errors.exceptions import PermanentError
from akay_convert_to_markdown.indexing.chunks import ChunkProvenance, ContentChunk, SegmentCitation


class ChunkingError(PermanentError):
    code = "CONTENT_CHUNKING_FAILED"


def _params() -> MarkdownParams:
    params = MarkdownParams(layers={ContentLayer.BODY}, image_mode=ImageRefMode.PLACEHOLDER,
                            image_placeholder="", include_hyperlinks=False, escape_underscores=False,
                            escape_html=False, include_picture_classification=False)
    params.labels -= {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
    return params


class _ScopedSerializer(ChunkingDocSerializer):
    excluded: set[str] = Field(default_factory=set)

    def get_excluded_refs(self, **kwargs) -> set[str]:
        return super().get_excluded_refs(**kwargs) | self.excluded


class _ScopedProvider(ChunkingSerializerProvider):
    def __init__(self, excluded: set[str]):
        self.excluded = excluded

    def get_serializer(self, doc: DoclingDocument):
        return _ScopedSerializer(doc=doc, params=_params(), excluded=self.excluded)


class _BudgetTokenizer(BaseTokenizer):
    delegate: BaseTokenizer
    limit: int

    def count_tokens(self, text: str) -> int:
        return self.delegate.count_tokens(text)

    def get_max_tokens(self) -> int:
        return self.limit

    def get_tokenizer(self):
        # semchunk accepts a counter callable: use exactly the same counting
        # policy as contextualization, including any tokenizer-added tokens.
        return self.count_tokens


class _ContextChunker(HybridChunker):
    heading_path: list[str] = Field(default_factory=list)
    resource_name: str
    include_internal: bool = True

    def contextualize(self, chunk) -> str:
        parts = [" > ".join(self.heading_path), self.resource_name]
        if self.include_internal:
            parts.append(" > ".join(chunk.meta.headings or []))
        parts.append(chunk.text)
        return "\n\n".join(part for part in parts if part)

    def _split_using_plain_text(self, doc_chunk, doc_serializer):
        empty = doc_chunk.model_copy(update={"text": ""})
        lengths = self._doc_chunk_length(doc_chunk)
        if (self.tokenizer.count_tokens(self.contextualize(empty)) >= self.max_tokens
                or (lengths.total_len > self.max_tokens and lengths.other_len >= self.max_tokens)):
            # Core otherwise drops headings and warns with the full document text.
            raise ChunkingError("The required context exceeds the chunk budget.", code="CHUNK_CONTEXT_TOO_LARGE")
        return super()._split_using_plain_text(doc_chunk, doc_serializer)


def _sections(document: DoclingDocument, content_key: str):
    collector = SectionTextSerializer(content_key=content_key)
    # Reproduce N4's exact heading rendering for inline-only title fallbacks.
    params = MarkdownParams(layers={ContentLayer.BODY}, image_mode=ImageRefMode.PLACEHOLDER, image_placeholder="")
    params.labels -= {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
    MarkdownDocSerializer(doc=document, text_serializer=collector, params=params).serialize()
    return collector.sections


def _document_input(request: IndexRequest, raw: str | bytes, review_raw: str | bytes | None):
    # model validation reloads structure, unlike load/export helpers that can
    # materialize referenced pictures. No original PDF or resource is opened.
    document = validate_wire(TypeAdapter(DoclingDocument), raw)
    blob_name(document.name)
    if PurePosixPath(document.name).name != document.name:
        raise ChunkingError("The document resource name must be a portable filename.")
    for page in document.pages.values():
        page.image = None
    for item in [*document.pictures, *document.tables]:
        item.image = None
    if document.origin is not None:
        document.origin.uri = None
    for item in document.texts:
        link = item.hyperlink
        scheme = getattr(link, "scheme", "")
        if link is not None and (isinstance(link, Path) or scheme == "file" or len(scheme) == 1):
            item.hyperlink = None
    sections = _sections(document, request.content_key)
    for item in document.texts:
        item.hyperlink = None
    origin = None
    if request.section_context.mode == "fromReview":
        if review_raw is None:
            raise ChunkingError("A matching review is required.")
        review = parse_review(review_raw)
        if (PurePosixPath(request.source.blob_name).parent != PurePosixPath(request.section_context.review_blob_name).parent
                or review.content_type != "document" or review.content_key != request.content_key
                or review.sections != sections or PurePosixPath(review.source.blob_name).name != document.name
                or (document.origin is not None and document.origin.filename != document.name)):
            raise ChunkingError("The review does not match the structured document.")
        origin = review.source
    elif review_raw is not None:
        raise ChunkingError("Review data requires the fromReview section context.")
    # Core's hierarchical chunker reads heading.text, whereas its Markdown
    # serializer also renders inline groups. Reuse the exporter's effective
    # heading text without emitting those inline spans again as body content.
    by_ref = {item.self_ref: item for item, _ in document.iterate_items()}
    for section in sections:
        heading = by_ref[section.docling_item_ref]
        if not heading.text:
            heading.text = section.title
            heading.children = [ref for ref in heading.children if not isinstance(ref.resolve(document), InlineGroup)]
    return document, sections, origin, {}


def _transcript_input(request: IndexRequest, raw: str | bytes, review_raw: str | bytes | None):
    transcript = parse_transcript(raw)
    if transcript.content_key != request.content_key or not transcript.segments or review_raw is not None:
        raise ChunkingError("The transcript does not match the requested content.")
    origin = transcript.origin
    name = PurePosixPath(origin.blob_name).name if origin.type == "blob" else origin.url
    document = DoclingDocument(name=name)
    citations = {}
    for segment in transcript.segments:
        item = document.add_text(label=DocItemLabel.TEXT, text=segment.text)
        citations[item.self_ref] = SegmentCitation(id=segment.id, item_ref=item.self_ref,
                                                  start_milliseconds=segment.start_milliseconds,
                                                  end_milliseconds=segment.end_milliseconds,
                                                  speaker=segment.speaker,
                                                  language=segment.language or transcript.language)
    return document, [], origin, citations


def _partitions(document, sections, mode):
    """Partition by structural identity BEFORE HybridChunker can merge peers."""
    if mode != "fromReview":
        return [(None, [], set())]
    by_ref = {s.docling_item_ref: s for s in sections}
    by_id = {s.id: s for s in sections}
    owned = {None: set()}
    current = None
    for item, _ in document.iterate_items(with_groups=True, included_content_layers={ContentLayer.BODY}):
        if item.self_ref in by_ref:
            current = by_ref[item.self_ref].id
            owned[current] = set()
        owned[current].add(item.self_ref)
    all_refs = set().union(*owned.values())
    result = []
    for identity, refs in owned.items():
        path, ancestors = [], set()
        section = by_id.get(identity)
        while section is not None:
            path.insert(0, section.title)
            ancestors.add(section.docling_item_ref)
            section = by_id.get(section.parent_id)
        # Ancestor headers supply context, never body from another domain section.
        excluded = all_refs - refs - ancestors
        result.append((identity, path, excluded))
    return result


def _provenance(chunk: DocChunk, citations: dict[str, SegmentCitation]) -> ChunkProvenance:
    items = {item.self_ref: item for item in chunk.meta.doc_items}
    segments = [citations[ref] for ref in items if ref in citations]
    starts = [segment.start_milliseconds for segment in segments]
    ends = [segment.end_milliseconds for segment in segments]
    return ChunkProvenance(item_refs=list(items), pages=sorted({p.page_no for item in items.values() for p in item.prov}),
                           segments=segments,
                           start_milliseconds=min(starts) if starts and None not in starts else None,
                           end_milliseconds=max(ends) if ends and None not in ends else None)


def chunk_content(request: IndexRequest, source_raw: str | bytes, *, tokenizer: BaseTokenizer,
                  tokenizer_id: str, review_raw: str | bytes | None = None) -> list[ContentChunk]:
    """Synchronous local preparation; caller supplies downloaded bytes and tokenizer.

    No defaults or model discovery. Runtime callers must run this blocking work
    with the existing drain-on-cancel helper and bound input downloads. No partial
    result escapes on invalid structure, incompatible context or token overflow.
    """
    try:
        budget = request.index_profile.max_chunk_tokens
        if (not isinstance(tokenizer, BaseTokenizer) or tokenizer_id != request.index_profile.tokenizer
                or tokenizer.get_max_tokens() < budget):
            raise ChunkingError("The configured tokenizer is incompatible with the requested budget.")
        loader = _document_input if request.source.format == "docling" else _transcript_input
        document, sections, origin, citations = loader(request, source_raw, review_raw)
        results = []
        context = request.section_context
        for identity, path, excluded in _partitions(document, sections, context.mode):
            if context.mode == "fixed":
                identity, path = context.section_id, context.heading_path
            chunker = _ContextChunker(tokenizer=_BudgetTokenizer(delegate=tokenizer, limit=budget),
                                      serializer_provider=_ScopedProvider(excluded=excluded),
                                      resource_name=document.name, heading_path=path,
                                      include_internal=context.mode != "fromReview", repeat_table_header=False,
                                      always_emit_headings=True)
            for chunk in chunker.chunk(document):
                if not chunk.text.strip():
                    if not chunk.meta.headings or not chunk.meta.headings[-1].strip():
                        continue
                    chunk = chunk.model_copy(update={"text": chunk.meta.headings[-1]})
                text = chunker.contextualize(chunk)
                count = tokenizer.count_tokens(text)
                if count > budget:
                    raise ChunkingError("The contextualized chunk exceeds the token budget.", code="CHUNK_TOKEN_LIMIT")
                results.append(ContentChunk(chunk_index=len(results), section_id=identity, heading_path=path,
                                             internal_headings=chunk.meta.headings or [], text=chunk.text,
                                             contextualized_text=text, token_count=count, source=request.source,
                                             origin=origin, resource_name=document.name, provenance=_provenance(chunk, citations)))
        if not results:
            raise ChunkingError("The artifact contains no chunkable content.")
        return results
    except ChunkingError:
        raise
    except Exception:
        raise ChunkingError("The artifact could not be prepared for chunking.") from None
