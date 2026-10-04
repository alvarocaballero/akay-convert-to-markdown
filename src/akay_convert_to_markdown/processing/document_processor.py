"""Orchestrates a single document conversion request.

``DocumentProcessor`` knows nothing about Service Bus message settlement. It
either returns a :class:`ProcessingResult` (complete) or raises a
:class:`TransientError` (abandon). The Service Bus consumer maps those outcomes
to the correct settlement call.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from akay_convert_to_markdown.config.settings import Settings
from akay_convert_to_markdown.conversion.document_converter import DocumentConverter
from akay_convert_to_markdown.errors.exceptions import (
    DocumentTooLargeError,
    PermanentError,
    WebhookError,
)
from akay_convert_to_markdown.logging import context_logger
from akay_convert_to_markdown.models.conversion_request import ConversionRequest, validate_extension
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.storage.blob_storage import BlobStorage


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def safe_source_filename(file_name: str) -> str:
    """Return a safe basename for the temporary source file.

    Strips any directory components (POSIX and Windows separators) and rejects
    unusable basenames so the result can never resolve to ``.``, ``..``, a
    parent directory or an absolute path. The extension is preserved so
    MarkItDown can infer the document type.
    """
    name = file_name.replace("\\", "/").rstrip("/").split("/")[-1]
    if name in ("", ".", ".."):
        name = "source"
    return name


class DocumentProcessor:
    """Coordinates validate -> download -> convert -> upload -> webhook."""

    def __init__(
        self,
        settings: Settings,
        storage: BlobStorage,
        converter: DocumentConverter,
        webhook: WebhookClient,
        logger: logging.Logger,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._converter = converter
        self._webhook = webhook
        self._logger = logger

    async def process(self, request: ConversionRequest) -> ProcessingResult:
        log = context_logger(
            self._logger,
            document_id=str(request.document_id),
            context_id=str(request.context_id),
            user_id=str(request.user_id),
            file_name=request.file_name,
            callback=request.callback,
        )
        started = time.perf_counter()
        try:
            self._validate_extension(request)
            blob_size = await self._storage.get_blob_size(
                self._settings.source_container_name,
                request.source_blob_name,
            )
            self._validate_size(blob_size)

            await self._convert_and_deliver(request, log)

            log.info("document.processing.completed", extra={"duration_ms": _elapsed_ms(started)})
            return ProcessingResult.COMPLETED
        except PermanentError as exc:
            log.error(
                "document.processing.failed",
                extra={"error_code": exc.code, "duration_ms": _elapsed_ms(started)},
            )
            await self._send_failed_webhook(request, exc, log)
            return ProcessingResult.FAILED_PERMANENT

    async def _convert_and_deliver(self, request: ConversionRequest, log: logging.LoggerAdapter) -> None:
        temp_dir = self._settings.temp_directory / str(request.document_id)
        source_path = temp_dir / safe_source_filename(request.file_name)
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            await self._download(request, source_path, log)
            markdown = await self._convert(request, source_path, log)
            await self._upload(request, markdown, temp_dir, log)
            await self._send_completed_webhook(request, log)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _download(self, request: ConversionRequest, source_path: Path, log: logging.LoggerAdapter) -> None:
        log.info("document.download.started")
        started = time.perf_counter()
        await self._storage.download_to_file(
            self._settings.source_container_name,
            request.source_blob_name,
            source_path,
        )
        log.info("document.download.completed", extra={"duration_ms": _elapsed_ms(started)})

    async def _convert(self, request: ConversionRequest, source_path: Path, log: logging.LoggerAdapter) -> str:
        log.info("document.conversion.started")
        started = time.perf_counter()
        markdown = await self._converter.convert(source_path)
        log.info("document.conversion.completed", extra={"duration_ms": _elapsed_ms(started)})
        return markdown

    async def _upload(
        self,
        request: ConversionRequest,
        markdown: str,
        temp_dir: Path,
        log: logging.LoggerAdapter,
    ) -> None:
        started = time.perf_counter()
        output_path = temp_dir / "document.md"
        output_path.write_text(markdown, encoding="utf-8")
        blob_name = self._output_blob_name(request)
        await self._storage.upload_file(self._settings.destination_container_name, blob_name, output_path)
        log.info(
            "document.upload.completed",
            extra={"duration_ms": _elapsed_ms(started), "blob_name": blob_name},
        )

    async def _send_completed_webhook(self, request: ConversionRequest, log: logging.LoggerAdapter) -> None:
        payload = {
            "eventType": "document.conversion.completed",
            "callback": request.callback,
            "documentId": str(request.document_id),
            "contextId": str(request.context_id),
            "userId": str(request.user_id),
            "fileName": request.file_name,
            "output": {
                "containerName": self._settings.destination_container_name,
                "blobName": self._output_blob_name(request),
            },
        }
        await self._notify(
            request.callback,
            payload,
            f"convert-to-markdown:{request.document_id}:completed",
            log,
        )

    async def _send_failed_webhook(
        self,
        request: ConversionRequest,
        exc: PermanentError,
        log: logging.LoggerAdapter,
    ) -> None:
        payload = {
            "eventType": "document.conversion.failed",
            "callback": request.callback,
            "documentId": str(request.document_id),
            "contextId": str(request.context_id),
            "userId": str(request.user_id),
            "fileName": request.file_name,
            "error": {"code": exc.code, "message": exc.message},
        }
        await self._notify(request.callback, payload, f"convert-to-markdown:{request.document_id}:failed", log)

    async def notify_invalid_message(self, identity: dict, log: logging.LoggerAdapter) -> None:
        """Send a ``document.conversion.failed`` webhook for an invalid message.

        Only sends when both the document identity and a configured callback are
        recoverable; otherwise it logs and returns so the consumer settles the
        poison message. Raises :class:`WebhookError` (transient) when the webhook
        cannot be delivered, so the consumer abandons the message.
        """
        callback = identity.get("callback")
        if callback is None or not self._webhook.is_configured(callback):
            log.error(
                "webhook.callback_not_configured",
                extra={"callback": callback, "reason": "cannot notify invalid message"},
            )
            return

        payload: dict = {
            "eventType": "document.conversion.failed",
            "callback": callback,
            "documentId": identity["documentId"],
        }
        for field in ("contextId", "userId", "fileName"):
            if identity.get(field) is not None:
                payload[field] = identity[field]
        payload["error"] = {
            "code": "INVALID_MESSAGE",
            "message": "Message has missing or invalid required fields.",
        }
        await self._notify(callback, payload, f"convert-to-markdown:{identity['documentId']}:failed", log)

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

    def _validate_extension(self, request: ConversionRequest) -> None:
        validate_extension(request.file_name)

    def _validate_size(self, blob_size: int) -> None:
        if blob_size > self._settings.max_document_size_bytes:
            raise DocumentTooLargeError(
                f"Document size {blob_size} bytes exceeds the maximum "
                f"of {self._settings.max_document_size_bytes} bytes."
            )

    def _output_blob_name(self, request: ConversionRequest) -> str:
        return f"{request.context_id}/{request.document_id}/document.md"
