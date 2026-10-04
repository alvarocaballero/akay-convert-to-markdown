"""Service Bus consumer settlement mapping tests."""

from __future__ import annotations

import asyncio
import json
import uuid

from akay_convert_to_markdown.errors.exceptions import BlobStorageError, WebhookError
from akay_convert_to_markdown.messaging.service_bus_consumer import ServiceBusConsumer
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from tests.helpers import make_logger


class StubProcessor:
    def __init__(self, result=None, error=None) -> None:
        self.result = result
        self.error = error
        self.invalid_notifications: list = []
        self.notify_error = None

    async def process(self, request):
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
            "documentId": str(uuid.uuid4()),
            "contextId": str(uuid.uuid4()),
            "userId": str(uuid.uuid4()),
            "fileName": "a.pdf",
            "sourceBlobName": "c/d/a.pdf",
        }
    )


def _invalid_identifiable_body() -> str:
    # Missing sourceBlobName -> strict validation fails, but identity is intact.
    return json.dumps(
        {
            "documentId": str(uuid.uuid4()),
            "contextId": str(uuid.uuid4()),
            "userId": str(uuid.uuid4()),
            "fileName": "a.pdf",
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
    document_id = json.loads(body)["documentId"]

    await consumer._handle_message(receiver, FakeMessage(body))

    assert len(processor.invalid_notifications) == 1
    assert processor.invalid_notifications[0]["documentId"] == document_id
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
