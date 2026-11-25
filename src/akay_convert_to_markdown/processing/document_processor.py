"""Orchestrates a single content conversion request.

``DocumentProcessor`` knows nothing about Service Bus message settlement. It
either returns a :class:`ProcessingResult` (complete) or raises a
:class:`TransientError` (abandon). The Service Bus consumer maps those outcomes
to the correct settlement call.

It detects the content type and dispatches to the matching strategy:

* ``Document`` -> Docling;
* ``Audio``    -> Azure Fast Transcription;
* ``Video``    -> FFmpeg audio extraction + Fast Transcription.

Downloading, size/duration limits, timeout, temporary-file cleanup, Blob
upload and webhook delivery are shared across every strategy.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from akay_convert_to_markdown.config.settings import ConversionSettings
from akay_convert_to_markdown.conversion.document_converter import DocumentConverter
from akay_convert_to_markdown.errors.exceptions import (
    DocumentTooLargeError,
    PermanentError,
    ProcessingTimeoutError,
    UnsupportedContentTypeError,
    WebhookError,
)
from akay_convert_to_markdown.logging import context_logger
from akay_convert_to_markdown.models.content_type import ContentType, detect_content_type
from akay_convert_to_markdown.models.conversion_request import ConversionRequest, validate_extension
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from akay_convert_to_markdown.processing.blocking import drain_on_cancel

if TYPE_CHECKING:
    from akay_convert_to_markdown.processing.audio_processor import AudioProcessor
    from akay_convert_to_markdown.processing.video_processor import VideoProcessor


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def safe_source_filename(file_name: str) -> str:
    """Return a safe basename for the temporary source file.

    Strips any directory components (POSIX and Windows separators) and rejects
    unusable basenames so the result can never resolve to ``.``, ``..``, a
    parent directory or an absolute path. The extension is preserved so
    the document adapter can select the document type.
    """
    name = file_name.replace("\\", "/").rstrip("/").split("/")[-1]
    if name in ("", ".", ".."):
        name = "source"
    return name


class DocumentProcessor:
    """Coordinates detect -> download -> convert -> upload -> webhook."""

    def __init__(
        self,
        settings: ConversionSettings,
        storage: BlobStorage,
        converter: DocumentConverter | None,
        webhook: WebhookClient,
        logger: logging.Logger,
        *,
        audio_processor: AudioProcessor | None = None,
        video_processor: VideoProcessor | None = None,
        allowed_content_types: frozenset[ContentType] = frozenset(ContentType),
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._converter = converter
        self._webhook = webhook
        self._logger = logger
        self._audio_processor = audio_processor
        self._video_processor = video_processor
        self._allowed_content_types = allowed_content_types

    async def process(self, request: ConversionRequest) -> ProcessingResult:
        log = context_logger(
            self._logger,
            request_id=str(request.request_id),
            file_name=request.file_name,
            callback=request.callback,
        )
        started = time.perf_counter()
        execution_base, execution_dir = self._execution_directories(request)
        try:
            content_type = detect_content_type(
                file_name=request.file_name,
                explicit_type=request.content_type,
            )
            self._validate_input(request, content_type)

            if not request.overwrite_destination and await self._already_processed(request):
                log.info("document.already_processed", extra={"content_type": content_type.value})
                await self._send_completed_webhook(request, log)
                return ProcessingResult.COMPLETED

            blob_size = await self._storage.get_blob_size(
                self._settings.source_container_name,
                request.source.blob_name,
            )
            self._validate_size(blob_size)

            execution_dir.mkdir(parents=True, exist_ok=False)
            await self._convert_with_timeout(request, content_type, execution_dir, log)
            await self._send_completed_webhook(request, log)

            log.info(
                "document.processing.completed",
                extra={"duration_ms": _elapsed_ms(started), "content_type": content_type.value},
            )
            return ProcessingResult.COMPLETED
        except PermanentError as exc:
            log.error(
                "document.processing.failed",
                extra={
                    "error_code": exc.code,
                    "duration_ms": _elapsed_ms(started),
                },
            )
            await self._send_failed_webhook(request, exc, log)
            return ProcessingResult.FAILED_PERMANENT
        finally:
            await self._cleanup_execution_directory(execution_base, execution_dir)

    def _execution_directories(self, request: ConversionRequest) -> tuple[Path, Path]:
        """Return the ``(base, execution)`` temporary directories for a request.

        The base directory is shared by redeliveries of a request; each execution
        carries a random UUID so concurrent runs never share temporary files.
        """
        base = self._settings.temp_directory / str(request.request_id)
        return base, base / str(uuid4())

    async def _cleanup_execution_directory(self, base: Path, execution_dir: Path) -> None:
        """Remove the execution directory and prune empty parent directories.

        Runs on a worker thread so filesystem removal never blocks the event
        loop. The execution directory is always removed — success, error or
        cancellation — and the empty request directory is pruned without
        removing the configured temporary root.
        """
        if not execution_dir.exists() and not base.exists():
            return

        def _remove() -> None:
            shutil.rmtree(execution_dir, ignore_errors=True)
            parent = base
            stop = self._settings.temp_directory
            while parent != stop and parent != stop.parent:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent

        await drain_on_cancel(_remove)

    async def _convert_with_timeout(
        self,
        request: ConversionRequest,
        content_type: ContentType,
        execution_dir: Path,
        log: logging.LoggerAdapter,
    ) -> None:
        try:
            await asyncio.wait_for(
                self._convert_and_deliver(request, content_type, execution_dir, log),
                timeout=self._settings.process_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ProcessingTimeoutError(
                f"Processing exceeded {self._settings.process_timeout_minutes} minutes."
            ) from exc

    async def _convert_and_deliver(
        self,
        request: ConversionRequest,
        content_type: ContentType,
        execution_dir: Path,
        log: logging.LoggerAdapter,
    ) -> None:
        markdown = await self._to_markdown(request, content_type, execution_dir, log)
        await self._upload(request, markdown, execution_dir, log)

    async def _to_markdown(
        self,
        request: ConversionRequest,
        content_type: ContentType,
        execution_dir: Path,
        log: logging.LoggerAdapter,
    ) -> str:
        if content_type is ContentType.DOCUMENT:
            source_path = execution_dir / safe_source_filename(request.file_name)
            await self._download(request, source_path, log)
            return await self._convert(request, source_path, log)

        if content_type is ContentType.AUDIO:
            source_path = execution_dir / safe_source_filename(request.file_name)
            await self._download(request, source_path, log)
            return await self._require_audio().to_markdown(request, source_path, execution_dir, log)

        if content_type is ContentType.VIDEO:
            source_path = execution_dir / safe_source_filename(request.file_name)
            await self._download(request, source_path, log)
            return await self._require_video().to_markdown(request, source_path, execution_dir, log)

        raise UnsupportedContentTypeError(f"Unsupported content type '{content_type.value}'.")

    def _require_audio(self) -> AudioProcessor:
        if self._audio_processor is None:
            raise UnsupportedContentTypeError("Audio processing is not available.")
        return self._audio_processor

    def _require_video(self) -> VideoProcessor:
        if self._video_processor is None:
            raise UnsupportedContentTypeError("Video processing is not available.")
        return self._video_processor

    async def _download(self, request: ConversionRequest, source_path: Path, log: logging.LoggerAdapter) -> None:
        log.info("document.download.started")
        started = time.perf_counter()
        await self._storage.download_to_file(
            self._settings.source_container_name,
            request.source.blob_name,
            source_path,
        )
        log.info("document.download.completed", extra={"duration_ms": _elapsed_ms(started)})

    async def _convert(self, request: ConversionRequest, source_path: Path, log: logging.LoggerAdapter) -> str:
        log.info("document.conversion.started")
        started = time.perf_counter()
        if self._converter is None:
            raise UnsupportedContentTypeError("Document processing is not available.")
        markdown = await self._converter.convert(source_path)
        log.info("document.conversion.completed", extra={"duration_ms": _elapsed_ms(started)})
        return markdown

    async def _upload(
        self,
        request: ConversionRequest,
        markdown: str,
        execution_dir: Path,
        log: logging.LoggerAdapter,
    ) -> None:
        started = time.perf_counter()
        output_path = execution_dir / "document.md"
        await drain_on_cancel(lambda: output_path.write_text(markdown, encoding="utf-8"))
        blob_name = self._output_blob_name(request)
        await self._storage.upload_file(self._settings.destination_container_name, blob_name, output_path,
                                        overwrite=request.overwrite_destination)
        log.info(
            "document.upload.completed",
            extra={"duration_ms": _elapsed_ms(started), "blob_name": blob_name},
        )

    async def _already_processed(self, request: ConversionRequest) -> bool:
        blob_name = self._output_blob_name(request)
        return await self._storage.blob_exists(self._settings.destination_container_name, blob_name)

    async def _send_completed_webhook(self, request: ConversionRequest, log: logging.LoggerAdapter) -> None:
        payload = self._webhook_payload(request, "document.conversion.completed")
        await self._notify(
            request.callback,
            payload,
            f"convert-to-markdown:{request.request_id}:completed",
            log,
        )

    async def _send_failed_webhook(
        self,
        request: ConversionRequest,
        exc: PermanentError,
        log: logging.LoggerAdapter,
    ) -> None:
        payload = self._webhook_payload(request, "document.conversion.failed")
        payload["error"] = {"code": exc.code, "message": exc.message}
        await self._notify(request.callback, payload, f"convert-to-markdown:{request.request_id}:failed", log)

    def _webhook_payload(self, request: ConversionRequest, event_type: str) -> dict:
        content_type = detect_content_type(file_name=request.file_name, explicit_type=request.content_type)
        return {
            "eventType": event_type,
            "requestId": str(request.request_id),
            "source": request.source.model_dump(by_alias=True),
            "destinationBlobName": request.destination_blob_name,
            "contentType": content_type.value,
            "payload": request.payload,
        }

    async def notify_invalid_message(self, identity: dict, log: logging.LoggerAdapter) -> None:
        """Send a ``document.conversion.failed`` webhook for an invalid message.

        Only sends when both the request identity and a configured callback are
        recoverable; otherwise it logs and returns so the consumer settles the
        poison message. Raises :class:`WebhookError` (transient) when the webhook
        cannot be delivered, so the consumer abandons the message.
        """
        callback = identity.get("callback")
        if not isinstance(callback, str) or not self._webhook.is_configured(callback):
            log.error(
                "webhook.callback_not_configured",
                extra={"callback": callback, "reason": "cannot notify invalid message"},
            )
            return

        payload: dict = {
            "eventType": "document.conversion.failed",
            "requestId": identity["requestId"],
        }
        for field in ("source", "destinationBlobName", "contentType", "payload", "operation"):
            if identity.get(field) is not None:
                payload[field] = identity[field]
        payload["error"] = {
            "code": "INVALID_MESSAGE",
            "message": "Message has missing or invalid required fields.",
        }
        await self._notify(callback, payload, f"convert-to-markdown:{identity['requestId']}:failed", log)

    async def _notify(
        self,
        callback: str,
        payload: dict,
        idempotency_key: str,
        log: logging.LoggerAdapter,
    ) -> None:
        started = time.perf_counter()
        try:
            await self._webhook.send(callback, payload, idempotency_key)
        except WebhookError:
            log.error(
                "webhook.failed",
                extra={"idempotency_key": idempotency_key, "duration_ms": _elapsed_ms(started)},
            )
            raise
        log.info(
            "webhook.completed",
            extra={"idempotency_key": idempotency_key, "duration_ms": _elapsed_ms(started)},
        )

    def _validate_input(self, request: ConversionRequest, content_type: ContentType) -> None:
        if content_type not in self._allowed_content_types:
            raise UnsupportedContentTypeError("Content type is not supported by this worker.")
        if content_type is ContentType.DOCUMENT:
            validate_extension(request.file_name)

    def _validate_size(self, blob_size: int) -> None:
        if blob_size > self._settings.max_input_size_bytes:
            raise DocumentTooLargeError(
                f"Input size {blob_size} bytes exceeds the maximum "
                f"of {self._settings.max_input_size_bytes} bytes."
            )

    def _output_blob_name(self, request: ConversionRequest) -> str:
        return request.destination_blob_name
