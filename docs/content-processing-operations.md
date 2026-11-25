# Operate the three workers and track external verification

Use separate document, media and index queues/apps. Publish availability only after
the consumer's current approval/preparation/index result, not a conversion callback.
This guide describes the implemented Python boundary and the still-required
authorized integration work. The [handoff](content-processing-handoff.md) provides
the runnable local flow, complete examples and future .NET/data responsibilities.

## Configuration and routes

| Worker | Required configuration beyond shared Blob/Service Bus/callback budgets |
| --- | --- |
| `akay-convert-document` | `DOCUMENT_SERVICEBUS_QUEUE_NAME`, output container and paired publication-state container/prefix; explicit local Docling bundle for PDF. Default concurrency 1. Both document operations use this route. |
| `akay-transcribe-media` | `MEDIA_SERVICEBUS_QUEUE_NAME`, output/publication-state settings, Speech endpoint/key and FFmpeg/FFprobe; pinned yt-dlp/EJS/Deno for explicit YouTube. No document/index settings. |
| `akay-index-content` | `INDEX_SERVICEBUS_QUEUE_NAME`, saved-final-artifact source container, technical state, immutable profiles, local tokenizer, explicit Azure embedding endpoint/deployment/authentication and Qdrant target/authentication. No Speech/FFmpeg/output container. Missing adapter settings exit 2 before credential construction/consumption. |

Exact variable inventories: [README](../README.md#environment-variables),
[publication](content-processing-publication.md), [YouTube policy](content-processing-youtube.md),
[embedding configuration](content-processing-indexing.md) and
[index runtime](content-processing-ordering.md#configure-before-starting).
Only AzureOpenAI / text-embedding-3-small / 1536 / cl100k_base is approved as a
model selection; full production profile/endpoint/deployment/quotas are pending.
Runtime Blob/Service Bus authentication is separate from Speech, embedding,
Qdrant, GHCR publication/pull and deployment OIDC authentication.

Supply all known queue assignments to detect local collisions. Stop/drain the old
mixed consumer and coordinate producers before reusing any old queue. The existing
legacy command still supports Markdown-only envelopes; it does not accept version
one. Queue validation cannot discover other deployments or inspect backlogs.
There are three queues, no Topics/subscriptions, YouTube queue or ingress server.

## Observe and recover

Correlate safe event/code/type logs by request ID, content/scope and sequence where
available; retain exact request snapshots/receipts through recovery. Do not log
document text, secrets, arbitrary exception messages or subprocess output. Configure
queue/DLQ age/depth, lock loss, workflow timeout, callback failure, deployment exit/
restart and uncertain-index-lane monitoring in the authorized environment. Such
cloud dashboards/alerts are not installed by this repository.

| Observed condition | Operator action / invariant |
| --- | --- |
| Callback failure after publication/index | Retry the unchanged envelope/UUID. Durable outcomes skip confirmed extraction/embeddings/mutations. A callback may repeat; receiver must deduplicate and check current request/sequence. Complete the message only after a successful callback. |
| Definitive preparation failure | Safe operation-specific failed callback is persisted/replayed; a changed attempt needs a new UUID and suitable separate output. Do not edit the same immutable request to force retry. |
| Transient 429/5xx/network/configuration | Repair the explicitly configured dependency, allow bounded retries/redelivery. No definitive failure is promised for every temporary fault or after delivery exhaustion. |
| Workflow/lock/lease loss or shutdown | Admission stops; active work cancels/drains with ownership retained. Native inference is not hard-killed by cancelling its await. Do not delete temp/state or start competing writers while work may still run. Tune workflow/renewal/grace from actual workload measurements. |
| DLQ | Service Bus owns MaxDeliveryCount. Inspect authorized exact messages, repair the underlying cause, deliberately resubmit the unchanged request to the correct route. There is no automatic DLQ final webhook or recovery consumer. |
| Incomplete/unowned artifact set | Do not treat existing Markdown as success or force overwrite. Preserve receipt/staging/namespace ownership; retry identical ready state or choose an authorized new destination for different content. Never sweep a broad consumer prefix. |
| Uncertain Qdrant mutation | Keep the target lane blocked. Lease expiry alone does not fence a delayed write. Stop writers, establish quiescence and reconcile exact lane/intent/points before separately authorized conditional repair. No admin unblocking command exists; do not erase pending/receipts or break leases as a shortcut. |
| Reassignment/removal | Exclude obsolete domain associations immediately; explicit scoped delete and higher-sequence index retain original/derived artifacts. No index operation changes domain rows or owns file cleanup. |

See [reliability](content-processing-reliability.md),
[complete-set publication](content-processing-publication.md) and
[ordered-lane recovery](content-processing-ordering.md#recover-an-uncertain-lane)
for exact behavior. Multi-batch index writes can be visible before completion;
domain accepted-state filtering is required. Blob/Qdrant/HTTP/domain data do not
share a transaction.

## Build, release and rollback

1. Reproduce the pinned [three-image builds/smoke](content-processing-images.md).
   The document model/tokenizer bytes are explicit locked inputs, readable by
   UID 10001 offline; media tools and index/extraction dependencies are isolated.
   Supply bounded writable temporary storage. Fixture resource observations are
   not production sizing or termination guarantees.
2. [CI](content-processing-ci.md) tests before builds and all offline smoke phases.
   GHCR publishing requires explicit manual authorization/configuration. Retain
   one complete SHA/run/attempt identity and all three confirmed digests. Partial
   pushes are not a release; deployments never use `latest`.
3. Follow the [deployment prerequisites and cutover/rollback](content-processing-deployment.md).
   Apps/queues/identities/Key Vault/state must already exist; the prepared workflow
   updates one app at a time through protected environment/OIDC gates. Scaler RBAC
   and GHCR pull credentials are separate from worker/runtime/publisher rights.
4. Preserve previous complete digests **and full compatible configuration**. Pause
   affected routes, drain/reconcile in-flight work and apply each previous role
   explicitly if rollback is authorized. Restoring a revision alone does not
   restore app-level configuration or undo durable state. No automatic cutover,
   publication, resource creation or rollback is performed by local checks.

## Local acceptance map

References below are executable checks plus recorded evidence, not a claim of
cloud/.NET completion. Test paths are under `tests/`; image results and exact runs
are retained in [progress](docling-rag-progress.md).

| Specification §19 criteria | Local evidence / boundary |
| --- | --- |
| 1–2: IDs, principal/additional | `unit/test_document_artifacts.py`, `test_content_chunking.py`, `test_content_handoff.py`; shared UUID vectors, repeated/nested headings, preamble and additional internal headings. |
| 3, 6, 22, 24: extraction/options/formats/OCR | `unit/test_docling_conversion.py`, opt-in `integration/test_docling_models.py`, document image phases. Actual four flags, seven resource initializations, Spanish raster/overlay extraction and model-free formats. OCR/layout quality limits below remain. |
| 4, 17: image inventory/JSON/safety | `unit/test_document_artifacts.py`, `test_reviewed_content.py`, `test_content_contracts.py`; actual crops, only review inventory, no page-image exports, strict examples/no nonfinite JSON; edited links remain unfetched/tolerated. |
| 5, 16: independent engines/images/config | `unit/test_worker_boundaries.py`, `test_packaging.py`, `test_images.py`, `test_ci_release.py`, `test_deployments.py`; actual isolated installs/three images and offline app configuration. Remote publication/deployment is separate. |
| 7–8, 18: media routing/segments/offline default | `unit/test_media_artifacts.py`, `test_youtube_source.py`, `test_content_handoff.py`; Speech/extractor/process fixtures and real offline media image tools. No live YouTube/Speech claim. |
| 9–11: saved inputs/chunks/replacement | `unit/test_content_chunking.py`, `test_content_indexing.py`, `test_ordered_indexing.py`, N10 probe and N16 real-tokenizer harness; persistent local Qdrant, no reconversion and bounded context. Synthetic embeddings do not test retrieval relevance. |
| 12–14: scoped deletion/preservation/order | `unit/test_ordered_indexing.py`, `test_content_handoff.py`; explicit detach/reassign, old work superseded and all file bytes retained. Future domain FK/filter behavior remains .NET work. |
| 15: partial/callback/lease/timeout/shutdown | `unit/test_artifact_publication.py`, `test_worker_reliability.py`, `test_ordered_indexing.py`; doubles enforce leases/ETags and delayed/lost outcomes. Actual Azure expiry/server replication/load remain pending. |
| 19–20: final edited artifacts/diagnostics | `unit/test_reviewed_content.py`, `test_content_indexing.py`, `test_content_handoff.py`; final text/headings/ref mapping, separate reports/shared image preservation, null final page/confidence and current JSON indexed. |
| 21: corrected transcript | `unit/test_reviewed_content.py`, `test_content_handoff.py`; changed text/unchanged segment identity/order/times/origin reach chunks/points without Speech. Fixture persistence is not an editor implementation. |
| 23: approval lock/explicit index | Handoff contract, standalone queue paths and N16 no-index-on-conversion assertion. Actual .NET locks/authorized approval/latest-callback handling are not verified. |

### Known failed, skipped and unverified checks

- Known separate diagnostics: strict Spanish OCR accent fidelity fails on the
  controlled scans; Linux native layout does not classify the synthetic formula.
  Neither diagnostic is weakened/xfail or repaired. Actual integration/crop
  inference passes; no character-perfect OCR claim. Real OCR quality in **eu, gl,
  ca, fr, en and de** is individually unmeasured; resources for all seven load.
- Default host suite has 18 intentional integration omissions: 13 local-model
  opt-ins, two separate quality diagnostics, Azure Blob disabled, absent host
  FFmpeg/FFprobe and absent Speech configuration. Container tool/model results are
  separate observations, not a claim those skipped host tests ran. Two upstream
  OCR-option serialization warnings remain.
- Offline Blob doubles do not prove Azure lease/ETag/expiry/RBAC/cross-process
  interoperability. Local Qdrant does not prove server transport, strong-order
  replication or payload-index acceleration. Stub vectors do not establish
  production embeddings or semantic search.

## Remaining external actions, in dependency order

These require their own explicit destinations/credentials/authorization. They are
not another implicit N-task and must not be executed merely to close this handoff.

1. **Consumer/data owner:** implement the separate Akay.Be editor/draft/segment-text
   persistence, approval freeze, final-section persistence, nullable associations,
   reliable producer/inbox, sequence allocation, retrieval permissions and exact
   cleanup from the [manual handoff](content-processing-handoff.md#consumer-owned-data-and-manual-database-handoff).
   Reconcile the real schema first; no migration was created here.
2. **Environment owner:** approve physical queues/GHCR repos/apps/environment,
   full immutable profile/collection/budgets, Blob/output/state access, callback
   URLs/authentication and runtime/scaler/pull/OIDC identities/RBAC. Provision the
   selected Azure embedding resource/deployment later with authorization; none
   exists or is inferred from the sample deployment string. Approve Qdrant hosting,
   credentials, quotas, Speech locale policy and supported YouTube usage.
3. **Release owner:** authorize an actual GitHub Actions/Linux-host run, exact
   public-source asset acquisition/cache, all builds/smoke and complete GHCR
   publication/digest artifact retention. Local Docker IDs are not remote release
   digests. No push/publication was performed for this task.
4. **Deployment owner:** bootstrap missing authorized resources, validate/apply
   reviewed pinned CLI/ARM settings, verify image pull/Key Vault/RBAC/network,
   non-root writable volumes/model/tokenizer access and every separate scaler.
   Prepared YAML/ARM or control-plane success does not prove readiness.
5. **Integration/operator owners:** authorized staging Blob/Service Bus/webhook/
   Speech/YouTube/Azure embeddings/Qdrant-server flow, current-callback/replay/
   reassignment/delete ordering, DLQ and uncertain-write procedures; measure
   concurrency, memory/time/temporary capacity, scale-from-zero and termination
   under load. Coordinate producer cutover and rollback, then verify actual .NET
   acceptance/filtering/chat behavior separately. Keep affected routes paused
   until compatible settings and results are established.

N0–N16 plus N9A have a locally verifiable completion boundary. The next fresh
session should select **one explicitly authorized external integration follow-up**;
there is no N17 or automatically authorized live test/deployment.
