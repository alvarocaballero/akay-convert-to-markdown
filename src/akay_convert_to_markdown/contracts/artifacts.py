"""Artifact references, review metadata and timed transcripts, not publishers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, TypeAdapter, model_validator, model_serializer

from akay_convert_to_markdown.contracts.base import (
    BlobName, Contract, MarkdownDestination, NonEmpty, NonNegativeInt, PositiveInt, Uuid, Version, validate_wire,
)
from akay_convert_to_markdown.contracts.requests import BlobSource, Source


class DocumentArtifactRefs(Contract):
    docling_json_blob_name: BlobName
    review_blob_name: BlobName


class MediaArtifactRefs(Contract):
    transcript_json_blob_name: BlobName
    review_blob_name: BlobName


class ArtifactLayout(Contract):
    destination_blob_name: MarkdownDestination

    @classmethod
    def for_destination(cls, destination: str) -> ArtifactLayout:
        return cls(destination_blob_name=destination)

    @property
    def prefix(self) -> str:
        return self.destination_blob_name[:-3] + ".artifacts/"

    def document_refs(self) -> DocumentArtifactRefs:
        return DocumentArtifactRefs(docling_json_blob_name=self.prefix + "document.docling.json",
                                    review_blob_name=self.prefix + "review.json")

    def media_refs(self) -> MediaArtifactRefs:
        return MediaArtifactRefs(transcript_json_blob_name=self.prefix + "transcript.json",
                                 review_blob_name=self.prefix + "review.json")


class ReviewSummary(Contract):
    page_count: NonNegativeInt | None = None
    section_count: NonNegativeInt = 0
    table_count: NonNegativeInt = 0
    image_count: NonNegativeInt = 0
    formula_count: NonNegativeInt = 0
    duration_milliseconds: NonNegativeInt | None = None


class Section(Contract):
    id: Uuid
    parent_id: Uuid | None = None
    title: NonEmpty
    level: PositiveInt
    order: NonNegativeInt
    docling_item_ref: NonEmpty
    page_number: PositiveInt | None = None


class ReviewImage(Contract):
    id: NonEmpty
    blob_name: BlobName
    caption: str | None = None
    page_number: PositiveInt | None = None


class ReviewTable(Contract):
    id: NonEmpty
    docling_item_ref: NonEmpty
    title: str | None = None
    caption: str | None = None
    page_number: PositiveInt | None = None
    # Retain upstream cell representation without inventing a second table engine.
    cells: list[dict[str, JsonValue]] = Field(default_factory=list)
    blob_name: BlobName | None = None


class ReviewFormula(Contract):
    id: NonEmpty
    docling_item_ref: NonEmpty
    section_id: Uuid | None = None
    text: str
    latex: str | None = None
    page_number: PositiveInt | None = None


class PageConfidence(Contract):
    page_number: PositiveInt
    layout_score: float | None = None
    layout_grade: NonEmpty | None = None
    ocr_score: float | None = None
    ocr_grade: NonEmpty | None = None
    parse_score: float | None = None
    parse_grade: NonEmpty | None = None
    table_score: float | None = None
    table_grade: NonEmpty | None = None
    mean_score: float | None = None
    mean_grade: NonEmpty | None = None
    low_grade: NonEmpty | None = None


class Confidence(Contract):
    mean_grade: NonEmpty | None = None
    low_grade: NonEmpty | None = None
    pages: list[PageConfidence] = Field(default_factory=list)


class Warning(Contract):
    code: NonEmpty
    message: NonEmpty
    page_number: PositiveInt | None = None


class Processing(Contract):
    operation: Literal["convert", "rebuildFromMarkdown"] | None = None
    engine: NonEmpty
    engine_version: NonEmpty

    @model_serializer(mode="wrap")
    def _optional_document_operation(self, handler):
        data = handler(self)
        if self.operation is None:
            data.pop("operation", None)
        return data


class YouTubeMetadata(Contract):
    video_id: NonEmpty
    canonical_url: NonEmpty
    title: NonEmpty | None = None

    @model_validator(mode="after")
    def _identity(self):
        from akay_convert_to_markdown.models.youtube import video_identity

        identity, canonical = video_identity(self.canonical_url)
        if identity != self.video_id or canonical != self.canonical_url:
            raise ValueError("YouTube metadata must use a canonical video identity.")
        return self


class Review(Contract):
    schema_version: Version
    content_key: NonEmpty
    content_type: Literal["document", "audio", "video"]
    source: Source
    summary: ReviewSummary
    sections: list[Section] = Field(default_factory=list)
    tables: list[ReviewTable] = Field(default_factory=list)
    images: list[ReviewImage] = Field(default_factory=list)
    formulas: list[ReviewFormula] = Field(default_factory=list)
    confidence: Confidence = Field(default_factory=Confidence)
    warnings: list[Warning] = Field(default_factory=list)
    processing: Processing
    youtube: YouTubeMetadata | None = None
    extraction_review_blob_name: BlobName | None = None

    @model_validator(mode="after")
    def _consistent_review(self):
        if self.processing.operation == "rebuildFromMarkdown":
            if (self.content_type != "document"
                    or self.confidence != Confidence() or self.summary.page_count is not None
                    or any(item.page_number is not None for item in [*self.sections, *self.tables, *self.formulas])):
                raise ValueError("Reconstructed text cannot inherit extraction page measurements.")
        elif self.extraction_review_blob_name is not None:
            raise ValueError("Only reconstructed documents reference an extraction review.")
        if self.youtube is not None:
            from akay_convert_to_markdown.contracts.requests import YouTubeSource
            from akay_convert_to_markdown.models.youtube import video_identity

            if (not isinstance(self.source, YouTubeSource)
                    or video_identity(self.source.url)[0] != self.youtube.video_id):
                raise ValueError("YouTube metadata must describe the original source.")
        for count, items in ((self.summary.section_count, self.sections), (self.summary.table_count, self.tables),
                             (self.summary.image_count, self.images), (self.summary.formula_count, self.formulas)):
            if count != len(items) or len({item.id for item in items}) != len(items):
                raise ValueError("Review inventory and summary must agree with unique identities.")
        seen = {}
        for order, section in enumerate(self.sections):
            if section.order != order or (section.parent_id is not None and
                                         (section.parent_id not in seen or seen[section.parent_id] >= section.level)):
                raise ValueError("Sections must be in reading order with preceding higher-level parents.")
            seen[section.id] = section.level
        if any(item.section_id is not None and item.section_id not in seen for item in self.formulas):
            raise ValueError("Formula sections must reference this review's sections.")
        if self.content_type != "document":
            if (self.sections or self.tables or self.images or self.formulas or self.confidence != Confidence()
                    or self.summary.page_count is not None):
                raise ValueError("Media reviews cannot contain document sections or PDF measurements.")
        elif not isinstance(self.source, BlobSource):
            raise ValueError("Document reviews require a Blob source.")
        return self


class TranscriptSegment(Contract):
    id: NonEmpty
    start_milliseconds: NonNegativeInt | None = None
    end_milliseconds: NonNegativeInt | None = None
    speaker: NonEmpty | None = None
    language: NonEmpty | None = None
    text: NonEmpty

    @model_validator(mode="after")
    def _time_range(self):
        if (self.start_milliseconds is not None and self.end_milliseconds is not None
                and self.end_milliseconds < self.start_milliseconds):
            raise ValueError("Segment end cannot precede start.")
        return self


class Transcript(Contract):
    schema_version: Version
    content_key: NonEmpty
    origin: Source
    language: NonEmpty | None = None
    duration_milliseconds: NonNegativeInt | None = None
    segments: list[TranscriptSegment]

    @model_validator(mode="after")
    def _segments(self):
        seen = set()
        last_start = None
        for segment in self.segments:
            if segment.id in seen:
                raise ValueError("Segment identities must be unique.")
            seen.add(segment.id)
            start = segment.start_milliseconds
            if start is not None:
                if last_start is not None and start < last_start:
                    raise ValueError("Segments must preserve chronological reading order.")
                last_start = start
            for time in (start, segment.end_milliseconds):
                if time is not None and self.duration_milliseconds is not None and time > self.duration_milliseconds:
                    raise ValueError("Segment exceeds transcript duration.")
        return self


class DocumentArtifactResult(Contract):
    markdown: str
    # The full upstream schema is validated by pinned Docling Core at extraction/reload.
    docling_json: dict[str, JsonValue]
    review: Review
    artifacts: DocumentArtifactRefs

    @model_validator(mode="after")
    def _document_review(self):
        if self.review.content_type != "document":
            raise ValueError("Document artifacts require a document review.")
        return self


class MediaArtifactResult(Contract):
    markdown: str
    transcript: Transcript
    review: Review
    artifacts: MediaArtifactRefs

    @model_validator(mode="after")
    def _matching_origin(self):
        if (self.review.content_type == "document" or self.review.content_key != self.transcript.content_key
                or self.review.source != self.transcript.origin):
            raise ValueError("Transcript and review must describe the same media content and origin.")
        return self


REVIEW_ADAPTER = TypeAdapter(Review)
TRANSCRIPT_ADAPTER = TypeAdapter(Transcript)


def parse_review(raw: str | bytes) -> Review:
    return validate_wire(REVIEW_ADAPTER, raw)


def parse_transcript(raw: str | bytes) -> Transcript:
    return validate_wire(TRANSCRIPT_ADAPTER, raw)
