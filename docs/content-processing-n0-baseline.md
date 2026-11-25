# N0: compatible baseline and implementation decisions

Checked on 2026-11-13 at `f03c7a4`. This is the baseline for the
[three-worker specification](content-processing-specification.md), not an
implementation of its runtime contracts. See [progress](docling-rag-progress.md)
for observed checks and the next task.

## Compatibility and reuse map

| Observed implementation / prior work | Reuse and remaining work |
| --- | --- |
| `main.py`, `Settings`, one console command and one mixed document/media consumer | Retain technical wiring; N1 separates three entry points, settings and dispatch. No new consumer may compete on the existing mixed queue. |
| `DocumentConverter.convert(Path) -> str`, MarkItDown adapter using `asyncio.to_thread` | Retain the conversion boundary and format coverage. N2 introduces typed artifacts; N3 replaces the adapter with Docling and makes inference cancellation-safe. |
| `ConversionRequest` accepts Blob, opaque payload and callback; ignores unknown envelope fields | Retain payload/routing behavior. No `schemaVersion`, `contentKey`, document options or index contracts are implemented. N2 must enforce the new variants. |
| `BlobStorage` streaming/authentication, atomic single-blob non-overwrite upload | Reuse clients and error handling. Current Markdown existence check is insufficient for N5's complete artifact set and provenance checks. No durable publication receipt/lease exists. |
| Speech normalizes phrase segments in seconds; audio/video processors publish Markdown only | Reuse Speech/FFmpeg, format detection, size/duration checks and local doubles. N6 retains validated nullable times, language/speaker/origin and publishes transcript/review JSON. Existing missing timestamps default to zero; this does not meet the new contract. |
| Consumer settlement, lock renewal, allowlisted/authenticated callbacks, retries, safe-log helpers, temporary execution directories | Reuse tests and helpers. N8 still needs whole-workflow lock budgets, stable notification receipts, lease-loss and cancellation/shutdown evidence. |
| No principal/additional distinction, section extraction, figure inventory, YouTube adapter, chunking, embedding client or Qdrant path | Implement only in their assigned tasks. Backend acceptance/reassignment/deletion responsibilities remain a later integration contract, not Python database work. |
| One Dockerfile with FFmpeg; one GHCR workflow, no test step or Azure deployment job | N12-N15 separate dependencies/images and gate release/deployment. Existing workflow tags before build and publishes on main push; it is not evidence of target CI/CD completion. |
| Historical T0 documents and synthetic probe under `versión old/` | Reuse the exact-version API evidence and unchanged probe. Historical T0 remained pending; it does not complete N0 or N1-N16. Preserve old records/fixtures as historical inputs. |

### Superseded T0 assumptions

The new specification controls: `akay-section:start` immediately before a
structural heading, UUID identifiers, no end marker; principal-only sections;
images inventoried only in review JSON; timed media JSON; three workers/queues;
full immutable index-profile snapshot; optional internal fingerprint; ordered
index/delete operations across profiles. Do not copy the old paired `section`
fixture, webhook image-list idea, required fingerprint, two-image topology or
old T0 schema deliverables into the implementation. New typed schemas/fixtures
belong to N2.

## Retained exact-version API baseline

Keep the compatible T0 selection: Docling/docling-slim **2.141.0**, docling-core
**2.99.0**, Python **3.12**. The project still pins MarkItDown **0.1.1**, HTTPX
**0.27.2**, Pydantic **2.10.4**, pydantic-settings **2.7.1**. No project pins change
in N0. Incorporation needs the previously resolved HTTPX **0.28.1** and settings
**2.14.0** replacements; retain Pydantic **2.10.4** where compatible. The prior
Windows resolver success is historical evidence, not a Linux/CPU lock or a new
resolver run in this session. Dependency installation/regressions belong to N3;
isolated target locks belong to N12.

| Requirement | Rechecked against the pinned API |
| --- | --- |
| Standard / docling_parse | `PdfFormatOption` defaults to `StandardPdfPipeline` and `ThreadedDoclingParseDocumentBackend`. |
| Heading hierarchy | `PdfPipelineOptions.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)`; retain `generate_parsed_pages=True` for the font-style signal. Synthetic repeated headings retain distinct references on reload; real inference is not tested. |
| Bounded OCR / tables | `RapidOcrOptions(backend="onnxruntime", mode=OcrMode.PDF_AWARE_LAYOUT_REGIONS)`, `do_ocr=True`, accurate table mode. No full-page OCR forcing. OCR languages, weights and asset locks remain N3/N12-N13 work, not inferred from library defaults. |
| Optional enrichment | Code/formula flags exist independently and default false; picture classification/description, remote services and external plugins remain disabled. Four real feature combinations still need N3 tests. |
| Confidence | `ConversionResult.confidence` is `ConfidenceReport`; missing component scores can be NaN and grades `unspecified`. N4 normalizes absent/non-finite review values to null, never zero; raw upstream aggregates are not a safe review serializer. |
| Referenced figures / reload | Relative `artifacts_dir=Path("images")`, referenced Markdown/JSON export, real synthetic PNG existence, distinct heading refs and reload pass without image fetching. Windows JSON separators need portable URI normalization. This does not prove production image naming or page-image exclusion. |
| Broken text layers | No `replace_broken_text_layer` field in PDF pipeline, PDF backend or threaded parser backend options. Do not invent a flag or describe OCR merging/`force_backend_text` as universal repair. N3 must test broken-layer fixtures and surface explicit conversion failure for incomplete extraction rather than silently reporting completed; partial-but-recoverable warnings need evidence. |
| HTML/Markdown resources | `fetch_images`, `enable_remote_fetch`, `enable_local_fetch` default false. N3 must enforce these boundaries and test blocked-network extraction. |

The no-inference probe is [checks/content_processing_n0_probe.py](checks/content_processing_n0_probe.py).
It reuses the old probe and adds backend/ConversionResult checks and the UUID
vectors below. It neither constructs a conversion pipeline nor downloads models.

## Frozen technical decisions

### Artifact layout

Use the complete POSIX Blob destination, remove only its final Markdown suffix,
and append `.artifacts/`. Preserve the parent path, case and other dots:

| Markdown | Sidecar directory |
| --- | --- |
| `topics/25/document.md` | `topics/25/document.artifacts/` |
| `topics/25/notes.md` | `topics/25/notes.artifacts/` |
| `manual.v2.md` | `manual.v2.artifacts/` |

Document sidecars are `document.docling.json`, `review.json` and necessary
`images/` files. Media sidecars are `transcript.json` and `review.json`.
Return exact Blob paths, never SAS/local paths. Only review JSON inventories
images; no public manifest or second webhook inventory. N2/N5 validate accepted
destinations, portable links and conflicting namespace reservations (including
destinations inside another publication's artifact directory). Originals stay put.

### Section UUID namespace and canonicalization

Freeze namespace UUID **`bdac804b-e605-5299-872e-42443fecc0c9`**. Its reproducible
derivation is UUIDv5 of the standard URL namespace and the exact name
`urn:akay:convert-to-markdown:section:v1` (a namespace label, not a network URL).
N4 will implement ONE shared section-ID function used by all exporters:

1. Serialize `["section-v1", contentKey, doclingItemRef]` as JSON using
   `ensure_ascii=False`, `separators=(",", ":")`, `allow_nan=False`.
2. Use that exact Unicode string as the UUIDv5 name (UTF-8 encoding).
3. Emit the lowercase, hyphenated UUID string. Do not trim, case-fold, normalize
   Unicode, parse domain prefixes or include request ID, title or heading level.

| contentKey | doclingItemRef | Expected section ID |
| --- | --- | --- |
| `topic-content:501` | `#/texts/0` | `c1a3cc1f-4beb-5058-ba1e-51af764fccd7` |
| `topic-content:501` | `#/texts/1` | `7172ce0f-1a0b-5376-a8ed-871bbb1227fc` |
| `manual:á` | `#/texts/0` | `59db2df5-39db-5dad-abdf-677402b8512d` |

JSON arrays avoid ambiguous delimiter concatenation. Repeated titles do not
collide when item references differ. References are stable only for the same
source and pinned processing configuration; parser/model changes have no such
guarantee. Follow specification section 7 for boundaries, hierarchy, preamble
`sectionId=null`, excluded page furniture and `extractSections=false` behavior.
The specification's illustrative UUID need not match these new decision vectors.

### Durable coordination

Choose Blob technical state with renewable finite **blob** leases and conditional
ETag/create writes, reusing the existing storage integration instead of adding a
database or coordination service. This is a design choice; no coordinator is
implemented or cloud-verified in N0.

- N5 coordinates by storage account/container/exact Markdown destination, with
  persisted source/options/contentKey identity, attempt ownership, complete-set
  receipt and notification result. Reuse requires a coherent, matching artifact
  set, not merely an existing Markdown. Reserve/check artifact ownership too.
- N11 coordinates by exact `(scopeKey, contentKey)` independent of profile or
  collection. Persist admitted operationSequence, request/parameter identity,
  destinations, mutation progress and confirmed outcome. Sequence is an operation
  counter, never a document version. Repeated/conflicting/stale jobs follow
  specification 5.2, including the superseded event.
- Encode technical state keys from SHA-256 of compact UTF-8 JSON arrays of the
  respective identity components, with separate publication/index key spaces;
  store and compare the full identity in the record. Never embed raw opaque keys
  into local paths or use broad consumer-prefix cleanup. The controlled state
  container/prefix and permissions are deployment inputs, not public artifacts.
- Leases protect their Blob, not Qdrant or every artifact automatically. ETags
  detect conflicting state writes; neither mechanism creates a cross-service
  transaction. N5/N8/N11 must prove ownership checks, lost-lease handling,
  in-flight mutation draining/recovery, and no late resurrection after delete.
  A local mutex or checking a lease once before a Qdrant write is insufficient.

Finite leases trade renewal/recovery complexity for crash recovery without an
indefinite orphan lock. This choice avoids new domain tables but does not waive
the race/recovery acceptance tests or authorize provisioning technical storage.

## Pending configuration by dependent task

| Missing input / evidence | First affected work; does not block N1 |
| --- | --- |
| Production embedding provider/model/revision/deployment, dimensions, compatible tokenizer and chunk policy | Confirm before production adapter N10; N9 needs an explicit compatible test tokenizer/budget. The sample profile is NOT a selection. |
| Qdrant hosting, authorized endpoint, credentials, collections/space compatibility | N10 local doubles/local service can proceed; real-service checks and rollout require explicit authorization. |
| OCR languages/locked weights, Speech locales, extractor version/runtime and supported YouTube policy | N3, N6-N7 and N12-N13 must record concrete tested configuration; no default model/credentials invented here. |
| Physical names for all three queues/images/apps, resource group/environment, technical-state storage, identities/RBAC, OIDC, GHCR pull/publication permissions, callbacks, limits | N12-N15 setup/integration and authorized external checks. Logical names in the spec and old README examples are not confirmed resource names. |
| Producer routing/cutover and later Akay.Be acceptance/filtering/reassignment integration | N15-N16 handoff. No new document-only consumer may process the old mixed queue before coordination. No changes to Akay.Be or databases here. |

## Official API evidence

- [Versioned heading hierarchy](https://github.com/docling-project/docling/blob/v2.141.0/docs/usage/heading_levels.md)
  and [confidence](https://github.com/docling-project/docling/blob/v2.141.0/docs/concepts/confidence_scores.md),
  rechecked through the versioned official documentation index.
- [Versioned backend options](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/backend_options.py),
  checked alongside installed pinned models; see the historical inputs for
  pipeline/OCR/Core source links and prior dependency-resolution commands.
- [Azure Blob concurrency](https://learn.microsoft.com/en-us/azure/storage/blobs/concurrency-manage)
  and [lease semantics](https://learn.microsoft.com/en-us/rest/api/storageservices/lease-blob):
  finite leases are 15-60 seconds; conditional ETag mismatches fail rather than
  silently overwriting. Exact SDK wiring/tests remain with N5/N11.
