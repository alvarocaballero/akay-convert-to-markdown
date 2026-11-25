# ConvertToMarkdown: phased Docling and RAG implementation plan

Status: proposed implementation handoff; no application changes have been made.
Scope: `C:\Develop\Akay\Akay.ConvertToMarkdown` only. Database and Akay.Be changes are deferred.
Architecture reference: `docling-rag-architecture-summary.md`, with the clarifications below taking precedence.

## Outcome and boundaries

Produce two Python workers, two independently built images, and deployment workflows for two Azure Container Apps:

| Worker | Input queue | Work | Output |
| --- | --- | --- | --- |
| Converter | Existing conversion queue | Docling for documents; existing Azure Speech/FFmpeg for media | Blob artifacts and conversion webhook |
| Indexer | New indexing queue | Load accepted structured documents, HybridChunker, embeddings, Qdrant; scoped deletion | Indexing/deletion webhook |

Do not implement database tables, migrations, Akay.Be handlers, acceptance UI, chat, exercise generation, or automatic replacement of domain records. Do not query the Akay database from either worker. Do not introduce document history/versioning.

This plan authorizes preparation for a future implementation agent, not a live deployment now. Pushes, registry publication, Azure changes, queue creation, and real service calls require an explicitly selected environment and authorized credentials. Keep automatic deployment disabled until those prerequisites and the consumer contracts are ready.

## Verified starting point

Read on 2026-11-12:

- Python 3.12; package `akay-convert-to-markdown`, version `1.0.1` in `pyproject.toml`.
- `markitdown[pdf,docx,pptx]==0.1.1` is a runtime dependency.
- Entry point: `akay-convert-to-markdown` -> `akay_convert_to_markdown.main:main`.
- `conversion/document_converter.py` currently returns a Markdown string.
- `conversion/markitdown_converter.py` runs synchronous conversion through `asyncio.to_thread`.
- `processing/document_processor.py` orchestrates conversion and notification, with existing-destination reuse.
- Requests contain `requestId`, Blob source, `destinationBlobName`, `contentType`, `overwriteDestination`, `callback`, and opaque `payload`.
- Audio/video use Azure Speech Fast Transcription and FFmpeg, respectively. Preserve their current behavior.
- Dockerfile uses `python:3.12-slim`, installs FFmpeg/FFprobe, runs non-root, exposes no port.
- `.github/workflows/build-and-push.yml` tags a release, builds one Linux/amd64 image and pushes it to GHCR. It does not deploy to Azure, and its release tag is created before the image build succeeds.
- Unit tests use pytest. Live Azure integration tests are opt-in.

Paths above are relative to the repository unless absolute. The implementation agent must recheck the working tree and nearest instructions before editing.

## Clarifications to the architecture summary

1. **Original files stay where the caller uploaded them.** Do not move or duplicate originals merely to match the illustrative folder layout. Derive output paths from the caller's `destinationBlobName`, not from domain IDs hidden in `payload`.
2. **Artifact publication is not a Blob transaction.** Uploading Markdown last alone does not make concurrent overwrite/retry safe. The implementation must define and test a small publication protocol, including coordination for the same destination and recovery after partial upload.
3. **Section tags are not yet specified.** Do not invent semantic labels such as `architecture` or add an LLM call. Confirm the agreed marker syntax, identifier rules, and whether tags mean structural section IDs or semantic labels before implementing this task.
4. **Docling confidence is not universal.** Preserve available values; represent unavailable grades/pages as absent or null, particularly for non-paginated formats. Never invent PDF-style pages for DOCX/HTML/TXT.
5. **No page-image export is required.** Internal page rendering may still be necessary for OCR, layout, or picture crops. Prevent full-page image artifacts from being uploaded/exported; do not disable rendering blindly.
6. **Qdrant IDs must use a valid supported type.** Use deterministic UUIDs for points, not the illustrative arbitrary strings in the architecture summary.
7. **Model packages and model weights differ.** A document feature may require Transformers without requiring Whisper. Exclude ASR/VLM extras and weights, not shared libraries needed by formula/code processing.
8. **The future RagIndexProfile table is out of scope.** The indexer consumes a validated technical profile/configuration and echoes its identity in results. A `profileId` alone cannot be resolved without a configured mapping; never add a hidden database lookup.
9. **Media conversion remains unchanged in this delivery.** Its current Markdown/webhook path stays supported. Docling JSON-based indexing is initially for document artifacts; indexation of existing media transcripts is deferred rather than silently calling Docling ASR.

## Phase map

| Phase | Tasks | Deliverable | Dependency |
| --- | --- | --- | --- |
| 0 | T0 | Confirm contracts, versions, and deployment inputs | None |
| 1 | T1-T2 | Multi-artifact conversion interfaces and contract tests | T0 |
| 2 | T3-T4 | Docling conversion, section metadata and review report | Phase 1 |
| 3 | T5-T6 | Reliable Blob publication and updated converter webhook | Phase 2 |
| 4 | T7-T9 | Separate indexing/deletion worker with Qdrant | T0; artifact contract from Phase 3 |
| 5 | T10-T11 | Heavy converter image and lightweight indexer image | Phases 3-4 |
| 6 | T12-T13 | Dual-image CI and separately gated Azure deployments | Phase 5 |
| 7 | T14 | End-to-end checks and handoff for later Akay.Be work | All prior phases |

Deliver in order, with a verified checkpoint after each phase. Do not launch one unbounded rewrite. Include code, relevant tests, and documentation with each behavior change.

## Phase 0 — Resolve prerequisites and freeze contracts

### T0 — Establish implementation inputs

- Recheck repository status, instructions, current tests, and the relevant dependency APIs. Use the existing test suite as baseline evidence.
- Select compatible pinned Docling and docling-core versions for Python 3.12. Verify APIs for heading hierarchy, OCR text-layer repair, picture export, confidence and JSON reload against those exact versions.
- Resolve the section-marker specification from an existing project example or ask the user one focused question. Do not silently substitute a tagging design.
- Confirm the first embedding provider/model/deployment and dimensions. Implement one production provider, not a generic multi-provider framework. Other providers can be added later.
- Define a technical embedding profile: profile identifier/fingerprint, model identity, deployment/model revision when available, dimensions, tokenizer, chunk token budget, distance, and collection. Secrets and service endpoints belong in controlled settings, not untrusted job metadata.
- Confirm the Azure resource group, existing Container Apps environment, existing converter app name, new indexer app name, queue names, identities, GHCR repository names/visibility, and deployment environment.
- Document unresolved inputs as explicit prerequisites. They block only their dependent tasks: Azure names must not block local conversion work; the embedding provider must not block converter implementation.

**Contract decisions to record:**

- Preserve existing conversion envelope fields and opaque `payload` forwarding. Add optional `documentOptions` for code/formula enrichment, both defaulting to false.
- Completed document webhooks retain `destinationBlobName` and add artifact references for Docling JSON, review JSON and images. Failure events retain bounded safe errors. Audio/video webhook semantics remain unchanged.
- Add versioned schemas for new review/index contracts, with fixture messages and example webhook bodies. These schema versions are technical compatibility markers, not document versions.
- Index/delete requests include a request UUID, operation, explicit document/index key, callback, profile reference/configuration, scope metadata and, for indexing, trusted Blob artifact locations. `payload` remains opaque.
- Do not index automatically after conversion: a later acceptance-triggered producer sends the indexing request. Provide sample messages for manual/test use until Akay.Be is updated.

**Exit:** contracts and the necessary task-specific decisions are documented; unaffected work may proceed if a later external prerequisite is missing.

## Phase 1 — Prepare conversion contracts

### T1 — Return a typed artifact result

- Replace the document converter's string-only result with an internal typed result for Markdown, structured document export, image files, and review data.
- Keep Docling implementation details inside the adapter/report builder rather than leaking them into Service Bus settlement.
- Reuse the existing storage, notification and error abstractions. Avoid a repository-wide rename or new framework.
- Keep heavy converter dependencies out of indexer startup imports.

### T2 — Extend request and webhook schemas

- Validate optional document flags strictly and preserve existing default values.
- Expose relative artifact locations through additive webhook fields; document that the future Akay.Be consumer must accept them before production rollout.
- Document partial/unavailable metadata and absent-image behavior consistently.

**Exit:** contract/dispatch tests pass; audio/video behavior and opaque payload forwarding are preserved.

## Phase 2 — Implement document extraction

### T3 — Replace MarkItDown with Docling

| Setting | Target behavior |
| --- | --- |
| Pipeline/backend | Standard; docling_parse |
| OCR | Enabled, no forced full-page OCR; repair broken text layers if supported by the pinned version |
| OCR engine | Prefer explicit RapidOCR with a pinned backend and matching prefetched language assets for reproducible Linux behavior |
| Tables | Enabled, accurate |
| Heading levels | Enable supported hierarchy inference |
| Pictures | Export referenced document pictures, not full-page screenshots |
| Classification/description | Disabled |
| Code/formula enrichment | Controlled by validated request flags; default false |
| External services/plugins | Not enabled for document extraction |

- Preserve the existing document extension allowlist, including HTML, TXT and MD. Verify native/passthrough handling where a layout pipeline is unnecessary.
- Do not silently fetch arbitrary remote images/links from HTML or Markdown. Render-time asset access remains an Akay.Be concern.
- Do not add a MarkItDown fallback or speculative second parser during this delivery. Record a parsing failure clearly; alternate backends can follow demonstrated cases later.
- Handle Docling failure/partial status explicitly. An incomplete or empty output must not accidentally become a successful complete document. Surface recoverable warnings in the review data.
- Start with one document conversion at a time per converter replica. Do not assume a shared converter is thread-safe.
- Keep asyncio responsive and Service Bus lock renewal functional. A cancelled `asyncio.to_thread` await does not stop the underlying conversion: use a bounded process boundary or a proven mechanism that stops work before temp cleanup and retry.

### T4 — Produce section metadata and review data

- Apply the confirmed section markers after conversion and before notification; make marker insertion idempotent.
- Keep the Docling JSON valid for docling-core reload. Store section-to-Docling-item reference mappings in review data so the indexer can attach tags even though it does not chunk Markdown.
- Identify sections by stable item references/IDs, not by heading text alone; repeated headings must remain distinguishable.
- Produce `review.json`: schema version, source/conversion fingerprint, statistical summary, section tree/mappings, table representations, image references, warnings, available document/page scores and grades, extraction engine version.
- The summary is counts/structural information, not an LLM-generated content summary.
- Do not equate page headers/footers with section headings. Preserve real heading levels where available.
- Preserve valid relative picture references and protect local paths. Verify JSON reload for chunking without enabling unrestricted local asset fetching.

**Exit:** controlled fixtures cover headings, repeated headings, lists, tables, pictures, scanned text, formula/code opt-in, DOCX, PPTX, HTML, TXT and MD. Grade availability is honest; no exported full-page screenshots; no text/content logging.

## Phase 3 — Store the artifact set reliably

### T5 — Publish and reuse complete artifact sets

- Generate Markdown, Docling JSON, review JSON and picture files in an isolated execution directory.
- Preserve the caller-selected Markdown Blob name. Define predictable adjacent artifact names and expose the actual names in the webhook/review data.
- Do not upload originals again or require knowledge of TopicContent storage conventions.
- Define and test destination-level coordination/conditional writes so concurrent overwrite or redelivery cannot publish mixed image/JSON/Markdown generations.
- Reuse a document conversion only after checking the full published artifact set; a legacy Markdown-only Blob is not evidence that Docling artifacts exist.
- Keep the old audio/video single-file reuse semantics intact.
- Retrying only the webhook after successful artifact publication must not require reconversion. A failed partial publication must be repairable on redelivery.
- Clean only temporary files or this attempt's uncommitted artifacts; never broadly delete a caller's prefix.

### T6 — Preserve reliable message handling

- Notify completion only after conversion, section tagging, validation and complete artifact publication.
- Distinguish permanent document/contract failures from transient storage/network/rate-limit/webhook failures. A transient tagging/notification error must not become a permanent failed document.
- Reuse existing at-least-once settlement rules and queue-controlled dead lettering.
- Ensure lock renewal covers processing, uploads, notification retries and a margin; account for shutdown/cancellation as well as successful runs.
- Preserve webhook authentication, correlation/idempotency headers, bounded logs and opaque payload behavior.

**Exit:** tests cover upload failure midway, webhook failure after publication, existing Markdown without sidecars, repeated requests, overwrite/non-overwrite races, timeout, shutdown and temp cleanup. No premature completed webhook or lost-lock parallel conversion.

## Phase 4 — Add the lightweight indexer

### T7 — Separate entry point, settings and consumer wiring

- Add an indexer command, for example `akay-index-content`, sharing bounded technical helpers with the existing converter command.
- Converter startup must not require Qdrant/embedding settings; indexer startup must not require Speech/FFmpeg/converter settings.
- Accept index and delete operations with explicit scoping. No database access or automatic acceptance decisions.
- Resolve embedding profiles from controlled configuration or validated complete job data; the future backend can provide the profile contract without changing the chunker.

### T8 — Chunk and embed the structured document

- Reload the saved Docling JSON using compatible docling-core, without reprocessing the source PDF.
- Run HybridChunker with the actual embedding-model tokenizer and a tested token budget that includes contextualized headings/captions.
- Fix an earlier illustrative example: do not configure a 400-token chunk budget for a model with a smaller supported context window.
- Map sections/tags using item references, preserve page provenance when available, and keep clean text separate from contextualized embedding text.
- Fetch embeddings in bounded batches with timeouts and bounded transient retries. Validate output count, vector dimensions and numeric validity before uploading points.
- Do not load a local embedding model in this image if embeddings are requested from an external service. Prepackage/cache tokenizer assets as needed.
- Produce deterministic UUID point IDs from the agreed indexing scope, document key, profile/chunker fingerprint and chunk identity.

### T9 — Store and delete points safely

- Use Qdrant's supported client and wait for acknowledged writes before the indexing-completed webhook.
- Validate existing collection dimensions, distance and model/profile identity; equal dimensions alone do not make different embedding models compatible.
- Store text, headings, tags, pages when present, source references, document key, technical profile and explicitly supplied scope metadata in the payload.
- Index fields used for filtering/deletion. Never infer business ownership from arbitrary source paths.
- Make retries converge to the same point set. Do not leave stale chunks when a repeated indexing job produces fewer chunks.
- On partial indexing failure, report no completed state. Later .NET must expose documents only after acknowledged indexing; this worker does not implement domain publication.
- Delete only the supplied document/profile/security scope. Repeating delete for already absent points succeeds without affecting neighbors.
- Serialize or reject competing index/delete jobs for the same document; an old in-flight index must not recreate data after acknowledged deletion.
- Return profile identity, document identity, indexed chunk count and operation result in the webhook; never credentials or full content.

**Exit:** unit tests with fake embeddings plus integration tests against local Qdrant cover token limits, tags/provenance, valid point IDs, repeated upserts, partial batches, dimension/profile mismatch, fewer-chunk cleanup, scoped repeated deletion, and index/delete ordering. No live cloud provider is required by default tests.

## Phase 5 — Build two dependency-isolated images

### T10 — Split packaging and entry points

- Move heavy document and indexer dependencies into separately installable extras/groups or equivalent targets. Shared base dependencies must not implicitly pull the full converter into the indexer.
- Pin compatible document/chunking versions and lock reproducible resolved dependencies per target.
- Remove MarkItDown and its adapter after replacement tests pass.
- Preserve the current converter command; provide the new indexer command and target-specific configuration validation.

### T11 — Create converter and indexer Docker targets

Converter image:
- Python 3.12 Linux/amd64, existing FFmpeg/FFprobe, Docling and required OCR/layout/table/code-formula assets.
- Prefetch only selected assets and languages for the pinned Docling release; no Whisper, ASR, picture-description or full-page VLM weights.
- Use CPU-only inference packages where supported; do not accidentally bundle CUDA runtimes for a CPU deployment.
- Read-only model assets accessible by the non-root runtime user; bounded writable temporary directories.

Indexer image:
- Python 3.12, compatible docling-core/tokenizer, chosen embedding client, Qdrant and required Azure clients.
- No Docling PDF pipeline, OCR/layout/table weights, FFmpeg, Azure Speech client wiring, Whisper or VLM weights.

Both targets:
- Non-root, no public HTTP ingress, no secrets in build arguments/layers.
- Test import/startup of each target independently. Inspect installed distributions and final sizes instead of assuming exclusions worked.
- Test document conversion/tokenization with external downloads blocked. Azure Blob, Service Bus, webhook, embedding API and Qdrant access remain separately permitted runtime integrations; do not claim the whole worker runs offline.

**Exit:** both images build; converter fixtures work with local prefetched assets; indexer chunking works without converter dependencies; required media tools remain available in converter only.

## Phase 6 — CI/CD for GHCR and two Container Apps

### T12 — Test, build and publish two images

- Extend the existing GitHub Actions workflow rather than assuming an Azure DevOps pipeline exists.
- Run unit/contract tests and target-specific checks before publication. Run local service integration checks in CI where practical without cloud secrets.
- Build both Docker targets, and smoke-test both images before releasing them.
- Publish distinct GHCR image names, for example `${repository}-converter:${sha}` and `${repository}-indexer:${sha}`. Confirm actual package names in T0; do not hard-code `ghcr.io/akay`.
- Deploy exact immutable SHA tags/digests, not `latest`. Maintain a shared release identity for the two images.
- Prevent concurrent release-tag allocation races. Do not push the existing semver release tag before both builds/tests succeed; do not publish a successful overall release if one target fails.
- Allow efficient per-target caching and avoid embedding Hugging Face tokens in layers/logs. If build downloads need authentication, use ephemeral build secrets.

### T13 — Add explicit Azure deployment stages

- Add two separately selectable/gated jobs: deploy converter and deploy indexer. A failed dependent build prevents its deployment.
- Use a GitHub Environment with explicit deployment approval while the new consumer/infra setup is pending. A normal push must not automatically cut over an unready production consumer.
- Configure Azure authentication with an explicitly authorized identity, preferably GitHub OIDC. Document required repository/environment variables and least-privilege role assignments.
- Configure GHCR pull authentication separately from CI push authentication, especially for private images. Do not assume `GITHUB_TOKEN` used during build is a durable Azure pull credential.
- Each Container App gets its own image, entry point, queue/scaler, runtime identity/settings/secrets, CPU/RAM and replica limits. No ingress.
- Target the existing converter app and the new indexer app in the approved Container Apps environment. Decide explicitly whether a deployment provisions the new app or requires it to exist; provide an idempotent bootstrap definition or operator instructions accordingly.
- Configure non-HTTP Service Bus scaling for both apps. The indexer must not listen to the converter queue. Confirm queue authorization separately for the runtime consumer and scaler.
- Use conservative, configurable starting resources; converter suggestion: 2 vCPU/4 GiB and one concurrent conversion. Treat this as a measurement starting point, not proven capacity. Size indexer from its tokenizer, batching and client memory needs.
- Validate startup/configuration and revision health; a running background process alone is not an end-to-end acceptance test.
- Record deployed image digests and provide independent rollback procedures. Azure deployment of two apps is not atomic: contracts must tolerate one app temporarily running the previous compatible release.
- Never require schema migrations or Akay.Be deployment from these workflows.

**Exit:** workflow validation and local builds pass; jobs reference different images and approved app/queue names. A real staging deployment and smoke test is explicitly marked pending until the destination, identity and credentials have been authorized. Missing Azure setup must not be reported as successful deployment.

## Phase 7 — Verify and hand off

### T14 — Exercise the pipeline without Akay.Be changes

- Provide example conversion, indexing and deletion messages; a local callback receiver; test fixtures; and exact local commands.
- Demonstrate: source Blob -> conversion -> complete artifact set -> authenticated callback -> separate manual index request -> Qdrant points -> authenticated callback -> scoped delete.
- Use a stub embedding service by default; verify the selected real provider separately with an explicitly authorized test environment.
- Include an audio and video regression test showing the existing Speech/FFmpeg path is unchanged.
- Document operator setup: two apps, two queues, GHCR pull configuration, identities, secrets, Qdrant collection/profile, and scaler settings.
- Update README examples, errors, artifact layout, options, resource/timeouts, test commands and the two-image build/deployment process. Replace obsolete non-goals only where this delivery changes them.
- Write a later-integration handoff for Akay.Be: conversion webhook fields, review schema, index/delete contracts, profile metadata, and the requirement to filter retrieval by authorized and indexed documents.
- Record the database fields/table as manual follow-up notes only; create no SQL, ORM migrations, or database connections in this repository.

**Exit:** report observed test outcomes, image sizes, fixture timings and memory where measured; list every skipped or externally blocked check. Do not claim the full user acceptance/chat workflow is implemented.

## Implementation discipline for the receiving agent

1. Work only in `C:\Develop\Akay\Akay.ConvertToMarkdown`; do not edit Akay.Be, Akay.To, databases, or synced project references.
2. Read this plan and the architecture summary, then resolve T0 inputs. Ask only the next question that actually blocks the current phase.
3. Preserve existing behavior outside the requested document/index/deployment changes. Keep `payload` opaque and Service Bus settlement separate from processing.
4. Use pytest. For deterministic behavior changes, observe a failing focused test first, implement the smallest fix, then rerun focused tests and the applicable suite. Pin shared-path regressions for audio/video, authentication, callbacks and retries.
5. Keep each phase reviewable; include implementation, tests and docs together. Follow repository instructions for branches, commits, review and delegation. Do not interpret this plan as permission to push, publish or run remote services.
6. Do not hide an unavailable feature behind a silent fallback, invent grades/tags, or mark missing cloud verification as passed.
7. Before moving to the next phase, report completed task IDs, changed surfaces, observed checks and remaining prerequisites. Maintain a short progress log in the implementation workspace.

## Primary references to verify against pinned versions

- [Docling advanced options and model prefetching](https://docling-project.github.io/docling/usage/advanced_options/)
- [Docling chunking and tokenizer-specific extras](https://docling-project.github.io/docling/concepts/chunking/)
- [Docling confidence reports](https://docling-project.github.io/docling/concepts/confidence_scores/)
- [Qdrant points and identifiers](https://qdrant.tech/documentation/manage-data/points/)
- [Qdrant official SDKs](https://qdrant.tech/documentation/interfaces/)
- [Deploy Azure Container Apps with GitHub Actions, including GHCR](https://learn.microsoft.com/en-us/azure/container-apps/github-actions)

## Request defining this scope

> ok, sí, ese es el punto de partida y el otro md que acabas de preparar lo que queremos obtener. Hacemos un plan por fases para pasárselo al agente y que lo haga? Incluyendo la modificación de las pipelines para que ahora publique el componente en 2 container apps en azure. De momento solo la parte de converttomarkdown, los cambios de tablas los haré manualmente y los cambios en akay.be los dejaremos para después
