"""Blob/YouTube media through existing strategies and the complete-set publisher."""

from __future__ import annotations

import asyncio
import json
from pathlib import PurePosixPath

from akay_convert_to_markdown.contracts.events import idempotency_key, request_failed
from akay_convert_to_markdown.contracts.artifacts import YouTubeMetadata
from akay_convert_to_markdown.contracts.requests import BlobSource, MediaRequest, parse_request
from akay_convert_to_markdown.errors.exceptions import (
    BlobStorageError, MediaTooLongError, PermanentError, ProcessingTimeoutError, UnsupportedContentTypeError,
)
from akay_convert_to_markdown.models.content_type import ContentType, detect_content_type
from akay_convert_to_markdown.models.conversion_request import parse_conversion_request
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor, safe_source_filename
from akay_convert_to_markdown.processing.media_artifacts import export_media_artifacts
from akay_convert_to_markdown.storage.artifact_publication import ArtifactPackage


class PublishedMediaProcessor(DocumentProcessor):
    def __init__(self, *args, youtube_service=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._youtube = youtube_service

    def parse_message(self, raw):
        try:
            fields = json.loads(raw)
        except (ValueError, TypeError, UnicodeDecodeError):
            return parse_conversion_request(raw)
        if isinstance(fields, dict) and any(key in fields for key in ("schemaVersion", "schema_version", "contentKey",
                                                                      "content_key", "documentOptions", "document_options")):
            return parse_request(raw, worker="media", callbacks=self._settings.webhook_callbacks)
        return parse_conversion_request(raw)

    async def process(self, request):
        if not isinstance(request, MediaRequest):
            return await super().process(request)
        request = MediaRequest.model_validate_json(request.model_dump_json())
        base, execution = self._execution_directories(request)

        async def build():
            async def transcribe_package():
                if (isinstance(request.source, BlobSource)
                        and detect_content_type(file_name=request.source.blob_name) is ContentType.DOCUMENT):
                    raise UnsupportedContentTypeError("The media source must use a supported audio/video extension.")
                execution.mkdir(parents=True, exist_ok=False)
                youtube = None
                if isinstance(request.source, BlobSource):
                    size = await self._storage.get_blob_size(self._settings.source_container_name, request.source.blob_name)
                    self._validate_size(size)
                    source = execution / safe_source_filename(request.source.blob_name)
                    await self._storage.download_to_file(self._settings.source_container_name, request.source.blob_name, source)
                else:
                    if self._youtube is None:
                        raise BlobStorageError("The YouTube source adapter is not configured.")
                    source, metadata = await self._youtube.download(request.source, execution / "youtube")
                    youtube = YouTubeMetadata(**metadata)
                self._validate_size(source.stat().st_size)
                strategy = self._require_audio() if request.content_type == "audio" else self._require_video()
                result = await strategy.transcribe(source, execution)
                if (result.duration_milliseconds is not None
                        and result.duration_milliseconds > self._settings.max_media_duration_seconds * 1000):
                    raise MediaTooLongError("The measured media duration exceeds the configured limit.")
                output = execution / "package"
                bundle = await export_media_artifacts(result, request, output, api_version=self._settings.speech_api_version,
                                                      youtube=youtube)
                parent = PurePosixPath(request.destination_blob_name).parent
                names = (request.destination_blob_name, bundle.artifacts.transcript_json_blob_name,
                         bundle.artifacts.review_blob_name)
                return ArtifactPackage(files={name: output.joinpath(*PurePosixPath(name).relative_to(parent).parts)
                                              for name in names})

            try:
                return await asyncio.wait_for(transcribe_package(), timeout=self._settings.process_timeout_seconds)
            except TimeoutError:
                raise ProcessingTimeoutError("Media processing exceeded its time budget.") from None

        try:
            container, prefix = self._settings.publication_state_container_name, self._settings.publication_state_prefix
            if not container or not prefix:
                raise BlobStorageError("Version-one media publication requires explicit technical storage configuration.")
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
