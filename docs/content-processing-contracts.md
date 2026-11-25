# Version-one content-processing contracts (N2)

Typed inputs, artifact results and webhook bodies are implemented in
`src/akay_convert_to_markdown/contracts/` using the existing Pydantic **2.10.4**
pin. They implement the [specification](content-processing-specification.md).
The [N11 coordinator](content-processing-ordering.md) supplies actual durable
index/delete delivery; these schema types alone are not that implementation.
N5 enables the dedicated document worker's
[version-one complete-set path](content-processing-publication.md) with explicit
technical storage settings. N6 enables the dedicated media worker's
[Blob transcript/review path](content-processing-media.md) with the same settings.
The mixed entry still runs legacy Markdown-only processing and rejects version-one jobs.

## Validate a request locally

Use `parse_request(raw, worker=..., callbacks=...)` at an artifact-capable worker's
entry boundary. Supply callback identities from controlled configuration, not
URLs from the incoming message. This function performs no network access.

```python
from akay_convert_to_markdown.contracts import parse_request

request = parse_request(raw_json,
                        worker="document",
                        callbacks={"topic-content"})
wire = request.model_dump(mode="json", by_alias=True)
```

The specification's complete JSON examples are automatically validated, and
[local fixtures](../tests/fixtures/content_processing/contracts.json) provide
opaque generic identities and a **test-only** embedding profile. No production
provider, model, tokenizer, endpoint or credential is selected by these fixtures.

| Worker / model | Required variant fields |
| --- | --- |
| `document` / `DocumentRequest` | `source.type=blob`, `contentType=document`; optional `operation` (default `convert`) and `documentOptions`. `convert` requires `destinationBlobName`. `rebuildFromMarkdown` requires a Markdown source and omits destination/extraction-review fields; it overwrites only the source's artifacts. |
| `media` / `MediaRequest` | Blob with `contentType=audio` or `video`; YouTube with `contentType=video`; `destinationBlobName`, optional `overwriteDestination`. |
| `index` / `IndexRequest` | `operation=index`, positive integer `operationSequence`, `scopeKey`, Blob `source.format=docling` or `transcript`, `sectionContext`, full `indexProfile`; optional `metadata`. |
| `index` / `DeleteRequest` | `operation=delete`, positive integer `operationSequence`, `scopeKey`, exact `indexTarget.profileId` and `collection`. No source/profile/section fields. |

Every request requires integer `schemaVersion=1`, UUID `requestId`, nonblank
opaque `contentKey` and an allowed `callback`. `payload` is an opaque JSON object,
default `{}`, forwarded without interpreting domain keys. `scopeKey` and
`contentKey` are not parsed, trimmed or case-folded. They do not grant authority.

### Strict variants and options

- Unknown fields/options, wrong types, ambiguous source fields, duplicate JSON
  keys, NaN/Infinity (including nested payload/metadata) and invalid UUIDs fail
  with a safe `InvalidMessageError`. Numeric strings and booleans are not integer
  versions/sequences/dimensions. No document options are accepted on media jobs.
- `extractSections`, `codeEnrichment`, `formulaEnrichment` and
  `overwriteDestination` are independent strict booleans, default `false`.
  Additional documents use `extractSections=false`; headings are still content.
- `documentOptions.ocrLanguage` is an optional string with exactly these values:
  `es` (Spanish), `eu` (Basque), `gl` (Galician), `ca` (Catalan), `fr` (French),
  `en` (English), `de` (German). Omission, an empty options object or omission of
  the options object selects `es`. Explicit null, empty/whitespace, wrong-type,
  uppercase, locale/engine tags and unsupported values are rejected, not normalized.
  One language is selected per conversion; this is document OCR, not translation
  or Speech. Effective request identity includes the selection: omitted and
  explicit `es` are equivalent; changing to another language changes the snapshot.
  Reconstruction validates the same language contract without running OCR.
- `operation=rebuildFromMarkdown` rejects true code/formula enrichment flags;
  ordinary code, tables and representable formula text remain parser content.
  Omit `destinationBlobName` and `extractionReviewBlobName`: the edited Markdown
  determines the existing artifact namespace. The worker replaces its JSON/review
  and deletes unused images from the current inventory without writing the Markdown. See the
  [N9A preparation guide](content-processing-reviewed-content.md) for controlled
  storage, content ownership, final review and source-free retry behavior.
- `sectionContext` is exactly `fixed` (`sectionId`, `headingPath`), `fromReview`
  (`reviewBlobName`, Docling only), or `none`. No domain IDs are required.
- `indexProfile` contains id/provider/model, optional modelRevision/deployment,
  positive dimensions/token budget, tokenizer, distance and collection. Endpoints,
  keys and dynamically loaded providers are not message fields. N9-N10 must
  validate actual tokenizer/provider/model/collection compatibility against
  controlled configuration; schema validity is not provider authorization.
- Metadata cannot set the reserved point fields `scopeKey`, `contentKey`,
  `profileId`, `operationSequence`, `chunkIndex`, `sectionId`, `headingPath`,
  `text`, `contextualizedText`, `source`, `provenance` or `metadata` itself.
- Blob references use portable relative slash-separated names, not local paths,
  query strings, fragments or URLs. Markdown destinations end in `.md` and cannot
   live inside reserved `.artifacts` directories. N5 coordinates exact destination
   and sidecar-namespace ownership, including `.md`/`.MD` aliases of the same stem.
- A YouTube source retains the original HTTPS URL and requires a supported
  individual video/11-character ID, without playlists, URL credentials, ambiguous
  query fields, escapes or fragments. See the [N7 source/network policy](content-processing-youtube.md).
  Parsing does not follow the URL; retrieval is restricted to the dedicated media
  processor after complete-set reuse checks. Review's optional `youtube` metadata
  contains matching `videoId`, canonical watch URL and nullable available title.

## Artifacts and results

`ArtifactLayout.for_destination("topics/manual.v2.md")` gives:

| Document references | Media references |
| --- | --- |
| `topics/manual.v2.artifacts/document.docling.json` | `topics/manual.v2.artifacts/transcript.json` |
| `topics/manual.v2.artifacts/review.json` | `topics/manual.v2.artifacts/review.json` |

`DocumentArtifactResult` carries Markdown, the full upstream Docling JSON object,
a typed `Review` and `DocumentArtifactRefs`. Docling Core validates its own
document schema at extraction/reload (N3/N9); N2 does not reimplement it.
`MediaArtifactResult` carries Markdown, typed `Transcript`, typed `Review` and
`MediaArtifactRefs`. It rejects mismatched transcript/review content or origin.
These are data contracts: they do not prove extraction, file existence, upload,
publication or equality of produced Markdown/transcript text (N3-N6).

Use `parse_review(raw)` and `parse_transcript(raw)` for strict artifact reads.
`Review` holds summary, ordered sections, tables/cells, **the only image
inventory**, confidence, structured warnings and engine/version. Counts must
agree with unique inventory IDs; section parents precede children at a higher
level. Additional documents carry `sections=[]`; media cannot carry document
sections, page counts or PDF confidence measurements.

Absent/unmeasured confidence, page count, duration and timestamps are `null`,
never invented zeros. Nonfinite values must be normalized to `null` by the
extractor when unavailable; nonfinite values reaching these contracts are
rejected. Transcript segments preserve text, IDs, nullable speaker/language and
nullable millisecond endpoints. IDs are unique, known starts stay ordered,
known ranges are nonnegative/end-after-start and do not exceed known duration.
Warnings for unavailable Speech times and normalization are N6 responsibilities.

## Webhook bodies

`parse_event(raw)` validates these exact variants. Builders copy the request
identity and opaque payload; they do not send HTTP requests.

| Builder / event | Result fields |
| --- | --- |
| `conversion_completed` / `document.conversion.completed` | Source, Markdown destination, content type, document artifacts (`doclingJsonBlobName`, `reviewBlobName`) **or** media artifacts (`transcriptJsonBlobName`, `reviewBlobName`). Artifact paths must match the destination. |
| `index_completed` / `content.indexing.completed` | Scope/sequence and `index={profileId,chunkCount}` (nonnegative integer). |
| `index_completed` / `content.index.deleted` | Scope/sequence and `index={profileId}`. No chunk count or Blob deletion. |
| `index_superseded` / `content.index.operation.superseded` | Scope/sequence and strictly greater `currentOperationSequence`. |
| `request_failed` / `document.conversion.failed`, `content.indexing.failed`, `content.index.deletion.failed` | Recoverable identities, index operation/sequence where applicable, payload and `error={code,message}`. Caller supplies a safe message, never raw exception/log content. |

Document completed bodies include `operation=convert|rebuildFromMarkdown`;
document failures include it when recoverable. Media bodies do not acquire a
document operation. For reconstruction, `destinationBlobName` in the event equals
`source.blobName`, even though no Markdown is written. The updated review contains
`processing.operation=rebuildFromMarkdown`, no original-review reference and only
the images still referenced by the edited Markdown. Repeated rebuilds accept the
current review, including a previous rebuild. New text has no original page or
confidence claims. Historical review references remain readable for compatibility.

There is no `images`, `imagesPrefix`, binary image data or alternate
`transcriptionJsonBlobName` in a completed webhook. No manifest/report/HTML
artifact is introduced. Partial failure bodies can omit unrecoverable content,
source or index identity; valid UUID `requestId`, schemaVersion and safe error
remain required. Callback allowlisting/recovery and transport settlement remain
the worker's responsibility (N8); no webhook is invented for a poison message.

The version-one `idempotency_key(event)` is `{requestId}:{eventType}`. The
existing legacy HTTP header format remains unchanged. A receiver must deduplicate;
building the header does not enforce it or indicate teacher acceptance.

## Request identity and ordered-operation acceptance

`RequestIdentity.capture(request)` snapshots effective aliased JSON, including
defaults, with sorted object keys, compact UTF-8 JSON and finite numbers. The
immutable string preserves nested payload/configuration independently of later
mutations of caller dictionaries. Pydantic's frozen fields alone are **shallow**;
do not use a mutable model object as a durable request identity.

`IndexReceipt` is a serializable **admission contract**, not an implemented Blob
coordinator or a published consumer artifact. It carries latest admitted/completed
request identity and older admitted identities. `index_admission` evaluates it:

| Incoming operation versus recorded state | Decision |
| --- | --- |
| No receipt, or a new request with a greater sequence | `admit` |
| Exact latest request/parameters, admitted but unfinished | `resume` |
| Exact latest request/parameters, completed | `replay` |
| Older unchanged operation | `superseded` |
| Reused request ID with changed parameters, or occupied sequence with another request/parameters | `conflict` |
| Different scope/content state supplied by the caller | Reject the mismatched receipt. |

The comparison includes profile/collection and section changes, but coordination
is keyed solely by exact `(scopeKey, contentKey)`. `operationSequence` is an
operation counter, not a document version. Tests serialize/reload receipts and
cover an old index after a completed delete and later reassignment.

N11 implements durable reads/writes, leases/ETags, history, mutation progress,
completed outcomes and fail-closed uncertain-write recovery; see the
[ordering guide](content-processing-ordering.md) for its local evidence and pending
Azure/Qdrant-server checks. Calling this pure helper alone is not durable
coordination and cannot prevent a mutation race. N10 enforces immutable profiles.
The [N16 handoff](content-processing-handoff.md) provides validated routed samples
and the future consumer's approval/current-result/deduplication responsibilities.

## Verification and next integration

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"
.venv\Scripts\python.exe -m pytest tests/unit/test_content_contracts.py -q --tb=short
.venv\Scripts\python.exe -m pytest -q
```

Tests validate all complete specification examples, source/routing variants,
strict options, results, null/absent measurements, receipt decisions and the
current consumer's fail-closed boundary. They use local JSON and existing doubles.
No Azure, Speech, YouTube, embeddings or Qdrant access is required.

API evidence: [Pydantic v2.10.4 strict mode](https://github.com/pydantic/pydantic/blob/v2.10.4/docs/concepts/strict_mode.md),
[discriminated unions](https://github.com/pydantic/pydantic/blob/v2.10.4/docs/concepts/unions.md)
and [configuration source](https://github.com/pydantic/pydantic/blob/v2.10.4/pydantic/config.py).
Context7's closest indexed version (2.10.6) was cross-checked against these exact
2.10.4 sources and the installed pin; no dependency upgrade was needed.

The OCR-language contract amendment and **N3 extraction integration are complete**:
the local adapter honors the selection, all seven resources initialize, and real
PDF/scanned-PDF invocation/export tests pass. Upstream OCR quality limitations
remain documented without claiming repairs. Activate each new runtime contract only with its requisite extraction,
review/publication behavior (N3-N6), and preserve legacy compatibility explicitly.
N5 activates that path for documents; N6 activates it for Blob media. A Markdown-only
legacy success never counts as version-one publication. N7 adds bounded YouTube
retrieval to the same dedicated media flow, preserving original URL provenance
and notification-only package reuse. Actual platform interoperability remains unverified.
