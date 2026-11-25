# Reproduce the local pipeline and integrate a consumer

N16 supplies an offline end-to-end harness, validated requests and a fixture-only
callback receiver. The Python implementation is locally verified; **Akay.Be's
editors, approval/persistence, chat and cloud integration are not implemented or
verified by this handoff**. Start with the local flow, then use the consumer
contract below. Operational recovery and remaining external actions are in the
[operator guide](content-processing-operations.md).

## Reproduce the handoff

Use the Python 3.12 development installation from the
[packaging guide](content-processing-packaging.md), including all three engine
targets and test tooling. This repository-level harness deliberately reuses the
existing test doubles; it is not shipped in the worker wheels/images.

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS='false'
$env:RUN_DOCLING_MODEL_TESTS='false'
$env:RUN_DOCLING_QUALITY_DIAGNOSTICS='false'
.venv\Scripts\python.exe -m pytest tests/unit/test_content_handoff.py -q --tb=short
.venv\Scripts\python.exe -m tools.content_processing_demo --tokenizer .local/cl100k_base.tiktoken --output .local/n16/handoff-01
```

Supply the existing explicitly prefetched `cl100k_base` file. Its official hash
is validated before use; there is no tokenizer download/cache fallback. Choose a
**new** output directory for each run; the harness refuses to overwrite evidence.
On Linux substitute the venv Python path. Neither command requires cloud settings.

The harness uses real document extraction (model-free Markdown), rebuild/export,
publication, strict parsing, the shared consumer's processing/settlement path,
HybridChunker, the local tokenizer, ordered index/delete and persistent Qdrant
client local mode. Conditional leased Blob state, receiver/lock renewal, FFmpeg
process output, Speech HTTP responses, YouTube retrieval and embeddings are
explicit doubles. Default tests inject a character counter; the CLI uses the real
hash-verified tokenizer. Synthetic vectors test data flow, **not semantic quality**.

Environment scrubbing, an empty home, socket/DNS guards and a credential-constructor
trap prevent accidental service access. The demo creates no Service Bus client,
Azure resource or domain database. Deliberate callback acknowledgement loss emits
two `document.processing.failed` log entries; both messages are abandoned once and
then complete from durable outcomes. These are expected recovery cases.

| Generated technical evidence | Inspect |
| --- | --- |
| `report.json` | `passed-local-only`, eight successful boundary checks, 13 completions and two intentional abandons; never deployment status. |
| `requests.json`, `events.json` | Effective sample requests and 13 unique callbacks (15 deliveries). Real final section IDs replace illustrative association IDs in the running demo. |
| `sources/`, `artifacts/` | Original and edited Markdown, updated JSON/review in place, additional document, three media packages and consumer-corrected transcript/Markdown. |
| `qdrant/` | Test-only local point persistence, reopened and checked before success. This is generated technical data, not a domain migration or public artifact. |

The flow verifies current final text/sections, repeated headings without collisions,
null final text page diagnostics, no fetched image links, additional internal
headings without Akay markers, all three media routes, corrected segment citations,
source-free callback replay and higher-sequence reassignment without reconversion.
Deleting a principal's points leaves additional points/files intact; detaching an
additional explicitly deletes only its points. An older index is superseded and
cannot resurrect them. All source/published bytes survive the deletes/reassignment.
Figure-byte preservation and actual PDF/OCR/codec/engine inference are covered by
the existing focused suites and image checks, not fabricated by the Markdown demo.

## Validated request examples and routing

Every complete envelope in
[`handoff-requests.json`](../tests/fixtures/content_processing/handoff-requests.json)
is validated automatically. All `fixture:*` keys, deployment/profile/collection,
budget/distance, UUID associations and paths are **synthetic**, not production
settings, authorization or a public YouTube test target. Do not send them to live
queues. Build real envelopes from authorized current records and returned paths.

| Example | Dedicated route / prerequisite |
| --- | --- |
| `principal` | Document: `convert`, `extractSections=true`; original remains in its source Blob. |
| `additional` | Document: `convert`, `extractSections=false`; no domain sections, keep internal headings. |
| `rebuild` | Document: edited Markdown, same content key/new request ID; overwrite its JSON/review, prune unused images, never write Markdown; no destination/extraction-review input or enrichment/OCR. |
| `audio`, `video`, `youtube` | Media: Blob audio/video or one explicit YouTube video; same worker/queue. |
| `indexPrincipal` | Index: final Docling JSON plus final review, `fromReview`. |
| `indexAdditional` | Index: additional Docling JSON, `fixed` accepted parent section/context. |
| `indexTranscript` | Index: saved corrected transcript, `fixed`; unchanged transcripts can use the original coherent media package. |
| `deletePrincipal`, `deleteTranscript` | Index: exact scope/content/profile/destination. No Blob/domain deletion. |
| `reassign` | Index: greater per-content sequence, saved artifacts, explicitly selected new section/path. No new transcription. |

Callback is a configured identity, not a URL in the envelope. Source and review
containers are controlled worker settings, not per-message overrides. Index
`SOURCE_CONTAINER_NAME` must read the final artifacts sent by the consumer.
Physical queue names are integration inputs; the retained mixed command accepts
only legacy envelopes and must not compete on dedicated routes.

## Run the local callback receiver

```powershell
.venv\Scripts\python.exe -m tools.callback_receiver --api-key n16-fixture-key --port 8765 --fail-after-accept
```

This explicitly synthetic key is only for this fixture. The server binds only
`127.0.0.1`; POST to `/callbacks` using `X-Api-Key` and
`Idempotency-Key: {requestId}:{eventType}` with a valid version-one event. Configure
an explicitly local test sender's callback mapping to this URL. The default demo
uses the **same inbox through HTTPX MockTransport**, not this listening server;
the focused test additionally exercises an actual loopback server/WebhookClient.
No inbound HTTP listener is added to any worker image or Container App.

The receiver validates strict event JSON and the exact key, deduplicates equivalent
repeats, returns 409 for changed bodies under the same key, and optionally returns
503 **after storing the first event** to model a lost acknowledgement. Bodies are
limited to 1 MiB and 1000 unique events in memory; unknown paths fail. Ctrl+C stops
it and prints counts only. It does not log bodies/keys or fetch credentials.
It forgets all receipts on restart and has no authorization/approval/current-state
logic: **it is not the future production webhook endpoint**.

## Consumer-owned data and manual database handoff

These are conceptual integration requirements, not SQL, DDL, migrations or a
claim about the current Akay schema. The Akay.Be/data owner must map them to the
actual authorized model in a separate task. Python never reads its tables.

| Concept | Information/invariant the consumer must preserve |
| --- | --- |
| Content | Stable opaque content key, topic/role (principal/additional), original Blob/YouTube source, options and exact Markdown/JSON/review references returned by the current request. One active textual principal per Topic. |
| Final sections | GUID, parent GUID, title/level/order/Docling ref from the **accepted final** review. Persist only principal sections. Repeated titles are not identities. |
| Additional assignment | Nullable section association so retiring/replacing a principal cannot cascade-delete additional contents or their original/derived files. Detached items are excluded until explicit reassignment. |
| Review/edit lifecycle | Draft and corrected segment text, current conversion/preparation request, frozen approval input, edit lock and acceptance/availability. No approved-document edit/history feature: subsequent change requires deletion/new upload with a new content identity. |
| Immutable profile | Full id/provider/model/revision-if-known/deployment/dimensions/tokenizer/token-budget/distance/collection snapshot, display/active status if needed, **no secrets**. Preserve previously used destinations for exact cleanup. |
| Index coordination | Monotonically increasing operation sequence per exact scope/content **across profiles**, operation request ID/snapshot, pending/completed result and used destinations. Sequence is not a document version. |
| Reliable delivery/inbox | Durable producer publication/retry, authenticated callback identity, dedupe receipts and current-request/sequence checks coordinated with domain persistence; identical redelivery keeps the UUID and entire envelope. |

### Approval and publication order

1. Convert and show Markdown with authorized review/image access. Sections/grades
   are provisional extraction diagnostics; sanitize untrusted text/HTML and avoid
   server-side arbitrary resource fetching.
2. Before approval allow Markdown text/headings, or only existing transcript
   segments' `text`, to change. Do not edit images, segment IDs/order/times/speaker/
   origin or add/remove/merge segments. Enforce nonempty text and size limits.
3. Freeze the input and lock editing on approval. For changed Markdown issue
   `rebuildFromMarkdown`; for no edits reuse the coherent initial artifact set.
   For corrected media save transcript JSON **and regenerate matching Markdown**
   without Speech. That persistence/editor is not a Python worker operation.
4. Accept only the current preparation result. Rebuild overwrites JSON/review and
   deletes unused inventory images; the edited Markdown remains untouched. Final
   text grades/pages are unavailable, not inherited. Unknown image links are not fetched.
5. Persist final sections before attaching additionals. Explicitly enqueue index
   with final artifact references and an immutable configured profile. Conversion
   completion never triggers index automatically. A failure remains retryable with
   the edit lock retained; do not expose partial preparation/indexing as available.
6. Accept only the current index result before enabling retrieval. A superseded
   event cannot reactivate content. Duplicate or old extraction callbacks cannot
   replace final artifacts, unlock editing or reverse an approved deletion.

### Retrieval, detachment and cleanup

- Construct exact `scopeKey` filters from the authenticated backend context, plus
  accepted/available content, current section associations and user permissions.
  Browser-supplied scope/content IDs never establish authorization. Synthetic-vector
  tests do not prove .NET retrieval, chat or exercise generation. For whole-material
  exercises, top-k retrieval alone is not complete coverage.
- Query embeddings must use the same effective model/deployment/space/preprocessing
  as indexed documents. Equal dimensions alone are insufficient. A changed profile
  creates a new ID/destination and explicit reindex/old-destination cleanup.
- Retire a principal: exclude affected associations from retrieval immediately;
  preserve additionals, detach them, send explicit scoped deletes where required,
  and associate them only after new final sections exist. Never auto-match by title
  or ordinal. Reassignment uses greater-sequence index jobs and existing artifacts.
- Permanent additional deletion coordinates exact index cleanup, owned artifact
  references and domain record cleanup with retries. Index `delete` does not perform
  the latter two. Keep shared extracted images/reports while referenced. No broad
  Blob-prefix sweep, cascade deletion or transaction across Qdrant/Blob/domain data
  is implied. Record every used profile destination for cleanup.

## Acceptance evidence and remaining work

[Progress](docling-rag-progress.md) records exact RED/GREEN, regression, real-tokenizer
and image-check commands/results. [Operations](content-processing-operations.md)
maps the acceptance criteria to checks and lists pending external actions. Local
completion is the handoff boundary, not deployment or a working .NET approval/chat
workflow. No production embedding deployment, credentials or physical destinations
are inferred from these fixtures.

API evidence for the harness: pinned
[HTTPX 0.28.1 MockTransport](https://github.com/encode/httpx/blob/0.28.1/docs/advanced/transports.md),
[environment opt-out](https://github.com/encode/httpx/blob/0.28.1/docs/environment_variables.md)
and [Qdrant client 1.19.1 local/async mode](https://github.com/qdrant/qdrant-client/blob/v1.19.1/README.md).
Docling/Blob/ordering APIs are reused without pin changes; their exact-version
references remain in the feature guides.
