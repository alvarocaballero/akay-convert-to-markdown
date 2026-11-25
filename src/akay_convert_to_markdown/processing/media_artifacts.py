"""Produce one coherent local media package from already transcribed phrases."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from akay_convert_to_markdown.contracts.artifacts import (
    ArtifactLayout, MediaArtifactResult, Processing, Review, ReviewSummary, Transcript, TranscriptSegment, Warning, YouTubeMetadata,
)
from akay_convert_to_markdown.contracts.requests import MediaRequest
from akay_convert_to_markdown.errors.exceptions import SpeechTranscriptionError
from akay_convert_to_markdown.models.transcription import TranscriptionResult
from akay_convert_to_markdown.processing.blocking import drain_on_cancel
from akay_convert_to_markdown.services.markdown_builder import build_transcription_markdown


async def export_media_artifacts(result: TranscriptionResult, request: MediaRequest, output_directory: Path,
                                 *, api_version: str, youtube: YouTubeMetadata | None = None) -> MediaArtifactResult:
    """Use a fresh attempt directory; the shared publisher owns remote atomicity."""
    def export():
        segments = []
        for segment in result.segments:
            if not segment.text.strip():
                continue
            start, duration = segment.start_seconds, segment.duration_seconds
            segments.append(TranscriptSegment(id=f"segment-{len(segments) + 1:04d}", text=segment.text.strip(),
                                               start_milliseconds=None if start is None else round(start * 1000),
                                               end_milliseconds=None if start is None or duration is None else round((start + duration) * 1000),
                                               speaker=segment.speaker, language=segment.language))
        if not segments:
            raise SpeechTranscriptionError("The media contains no transcribed phrases.")
        transcript = Transcript(schema_version=1, content_key=request.content_key, origin=request.source,
                                language=result.language, duration_milliseconds=result.duration_milliseconds,
                                segments=segments)
        warnings = list(result.warnings)
        if any(segment.start_milliseconds is None or segment.end_milliseconds is None for segment in segments):
            warnings.append(Warning(code="TRANSCRIPT_TIMESTAMPS_UNAVAILABLE",
                                    message="Some phrase boundaries are unavailable; unknown times remain null."))
        review = Review(schema_version=1, content_key=request.content_key, content_type=request.content_type,
                        source=request.source, summary=ReviewSummary(duration_milliseconds=transcript.duration_milliseconds),
                        processing=Processing(engine="azure-speech-fast-transcription", engine_version=api_version),
                        warnings=warnings, youtube=youtube)
        bundle = MediaArtifactResult(markdown=build_transcription_markdown(result), transcript=transcript, review=review,
                                     artifacts=ArtifactLayout.for_destination(request.destination_blob_name).media_refs())
        parent = PurePosixPath(request.destination_blob_name).parent
        output_directory.mkdir(parents=True, exist_ok=False)
        for name, value in ((request.destination_blob_name, bundle.markdown),
                            (bundle.artifacts.transcript_json_blob_name, transcript.model_dump_json(by_alias=True)),
                            (bundle.artifacts.review_blob_name, review.model_dump_json(by_alias=True))):
            path = output_directory.joinpath(*PurePosixPath(name).relative_to(parent).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        return bundle

    return await drain_on_cancel(export)
