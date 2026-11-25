"""N1 startup, configuration and dispatch boundaries; no external services."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from tests.helpers import FakeConverter, FakeStorage, FakeWebhook, make_logger, make_request


TARGETS = [
    ("document_main", "DocumentWorkerSettings", "DOCUMENT_SERVICEBUS_QUEUE_NAME"),
    ("media_main", "MediaWorkerSettings", "MEDIA_SERVICEBUS_QUEUE_NAME"),
    ("index_main", "IndexerSettings", "INDEX_SERVICEBUS_QUEUE_NAME"),
]


@pytest.fixture
def worker_environment(monkeypatch):
    # Replace, rather than inspect/reuse, ambient configuration and credentials.
    environment = {
        "AZURE_STORAGE_ACCOUNT_URL": "https://fixture.blob.core.windows.net",
        "SOURCE_CONTAINER_NAME": "source",
        "DESTINATION_CONTAINER_NAME": "output",
        "SERVICEBUS_FULLY_QUALIFIED_NAMESPACE": "fixture.servicebus.windows.net",
        "WEBHOOK_CALLBACKS": '{"topic-content":"https://callback.invalid/result"}',
        "WEBHOOK_API_KEY": "fixture-key",
    }
    if sys.platform == "win32":
        # Winsock/asyncio needs this OS path even in a scrubbed child environment.
        environment["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setattr(os, "environ", environment)
    return environment


def load_settings(name):
    return getattr(importlib.import_module("akay_convert_to_markdown.config.settings"), name)()


@pytest.mark.parametrize("module,settings_name,queue_variable", TARGETS)
def test_target_requires_explicit_queue(worker_environment, module, settings_name, queue_variable):
    worker_environment.update(SPEECH_RESOURCE_KEY="fixture-key", SPEECH_ENDPOINT="https://speech.invalid")
    worker_environment["SERVICEBUS_QUEUE_NAME"] = "legacy-mixed"
    with pytest.raises(ValidationError):
        load_settings(settings_name)
    worker_environment[queue_variable] = "target-only"
    assert load_settings(settings_name).servicebus_queue_name == "target-only"


@pytest.mark.parametrize("module,settings_name,queue_variable", TARGETS)
def test_target_settings_ignore_other_workers(worker_environment, module, settings_name, queue_variable):
    worker_environment[queue_variable] = "target-only"
    if module != "media_main":
        worker_environment.update(SPEECH_TIMEOUT_SECONDS="not-a-number",
                                  FFMPEG_TIMEOUT_SECONDS="not-a-number")
    else:
        worker_environment.update(SPEECH_RESOURCE_KEY="fixture-speech-key",
                                  SPEECH_ENDPOINT="https://speech.invalid")
    if module == "index_main":
        del worker_environment["DESTINATION_CONTAINER_NAME"]
    settings = load_settings(settings_name)
    assert settings.servicebus_queue_name == "target-only"
    if module != "media_main":
        assert not hasattr(settings, "speech_endpoint")
        assert not hasattr(settings, "ffmpeg_timeout_seconds")


@pytest.mark.parametrize("missing", ["SPEECH_RESOURCE_KEY", "SPEECH_ENDPOINT"])
def test_transcriber_requires_its_speech_settings(worker_environment, missing):
    worker_environment.update(MEDIA_SERVICEBUS_QUEUE_NAME="media-only",
                              SPEECH_RESOURCE_KEY="fixture-key", SPEECH_ENDPOINT="https://speech.invalid")
    del worker_environment[missing]
    with pytest.raises(ValidationError):
        load_settings("MediaWorkerSettings")


@pytest.mark.parametrize("module,settings_name,queue_variable,other", [
    (*target, other) for target in TARGETS
    for other in ["SERVICEBUS_QUEUE_NAME", "DOCUMENT_SERVICEBUS_QUEUE_NAME",
                  "MEDIA_SERVICEBUS_QUEUE_NAME", "INDEX_SERVICEBUS_QUEUE_NAME"] if other != target[2]
])
def test_configured_queue_collisions_fail_before_consumption(worker_environment, module, settings_name,
                                                            queue_variable, other):
    worker_environment.update(SPEECH_RESOURCE_KEY="fixture-key", SPEECH_ENDPOINT="https://speech.invalid")
    worker_environment[queue_variable] = " Same-Queue "
    worker_environment[other] = "same-queue"
    with pytest.raises(ValidationError, match="distinct"):
        load_settings(settings_name)


@pytest.mark.parametrize("worker,extension,accepted", [
    ("document_main", "pdf", True), ("document_main", "mp3", False),
    ("document_main", "mp4", False), ("media_main", "pdf", False),
    ("media_main", "mp3", True), ("media_main", "mp4", True),
    ("media_main", "webm", True),
])
@pytest.mark.parametrize("existing", [False, True])
async def test_worker_dispatch_is_restricted_before_reuse(worker_environment, monkeypatch, tmp_path,
                                                         worker, extension, accepted, existing):
    worker_environment.update(DOCUMENT_SERVICEBUS_QUEUE_NAME="documents-only",
                              MEDIA_SERVICEBUS_QUEUE_NAME="media-only",
                              SPEECH_RESOURCE_KEY="fixture-key", SPEECH_ENDPOINT="https://speech.invalid")
    module = importlib.import_module(f"akay_convert_to_markdown.{worker}")
    settings_name = "DocumentWorkerSettings" if worker == "document_main" else "MediaWorkerSettings"
    settings = load_settings(settings_name)
    settings.temp_directory = tmp_path
    storage, webhook, converter = FakeStorage(), FakeWebhook(), FakeConverter()
    transcription = AsyncMock()
    if worker == "document_main":
        monkeypatch.setattr(module, "DoclingDocumentConverter", lambda **_: converter)
    else:
        # Keep the existing media strategies, replacing just their external boundaries.
        from akay_convert_to_markdown.models.transcription import TranscriptionResult
        from akay_convert_to_markdown.services.ffmpeg_service import MediaInfo
        transcription.transcribe.return_value = TranscriptionResult(text="fixture transcript", segments=[])
        ffmpeg = AsyncMock()
        ffmpeg.probe_media.return_value = MediaInfo(duration_seconds=1, audio_codecs=("mp3",))
        ffmpeg.prepare_audio.return_value = tmp_path / "audio.mp3"
        monkeypatch.setattr(module, "FfmpegService", lambda _: ffmpeg)
        monkeypatch.setattr(module, "FastTranscriptionService", lambda _: transcription)

    processor, close = module.build_processor(settings, storage, webhook, make_logger())
    request = make_request(file_name=f"fixture.{extension}")
    storage.existing_blobs[request.destination_blob_name] = existing
    try:
        await processor.process(request)
    finally:
        await close()
    payload = webhook.calls[0][1]
    assert payload["eventType"] == ("document.conversion.completed" if accepted else "document.conversion.failed")
    if not accepted:
        assert payload["error"]["code"] == "UNSUPPORTED_CONTENT_TYPE"
    assert len(storage.downloads) == int(accepted and not existing)
    assert len(converter.calls) == int(worker == "document_main" and accepted and not existing)
    if worker == "media_main":
        assert transcription.transcribe.await_count == int(accepted and not existing)
        transcription.aclose.assert_awaited_once()


@pytest.mark.parametrize("module,settings_name,queue_variable", TARGETS + [
    ("main", "Settings", "SERVICEBUS_QUEUE_NAME"),
])
def test_fresh_process_startup_without_foreign_imports(worker_environment, module, settings_name, queue_variable):
    environment = dict(worker_environment, PYTHONPATH=str(Path("src").resolve()))
    environment.update({queue_variable: "isolated-target", "SPEECH_RESOURCE_KEY": "fixture-key",
                        "SPEECH_ENDPOINT": "https://speech.invalid"})
    script = '''
import importlib, importlib.abc, sys
from unittest.mock import AsyncMock, MagicMock
target = sys.argv[1]
forbidden = ["docling", "docling_core", "qdrant_client"]
if target not in ("document_main", "main"):
    forbidden += ["markitdown", "akay_convert_to_markdown.conversion.markitdown_converter"]
if target not in ("media_main", "main"):
    forbidden += ["akay_convert_to_markdown.services.fast_transcription_service",
                  "akay_convert_to_markdown.services.ffmpeg_service",
                  "akay_convert_to_markdown.processing.audio_processor",
                  "akay_convert_to_markdown.processing.video_processor"]
class BlockForeignImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in forbidden):
            raise AssertionError("Foreign dependency imported: " + fullname)
sys.meta_path.insert(0, BlockForeignImports())
entry = importlib.import_module("akay_convert_to_markdown." + target)
if target != "index_main":
    runtime = importlib.import_module("akay_convert_to_markdown.worker_runtime")
    credential = AsyncMock()
    runtime.build_credential = MagicMock(return_value=credential)
    runtime.BlobStorage.from_settings = MagicMock(return_value=AsyncMock())
    runtime.WebhookClient = MagicMock(return_value=AsyncMock())
    consumer = MagicMock(return_value=AsyncMock())
    runtime.ServiceBusConsumer = consumer
    result = entry.main()
    consumer.return_value.run.assert_awaited_once()
    assert consumer.call_args.args[0].servicebus_queue_name == "isolated-target"
    credential.__aexit__.assert_awaited_once()
    runtime.WebhookClient.return_value.aclose.assert_awaited_once()
    runtime.BlobStorage.from_settings.return_value.aclose.assert_awaited_once()
else:
    result = entry.main()
    assert "azure.identity.aio" not in sys.modules
    assert "akay_convert_to_markdown.messaging.service_bus_consumer" not in sys.modules
assert result == (2 if target == "index_main" else 0), result
print("PASS isolated startup " + target)
'''
    result = subprocess.run([sys.executable, "-c", script, module], env=environment,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS isolated startup {module}" in result.stdout


@pytest.mark.parametrize("stage", ["builder", "consumer"])
async def test_shared_startup_closes_resources_on_failure(worker_environment, monkeypatch, stage):
    from akay_convert_to_markdown import worker_runtime

    worker_environment["DOCUMENT_SERVICEBUS_QUEUE_NAME"] = "documents-only"
    credential, storage, webhook, close = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(worker_runtime, "build_credential", lambda _: credential)
    monkeypatch.setattr(worker_runtime.BlobStorage, "from_settings", lambda *_: storage)
    monkeypatch.setattr(worker_runtime, "WebhookClient", lambda _: webhook)
    consumer = AsyncMock()
    consumer.run.side_effect = RuntimeError("fixture startup failure")
    monkeypatch.setattr(worker_runtime, "ServiceBusConsumer", lambda *_: consumer)
    builder = MagicMock(return_value=(AsyncMock(), close))
    if stage == "builder":
        builder.side_effect = RuntimeError("fixture startup failure")
    with pytest.raises(RuntimeError, match="fixture startup failure"):
        await worker_runtime.run_worker(load_settings("DocumentWorkerSettings"), make_logger(), builder)
    credential.__aexit__.assert_awaited_once()
    storage.aclose.assert_awaited_once()
    webhook.aclose.assert_awaited_once()
    assert close.await_count == int(stage == "consumer")


def test_three_console_scripts_and_legacy_command_are_registered():
    scripts = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    expected = {"akay-convert-to-markdown": "main", "akay-convert-document": "document_main",
                "akay-transcribe-media": "media_main", "akay-index-content": "index_main"}
    for command, module in expected.items():
        assert scripts[command] == f"akay_convert_to_markdown.{module}:main"
