"""N5 publication contracts with a persistent, conditional Azure SDK double."""

from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceModifiedError, ResourceNotFoundError

from akay_convert_to_markdown.contracts.requests import DocumentRequest
from akay_convert_to_markdown.errors.exceptions import BlobStorageError, PermanentError, WebhookError
from akay_convert_to_markdown.storage.blob_storage import BlobStorage


class MemoryBlobs:
    """Survives publisher recreation; enforces blob leases and atomic conditions."""

    def __init__(self):
        self.data = {}
        self.leases = {}
        self.sequence = 0
        self.calls = []
        self.fail_name = None
        self.fail_after_write = None
        self.before_upload = None
        self.renew_error = False
        self.fail_receipt_status = None

    def get_blob_client(self, container, blob):
        return MemoryBlob(self, (container, blob))


class MemoryBlob:
    def __init__(self, service, key):
        self.service, self.key = service, key

    def check(self, *, lease=None, etag=None, match_condition=None):
        service = self.service
        lease_id = getattr(lease, "id", lease)
        if lease is not None and service.leases.get(self.key) != lease_id:
            raise ResourceModifiedError("lost lease")
        if service.leases.get(self.key) is not None and lease_id != service.leases[self.key]:
            raise ResourceModifiedError("lease required")
        if match_condition == MatchConditions.IfNotModified:
            if self.key not in service.data or service.data[self.key][1] != etag:
                raise ResourceModifiedError("ETag mismatch")

    async def upload_blob(self, data, *, overwrite=False, lease=None, etag=None,
                          match_condition=None, metadata=None, **kwargs):
        service = self.service
        if service.before_upload:
            await service.before_upload(self.key)
        self.check(lease=lease, etag=etag, match_condition=match_condition)
        service.calls.append(("upload", self.key, overwrite, lease, etag, match_condition))
        if self.key[1] == service.fail_name:
            service.fail_name = None
            raise OSError("simulated network error with secret")
        if not overwrite and self.key in service.data:
            raise ResourceExistsError("exists")
        value = data.read() if hasattr(data, "read") else data
        if ("/publications/" in self.key[1] or "/rebuilds/" in self.key[1]) and service.fail_receipt_status:
            record = json.loads(value)
            statuses = [record.get("status"), *(job.get("status") for job in record.get("jobs", {}).values())]
            if service.fail_receipt_status in statuses:
                service.fail_receipt_status = None
                raise OSError("receipt write failed")
        service.sequence += 1
        new_etag = str(service.sequence)
        service.data[self.key] = (value, new_etag, metadata or {})
        if self.key[1] == service.fail_after_write:
            service.fail_after_write = None
            raise OSError("response lost after commit")
        return {"etag": new_etag}

    async def get_blob_properties(self, **kwargs):
        if self.key not in self.service.data:
            raise ResourceNotFoundError("missing")
        if kwargs.get("lease") is not None:
            self.check(**kwargs)
        data, etag, metadata = self.service.data[self.key]
        return SimpleNamespace(size=len(data), etag=etag, metadata=metadata)

    async def download_blob(self, **kwargs):
        props = await self.get_blob_properties(**kwargs)
        data = self.service.data[self.key][0]

        async def readall():
            return data

        async def chunks():
            yield data

        async def readinto(stream):
            stream.write(data)

        return SimpleNamespace(readall=readall, chunks=chunks, readinto=readinto, properties=props)

    async def delete_blob(self, **kwargs):
        self.check(**kwargs)
        self.service.calls.append(("delete", self.key))
        if self.key not in self.service.data:
            raise ResourceNotFoundError("missing")
        del self.service.data[self.key]

    async def acquire_lease(self, lease_duration):
        assert lease_duration == 60
        if self.key in self.service.leases:
            raise ResourceExistsError("leased")
        lease = MemoryLease(self)
        self.service.leases[self.key] = lease.id
        return lease


class MemoryLease:
    def __init__(self, blob):
        self.blob, self.id = blob, str(uuid4())

    async def renew(self):
        if self.blob.service.renew_error:
            raise OSError("lease renewal failed")
        self.blob.check(lease=self)

    async def release(self):
        self.blob.check(lease=self)
        del self.blob.service.leases[self.blob.key]


def request(**changes):
    data = dict(schema_version=1, request_id=uuid4(), content_key="opaque:á",
                source={"type": "blob", "blob_name": "original/input.md"},
                destination_blob_name="shared/document.md", content_type="document",
                callback="local", payload={"untouched": [1, {"a": True}]})
    data.update(changes)
    return DocumentRequest(**data)


@pytest.fixture
def api():
    return importlib.import_module("akay_convert_to_markdown.storage.artifact_publication")


def publisher(service):
    return BlobStorage(service).artifact_publisher(destination_container="outputs", source_container="sources",
                                                  state_container="technical", state_prefix="processing")


class PackageBuilder:
    def __init__(self, api, root, request):
        self.api, self.root, self.request = api, root, request
        self.count = 0

    async def __call__(self):
        self.count += 1
        directory = self.root / str(uuid4())
        directory.mkdir()
        destination = self.request.destination_blob_name
        prefix = destination[:-3] + ".artifacts/"
        files = {}
        for name, data in ((destination, b"# Principal\n\nText"),
                           (prefix + "document.docling.json", b'{"schema_name":"DoclingDocument"}'),
                           (prefix + "review.json", b'{"images":[]}'),
                           (prefix + "images/figure-001.png", b"actual crop fixture")):
            path = directory / str(len(files))
            path.write_bytes(data)
            files[name] = path
        return self.api.ArtifactPackage(files=files)


class Notifications:
    def __init__(self, service):
        self.service, self.events, self.fail = service, [], False

    async def __call__(self, callback, event, key):
        assert callback == "local"
        assert key == f"{event['requestId']}:{event['eventType']}"
        prefix = event["destinationBlobName"][:-3] + ".artifacts/"
        for name in (event["destinationBlobName"], prefix + "review.json", prefix + "document.docling.json",
                     prefix + "images/figure-001.png"):
            assert ("outputs", name) in self.service.data
        self.events.append(event)
        if self.fail:
            self.fail = False
            raise WebhookError("callback unavailable")


async def test_publish_full_set_and_retry_callback_without_rebuilding(api, tmp_path):
    service, job = MemoryBlobs(), request(overwrite_destination=True)
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)
    notify.fail = True
    with pytest.raises(WebhookError):
        await publisher(service).deliver(job, build, notify)
    original = {k: v for k, v in service.data.items() if k[0] == "outputs"}
    await publisher(service).deliver(job, build, notify)
    await publisher(service).deliver(job, build, notify)
    assert build.count == 1
    assert len(notify.events) == 2
    assert notify.events[0] == notify.events[1]
    assert notify.events[-1]["payload"] == job.payload
    assert "images" not in notify.events[-1] and "imagesPrefix" not in notify.events[-1]
    assert original == {k: v for k, v in service.data.items() if k[0] == "outputs"}


@pytest.mark.parametrize("response_lost", [False, True])
async def test_mid_upload_recovers_exact_ready_package(api, tmp_path, response_lost):
    service, job = MemoryBlobs(), request()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)
    name = "shared/document.artifacts/review.json"
    if response_lost:
        service.fail_after_write = name
    else:
        service.fail_name = name
    with pytest.raises(BlobStorageError, match="publication"):
        await publisher(service).deliver(job, build, notify)
    assert not notify.events
    await publisher(service).deliver(job, build, notify)
    assert build.count == 1 and len(notify.events) == 1


@pytest.mark.parametrize("field,value", [("content_key", "other"),
                                         ("source", {"type": "blob", "blob_name": "other.md"}),
                                         ("document_options", {"extract_sections": True})])
@pytest.mark.parametrize("overwrite", [False, True])
async def test_published_identity_cannot_be_rebound(api, tmp_path, field, value, overwrite):
    service, job = MemoryBlobs(), request()
    notify = Notifications(service)
    await publisher(service).deliver(job, PackageBuilder(api, tmp_path, job), notify)
    original = dict(service.data)
    other = job.model_copy(update={"request_id": uuid4(), "overwrite_destination": overwrite})
    data = other.model_dump()
    data[field] = value
    other = DocumentRequest(**data)
    build = PackageBuilder(api, tmp_path, other)
    with pytest.raises(PermanentError) as error:
        await publisher(service).deliver(other, build, notify)
    assert error.value.code == "ARTIFACT_PUBLICATION_CONFLICT"
    assert build.count == 0 and service.data == original


async def test_same_request_changed_payload_is_conflict_but_new_request_can_reuse(api, tmp_path):
    service, job = MemoryBlobs(), request()
    notify, build = Notifications(service), PackageBuilder(api, tmp_path, job)
    await publisher(service).deliver(job, build, notify)
    changed = job.model_copy(update={"payload": {"different": True}})
    with pytest.raises(PermanentError):
        await publisher(service).deliver(changed, build, notify)
    changed = changed.model_copy(update={"request_id": uuid4()})
    await publisher(service).deliver(changed, build, notify)
    assert build.count == 1 and notify.events[-1]["payload"] == {"different": True}


@pytest.mark.parametrize("overwrite", [False, True])
async def test_legacy_markdown_is_not_complete_or_safe_to_replace(api, tmp_path, overwrite):
    service, job = MemoryBlobs(), request(overwrite_destination=overwrite)
    await service.get_blob_client("outputs", job.destination_blob_name).upload_blob(b"old markdown")
    notify = Notifications(service)
    with pytest.raises(PermanentError):
        await publisher(service).deliver(job, PackageBuilder(api, tmp_path, job), notify)
    assert not notify.events
    assert service.data[("outputs", job.destination_blob_name)][0] == b"old markdown"


async def test_distinct_destinations_in_shared_parent_do_not_collide(api, tmp_path):
    service, first = MemoryBlobs(), request()
    second = first.model_copy(update={"destination_blob_name": "shared/notes.md", "request_id": uuid4()})
    notify = Notifications(service)
    await asyncio.gather(*(publisher(service).deliver(job, PackageBuilder(api, tmp_path, job), notify)
                           for job in (first, second)))
    assert len([key for key in service.data if key[0] == "outputs"]) == 8


async def test_destination_race_is_retryable_then_reuses_winner(api, tmp_path):
    service, job = MemoryBlobs(), request()
    entered, finish = asyncio.Event(), asyncio.Event()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)

    async def held_build():
        entered.set()
        await finish.wait()
        return await build()

    first = asyncio.create_task(publisher(service).deliver(job, held_build, notify))
    await entered.wait()
    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(job, build, notify)
    finish.set()
    await first
    await publisher(service).deliver(job, build, notify)
    assert build.count == 1 and len(notify.events) == 1


async def test_lost_lease_cannot_publish_or_notify(api, tmp_path):
    service, job = MemoryBlobs(), request()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)

    async def lose_ownership():
        result = await build()
        service.leases.clear()
        return result

    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(job, lose_ownership, notify)
    assert not notify.events and not any(k[0] == "outputs" for k in service.data)
    await publisher(service).deliver(job, build, notify)
    assert len(notify.events) == 1


async def test_corrupt_or_missing_published_file_never_reports_success(api, tmp_path):
    service, job = MemoryBlobs(), request()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)
    await publisher(service).deliver(job, build, notify)
    del service.data[("outputs", "shared/document.artifacts/review.json")]
    retry = job.model_copy(update={"request_id": uuid4()})
    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(retry, build, notify)
    assert build.count == 1 and len(notify.events) == 1


async def test_cleanup_never_deletes_public_or_unrelated_blobs(api, tmp_path):
    service, job = MemoryBlobs(), request()
    await service.get_blob_client("outputs", "shared/unrelated.png").upload_blob(b"keep")
    await publisher(service).deliver(job, PackageBuilder(api, tmp_path, job), Notifications(service))
    assert service.data[("outputs", "shared/unrelated.png")][0] == b"keep"
    deleted = [call[1] for call in service.calls if call[0] == "delete"]
    assert deleted and all(container == "technical" and "/attempts/" in name for container, name in deleted)
    assert not any("/attempts/" in name for container, name in service.data)


async def test_unowned_sidecar_cannot_be_overwritten(api, tmp_path):
    service, job = MemoryBlobs(), request(overwrite_destination=True)
    await service.get_blob_client("outputs", "shared/document.artifacts/review.json").upload_blob(b"somebody else's")
    notify = Notifications(service)
    with pytest.raises(PermanentError):
        await publisher(service).deliver(job, PackageBuilder(api, tmp_path, job), notify)
    assert not notify.events


async def test_invalid_package_never_becomes_ready(api, tmp_path):
    service, job = MemoryBlobs(), request()
    external = tmp_path / "bad"
    external.write_bytes(b"bad")

    async def build():
        return api.ArtifactPackage(files={"shared/document.md": external, "elsewhere/review.json": external})

    with pytest.raises(PermanentError):
        await publisher(service).deliver(job, build, Notifications(service))
    assert not any(k[0] == "outputs" for k in service.data)


async def test_real_document_entry_publishes_and_consumer_retries_callback_only(api, tmp_path, monkeypatch):
    from akay_convert_to_markdown import document_main
    from akay_convert_to_markdown.config.settings import DocumentWorkerSettings
    from akay_convert_to_markdown.messaging.service_bus_consumer import ServiceBusConsumer
    from akay_convert_to_markdown.contracts.artifacts import parse_review
    from docling_core.types.doc import DoclingDocument
    from tests.helpers import make_settings, make_logger, FakeWebhook
    from tests.unit.test_consumer import FakeMessage, FakeReceiver, FakeLockRenewerFactory

    settings = DocumentWorkerSettings(**make_settings().model_dump(exclude={"servicebus_queue_name"}),
                                      DOCUMENT_SERVICEBUS_QUEUE_NAME="documents-only",
                                      publication_state_container_name="technical", publication_state_prefix="processing")
    settings.temp_directory = tmp_path
    monkeypatch.setattr(document_main, "DoclingSettings", lambda: SimpleNamespace(artifacts_path=None))
    service, job = MemoryBlobs(), request(callback="topic-content", document_options={"extract_sections": True})
    source = service.get_blob_client(settings.source_container_name, job.source.blob_name)
    await source.upload_blob(b"Preamble\n\n# Principal\n\nActual content")
    webhook = FakeWebhook()
    webhook.error = WebhookError("local failure")
    processor, close = document_main.build_processor(settings, BlobStorage(service), webhook, make_logger())
    consumer = ServiceBusConsumer(settings, processor, None, make_logger(), asyncio.Event(), FakeLockRenewerFactory())
    receiver = FakeReceiver()
    message = FakeMessage(job.model_dump_json(by_alias=True))
    try:
        await consumer._handle_message(receiver, message)
        assert receiver.abandoned == [message] and not receiver.completed
        # No source is needed after publication: no extraction on redelivery.
        del service.data[(settings.source_container_name, job.source.blob_name)]
        webhook.error = None
        await consumer._handle_message(receiver, message)
        assert receiver.completed == [message]
        event = webhook.calls[-1][1]
        assert event["schemaVersion"] == 1 and event["contentKey"] == job.content_key
        review_name = event["artifacts"]["reviewBlobName"]
        review = parse_review(service.data[(settings.destination_container_name, review_name)][0])
        markdown = service.data[(settings.destination_container_name, job.destination_blob_name)][0].decode()
        document_name = event["artifacts"]["doclingJsonBlobName"]
        document = DoclingDocument.model_validate_json(service.data[(settings.destination_container_name, document_name)][0])
        assert len(review.sections) == 1 and str(review.sections[0].id) in markdown
        assert "Actual content" in document.export_to_markdown()
        assert not list(tmp_path.iterdir())
    finally:
        await close()


async def test_same_stem_different_markdown_suffix_reserves_artifact_namespace(api, tmp_path):
    service, job = MemoryBlobs(), request()
    await publisher(service).deliver(job, PackageBuilder(api, tmp_path, job), Notifications(service))
    alias = job.model_copy(update={"destination_blob_name": "shared/document.MD", "request_id": uuid4()})
    with pytest.raises(PermanentError):
        await publisher(service).deliver(alias, PackageBuilder(api, tmp_path, alias), Notifications(service))


@pytest.mark.parametrize("field", ["publication_state_container_name", "publication_state_prefix"])
def test_partial_publication_configuration_fails_validation(field):
    from pydantic import ValidationError
    from akay_convert_to_markdown.config.settings import DocumentWorkerSettings
    from tests.helpers import make_settings

    with pytest.raises(ValidationError):
        DocumentWorkerSettings(**make_settings().model_dump(exclude={"servicebus_queue_name"}),
                               DOCUMENT_SERVICEBUS_QUEUE_NAME="documents-only", **{field: "explicit"})


async def test_failed_draft_upload_cleans_only_owned_stage_and_rebuilds(api, tmp_path):
    service, job = MemoryBlobs(), request()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)

    async def fail_second_stage(key):
        if key[0] == "technical" and "/attempts/" in key[1] and key[1].endswith("/1"):
            service.fail_name = key[1]
            service.before_upload = None

    service.before_upload = fail_second_stage
    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(job, build, notify)
    stages = {key for key in service.data if "/attempts/" in key[1]}
    assert stages and not any(key[0] == "outputs" for key in service.data)
    await publisher(service).deliver(job, build, notify)
    assert build.count == 2 and len(notify.events) == 1
    assert stages.isdisjoint(service.data)


async def test_receipt_commit_failure_recovers_without_extracting(api, tmp_path):
    service, job = MemoryBlobs(), request()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)
    service.fail_receipt_status = "complete"
    with pytest.raises(BlobStorageError):
        await publisher(service).deliver(job, build, notify)
    assert not notify.events
    assert len([key for key in service.data if key[0] == "outputs"]) == 4
    await publisher(service).deliver(job, build, notify)
    assert build.count == 1 and len(notify.events) == 1


async def test_takeover_during_public_upload_cannot_mix_or_overwrite(api, tmp_path):
    service, job = MemoryBlobs(), request()
    first_entered, release_first = asyncio.Event(), asyncio.Event()
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)

    async def hold_one_upload(key):
        if key == ("outputs", "shared/document.artifacts/review.json"):
            service.before_upload = None
            first_entered.set()
            await release_first.wait()

    service.before_upload = hold_one_upload
    first = asyncio.create_task(publisher(service).deliver(job, build, notify))
    await first_entered.wait()
    service.leases.clear()  # Simulate lease expiry before the old request finishes.
    await publisher(service).deliver(job, build, notify)
    completed = {k: v for k, v in service.data.items() if k[0] == "outputs"}
    release_first.set()
    with pytest.raises(BlobStorageError):
        await first
    assert completed == {k: v for k, v in service.data.items() if k[0] == "outputs"}
    assert len(notify.events) == 1 and build.count == 1


async def test_heartbeat_renewal_failure_prevents_ready_publication(api, tmp_path):
    service, job = MemoryBlobs(), request()
    owner = publisher(service)
    owner.renewal_seconds = 0.001
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)

    async def delayed_build():
        service.renew_error = True
        await asyncio.sleep(0.02)
        return await build()

    with pytest.raises(BlobStorageError):
        await owner.deliver(job, delayed_build, notify)
    assert not notify.events and not any(k[0] == "outputs" for k in service.data)


async def test_cancel_keeps_lease_until_native_builder_is_drained(api, tmp_path):
    import threading
    from akay_convert_to_markdown.conversion.docling_converter import _drain_on_cancel

    started, finish = threading.Event(), threading.Event()
    service, job = MemoryBlobs(), request()
    notify = Notifications(service)

    def native_work():
        started.set()
        assert finish.wait(5)

    async def build():
        await _drain_on_cancel(native_work)
        pytest.fail("Cancelled extraction must not publish")

    running = asyncio.create_task(publisher(service).deliver(job, build, notify))
    try:
        async with asyncio.timeout(3):
            while not started.is_set():
                await asyncio.sleep(0.001)
        running.cancel()
        await asyncio.sleep(0.01)
        assert service.leases and not running.done()
        running.cancel()
        await asyncio.sleep(0.01)
        assert service.leases and not running.done()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert not service.leases and not notify.events


async def test_real_crop_package_retains_exact_bytes_references_and_no_page_images(api, tmp_path):
    from PIL import Image
    from docling_core.types.doc import DoclingDocument, ImageRef
    from tests.unit.test_document_artifacts import extracted
    from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts
    from akay_convert_to_markdown.contracts.artifacts import parse_review
    from pathlib import PurePosixPath
    from urllib.parse import unquote

    service, job = MemoryBlobs(), request()
    doc = DoclingDocument(name="fixture")
    doc.add_title("Crop")
    picture = doc.add_picture()
    picture.image = ImageRef.from_pil(Image.new("RGB", (8, 8), "blue"), dpi=72)
    output = tmp_path / "package"
    result = await export_document_artifacts(extracted(doc), job, output)
    parent = PurePosixPath(job.destination_blob_name).parent
    names = [job.destination_blob_name, result.artifacts.docling_json_blob_name,
             result.artifacts.review_blob_name, *(image.blob_name for image in result.review.images)]
    files = {name: output.joinpath(*PurePosixPath(name).relative_to(parent).parts) for name in names}

    async def build():
        return api.ArtifactPackage(files)

    await publisher(service).deliver(job, build, Notifications(service))
    for name, path in files.items():
        assert service.data[("outputs", name)][0] == path.read_bytes()
    review = parse_review(service.data[("outputs", result.artifacts.review_blob_name)][0])
    assert len(review.images) == 1
    image = review.images[0]
    assert service.data[("outputs", image.blob_name)][0].startswith(b"\x89PNG")
    reloaded = DoclingDocument.model_validate_json(service.data[("outputs", result.artifacts.docling_json_blob_name)][0])
    assert str(reloaded.pictures[0].image.uri).replace("\\", "/") == "images/figure-001.png"
    assert not reloaded.pages
    assert unquote("document.artifacts/images/figure-001.png") in result.markdown


async def test_mutated_request_while_builder_runs_does_not_change_event_identity(api, tmp_path):
    service, job = MemoryBlobs(), request()
    original = json.loads(job.model_dump_json(by_alias=True))["payload"]
    build, notify = PackageBuilder(api, tmp_path, job), Notifications(service)

    async def change_payload():
        job.payload["unexpected"] = "mutation"
        return await build()

    await publisher(service).deliver(job, change_payload, notify)
    assert notify.events[0]["payload"] == original


async def test_pinned_sdk_serializes_create_etag_and_lease_conditions_without_network():
    from azure.core.pipeline.transport import AsyncHttpTransport, AsyncHttpResponse
    from azure.storage.blob.aio import BlobClient

    class Response(AsyncHttpResponse):
        def __init__(self, request):
            super().__init__(request, None)
            self.status_code = 200 if request.headers.get("x-ms-lease-action") in {"renew", "release"} else 201
            self.headers = {"etag": '"new"', "x-ms-lease-id": "00000000-0000-0000-0000-000000000001"}
            self.content_type = "application/xml"

        def body(self):
            return b""

        async def load_body(self):
            pass

    class Transport(AsyncHttpTransport):
        def __init__(self):
            self.requests = []

        async def open(self):
            pass

        async def close(self):
            pass

        async def __aexit__(self, *args):
            await self.close()

        async def send(self, request, **kwargs):
            self.requests.append(request)
            return Response(request)

    transport = Transport()
    async with BlobClient("https://fixture.invalid", "technical", "state", transport=transport) as blob:
        await blob.upload_blob(b"{}", overwrite=False)
        lease = await blob.acquire_lease(lease_duration=60)
        lease_id = lease.id
        await blob.upload_blob(b"{}", overwrite=True, lease=lease, etag='"old"',
                               match_condition=MatchConditions.IfNotModified,
                               metadata={"publication_attempt": "test", "sha256": "digest"})
        await lease.renew()
        await lease.release()
    create, acquire, conditional, renew, release = transport.requests
    assert create.headers["If-None-Match"] == "*"
    assert acquire.headers["x-ms-lease-duration"] == "60"
    assert conditional.headers["If-Match"] == '"old"'
    assert conditional.headers["x-ms-lease-id"] == lease_id
    assert conditional.headers["x-ms-meta-publication_attempt"] == "test"
    assert renew.headers["x-ms-lease-action"] == "renew" and release.headers["x-ms-lease-action"] == "release"
