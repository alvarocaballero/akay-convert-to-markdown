"""Build Markdown from a normalized transcription."""

from __future__ import annotations

from akay_convert_to_markdown.models.transcription import TranscriptionResult


def format_timestamp(seconds: float) -> str:
    """Format a timestamp as ``HH:MM:SS``."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_transcription_markdown(result: TranscriptionResult) -> str:
    """Render a transcription as Markdown with per-segment timestamps.

    Timestamps are preserved as section anchors so later RAG/chunking stages can
    link a section of the Markdown back to the exact media instant.
    """
    lines = ["# Transcripción", ""]
    for segment in result.segments:
        text = segment.text.strip()
        if not text:
            continue
        lines.append(f"## [{format_timestamp(segment.start_seconds)}]")
        lines.append("")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
