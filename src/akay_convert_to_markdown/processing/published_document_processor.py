"""Artifact-capable document path; retain the existing legacy processing path."""

from __future__ import annotations

import asyncio
import json
from pathlib import PurePosixPath

from akay_convert_to_markdown.contracts.events import idempotency_key, request_failed
from akay_convert_to_markdown.contracts.requests import DocumentRequest, parse_request
from akay_convert_to_markdown.errors.exceptions import BlobStorageError, PermanentError, ProcessingTimeoutError, SourceBlobNotFoundError
from akay_convert_to_markdown.models.conversion_request import parse_conversion_request, validate_extension
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor, safe_source_filename
from akay_convert_to_markdown.storage.artifact_publication import ArtifactPackage
from akay_convert_to_markdown.processing.blocking import drain_on_cancel


class PublishedDocumentProcessor(DocumentProcessor):
    def parse_message(self, raw):
        try:
            fields = json.loads(raw)
        except (ValueError, TypeError, UnicodeDecodeError):
            return parse_conversion_request(raw)
        if isinstance(fields, dict) and any(key in fields for key in ("schemaVersion", "schema_version", "contentKey",
                                                                      "content_key", "documentOptions", "document_options",
                                                                      "operation", "extractionReviewBlobName", "extraction_review_blob_name")):
            return parse_request(raw, worker="document", callbacks=self._settings.webhook_callbacks)
        return parse_conversion_request(raw)

    async def process(self, request):
        if not isinstance(request, DocumentRequest):
            return await super().process(request)
        container = getattr(self._settings, "publication_state_container_name", None)
        prefix = getattr(self._settings, "publication_state_prefix", None)
        if not container or not prefix:
            raise BlobStorageError("Version-one document publication requires explicit technical storage configuration.")
        # Snapshot nested options/payload before any asynchronous work.
        request = DocumentRequest.model_validate_json(request.model_dump_json())
        base, execution = self._execution_directories(request)

        async def build():
            # Heavy document imports remain private to this document job path.
            from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts

            async def extract_package():
                validate_extension(request.source.blob_name)
                size = await self._storage.get_blob_size(self._settings.source_container_name, request.source.blob_name)
                self._validate_size(size)
                execution.mkdir(parents=True, exist_ok=False)
                source = execution / safe_source_filename(request.source.blob_name)
                await self._storage.download_to_file(self._settings.source_container_name, request.source.blob_name, source)
                self._validate_size(source.stat().st_size)
                output = execution / "package"
                if request.operation == "rebuildFromMarkdown":
                    from akay_convert_to_markdown.conversion.markdown_rebuild import rebuild_document_artifacts

                    from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout, parse_review

                    review_name = ArtifactLayout.for_destination(request.source.blob_name).document_refs().review_blob_name
                    review_path = execution / "current-review.json"
                    try:
                        size = await self._storage.get_blob_size(self._settings.destination_container_name, review_name)
                        self._validate_size(size)
                        await self._storage.download_to_file(self._settings.destination_container_name, review_name, review_path)
                        self._validate_size(review_path.stat().st_size)
                    except SourceBlobNotFoundError:
                        review_raw = None
                    else:
                        review_raw = await drain_on_cancel(review_path.read_bytes)
                    raw = await drain_on_cancel(source.read_bytes)
                    result = await rebuild_document_artifacts(raw, review_raw, request, output)
                else:
                    extraction = await self._converter.extract(source, request.document_options)
                    result = await export_document_artifacts(extraction, request, output)
                # Inventory comes from the verified exporter, not a Blob listing
                # or consumer-supplied payload paths. No original is copied.
                parent = PurePosixPath(request.artifact_markdown_blob_name).parent
                names = [result.artifacts.docling_json_blob_name, result.artifacts.review_blob_name]
                if request.operation == "convert":
                    names.insert(0, request.destination_blob_name)
                    names.extend(image.blob_name for image in result.review.images)
                retained = tuple(image.blob_name for image in result.review.images) if request.operation == "rebuildFromMarkdown" else ()
                previous = parse_review(review_raw).images if request.operation == "rebuildFromMarkdown" and review_raw else []
                return ArtifactPackage(files={name: output.joinpath(*PurePosixPath(name).relative_to(parent).parts)
                                              for name in names}, retained_images=retained,
                                       removed_images=tuple(image.blob_name for image in previous if image.blob_name not in retained))

            try:
                return await asyncio.wait_for(extract_package(), timeout=self._settings.process_timeout_seconds)
            except TimeoutError:
                raise ProcessingTimeoutError("Document processing exceeded its time budget.") from None

        try:
            publisher = self._storage.artifact_publisher(destination_container=self._settings.destination_container_name,
                                                         source_container=self._settings.source_container_name,
                                                         state_container=container, state_prefix=prefix)
            return await publisher.deliver(request, build, self._webhook.send)
        except PermanentError as exc:
            event = request_failed(request, code=exc.code, message=exc.message)
            await self._webhook.send(request.callback, event.model_dump(mode="json", by_alias=True), idempotency_key(event))
            return ProcessingResult.FAILED_PERMANENT
        finally:
            await self._cleanup_execution_directory(base, execution)
