# Content processing: implementation plan for the three-worker specification

Revision: 2026-11-14. Status: implementation handoff, not completed work.
Target repository: C:\Develop\Akay\Akay.ConvertToMarkdown.
Normative input: docs/content-processing-specification.md, sections 1-21.
Authoritative document paths: C:\Develop\Akay\Akay.ConvertToMarkdown\docs\content-processing-specification.md and C:\Develop\Akay\Akay.ConvertToMarkdown\docs\docling-rag-implementation-plan.md.

## Read this first

This plan replaces the earlier two-image T0-T14 plan. Stable task IDs are N0-N16 plus the supplemental N9A, inserted after N9 and before N10. Reconcile and reuse existing implementation/probes/tests; do not restart working code merely because requirements changed.

**Resume instruction for the 2026-11-14 revision:** if N9 is complete and the agent is waiting for N10, execute N9A next. N10 is blocked until N9A passes its exit criteria. Do not renumber tasks or rerun completed N0-N9 wholesale. Completion of the old N2-N9 does not imply completion of the new N9A. This document does not certify the actual implementation status; reconcile the repository progress record first.

The authoritative copies are in this repository's docs/ directory, not the earlier ChatGPT working directory. Treat copies outside the repository as reference material, not a newer implementation baseline.

Implement only the task explicitly assigned to the current session. Each session reads the specification, this plan, the repository README/instructions, current git state and the persistent progress record.

Do not modify Akay.Be, Akay.To, databases or synced project sources. Do not create migrations. No real queue creation, deployment, image publication, push or live API calls without explicit destination/credential authorization.

The architecture/specification is authoritative; the README describes current implementation and is updated as implementation advances. Preserve the baseline outside explicitly changed behavior.

## Phase and task map

| Phase | Task | Outcome | Prerequisites |
| --- | --- | --- | --- |
| 0 | N0 | Reconcile existing work and pin prerequisite decisions | None |
| 1 | N1 | Three target entry points/settings and reusable technical interfaces | N0 |
| 1 | N2 | Typed input/output/artifact contracts with fixtures | N0-N1 |
| 2 | N3 | Document conversion through Docling | N2 |
| 2 | N4 | Principal section markers, mappings and review metadata | N3 |
| 2 | N5 | Reliable multi-artifact storage/publication | N4 |
| 3 | N6 | Separate Blob media transcription with timed JSON | N2; reuse N5 storage contracts |
| 3 | N7 | Explicit YouTube source adapter in the media worker | N6 |
| 4 | N8 | Reliable callbacks, settlement, timeouts and shutdown for workers | N5-N7 |
| 5 | N9 | Structured document/transcript chunking and section assignment | N2, N4, N6 |
| 5 | N9A | Prepare reviewed Markdown and verify corrected-transcript chunking | N9; reuse N2-N8 |
| 5 | N10 | First embedding provider and Qdrant point-set indexing | N9 AND N9A; selected provider |
| 5 | N11 | Ordered index/delete operations, receipts and reassignment | N10 |
| 6 | N12 | Three isolated dependency sets and packaging | N1-N11, including N9A |
| 6 | N13 | Three reproducible images and target-specific smoke tests | N12 |
| 7 | N14 | CI tests/builds and three GHCR publications | N13 |
| 7 | N15 | Three separately gated Azure Container Apps deployments | N14; authorized environment prerequisites |
| 8 | N16 | End-to-end verification, operator docs and .NET handoff | N0-N15, including N9A; disclose pending external checks |

Never mark cloud deployment complete from YAML validation alone. Missing external setup blocks only the affected external checks, not local conversion work.

## Supplemental formula inventory — 2026-11-16

Specification: §10.1.1 and acceptance criterion 25. This is an explicitly scoped
supplement, not N17 or a reset of completed N0-N16/N9A. Its observed completion
and exact checks are recorded in `docs/docling-rag-progress.md`.

- Add `review.formulas` and `summary.formulaCount` (equal to array length).
  Default missing fields in older reviews to `[]`/`0`, retaining schemaVersion 1.
- Collect existing structured FormulaItems with document-local numbered identities,
  Docling references, nullable current-review section/page mapping, source text
  and only the decoded LaTeX representation available on the pinned item API.
  Keep identical expressions as separate occurrences; do not repair expressions.
- Reuse the same collector on the reconstructed document, never the extraction
  inventory or its pages. Preserve model-free reconstruction and unchanged
  formulaEnrichment/codeEnrichment options. No LLM/model/extraction pass is added.
- Verify Docling 2.141.0/Core 2.99.0 APIs and test real parser limitations honestly:
  current Markdown/Marko GFM does not turn dollar-delimited math into FormulaItems.
  Cover edited/added/deleted source expressions with that real backend; separately
  inject a controlled formula-bearing backend result to verify regenerated values,
  references, sections and absent page provenance. Do not describe the latter as
  real Markdown math support or guarantee complete/inline formula detection.
- Focused tests cover available/unavailable LaTeX independent of enrichment flags,
  empty inventory, repeat identities/occurrences, section mapping, JSON backslash
  round-trip, reconstruction, older reviews and empty media inventories. Run the
  applicable regressions; disclose real-model checks not run for this supplement.
- Keep webhooks and code content unchanged. No codeBlocks/codeBlockCount,
  Akay.Be/database/migration work or summary/glossary generation. Consumers read
  review.json; later consumer features remain outside this implementation.

Exit: coherent supplemental inventory in initial/rebuilt/media reviews, compatible
legacy reads, focused/full regression evidence and preserved documentation history.
Stop after reporting this supplement; no new task is selected automatically.

## N0 — Reconcile and freeze the implementation baseline

Specification: sections 1-5, 20.

- Read git status, current instructions, README, old progress records and existing Docling T0 probes/contracts if present.
- Inventory completed work against this specification, especially new main/additional semantics, three workers, image inventory, media JSON and YouTube.
- Preserve verified dependency choices where compatible. Recheck heading hierarchy, confidence, JSON reload, referenced figures and OCR text-layer repair against the pinned APIs; do not invent fields.
- Confirm the first embedding provider/model and compatible tokenizer before N10. Initial selection is now approved: AzureOpenAI / text-embedding-3-small / 1536 / cl100k_base. Endpoint/deployment/authentication are separate pending Azure inputs; the example's remaining values are not approved production settings.
- Confirm Blob artifact naming, the fixed section UUID namespace/canonicalization and durable coordination choices. Section marker syntax is already specified; do not reopen the structural-vs-semantic-tag question.
- Record physical queue/image/app names and later Azure prerequisites when supplied; do not probe credentials or remote environments to discover them.
- Treat operationSequence as an index-operation counter, not a document version.
- Run baseline applicable local tests. Record pre-existing failures by exact test name/command.

Exit: a short compatibility/reuse map and progress record with observed baseline checks and scoped pending configuration.

## N1 — Separate worker entry points and settings

Specification: sections 3-4, 18.

- Keep one repository/package structure with three runtime entry points, e.g. akay-convert-document, akay-transcribe-media, akay-index-content.
- Reuse Blob, Service Bus, authentication, webhook and safe logging helpers. Avoid a generic framework rewrite.
- Extract only the shared processing interfaces needed by those entry points.
- Keep Speech/FFmpeg and Docling wiring/imports separate; preserve existing audio/video implementations where possible.
- Each worker validates only its own required settings. Document how the existing command is replaced or retained as a documentary alias.
- Do not leave two different workers consuming the same mixed queue.

Exit: isolated startup/settings/dispatch tests; converter starts without Speech/Qdrant, transcriber without Docling/Qdrant, indexer without Speech/FFmpeg.

## N2 — Implement the new contracts

Specification: sections 5-12, 14-16.

- Create typed, validated envelopes for document conversion, Blob/YouTube media, index/delete and their webhook results.
- Enforce documentOptions booleans, source discriminators, schemaVersion, callback identity, positive operationSequence for index jobs and immutable request identity.
- Reopen only the affected N2 contract slice for `documentOptions.ocrLanguage`: optional string, exactly es/eu/gl/ca/fr/en/de, default es when omitted; reject null, empty/whitespace and unsupported/wrong-type values. Update fixtures, effective request identity, validation tests and docs; preserve unrelated completed N2 work. Document OCR only, not translation or Speech. The supplemental operation/extraction-review delta is implemented in N9A, without restarting unrelated completed work.
- contentKey/scopeKey/payload remain domain-neutral. Protect reserved index metadata fields from caller overrides.
- Define typed artifact results: document Markdown/Docling/review/figures; media Markdown/transcript/review.
- Store the image inventory only in review.json. Do not add image-list/ImagesPrefix fields to completed callbacks.
- Include the superseded-operation event and durable ordering acceptance tests.
- Validate JSON examples/fixtures, including null/absent grade and time values; forbid NaN/Infinity.

Exit: contract tests for all variants, invalid combinations, wrong types, unknown options and exact payload forwarding. Update consumer-facing docs with these contracts.

## N3 — Implement document extraction through Docling

Specification: sections 6, 9, 19.

- Replace MarkItDown behind the existing document-conversion abstraction.
- Standard/docling_parse, bounded OCR, accurate tables, heading hierarchy and picture crops/referenced export; disable VLM/classification/description.
- Map each request's `ocrLanguage` to the pinned OCR engine's supported configuration; one selection per conversion, no global override or silent substitution. Verify compatible local resources for all seven languages; perform immediate real OCR verification in Spanish and record unverified quality per language. Inspect explicitly authorized existing caches/paths before fetching; the Hugging Face hub root is not an `artifacts_path` bundle. Report exact missing-resource commands/destination before any download; reuse compatible assets without reinstalling Docling.
- Apply code/formula flags independently. Verify the four combinations.
- Preserve PDF/DOCX/PPTX/HTML/HTM/TXT/MD support; preserve ordinary headings in additional documents.
- Do not fetch arbitrary linked resources. Do not introduce a MarkItDown or speculative parser fallback.
- Define explicit empty/partial/failure behavior. Do not call an incomplete document completed.
- Make blocking inference cancellation-safe; cancelling an await on a thread does not terminate inference.
- Scope clarification: N3 verifies the ConvertToMarkdown integration, not OCR/model repair or character-perfect recognition. Preserve selected options and upstream results/status/errors. Record observed recognition limitations without making optical-quality diagnostics an integration release gate. Keep optional quality diagnostics separately selectable and retain their observed failures.

Exit: controlled document fixtures verify successful invocation, option forwarding, usable content/structure, export/reload and error handling with honest warnings. Recognition-quality limitations are documented, not repaired in N3. PDF rendering used internally must not cause uploaded full-page screenshots.

## N4 — Generate principal sections and review data

Specification: sections 7, 10.

- Generate the specified UUID section markers only when extractSections=true.
- Use the same section-ID function for Markdown and review metadata; repeated titles have distinct IDs.
- Preserve parent/order/level/Docling references and define preamble behavior without synthetic sections.
- Build review.json summary, tables, figures, warnings and available confidence from ConversionResult.
- Do not emit semantic taxonomy tags or add an LLM.
- Additional documents and all media have sections=[]; figure inventory lives only in review.json.
- Preserve valid image references and prevent path traversal/local path leakage.

Exit: structural tests cover nested/repeated headings, idempotent markers, additional documents, unavailable confidence and referenced images. JSON reload retains usable references.

## N5 — Publish complete artifact sets

Specification: section 9.

- Derive the artifact subdirectory from destinationBlobName as specified, so different Markdown files in a shared parent cannot collide.
- Do not move/copy originals or derive paths from TopicContent fields in payload.
- Reuse existing storage auth/streaming mechanisms, adding target-scoped coordination/conditional writes.
- Store the full set before success notification; recover from partial uploads and reject conflicting reuse.
- Treat a legacy Markdown-only result as incomplete for the new contract.
- Reuse complete results on callback retry without reconversion.
- Clean only this attempt's uncommitted resources; protect other contents and already published artifacts.

Exit: upload-midway failure, shared-parent destinations, destination races, overwrite/non-overwrite, callback retry and cleanup tests. Writing Markdown last alone is not sufficient proof of consistency.

## N6 — Separate and normalize media transcription

Specification: sections 8-11.

- Reuse Azure Speech Fast Transcription and FFmpeg/FFprobe from the existing worker.
- Keep Blob media format coverage and audio-only WebM behavior.
- Preserve phrase segments/timestamps instead of dropping all structure into a combined string.
- Produce readable Markdown, transcript.json and review.json; do not create PDF-style scores or Topic sections.
- Keep the canonical property name transcriptJsonBlobName.
- Ensure content in Markdown and transcript JSON agrees and units/ranges/speaker/language values are validated.
- Publish/reuse the complete artifact set through the shared storage mechanism.

Exit: audio/video regression fixtures, no-audio/invalid-media/size/duration failures, nullable temporal metadata and same-content Markdown/JSON tests. Default tests use Speech doubles, not billable Azure calls.

## N7 — Add YouTube as a media source

Specification: section 8.2.

- Handle source.type=youtube within transcribe-media; no new worker, queue or Service Bus Topic.
- Validate a supported individual YouTube URL/video ID and retrieve the audio only with a pinned extractor.
- Include required JavaScript/runtime dependencies for the selected extractor release.
- Reuse FFmpeg/Speech transcription and the same artifacts/webhooks.
- Reject playlists, live streams, unknown hosts/protocols and unsafe destinations/redirects.
- Enforce download byte/duration/time/temp limits; reject caller-supplied executable arguments, cookies and credentials.
- Preserve stable origin URL/video identity, not expiring audio URLs. Do not automatically crawl document links.
- Reuse a published result if only notification needs retry.

Exit: mocked extractor tests cover source routing, unsafe URL/redirect, timeout, byte-limit, unavailable/private video and cleanup. Real YouTube testing is separately authorized and its limitations recorded.

## N8 — Preserve processing reliability

Specification: sections 5, 9.5, 16.

- Reuse settlement, callback allowlists/authentication and bounded local retry policies across the workers.
- Success is processing/publication plus callback success; permanent failures notify safely; transient failures are retried.
- Capture stable outcomes for notification-only retries.
- Lock renewal covers the whole workflow and margin. Stop work safely before cleanup/releasing ownership.
- No secret/content logs or subprocess-output leakage in errors.
- Document DLQ behavior honestly; do not invent a final failure callback after retry exhaustion.

Exit: repeated callback, transient/permanent failures, lock loss, shutdown/cancellation, event-loop responsiveness and temporary-resource tests.

## N9 — Adapt documents and transcripts for chunking

Specification: sections 12-13.

- Load saved Docling JSON without source reconversion or unrestricted local image fetching.
- Build a Docling Core document from transcript segments, preserving a source/segment-to-time mapping; do not run ASR.
- Support fixed, fromReview and generic none section contexts.
- Enforce domain section boundaries explicitly, including identically named sections; do not rely only on matching heading strings.
- Retain internal headings from additional documents while attaching their supplied parent context.
- Use HybridChunker with a compatible tokenizer and count the full contextualized text.
- Preserve clean text, context, source, pages/times and item references without fabricated provenance.

N9A adds focused integration checks for reconstructed JSON/review and corrected transcript segments. Keep this task complete if its existing implementation passes those checks; correct only affected seams in N9A if needed.

Exit: both formats yield bounded chunks with correct sections and citations, including repeated headings and split/merged transcript segments.

## N9A — Prepare reviewed content before indexing

Specification: sections 2.1.1, 5.1, 6.1-6.3, 7, 9-11, 13, 17.3 and acceptance criteria 19-23.
Prerequisite: N9 complete. Mandatory next task before N10. Status: pending until repository implementation and checks prove completion.

This is one supplemental behavior change across the existing converter, contracts, storage and chunking seams. Reuse the helpers and functionality completed in N2-N9; do not rebuild the workers or reopen unrelated completed tasks. Record the delta against those tasks in the existing progress record.

- First reconcile this revision with the repository's own specification/plan/progress copies. Preserve compatible local changes, including the already agreed OCR-language support; do not overwrite newer work blindly.
- Extend document request validation with operation=convert|rebuildFromMarkdown, default convert when omitted. Require extractionReviewBlobName only for reconstruction and validate ownership/contentKey and authorized Blob destinations. Preserve multimedia envelopes and index-content unchanged.
- Return the document operation in completed callbacks and recoverable document failures. Keep document.conversion.completed and the existing artifact-reference shape; do not add another image inventory or automatic indexing.
- Reconstruct a new DoclingDocument from frozen Markdown in Blob. Regenerate document.docling.json, headings/section IDs, markers and review.json from current content. Discard stale Akay markers structurally without interpreting headings inside code blocks as sections. Do not reuse the original JSON text or references.
- Do not invoke OCR, PDF/layout/table inference, code/formula enrichment, picture extraction or URL fetching for reconstruction. Reject true code/formula enrichment flags for this operation; normal Markdown parsing still preserves representable code/formulas/tables.
- Preserve existing image files and the extraction inventory in final review.json. Do not fail solely because an edited Markdown image link is removed, changed or nonexistent. Do not repair/fetch those links or expose arbitrary file/network access. Preserve edited Markdown except regenerated markers and necessary rebasing of existing relative image paths.
- Publish a coherent final Markdown/Docling JSON/review set to destinations separate from both the frozen draft and original extraction report. Keep extractionReviewBlobName in final review.json and processing.operation explicit. Preserve shared extracted image files across retries/cleanup.
- Final sections/tables come from the reconstructed document. Do not copy original page/coordinate provenance onto edited text. Final confidence is unavailable/null with pages=[]; the original report remains the source of extraction-only page diagnostics. Image entries can retain explicitly original provenance.
- Use N9 to prove changed text and renamed/added/deleted/reordered headings reach the final chunks, including repeated titles, with matching final review references and no stale section markers/text. Prove repeat requests are idempotent and notification-only retries do not rebuild artifacts.
- Feed corrected-transcript fixtures through N9: change only segment text and verify chunk content changes while IDs, ordering, origin and available time mapping survive. Do not call Speech, implement a transcript editor, add a media operation or pretend that .NET persistence already exists.
- Preserve no-edit conversion and media behavior. Verify default convert compatibility, the agreed OCR-language validation, malformed contracts, missing/wrong-content extraction reports, same-path draft/output rejection, image-link tolerance, no remote fetching, and partial-publication/callback-retry behavior.
- Document consumer responsibilities only: editing/saving drafts and segment text, freezing on approval, persisting final sections, sending final artifact references to the indexer, and disallowing edits after approval. Do not implement Akay.Be, databases, UI or approval states in Python.

Exit: updated contracts/fixtures and focused tests demonstrate extraction -> edited Markdown -> final structured artifacts -> N9 chunks, plus corrected transcript -> N9 chunks. Original extraction diagnostics/assets survive and final artifacts contain the corrections. Record actual checks, pending real-model checks and blockers honestly. Mark N9A complete before selecting N10; N0-N9 remain completed where their evidence still holds.

## N10 — Embed and index point sets

Specification: sections 12.3-13.
Prerequisites: N9 AND N9A complete; production embedding provider selected. If the agent was previously assigned N10, finish N9A in a separate session first.

**Approved selection (2026-11-14):** AzureOpenAI, text-embedding-3-small, 1536
dimensions, cl100k_base. No Azure OpenAI resource or embedding deployment exists.
Do not invent a deployment name, credentials or model revision. Missing Azure
provisioning/configuration does not block this task's local adapter verification.

**Implementation boundary:** N10 supplies a serialized-call local API, a
configurable Azure REST adapter and Qdrant point-set primitives. Its offline
checks use explicit synthetic settings, stub embeddings and persistent local
Qdrant; no live-service calls or Azure provisioning. N11 still owns durable
admission/ordering, receipt-based callback replay and queue activation. Consult
the progress record for actual observed checks; local N10 completion is not
verification of the production integration.

- Implement only the selected production embedding adapter, plus a test double. Secrets/endpoints come from controlled settings.
- Require an explicit endpoint/deployment/authentication mode for real Azure calls; support API-key or explicitly supplied Entra token acquisition without ambient credential fallback. Keep tokenizer assets local/hash-verified and model revision absent until approved. Record pending provisioning, deployment settings, quotas and authorized live verification separately.
- Validate immutable profile identity, tokenizer, limits, model/dimensions/distance and collection compatibility.
- Generate deterministic UUID point IDs independent of requestId.
- Use bounded batches, retries and vector validation.
- Store scope/content/profile/section/provenance and protected metadata in Qdrant.
- Index filter fields and acknowledge all desired writes before completion.
- Repeated indexing converges; fewer chunks and changed section context leave no stale points.
- Keep fingerprint optional/internal. Webhook index result requires profileId and chunkCount, not another model registry.
- Add an integration case indexing the final JSON/review produced by N9A, not the initial extraction, and another using corrected transcript segments. Assert stored text/section/provenance matches those inputs. The indexer does not query Akay's approval state; the consumer controls when it sends index-content.

Exit: local-Qdrant tests with stub embeddings cover dimension/model mismatch, token bounds, repeat indexing, partial batches, scoped point identity and complete replacement.

Production evidence remains separate: provision the approved Azure resource and
deployment later with authorization, supply endpoint/authentication and effective
profile/target settings, then run explicitly authorized Azure/Qdrant-server checks.
Neither the initial selection nor local HTTP mocks establish that integration.

**Observed checkpoint:** N10's local acceptance is complete; exact RED/GREEN,
persistent local-Qdrant and real-tokenizer probe results are recorded in
`docs/docling-rag-progress.md`. Azure provisioning/deployment/live verification
remain pending. The next implementation task is N11 in a fresh session.

## N11 — Serialize index/delete and support reassignment

Specification: sections 5.2, 14-16.

- Use durable, cross-replica latest-operation state per scopeKey/contentKey, including request/sequence consistency.
- Guard every mutation against stale operations. Define recovery after Qdrant succeeds but receipt/callback fails.
- Emit the superseded result for stale jobs without resurrecting points.
- Delete only the requested content/profile/destination. Never delete Blob artifacts or database records.
- Repeated delete succeeds; a later reassignment uses a higher sequence and existing artifacts.
- Old index jobs, duplicate deliveries and a lost lease cannot recreate data after a completed delete.
- Preserve profile-destination information needed for explicit cleanup if profiles migrate.

Exit: out-of-order operations, duplicate/conflicting sequences, index/delete races, cross-profile stale work, receipt failure and lost-lease tests against persistent state and local Qdrant.

## N12 — Package three isolated dependency sets

Specification: section 18.1.

- Move dependencies into separate installation groups/targets with a genuinely minimal shared base.
- Remove MarkItDown once the replacement path and tests pass.
- Converter installs only document extraction dependencies/assets.
- Include the resolved OCR resources for es/eu/gl/ca/fr/en/de, deduplicating shared weights where the pinned registry allows it; retain per-conversion selection/default es. Lock resources for layout, accurate tables and offered code/formula flags, without ASR/Whisper or picture description/classification models.
- The same converter installation supports convert and rebuildFromMarkdown; reconstruction adds no OCR/ASR/VLM weights. Include the agreed OCR language resources without reverting compatible existing packaging work.
- Transcriber installs only media/Azure/extractor dependencies and required tools.
- Indexer installs Docling Core/tokenizer, embedding/Qdrant and technical Azure clients, not full Docling extraction.
- Pin compatible versions and resolved dependencies; prefer CPU packages for CPU deployments.

Exit: inspect installed distributions/import graphs for each isolated target. Startup tests prove absence of mandatory settings/imports from other targets.

## N13 — Build three images

Specification: section 18.1.

- Build three targets or Dockerfiles with non-root runtime and bounded writable temp directories, no ingress.
- Prefetch only required converter model assets and indexer tokenizer assets. Verify all enabled code/formula/OCR paths.
- No Whisper/ASR/VLM weights. Do not remove shared libraries actually required by document features.
- Validate FFmpeg/FFprobe/extractor dependencies in the transcriber only.
- Test local extraction/tokenization with model download access blocked; network calls to application services are separate.
- For the document image, prove all seven OCR selections resolve local resources under the non-root runtime with downloads blocked. Test Spanish OCR immediately; disclose any other language's unverified real quality separately from resource availability and mocked checks. Do not enable seven languages simultaneously.
- Smoke-test both document operations in the converter image, proving reconstruction does not initialize/download extraction models. Verify configured OCR resources for all seven supported languages and record any quality checks not performed.
- Report actual image sizes and fixture resource observations, not estimates as measurements.

Exit: three build and smoke-test results, independent entry points and installed dependency/asset evidence.

## N14 — Test/build/publish three GHCR images

Specification: section 18.2.

- Adapt the existing GitHub Actions workflow to the three targets.
- Test before publish/release; smoke-test all images.
- Use one release identity and immutable SHA tags/digests; avoid latest for deployments.
- Avoid release-tag allocation races and do not tag a successful release before the full build set succeeds.
- Share caches safely; never embed downloader credentials in layers or logs.
- Keep registry publication gated until explicitly authorized.

Exit: workflow syntax/structure checks and local build evidence. A prepared workflow is not proof it ran remotely.

## N15 — Prepare three Azure Container Apps deployments

Specification: sections 4, 18.2, 20.

- Separate image/entry point, queue/scaler, identity/secrets, resources and replica controls for all three apps.
- Preserve the approved existing converter deployment where appropriate; document creation/bootstrap of the other apps and queues.
- Use explicitly authorized Azure authentication, preferably OIDC, and separately configure GHCR pull credentials.
- No HTTP ingress and no assumption that runtime consumer permissions automatically configure scaler authentication.
- Gate deployments through an approved environment/manual selection until Akay.Be producers/consumers are coordinated.
- Provide rollback and mixed-release/cutover instructions for the old mixed queue and new routes.
- Do not implement Akay.Be deployment or migrations in these workflows.

Exit: validated configuration plus an explicit pending/observed status for real staging deployment and end-to-end smoke checks. Missing cloud inputs remain clearly documented.

## N16 — Verify and hand off

Specification: sections 17, 19-20.

- Provide sample requests for principal/additional document, Blob audio/video, YouTube, both index formats, reassignment and delete.
- Add extraction -> editable draft -> rebuildFromMarkdown -> final index examples and corrected-transcript fixtures. Explain no-edit artifact reuse, provisional versus final sections, extraction-only grades, preserved image assets and tolerated user-edited image links.
- Provide a local callback receiver and service doubles; avoid default cloud dependencies.
- Run the applicable suite, local end-to-end flow and image checks.
- Verify no duplicated image inventory, no automatic URL crawling, no document-history feature, no deletion of detached additional resources.
- Update README and operator docs for three queues/images/apps, configuration, source restrictions, errors and technical sequence/state.
- Produce an Akay.Be/manual-database handoff, including accepted-state filtering, section persistence, nullable assignments, immutable profiles, operationSequence, message routing, review access and webhook deduplication.
- Include future Markdown/segment-text editors, draft/transcript persistence, regenerated transcript Markdown, approval freeze, latest-request callback handling, final-section persistence before attachment, and deletion/new upload for post-approval changes. Keep these explicitly outside Python implementation scope.
- Report all failed, skipped, blocked or pending checks honestly. No claim of a working .NET acceptance/chat workflow.

Exit: a reproducible local handoff and exact remaining external actions.

## Per-session prompt for the implementation agent

~~~text
Read the repository instructions and current README, then:
- docs/content-processing-specification.md
- docs/docling-rag-implementation-plan.md
- docs/docling-rag-progress.md, preserving existing entries and evidence.

Work only on task N9A of the revised plan. Do not execute N10 or another task.
N9A is mandatory after N9 and before N10. Preserve completed compatible N0-N9.
Check actual code and prerequisite evidence; reuse completed compatible work.
Ask one focused question only if an essential decision blocks this task.
Add/run the task's tests and update the progress record with:
task ID, decisions, changed files, observed checks, blockers and next prerequisite.

Do not modify Akay.Be or databases. Do not publish, push or deploy.
Stop after reporting this task's result.
~~~

This revision's resume prompt deliberately selects N9A, not N10. In subsequent fresh sessions replace N9A with the explicitly assigned task only after prerequisites pass. If using automatic next-task selection, follow the dependency table, not integer-only sorting: N9 -> N9A -> N10. Keep progress in the implementation repository so a new session does not depend on previous chat history. Use English for code/comments/docs in that repository unless its instructions or the user explicitly require otherwise.

## Verification discipline

For runnable deterministic behavior changes, observe focused RED before implementation, then GREEN and the applicable existing suite. Passive contract/document changes use structural validation instead of invented RED evidence.

Follow the repository's branch/commit/review policy. Keep behavior, tests and documentation together. Do not interpret a document task checkbox as proof or as authorization to publish.

## Change from the original plan

- Two images -> three; media now has its own worker/image/queue.
- Main document only creates Akay sections; additional documents are assigned later.
- Additional contents survive principal replacement and can be reassigned.
- Timed transcript JSON and media RAG are in scope.
- Explicit YouTube source shares the media queue; no Topics.
- Images are inventoried only in review.json.
- contentKey, scopeKey and immutable index profiles remain generic.
- Fingerprint is optional/internal.
- operationSequence and durable ordering prevent stale index/delete resurrection.
- Artifact subdirectories prevent sidecar collisions for Markdown files sharing a parent.
- Revision 2026-11-14 adds pre-approval Markdown editing and segment-text correction. Approved contents are immutable; post-approval changes require deletion/new upload. No historical document-version feature is added.
- N9A is a pending mandatory prerequisite of N10, not a renumbering or a reset of N0-N9. It implements the converter/artifact contract delta and tests the existing N9 seams; UI/.NET/database work remains deferred.
- Extraction reports/assets remain available separately from final structured artifacts, and only final accepted references are sent for indexing. No fourth worker, image or queue is introduced.
