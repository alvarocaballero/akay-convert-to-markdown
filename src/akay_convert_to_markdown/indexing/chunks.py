"""Internal prepared chunks, not another public artifact or webhook contract."""

from pydantic import Field

from akay_convert_to_markdown.contracts.base import Contract, NonEmpty, NonNegativeInt, PositiveInt, Uuid
from akay_convert_to_markdown.contracts.requests import IndexSource, Source


class SegmentCitation(Contract):
    id: NonEmpty
    item_ref: NonEmpty
    start_milliseconds: NonNegativeInt | None = None
    end_milliseconds: NonNegativeInt | None = None
    speaker: NonEmpty | None = None
    language: NonEmpty | None = None


class ChunkProvenance(Contract):
    item_refs: list[NonEmpty]
    pages: list[PositiveInt] = Field(default_factory=list)
    start_milliseconds: NonNegativeInt | None = None
    end_milliseconds: NonNegativeInt | None = None
    segments: list[SegmentCitation] = Field(default_factory=list)


class ContentChunk(Contract):
    chunk_index: NonNegativeInt
    section_id: Uuid | None = None
    heading_path: list[NonEmpty] = Field(default_factory=list)
    internal_headings: list[NonEmpty] = Field(default_factory=list)
    text: NonEmpty
    contextualized_text: NonEmpty
    token_count: PositiveInt
    source: IndexSource
    origin: Source | None = None
    resource_name: NonEmpty
    provenance: ChunkProvenance
