"""Document converter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from akay_convert_to_markdown.conversion.markitdown_converter import MarkItDownDocumentConverter
from akay_convert_to_markdown.errors.exceptions import DocumentConversionError


class FakeMarkItDown:
    def __init__(self, text: str = "# hello", error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.last_source = None

    def convert(self, source: str):
        self.last_source = source
        if self._error:
            raise self._error
        return type("Result", (), {"text_content": self._text})()


@pytest.mark.parametrize("name", ["a.pdf", "a.docx", "a.pptx", "a.html", "a.htm"])
async def test_conversion_for_supported_types(name):
    fake = FakeMarkItDown()
    converter = MarkItDownDocumentConverter(fake)
    result = await converter.convert(Path("source") / name)
    assert result == "# hello"


async def test_converter_failure_raises_document_conversion_error():
    converter = MarkItDownDocumentConverter(FakeMarkItDown(error=RuntimeError("boom")))
    with pytest.raises(DocumentConversionError):
        await converter.convert(Path("a.pdf"))


async def test_empty_output_raises_document_conversion_error():
    converter = MarkItDownDocumentConverter(FakeMarkItDown(text=""))
    with pytest.raises(DocumentConversionError):
        await converter.convert(Path("a.pdf"))


async def test_real_markitdown_converts_html(tmp_path):
    src = tmp_path / "sample.html"
    src.write_text("<html><body><h1>Title</h1><p>Hello</p></body></html>")
    converter = MarkItDownDocumentConverter()
    text = await converter.convert(src)
    assert "Title" in text
    assert "Hello" in text
