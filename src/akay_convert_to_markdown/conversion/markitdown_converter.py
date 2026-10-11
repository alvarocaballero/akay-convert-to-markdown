"""Microsoft MarkItDown based converter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from markitdown import MarkItDown

from akay_convert_to_markdown.errors.exceptions import DocumentConversionError


class MarkItDownDocumentConverter:
    """Initial :class:`DocumentConverter` implementation backed by MarkItDown.

    MarkItDown is synchronous and not assumed to be thread-safe, so a fresh
    instance is created for every conversion and run in a worker thread via
    ``asyncio.to_thread``. This keeps the asyncio event loop responsive and
    avoids serializing independent document conversions behind a shared lock.
    """

    def __init__(self, factory: Callable[[], MarkItDown] | None = None) -> None:
        self._factory = factory or MarkItDown

    async def convert(self, source_path: Path) -> str:
        def _convert() -> str:
            markitdown = self._factory()
            try:
                result = markitdown.convert(str(source_path))
            except Exception as exc:
                raise DocumentConversionError(f"MarkItDown failed to convert the document: {exc}") from exc

            text = getattr(result, "text_content", None) or getattr(result, "markdown", None)
            if not text:
                raise DocumentConversionError("MarkItDown produced no Markdown output.")
            return text

        try:
            return await asyncio.to_thread(_convert)
        except DocumentConversionError:
            raise
        except Exception as exc:
            raise DocumentConversionError(f"Unexpected conversion error: {exc}") from exc
