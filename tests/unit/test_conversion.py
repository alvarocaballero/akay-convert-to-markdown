"""Document converter tests."""

from __future__ import annotations

import asyncio
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


@pytest.mark.parametrize("name", ["a.pdf", "a.docx", "a.pptx", "a.html", "a.htm", "a.txt", "a.md"])
async def test_conversion_for_supported_types(name):
    fake = FakeMarkItDown()
    converter = MarkItDownDocumentConverter(lambda: fake)
    result = await converter.convert(Path("source") / name)
    assert result == "# hello"


async def test_creates_a_new_instance_per_conversion():
    instances: list[FakeMarkItDown] = []

    def factory() -> FakeMarkItDown:
        instance = FakeMarkItDown()
        instances.append(instance)
        return instance

    converter = MarkItDownDocumentConverter(factory)
    await converter.convert(Path("a.pdf"))
    await converter.convert(Path("b.docx"))

    assert len(instances) == 2
    assert instances[0] is not instances[1]


async def test_converter_failure_raises_document_conversion_error():
    converter = MarkItDownDocumentConverter(lambda: FakeMarkItDown(error=RuntimeError("boom")))
    with pytest.raises(DocumentConversionError):
        await converter.convert(Path("a.pdf"))


async def test_empty_output_raises_document_conversion_error():
    converter = MarkItDownDocumentConverter(lambda: FakeMarkItDown(text=""))
    with pytest.raises(DocumentConversionError):
        await converter.convert(Path("a.pdf"))


async def test_concurrent_document_conversions():
    async def slow_convert(converter, source):
        return await converter.convert(source)

    converter = MarkItDownDocumentConverter(lambda: FakeMarkItDown())
    sources = [Path(f"doc-{i}.pdf") for i in range(20)]
    results = await asyncio.gather(*(slow_convert(converter, s) for s in sources))
    assert results == ["# hello"] * len(sources)


async def test_real_markitdown_converts_html(tmp_path):
    src = tmp_path / "sample.html"
    src.write_text("<html><body><h1>Title</h1><p>Hello</p></body></html>")
    converter = MarkItDownDocumentConverter()
    text = await converter.convert(src)
    assert "Title" in text
    assert "Hello" in text


async def test_real_markitdown_converts_md(tmp_path):
    src = tmp_path / "sample.md"
    src.write_text("# Heading\n\nSome **markdown**.")
    converter = MarkItDownDocumentConverter()
    text = await converter.convert(src)
    assert "Heading" in text
