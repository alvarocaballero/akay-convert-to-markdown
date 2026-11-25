"""Replace the artifacts of an edited Markdown, without writing the Markdown itself."""

from hashlib import sha256
from tempfile import TemporaryFile
from typing import Literal
from uuid import uuid4
import re

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from pydantic import Field

from akay_convert_to_markdown.contracts.artifacts import ArtifactLayout
from akay_convert_to_markdown.contracts.base import BlobName, Contract
from akay_convert_to_markdown.contracts.events import conversion_completed, request_failed
from akay_convert_to_markdown.contracts.ordering import RequestIdentity
from akay_convert_to_markdown.contracts.requests import DocumentRequest
from akay_convert_to_markdown.errors.exceptions import BlobStorageError, PermanentError, TransientError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from akay_convert_to_markdown.processing.blocking import drain_on_cancel
from akay_convert_to_markdown.storage.artifact_publication import ArtifactPublisher, PublicationConflict, _File, _canonical


class _RebuildJob(Contract):
    identity: str
    attempt: str
    status: Literal["draft", "ready", "complete", "failed"] = "draft"
    files: list[_File] = Field(default_factory=list)
    removed_images: list[BlobName] = Field(default_factory=list)
    retained_images: list[BlobName] = Field(default_factory=list)
    event: dict | None = None
    notified: bool = False


class _RebuildReceipt(Contract):
    target: list[str]
    current: str
    jobs: dict[str, _RebuildJob]


class ArtifactRebuilder(ArtifactPublisher):
    """Serialize edits and retain only technical retry state, never an extraction backup."""

    @staticmethod
    def _validate_names(request, names, *, allow_empty=False):
        layout = ArtifactLayout.for_destination(request.source.blob_name)
        refs = layout.document_refs()
        if set(names) != {refs.docling_json_blob_name, refs.review_blob_name} or len(names) != 2:
            raise PublicationConflict()

    @staticmethod
    def _validate_images(request, removed, retained):
        prefix = ArtifactLayout.for_destination(request.source.blob_name).prefix + "images/"
        if set(removed) & set(retained) or len(set([*removed, *retained])) != len(removed) + len(retained):
            raise PublicationConflict()
        for name in [*removed, *retained]:
            if not name.startswith(prefix) or not re.fullmatch(r"(?:figure|table)-[0-9]+\.png", name[len(prefix):]):
                raise PublicationConflict()

    async def deliver(self, request, build, notify):
        request = DocumentRequest.model_validate_json(request.model_dump_json())
        layout = ArtifactLayout.for_destination(request.source.blob_name)
        target = [self._source, self._destination, request.source.blob_name]
        key = sha256(_canonical([self._destination, layout.prefix]).encode()).hexdigest()
        state_name = f"{self._prefix}/rebuilds/{key}.json"
        if ((self._state == self._destination and state_name.startswith(layout.prefix))
                or (self._state == self._source and state_name == request.source.blob_name)):
            raise PublicationConflict()
        identity = RequestIdentity.capture(request).canonical_request
        request_id = str(request.request_id)
        blob = self._blob(self._state, state_name)
        initial_job = _RebuildJob(identity=identity, attempt=str(uuid4()))
        try:
            try:
                initial = _RebuildReceipt(target=target, current=request_id, jobs={request_id: initial_job})
                await blob.upload_blob(initial.model_dump_json().encode(), overwrite=False)
            except ResourceExistsError:
                pass
            async with self._ownership(blob) as (lease, guard, owned):
                download = await blob.download_blob(lease=lease)
                receipt = _RebuildReceipt.model_validate_json(await download.readall())
                etag = download.properties.etag
                if receipt.target != target:
                    raise PublicationConflict()
                job = receipt.jobs.get(request_id)
                if job is not None and job.identity != identity:
                    raise PublicationConflict()

                async def save(updated, *, current=None):
                    nonlocal receipt, etag, job
                    await guard()
                    updated_receipt = receipt.model_copy(update={"jobs": {**receipt.jobs, request_id: updated},
                                                                 "current": current or receipt.current})
                    response = await blob.upload_blob(updated_receipt.model_dump_json().encode(), overwrite=True,
                                                      lease=lease, etag=etag, match_condition=MatchConditions.IfNotModified)
                    receipt, etag, job = updated_receipt, response["etag"], updated

                if job is None:
                    if receipt.jobs[receipt.current].status in {"draft", "ready"}:
                        raise BlobStorageError("An earlier artifact rebuild must finish before another edit.")
                    await save(initial_job, current=request_id)

                if job.status == "draft":
                    await self._cleanup(job)
                    try:
                        package = await owned(build())
                        files = await drain_on_cancel(lambda: self._inventory(request, package))
                        self._validate_images(request, package.removed_images, package.retained_images)
                    except PermanentError as exc:
                        event = request_failed(request, code=exc.code, message=exc.message)
                        await save(job.model_copy(update={"status": "failed", "event": event.model_dump(mode="json", by_alias=True)}))
                    else:
                        await save(job.model_copy(update={"attempt": str(uuid4()), "files": files,
                                                         "removed_images": list(package.removed_images),
                                                         "retained_images": list(package.retained_images)}))
                        for index, entry in enumerate(job.files):
                            await guard()
                            with package.files[entry.name].open("rb") as stream:
                                await self._stage(job, index).upload_blob(stream, overwrite=False,
                                                                         metadata=self._metadata(job, entry))
                        await save(job.model_copy(update={"status": "ready"}))

                if job.status == "ready":
                    self._validate_names(request, [entry.name for entry in job.files])
                    self._validate_images(request, job.removed_images, job.retained_images)
                    for name in job.retained_images:
                        if await self._properties(self._blob(self._destination, name)) is None:
                            raise BlobStorageError("A referenced artifact image is unavailable.")
                    # Only exact names from the previous controlled inventory may be removed.
                    for name in job.removed_images:
                        await guard()
                        image = self._blob(self._destination, name)
                        props = await self._properties(image)
                        if props is not None:
                            try:
                                await image.delete_blob(etag=props.etag, match_condition=MatchConditions.IfNotModified)
                            except ResourceNotFoundError:
                                pass
                    for index, entry in enumerate(job.files):
                        await guard()
                        destination = self._blob(self._destination, entry.name)
                        props = await self._properties(destination)
                        if props is not None and props.metadata == self._metadata(job, entry):
                            await self._read_verified(destination, entry)
                            continue
                        with TemporaryFile() as stream:
                            await self._read_verified(self._stage(job, index), entry, stream)
                            await guard()
                            conditions = ({"etag": props.etag, "match_condition": MatchConditions.IfNotModified}
                                          if props is not None else {})
                            await destination.upload_blob(stream, overwrite=props is not None,
                                                          metadata=self._metadata(job, entry), **conditions)
                    event = conversion_completed(request, layout.document_refs())
                    await save(job.model_copy(update={"status": "complete", "event": event.model_dump(mode="json", by_alias=True)}))

                await self._cleanup(job)
                if not job.notified:
                    await guard()
                    await owned(notify(request.callback, job.event, f"{request_id}:{job.event['eventType']}"))
                    await save(job.model_copy(update={"notified": True}))
                return ProcessingResult.COMPLETED if job.status == "complete" else ProcessingResult.FAILED_PERMANENT
        except (PermanentError, TransientError):
            raise
        except Exception:
            raise BlobStorageError("Artifact reconstruction could not be completed.") from None
