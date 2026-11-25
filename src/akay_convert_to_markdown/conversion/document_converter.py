"""Conversion abstraction.

The document extraction engine stays behind this interface. Rich Docling
extraction is available separately for the version-one artifact pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DocumentConverter(Protocol):
    """Convert a local document into Markdown text."""

    async def convert(self, source_path: Path) -> str:
        ...
