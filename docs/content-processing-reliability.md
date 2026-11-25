# Worker reliability (N8)

The shared consumer completes a message only after processing and its callback
succeed. Dedicated version-one document/media jobs reuse durable complete packages
and definitive build failures for notification-only retries, including YouTube.
N11's [ordered index/delete delivery](content-processing-ordering.md) reuses this
consumer when explicitly configured; missing adapter settings exit 2 before
credentials or consumption. N16 provides [local end-to-end/operator evidence](content-processing-handoff.md).

## Configure the whole workflow

| Setting | Default | Meaning |
| --- | --- | --- |
| `PROCESS_TIMEOUT_MINUTES` | `60` | Existing extraction/transcription/package-build budget. Legacy jobs include Markdown upload, but no longer their callback, in this budget. |
| `WORKFLOW_TIMEOUT_SECONDS` | `4200` | Full consumer operation: source/build, staging/publication, callback retries, cleanup and settlement. Also applies to reused outcomes and invalid-message notification. |
| `SERVICEBUS_MAX_LOCK_RENEWAL_SECONDS` | `4500` | Finite SDK renewal allowance, including workflow plus drain/settlement margin. Replaces the unsafe 900-second default. |

Let `P = PROCESS_TIMEOUT_MINUTES * 60` and
`C = WEBHOOK_TIMEOUT_SECONDS * WEBHOOK_RETRY_COUNT + WEBHOOK_RETRY_DELAY_SECONDS * (WEBHOOK_RETRY_COUNT - 1)`.
Startup requires `W >= P + C + 60` and `R >= W + 60`, where W/R are the workflow
and renewal settings. The minimum publication allowance is a validation floor,
not measured capacity; configure larger budgets from observed workloads.
Concurrency/retry counts must be positive. Callback timeout/delay and workflow
budgets must be finite with valid signs. Increasing P or callback retries may
require increasing both W and R.

Prefetch is disabled. Receive at most the active concurrency limit, and register
renewal before parsing, including poison-message callbacks. No extra prefetched
batch ages under a lock while a long job runs.

## Outcomes and retries

| Condition | Result |
| --- | --- |
| Version-one complete set | Verify/reuse N5 receipt; deliver the same completed event without source work. Skip recorded successful notification. |
| Version-one permanent build failure | Persist safe error code/message per immutable request under lease/ETag **before** HTTP. Redelivery replays failure without extraction/Speech/YouTube, even if the source becomes usable. A new request ID may attempt a still-unpublished destination. |
| Transient source/storage/Speech/network failure | No definitive failure is frozen. Abandon while the message lock is valid; redelivery can retry. |
| Callback failure | Local retry for network failures, timeouts, 408, 429 and all 5xx. Other HTTP errors have one local attempt. Failed delivery remains transient to Service Bus; completion requires 2xx/recorded success. |
| Whole-workflow deadline | Cancel/drain; abandon if lock remains valid. Do not create a conflicting definitive failed event after publication. Ready/complete state supports source-free recovery. |
| Lock loss / renewal failure | Cancel/drain; no settlement using lost ownership. Observe async SDK callback, public `auto_renew_error` and `locked_until_utc`: the pinned SDK can stop renewal without immediately invoking the callback. |
| Settlement error / uncertain response | Log safe type, keep receive loop available, rely on redelivery. No second conflicting disposition. |
| Invalid message | Notify only with recoverable request/callback identity; otherwise log and complete poison message. Failed notification must succeed before completion; unexpected notification errors abandon safely. |

The failure map is internal technical state, not a public artifact. Old N5
receipts load with an empty map; no migration/container creation. Keep cooperating
replicas on this implementation before relying on new failure replay: older
binaries do not understand that state.

HTTP and receipt writes have no shared transaction. A callback whose receipt did
not commit can be repeated with identical body/idempotency key; the receiver must
deduplicate. Conflicting request identities/destinations remain rejected. Legacy
envelopes retain Markdown-only overwrite/reuse semantics; they do not gain
version-one durable failure receipts.

## Shutdown and resource ownership

- SIGINT/SIGTERM stops admission and drains the active batch with renewal running.
  A batch returned after stop is abandoned without processing. Restore handlers on
  exit; Windows uses main-thread `signal.signal` when loop handlers are unavailable.
- Forced/repeated cancellation drains owned jobs before closing receiver,
  renewer or clients. `asyncio.run` shutdown does not release native writers early.
- Hash inventories, Markdown writes and local cleanup drain executor Futures.
  Blob heartbeat failure interrupts async builds/callbacks and drains native work
  before lease release. N5 immutable ready bytes/create-only writes fence uploads.
- FFmpeg/FFprobe creation is shielded until a child handle is owned; cancellation
  during creation kills/reaps the returned child. Timeout/repeated cancellation
  waits for exit before cleanup. YouTube retains N7 child-tree termination.

Cancellation does **not** hard-kill native inference threads. Draining can exceed
W or the finite renewal allowance R if native work hangs. Cancelled builds do not
send successful callbacks; ready uploads remain immutable. Set container grace
from measured jobs in N13/N15. SIGKILL, machine failure and expired leases cannot
be made graceful by Python; durable recovery remains necessary.

Application failure logs retain event/code/type and correlation, not raw
unexpected messages, tracebacks, document text, secrets or subprocess output.
Safe webhook errors remain separate from diagnostics.

## Dead-letter recovery

Service Bus controls `MaxDeliveryCount` and DLQ movement. No implemented DLQ
consumer guarantees a final callback after exhaustion. Monitor queue/DLQ counts,
message age and lock/timeout/settlement events in the authorized environment.
Inspect authorized messages, fix the underlying settings/service failure, then
deliberately resubmit the unchanged envelope/request ID to its worker queue.
Do not edit an old request or delete its receipt to force retry; changed input
requires a new operation and appropriate destination.

## Verification and API evidence

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py tests/unit/test_consumer.py tests/unit/test_artifact_publication.py tests/unit/test_media_artifacts.py tests/unit/test_process_runner.py tests/unit/test_webhook.py -q --tb=short
```

Persistent conditional/leased Blob doubles, actual worker composition, HTTPX
MockTransport, controlled executor writers and local subprocesses require no live
services or ambient credentials. Exact results/omissions: [progress](docling-rag-progress.md).

Verified installed `azure-servicebus==7.14.0` register/async callback/close signatures
against [official tagged source](https://github.com/Azure/azure-sdk-for-python/blob/azure-servicebus_7.14.0/sdk/servicebus/azure-servicebus/azure/servicebus/aio/_async_auto_lock_renewer.py)
and [Microsoft Learn](https://learn.microsoft.com/python/api/azure-servicebus/azure.servicebus.aio.autolockrenewer).
HTTP retry uses the existing pinned `httpx==0.28.1` boundary. No dependencies or
service adapters were replaced in N8.
