# Complete artifact publication (N5)

This immutable-package protocol applies to `convert` and media transcription.
`rebuildFromMarkdown` uses the [artifact-update path](content-processing-reviewed-content.md):
it overwrites the source Markdown's JSON artifacts and prunes unused inventory
images without writing Markdown or retaining an extraction-review backup.

The dedicated document worker processes version-one document requests through
Docling, the N4 exporter and a durable complete-set publisher. Success requires
the recorded package and its callback. N6 uses the same publisher for the dedicated
media worker's [Markdown/transcript/review sets](content-processing-media.md).
Legacy envelopes retain their Markdown-only behavior.

## Configuration and use

Configure the dedicated worker's queue, Blob account/source/destination and
allowlisted webhook settings, plus both explicit technical-storage values:

| Environment variable | Requirement |
| --- | --- |
| `PUBLICATION_STATE_CONTAINER_NAME` | Existing controlled container in the same configured Blob account. No default or automatic creation. |
| `PUBLICATION_STATE_PREFIX` | Controlled, portable relative prefix for technical receipts and attempt staging. No default. Use the same namespace across replicas. |

Providing only one value or a blank value fails settings validation. Without both,
legacy jobs remain available, while version-one Blob jobs raise a transient
configuration error before source access or a completed notification. These values
are loaded only by the dedicated document/media workers; no ambient storage or credentials
are discovered. The identity/SAS must have read/write/delete and Blob lease access
to technical storage as well as the existing source/destination permissions.

Run `akay-convert-document` with a document request from the
[contract guide](content-processing-contracts.md). PDF additionally needs the
explicit local [Docling model bundle](content-processing-docling.md). Conversion
does not trigger indexing. Producers must still coordinate queue routing/cutover.

## Publication protocol

| State / boundary | Behavior |
| --- | --- |
| Admission | Create a technical receipt conditionally; acquire a 60-second Blob lease, renew every 20 seconds and before guarded operations. Persist effective request snapshots; the same request UUID with changed parameters conflicts. |
| Identity | Bind exact destination/container, source container/reference, contentKey, contentType and effective document options. Source references must identify the original for that content; there is no automatic changed-original detection or source-history feature. Payload remains opaque. |
| Draft | Build the local package only when needed. Record exact filenames, SHA-256 and lengths, then stream files to unique attempt-owned technical staging. No canonical artifact is written yet. A failed draft is cleaned by exact owned stage paths and rebuilt on retry. |
| Ready | Freeze the staged package durably under lease and ETag. All future owners must finish these same bytes; never replace a ready package with a new extraction. |
| Canonical files | Stream and verify frozen bytes, then use create-only writes at the normative Markdown/sidecar/image paths. Existing files must have matching attempt/hash metadata and bytes. A stale holder can only finish identical immutable files, not overwrite another result. |
| Complete | Verify every file, persist final ETags under lease/If-Match, then clean only this attempt's stage files. Recheck recorded ETags/lengths on reuse. A missing/modified published file fails safely rather than producing success or silently repairing accepted material. |
| Callback | Send the version-one event using the existing authenticated allowlisted webhook client. Persist this request's notification success. Replaying the same delivered request skips delivery; uncertain delivery/receipt failures may repeat the same idempotency key, so the receiver must deduplicate. |
| Permanent build failure (N8) | Persist the safe error against the immutable request before HTTP; replay the identical failed event without rebuilding. New requests may try a still-unpublished destination. No definitive outcome is frozen for transient failures. |

Technical state is internal, not `manifest.json`, a review artifact or another
public image inventory. Consumer references remain exactly the paths in the
callback and review. JSON image URIs remain relative to the sidecar; Markdown
links remain relative to Markdown. Originals are not moved/copied and payload is
never used for naming.

The key is SHA-256 of compact Unicode JSON `[destinationContainer, artifactPrefix]`
inside the controlled `publications/` key space. The receipt compares the full
exact destination. Reserving the sidecar namespace also prevents `document.md`
and `document.MD` from claiming the same `document.artifacts/` directory.
Distinct stems in a common parent have independent leases and artifacts.

### Reuse and overwrite

- Both `overwriteDestination=false` and `true` reuse an already complete compatible
  package, including after callback failure. Redelivery never forces another
  extraction merely because overwrite was requested.
- An incompatible source/options/contentKey or an unowned existing Markdown or
  sidecar returns `ARTIFACT_PUBLICATION_CONFLICT`. Legacy Markdown-only output is
  not adopted as complete or overwritten. Use a fresh destination for the new
  contract. Overwrite is not permission to change accepted material invisibly;
  this implementation provides no administrative retirement/rebinding API.
- Partial canonical uploads resume from the durable ready stage without the
  source or local files. There is no reader-visible multi-Blob transaction: the
  backend must only expose artifacts after the matching completed event.

### Failure and cleanup boundaries

Lease/ETag, network, storage and damaged-publication failures are transient.
Permanent extraction/conflict failures use the typed safe failed event. Existing
Service Bus settlement is reused: processing returns only after its notification
succeeds; otherwise the consumer abandons the message.

Cancellation never detaches publication uploads. Native extraction/export retains
N3/N4 draining, keeping the lease until the builder stops. No public artifact or
consumer prefix is deleted. Incomplete ready stages are retained for recovery;
failed draft stages are cleaned on retry. A process killed while a draft write is
in flight can leave an unreferenced technical orphan. No broad sweeper is added;
operator recovery must reconcile exact attempt ownership before removal.

All cooperating writers must share the state namespace and use this protocol.
Do not run a legacy writer against the same destination: it does not participate
in leases or immutable publication. Whole-workflow renewal budgets, transport
lock-loss/shutdown policy and stable permanent-failure outcomes are documented
and tested in [N8 reliability](content-processing-reliability.md).

## Verification

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"
$env:RUN_DOCLING_MODEL_TESTS = "false"
$env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
.venv\Scripts\python.exe -m pytest tests/unit/test_artifact_publication.py -q --tb=short
```

Local doubles persist state across publisher recreation and enforce create/ETag/
lease conditions. Tests cover interrupted uploads, response/receipt loss, races,
takeover during a write, heartbeat failure, repeated cancellation, identity
conflicts, legacy outputs, shared-parent paths and exact cleanup. Actual Core
PNG/JSON reload verifies byte-preserving publication and portable references.
The real document entry/consumer harness proves notification-only recovery even
after removing the source from the double. A real pinned SDK client with an
in-process HTTP transport verifies serialized conditional/lease headers;
it makes no network connection.

Azure Storage/emulator interoperability, real cross-process crash/lease expiry,
cloud permissions, Docker/CI and deployment are pending external/later-task
evidence. No resource names or credentials are inferred and no live service was
called. See [progress](docling-rag-progress.md) for exact observed results.

## Pinned API references

- [Azure Blob SDK 12.24.1 async BlobClient](https://github.com/Azure/azure-sdk-for-python/blob/azure-storage-blob_12.24.1/sdk/storage/azure-storage-blob/azure/storage/blob/aio/_blob_client_async.py)
- [Azure Blob SDK 12.24.1 async leases](https://github.com/Azure/azure-sdk-for-python/blob/azure-storage-blob_12.24.1/sdk/storage/azure-storage-blob/azure/storage/blob/aio/_lease_async.py)
- [Concurrency and ETags](https://learn.microsoft.com/en-us/azure/storage/blobs/concurrency-manage)
- [Blob lease behavior](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-lease-python)

Context7/Microsoft Learn guidance was cross-checked against installed
`azure-storage-blob==12.24.1` signatures/documentation and local wire tests.
Publisher dependencies and pins are unchanged. N6 reuses `ArtifactPackage` for
timed Blob media output; N7 reuses it for explicit YouTube without changing the
publisher. N8 adds durable failure replay, cancellation-safe inventory and
lease-loss interruption; see the current [progress](docling-rag-progress.md).
