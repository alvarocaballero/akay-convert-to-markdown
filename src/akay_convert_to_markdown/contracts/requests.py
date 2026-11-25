"""Document, media and index/delete inputs. No provider or service is loaded."""

from __future__ import annotations

from collections.abc import Collection
from typing import Annotated, Literal

from pydantic import Field, JsonValue, TypeAdapter, field_validator, model_validator, model_serializer

from akay_convert_to_markdown.contracts.base import (
    BlobName, Contract, MarkdownDestination, NonEmpty, PositiveInt, Uuid, Version, validate_wire,
)
from akay_convert_to_markdown.errors.exceptions import InvalidMessageError
from akay_convert_to_markdown.models.youtube import video_identity


class BlobSource(Contract):
    type: Literal["blob"]
    blob_name: BlobName


class YouTubeSource(Contract):
    type: Literal["youtube"]
    url: NonEmpty

    @field_validator("url")
    @classmethod
    def _youtube_url(cls, value: str) -> str:
        video_identity(value)
        return value


Source = Annotated[BlobSource | YouTubeSource, Field(discriminator="type")]


class Request(Contract):
    schema_version: Version
    request_id: Uuid
    content_key: NonEmpty
    callback: NonEmpty
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("callback")
    @classmethod
    def _callback_identity(cls, value: str) -> str:
        if "://" in value or value.startswith(("/", "\\")):
            raise ValueError("Callback must be a configured identity, not a URL.")
        return value


class DocumentOptions(Contract):
    extract_sections: bool = False
    code_enrichment: bool = False
    formula_enrichment: bool = False
    ocr_language: Literal["es", "eu", "gl", "ca", "fr", "en", "de"] = "es"


class ConversionRequest(Request):
    destination_blob_name: MarkdownDestination
    overwrite_destination: bool = False


class DocumentRequest(ConversionRequest):
    destination_blob_name: MarkdownDestination | None = None
    operation: Literal["convert", "rebuildFromMarkdown"] = "convert"
    extraction_review_blob_name: BlobName | None = None
    source: BlobSource
    content_type: Literal["document"]
    document_options: DocumentOptions = Field(default_factory=DocumentOptions)

    @model_validator(mode="after")
    def _document_operation(self):
        if self.operation == "convert":
            if self.destination_blob_name is None:
                raise ValueError("Conversion requires a Markdown destination.")
            if self.extraction_review_blob_name is not None:
                raise ValueError("Extraction review is only accepted for reconstruction.")
            return self
        if not self.source.blob_name.lower().endswith(".md"):
            raise ValueError("Reconstruction requires frozen Markdown.")
        # The edited Markdown supplies the artifact namespace, but is never an output.
        from akay_convert_to_markdown.contracts.base import markdown_destination

        markdown_destination(self.source.blob_name)
        if self.destination_blob_name is not None or self.extraction_review_blob_name is not None:
            raise ValueError("Artifact reconstruction uses only the source Markdown; omit destination and extraction review.")
        if self.document_options.code_enrichment or self.document_options.formula_enrichment:
            raise ValueError("Reconstruction does not allow model enrichment.")
        return self

    @property
    def artifact_markdown_blob_name(self) -> str:
        """Naming anchor and callback reference, not necessarily a file to write."""
        return self.source.blob_name if self.operation == "rebuildFromMarkdown" else self.destination_blob_name

    @model_serializer(mode="wrap")
    def _artifact_only_request(self, handler):
        data = handler(self)
        if self.operation == "rebuildFromMarkdown":
            for field in ("destinationBlobName", "destination_blob_name", "extractionReviewBlobName", "extraction_review_blob_name"):
                if data.get(field) is None:
                    data.pop(field, None)
        return data


class MediaRequest(ConversionRequest):
    source: Source
    content_type: Literal["audio", "video"]

    @model_validator(mode="after")
    def _youtube_is_video(self):
        if isinstance(self.source, YouTubeSource) and self.content_type != "video":
            raise ValueError("YouTube is a video source, not an audio content type.")
        return self


class IndexSource(BlobSource):
    format: Literal["docling", "transcript"]


class FixedSection(Contract):
    mode: Literal["fixed"]
    section_id: Uuid
    heading_path: list[NonEmpty]


class ReviewSections(Contract):
    mode: Literal["fromReview"]
    review_blob_name: BlobName


class NoSection(Contract):
    mode: Literal["none"]


SectionContext = Annotated[FixedSection | ReviewSections | NoSection, Field(discriminator="mode")]


class IndexProfile(Contract):
    id: NonEmpty
    provider: NonEmpty
    model: NonEmpty
    model_revision: NonEmpty | None = None
    deployment: NonEmpty | None = None
    dimensions: PositiveInt
    tokenizer: NonEmpty
    max_chunk_tokens: PositiveInt
    distance: Literal["Cosine", "Dot", "Euclid", "Manhattan"]
    collection: NonEmpty


class IndexTarget(Contract):
    profile_id: NonEmpty
    collection: NonEmpty


class IndexOperation(Request):
    operation_sequence: PositiveInt
    scope_key: NonEmpty


RESERVED_METADATA = frozenset({"scopeKey", "contentKey", "profileId", "operationSequence", "chunkIndex", "sectionId",
                               "headingPath", "text", "contextualizedText", "source", "provenance", "metadata"})


class IndexRequest(IndexOperation):
    operation: Literal["index"]
    source: IndexSource
    section_context: SectionContext
    index_profile: IndexProfile
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _reserved_metadata(cls, value: dict) -> dict:
        if RESERVED_METADATA.intersection(value):
            raise ValueError("Metadata cannot override reserved index fields.")
        return value

    @model_validator(mode="after")
    def _review_requires_docling(self):
        if self.source.format == "transcript" and self.section_context.mode == "fromReview":
            raise ValueError("Review-based sections require a Docling source.")
        return self


class DeleteRequest(IndexOperation):
    operation: Literal["delete"]
    index_target: IndexTarget


IndexJob = Annotated[IndexRequest | DeleteRequest, Field(discriminator="operation")]
REQUEST_ADAPTERS = {"document": TypeAdapter(DocumentRequest), "media": TypeAdapter(MediaRequest),
                    "index": TypeAdapter(IndexJob)}


def parse_request(raw: str | bytes, *, worker: Literal["document", "media", "index"],
                  callbacks: Collection[str]) -> DocumentRequest | MediaRequest | IndexRequest | DeleteRequest:
    request = validate_wire(REQUEST_ADAPTERS[worker], raw)
    if request.callback not in callbacks:
        raise InvalidMessageError("Message has an invalid callback identity.")
    return request
