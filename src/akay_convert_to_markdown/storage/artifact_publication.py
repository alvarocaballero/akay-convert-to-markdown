"""Coherent, resumable artifact publication using the existing async Blob client.

Only a durable complete receipt authorizes a callback. Public paths are immutable
once bound: create-only writes from an old lease holder can at most finish the
same frozen package. A lease on the receipt alone cannot fence other blobs.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryFile
from typing import Literal
from uuid import uuid4

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from pydantic import Field

from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout
from akay_convert_to_markdown.contracts.base import BlobName, Contract, NonNegativeInt, blob_name
from akay_convert_to_markdown.contracts.events import conversion_completed, idempotency_key, request_failed
from akay_convert_to_markdown.contracts.ordering import RequestIdentity
from akay_convert_to_markdown.contracts.requests import DocumentRequest, MediaRequest
from akay_convert_to_markdown.errors.exceptions import BlobStorageError, PermanentError, TransientError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.blocking import await_cleanup, drain_on_cancel, drain_task


class PublicationConflict(PermanentError):
    code = "ARTIFACT_PUBLICATION_CONFLICT"

    def __init__(self):
        super().__init__("The destination is already bound or contains unowned artifacts; use a new destination.")


@dataclass(frozen=True)
class ArtifactPackage:
    """Exact files from an owned local exporter; never a caller-supplied prefix."""

    files: dict[str, Path]
    removed_images: tuple[str, ...] = ()
    retained_images: tuple[str, ...] = ()


class _File(Contract):
    name: BlobName
    size: NonNegativeInt
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    etag: str | None = None


class _Receipt(Contract):
    target: list[str]
    material: str
    status: Literal["draft", "ready", "complete"] = "draft"
    attempt: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    files: list[_File] = Field(default_factory=list)
    requests: dict[str, str] = Field(default_factory=dict)
    notified: list[str] = Field(default_factory=list)
    failures: dict[str, dict[str, str]] = Field(default_factory=dict)


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


class ArtifactPublisher:
    """One controlled state namespace per destination namespace, across replicas.

    The state container/prefix must be explicitly configured and shared by all
    writers. No container creation, credential lookup or prefix enumeration.
    """

    renewal_seconds = 20

    def __init__(self, client, *, destination_container: str, source_container: str,
                 state_container: str, state_prefix: str):
        if not all(value.strip() for value in (destination_container, source_container, state_container, state_prefix)):
            raise ValueError("Explicit publication storage configuration is required.")
        blob_name(state_prefix)
        self._client = client
        self._destination = destination_container
        self._source = source_container
        self._state = state_container
        self._prefix = state_prefix

    def _blob(self, container, name):
        return self._client.get_blob_client(container, name)

    @asynccontextmanager
    async def _ownership(self, blob):
        lease = await blob.acquire_lease(lease_duration=60)
        stop, lost = asyncio.Event(), asyncio.Event()

        async def renew():
            try:
                while True:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=self.renewal_seconds)
                        return
                    except TimeoutError:
                        await lease.renew()
            except Exception:
                lost.set()

        heartbeat = asyncio.create_task(renew())

        async def guard():
            if lost.is_set():
                raise BlobStorageError("Artifact publication ownership was lost.")
            await lease.renew()

        async def owned(awaitable):
            # A heartbeat failure must interrupt async source/notification work,
            # while native writers still drain before ownership is released.
            work = asyncio.ensure_future(awaitable)
            failure = asyncio.create_task(lost.wait())
            try:
                await asyncio.wait((work, failure), return_when=asyncio.FIRST_COMPLETED)
                if lost.is_set():
                    raise BlobStorageError("Artifact publication ownership was lost.")
                return await work
            finally:
                for task in (work, failure):
                    if not task.done():
                        task.cancel()
                    await drain_task(task)

        try:
            yield lease, guard, owned
        finally:
            async def release_ownership():
                stop.set()
                # Builders have drained before entering this cleanup. Keep the
                # release itself alive on cancellation without swallowing it.
                await drain_task(heartbeat)
                with suppress(Exception):
                    await lease.release()

            await await_cleanup(release_ownership())

    async def deliver(self, request: DocumentRequest | MediaRequest, build, notify) -> ProcessingResult:
        """Publish/reuse the full set, then deliver and record this request's event.

        build() is called only for a missing/incomplete draft. notify has the
        WebhookClient.send signature. Durable ready recovery needs no source,
        local files, extraction, or retranscription, including overwrite retries.
        """
        if isinstance(request, DocumentRequest) and request.operation == "rebuildFromMarkdown":
            from akay_convert_to_markdown.storage.artifact_rebuild import ArtifactRebuilder

            return await ArtifactRebuilder(self._client, destination_container=self._destination,
                                           source_container=self._source, state_container=self._state,
                                           state_prefix=self._prefix).deliver(request, build, notify)
        # Frozen Pydantic models are shallow; snapshot opaque payload/options now.
        request = type(request).model_validate_json(request.model_dump_json())
        layout = ArtifactLayout.for_destination(request.destination_blob_name)
        target = [self._destination, request.destination_blob_name]
        # .md and .MD can share a stem/sidecar directory: reserve that namespace
        # too, and compare the full exact target inside the receipt.
        key = sha256(_canonical([self._destination, layout.prefix]).encode()).hexdigest()
        state_name = f"{self._prefix}/publications/{key}.json"
        if self._state == self._destination and (state_name == request.destination_blob_name
                                                 or state_name.startswith(layout.prefix)):
            raise PublicationConflict()
        material_fields = {"sourceContainer": self._source, "source": request.source.model_dump(mode="json"),
                                "contentKey": request.content_key, "contentType": request.content_type,
                                "options": request.document_options.model_dump() if isinstance(request, DocumentRequest) else None}
        material = _canonical(material_fields)
        identity = RequestIdentity.capture(request).canonical_request
        request_id = str(request.request_id)
        blob = self._blob(self._state, state_name)
        try:
            initial = _Receipt(target=target, material=material, attempt=str(uuid4()), requests={request_id: identity})
            try:
                await blob.upload_blob(initial.model_dump_json().encode(), overwrite=False)
            except ResourceExistsError:
                pass
            async with self._ownership(blob) as (lease, guard, owned):
                download = await blob.download_blob(lease=lease)
                receipt = _Receipt.model_validate_json(await download.readall())
                etag = download.properties.etag
                if receipt.target != target or receipt.material != material:
                    raise PublicationConflict()
                if request_id in receipt.requests and receipt.requests[request_id] != identity:
                    previous = json.loads(receipt.requests[request_id])
                    # Old document receipts predate these two default fields.
                    # Expand defaults only; changed source/options/payload still
                    # conflict, and media/index identities are never rewritten.
                    if isinstance(request, DocumentRequest) and request.operation == "convert":
                        previous.setdefault("operation", "convert")
                        previous.setdefault("extractionReviewBlobName", None)
                    if _canonical(previous) != identity:
                        raise PublicationConflict()
                self._validate_names(request, [entry.name for entry in receipt.files], allow_empty=receipt.status == "draft")
                if receipt.status == "complete" and any(not entry.etag for entry in receipt.files):
                    raise BlobStorageError("Artifact publication receipt is incomplete.")

                async def save(**changes):
                    nonlocal receipt, etag
                    await guard()
                    updated = receipt.model_copy(update=changes)
                    response = await blob.upload_blob(updated.model_dump_json().encode(), overwrite=True,
                                                      lease=lease, etag=etag, match_condition=MatchConditions.IfNotModified)
                    receipt, etag = updated, response["etag"]

                if request_id not in receipt.requests:
                    await save(requests={**receipt.requests, request_id: identity})

                async def notify_failure():
                    await guard()
                    if request_id not in receipt.notified:
                        event = request_failed(request, **receipt.failures[request_id])
                        await owned(notify(request.callback, event.model_dump(mode="json", by_alias=True), idempotency_key(event)))
                        await save(notified=[*receipt.notified, request_id])
                    return ProcessingResult.FAILED_PERMANENT

                if request_id in receipt.failures:
                    return await notify_failure()
                if receipt.status == "draft":
                    await self._cleanup(receipt)
                    # Unreceipted legacy output is never proof of a complete set.
                    if await self._properties(self._blob(self._destination, request.destination_blob_name)):
                        raise PublicationConflict()
                    try:
                        package = await owned(build())
                    except PermanentError as exc:
                        # Freeze the definitive result before HTTP. A redelivery
                        # must not rerun extraction or change failed into completed.
                        await save(failures={**receipt.failures, request_id: {"code": exc.code, "message": exc.message}})
                        return await notify_failure()
                    await guard()
                    files = await drain_on_cancel(lambda: self._inventory(request, package))
                    for entry in files:
                        if await self._properties(self._blob(self._destination, entry.name)):
                            raise PublicationConflict()
                    await save(attempt=str(uuid4()), files=files)
                    for index, entry in enumerate(receipt.files):
                        await guard()
                        with package.files[entry.name].open("rb") as stream:
                            await self._stage(receipt, index).upload_blob(stream, overwrite=False,
                                                                         metadata=self._metadata(receipt, entry))
                    # This is the irreversible binding. Never replace a ready
                    # package: late create-only uploads must contain identical bytes.
                    await save(status="ready")

                if receipt.status == "ready":
                    final_files = []
                    for index, entry in enumerate(receipt.files):
                        await guard()
                        destination = self._blob(self._destination, entry.name)
                        props = await self._properties(destination)
                        if props is None:
                            # Stream from the immutable stage and verify its actual
                            # bytes before creating a canonical Blob (not a copy URL).
                            with TemporaryFile() as stream:
                                await self._read_verified(self._stage(receipt, index), entry, stream)
                                await guard()
                                try:
                                    await destination.upload_blob(stream, overwrite=False,
                                                                  metadata=self._metadata(receipt, entry))
                                except ResourceExistsError:
                                    pass  # Another holder can only finish this ready set.
                            props = await destination.get_blob_properties()
                        if props.size != entry.size or props.metadata != self._metadata(receipt, entry):
                            raise PublicationConflict()
                        await self._read_verified(destination, entry)
                        final_files.append(entry.model_copy(update={"etag": props.etag}))
                    await save(status="complete", files=final_files)

                # Verify every recorded file even on notification-only retries.
                # Never repair/rebind damaged already published material invisibly.
                for entry in receipt.files:
                    props = await self._properties(self._blob(self._destination, entry.name))
                    if props is None or props.etag != entry.etag or props.size != entry.size:
                        raise BlobStorageError("Artifact publication is incomplete or was modified.")
                await self._cleanup(receipt)
                if request_id not in receipt.notified:
                    await guard()
                    refs = layout.document_refs() if isinstance(request, DocumentRequest) else layout.media_refs()
                    event = conversion_completed(request, refs)
                    await owned(notify(request.callback, event.model_dump(mode="json", by_alias=True), idempotency_key(event)))
                    await save(notified=[*receipt.notified, request_id])
                return ProcessingResult.COMPLETED
        except (PermanentError, TransientError):
            raise
        except Exception:
            raise BlobStorageError("Artifact publication could not be completed.") from None

    def _stage(self, receipt, index):
        return self._blob(self._state, f"{self._prefix}/attempts/{receipt.attempt}/{index}")

    @staticmethod
    def _metadata(receipt, entry):
        return {"publication_attempt": receipt.attempt, "sha256": entry.digest}

    @staticmethod
    async def _properties(blob):
        try:
            return await blob.get_blob_properties()
        except ResourceNotFoundError:
            return None

    @staticmethod
    def _validate_names(request, names, *, allow_empty=False):
        if allow_empty and not names:
            return
        layout = ArtifactLayout.for_destination(request.destination_blob_name)
        required = {request.destination_blob_name, layout.prefix + "review.json",
                    layout.prefix + ("document.docling.json" if isinstance(request, DocumentRequest) else "transcript.json")}
        if not required.issubset(names) or len(set(names)) != len(names):
            raise PublicationConflict()
        for name in names:
            if name not in required and not (name.startswith(layout.prefix + "images/")
                                             and name[len(layout.prefix + "images/"):].startswith(("figure-", "table-"))
                                             and name.endswith(".png")):
                raise PublicationConflict()
            blob_name(name)

    @classmethod
    def _inventory(cls, request, package):
        cls._validate_names(request, list(package.files))
        entries = []
        for name, path in sorted(package.files.items()):
            if path.is_symlink() or not path.is_file():
                raise PublicationConflict()
            with path.open("rb") as stream:
                digest = sha256()
                size = 0
                while data := stream.read(1024 * 1024):
                    digest.update(data)
                    size += len(data)
            entries.append(_File(name=name, size=size, digest=digest.hexdigest()))
        return entries

    @staticmethod
    async def _read_verified(blob, entry, stream=None):
        digest, size = sha256(), 0
        download = await blob.download_blob()
        async for data in download.chunks():
            digest.update(data)
            size += len(data)
            if stream is not None:
                stream.write(data)
        if size != entry.size or digest.hexdigest() != entry.digest:
            raise BlobStorageError("Artifact publication bytes do not match the frozen package.")
        if stream is not None:
            stream.seek(0)

    async def _cleanup(self, receipt):
        # Exact attempt-owned stage files only. Complete receipts never need them
        # again; incomplete ready receipts retain them for source-free recovery.
        if receipt.status == "ready":
            return
        for index, entry in enumerate(receipt.files):
            blob = self._stage(receipt, index)
            props = await self._properties(blob)
            if props is not None and props.metadata == self._metadata(receipt, entry):
                try:
                    await blob.delete_blob(etag=props.etag, match_condition=MatchConditions.IfNotModified)
                except ResourceNotFoundError:
                    pass
