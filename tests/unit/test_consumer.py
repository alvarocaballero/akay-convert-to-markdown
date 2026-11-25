"""Service Bus consumer settlement mapping tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from azure.servicebus.aio import ServiceBusClient

from akay_convert_to_markdown.errors.exceptions import (
    BlobStorageError,
    CallbackNotConfiguredError,
    WebhookError,
)
from akay_convert_to_markdown.messaging.service_bus_consumer import ServiceBusConsumer
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.notifications.webhook_client import WebhookClient
from akay_convert_to_markdown.processing.document_processor import DocumentProcessor
from tests.helpers import FakeConverter, FakeStorage, make_logger, make_settings


class StubProcessor:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.invalid_notifications: list = []
        self.notify_error = None
        self.requests: list = []

    async def process(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result

    async def notify_invalid_message(self, identity, log):
        if self.notify_error:
            raise self.notify_error
        self.invalid_notifications.append(identity)


class FakeReceiver:
    def __init__(self) -> None:
        self.completed: list = []
        self.abandoned: list = []

    async def complete_message(self, message) -> None:
        self.completed.append(message)

    async def abandon_message(self, message) -> None:
        self.abandoned.append(message)


class FakeMessage:
    def __init__(self, body, delivery_count: int = 1) -> None:
        self.body = body
        self.delivery_count = delivery_count


class FakeLockRenewer:
    def __init__(self) -> None:
        self.registered: list = []
        self.closed = False

    def register(self, receiver, message, max_lock_renewal_duration=None, **kwargs) -> None:
        self.registered.append((receiver, message, max_lock_renewal_duration))

    async def close(self) -> None:
        self.closed = True


class FakeLockRenewerFactory:
    def __init__(self) -> None:
        self.renewers: list = []

    def __call__(self):
        renewer = FakeLockRenewer()
        self.renewers.append(renewer)
        return renewer


def _make_consumer(settings, processor, factory=None) -> ServiceBusConsumer:
    return ServiceBusConsumer(
        settings,
        processor,
        None,
        make_logger(),
        asyncio.Event(),
        lock_renewer_factory=factory or FakeLockRenewerFactory(),
    )


def _valid_body() -> str:
    return json.dumps(
        {
            "requestId": str(uuid.uuid4()),
            "source": {"type": "blob", "blobName": "c/d/a.pdf"},
            "destinationBlobName": "c/d/a.md",
            "callback": "topic-content",
        }
    )


def _invalid_identifiable_body() -> str:
    # Missing source -> strict validation fails, but identity is intact.
    return json.dumps(
        {
            "requestId": str(uuid.uuid4()),
            "callback": "topic-content",
        }
    )


async def test_completes_on_success(settings):
    consumer = _make_consumer(settings, StubProcessor(result=ProcessingResult.COMPLETED))
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage(_valid_body()))

    assert len(receiver.completed) == 1
    assert not receiver.abandoned


async def test_completes_on_permanent_failure(settings):
    consumer = _make_consumer(settings, StubProcessor(result=ProcessingResult.FAILED_PERMANENT))
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage(_valid_body()))

    assert len(receiver.completed) == 1
    assert not receiver.abandoned


async def test_abandons_on_transient(settings):
    consumer = _make_consumer(settings, StubProcessor(error=BlobStorageError("temporary")))
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage(_valid_body()))

    assert len(receiver.abandoned) == 1
    assert not receiver.completed


async def test_invalid_message_is_completed(settings):
    consumer = _make_consumer(settings, StubProcessor(result=ProcessingResult.COMPLETED))
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage("{bad"))

    assert len(receiver.completed) == 1
    assert not receiver.abandoned


async def test_unexpected_exception_abandons_and_does_not_escape(settings):
    consumer = _make_consumer(settings, StubProcessor(error=RuntimeError("boom")))
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage(_valid_body()))

    assert len(receiver.abandoned) == 1
    assert not receiver.completed


async def test_invalid_identifiable_message_sends_failed_webhook(settings):
    processor = StubProcessor(result=ProcessingResult.COMPLETED)
    consumer = _make_consumer(settings, processor)
    receiver = FakeReceiver()
    body = _invalid_identifiable_body()
    request_id = json.loads(body)["requestId"]

    await consumer._handle_message(receiver, FakeMessage(body))

    assert len(processor.invalid_notifications) == 1
    assert processor.invalid_notifications[0]["requestId"] == request_id
    assert processor.invalid_notifications[0]["callback"] == "topic-content"
    assert len(receiver.completed) == 1
    assert not receiver.abandoned


async def test_failed_webhook_for_invalid_message_abandons(settings):
    processor = StubProcessor(result=ProcessingResult.COMPLETED)
    processor.notify_error = WebhookError("webhook down")
    consumer = _make_consumer(settings, processor)
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage(_invalid_identifiable_body()))

    assert len(receiver.abandoned) == 1
    assert not receiver.completed


async def test_lock_renewal_is_registered(settings):
    factory = FakeLockRenewerFactory()
    consumer = _make_consumer(settings, StubProcessor(result=ProcessingResult.COMPLETED), factory)
    receiver = FakeReceiver()
    message = FakeMessage(_valid_body())

    await consumer._handle_message(receiver, message)

    assert len(factory.renewers) == 1
    renewer = factory.renewers[0]
    assert len(renewer.registered) == 1
    _, registered_message, duration = renewer.registered[0]
    assert registered_message is message
    assert duration == settings.servicebus_max_lock_renewal_seconds


async def test_lock_renewer_is_closed_after_processing(settings):
    factory = FakeLockRenewerFactory()
    consumer = _make_consumer(settings, StubProcessor(result=ProcessingResult.COMPLETED), factory)

    await consumer._handle_message(FakeReceiver(), FakeMessage(_valid_body()))

    assert factory.renewers[0].closed is True


async def test_lock_renewer_is_closed_after_invalid_message(settings):
    factory = FakeLockRenewerFactory()
    consumer = _make_consumer(settings, StubProcessor(result=ProcessingResult.COMPLETED), factory)

    await consumer._handle_message(FakeReceiver(), FakeMessage("{bad"))

    assert factory.renewers[0].closed is True


async def test_unknown_callback_abandons(settings):
    consumer = _make_consumer(
        settings,
        StubProcessor(error=CallbackNotConfiguredError("Callback 'x' is not configured.")),
    )
    receiver = FakeReceiver()

    await consumer._handle_message(receiver, FakeMessage(_valid_body()))

    assert len(receiver.abandoned) == 1
    assert not receiver.completed


async def test_unknown_callback_end_to_end_abandons_without_http(tmp_path):
    http_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        http_calls.append(request)
        return httpx.Response(200)

    settings = make_settings(
        temp_directory=tmp_path / "akay",
        webhook_callbacks={"topic-content": "https://webhook.example.com/akay"},
    )
    webhook = WebhookClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    processor = DocumentProcessor(settings, FakeStorage(), FakeConverter(), webhook, make_logger())
    consumer = _make_consumer(settings, processor)
    receiver = FakeReceiver()

    body = json.dumps(
        {
            "requestId": str(uuid.uuid4()),
            "source": {"type": "blob", "blobName": "c/d/a.pdf"},
            "destinationBlobName": "c/d/a.md",
            "callback": "unknown-callback",
        }
    )

    await consumer._handle_message(receiver, FakeMessage(body))

    assert len(receiver.abandoned) == 1
    assert not receiver.completed
    assert http_calls == []


async def test_concurrent_processing_is_bounded_by_max_concurrent_jobs():
    settings = make_settings(max_concurrent_jobs=1)
    active = 0
    max_active = 0

    class TrackingProcessor:
        async def process(self, request):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1
            return ProcessingResult.COMPLETED

        async def notify_invalid_message(self, identity, log):
            pass

    consumer = _make_consumer(settings, TrackingProcessor())
    receiver = FakeReceiver()

    await asyncio.gather(
        consumer._handle_message(receiver, FakeMessage(_valid_body())),
        consumer._handle_message(receiver, FakeMessage(_valid_body())),
        consumer._handle_message(receiver, FakeMessage(_valid_body())),
    )

    assert max_active == 1


@pytest.mark.parametrize("body_kind", ["text", "bytes", "list", "generator"])
async def test_body_formats_and_split_utf8(settings, body_kind):
    processor = StubProcessor(result=ProcessingResult.COMPLETED)
    receiver = FakeReceiver()
    data = json.loads(_valid_body())
    data["payload"] = {"title": "lección"}
    text = json.dumps(data, ensure_ascii=False)
    raw = text.encode("utf-8")
    boundary = raw.index("ó".encode("utf-8")) + 1
    chunks = [raw[:boundary], raw[boundary:]]
    bodies = {"text": text, "bytes": raw, "list": chunks, "generator": iter(chunks)}

    await _make_consumer(settings, processor)._handle_message(receiver, FakeMessage(bodies[body_kind]))

    assert len(receiver.completed) == 1
    assert not receiver.abandoned
    assert processor.requests[0].payload == {"title": "lección"}


async def test_invalid_contract_generator_is_read_once_and_identity_recovered(settings):
    processor = StubProcessor()
    receiver = FakeReceiver()
    raw = _invalid_identifiable_body().encode()

    class OnePass:
        def __init__(self):
            self.reads = 0

        def __iter__(self):
            self.reads += 1
            assert self.reads == 1
            yield raw[:7]
            yield raw[7:]

    body = OnePass()
    await _make_consumer(settings, processor)._handle_message(receiver, FakeMessage(body))

    assert body.reads == 1
    assert processor.invalid_notifications[0]["requestId"] == json.loads(raw)["requestId"]
    assert processor.invalid_notifications[0]["callback"] == "topic-content"
    assert len(receiver.completed) == 1


@pytest.mark.parametrize("body", [42, {"unexpected": "object"}, [b"valid", "not bytes"], b"\xff", [b"{bad"]])
async def test_unrecoverable_body_does_not_prevent_next_message(settings, body):
    processor = StubProcessor(result=ProcessingResult.COMPLETED)
    receiver = FakeReceiver()
    consumer = _make_consumer(settings, processor)
    await consumer._handle_message(receiver, FakeMessage(body))
    await consumer._handle_message(receiver, FakeMessage(_valid_body()))
    assert len(receiver.completed) == 2
    assert not receiver.abandoned
    assert not processor.invalid_notifications
    assert len(processor.requests) == 1


async def test_raising_body_generator_does_not_stop_consumer(settings):
    def broken():
        yield b"{"
        raise RuntimeError("unreadable section")

    processor = StubProcessor(result=ProcessingResult.COMPLETED)
    receiver = FakeReceiver()
    consumer = _make_consumer(settings, processor)
    await consumer._handle_message(receiver, FakeMessage(broken()))
    await consumer._handle_message(receiver, FakeMessage(_valid_body()))
    assert len(receiver.completed) == 2
    assert len(processor.requests) == 1


@pytest.mark.parametrize("namespace,has_connection_string,expect_namespace", [
    ("test.servicebus.windows.net", False, True),
    (None, True, False),
    ("test.servicebus.windows.net", True, True),
    ("   ", True, False),
])
async def test_client_authentication_and_context_closure(namespace, has_connection_string, expect_namespace):
    conn_str = "Endpoint=sb://localhost;SharedAccessKeyName=test;SharedAccessKey=placeholder;UseDevelopmentEmulator=true"
    settings = make_settings(
        servicebus_fully_qualified_namespace=namespace,
        servicebus_connection_string=conn_str if has_connection_string else None,
    )
    credential = object()
    receiver = MagicMock()
    receiver.__aenter__ = AsyncMock(return_value=receiver)
    receiver.__aexit__ = AsyncMock(return_value=False)
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get_queue_receiver.return_value = receiver
    consumer = ServiceBusConsumer(settings, StubProcessor(), credential, make_logger(), asyncio.Event())
    consumer._receive_loop = AsyncMock()

    with patch("akay_convert_to_markdown.messaging.service_bus_consumer.ServiceBusClient") as factory:
        factory.return_value = client
        factory.from_connection_string.return_value = client
        await consumer.run()
        if expect_namespace:
            factory.assert_called_once_with("test.servicebus.windows.net", credential=credential)
            factory.from_connection_string.assert_not_called()
        else:
            factory.from_connection_string.assert_called_once_with(conn_str)
            factory.assert_not_called()

    client.get_queue_receiver.assert_called_once_with(settings.servicebus_queue_name,
                                                      prefetch_count=0)
    consumer._receive_loop.assert_awaited_once_with(receiver)
    receiver.__aexit__.assert_awaited_once()
    client.__aexit__.assert_awaited_once()


async def test_namespace_connection_failure_does_not_fall_back_to_connection_string():
    settings = make_settings(servicebus_fully_qualified_namespace="test.servicebus.windows.net",
                             servicebus_connection_string="Endpoint=sb://localhost;SharedAccessKey=placeholder")
    credential = object()
    consumer = ServiceBusConsumer(settings, StubProcessor(), credential, make_logger(), asyncio.Event())
    client = MagicMock()
    client.__aenter__ = AsyncMock(side_effect=RuntimeError("namespace connection failed"))
    client.__aexit__ = AsyncMock(return_value=False)

    with patch("akay_convert_to_markdown.messaging.service_bus_consumer.ServiceBusClient") as factory:
        factory.return_value = client
        with pytest.raises(RuntimeError, match="namespace connection failed"):
            await consumer.run()
        factory.assert_called_once_with("test.servicebus.windows.net", credential=credential)
        factory.from_connection_string.assert_not_called()


async def test_installed_sdk_accepts_emulator_connection_string_without_network():
    connection = ("Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;"
                  "SharedAccessKey=cGxhY2Vob2xkZXI=;UseDevelopmentEmulator=true;")
    async with ServiceBusClient.from_connection_string(connection) as client:
        receiver = client.get_queue_receiver("convert-to-markdown")
        await receiver.close()
