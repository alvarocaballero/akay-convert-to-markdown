"""N8 reliability at the real consumer/publication boundaries, entirely offline."""

from __future__ import annotations

import asyncio
import json
import signal
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import httpx
import pytest
from azure.servicebus.exceptions import MessageLockLostError
from pydantic import ValidationError

from akay_convert_to_markdown.errors.exceptions import BlobStorageError, DocumentConversionError, WebhookError
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.blocking import drain_on_cancel
from tests.helpers import FakeConverter, FakeStorage, FakeWebhook, make_logger, make_request, make_settings
from tests.unit.test_artifact_publication import MemoryBlobs, PackageBuilder, publisher, request
from tests.unit.test_media_artifacts import job, runtime
from tests.unit.test_consumer import (
    FakeLockRenewer, FakeMessage, FakeReceiver, StubProcessor, _make_consumer, _valid_body,
)


class ControlledRenewer(FakeLockRenewer):
    def register(self, receiver, message, **kwargs):
        super().register(receiver, message, **kwargs)
        self.failure = kwargs.get("on_lock_renew_failure")


@pytest.mark.parametrize("overrides", [
    {"servicebus_max_lock_renewal_seconds": 900},
    {"workflow_timeout_seconds": 3600},
    {"webhook_retry_count": 0},
    {"webhook_timeout_seconds": float("nan")},
    {"webhook_retry_delay_seconds": -1},
    {"max_concurrent_jobs": 0},
])
def test_rejects_unusable_workflow_and_renewal_budgets(overrides):
    with pytest.raises(ValidationError):
        make_settings(**overrides)


async def test_invalid_identifiable_message_also_registers_renewal():
    renewer = ControlledRenewer()
    processor = StubProcessor()
    consumer = _make_consumer(make_settings(), processor, lambda: renewer)
    await consumer._handle_message(FakeReceiver(), FakeMessage(json.dumps({
        "requestId": json.loads(_valid_body())["requestId"], "callback": "topic-content",
    })))
    assert len(renewer.registered) == 1 and renewer.failure is not None


async def test_lost_lock_cancels_and_drains_native_writer_before_renewer_closes(tmp_path):
    entered, release = threading.Event(), threading.Event()
    renewer, receiver = ControlledRenewer(), FakeReceiver()
    path = tmp_path / "owned"
    path.write_text("source", encoding="utf-8")

    class Processor(StubProcessor):
        async def process(self, job):
            def writer():
                entered.set()
                assert release.wait(5)
                assert path.exists() and not renewer.closed

            try:
                await drain_on_cancel(writer)
            finally:
                path.unlink()

    consumer = _make_consumer(make_settings(), Processor(), lambda: renewer)
    task = asyncio.create_task(consumer._handle_message(receiver, FakeMessage(_valid_body())))
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        assert renewer.failure is not None
        await renewer.failure(None, RuntimeError("untrusted SDK details"))
        await asyncio.sleep(0.02)
        assert not task.done() and path.exists() and not renewer.closed
    finally:
        release.set()
        await task
    assert renewer.closed and not path.exists()
    assert not receiver.completed and not receiver.abandoned


@pytest.mark.parametrize("failure", ["auto_error", "expired"])
async def test_no_settlement_after_silent_sdk_lock_loss(failure):
    message = FakeMessage(_valid_body())
    if failure == "auto_error":
        message.auto_renew_error = RuntimeError("not delivered via callback")
    else:
        message.locked_until_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
    receiver = FakeReceiver()
    processor = StubProcessor()
    await _make_consumer(make_settings(), processor)._handle_message(receiver, message)
    assert not receiver.completed and not receiver.abandoned and not processor.requests


@pytest.mark.parametrize("settlement", ["complete_message", "abandon_message"])
@pytest.mark.parametrize("error_type", [MessageLockLostError, RuntimeError])
async def test_settlement_failure_does_not_stop_next_message(settlement, error_type, caplog):
    receiver = FakeReceiver()
    error = MessageLockLostError() if error_type is MessageLockLostError else RuntimeError("SECRET-SETTLEMENT")
    original = getattr(receiver, settlement)
    setattr(receiver, settlement, AsyncMock(side_effect=[error, None]))
    processor = StubProcessor(error=BlobStorageError("secret content") if settlement == "abandon_message" else None)
    consumer = _make_consumer(make_settings(), processor)
    await consumer._handle_message(receiver, FakeMessage(_valid_body()))
    setattr(receiver, settlement, original)
    await consumer._handle_message(receiver, FakeMessage(_valid_body()))
    assert len(processor.requests) == 2
    assert "secret content" not in caplog.text
    assert "SECRET-SETTLEMENT" not in caplog.text
    if settlement == "complete_message":
        assert not receiver.abandoned


async def test_unexpected_exception_logs_only_safe_class(caplog):
    consumer = _make_consumer(make_settings(), StubProcessor(error=RuntimeError("SECRET-DOCUMENT-and-token")))
    await consumer._handle_message(FakeReceiver(), FakeMessage(_valid_body()))
    assert "SECRET-DOCUMENT-and-token" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_outer_workflow_timeout_is_transient_and_cancels_callback(monkeypatch):
    settings, receiver = make_settings(), FakeReceiver()
    monkeypatch.setattr(type(settings), "workflow_timeout_seconds", property(lambda _: 0.04), raising=False)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    class Processor(StubProcessor):
        async def process(self, job):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    task = asyncio.create_task(_make_consumer(settings, Processor())._handle_message(receiver, FakeMessage(_valid_body())))
    try:
        await asyncio.wait_for(asyncio.shield(task), 0.5)
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert entered.is_set() and cancelled.is_set()
    assert len(receiver.abandoned) == 1 and not receiver.completed


@pytest.mark.parametrize("status", [501, 505, 507, 599])
async def test_all_server_errors_are_locally_retryable(status):
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(status if len(calls) == 1 else 204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await WebhookClient(make_settings(), client).send("topic-content", {"eventType": "x"}, "stable-key")
    assert len(calls) == 2
    assert calls[0].content == calls[1].content
    assert calls[0].headers["Idempotency-Key"] == calls[1].headers["Idempotency-Key"]


async def test_permanent_outcome_survives_callback_retry_and_process_recreation():
    service, job, events = MemoryBlobs(), request(), []
    count = 0

    async def build():
        nonlocal count
        count += 1
        raise DocumentConversionError("The document could not be converted.")

    async def notify(callback, event, key):
        events.append((callback, event, key))
        if len(events) == 1:
            raise WebhookError("temporary")

    with pytest.raises(WebhookError):
        await publisher(service).deliver(job, build, notify)
    await publisher(service).deliver(job, build, notify)
    await publisher(service).deliver(job, build, notify)
    assert count == 1 and len(events) == 2 and events[0] == events[1]
    assert events[0][1]["eventType"] == "document.conversion.failed"
    assert not any(key[0] == "outputs" for key in service.data)


async def test_transient_build_does_not_freeze_definitive_failure():
    service, job = MemoryBlobs(), request()
    notify = AsyncMock()
    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(job, AsyncMock(side_effect=BlobStorageError("temporary")), notify)
    notify.assert_not_awaited()
    assert not any(json.loads(value[0]).get("failures") for key, value in service.data.items()
                   if "/publications/" in key[1])


async def test_media_permanent_failure_retries_only_callback_through_real_consumer(runtime):
    runtime.ffmpeg.codecs = ()
    runtime.webhook.error = WebhookError("unavailable")
    req = job()
    message, receiver = FakeMessage(req.model_dump_json(by_alias=True)), FakeReceiver()
    await _make_consumer(runtime.settings, runtime.build())._handle_message(receiver, message)
    assert receiver.abandoned == [message] and not receiver.completed
    runtime.ffmpeg.codecs = ("mp3",)  # Source recovery cannot change this request's frozen failure.
    runtime.webhook.error = None
    await _make_consumer(runtime.settings, runtime.build())._handle_message(receiver, message)
    assert receiver.completed == [message]
    assert len(runtime.ffmpeg.probe_calls) == 1 and len(runtime.storage.downloads) == 1
    assert runtime.webhook.calls[0][1]["error"]["code"] == "NO_AUDIO_TRACK"
    assert not runtime.calls and not runtime.blobs.leases
    assert not list(runtime.settings.temp_directory.rglob("*"))


async def test_lost_blob_lease_cancels_async_builder_promptly():
    service, req = MemoryBlobs(), request()
    owner = publisher(service)
    owner.renewal_seconds = 0.005
    cancelled = asyncio.Event()

    async def build():
        service.renew_error = True
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(owner.deliver(req, build, AsyncMock()))
    try:
        with pytest.raises(BlobStorageError):
            await asyncio.wait_for(asyncio.shield(task), 0.3)
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert cancelled.is_set() and not service.leases


async def test_repeated_consumer_cancellation_drains_writer_before_closing(tmp_path):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    renewer, receiver = ControlledRenewer(), FakeReceiver()

    class Processor(StubProcessor):
        async def process(self, req):
            def write():
                entered.set()
                assert release.wait(5)
                assert not renewer.closed
                finished.set()
            await drain_on_cancel(write)

    task = asyncio.create_task(_make_consumer(make_settings(), Processor(), lambda: renewer)._handle_message(
        receiver, FakeMessage(_valid_body())))
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done() and not renewer.closed
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set() and renewer.closed
    assert not receiver.completed and not receiver.abandoned


async def test_graceful_stop_drains_active_batch_without_receiving_more():
    entered, release = asyncio.Event(), asyncio.Event()

    class Processor(StubProcessor):
        async def process(self, req):
            entered.set()
            await release.wait()

    receiver = FakeReceiver()
    receiver.receive_messages = AsyncMock(return_value=[FakeMessage(_valid_body())])
    consumer = _make_consumer(make_settings(), Processor())
    task = asyncio.create_task(consumer._receive_loop(receiver))
    await entered.wait()
    consumer._stop_event.set()
    await asyncio.sleep(0.01)
    assert not task.done() and not receiver.completed
    release.set()
    await task
    assert len(receiver.completed) == 1 and receiver.receive_messages.await_count == 1


async def test_inventory_cancellation_keeps_lease_until_hash_reader_stops(tmp_path, monkeypatch):
    from akay_convert_to_markdown.storage import artifact_publication as api

    entered, release = threading.Event(), threading.Event()
    service, req = MemoryBlobs(), request()
    original = api.ArtifactPublisher._inventory

    def held_inventory(cls, request, package):
        entered.set()
        assert release.wait(5)
        assert service.leases and all(path.exists() for path in package.files.values())
        return original(request, package)

    monkeypatch.setattr(api.ArtifactPublisher, "_inventory", classmethod(held_inventory))
    task = asyncio.create_task(publisher(service).deliver(req, PackageBuilder(api, tmp_path, req), AsyncMock()))
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done() and service.leases
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not service.leases and not any(key[0] == "outputs" for key in service.data)


async def test_ffmpeg_repeated_cancellation_waits_for_process_exit(monkeypatch):
    from akay_convert_to_markdown.services.process_runner import run_process

    entered, killed, exited = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Child:
        async def communicate(self):
            entered.set()
            await asyncio.Event().wait()

        def kill(self):
            killed.set()

        async def wait(self):
            await exited.wait()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=Child()))
    task = asyncio.create_task(run_process(["ffmpeg"], timeout_seconds=60, max_log_bytes=100))
    await entered.wait()
    task.cancel()
    await killed.wait()
    task.cancel()
    await asyncio.sleep(0.02)
    try:
        assert not task.done()
    finally:
        exited.set()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_subprocess_detail_is_not_written_to_application_logs(tmp_path, caplog):
    from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
    from akay_convert_to_markdown.errors.exceptions import FfmpegError

    converter = FakeConverter()
    converter.error = FfmpegError("FFmpeg failed.", detail="SECRET-FROM-SUBPROCESS")
    processor = DocumentProcessor(make_settings(temp_directory=tmp_path), FakeStorage(), converter,
                                  FakeWebhook(), make_logger())
    await processor.process(make_request())
    assert all("SECRET-FROM-SUBPROCESS" not in str(record.__dict__) for record in caplog.records)


async def test_lock_loss_during_callback_keeps_complete_package_for_redelivery(runtime):
    entered = asyncio.Event()
    original = runtime.webhook.send

    async def blocked_callback(*args):
        entered.set()
        await asyncio.Event().wait()

    runtime.webhook.send = blocked_callback
    receiver, renewer = FakeReceiver(), ControlledRenewer()
    message = FakeMessage(job().model_dump_json(by_alias=True))
    consumer = _make_consumer(runtime.settings, runtime.build(), lambda: renewer)
    task = asyncio.create_task(consumer._handle_message(receiver, message))
    await asyncio.wait_for(entered.wait(), 3)
    await renewer.failure(message, RuntimeError("lost lock"))
    await task
    assert not receiver.completed and not receiver.abandoned and not runtime.blobs.leases
    assert not list(runtime.settings.temp_directory.rglob("*"))
    runtime.webhook.send = original
    await _make_consumer(runtime.settings, runtime.build())._handle_message(receiver, message)
    assert receiver.completed == [message] and len(runtime.calls) == 1


async def test_notification_receipt_response_loss_repeats_only_identical_failure():
    service, req, events = MemoryBlobs(), request(), []
    build = AsyncMock(side_effect=DocumentConversionError("The document could not be converted."))

    async def notify(*args):
        events.append(args)
        if len(events) == 1:
            state_name = next(key[1] for key in service.data if "/publications/" in key[1])
            service.fail_after_write = state_name

    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(req, build, notify)
    await publisher(service).deliver(req, build, notify)
    # HTTP and receipt actually succeeded although the receipt response was lost.
    assert len(events) == 1 and build.await_count == 1


async def test_spawn_cancellation_reaps_child_before_returning(monkeypatch):
    from akay_convert_to_markdown.services.process_runner import run_process

    started, release = asyncio.Event(), asyncio.Event()
    child = SimpleNamespace(kill=AsyncMock(), wait=AsyncMock(return_value=0))
    child.kill = lambda: setattr(child, "killed", True)

    async def spawn(*args, **kwargs):
        started.set()
        await release.wait()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(run_process(["ffmpeg"], timeout_seconds=60, max_log_bytes=100))
    await started.wait()
    task.cancel()
    await asyncio.sleep(0.01)
    try:
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert child.killed
    child.wait.assert_awaited_once()


async def test_legacy_callback_is_outside_extraction_timeout(tmp_path, monkeypatch):
    from akay_convert_to_markdown.processing.document_processor import DocumentProcessor

    settings = make_settings(temp_directory=tmp_path)
    monkeypatch.setattr(type(settings), "process_timeout_seconds", property(lambda _: 0.04))
    webhook = FakeWebhook()
    send = webhook.send

    async def slow_send(*args):
        await asyncio.sleep(0.07)
        await send(*args)

    webhook.send = slow_send
    processor = DocumentProcessor(settings, FakeStorage(), FakeConverter(), webhook, make_logger())
    await processor.process(make_request())
    assert [event[1]["eventType"] for event in webhook.calls] == ["document.conversion.completed"]


async def test_signal_fallback_schedules_graceful_stop_and_restores_handlers(monkeypatch):
    from contextlib import ExitStack
    from akay_convert_to_markdown import worker_runtime

    loop = MagicMock()
    loop.add_signal_handler.side_effect = NotImplementedError
    installed = []
    previous = object()
    monkeypatch.setattr(signal, "getsignal", lambda _: previous)
    monkeypatch.setattr(signal, "signal", lambda sig, handler: installed.append((sig, handler)))
    stop = asyncio.Event()
    with ExitStack() as resources:
        worker_runtime.install_stop_handlers(loop, stop, resources)
        assert [entry[0] for entry in installed] == [signal.SIGINT, signal.SIGTERM]
        installed[1][1](signal.SIGTERM, None)
        loop.call_soon_threadsafe.assert_called_once_with(stop.set)
    assert installed[-2:] == [(signal.SIGTERM, previous), (signal.SIGINT, previous)]


async def test_invalid_notification_unexpected_error_cannot_stop_receive_loop(caplog):
    processor, receiver = StubProcessor(), FakeReceiver()
    processor.notify_error = RuntimeError("SECRET-INVALID-NOTIFICATION")
    consumer = _make_consumer(make_settings(), processor)
    body = json.loads(_valid_body())
    del body["source"]
    await consumer._handle_message(receiver, FakeMessage(json.dumps(body)))
    await consumer._handle_message(receiver, FakeMessage(_valid_body()))
    assert len(receiver.abandoned) == len(receiver.completed) == 1
    assert "SECRET-INVALID-NOTIFICATION" not in caplog.text


async def test_global_runner_shutdown_retains_renewer_until_native_exit():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    renewer = ControlledRenewer()

    class Processor(StubProcessor):
        async def process(self, req):
            def write():
                entered.set()
                assert release.wait(5)
                assert not renewer.closed
                finished.set()
            await drain_on_cancel(write)

    async def main():
        consumer = _make_consumer(make_settings(), Processor(), lambda: renewer)
        asyncio.create_task(consumer._handle_message(FakeReceiver(), FakeMessage(_valid_body())))
        while not entered.is_set():
            await asyncio.sleep(0.001)
        # asyncio.run now cancels every pending Task, including nested workers.

    task = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(main())))
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        await asyncio.sleep(0.02)
        assert not task.done() and not renewer.closed
    finally:
        release.set()
    await task
    assert finished.is_set() and renewer.closed


async def test_stop_during_receive_returns_unstarted_batch_without_processing():
    processor, receiver = StubProcessor(), FakeReceiver()
    consumer = _make_consumer(make_settings(), processor)
    message = FakeMessage(_valid_body())

    async def receive(**kwargs):
        consumer._stop_event.set()
        return [message]

    receiver.receive_messages = receive
    await consumer._receive_loop(receiver)
    assert not processor.requests and not receiver.completed
    assert receiver.abandoned == [message]


async def test_cancellation_during_lease_release_is_not_swallowed(tmp_path, monkeypatch):
    from akay_convert_to_markdown.storage import artifact_publication as api
    from tests.unit.test_artifact_publication import MemoryLease

    entered, release = asyncio.Event(), asyncio.Event()
    original = MemoryLease.release

    async def held_release(lease):
        entered.set()
        await release.wait()
        await original(lease)

    monkeypatch.setattr(MemoryLease, "release", held_release)
    service, req = MemoryBlobs(), request()
    task = asyncio.create_task(publisher(service).deliver(req, PackageBuilder(api, tmp_path, req), AsyncMock()))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0.01)
    try:
        assert not task.done() and service.leases
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not service.leases
