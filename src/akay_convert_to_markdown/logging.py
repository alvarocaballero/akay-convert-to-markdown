"""Structured, secret-safe JSON logging."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

# Fields rendered in the JSON output when present on the log record.
_LOG_FIELDS = (
    "document_id",
    "context_id",
    "user_id",
    "file_name",
    "callback",
    "delivery_count",
    "duration_ms",
    "attempt",
    "status_code",
    "error_code",
    "idempotency_key",
    "blob_name",
    "reason",
    "log_level",
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in _LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that merges fixed context into every record."""

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        extra = dict(kwargs.get("extra") or {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(level: str) -> None:
    """Configure the root logger with the JSON formatter and level."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def context_logger(logger: logging.Logger, **fields: Any) -> logging.LoggerAdapter:
    """Return a logger adapter bound to the given structured fields."""
    return ContextLoggerAdapter(logger, {key: value for key, value in fields.items() if value is not None})
