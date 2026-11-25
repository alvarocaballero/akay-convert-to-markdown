"""Typed webhook bodies and pure builders. No notification or processing side effects."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, JsonValue, TypeAdapter, model_validator, model_serializer

from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout, DocumentArtifactRefs, MediaArtifactRefs
from akay_convert_to_markdown.contracts.base import (
    BlobName, Contract, MarkdownDestination, NonEmpty, NonNegativeInt, PositiveInt, Uuid, Version, validate_wire,
)
from akay_convert_to_markdown.contracts.requests import (
    BlobSource, DeleteRequest, DocumentRequest, IndexRequest, MediaRequest, Request, Source,
)


class Event(Contract):
    schema_version: Version
    request_id: Uuid
    content_key: NonEmpty
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ConversionCompleted(Event):
    event_type: Literal["document.conversion.completed"]
    destination_blob_name: MarkdownDestination

    @model_validator(mode="after")
    def _matching_artifact_layout(self):
        layout = ArtifactLayout.for_destination(self.destination_blob_name)
        expected = layout.document_refs() if self.content_type == "document" else layout.media_refs()
        if self.artifacts != expected:
            raise ValueError("Artifacts do not belong to the Markdown destination.")
        return self


class DocumentCompleted(ConversionCompleted):
    operation: Literal["convert", "rebuildFromMarkdown"] = "convert"
    source: BlobSource
    content_type: Literal["document"]
    artifacts: DocumentArtifactRefs


class MediaCompleted(ConversionCompleted):
    source: Source
    content_type: Literal["audio", "video"]
    artifacts: MediaArtifactRefs

    @model_validator(mode="after")
    def _source_type(self):
        if self.source.type == "youtube" and self.content_type != "video":
            raise ValueError("YouTube results must have video content type.")
        return self


class SafeError(Contract):
    code: NonEmpty
    message: NonEmpty


class Failure(Contract):
    schema_version: Version
    request_id: Uuid
    content_key: NonEmpty | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    error: SafeError


class ConversionFailed(Failure):
    event_type: Literal["document.conversion.failed"]
    source: Source | None = None
    destination_blob_name: BlobName | None = None
    content_type: Literal["document", "audio", "video"] | None = None
    operation: Literal["convert", "rebuildFromMarkdown"] | None = None

    @model_serializer(mode="wrap")
    def _document_operation_only(self, handler):
        data = handler(self)
        if self.operation is None:
            data.pop("operation", None)
        return data

    @model_validator(mode="after")
    def _operation_type(self):
        if self.operation is not None and self.content_type in {"audio", "video"}:
            raise ValueError("Document operations are not media operations.")
        return self


class IndexEvent(Event):
    scope_key: NonEmpty
    operation_sequence: PositiveInt


class IndexReport(Contract):
    profile_id: NonEmpty
    chunk_count: NonNegativeInt


class DeleteReport(Contract):
    profile_id: NonEmpty


class IndexCompleted(IndexEvent):
    event_type: Literal["content.indexing.completed"]
    index: IndexReport


class IndexDeleted(IndexEvent):
    event_type: Literal["content.index.deleted"]
    index: DeleteReport


class IndexSuperseded(IndexEvent):
    event_type: Literal["content.index.operation.superseded"]
    current_operation_sequence: PositiveInt

    @model_validator(mode="after")
    def _newer_operation(self):
        if self.current_operation_sequence <= self.operation_sequence:
            raise ValueError("A superseding operation must be newer.")
        return self


class IndexFailed(Failure):
    event_type: Literal["content.indexing.failed"]
    operation: Literal["index"] | None = None
    scope_key: NonEmpty | None = None
    operation_sequence: PositiveInt | None = None


class DeleteFailed(Failure):
    event_type: Literal["content.index.deletion.failed"]
    operation: Literal["delete"] | None = None
    scope_key: NonEmpty | None = None
    operation_sequence: PositiveInt | None = None


CompletedConversion = Annotated[DocumentCompleted | MediaCompleted, Field(discriminator="content_type")]
WebhookEvent = Annotated[CompletedConversion | ConversionFailed | IndexCompleted | IndexDeleted | IndexSuperseded
                         | IndexFailed | DeleteFailed, Field(discriminator="event_type")]
EVENT_ADAPTER = TypeAdapter(WebhookEvent)


def parse_event(raw: str | bytes) -> WebhookEvent:
    return validate_wire(EVENT_ADAPTER, raw)


def _identity(request: Request) -> dict:
    return {"schema_version": request.schema_version, "request_id": request.request_id,
            "content_key": request.content_key, "payload": request.payload}


def conversion_completed(request: DocumentRequest | MediaRequest,
                         artifacts: DocumentArtifactRefs | MediaArtifactRefs) -> DocumentCompleted | MediaCompleted:
    model = DocumentCompleted if isinstance(request, DocumentRequest) else MediaCompleted
    fields = {"operation": request.operation} if isinstance(request, DocumentRequest) else {}
    return model(**_identity(request), **fields, event_type="document.conversion.completed", source=request.source,
                 destination_blob_name=(request.artifact_markdown_blob_name if isinstance(request, DocumentRequest)
                                        else request.destination_blob_name), content_type=request.content_type, artifacts=artifacts)


def index_completed(request: IndexRequest | DeleteRequest, *, chunk_count: int | None = None) -> IndexCompleted | IndexDeleted:
    fields = dict(**_identity(request), scope_key=request.scope_key, operation_sequence=request.operation_sequence)
    if isinstance(request, IndexRequest):
        return IndexCompleted(**fields, event_type="content.indexing.completed",
                              index=IndexReport(profile_id=request.index_profile.id, chunk_count=chunk_count))
    if chunk_count is not None:
        raise ValueError("A deletion result does not report a chunk count.")
    return IndexDeleted(**fields, event_type="content.index.deleted", index=DeleteReport(profile_id=request.index_target.profile_id))


def index_superseded(request: IndexRequest | DeleteRequest, *, current_operation_sequence: int) -> IndexSuperseded:
    return IndexSuperseded(**_identity(request), event_type="content.index.operation.superseded", scope_key=request.scope_key,
                           operation_sequence=request.operation_sequence, current_operation_sequence=current_operation_sequence)


def request_failed(request: DocumentRequest | MediaRequest | IndexRequest | DeleteRequest, *, code: str,
                   message: str) -> ConversionFailed | IndexFailed | DeleteFailed:
    # Only caller-selected, safe messages belong here, never str(exception).
    fields = dict(**_identity(request), error=SafeError(code=code, message=message))
    if isinstance(request, (DocumentRequest, MediaRequest)):
        if isinstance(request, DocumentRequest):
            fields["operation"] = request.operation
        return ConversionFailed(**fields, event_type="document.conversion.failed", source=request.source,
                                destination_blob_name=(request.artifact_markdown_blob_name if isinstance(request, DocumentRequest)
                                                       else request.destination_blob_name), content_type=request.content_type)
    model = IndexFailed if isinstance(request, IndexRequest) else DeleteFailed
    event_type = "content.indexing.failed" if isinstance(request, IndexRequest) else "content.index.deletion.failed"
    return model(**fields, event_type=event_type, operation=request.operation, scope_key=request.scope_key,
                 operation_sequence=request.operation_sequence)


def idempotency_key(event: WebhookEvent) -> str:
    return f"{event.request_id}:{event.event_type}"
