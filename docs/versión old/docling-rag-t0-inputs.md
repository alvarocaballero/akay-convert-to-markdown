# T0 implementation inputs

Status: **pending user input**, checked on 2026-11-12 at baseline commit `f03c7a4`.
This checkpoint covers T0 only. It records verified inputs and preserves the
remaining decisions for T0; it does not authorize starting T1.
See [progress](docling-rag-progress.md) for commands and results.

## Verified repository baseline

- Read the workspace instructions in `../AGENTS.md`, the current `README.md`,
  [architecture summary](docling-rag-architecture-summary.md) and
  [implementation plan](docling-rag-implementation-plan.md). No repository-local
  `AGENTS.md` or existing progress log was found.
- Initial working tree: `?? docs/`; these pre-existing documents were preserved.
- Python 3.12.10; application version 1.0.1. Installed pins match `pyproject.toml`:
  MarkItDown 0.1.1, HTTPX 0.27.2, Pydantic 2.10.4, pydantic-settings 2.7.1.
  Docling, docling-slim and docling-core are not installed in the project environment.
- `DocumentConverter.convert` returns a string. The MarkItDown adapter uses
  `asyncio.to_thread`. The processor uploads a single Markdown file and reuses an
  existing destination without checking sidecars.
- The request model preserves opaque `payload`, ignores unknown envelope fields,
  and has no `documentOptions` field. Unknown options are therefore not evidence
  that enrichment is implemented. Audio/video retain their Speech/FFmpeg path.
- One command and one Docker image exist. The workflow publishes to
  `ghcr.io/${{ github.repository }}` and creates the release tag before building.
  It contains no Azure deployment stage.

## Selected version baseline

| Component | Exact selected version | Evidence and consequence |
| --- | --- | --- |
| Docling | `2.141.0` | Version-specific documentation available; the distribution depends on `docling-slim[standard]==2.141.0`. |
| docling-slim | `2.141.0` | Contains the `docling` Python modules; installed without heavy extras for the T0 probe only. |
| docling-core | `2.99.0` | Matches Docling's declared `>=2.99.0,<3` requirement; document save/reload exercised. |
| HTTPX | `0.28.1` | Future replacement for `0.27.2`; the selected standard extra requires `>=0.28,<1`. |
| pydantic-settings | `2.14.0` | Future replacement for `2.7.1`; required by the selected core. |
| Pydantic | `2.10.4` | Existing pin retained in the successful resolver/probe checks. |

All selected Docling packages declare Python `>=3.10,<4`, including Python 3.12.
The version pair is a fixed API baseline, not a claim to use the newest release.
No project dependency was installed, removed or changed for T0.

The current settings pin causes a reproduced `ResolutionImpossible`. Resolution
with the future HTTPX/settings pins, `docling[rapidocr]==2.141.0`, the selected
core and existing Azure client pins succeeds on Windows/Python 3.12. This does
not certify Linux wheels, CPU-only inference, extraction quality or a final lock.
Dependency installation/regression checks belong to the conversion change;
target-specific transitive locks and CPU/model isolation remain T10-T11 work.
Do not install ASR/audio/video/VLM extras merely to enable document processing.

## Exact-version API findings

| Requirement | Verified API or limitation |
| --- | --- |
| Standard PDF / docling_parse | `PdfFormatOption` defaults to `StandardPdfPipeline` and `ThreadedDoclingParseDocumentBackend`; both defaults were checked by the probe. |
| Heading hierarchy | `PdfPipelineOptions.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)`. Retain `generate_parsed_pages=True` for the font-style signal. Repeated headings retain distinct `self_ref` values after JSON reload. |
| OCR without forced full-page mode | `do_ocr=True`; explicit `RapidOcrOptions(backend="onnxruntime", mode=OcrMode.PDF_AWARE_LAYOUT_REGIONS)`. The old `force_full_page_ocr` property is deprecated. This configures options; the probe does not execute OCR. |
| Broken text layers | No `replace_broken_text_layer` option exists. The selected OCR implementation distinguishes visible/invisible PDF cells and merges overlapping OCR results accordingly. This is not a guarantee to repair every corrupt visible text layer. Keep this limitation explicit and verify a broken-layer fixture in T3; do not equate `force_backend_text=False` with universal repair. |
| Tables / optional enrichment | `table_structure_options.mode = TableFormerMode.ACCURATE`; `do_code_enrichment` and `do_formula_enrichment` default false. Model/backend asset selection is still T3/T11 work. |
| Picture export | `generate_picture_images=True`, `ImageRefMode.REFERENCED`, `save_as_markdown` and `save_as_json`. Pass a **relative** `artifacts_dir=Path("images")`; an absolute directory produced local paths / `file:` Markdown URIs during the probe. Windows JSON references use backslashes, so T4 must normalize published URI paths. |
| Page-image boundary | `generate_page_images=False` is independently configurable. JSON saving can export page images if they exist on the document; T3/T4 must ensure none reach publication, even when internal rendering is needed. The synthetic probe has no pages and does not prove real PDF export behavior. |
| Confidence | `ConversionResult.confidence`, `ConfidenceReport.pages`, `mean_grade` / `low_grade`, and component scores exist. Unmeasured scores are NaN and grades `unspecified`; normalize unavailable/non-finite values to null or absent in the future review contract. Do not invent pages. |
| JSON reload | `DoclingDocument.save_as_json` / `load_from_json` work with a synthetic document and referenced image without fetching it. Keep the upstream document schema separate from the review schema. |
| Asset access | `HTMLBackendOptions` / `MarkdownBackendOptions` expose `fetch_images=False`; base options expose local/remote fetch controls. `enable_remote_services` and `allow_external_plugins` default false. Actual blocked-network extraction is a later check. |
| TXT / MD | The selected `FormatToExtensions[InputFormat.MD]` includes `txt` and `md`; the existing application allowlist must remain narrower than Docling's full format list. |

## Contract invariants already required by the plan

These decisions are carried forward from T0's contract requirements, not new
runtime behavior:

- Preserve conversion envelope fields, caller-selected `destinationBlobName`,
  existing defaults, opaque `payload`, callback routing, webhook authentication
  and at-least-once settlement. Originals stay at their uploaded locations.
- Add optional strictly validated `documentOptions` for code/formula enrichment,
  both false by default. The final wire names and fixtures remain to be frozen.
- Completed document notifications retain the existing fields and add relative
  references to Docling JSON, review JSON and images. No-image documents need a
  consistent empty representation. Media notifications retain current semantics.
- Review/index schema versions describe technical compatibility, not document
  history. Review data maps sections to Docling item references, retains available
  confidence, and summarizes counts/structure without an LLM call.
- Index/delete jobs require a UUID, operation, explicit document/index identity,
  callback, controlled profile reference/configuration and explicit scope.
  Indexing also needs trusted Blob locations. `payload` is never interpreted as
  authorization, domain identity, credentials or service configuration.
- An acceptance-triggered producer sends indexing separately. Conversion never
  automatically indexes. Deterministic Qdrant point IDs must be valid UUIDs.

**Still T0 work:** freeze versioned review/index schemas, fixture messages and
example webhooks after the section/profile decisions. There are no approved
new schema files or runnable future index messages at this checkpoint.

## User-confirmed section-marker syntax

The user supplied a Markdown example and then explicitly changed the marker
name to `section`. Preserve these exact HTML-comment delimiters:

```markdown
<!-- section:start id="01JCK8M2QX4F7K9W3B6H5T1R8A" -->
# Section heading

Section content.

<!-- section:end id="01JCK8M2QX4F7K9W3B6H5T1R8A" -->
```

The same ID pairs the start/end of one section. The supplied example has three
sequential, non-nested sections and keeps an `### Ejercicio` subheading inside
the third section, without a separate marker. Do not infer that every heading
necessarily starts a marked section or that heading nesting implies marker nesting.
The IDs identify sections; the example does not specify semantic tag labels.

[Reference fixture](fixtures/section-markers.md) preserves the user's content
with the requested marker name. This is a contract example, not converter output.
Identifier format/generation/reprocessing stability and the general rule for
section boundaries still require confirmation; the sample alone does not
mandate ULID validation or a heading-depth cutoff.

## Unresolved inputs and dependent tasks

| Input | Current evidence | Blocks |
| --- | --- | --- |
| Section markers | Syntax and paired-ID example supplied by the user; marker name confirmed as `section`. Identifier generation/stability and general section-boundary rules remain unconfirmed. | Section-bearing review schema finalization and T4; does not block the internal T1 interface design. |
| Embedding provider/model | The architecture's AzureOpenAI / `text-embedding-3-small` / `embedding-small` / 1536 values are explicitly examples, not confirmed settings. | Production profile freeze and T8-T9; not converter implementation. |
| Technical profile | Required fields below identified; values unconfirmed. | Final index fixtures, tokenizer/embedding implementation and collection validation. |
| Index/security scope | Must be explicit; no confirmed scope fields or stable document/index key encoding yet. | Index/delete schema freeze and safe scoped deletion in T7-T9. |
| Qdrant destination | Hosting, endpoint setting and collection unconfirmed. | Real-service verification and deployment, not local fake-provider checks. |
| Azure / GHCR | Required inputs listed below; no environment selected or authorized. | T12 publication naming, T13 deployment and cloud smoke checks. |
| Consumer compatibility | Future Akay.Be acceptance of additive artifacts and new contracts not implemented here. | Production cutover, not local contract development. |

### Technical embedding profile to complete in T0

Record one production provider and profile with: `profileId`, fingerprint,
provider, model identity, deployment, model revision when available, dimensions,
tokenizer identity/revision, contextualized chunk token budget, distance and
Qdrant collection. Record chunker version/options in the indexing fingerprint.
No field value is inferred from the illustrative architecture profile.

The fingerprint must change when embedding/chunking compatibility changes.
Its exact canonicalization and scope/key encoding must be documented with the
index schema. Endpoints and credentials resolve from controlled settings, not
untrusted job metadata. No profile ID triggers a database lookup.

### Deployment inputs to confirm later within T0

Record the deployment environment, Azure resource group, existing Container Apps
environment, existing converter app, new indexer app, and whether the latter is
pre-provisioned or bootstrapped. Also confirm both queue names/namespaces, runtime
and scaler identities/permissions, deployment identity/OIDC configuration,
GHCR repository names/visibility/pull authentication and GitHub Environment.

`convert-to-markdown` and `index-topic-content` are the plan's intended queues;
the actual environment settings/resources are unconfirmed. The existing workflow
template does not approve names for the two future image packages. No cloud
resource or secret configuration was read to manufacture those decisions.

## Versioned evidence sources

- [Docling 2.141.0 package metadata](https://pypi.org/pypi/docling/2.141.0/json),
  [slim metadata](https://pypi.org/pypi/docling-slim/2.141.0/json),
  [core 2.99.0 metadata](https://pypi.org/pypi/docling-core/2.99.0/json).
- [Heading hierarchy](https://github.com/docling-project/docling/blob/v2.141.0/docs/usage/heading_levels.md)
  and [pipeline options](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/pipeline_options.py).
- [OCR cell merging](https://github.com/docling-project/docling/blob/v2.141.0/docling/models/base_ocr_model.py),
  [confidence models](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/base_models.py)
  and [backend fetch options](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/backend_options.py).
- [Core serialization](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/types/doc/document.py).
