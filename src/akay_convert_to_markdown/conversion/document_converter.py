"""Conversion abstraction.

``MarkItDown`` stays behind this interface so another converter can replace it
without changing the processing workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DocumentConverter(Protocol):
    """Convert a local document into Markdown text."""

    async def convert(self, source_path: Path) -> str:
        ...
