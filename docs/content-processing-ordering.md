# Ordered index/delete delivery (N11)

The dedicated index worker supports version-one `index` and `delete` jobs,
reusing N9/N10 with durable admission, mutation acknowledgements and callback
replay. Acceptance uses persistent Blob doubles and persistent Qdrant client
local mode. **Azure/Qdrant-server integration and deployment remain unverified.**

## Configure before starting

Run `akay-index-content` or `python -m akay_convert_to_markdown.index_main` only
after assigning its separate queue and supplying controlled configuration.
Common Blob, Service Bus, callback and workflow-budget settings are in the README.
`SOURCE_CONTAINER_NAME` identifies saved final artifacts, not original PDFs/media.
The indexer requires no destination container, Speech or FFmpeg settings.

Missing/invalid adapter settings log `INDEX_CONFIGURATION_REQUIRED` and return 2
before constructing credentials or consuming messages. No profile, endpoint or
key is inferred from specification examples. Collection creation occurs only
while processing an explicitly configured index job, not as a startup probe.

| Variable | Requirement / behavior |
| --- | --- |
| `INDEX_SERVICEBUS_QUEUE_NAME` | Required independent queue; existing local queue-collision checks apply. |
| `INDEX_STATE_CONTAINER` | Required existing controlled technical Blob container; never created by the worker. |
| `INDEX_STATE_PREFIX` | Required portable namespace shared by every cooperating replica. |
| `INDEX_PROFILES` | Required JSON array of complete immutable profiles. No production profile ID, distance, chunk budget or collection default. |
| `INDEX_TOKENIZER_PATH` | Required local `cl100k_base` file with the existing official hash check; no cache search/download. |
| `INDEX_QDRANT_URL` | Required exact HTTP(S) origin, without userinfo/query/fragment. All writers of the same target must share its exact origin and state namespace. |
| `INDEX_QDRANT_AUTH_MODE` | Required `apiKey` or explicit `none`. |
| `INDEX_QDRANT_API_KEY` | Required nonblank secret in `apiKey` mode, which requires HTTPS. Forbidden in `none` mode. |
| `INDEX_QDRANT_TIMEOUT_SECONDS` | 1–300 seconds per call; default 30. |
| `INDEX_BATCH_SIZE` | 1–2048 chunks per preparation/upsert batch; default 32. |
| `INDEX_MAX_CHUNKS` | 1–100000 chunks; default 10000. |
| `INDEX_MAX_STATE_BYTES` | Bounded technical record/input/cache reads; default 128 MiB. Size with artifact/batch budgets. |

Also supply explicit `AZURE_OPENAI_*` settings from the
[N10 guide](content-processing-indexing.md). The CLI uses `apiKey` mode. The
programmatic builder also accepts `entra` with a caller-supplied async
`token_provider`; its authorized audience, refresh and lifetime are integration
inputs. There is no ambient embedding authentication fallback. Blob/Service Bus
retain their independent existing authentication paths.

Qdrant REST construction disables environment proxy trust and automatic server
compatibility requests. Server/client compatibility is a separate integration
check. All prior pins remain, including Qdrant client **1.19.1** and Blob **12.24.1**.

## Admission, frozen preparation and replay

- Hash compact UTF-8 JSON `[targetIdentity, scopeKey, contentKey]` for each content
  receipt, independent of profile/collection. Compare full identities and source
  container too. A target-wide lane serializes collection metadata and delivery,
  including callbacks. This conservative design makes no throughput claim.
- Reuse N2's canonical request/admission rules. Persist admission before effects;
  preserve earlier admitted identities. Reused sequences with different parameters
  or request IDs, and request IDs reused for other content/operations in the same
  target, return `INDEX_OPERATION_CONFLICT` without mutation.
- Lower sequences emit `content.index.operation.superseded`. A replay of the
  current completed operation reuses its stored event, including a definitive
  preparation failure. Older completions are not replayed after a newer operation.
- Freeze input/review in owned technical storage. Cache validated embeddings by
  effective space and exact contextualized strings before point writes. Partial
  recovery reuses confirmed vectors, including repeated equal text within a job.
- Cache acknowledged mutation results. A failed final receipt write can rerun
  preparation from frozen inputs without repeating those embeddings/commands.
  After the completed receipt exists, notification replay needs no source,
  chunking, embeddings or Qdrant mutation.
- Save the stable event before HTTP, then record notification. Uncertain HTTP or
  notification-receipt writes may repeat the same event/key. Receiver deduplication
  and current-sequence/approval checks remain necessary: Blob cannot fence a late
  HTTP callback either.

## Why an expired lease does not authorize takeover

Finite 60-second leases, renewed every 20 seconds, and conditional ETags protect
the technical Blobs. **They do not fence Qdrant.** Before each mutation, save a
unique in-flight intent in the lane. Only that execution sends its request, with
one attempt, `wait=True` and strong ordering for point/index changes. Require
`COMPLETED`, then store the result and an immutable settled acknowledgement.

| Evidence available to a successor | Action |
| --- | --- |
| Settled acknowledgement | Clear the pending reference conditionally; continue ordered recovery/admission. The former writer needs valid ownership for any subsequent command. |
| Dispatch never started, including a lost pending-receipt response | Original execution records settled/no-dispatch; retry can advance safely. |
| Explicit rejection, including the client's special `429`/Retry-After exception | Record settled without caching success. Throttling/auth/configuration rejection is transient; ordinary permanent rejection becomes a safe failed event. |
| Transport loss, timeout, unconfirmed status or death before acknowledgement after possible dispatch | Keep the lane blocked with a safe transient uncertain-outcome error. No successor index/delete completes while an old request might still arrive. |

Cancellation drains a known in-flight command before releasing resources. A killed
process cannot supply that proof. Even a server-applied write can require operator
recovery if the process dies before acknowledgement. This is an availability
tradeoff, **not automatic cross-service crash recovery or a transaction**.

### Recover an uncertain lane

No administrative unblocking command is implemented. Recovery requires explicit
operational authorization: stop all writers for that target, establish that old
processes and remote requests cannot write again, inspect the exact lane/intent/
content receipts and actual points, and reconcile against the latest intended
operation. Only after proving quiescence may an operator conditionally repair the
specific technical state and resume the appropriate job. Do not clear `pending`,
break a lease or delete receipts merely because time elapsed. Keep it blocked if
quiescence cannot be established.

Private technical inputs, vectors and acknowledgements require controlled access
and retention. No technical sweeper is implemented; do not delete state still
needed for ordering/replay. Direct N10 callers or other writers bypassing the lane
must not mutate the same live target concurrently.

## Delete, migration and reassignment

Deletion authorizes an exact `(profileId, collection)` from controlled configuration
or this content's recorded used destinations. Its filter requires exact scope,
content and profile. Absent collections/points succeed without creation/embedding.
No original, image, Markdown, JSON, database record or additional content is deleted.

Used full profile/space snapshots are immutable in target state and collection
metadata. Retain old destinations after profile retirement for explicit cleanup.
A migration needs a new profile ID; one delete does not implicitly clean other
destinations. The consumer coordinates those deletes with increasing sequences.
Old index work for any profile cannot cross the newer scope/content boundary.

Reassignment is a higher-sequence index using existing final artifacts and new
fixed section context. N10 replaces deterministic IDs and prunes tails; changed
context produces new embeddings. Consumer approval, permissions and availability
filtering remain required. Partial batches may be visible before completion;
Python does not declare domain publication.

## Reproduce local evidence

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py -q --tb=short
.venv\Scripts\python.exe -m pytest -q
```

Tests block application-service connections, recreate coordinators over persistent
conditional/leased doubles, reopen real local Qdrant, force takeover during a
delayed mutation, and exercise actual consumer settlement/entry composition with
explicit doubles. Exact RED/GREEN and receipt-fault evidence is in
[progress](docling-rag-progress.md). This does not establish server replication,
payload-index acceleration, actual Azure expiry/RBAC or production routing.

API evidence: [Qdrant 1.19.1 async client](https://github.com/qdrant/qdrant-client/blob/v1.19.1/qdrant_client/async_qdrant_client.py),
[single-send transport/throttling](https://github.com/qdrant/qdrant-client/blob/v1.19.1/qdrant_client/http/api_client.py),
[Azure concurrency](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage),
[lease semantics](https://learn.microsoft.com/rest/api/storageservices/lease-blob)
and [pinned async Blob client](https://github.com/Azure/azure-sdk-for-python/blob/azure-storage-blob_12.24.1/sdk/storage/azure-storage-blob/azure/storage/blob/aio/_blob_client_async.py).

N12 now verifies [isolated packaging](content-processing-packaging.md).
N13-N15 add verified local images and gated CI/deployment preparation. The
[N16 handoff](content-processing-handoff.md) and [operator guide](content-processing-operations.md)
describe the full local flow and remaining explicitly authorized external checks.
