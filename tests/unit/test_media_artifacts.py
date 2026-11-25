"""N6 timed media production and real worker/publication boundaries, offline."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from akay_convert_to_markdown.config.settings import MediaWorkerSettings
from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout, parse_review, parse_transcript
from akay_convert_to_markdown.contracts.requests import MediaRequest
from akay_convert_to_markdown.errors.exceptions import (
    BlobStorageError, FfmpegError, SpeechTranscriptionError, WebhookError,
)
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.services.fast_transcription_service import FastTranscriptionService
from akay_convert_to_markdown.storage.blob_storage import BlobStorage
from tests.helpers import FakeStorage, FakeWebhook, make_logger, make_settings
from tests.unit.test_artifact_publication import MemoryBlobs
from tests.unit.test_consumer import FakeMessage, FakeReceiver, _make_consumer
from tests.unit.test_media_processors import FakeFfmpeg


SPEECH = {
    "durationMilliseconds": 18500,
    "combinedPhrases": [{"text": "First phrase. Second phrase."}],
    "phrases": [
        {"offsetMilliseconds": 12001, "durationMilliseconds": 2002,
         "text": "First phrase.", "locale": "es-ES", "speaker": 0},
        {"offsetMilliseconds": 15000, "durationMilliseconds": 3500,
         "text": "Second phrase.", "locale": "es-ES", "speaker": 1},
    ],
}


def job(extension="mp3", **changes):
    values = dict(schema_version=1, request_id=uuid4(), content_key="opaque:media",
                  source={"type": "blob", "blob_name": f"original/input.{extension}"},
                  destination_blob_name="shared/lesson.md", content_type="audio" if extension != "mp4" else "video",
                  callback="topic-content", payload={"opaque": [1, {"keep": True}]})
    values.update(changes)
    return MediaRequest(**values)


@pytest.fixture
def api():
    return importlib.import_module("akay_convert_to_markdown.processing.media_artifacts")


def service():
    # Parsing is pure: do not instantiate an HTTP client or load ambient proxies.
    return FastTranscriptionService


async def test_speech_retains_measured_metadata_and_exact_milliseconds(api, tmp_path):
    result = service()._parse(SPEECH)
    output = tmp_path / "package"
    bundle = await api.export_media_artifacts(result, job(), output, api_version="2025-10-15")
    transcript = bundle.transcript
    assert transcript.duration_milliseconds == 18500 and transcript.language == "es-ES"
    assert [(s.start_milliseconds, s.end_milliseconds, s.speaker, s.language) for s in transcript.segments] == [
        (12001, 14003, "0", "es-ES"), (15000, 18500, "1", "es-ES")]
    assert [s.id for s in transcript.segments] == ["segment-0001", "segment-0002"]
    assert bundle.review.summary.duration_milliseconds == 18500
    assert bundle.review.sections == bundle.review.tables == bundle.review.images == []
    assert bundle.review.summary.page_count is None and bundle.review.confidence.pages == []
    assert bundle.review.confidence.mean_grade is None
    assert bundle.review.processing.engine_version == "2025-10-15"
    for segment in transcript.segments:
        assert bundle.markdown.count(segment.text) == 1
    assert "## [00:00:12]" in bundle.markdown and "akay-section" not in bundle.markdown
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == {
        "lesson.md", "lesson.artifacts/transcript.json", "lesson.artifacts/review.json"}
    assert parse_transcript((output / "lesson.artifacts/transcript.json").read_bytes()) == transcript
    assert parse_review((output / "lesson.artifacts/review.json").read_bytes()) == bundle.review


@pytest.mark.parametrize("payload,expected", [
    ({"phrases": [{"text": "Untimed."}]}, [(None, None)]),
    ({"phrases": [{"text": "Start only.", "offsetMilliseconds": 10}]}, [(10, None)]),
    ({"phrases": [{"text": "Duration only.", "durationMilliseconds": 50}]}, [(None, None)]),
    ({"combinedPhrases": [{"text": "Combined only."}]}, [(None, None)]),
    ({"phrases": [{"text": "Zero.", "offsetMilliseconds": 0, "durationMilliseconds": 0}]}, [(0, 0)]),
])
async def test_nullable_times_are_not_fabricated(api, tmp_path, payload, expected):
    bundle = await api.export_media_artifacts(service()._parse(payload), job(), tmp_path / "package",
                                            api_version="2025-10-15")
    assert [(s.start_milliseconds, s.end_milliseconds) for s in bundle.transcript.segments] == expected
    assert bundle.transcript.duration_milliseconds is None and bundle.transcript.language is None
    assert all(s.speaker is None for s in bundle.transcript.segments)
    missing = any(start is None or end is None for start, end in expected)
    assert ("TRANSCRIPT_TIMESTAMPS_UNAVAILABLE" in {w.code for w in bundle.review.warnings}) == missing
    if expected[0][0] is None:
        assert "## [" not in bundle.markdown
    assert bundle.transcript.segments[0].text in bundle.markdown


async def test_phrase_text_is_canonical_and_mixed_language_not_guessed(api, tmp_path):
    payload = deepcopy(SPEECH)
    payload["phrases"][1]["locale"] = "fr-FR"
    payload["combinedPhrases"][0]["text"] = "Different combined representation."
    bundle = await api.export_media_artifacts(service()._parse(payload), job(), tmp_path / "package",
                                            api_version="2025-10-15")
    assert bundle.transcript.language is None
    assert [s.language for s in bundle.transcript.segments] == ["es-ES", "fr-FR"]
    assert "Different combined" not in bundle.markdown
    assert "SPEECH_COMBINED_TEXT_DIFFERS" in {w.code for w in bundle.review.warnings}


@pytest.mark.parametrize("field,value", [
    ("offsetMilliseconds", -1), ("durationMilliseconds", -1), ("offsetMilliseconds", "10"),
    ("offsetMilliseconds", True), ("durationMilliseconds", 1.5), ("durationMilliseconds", float("nan")),
    ("offsetMilliseconds", float("inf")), ("speaker", True), ("speaker", -1),
    ("locale", 42), ("locale", ""), ("text", 42),
])
def test_invalid_speech_measurements_fail_safely(field, value):
    payload = deepcopy(SPEECH)
    payload["phrases"][0][field] = value
    with pytest.raises(SpeechTranscriptionError, match="invalid|unexpected") as error:
        service()._parse(payload)
    assert "First phrase" not in str(error.value)


@pytest.mark.parametrize("payload", [None, [], {}, {"phrases": "bad"}, {"phrases": [None]},
                                     {"phrases": []}, {"combinedPhrases": [{"text": " "}]},
                                     {"durationMilliseconds": -1, "phrases": [{"text": "Text"}]}])
def test_invalid_or_empty_response_is_not_success(payload):
    with pytest.raises(SpeechTranscriptionError):
        service()._parse(payload)


@pytest.mark.parametrize("kind", ["out_of_order", "beyond_duration"])
def test_invalid_speech_ranges_are_not_silently_sorted_or_clamped(kind):
    payload = deepcopy(SPEECH)
    if kind == "out_of_order":
        payload["phrases"].reverse()
    else:
        payload["durationMilliseconds"] = 100
    with pytest.raises(SpeechTranscriptionError):
        service()._parse(payload)


@pytest.fixture
async def runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(os, "environ", {})
    values = make_settings().model_dump(exclude={"servicebus_queue_name"})
    values.update(MEDIA_SERVICEBUS_QUEUE_NAME="media-only", speech_resource_key="fixture-key",
                  speech_endpoint="https://speech.invalid", temp_directory=tmp_path / "jobs",
                  publication_state_container_name="technical", publication_state_prefix="processing",
                  speech_retry_delay_seconds=0)
    settings = MediaWorkerSettings(**values)
    return_value = SimpleNamespace(settings=settings, blobs=MemoryBlobs(), storage=FakeStorage(),
                                   ffmpeg=FakeFfmpeg(duration=18.5), calls=[], payload=deepcopy(SPEECH), status=200)

    def handler(request):
        return_value.calls.append(request)
        assert request.url.params["api-version"] == "2025-10-15"
        assert request.headers["Ocp-Apim-Subscription-Key"] == "fixture-key"
        assert b'name="audio"' in request.content and b'name="definition"' in request.content
        return httpx.Response(return_value.status, json=return_value.payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        speech = FastTranscriptionService(settings, client)
        from akay_convert_to_markdown import media_main

        monkeypatch.setattr(media_main, "FfmpegService", lambda _: return_value.ffmpeg)
        monkeypatch.setattr(media_main, "FastTranscriptionService", lambda _: speech)
        return_value.storage.artifact_publisher = BlobStorage(return_value.blobs).artifact_publisher
        return_value.webhook = FakeWebhook()
        return_value.build = lambda: media_main.build_processor(settings, return_value.storage,
                                                               return_value.webhook, make_logger())[0]
        yield return_value


@pytest.mark.parametrize("extension,content_type", [(ext, "audio") for ext in
                                                   ("mp3", "wav", "aac", "m4a", "ogg", "opus", "flac")] +
                                                  [(ext, "video") for ext in
                                                   ("mp4", "mov", "mkv", "webm", "avi", "m4v", "mpg", "mpeg", "wmv")])
async def test_real_media_entry_publishes_only_complete_media_set(runtime, extension, content_type):
    request = job(extension, content_type=content_type)
    processor = runtime.build()
    parsed = processor.parse_message(request.model_dump_json(by_alias=True))
    assert await processor.process(parsed) is ProcessingResult.COMPLETED
    assert len(runtime.calls) == 1 and len(runtime.ffmpeg.probe_calls) == 1
    assert len(runtime.ffmpeg.prepare_calls) == int(content_type == "video")
    event = runtime.webhook.calls[0][1]
    refs = ArtifactLayout.for_destination(request.destination_blob_name).media_refs()
    assert event["artifacts"] == refs.model_dump(by_alias=True) and event["payload"] == request.payload
    assert event["source"] == {"type": "blob", "blobName": f"original/input.{extension}"}
    outputs = {k[1]: v[0] for k, v in runtime.blobs.data.items() if k[0] == "markdown"}
    assert set(outputs) == {request.destination_blob_name, refs.transcript_json_blob_name, refs.review_blob_name}
    transcript, review = parse_transcript(outputs[refs.transcript_json_blob_name]), parse_review(outputs[refs.review_blob_name])
    assert transcript.origin == request.source and review.content_type == content_type
    assert all(s.text in outputs[request.destination_blob_name].decode() for s in transcript.segments)
    assert not list(runtime.settings.temp_directory.rglob("*"))


@pytest.mark.parametrize("codec,extension", [("opus", ".ogg"), ("wmav2", ".mp3")])
async def test_audio_only_webm_reuses_real_ffmpeg_command_adapter(runtime, codec, extension):
    from akay_convert_to_markdown.services.ffmpeg_service import FfmpegService
    from akay_convert_to_markdown.services.process_runner import ProcessResult

    commands = []

    async def runner(command, **limits):
        commands.append(command)
        if command[0] == "ffprobe":
            return ProcessResult(0, json.dumps({"streams": [{"codec_type": "audio", "codec_name": codec}],
                                               "format": {"duration": "18.5"}}), "")
        assert command[command.index("-map") + 1] == "0:a:0" and "-vn" in command
        assert Path(command[-1]).suffix == extension
        Path(command[-1]).write_bytes(b"fixture prepared audio")
        return ProcessResult(0, "", "")

    from akay_convert_to_markdown import media_main
    with patch.object(media_main, "FfmpegService", lambda _: FfmpegService(runtime.settings, runner)):
        request = job("webm", content_type="video")
        assert await runtime.build().process(request) is ProcessingResult.COMPLETED
    assert [command[0] for command in commands] == ["ffprobe", "ffmpeg"]
    assert f'filename="audio{extension}"'.encode() in runtime.calls[0].content
    assert runtime.webhook.calls[0][1]["source"]["blobName"].endswith("input.webm")


async def test_callback_retry_resumes_without_source_or_speech_through_consumer(runtime):
    request = job("webm", content_type="video", overwrite_destination=True)
    runtime.webhook.error = WebhookError("unavailable")
    receiver, message = FakeReceiver(), FakeMessage(request.model_dump_json(by_alias=True))
    await _make_consumer(runtime.settings, runtime.build())._handle_message(receiver, message)
    assert len(receiver.abandoned) == 1 and not receiver.completed
    assert len([k for k in runtime.blobs.data if k[0] == "markdown"]) == 3
    runtime.storage.missing.add(request.source.blob_name)
    runtime.webhook.error = None
    await _make_consumer(runtime.settings, runtime.build())._handle_message(receiver, message)
    assert len(receiver.completed) == 1 and len(runtime.calls) == 1 and len(runtime.storage.downloads) == 1
    assert len(runtime.webhook.calls) == 1


async def test_partial_upload_recovers_media_without_retranscribing(runtime):
    request = job()
    runtime.blobs.fail_name = "shared/lesson.artifacts/review.json"
    with pytest.raises(BlobStorageError):
        await runtime.build().process(request)
    assert not runtime.webhook.calls
    runtime.storage.missing.add(request.source.blob_name)
    assert await runtime.build().process(request) is ProcessingResult.COMPLETED
    assert len(runtime.calls) == 1


async def test_complete_set_exists_before_callback_and_shared_parent_is_independent(runtime):
    original_send = runtime.webhook.send

    async def checked_send(callback, event, key):
        assert key == f"{event['requestId']}:{event['eventType']}"
        for name in (event["destinationBlobName"], *event["artifacts"].values()):
            assert ("markdown", name) in runtime.blobs.data
        await original_send(callback, event, key)

    runtime.webhook.send = checked_send
    first = job()
    second = job(destination_blob_name="shared/other.md", content_key="other")
    await runtime.build().process(first)
    await runtime.build().process(second)
    assert len([k for k in runtime.blobs.data if k[0] == "markdown"]) == 6
    assert len(runtime.webhook.calls) == 2


async def test_transient_speech_failure_abandons_without_permanent_notification(runtime):
    runtime.status = 429
    receiver = FakeReceiver()
    await _make_consumer(runtime.settings, runtime.build())._handle_message(
        receiver, FakeMessage(job().model_dump_json(by_alias=True)))
    assert len(receiver.abandoned) == 1 and not receiver.completed
    assert not runtime.webhook.calls and not any(k[0] == "markdown" for k in runtime.blobs.data)


async def test_audio_without_audio_track_fails_before_speech(runtime):
    runtime.ffmpeg.codecs = ()
    assert await runtime.build().process(job()) is ProcessingResult.FAILED_PERMANENT
    assert runtime.webhook.calls[0][1]["error"]["code"] == "NO_AUDIO_TRACK" and not runtime.calls


async def test_cancel_export_keeps_owned_directory_and_lease_until_writer_stops(runtime, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    write_text = Path.write_text

    def blocked_write(path, *args, **kwargs):
        if path.name == "transcript.json":
            entered.set()
            assert release.wait(5)
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", blocked_write)
    running = asyncio.create_task(runtime.build().process(job()))
    try:
        async with asyncio.timeout(4):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        running.cancel()
        await asyncio.sleep(0.02)
        running.cancel()
        await asyncio.sleep(0.02)
        assert not running.done() and runtime.blobs.leases
        assert list(runtime.settings.temp_directory.rglob("lesson.md"))
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert not runtime.blobs.leases and not runtime.webhook.calls
    assert not list(runtime.settings.temp_directory.rglob("*"))


@pytest.mark.parametrize("failure,code", [("no_audio", "NO_AUDIO_TRACK"), ("invalid", "FFMPEG_FAILED"),
                                         ("size", "DOCUMENT_TOO_LARGE"), ("actual_size", "DOCUMENT_TOO_LARGE"),
                                         ("duration", "MEDIA_TOO_LONG"), ("speech_duration", "MEDIA_TOO_LONG"),
                                         ("empty", "SPEECH_TRANSCRIPTION_FAILED")])
async def test_media_failures_never_publish_completed(runtime, failure, code):
    request = job("mp4", content_type="video")
    if failure == "no_audio":
        runtime.ffmpeg.codecs = ()
    elif failure == "invalid":
        runtime.ffmpeg.prepare_error = FfmpegError("Invalid media.")
    elif failure == "size":
        runtime.storage.blob_sizes[request.source.blob_name] = runtime.settings.max_input_size_bytes + 1
    elif failure == "actual_size":
        runtime.settings.max_input_size_mb = 0
        runtime.storage.blob_sizes[request.source.blob_name] = 0
    elif failure == "duration":
        runtime.ffmpeg.duration = runtime.settings.max_media_duration_seconds + 1
    elif failure == "speech_duration":
        runtime.ffmpeg.duration = None
        runtime.payload["durationMilliseconds"] = int(runtime.settings.max_media_duration_seconds * 1000) + 1
    elif failure == "empty":
        runtime.payload = {"phrases": []}
    assert await runtime.build().process(request) is ProcessingResult.FAILED_PERMANENT
    event = runtime.webhook.calls[0][1]
    assert event["eventType"] == "document.conversion.failed" and event["error"]["code"] == code
    assert event["contentKey"] == request.content_key
    assert not any(k[0] == "markdown" for k in runtime.blobs.data)
    assert not list(runtime.settings.temp_directory.rglob("*"))


async def test_missing_publication_settings_fails_before_source_work(runtime):
    runtime.settings.publication_state_container_name = runtime.settings.publication_state_prefix = None
    with pytest.raises(BlobStorageError):
        await runtime.build().process(job())
    assert not runtime.calls and not runtime.storage.downloads and not runtime.webhook.calls


@pytest.mark.parametrize("field,value", [("publication_state_container_name", None),
                                        ("publication_state_prefix", ""), ("publication_state_prefix", "../unsafe")])
def test_media_rejects_partial_publication_configuration(runtime, field, value):
    data = runtime.settings.model_dump(exclude={"servicebus_queue_name"})
    data[field] = value
    with pytest.raises(ValidationError):
        MediaWorkerSettings(**data, MEDIA_SERVICEBUS_QUEUE_NAME="media-only")


async def test_youtube_unavailable_is_explicit_without_blob_or_speech(runtime, monkeypatch):
    from akay_convert_to_markdown import media_main
    from akay_convert_to_markdown.services.youtube_http import YouTubeError

    class Unavailable:
        async def download(self, *args):
            raise YouTubeError("The video is unavailable.")

    monkeypatch.setattr(media_main, "YouTubeService", lambda _: Unavailable())
    request = job(content_type="video", source={"type": "youtube", "url": "https://youtu.be/abcdefghijk"})
    assert await runtime.build().process(request) is ProcessingResult.FAILED_PERMANENT
    assert runtime.webhook.calls[0][1]["error"]["code"] == "YOUTUBE_SOURCE_UNAVAILABLE"
    assert not runtime.storage.downloads and not runtime.calls
