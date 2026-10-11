"""Markdown builder tests."""

from __future__ import annotations

from akay_convert_to_markdown.models.transcription import TranscriptionResult, TranscriptionSegment
from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown, format_timestamp


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(12.9) == "00:00:12"
    assert format_timestamp(227.0) == "00:03:47"
    assert format_timestamp(3661.0) == "01:01:01"


def test_build_markdown_preserves_segment_timestamps():
    result = TranscriptionResult(
        text="Intro. Now the second law.",
        segments=[
            TranscriptionSegment(start_seconds=12.0, duration_seconds=3.0, text="Intro."),
            TranscriptionSegment(start_seconds=227.0, duration_seconds=5.0, text="Now the second law."),
        ],
    )

    markdown = build_transcription_markdown(result)

    assert markdown.startswith("# Transcripción\n")
    assert "## [00:00:12]" in markdown
    assert "## [00:03:47]" in markdown
    assert "Intro." in markdown
    assert "Now the second law." in markdown


def test_build_markdown_skips_empty_segments():
    result = TranscriptionResult(
        text="Only text",
        segments=[
            TranscriptionSegment(start_seconds=1.0, duration_seconds=1.0, text="   "),
            TranscriptionSegment(start_seconds=2.0, duration_seconds=1.0, text="Only text"),
        ],
    )

    markdown = build_transcription_markdown(result)

    assert markdown.count("## [") == 1
    assert "## [00:00:02]" in markdown


def test_build_markdown_without_segments_is_header_only():
    result = TranscriptionResult(text="", segments=[])

    assert build_transcription_markdown(result) == "# Transcripción\n"
