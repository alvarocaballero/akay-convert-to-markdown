# Content-processing implementation progress

## Supplemental formula inventory — 2026-11-16

**Complete on the locally verified supplemental boundary. N0-N16/N9A and every
earlier checkpoint below remain preserved. This adds only the review.json formula
inventory; it does not select another task or authorize external integration.**

### Scope, pinned APIs and implementation

- Read current instructions, README, specification, plan, latest checkpoint and
  existing extraction/reconstruction/contracts/tests. Initial Git status already
  contained the uncommitted completed implementation/user files; retained them.
  No repository-local AGENTS.md was found. Used the existing CodeGraph index before
  code exploration. No dependencies, models, worker routes or webhook changed.
- Verified installed `docling-slim==2.141.0`, `docling-core==2.99.0` and
  `marko==2.2.5`, exact-version Docling enrichment documentation and installed
  FormulaItem/reading-order/enrichment/Core serializer/Markdown backend source.
  FormulaItem has no separate latex field: PDF reading order sets orig=extracted
  source and text=""; enrichment writes decoded math into text. Nonblank item.text
  supplies available latex, not a guarantee of valid/correct mathematics. Retain
  orig as text when present, otherwise item.text; no expression correction.
- New shared Core-only collector inventories existing FormulaItems in document.texts
  order using the established numbered local convention (`formula-001`, etc.) and
  exact item references. Identical expressions remain distinct occurrences and
  retry output is stable. Section mapping uses body reading order and the emitted
  review sections, not heading strings or text-array order. Preamble/additional/
  non-body elements have sectionId=null. Preserve available first-source page.
- Add typed formulas/formulaCount and inventory consistency checks to review
  contracts. Missing legacy fields default to []/0 without a schemaVersion bump.
  Validate unique occurrence IDs, matching counts and current-review section IDs.
  Media defaults to an empty inventory; reject supplied document formula entries.
- Initial export and rebuild call the same collector on their own current document.
  Rebuild never copies original formulas/pages. Cleanup traverses all content layers
  and picture children so even non-body reconstructed formulas lose provenance.
  Existing image-inventory retention and code/enrichment behavior remain compatible.
- **Verified parser limitation:** the pinned Markdown backend uses Marko/GFM with
  no native math nodes. Dollar-delimited expressions survive as text, not
  FormulaItems, so edited/added dollar math is absent from the inventory. The real
  backend test checks edited/added/deleted expressions, code retention and removal
  of stale extraction inventory. A separately labelled controlled backend-result
  test checks formula-bearing reconstruction, new references/sections, repeat
  output and no page provenance (including notes). It does not claim real Markdown
  math support. No second extraction pass, parser extension, LLM or model was added.

### Exact local verification

PowerShell in `C:\Develop\Akay\Akay.ConvertToMarkdown`, with opt-ins disabled:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS='false'; $env:RUN_DOCLING_MODEL_TESTS='false'; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS='false'
```

| Command/check | Observed result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_formula_inventory.py -q --tb=short` before implementation | **RED: 15 failed, 6 passed in 15.83s**; missing formula fields/export and legacy report rejection. The six negative contract cases already rejected unknown fields; positive behavior failures establish RED. |
| First implementation, same focused command | **2 failed, 19 passed in 25.31s**: Core body-only traversal omitted a non-body FormulaItem. Corrected inventory enumeration to document.texts, retaining body traversal only for section mapping. Added explicit audio/video and non-body rebuild coverage. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_formula_inventory.py tests/unit/test_document_artifacts.py tests/unit/test_docling_conversion.py tests/unit/test_reviewed_content.py tests/unit/test_media_artifacts.py tests/unit/test_content_contracts.py -q --tb=short` | **368 passed, 2 existing warnings in 57.83s**. |
| Final `.venv\Scripts\python.exe -m pytest tests/unit/test_formula_inventory.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q` | **23 focused passed in 22.48s; 1055 passed, 18 skipped, 2 existing warnings in 93.26s** overall, after all-layer reconstruction provenance cleanup. All 1032 previously passing cases plus 23 supplemental cases pass. |
| `.venv\Scripts\python.exe -m pip check` | **PASS:** no broken requirements. |
| `git -c core.autocrlf=false -c core.whitespace=cr-at-eol diff --check` plus per-path `diff --no-index --check -- NUL <path>` with the same settings | **PASS:** no whitespace diagnostics in the supplement. The initial plain whole-tree check reported CRLF as trailing whitespace in the pre-existing modified README; did not rewrite that user file. |

Tests cover available/absent/whitespace/empty decoded math independently of both
formulaEnrichment values, text retention, absent pages, JSON backslash round-trip,
no formulas/code retention, repeated expressions/IDs, nested/repeated sections,
preamble/additional/non-body mappings, legacy reads, count/type/identity/section
validation, reconstruction and media transcript text that resembles math.

### Files, limits and stopping point

- Updated `src/akay_convert_to_markdown/contracts/artifacts.py` and
  `conversion/{document_artifacts,markdown_rebuild}.py`; added
  `conversion/formulas.py` and `tests/unit/test_formula_inventory.py`.
- Updated specification §10.1.1/criterion 25, the plan's explicitly supplemental
  work unit and this prepend-preserving record. No codeBlocks/codeBlockCount,
  webhook inventory, Akay.Be/database/migration, summary or glossary generation.
- **Not reverified here:** real PDF layout/formula enrichment inference, LaTeX
  syntax/mathematical quality, complete formula detection or inline recall. The
  18 skips remain 13 model opt-ins, two quality diagnostics, Azure Blob, missing
  host FFmpeg/FFprobe and unconfigured Speech; the two warnings are upstream OCR
  serialization deprecations. Earlier Spanish OCR and Linux native formula-layout
  limitations remain disclosed below. Historical model/image evidence is not a
  fresh inventory/model result; existing images were not rebuilt for this change.
- No live-service call, model download, external repository change, publication,
  deployment, staging or commit. Rollback boundary is the four scoped source files,
  focused test file and three documentation deltas above; preserve all prior work.
- Stop after reporting this supplement. No next implementation task is implied.

## Current checkpoint — 2026-11-15: N16

**N16: complete on its locally verified handoff boundary. N0-N15 and N9A remain
complete on their recorded boundaries. Reproducible offline processing, routed
samples, a fixture callback receiver and operator/.NET/manual-data handoff are
verified. Production/cloud integration and Akay.Be approval/editor/persistence/chat
are NOT verified. No N17 exists; a fresh session must select one explicitly
authorized external integration follow-up, not infer permission to deploy.**

### N16 prerequisite reconciliation and scope

- Read applicable parent/user instructions (no repository-local AGENTS), current
  README, both complete authoritative documents, all 2313 preserved progress lines,
  N0's compatibility/frozen decisions and the historical T0 progress. Checked Git
  status/root/CodeGraph before filesystem code exploration. Actual strict contracts,
  entry/settings/consumer, Docling/publication/rebuild/media and local ordered
  indexing agree with their recorded verification and current regression results.
- Starting at N0 in dependency order, N0-N15/N9A retain compatible implemented
  boundaries and evidence. Reverified **128** deployment/CI/image/packaging/worker
  cases first. N15's offline generator/gates/app fixtures exist; external Azure
  checks remain honestly pending. N16 had no runnable combined handoff or local
  callback receiver, making it the first incomplete task. Executed **only N16**.
- Initial Git status already contained uncommitted N0-N15/N9A/user work. Preserve
  every earlier checkpoint/file. No application source, dependency pin/lock,
  Dockerfile or workflow changed in N16. New tests are discovered by the existing
  default CI suite; the fixture receiver is not a worker HTTP endpoint/image layer.

### N16 changes and decisions

| Area | Implemented and locally verified handoff |
| --- | --- |
| Complete sample envelopes | Twelve synthetic requests: principal/additional documents, frozen-draft rebuild, Blob audio/video, explicit YouTube, final principal/additional/transcript indexes, scoped principal/transcript deletes and higher-sequence reassignment. Parse all with their proper worker/allowlisted callback; unique operation UUIDs. Full sample profile/deployment/collection/budget/distance/association IDs are illustrative, not production choices. |
| Offline flow | Development-only tool reuses existing MemoryBlobs/conditional leases, receiver/renewal and embedding doubles. Actual document/model-free extraction, rebuild/export, publisher, consumer processing/settlement, Speech multipart/normalization, media strategies, HybridChunker and ordered Qdrant point writes run with explicit fixtures. No generic runtime framework or new parser/adapter. |
| Resource boundaries | Empty home, allowlisted/scrubbed environment, socket/DNS/connect traps and DefaultAzureCredential/image-loader traps. CLI requires an explicit existing official-hash tokenizer file. Reuse actual Qdrant client persistent local mode and reopen it. Test suite uses an explicitly injected character counter; only the separate CLI evidence establishes real tokenization. No Azure client/credential construction, remote APIs or asset download. |
| End-to-end invariants | Corrected final text/repeated final section IDs reach points with no inherited page confidence. Additional document retains headings without sections/markers; all three media routes retain source/segments. Simulate consumer-only text correction and concordant Markdown without new Speech calls. No index on conversion. Callback acknowledgement loss abandons once, then recovers without source/report or confirmed embedding repetition. Principal delete preserves additional points; explicit detach/delete and stale replay cannot resurrect audio. Reassignment reuses artifacts/context with a higher sequence. All original/derived bytes survive. |
| Callback receiver | Loopback-only stdlib HTTP server, explicit synthetic key, strict version-one parser/key binding, bounded 1 MiB bodies/1000 events, equivalent-repeat dedupe, changed-body conflict and optional stored-event/lost-ack 503. Actual HTTPX WebhookClient -> listening loopback server retry passes. In-memory receipts are intentionally fixture-only; no domain authorization/approval/durable inbox claimed. Logs omit contents/keys. |
| Operator/consumer delivery | New quick-path handoff and operator guide, acceptance-to-test map and ordered external action list. Define draft/segment editors, approval freeze, final section persistence, nullable additional assignments/no cascade deletion, immutable profiles, sequence allocation, reliable publication/inbox, current-callback filtering, accepted/authorized retrieval, exact cleanup and cutover/rollback as future consumer work. No SQL, schema changes, migrations or .NET implementation. |
| Documentation reconciliation | Correct current README/feature-guide statements that still called implemented N8/N11/N13 behavior pending. Preserve historical baseline and progress unchanged. Link the coherent three-route/image/config/recovery/handoff path; production release/deployment/.NET remain explicitly unverified. |

Pinned Qdrant client **1.19.1** local/async/scroll APIs and HTTPX **0.28.1**
MockTransport/environment opt-out were checked against official exact-version
Context7 documentation and actual calls. Existing Docling/Core/Blob APIs/pins are
reused. The new handoff links these references and existing exact-version guides.

### N16 exact checks and observed results

PowerShell in `C:\Develop\Akay\Akay.ConvertToMarkdown`; regression opt-ins:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS='false'; $env:RUN_DOCLING_MODEL_TESTS='false'; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS='false'
```

| Exact command/check | Observed result |
| --- | --- |
| Opt-ins above + `.venv\Scripts\python.exe -m pytest tests/unit/test_deployments.py tests/unit/test_ci_release.py tests/unit/test_images.py tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py -q --tb=short` | Prerequisite **128 passed in 29.30s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_handoff.py -q --tb=short` before implementation | **RED: 5 failed in 9.75s**: missing complete sample file, receiver module and runnable combined harness. After implementation **5 passed in 17.13s**; added scrub/guard/interruption/refuse-overwrite case, all six included below. |
| `Test-Path -LiteralPath ".local"; .venv\Scripts\python.exe -m tools.content_processing_demo --tokenizer .local/cl100k_base.tiktoken --output .local/n16/handoff-01` | **PASS**, actual CLI/real official-hash tokenizer with all application sockets blocked: eight boundary checks, **13 completed / 2 intentional abandons**, 13 unique events/15 deliveries, 2 remaining persistent local points. Exactly 2 model-free extractions, 3 mocked Speech requests, 3 probe/2 extraction process doubles and 1 YouTube double; no repeat source/embedding work on callback replay. Evidence under that exact ignored directory. Two safe processing-failed logs are expected acknowledgement-loss cases, not unresolved failures. |
| `test_actual_loopback_receiver_with_real_webhook_retry` in the final suite | **PASS**: actual ephemeral 127.0.0.1 listener + real WebhookClient/HTTPX transport, accepted first event returns 503, identical retry returns 200 with one stored event; wrong path/auth rejected. Separate inbox tests cover strict JSON/key, equivalent dedupe, changed-body conflict and memory/body limits. |
| `test_demo_scrubs_environment_blocks_network_and_restores_state` in the final suite | **PASS**: injected synthetic secret/proxy absent inside owned environment; DNS/connections forbidden; environment/socket state restored after forced interruption; reused output directory refused. No ambient credential value was discovered. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_handoff.py tests/unit/test_reviewed_content.py tests/unit/test_content_contracts.py tests/unit/test_content_indexing.py tests/unit/test_ordered_indexing.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q` with opt-ins above | Final **302 focused passed in 31.40s**; **1032 passed, 18 skipped, 2 existing warnings in 65.08s** overall. All prior 1026 cases plus six N16 cases pass. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | **PASS**: no broken requirements and both pinned API/backend/confidence/referenced-image/Core reload/frozen-UUID PASS lines. |
| `.venv\Scripts\python.exe tools/verify_assets.py --document-dir .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken` | **PASS**: all 19 locked model files, seven OCR selections/shared three weights and official tokenizer hash. No fetch. |
| Image commands below | **PASS**, all three startup/engine phases, separate fresh-process document rebuild and seven-language/full-model initialization; exit 0/no OOM, network none/non-root/read-only/bounded temp. Exact evidence directories below. |
| `git -c core.autocrlf=false diff --check`; per-file new/untracked checks below; `git check-ignore .local/n16/handoff-01/report.json`; final `git status --short --untracked-files=all` | No whitespace diagnostics; generated fixture evidence ignored. Initial user/N0-N15/N9A working-tree paths preserved. Nothing staged/committed. |

Exact image commands (unchanged existing N13 checker, explicit local engine):

```powershell
.venv\Scripts\python.exe tools/check_images.py --docker-host "npipe:////./pipe/dockerDesktopLinuxEngine" --document-models .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken --skip-build --smoke startup
.venv\Scripts\python.exe tools/check_images.py --docker-host "npipe:////./pipe/dockerDesktopLinuxEngine" --document-models .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken --target document --skip-build --smoke rebuild
.venv\Scripts\python.exe tools/check_images.py --docker-host "npipe:////./pipe/dockerDesktopLinuxEngine" --document-models .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken --target document --skip-build --smoke models
```

- `.local/n13/run-j4lzjiha`: document/media/index startup **7.31/1.96/4.47s**
  inside the container; actual dependency/import separation, both document operations,
  real FFmpeg/FFprobe audio-only WebM->OGG, bundled Deno/EJS and corrected saved
  transcript/local tokenizer/persistent local Qdrant. Index missing-config exit 2
  is expected; configured composition uses explicit service doubles.
- `.local/n13/run-hmqgo0bh`: fresh-process document rebuild **3.26s**, max RSS
  479048 KiB; no extraction pipeline/model/resource fetching.
- `.local/n13/run-uz85vvpl`: seven OCR selections plus layout/accurate table/code/
  formula initialization **8.60s**, max RSS 1103684 KiB. Existing upstream rope/
  tied-weight warnings remain; this is loading, not a new quality measurement.
- Checked existing exact N14 image IDs: document `4498fd1713e1780441cb85e17d2ee39386a05ea2674284e7dc2a2c0417f2a406`,
  media `0f6546d7972505feec3fe86bb9e17de2e02dafc8dcb9c7be07160e9dc8f1e529`,
  index `0ac7e469db2b77ca9584139ebc9c7b2e48fba667e900f1e83c487644f338ee4c`
  (all `sha256:`). Sizes remain **4647694076 / 1264186064 / 658554356 bytes**.
  No rebuild/publication in N16: application bytes, runtime locks and Docker inputs
  are unchanged; current README metadata is not claimed rebuilt into those wheels.
  N14's complete build/six-phase inference evidence remains compatible historical
  evidence, not a new inference run. No need to repeat expensive unchanged OCR/
  formula quality diagnostics; their known failures remain disclosed.

Per-file whitespace check, including all 19 N16 paths:

```powershell
foreach ($path in @('tools/callback_receiver.py', 'tools/content_processing_demo.py', 'tests/unit/test_content_handoff.py', 'tests/fixtures/content_processing/handoff-requests.json', 'docs/content-processing-handoff.md', 'docs/content-processing-operations.md', '.gitignore', 'README.md', 'docs/content-processing-contracts.md', 'docs/content-processing-reliability.md', 'docs/content-processing-ordering.md', 'docs/content-processing-deployment.md', 'docs/content-processing-images.md', 'docs/content-processing-chunking.md', 'docs/content-processing-docling.md', 'docs/content-processing-reviewed-content.md', 'docs/content-processing-media.md', 'docs/content-processing-youtube.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }
```

### N16 acceptance, files and next session

- New files: `tools/{callback_receiver,content_processing_demo}.py`,
  `tests/unit/test_content_handoff.py`,
  `tests/fixtures/content_processing/handoff-requests.json`,
  `docs/content-processing-{handoff,operations}.md`.
- Scoped updates: `.gitignore` (only `/.local/n16/`), README, the ten feature guides
  listed in the command above (current-status/link corrections) and this preserved
  progress record. Specification/plan, app source, runtime dependencies, Docker and
  CI/deployment configuration and all other user files remain unchanged by N16.
- Local exit met: reproducible complete flow, all required validated source/index/
  reassign/delete examples, real local callback receiver plus service doubles,
  applicable suite/image checks, preservation/no crawling/no auto-index invariants,
  coherent operator docs and an explicit future .NET/manual-data handoff. No known
  failing/skipped N16 acceptance check remains. No production semantic/retrieval or
  cloud/domain guarantee is inferred from these tests.
- Pending external checks/actions are enumerated in the new operator guide: physical
  approved configuration/bootstrap, embedding resource/deployment/full profiles/
  quotas, Qdrant-server/Azure actual transports/leases/replication/RBAC, live Speech/
  YouTube compatibility, real remote CI/GHCR/OIDC/pull/Key Vault/staging/scaling/
  termination/load/cutover/rollback, and actual .NET editors/approval/persistence/
  callback filtering/accepted-state retrieval/chat. No credentials discovered,
  live application service called, other repository/database modified, migration,
  resource creation, push/publication/deployment or commit was performed.
- The **18 skips** remain 13 local-model opt-ins, two separate quality diagnostics,
  disabled Azure Blob, absent host FFmpeg/FFprobe and absent Speech settings. Two
  default warnings remain upstream OCR-option serialization. Known Spanish accent
  fidelity and Linux native-formula classification diagnostic failures persist;
  real eu/gl/ca/fr/en/de quality remains individually unmeasured. Fresh image loading
  and media tool checks above do not retroactively execute skipped host tests.
- **Next fresh session:** no pending N-task remains. Select one separately scoped,
  explicitly authorized external integration follow-up from the operator guide;
  production target/credential decisions remain unresolved and must not be invented.
  Do not reopen completed tasks wholesale or create an implicit N17/deployment.
- Rollback unit: six new N16 files and the thirteen scoped ignore/README/guide/
  progress updates listed above. Preserve all earlier checkpoints/runtime work.
  Generated `.local/n16/` evidence is tool-owned synthetic data, not a public
  artifact or production state; no cleanup is necessary to preserve the handoff.

## N15 checkpoint — 2026-11-15 (preserved)

**N15: complete on its locally verified deployment-preparation boundary. N0-N14
and N9A remain complete. Next fresh session: N16 only. Three offline app templates,
manual environment/OIDC gates and single-app delivery/postchecks are verified with
local fixtures/doubles. Real Azure validation/deployment, bootstrap, staging and
N14 remote publication remain NOT verified. No cloud operation is credited.**

### N15 prerequisite reconciliation and scope

- Read applicable parent/user instructions (no repository-local AGENTS), current
  README, full authoritative specification/plan, N0 compatibility map and all 2203
  preserved progress lines. Started at N0 in dependency order. Actual isolated
  entries/settings, document/review/publication/media and saved-input indexing
  remain compatible with their recorded checks; CodeGraph supplied current source.
- Reverified **87** N14/image/packaging/worker-boundary cases before changes. N14's
  actual complete-set publisher and workflow, together with recorded three-image
  build/smoke evidence, substantiate its local exit. There was no Azure deployment
  workflow/configuration, making **N15** the first incomplete task. Missing remote
  publication and physical Azure inputs do not prevent offline preparation.
- Initial Git status already contained uncommitted N0-N14/N9A/user work. Preserve
  every earlier file/checkpoint. N15 adds only its workflow/tool/tests/operator guide
  and scoped current docs/lint/ignore delta. No N16 work, runtime/dependency/image
  change, Akay.Be/other repository, database or migration is included.

### N15 changes and decisions

| Area | Implemented and locally verified boundary |
| --- | --- |
| Offline templates | Stdlib-only `tools/container_apps.py prepare` validates explicit three-worker configuration and a complete matching N14 release/run/attempt. Generates three independent one-resource ARM templates and a plan; no network, `az`, registry, credential lookup or secret resolution. Unknown/missing fields, queue/app/image/identity collisions, raw key values and missing references fail closed. |
| Image lineage | Require successful same-repository main/manual N14 workflow metadata, exact commit/run/attempt, complete three-repository release ID/tags/digests and configured repository matching. Workflow fetches exact named artifact and run-attempt metadata before Azure login. All images use repository@sha256, never latest. Local metadata fixtures are not remote attestations. |
| App composition | Separate command/image/queue, runtime UAMI/client ID, scaler and secret-reader identities, Key Vault secret inventories, GHCR pull credential, CPU/memory/workload profile, concurrency/replicas/queue scaler and grace per app. Document concurrency starts at 1. Match baked model/tokenizer paths and current startup settings. JSON environment literals are ARM-escaped. |
| No ingress/temp | Single-revision mode, ingress=null and no HTTP probes/scaler. UID 10001 comes from the existing images; EmptyDir mounts `/tmp` with `/tmp/akay` processing. Platform CPU-dependent ephemeral capacity is not N13's tmpfs quota; no unsupported sizeLimit/read-only-root field. Actual ACLs/grace/resources remain staging evidence. |
| Authorization | New manual-only `deploy-workers.yml`; main ref + authorize + cutover_confirmed, selected GitHub environment and exact environment enablement. Validate explicit OIDC fields/config before login. Only deployment job grants id-token:write/actions:read, no package writes. GHCR publication, Azure deployment OIDC and GHCR pull remain distinct authorities. |
| Delivery/recovery | One selected existing app per dispatch; global non-cancelling deployment concurrency. Azure CLI 2.81.0/API 2025-07-01; no extension or provisioning commands. Check existing app/environment/location and reject ingress/sidecars before applying. ARM validate, Incremental one-resource apply, acknowledged provisioning and exact returned desired-property checks. No success for missing/mismatched/unconfirmed state. |
| Credentials/evidence | Explicit dedicated OIDC CLI config, scrubbed CLI subprocess environment; no developer-default credential fallback. Recheck prepared template files before CLI use; do not overwrite prior success evidence. Upload only prepared reference JSON and selected acknowledged `applied-control-plane-only` record, never Azure config/downloaded logs. Failed postchecks can leave an applied app without a success record; inspect exact cloud operation before retrying. |
| Bootstrap/cutover | Require explicitly existing queues/apps/environment/identities/storage/secrets. Document owner-authorized bootstrap of missing media/index apps, preserving compatible converter configuration, paused routes/old mixed-consumer drain, separate receiver/scaler RBAC, per-role verification, mixed-release windows and previous-complete-release/full-config rollback. No .NET deployment, auto-rollback or state/receipt deletion. |

Official Microsoft Learn schema/scaling/storage documentation and code samples,
Context7 CLI documentation, exact Azure CLI **2.81.0** command/argument source,
azure/login **v2**, azure/cli **v2** mount/environment implementation and artifact
**v4** inputs were checked. The action mounts the explicit host Azure config at
`/root/.azure` and omits the host variable inside its container. No library pin,
model asset, runtime source or Dockerfile changed. References/configuration are in
[the deployment guide](content-processing-deployment.md).

### N15 exact checks and observed results

PowerShell in `C:\Develop\Akay\Akay.ConvertToMarkdown`. Regression opt-ins:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS='false'; $env:RUN_DOCLING_MODEL_TESTS='false'; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS='false'
```

| Exact command/check | Observed result |
| --- | --- |
| Opt-ins above + `.venv\Scripts\python.exe -m pytest tests/unit/test_ci_release.py tests/unit/test_images.py tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py -q --tb=short` | Prerequisite **87 passed in 30.49s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_deployments.py -q --tb=short` before implementation | **RED: 1 failed, 30 errors in 0.69s**, absent deployment tool/workflow. Initial implementation exposed/fixed one nested-dict syntax error; then **31 passed in 0.81s**. Initial actionlint also caught job-level runner context use; moved it to supported step env before final lint. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_deployments.py -k "apply_is_one_worker or cross_app or unmanaged" -q --tb=short` | **RED: 3 failed, 31 deselected in 0.26s**. Azure GET does not echo template apiVersion; cross-app scaler identity sharing was accepted; an existing sidecar was not rejected before mutation. Corrected comparisons/isolation/preflight; expanded settings/main-CLI tests passed in the following regression. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_deployments.py tests/unit/test_ci_release.py tests/unit/test_images.py tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q` with opt-ins above, intermediate | **125 focused passed in 29.34s**; **1023 passed, 18 skipped, 2 existing warnings in 67.46s** overall. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_deployments.py -k "token_limits or apply_is_one_worker" -q --tb=short` | **RED: 1 failed, 3 passed, 37 deselected in 0.28s**. Broad TOKEN substring incorrectly treated the existing non-secret AZURE_OPENAI_MAX_BATCH_TOKENS limit as a credential. Restrict secret-name matching to actual singular suffixes; preserve the configurable limit. All three selected-app apply cases already passed. |
| Same complete focused/full command above after the final fix | Final **128 focused passed in 28.00s**; **1026 passed, 18 skipped, 2 existing warnings in 62.94s** overall. All prior 985 passing cases plus **41 N15 cases** pass. |
| Actual CLI subprocess in `test_real_cli_prepares_offline_without_reading_ambient_credentials` | **PASS** in final suite: explicit synthetic config/release/run files -> three actual JSON templates/plan under pytest tmp path, scrubbed environment, no service/CLI availability needed; default apply refused and no applied record. |
| Actual CLI main + injected subprocess in `test_explicit_apply_cli_scrubs_credentials_and_records_only_selected_ack` | **PASS**: explicit dedicated login config, pinned CLI/version output override, one selected app's show/validate/create/show order, ambient secrets/proxy absent, only that app's acknowledged record; repeat evidence rejected before further CLI calls. Changed template rejected before any CLI access in separate test. |
| `docker --config ".local/n13/run-k6ns5x6y/docker-config" --host "npipe:////./pipe/dockerDesktopLinuxEngine" run --rm --network none --mount "type=bind,source=C:\Develop\Akay\Akay.ConvertToMarkdown\.github\workflows,target=/workflows,readonly" rhysd/actionlint:1.7.7@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9 /workflows/build-and-push.yml /workflows/deploy-workers.yml` | Final **PASS, exit 0**, no syntax/expression/action-input/ShellCheck diagnostics for either workflow. Existing local linter image/empty tool-owned Docker config; no login. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | **PASS:** no broken requirements; both pinned API/confidence/backend/reload/UUID PASS lines. |
| `git -c core.autocrlf=false diff --check`; per-file command below; `git check-ignore .local/n15/reviewed/deployment-plan.json`; `git status --short` | **PASS:** no tracked/new-file whitespace diagnostics across all nine task paths; generated-plan path ignored. Initial N0-N14/N9A/user working-tree paths remain present. No staging/commit. |

Exact additional new/untracked-file check (same nine paths listed under files):

```powershell
foreach ($path in @('.github/workflows/deploy-workers.yml', 'tools/container_apps.py', 'tests/unit/test_deployments.py', 'docs/content-processing-deployment.md', '.github/workflows/build-and-push.yml', '.gitignore', 'README.md', 'docs/content-processing-ci.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }
```

No Azure CLI container, ARM service validation, OIDC/login, GHCR pull/push or cloud
deployment was executed. Azure command responses are local doubles, not a live
control plane. N13/N14's actual builds/smoke remain historical compatible image
evidence; rebuilding unchanged images is not required for this deployment-only
task. Default omissions remain 13 model opt-ins, 2 quality diagnostics, disabled
Azure Blob, absent host FFmpeg and absent Speech settings. Both warnings remain
upstream OCR serialization deprecations. Prior OCR/layout limitations persist.

### N15 acceptance, files and next session

- New: `.github/workflows/deploy-workers.yml`, `tools/container_apps.py`,
  `tests/unit/test_deployments.py`, `docs/content-processing-deployment.md`.
- Scoped updates: `.github/workflows/build-and-push.yml` (add deployment workflow
  to the existing lint command only), `.gitignore` (only `/.local/n15/`), README,
  `docs/content-processing-ci.md` and this prepend-preserving progress record.
  All previous application/Docker/requirements/user changes remain untouched.
- Local N15 exit is met: validated explicit three-app generation, own routes/scaler/
  identities/secrets/resources/replicas, gated one-app delivery, no ingress and
  documented prerequisite/bootstrap/cutover/rollback responsibilities, with exact
  local tests and separately pending real staging/end-to-end status. There is no
  claim of three deployed apps or verified authorized production configuration.
- Pending external inputs/evidence: physical approved snapshots/queues/apps/env,
  OIDC/branch reviewers/RBAC, GHCR pull/Key Vault secrets/network access, complete
  remote N14 publication/artifact retention, actual pinned CLI container/ARM
  validation/application, UID/temp mounts, startup/readiness/model/tokenizer access,
  scale-from-zero, independent sizing/termination under load, staging service/
  callback/ordering and actual coordinated cutover/rollback. No ambient credentials
  were discovered or reused; no values were inferred from illustrative fixtures.
- **Next fresh session: N16 only**, reproducible local end-to-end verification,
  operator docs and .NET/manual-data handoff, disclosing all external gaps. N16 was
  not implemented here. Missing cloud authorization does not justify live calls.
- Rollback unit: the four new N15 files and five scoped existing-file deltas above.
  Reverting this preparation must retain N14 publication gates and all earlier
  checkpoints. There is no local cloud change to undo; a later actual rollout
  requires the separately authorized coordinated rollback described in the guide.

## N14 checkpoint — 2026-11-15 (preserved)

**N14: complete on its locally verified workflow-preparation boundary. N0-N13 and
N9A remain complete. Next fresh session: N15 only. Three image builds and every
normal offline smoke phase pass; GitHub-hosted execution, public asset fetching
and actual GHCR publication are NOT verified. Publication remains explicitly gated.
No release, image push, deployment or cloud resource is credited.**

### N14 prerequisite reconciliation and scope

- Read applicable parent/user instructions (no repository-local AGENTS), current
  README, complete authoritative specification/plan and all 2079 preserved progress
  lines. Started at N0 in dependency order and checked actual code with CodeGraph.
  Existing entry/settings/contracts, Docling/artifacts/reconstruction, media and
  saved-input indexing/ordering remain compatible with their recorded evidence.
- Reverified **64 N13/packaging/worker-boundary tests**, then all prior **962**
  passing cases in the final 985-case regression. Existing six runtime locks,
  model/tokenizer hashes, three target stages and N13 recorded build/smoke evidence
  substantiate N13. The actual workflow still published one mixed image on push
  and tagged a release before building; N14 was the first incomplete task.
- Initial Git status contained all uncommitted N0-N13/N9A/user work. Preserve that
  work, the legacy Dockerfile/runtime and every checkpoint below. Only N14's
  workflow/tools/tests/current docs/ignore delta is added. No N15 configuration,
  other repository/database, migration or application-service call is included.

### N14 changes and decisions

| Area | Implemented and locally verified boundary |
| --- | --- |
| CI sequence | PR/push/manual triggers. Read-only default and credential-free checkouts. Actionlint 1.7.7 + ShellCheck, Python 3.12.12, hashed Linux engine/build locks, pinned test tooling, pip check, default suite/N0 probe; images job depends on successful tests. |
| Image checks | Reuse unchanged N13 checker/Dockerfile/asset locks; pinned Buildx 0.38.1 with local Docker driver and explicit plugin copy. Build all three targets and run document startup/rebuild/models/inference plus media/index startup engines. All six normal offline phases must have successful exit/no OOM and actual measurements. |
| Public build assets | New stdlib-only acquisition tool uses existing exact HF snapshots, official RapidOCR v3.10.0 URLs and existing tokenizer URL. Explicit download opt-in, bounded temporary transfers, hash/size verification before rename, reuse valid files and reject corrupt cache bytes. No token/netrc/proxy/user-cache discovery. No new weights were downloaded locally. |
| Cache/evidence | Cache only public assets with exact OS/lock/tool key, no restore prefix; always verify. Build layers remain job-local. Upload only positive-listed smoke JSON/logs/commands and release JSON, with hidden paths enabled and 14-day retention; no model bundle, Docker login config or user home. |
| Publication gate | Login/push requires workflow_dispatch + publish=true + GHCR_PUBLICATION_ENABLED exactly true + main ref, after all smoke phases. GHCR_IMAGE_REPOSITORIES must explicitly map document/media/index to distinct lowercase authorized GHCR repositories. No physical names/defaults were invented. GITHUB_TOKEN is passed only to gated login with its dedicated runner-temp config; images job alone declares packages:write. |
| Release identity | Shared `sha-<full commit>-<run id>-<run attempt>` for all three images. Reruns receive a new identity; workflow ref concurrency never cancels an active publisher. Removed the racy semver allocator/pre-build Git tag and latest aliases; no Git release/tag is created. Registry-enforced tag immutability is not claimed: deployment must pin returned repository@sha256 references. |
| Tested-ID delivery | Inspect all three exact smoke-tested IDs before mutating, then tag/push those IDs without rebuilding. Require matching RepoDigests after each successful push. Journal confirmed partial progress; write complete release.json only after all three digests. A failed/partial/missing-image/unconfirmed-digest set or reused local attempt cannot produce release success. Default CLI validates without Docker, repositories or credentials. |
| Failure boundary | Registry pushes are not atomic. Earlier images can remain after a later failure, without a complete release record. Retain partial evidence and rerun the entire workflow under a new attempt; no automatic registry cleanup/deployment. Public source availability, hosted runner resources and GHCR permission/transport remain external checks. |

Official GitHub Actions/Context7 syntax, cache/artifact-v4 behavior, Buildx action
v3 inputs, Docker CLI **29.9.3** tag/push/inspect/RepoDigests, actionlint **1.7.7**
and the exact RapidOCR **v3.10.0** registry were checked. No library/runtime lock
or application source changed. References and operational details are in
[the CI guide](content-processing-ci.md).

### N14 exact checks and observed results

PowerShell in `C:\Develop\Akay\Akay.ConvertToMarkdown`. Regression opt-ins:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS='false'; $env:RUN_DOCLING_MODEL_TESTS='false'; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS='false'
```

| Exact command/check | Observed result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_images.py tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py -q --tb=short` | Prerequisite **64 passed in 58.36s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ci_release.py -q --tb=short` before implementation | **RED: 19 failed in 0.42s**: actual workflow missing test/build/gate behavior and absent release/asset modules. Initial implementation **19 passed in 0.32s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ci_release.py -k "existing_success or dry_run or unconfirmed" -q --tb=short` | **RED: 1 failed, 3 passed, 19 deselected in 0.32s**. Existing release.json was checked only at final write, allowing earlier Docker mutations; added a preflight refusal. All 23 N14 cases pass in the final focused suite. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ci_release.py tests/unit/test_images.py tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q` with opt-ins above | **87 focused passed in 45.29s**; **985 passed, 18 skipped, 2 existing warnings in 84.58s** overall. All 962 preceding cases plus 23 N14 cases pass. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ci_release.py -q --tb=short` after final cross-platform source-path assertion | Final **23 passed in 0.37s**. No production code changed after the full regression. |
| `docker --config ".local/n13/run-k6ns5x6y/docker-config" --host "npipe:////./pipe/dockerDesktopLinuxEngine" run --rm --network none --mount "type=bind,source=C:\Develop\Akay\Akay.ConvertToMarkdown\.github\workflows,target=/workflows,readonly" rhysd/actionlint:1.7.7@sha256:887a259a5a534f3c4f36cb02dca341673c6089431057242cdc931e9f133147e9 /workflows/build-and-push.yml` | **PASS, exit 0**, no syntax/expression/action-input/ShellCheck diagnostics, including final Buildx pin and lint step. Public linter image pulled once using the existing tool-owned empty config; no registry authentication. |
| `.venv\Scripts\python.exe tools/ci_assets.py --directory .local/n14/assets --list-sources` | **PASS**, exact 20 paths/public URLs/SHA-256 printed, no downloads. Acquisition/reuse/corruption/size/atomic cleanup behavior uses injected byte-stream fixtures in N14 tests. |
| `Test-Path -LiteralPath ".local"; .venv\Scripts\python.exe tools/ci_release.py --results .local/n13/run-esk4t07l/results.json --output .local/n14/local-verification --sha "$(git rev-parse HEAD)" --run-id 1 --attempt 1` | **PASS** on the real complete six-phase smoke evidence. Only ignored build-verification.json written; no registry, Docker mutation or release.json. Local run IDs are synthetic; dirty worktree build is not claimed as a published commit/release. |
| `.venv\Scripts\python.exe -m pip check; .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py; .venv\Scripts\python.exe tools/verify_assets.py --document-dir .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken` | **PASS:** no broken requirements; both N0 API/backend/confidence/reload/UUID lines; all 19 model hashes and official tokenizer hash. |
| `git -c core.autocrlf=false diff --check`; `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for each of the nine N14 paths below; `git check-ignore .local/n14/local-verification/build-verification.json`; `git status --short` | **PASS:** no tracked/new-file whitespace diagnostics, generated evidence ignored, full status preserves all original N0-N13/N9A/user paths. Reviewed tracked workflow/ignore deltas and final CodeGraph source/impact; nothing staged/committed. |

Actual all-target build/smoke command (same exact staged assets, with no forwarded
host credentials):

```powershell
.venv\Scripts\python.exe tools/check_images.py --docker-host "npipe:////./pipe/dockerDesktopLinuxEngine" --buildx-plugin "C:\Users\alvaro.caballero\.docker\cli-plugins\docker-buildx.exe" --document-models .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken
```

**PASS:** all three builds and all six offline phases, captured in
`.local/n13/run-esk4t07l/{results.json,commands.jsonl,*-*.log}`. Existing dependency
layers were reused where valid; wheel README metadata was rebuilt. Independent
actual installed compositions, no-model reconstruction, seven OCR selections,
two Spanish scans, four flag combinations, code/formula crop inference, real
FFmpeg/FFprobe/Deno/EJS and saved-transcript/tokenizer/local-Qdrant all pass.

| Target | Local image ID (not a GHCR publication digest) | Bytes |
| --- | --- | ---: |
| document | `sha256:4498fd1713e1780441cb85e17d2ee39386a05ea2674284e7dc2a2c0417f2a406` | 4647694076 |
| media | `sha256:0f6546d7972505feec3fe86bb9e17de2e02dafc8dcb9c7be07160e9dc8f1e529` | 1264186064 |
| index | `sha256:0ac7e469db2b77ca9584139ebc9c7b2e48fba667e900f1e83c487644f338ee4c` | 658554356 |

Document inference: **610.98s**, **1195.28 CPU s**, **3740824 KiB max RSS**,
**3066658816 bytes cgroup peak**, exit 0/no OOM under the same N13 limits.
Document startup/rebuild/models: **11.00/5.67/15.62s** inside the process; media/index
startup: **3.04/5.48s**. These are fixture measurements, not deployment sizing.
Synthetic formula classification remains false in Linux; actual crop inference
returns the same 120/15 characters. No strict diagnostic assertion, optical
quality requirement or production extraction output was changed to pass N14.

### N14 acceptance, files and next session

- New: `tools/ci_assets.py`, `tools/ci_release.py`, `tests/unit/test_ci_release.py`,
  `docs/content-processing-ci.md`.
- Scoped updates: `.github/workflows/build-and-push.yml`, `.gitignore` (only
  `/.local/n14/`), README, image guide and this prepend-preserving progress record.
  Application code, dependency/resource locks, Dockerfiles and N13 harness are
  unchanged by N14. Retain every pre-existing N0-N13/N9A/user working-tree path.
- Local acceptance met: test-before-build/publication, three actual builds/smoke,
  workflow syntax/shell validation, shared unique SHA identity, exact tested-ID
  publication logic/digests, no pre-build release race, explicit publication gate
  and bounded credential-free asset/cache/evidence inputs. Nothing staged/committed.
- Pending external evidence: remote GitHub Actions execution (including Linux
  host regression/install and runner disk/time), availability of exact public
  snapshot URLs, authorized physical GHCR repositories/package rights, actual
  token login/push/digest delivery and artifact/cache service behavior. Neither
  workflow preparation nor Docker mocks prove these; no Actions run was triggered.
- Default omissions remain 13 local-model opt-ins, 2 separate quality diagnostics,
  disabled Azure Blob, host FFmpeg absent and Speech configuration absent. Actual
  container model/tool checks above are separate evidence. Existing two default
  upstream OCR deprecations and inference rope/tied-weight warnings persist.
  Spanish accent errors and unmeasured eu/gl/ca/fr/en/de quality remain disclosed.
- **Next fresh session: N15 only**, prepare separately gated three-app deployment
  configuration. Physical app/queue/identity/OIDC/pull-auth/RBAC/scaler/resource
  inputs remain explicit; do not infer values or create resources. No N15 work,
  push, GHCR publication, credential discovery or deployment occurred here.
- Rollback unit: the four new N14 files and five scoped existing-file deltas above;
  preserve all previous checkpoints, locks, images and runtime functionality.
  Reverting must not accidentally restore the old automatic publisher on an
  unapproved push; keep publication disabled while reviewing that workflow change.

## N13 checkpoint — 2026-11-15 (preserved)

**N13: complete on its local image/integration boundary. N0-N12 and N9A remain
complete. Next fresh session: N14 only. Three Linux/amd64 builds, independent
non-root/offline runtimes and actual local engines are verified. Native Linux
formula-layout recognition in the existing synthetic PDF remains a separately
failing diagnostic; actual CodeFormulaV2 crop inference succeeds. No model/layout
repair, registry publication, application-service call or deployment is credited.**

### N13 prerequisite reconciliation and scope

- Read applicable user/parent instructions (no repository-local AGENTS), README,
  the full authoritative specification/plan and all 1954 preserved progress lines.
  Initial Git status already contained N0-N12/N9A/user modified/untracked work.
  Preserve every checkpoint and unrelated file; use CodeGraph before source reads.
- Starting at N0, actual dedicated compositions, strict artifacts/reconstruction,
  Docling adapter, local chunking/indexing and ordered coordinator match recorded
  checks. Reverified **82 packaging/worker-boundary/ordered-index tests** before
  N13. N12's six dependency locks and explicit model/tokenizer inputs exist and
  their hashes pass. The old single mixed Dockerfile had no isolated image targets
  or model staging; N13 is the first incomplete task, dependent on N12.
- Docker CLI was installed but its local Linux daemon was stopped. `docker desktop
  start` succeeded; actual engine is Docker Desktop 4.99.0 / Engine 29.9.3,
  linux/amd64, Buildx 0.38.1. Only explicit local npipe transport was used. An empty
  tool-owned Docker config hides the user-only Buildx install; copy only the
  explicitly supplied plugin executable, never ambient registry credentials.

### N13 changes and decisions

| Area | Implemented/verified boundary |
| --- | --- |
| Targets | New `Dockerfile.workers` with `document-converter`, `media-transcriber`, `content-indexer`; each installs one unchanged N12 hashed Linux lock and the same built wheel, with its own exec entry. Minimal common base; build-only hashed Hatchling lock. Original mixed Dockerfile/current CI preserved. |
| Reproducible inputs | Python 3.12.12/bookworm base and Dockerfile frontend pinned by observed digest; Debian 20261110T000000Z snapshot. CPU Torch/vision remain exact N12 URLs/hashes. This is input/behavior reproducibility, not a bit-identical cross-builder image claim. |
| Asset staging | Explicit existing bundle/tokenizer only. Verify before staging, copy only the 19 locked model files or one tokenizer, verify again in build and non-root smoke. Exact runtime inventory excludes unrelated assets/audits. Verified asset stage avoids copying model bytes again into a runtime chmod layer (initial document image was 6,570,844,090 bytes; final is about 4.65 GB). No model downloads/cache discovery. |
| Linux native gaps | Minimal base rendered the fixture title as a picture. Liberation/fontconfig restores the title. The fixture formula is still ordinary text in Linux layout output; preserve that finding, not a production fallback. Pinned Deno wheel executable was mode 0644; image chmod 0755 and actual build/non-root execution fix it. Document headless dependencies pass without FFmpeg/libGL installs. |
| Runtime limits | UID/GID 10001; no ports, read-only root, no capabilities, no-new-privileges. Smoke uses network none, socket traps, 2 CPUs, 4 GiB, 256 PIDs and UID-owned 1 GiB tmpfs. These are measured fixture limits, not approved app sizing. Actual deployments must supply the bounded writable mount. |
| Document checks | Both operations/export/Core reload; fresh-process reconstruction rejects extraction pipeline/model imports. Seven OCR resources individually initialize, then layout/accurate tables/code/formula initialize offline. Two real Spanish raster/overlay extractions plus four real native-PDF flag conversions retain returned structure/assets; real code/formula ground-truth crop inference proves the local enrichment engine independently of layout classification. |
| Media/index checks | Real FFmpeg/FFprobe audio-only WebM -> OGG; actual pinned Deno/EJS evaluation with no granted permissions. Real corrected saved transcript -> HybridChunker/local tokenizer -> persistent local Qdrant. Actual installed composition uses service doubles; distribution/import inventories exclude foreign engines. |
| Harness reliability | Explicit scratch directory survives environment scrubbing; otherwise read-only Linux containers lose TMPDIR. Capture smoke logs/commands/exit/OOM/resource evidence under ignored `.local/n13/`; reject incompatible phase/target combinations. Explicit UTF-8 subprocess decode and console encoding handle model progress glyphs on Windows. Remove only exact tool-owned containers. |

The strict native formula-classification assertion is retained as
`--smoke layout-diagnostic` and still **fails**. Original N3 integration/quality
tests and fixtures are unchanged. Normal image checks report `formulaDetected=false`
instead of claiming the full converter decoded that equation. Separately supplied
ground-truth fixture crops invoke the real initialized CodeFormulaV2 stage, not a
mock, injected production detection or altered extraction result. N13 checks image
integration/asset availability; it does not repair upstream OCR/layout. Spanish
accent limitations and unmeasured quality in each of eu/gl/ca/fr/en/de remain.

### N13 exact checks and observed results

PowerShell in `C:\Develop\Akay\Akay.ConvertToMarkdown`. Image commands below use
this exact reusable argument array (no environment/credentials forwarded):

```powershell
$N13 = @('tools/check_images.py', '--docker-host', 'npipe:////./pipe/dockerDesktopLinuxEngine', '--document-models', '.local/docling-n3/models', '--tokenizer-file', '.local/cl100k_base.tiktoken')
$Buildx = @('--buildx-plugin', 'C:\Users\alvaro.caballero\.docker\cli-plugins\docker-buildx.exe')
```

| Exact command/check | Actual result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py tests/unit/test_ordered_indexing.py -q --tb=short` | Prerequisite **82 passed in 40.79s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_images.py -q --tb=short` before implementation | **RED: 6 failed in 0.43s**: missing image targets/checker and absent exact-input/credential boundaries. Initial GREEN: **6 passed in 0.20s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_images.py -k foreign_smoke -q --tb=short` | **RED: 2 failed, 6 deselected in 0.39s** before rejecting unsupported image/phase selections; fixed in the final focused regression. |
| `Test-Path -LiteralPath "requirements"` then clean-environment `uv pip compile requirements/image-build.in --generate-hashes --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --default-index https://pypi.org/simple --output-file requirements/image-build-linux.txt --no-config` | **PASS:** five build-only dependencies resolved/hashed; actual uv 0.11.16. Runtime locks unchanged. |
| `.venv\Scripts\python.exe @N13 @Buildx --target document --smoke startup` and same for media/index | Three initial builds succeeded. Initial image smoke exposed scrubbed TMPDIR (document/index) and Deno 0644 (media), not accepted as successful smoke. Buildx discovery initially failed before any build until explicit plugin handling. Fixed and repeated. |
| `.venv\Scripts\python.exe @N13 @Buildx --target document --smoke inference` | Fonts restored the missing title; native formula classification still failed. Record separate diagnostic and check actual crop enrichment without changing application output. Earlier media harness needed a fixture queue and `Object.assign(globalThis, lib)` when combining EJS; neither changes production code. |
| `.venv\Scripts\python.exe @N13 --target document --skip-build --smoke inference` | **PASS**, `.local/n13/run-jcs0ftru/results.json`: 2 Spanish scans, all 4 native flag conversions, table/code/figure/reference reload, plus actual code/formula crop inference. **505.56 s**, **984.03 CPU s**, **3,678,504 KiB max RSS**, **2,908,274,688 bytes cgroup peak**, no OOM. Four native calls: **6.35/121.10/6.19/117.02 s**; all report formulaDetected=false. Crop outputs 120/15 characters. |
| `.venv\Scripts\python.exe @N13 @Buildx --smoke startup` after final README/wheel metadata update | **All three builds and smoke checks PASS**, `.local/n13/run-k6ns5x6y/{results.json,*-startup.log,commands.jsonl}`. Final image IDs/sizes below; installed distributions and imports printed. Same production source, runtime locks and model assets as the inference run; only wheel README metadata changed, so expensive inference was not repeated. |
| `.venv\Scripts\python.exe @N13 --target document --skip-build --smoke rebuild` | **PASS**, `.local/n13/run-v07ne6th`: fresh-process no-model rebuild **6.11 s**, max RSS **480,288 KiB**, cgroup peak **389,361,664 bytes**, exit 0/no OOM. |
| `.venv\Scripts\python.exe @N13 --target document --skip-build --smoke models` | Final **PASS**, `.local/n13/run-fj5tgfg9`: seven OCR selections + full PDF/enrichment initialization **11.36 s**, max RSS **1,106,364 KiB**, cgroup peak **848,756,736 bytes**, exit 0/no OOM. Intermediate captured-log attempts failed on Windows decode/console encoding despite completed container work; final UTF-8 fix verified below. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_images.py -k utf8 -q --tb=short` before UTF-8 fix | **RED: 1 failed, 8 deselected in 0.76s**, real child UTF-8 output under mocked cp1252 locale raises UnicodeDecodeError. Explicit subprocess UTF-8 fixes it; console reconfiguration also fixes actual model smoke output. |
| `.venv\Scripts\python.exe @N13 --target document --skip-build --smoke layout-diagnostic` | **Known failing diagnostic**, `.local/n13/run-fvnxsomi`: exit 1/no OOM, `Native fixture formula was not classified as a formula on Linux.` Both preceding Spanish scans pass. Not an image load/download failure and not reported as GREEN/xfail. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_images.py tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py -q --tb=short` | Final **64 passed in 40.55s**, all **9 N13 tests** included. Earlier 61-case run passed; an earlier packaging-only 60s harness timeout is not a completed result. |
| Explicit false Azure/model/quality opt-ins plus `.venv\Scripts\python.exe -m pytest -q` | **961 passed, 18 skipped, 2 existing warnings in 135.51s** before adding the UTF-8 regression. The later focused 64-case run includes that new passing ninth N13 case. |
| Same full regression command after the final UTF-8/console fixes and documentation | Final **962 passed, 18 skipped, 2 existing warnings in 91.11s**. All 953 prior cases plus 9 N13 cases pass. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py && .venv\Scripts\python.exe tools/verify_assets.py --document-dir .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken` | **PASS:** no broken requirements, both N0 API/UUID/backend/reload lines, all 19 resource hashes and official tokenizer hash. |
| `docker --config ".local/n13/run-k6ns5x6y/docker-config" --host "npipe:////./pipe/dockerDesktopLinuxEngine" buildx build --check --platform linux/amd64 --file Dockerfile.workers --target document-converter --build-context "document_assets=.local/n13/run-k6ns5x6y/document" .` | **PASS**, check complete with no warnings. Actual three-target builds independently validate stages. |
| `git -c core.autocrlf=false diff --check`; `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for each of the 13 N13 paths listed below; `git check-ignore .local/n13/run-k6ns5x6y/results.json`; `git status --short` | **PASS:** no tracked/new-file whitespace diagnostics, generated evidence ignored, initial user/N0-N12/N9A working-tree paths preserved. Final CodeGraph review confirms the scoped checker helpers and their tests; nothing staged or committed. |

Final measured images (`docker image inspect .Size`, uncompressed bytes):

| Local tag | Image ID | Bytes | Startup wall / max RSS / cgroup peak |
| --- | --- | ---: | --- |
| `akay-n13-document:local` | `sha256:be00a0e6e2eee91abd191e50c323594d0dfbb612725ee5bf432e5109d0a814f5` | 4647693910 | 8.80 s / 566924 KiB / 470241280 bytes |
| `akay-n13-media:local` | `sha256:f08c29439ce71f615a58abba7bde56ded8a52350319a534ff6b4bc8c313d369d` | 1264185849 | 2.99 s / 95104 KiB / 108654592 bytes |
| `akay-n13-index:local` | `sha256:41d68a99b0c88e826da1e52a323bc576887b7b24f00703776c2c678df1685729` | 658554112 | 7.87 s / 438528 KiB / 417292288 bytes |

Linux RSS/cgroup counters are distinct measurements, not interchangeable capacity
estimates. All successful containers exited 0 without OOM. No production CPU/RAM
choice follows from these small fixtures. Public Docker/Context7 and pinned
Docling/Deno source/API/CLI checks support the implementation; see the image guide.

### N13 files, acceptance and next session

- New: `Dockerfile.workers`, `.dockerignore`,
  `requirements/image-build.in`, `requirements/image-build-linux.txt`,
  `tools/check_images.py`, `tools/container_smoke.py`, `tests/unit/test_images.py`,
  `docs/content-processing-images.md`.
- Scoped updates: `tools/target_probe.py` (optional scratch-directory argument and
  retaining that directory's TMPDIR), `.gitignore` (only `/.local/n13/`), README,
  packaging guide and this prepend-preserving record. Application source/runtime
  dependencies, authoritative specification/plan, N3 fixture/assertions, original
  mixed Dockerfile, workflows and prior user work remain intact.
- Local N13 acceptance: three built images, actual independent installed engines,
  non-root/no-ingress/read-only/bounded-temp smoke, exact assets and seven OCR
  selections, actual Spanish extraction, both document operations, enabled local
  code/formula inference, FFmpeg/FFprobe/Deno/EJS and tokenizer/local Qdrant.
- Pending/nonclaims: known strict Linux formula-layout diagnostic and Spanish
  accent fidelity, per-language OCR quality eu/gl/ca/fr/en/de, production resource
  sizing/termination under load, authorized live services, server Qdrant/Azure
  transport, actual CI/publication/deployment and .NET integration. Default 18
  omissions remain 13 model opt-ins, 2 quality diagnostics, Azure Blob disabled,
  host FFmpeg absent and missing Speech settings; container checks are separate
  evidence, not claims that the skipped host tests ran. Two warnings are existing
  upstream OCR-option deprecations; model checks also report upstream rope/tied weights.
- **Next fresh session: N14 only**, test/build/gated GHCR workflow preparation.
  No N14 or N15 implementation, push, publication, resource creation or deployment
  occurred. No application-service credentials were discovered/reused; no other
  repository/database/migration was touched. Nothing staged or committed.
- Rollback unit: the eight new N13 files and the five scoped updates above; remove
  only the N13 deltas and retain all preceding checkpoints/work. Local test tags,
  caches/staged `.local/n13/` evidence are technical build outputs, not published
  consumer artifacts. No broad cleanup/prune operation is part of this task.

## N12 checkpoint — 2026-11-14 (preserved)

**N12: complete on its locally verified packaging boundary. N0-N11 and N9A
remain complete. Next fresh session: N13 only. Clean Windows target installations
and offline asset/model loading pass; Linux locks are resolved, not runtime/image
verified. No image build/publication, cloud call or deployment is credited here.**

### N12 prerequisite reconciliation

- Read applicable user/parent instructions (no repository-local AGENTS), current
  README, full authoritative specification/plan and every preserved checkpoint,
  including N0's compatibility map. Initial git status already contained the
  uncommitted N0-N11/N9A/user work. Preserve that work and all prior evidence below.
- Started at N0 in dependency order. Actual Docling adapter, dedicated compositions,
  strict artifacts/review reconstruction and durable ordered index coordinator
  agree with their recorded verification. Reverified **65 worker-boundary/N11
  tests** before implementation. Earlier extraction/media/chunking/contract
  acceptance is supported by preserved checks and the final full regression.
- N12 was absent: all installations inherited the broad Docling/MarkItDown base;
  no target/transitive/resource locks or actual clean installation evidence existed.
  Execute only N12. Missing physical queues, Azure/OpenAI/Qdrant configuration and
  image identities are later external inputs, not packaging blockers.

### N12 changes and decisions

| Area | Implemented and verified boundary |
| --- | --- |
| Dependency ownership | Base is the six existing technical client/settings requirements. `document` selects granular slim document/PDF/local-model/ONNX-OCR extras, `media` pins yt-dlp/EJS/Deno, `index` selects Core's OpenAI chunking extra and existing adapters. Retain `youtube`, `test`, all scripts and legacy mixed behavior. Development now explicitly installs the worker locks before test tooling. |
| Compatibility | Preserve slim 2.141.0/Core 2.99.0/parser 7.26.0/RapidOCR 3.10.0/ONNX 1.20.1 and the measured numerical/model stack. Pin existing Torch 2.15.0, vision 0.29.2, Transformers 5.23.0, IBM models 4.0.4 and Hatchling 1.30.1. No engine upgrade/downgrade or parser replacement. |
| Hidden packaging gaps | Artifact exporters must read `version("docling-slim")`, not the optional metapackage. Clean index startup revealed Core 2.99's unconditional `huggingface_hub` import; add its tested 1.33.0 pin without Transformers/Torch. Both findings have observed failing evidence before their corrections. |
| Resolved locks | Six hashed runtime locks for Python 3.12/x86_64 Windows and Linux glibc >=2.28. CPU Torch/vision use official exact wheel URLs/hashes. Compiler checks resolved version/hash before URL binding; uv's backend-specific index was absent from generated requirements. No CUDA/NVIDIA/Triton/Whisper/ASR/description extras. Recompilation is byte-identical. |
| Resources | Promote the existing audited 19-file N3 bundle to a portable committed model lock with snapshot identities, sizes/hashes and seven language mappings. Three OCR files are shared, not seven copies. Separate N10 tokenizer lock. Explicit offline verifier rejects changed/missing/escaping files; no cache discovery, source paths, copying or remote model resolution. |
| Removal | Delete unused MarkItDown adapter and its 13 adapter-only tests; preserve actual Docling format/failure/cancellation/concurrent/runtime coverage. Update two stale strategy docstrings. Primary venv may still contain historical distributions; isolation evidence comes from the new clean venvs, not uninstallation from that shared environment. |
| Installation evidence | One built wheel installed into three initially clean, non-system-site-package venvs; exact target locks, pip check, real composition with service doubles and printed distribution/import roots. Real document convert/rebuild/Core reload and CPU Torch; actual saved-transcript chunking/local tokenizer/persistent local Qdrant without Torch/Transformers; media without Docling/Core/Qdrant. |
| Model loading | In the isolated slim install, all seven actual RapidOCR selections preserve their native code and load existing resources offline. Full StandardPdfPipeline initializes layout/accurate tables and both code/formula flags from the same bundle. CodeFormulaV2's internal VLM infrastructure is required for those approved flags, not picture description. This checks loading, not new OCR/inference quality. |
| Container compatibility | Existing Dockerfile installs the document/media Linux lock union so its retained mixed command remains compatible with the new minimal base. It remains one image with FFmpeg, without new model staging. Three images/build/sizes/non-root smoke checks are N13; CI remains N14. |

All tool processes use scrubbed environments, empty homes and explicit public
package indexes. Probes block service/model-download sockets and mock Azure
credential/client/consumer boundaries; no ambient credentials were inspected.
Public package wheels were downloaded for installation, not application services
or additional Hugging Face weights. Existing explicit bundle/tokenizer bytes were
reused unchanged. No other repository/database, migration, push, commit, registry
publication, resource creation or deployment occurred.

### N12 exact checks and observed results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Full regressions use:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact command/check | Observed result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_boundaries.py tests/unit/test_ordered_indexing.py -q --tb=short` | Prerequisite **65 passed in 26.53s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_packaging.py -q --tb=short` before production changes | **RED: 11 failed in 10.75s**. Nine correctly expose missing ownership/removal/locks; two engine cases initially had incorrect fixture imports. Corrected only that harness, then the engine-only command below failed on the actual version lookup. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_packaging.py -k artifact_engine -q --tb=short` before exporter changes | **RED: 2 failed, 9 deselected in 13.46s**. Without the metapackage's distribution metadata, both actual artifact paths failed. After using slim metadata: original N12 suite **11 passed in 13.15s**. |
| `Test-Path -LiteralPath ".local"`; `Test-Path -LiteralPath "requirements"`; `.venv\Scripts\python.exe tools/lock_dependencies.py` | Six locks successfully resolved with actual uv **0.11.16**. Subsequent CPU URL binding is included in the final regenerated locks. |
| `.venv\Scripts\python.exe tools/lock_dependencies.py --check` | **Six PASS lines**, byte-identical regeneration of every final lock, including CPU URL/hash binding and the index hub dependency. |
| `.venv\Scripts\python.exe tools/check_installations.py --tokenizer-file .local/cl100k_base.tiktoken --label locked` and same command with `--resume` | Wheel build and hashed document install succeeded after resuming the tool-timeout-interrupted clean venv. Earlier uv installs failed with Windows cache rename `Access denied`; pip avoids that failure. Initial pip attempt also proved uv's generated CPU pins needed explicit wheel URLs; verified filenames/hashes against official index before binding. First direct URL guesses (unencoded path/incorrect vision wheel tag) and uv source fragments were rejected, never accepted as installation evidence. Final locks use the exact `download-r2` links. |
| `.venv\Scripts\python.exe tools/check_installations.py --tokenizer-file .local/cl100k_base.tiktoken --label locked --target media --target index` | Media wheel/hash install and pip check passed. Probe initially exposed a Deno harness type assumption (`find_deno_bin` returns str), then standalone probe passed after `Path(...)`. Index was subsequently installed separately below. |
| Same installation command with `--target index`, then `tools/target_probe.py index` through that tool | **RED actual clean startup:** `ModuleNotFoundError: huggingface_hub` in Core's optional tokenizer module. Official v2.99 source confirms it. Added explicit hub pin and regenerated both index locks. |
| `.venv\Scripts\python.exe tools/check_installations.py --tokenizer-file .local/cl100k_base.tiktoken --label locked --target index --resume` | **PASS:** hashed final index install, wheel, pip check, configured actual composition, real local tokenizer/HybridChunker and persistent local Qdrant. Missing adapter config still exits 2 before credentials. |
| `.local\n12\document-locked\Scripts\python.exe -I tools/target_probe.py document --tokenizer-file .local/cl100k_base.tiktoken --document-models .local/docling-n3/models` | **PASS:** installed convert/rebuild/Core reload, CPU Torch, seven actual OCR initializations and full layout/accurate-table/code/formula pipeline initialization, sockets blocked. Upstream rope/tied-weight warnings only; no weight download. Earlier harness-only failures blocked asyncio's Windows socketpair or removed its required empty home; corrected without allowing application connections/ambient homes. |
| `.local\n12\media-locked\Scripts\python.exe -I tools/target_probe.py media --tokenizer-file .local/cl100k_base.tiktoken` | **PASS:** actual media startup with doubles and installed yt-dlp/EJS/Deno; printed inventory has no Docling/Core/Torch/Qdrant. No FFmpeg decoding/Speech/YouTube call. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_packaging.py tests/unit/test_worker_boundaries.py tests/unit/test_reviewed_content.py tests/unit/test_docling_conversion.py tests/unit/test_content_chunking.py tests/unit/test_ordered_indexing.py -q --tb=short` | **227 passed, 2 existing warnings in 90.80s**, including all **17 N12 cases** and prior seams. |
| Opt-ins above plus `.venv\Scripts\python.exe -m pytest -q` | Final **953 passed, 18 skipped, 2 existing warnings in 82.09s**. Accounting: prior 949 minus 13 retired MarkItDown-only cases plus 17 N12 cases. Earlier intermediate run with 11 N12 cases: 947 passed/18 skipped; an earlier 180s harness timeout was not a completed suite. |
| `.local\n12\document-locked\Scripts\python.exe -m pip check && .local\n12\media-locked\Scripts\python.exe -m pip check && .local\n12\index-locked\Scripts\python.exe -m pip check && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py && .venv\Scripts\python.exe tools/verify_assets.py --document-dir .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken` | **PASS:** four no-broken-requirements messages, both N0 API/UUID/reload probe lines, all 19 model-file hashes and official tokenizer hash. |
| `git -c core.autocrlf=false diff --check`; `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for all N12 new/untracked task paths; `git check-ignore .local/n12/document-locked`; `git status --short --untracked-files=all` / `git status --short` | **PASS:** no whitespace diagnostics; generated install/cache evidence ignored; reviewed scoped tracked diffs and full status, preserving the original N0-N11/N9A/user tree. Nothing staged or committed. |

Default omissions remain unchanged: 13 model integration opt-ins, two separate
Spanish optical-quality diagnostics, Azure Blob disabled, absent FFmpeg/FFprobe
and absent Speech settings. The two default warnings are upstream OCR-option
serialization. Resource/model initialization in this task is separate evidence,
not a claim that skipped inference/quality tests ran. Spanish accent limitations
and unmeasured quality in each of eu/gl/ca/fr/en/de remain unchanged.

### N12 files, acceptance and next session

- New: `requirements/{compatibility.txt,cpu-wheels.json,document-models.json,index-tokenizer.json}`;
  six `{document,media,index}-{windows,linux}.txt` locks;
  `tools/{lock_dependencies,check_installations,target_probe,verify_assets}.py`;
  `tests/unit/test_packaging.py`; `docs/content-processing-packaging.md`.
- Scoped updates: `pyproject.toml`, `.gitignore` (only `/.local/n12/`), Dockerfile,
  README, Docling/indexing/ordering/chunking/reviewed-content guides and this
  prepend-preserving record (only current packaging/handoff references);
  `conversion/{document_artifacts,markdown_rebuild}.py` version lookups and
  `models/content_type.py` / `processing/document_processor.py` docstrings.
  Remove `conversion/markitdown_converter.py` and `tests/unit/test_conversion.py`.
  Paths in the latter rows are under `src/akay_convert_to_markdown/` unless tests.
- Local acceptance met: minimal base/three dependency targets, resolved CPU locks,
  controlled resource inventory, clean installed distribution/import separation,
  startup/config isolation, both document operations and actual local index engine.
  No known failing N12 acceptance check remains. Linux execution is explicitly N13.
- Pending: **N13 only** in the next fresh session — three non-root images, exact
  asset staging/prefetch, Linux model/Spanish OCR/enrichment/reconstruction and
  tokenizer/media-tool smoke tests, process behavior, sizes and resource evidence.
  Preserve actual recorded N3 quality limits; do not reopen OCR repair. Physical
  deployment names/credentials and real application-service verification remain
  N14-N16/external inputs and were not inferred for packaging.
- Rollback boundary: remove the new N12 tools/locks/test/guide and reverse only
  the listed packaging/version/docstring/removal delta, restoring the unused
  adapter/tests together if reversing its removal. Preserve all N0-N11/N9A/user
  files and every checkpoint. Ignored `.local/n12/` contains only generated
  installation/cache evidence; it is not a consumer artifact or deployment.

## N11 checkpoint — 2026-11-14 (preserved)

**N11: complete on its locally verified ordered-delivery boundary. N0-N10 and
N9A remain complete. Next fresh session: N12 only. Live Azure/Qdrant-server
integration, production routing and deployment are not verified. An uncertain
in-flight Qdrant mutation deliberately blocks takeover pending explicit recovery.**

### N11 prerequisite reconciliation

- Read applicable parent/user instructions (no repository-local AGENTS), current
  README, the complete specification/plan, all 1740 lines of prior progress and
  N0's compatibility/frozen decisions. Inspected initial git status and used
  CodeGraph before source exploration. Initial tree already contained uncommitted
  N0-N10/N9A implementation and user documentation; preserved that work/history.
- Starting at N0, actual entry/settings boundaries, strict request/admission/event
  contracts, artifact publication/media/review preparation and N9/N10 APIs agree
  with recorded checks. Reverified **269 tests** covering N10/contracts/N9A and
  subsequently both N0 probes. N11 was absent: the index entry still exited 2 and
  N10 explicitly required external serialization. No earlier task was restarted.
- N10's selected provider/model/tokenizer prerequisite is resolved. Missing Azure
  resource/deployment/authentication and physical cloud targets remain external
  configuration, not blockers to local N11 tests. No such values were inferred.

### N11 implemented behavior and decisions

| Area | Implemented and locally verified boundary |
| --- | --- |
| Admission | Separate conditional/leased receipt for exact target/scope/content, independent of profile. Reuse N2's full canonical snapshots/history and admit/resume/replay/superseded/conflict decisions; additionally reject request-ID reuse across contents in the same target. Persist admission before effects. |
| Shared coordination | Explicit controlled Blob state container/prefix; no provisioning or database. Target-wide finite leased lane serializes metadata/profile registration and delivery, including callbacks. Content state has its own lease/ETag. 60-second leases, 20-second heartbeat and guards. This conservative lane favors safety over parallel throughput. |
| Mutation safety | A lease check alone cannot fence Qdrant. Persist a unique pending intent before dispatch; make one mutation attempt; require wait=True/strong ordering and COMPLETED; cache its result and immutable settled acknowledgement. A successor cannot advance without that acknowledgement, even after lease expiry. Known throttling/configuration rejection remains transient; ordinary explicit permanent rejection yields a safe failed event. |
| Uncertainty/recovery | Timed-out/lost/unconfirmed writes or process death before acknowledgement leave a fail-closed barrier. No automatic unsafe replay/takeover, final failure or successful delete is claimed for that uncertainty. Known in-flight cancellation drains before release. No-dispatch receipt loss is acknowledged safely; final receipt failure reuses confirmed commands. Unblocking after a hard crash requires explicit operator authorization and proof of writer/request quiescence; no admin unblocking tool is implemented. |
| Frozen preparation | Reuse N10 unchanged through a journaled store and embedding proxy. Freeze saved input/review in owned technical storage; persist validated embedding batches keyed by exact contextual text/space. Partial resume and final-receipt/callback recovery do not repeat confirmed embeddings. Completed receipt replay needs no source or point mutations. Technical records are private and retained; no sweeper/public artifact added. |
| Profiles/destinations | Bind full used profile/space snapshots in target state and retain per-content profile destinations, including interrupted/failed indexing. Reject same-ID collection/space changes; retired destinations remain explicitly deletable. Preserve N10 collection compatibility checks. |
| Delete/reassignment | Authorize exact configured/used profile+collection; delete only exact scope/content/profile filter, waiting for completion. Absent sets/collections succeed without embeddings or collection creation. Higher-sequence reassignment reuses artifacts, replaces deterministic IDs and prunes tails. Other scopes/contents/profiles and all Blob artifacts survive. Cross-profile stale work is superseded. |
| Results | Freeze completed/permanent-preparation-failure events before callback; reuse identical payload/key, persist notification and let the shared N8 consumer settle only after successful delivery. Superseded jobs return the current sequence, never an old success. HTTP/notification-receipt uncertainty can repeat delivery; receiver deduplication/current-sequence checks remain required. |
| Runtime | Strict dedicated index parser/invalid-index recovery; bounded declared/actual artifact reads from the configured source container. Explicit runtime profile/tokenizer/Azure/Qdrant/state configuration activates the existing index queue command. Missing adapter config exits 2 before credentials/consumption. CLI uses explicit Azure apiKey mode; programmatic Entra needs an explicit async token provider. Qdrant REST disables compatibility startup probes and environment proxy trust. Other workers keep their settings/import/legacy boundaries. |

The acknowledgement barrier is an availability tradeoff, not a cross-service
transaction: a server-applied write followed by death before its acknowledgement
can require manual recovery. A hard-crashed or ambiguous writer cannot be proven
quiescent by waiting for its Blob lease to expire. Direct N10/other writers must
not bypass the lane on a live target. Partial point batches are not an atomic
domain publication; the consumer still controls availability/approval/filtering.

### N11 exact checks and observed results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Regression runs use:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact command/check | Observed result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_indexing.py tests/unit/test_content_contracts.py tests/unit/test_reviewed_content.py -q --tb=short` before implementation | **269 passed in 62.44s**. Prior full-suite N10 result below remains historical, not a fresh full baseline. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py -q --tb=short` before production implementation | **RED: 9 missing-module setup errors in 12.68s**. Initial implementation: **3 failed, 6 passed in 85.28s**; mutation interception incorrectly depended on a wrapped method's __name__. Identify operations by client method identity instead. The other failure was a fixture reusing its fixed request ID for migration. Then **9 passed in 17.33s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py -k "processor or runtime_configuration" -q --tb=short` before runtime implementation | **RED: 2 failed, 12 deselected in 25.47s**, absent processor/settings. The preceding expanded run had 12 passing coordinator tests and a harness import-name error, corrected before this recorded RED. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py tests/unit/test_content_indexing.py tests/unit/test_consumer.py tests/unit/test_worker_boundaries.py -q --tb=short` | **145 passed in 54.76s** after runtime implementation, preserving startup/import, N10 and settlement behavior. |
| Same N11-only command after profile/partial-batch edge checks | **RED: 2 failed, 16 passed in 24.37s**. Real gap: a used profile ID could move to a new collection because prior immutability was collection-local. Added target-wide full profile/space bindings. Partial-batch test incorrectly expected repeated identical text to acquire redundant vectors; corrected that expectation and made the other-content fixture actually match its contentKey. |
| Same N11-only command plus full suite, intermediate | **23 passed in 25.61s**; **945 passed, 18 skipped, 2 existing warnings in 101.14s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py -k "request_id_cannot or lost_pending" -q --tb=short` | **RED: 2 failed, 23 deselected in 21.85s**. Cross-content request-ID reuse was not rejected; pending-receipt response loss before dispatch left an unnecessary uncertain barrier. Added target-wide identity snapshots and settled/no-dispatch acknowledgement. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py -k "explicit_qdrant_rejections" -q --tb=short` | **RED: 2 failed, 25 deselected in 19.79s**. Pinned client's special ResourceExhaustedResponse was treated as ambiguous; HTTP 400 rejection remained transient. Record settled rejection and preserve safe transient/permanent classification. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_ordered_indexing.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q` (final, opt-ins above) | **27 passed in 23.53s**; **949 passed, 18 skipped, 2 existing warnings in 96.26s** overall. All prior 922 passing cases plus 27 N11 cases pass. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | **Passed**: no broken requirements and both pinned API/confidence/backend/referenced-picture/Core reload/frozen UUID PASS lines. |
| `git -c core.autocrlf=false diff --check`; `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for each of the 13 N11 files listed below; `git status --short --untracked-files=all`; targeted shared-settings/consumer/storage diff inspection | **Passed**, no tracked/new-file whitespace diagnostics. Reviewed the complete status and scoped shared-seam changes against the initial user/N0-N10/N9A working tree. Nothing staged or committed. |

API evidence: Context7 exact Qdrant **1.19.1**, its official versioned async source,
installed mutation signatures and single-send REST/throttling implementation;
Microsoft Learn lease/concurrency guidance and actual Blob **12.24.1** async
upload/acquire/renew signatures. No dependency installation or pin change. Links
and the explicit operational recovery procedure are in the
[ordering guide](content-processing-ordering.md).

### N11 files, acceptance and next session

- New: `src/akay_convert_to_markdown/indexing/ordered.py`,
  `src/akay_convert_to_markdown/processing/index_processor.py`,
  `tests/unit/test_ordered_indexing.py`, `docs/content-processing-ordering.md`.
- Scoped updates: `indexing/profiles.py`, `config/indexing_settings.py`,
  `config/settings.py` (current-settings docstring), `index_main.py`,
  `storage/blob_storage.py`, `messaging/service_bus_consumer.py` under the package;
  README, `docs/content-processing-indexing.md` and this prepend-preserving record.
  N10 point preparation/chunking/embedding code and dependency pins are unchanged.
- Local acceptance verified: out-of-order/duplicate/conflicting operations,
  profile migration/retirement, exact repeated delete, reassignment, callback/final
  receipt failure (before and after commit), partial batches with frozen inputs,
  lease takeover during a delayed writer, cancellation drain, uncertain transport,
  definite throttling/rejection, actual consumer settlement/invalid index recovery,
  bounded artifact reads and explicit entry composition. Persistent local Qdrant
  reopens successfully; independent coordinator objects reuse the same technical
  state double. No local N11 acceptance failure or skipped N11 test remains.
- Pending: authorized Azure lease/ETag/expiry/replica interoperability, Qdrant-server
  transport/strong-order/replication/index acceleration, production routing and
  settings/RBAC/quotas, operational authorization to repair any genuinely uncertain
  lane, isolated dependency/image and later CI/deployment checks. Local doubles do
  not establish those external properties. Same 18 skips: 13 model opt-ins, two
  separate optical-quality diagnostics, disabled Azure Blob, absent FFmpeg/FFprobe
  and absent Speech settings. Two warnings remain upstream OCR serialization.
- **Next fresh session: N12 only**, isolated dependency sets/packaging, reusing
  completed N0-N11/N9A. Docker/CI changes were not required or performed by N11.
- Rollback unit: the four new files and nine scoped existing-file updates above.
  Stop index admission before reverting to the old fail-closed bootstrap; retain
  technical receipts/barriers for recovery rather than deleting them. Preserve all
  pre-existing user/N0-N10/N9A work. No other repository/database, migration, live
  application call, credential discovery, package/model download, commit, push,
  image publication, cloud resource creation or deployment occurred.

## N10 checkpoint — 2026-11-14 (preserved)

**N10: complete on its local adapter/point-set boundary. Approved selection:
AzureOpenAI / text-embedding-3-small / 1536 / cl100k_base. No Azure OpenAI resource
or embedding deployment exists; production integration is NOT verified. N0-N9 and
N9A remain complete. Next fresh session: N11 only.**

### N10 prerequisite reconciliation and approved decision

- The previous continuation below identified N10 as the first incomplete task
  after checking applicable instructions, current README, complete specification,
  plan/progress, N0 baseline, git status and actual CodeGraph/source seams. It
  reverified **139 prerequisite tests in 54.40s** and both N0 probe PASS lines.
  The prior N9A record includes **859 passed, 18 skipped** overall; that is
  historical baseline evidence, not a new baseline run in this continuation.
- The user explicitly approved AzureOpenAI, text-embedding-3-small, 1536 dimensions
  and cl100k_base, resolving the selected-model blocker. Endpoint, deployment and
  authentication must be configurable/valid for real calls; none was invented.
  No model revision, profile ID, distance, chunk budget, collection name, quota or
  production target was selected from the illustrative specification values.
- Reused actual N9 chunking, N9A final-artifact/transcript fixtures, existing
  finite/strict contracts, completion event builder, cancellation drain and pinned
  HTTPX. No earlier feature was restarted. Retained all pre-existing uncommitted
  implementation/user documents and every earlier checkpoint.

### N10 implementation and boundaries

| Area | Implemented and locally verified behavior |
| --- | --- |
| Azure adapter | Explicit HTTPS origin, deployment and apiKey/entra mode; no .env, credential discovery, DefaultAzureCredential or fallback. API key is secret/repr-hidden; Entra requires caller-supplied async token acquisition. HTTPX 0.28.1 / REST 2024-10-21, no redirects or environment proxy trust. Synthetic settings and MockTransport only during verification. |
| Input/retry/vector safety | Full contextualized token bounds, 8192/input plus bounded input-count/aggregate-token batches, capped retries/backoff, timeout and response bytes. Reorder indexed response vectors, reject model/count/index/dimension/nonfinite/bool/zero/float32-nonnormalizable values. Safe transport/408/429/5xx retries; auth/deployment 401/403/404 need configuration without local tight retries. |
| Profiles/space | Controlled full immutable ProfileCatalog snapshots, approved model/tokenizer/dimensions only, no guessed revision. Exact request-to-config comparison plus durable collection metadata bindings for endpoint/deployment/model/tokenizer/preprocessing and used profile snapshots. Validate actual vector config; do not adopt an unbound collection because dimensions match. Compatible different profile IDs can share a space. |
| Tokenizer | tiktoken 0.12.0 and explicit cl100k_base file, verified against official SHA-256. Exact upstream regex/special IDs; encode literal special-looking strings as ordinary text. No job-time fetch or ambient cache search. Real-tokenizer probe compares token IDs with the pinned upstream constructor and exercises N9A -> N9 -> local indexing. |
| Point sets | Async local API with CPU chunking/counting drained off-loop. Canonical UUIDv5 IDs use scope/content/profile/ordinal, independent of request/sequence. Preserve technical source, origin, sections, clean/contextualized text and full citations; metadata remains nested. Bounded upserts followed by exact scope/content/profile tail prune. Index/upsert/prune require wait=True and COMPLETED before returning existing profileId/chunkCount event. |
| Recovery/local storage | Real persistent AsyncQdrantClient local mode, reopen persistence, repeat/fewer chunks/section reassignment, profile/scope isolation, partial batches and lost committed responses. Local payload indexes have no acceleration; their keyword/integer API requests are verified, not server index behavior. No completed event for unconfirmed upsert/cleanup. |
| Reviewed inputs | Actual N9A rebuilt document JSON/review yields corrected text/final section IDs without original text page provenance. Saved corrected transcript yields changed text with original segment IDs, origin and known times; no Speech or source reconversion. |
| N11 boundary | Calls require external serialization. No atomic multi-batch visibility, cross-replica admission/leases, stale index/delete protection, durable confirmed-embedding receipt or callback-only replay is claimed. The index queue bootstrap still exits 2; N11 must supply its ordered runtime. No webhook is sent by the N10 API. |

### N10 exact checks and observed results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Full regressions use:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact check | Observed result |
| --- | --- |
| `Test-Path -LiteralPath ".venv" && .venv\Scripts\python.exe -m pip install "qdrant-client==1.19.1" "tiktoken==0.12.0"` | Installed the exact selected client/tokenizer and needed transitive client dependencies; existing Docling/Core/HTTPX/Pydantic/Azure pins unchanged. No model weights installed/downloaded. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_indexing.py -q --tb=short` before production implementation | **RED: 43 setup errors in 17.20s**, missing point_sets/indexing_settings modules. Initial implementation: **43 passed in 21.22s**. Expanded local/tokenizer/auth/batch checks: **48 passed in 17.22s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_indexing.py -k "invalid_vectors or nonfinite_unchecked" -q --tb=short` | **RED: 4 failed, 6 passed, 42 deselected in 16.17s**: finite values overflowed/underflowed float32 normalization, huge integers escaped as OverflowError, unchecked NaN metadata became null. Added float32-normalizability validation and finite validation before request serialization. Then **52 N10 cases passed in 16.61s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py tests/unit/test_reviewed_content.py tests/unit/test_content_contracts.py tests/unit/test_worker_boundaries.py -q --tb=short` | **298 passed in 63.16s**, preserving actual N9/N9A and strict/startup boundaries. |
| Opt-ins above plus `.venv\Scripts\python.exe -m pytest -q` (intermediate) | **911 passed, 18 skipped, 2 existing warnings in 86.63s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_indexing.py -k "invalid_embedding_inputs" -q --tb=short` | **RED: 4 failed, 2 passed, 57 deselected in 15.16s**: invalid direct adapter inputs reached tokenization or a string was treated as a character batch. Reject invalid lists before counting/sending; count off-loop with existing drain helper. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_indexing.py -q --tb=short` (final) | **63 passed in 19.70s**, including lost-commit-response, unconfirmed-write and independently incompatible vector-config cases. |
| `Test-Path -LiteralPath ".local" && curl.exe --fail --silent --show-error --output ".local/cl100k_base.tiktoken" "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"` | Prefetched only the public static vocabulary into the explicit ignored local file. No embedding/API credentials used. |
| `.venv\Scripts\python.exe docs/checks/content_processing_n10_probe.py --tokenizer ".local/cl100k_base.tiktoken"` | **All three PASS lines**, including the final rerun: official hash/upstream encoding equivalence; actual tokenizer + final N9A JSON/review and corrected transcript -> stub vectors -> persistent local Qdrant/reopen; Azure MockTransport with actual tokenizer. Socket access blocked throughout. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | **Passed**: no broken requirements and both pinned API/backend/confidence/referenced-picture/Core reload/frozen section-UUID PASS lines. |
| Opt-ins above plus `.venv\Scripts\python.exe -m pytest -q` (final) | **922 passed, 18 skipped, 2 existing warnings in 84.73s**. All 859 prior passing cases plus 63 N10 cases pass. |
| `git -c core.autocrlf=false diff --check`; for each of the 15 task files below, `git -c core.autocrlf=false diff --no-index --check -- NUL <path>`; `git check-ignore ".local/cl100k_base.tiktoken"`; `git status --short --untracked-files=all` / `git status --short` | **Passed**, no tracked/new-file whitespace diagnostics; tokenizer resource is ignored. Reviewed complete status and tracked README/dependency/ignore diffs against the initial uncommitted/user work. No files staged or committed. |

The same 18 omissions remain: 13 model opt-ins, 2 separate OCR-quality diagnostics,
Azure Blob opt-in, unavailable FFmpeg/FFprobe and absent Speech settings. The two
warnings are upstream Docling OCR-option serialization deprecations. No new skipped
N10 case or known failing local N10 acceptance check remains. Real-model OCR reruns
are not required for this indexing-only task.

API evidence: Context7 for exact Qdrant client 1.19.1/tiktoken 0.12.0, official
versioned source and installed async collection metadata/upsert/delete/wait/model
signatures, Microsoft Learn REST 2024-10-21 and embedding limits. See the
[indexing guide](content-processing-indexing.md) for links and configuration.
The tokenizer's SHA-256 is
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`.

### N10 changed files, pending evidence and handoff

- New source: `config/indexing_settings.py` and
  `indexing/{profiles,azure_embeddings,tokenizer,point_sets}.py` under
  `src/akay_convert_to_markdown/`.
- New tests/checks/docs: `tests/unit/test_content_indexing.py`,
  `docs/checks/content_processing_n10_probe.py`, `docs/content-processing-indexing.md`.
- Scoped updates: `.gitignore` (only explicit tokenizer asset), `pyproject.toml`
  (index/test adapter pins), README, specification, implementation plan,
  chunking guide and this prepend-preserving progress record. Existing N9/N9A
  production code, other worker paths, Docker and CI remain unchanged by N10.
- Production is **not integrated or verified**: Azure resource provisioning,
  actual endpoint/deployment/authentication/token audience/RBAC/quotas, approved
  full production profile/collection settings and explicitly authorized live
  checks remain pending. Qdrant-server transport, payload-index acceleration,
  replica behavior, clean isolated installs/images and semantic retrieval quality
  are not established by persistent client local mode/stub vectors.
- **Next fresh session: N11 only** — durable ordered admission/index/delete,
  receipts, cross-profile stale protection, mutation recovery and reassignment,
  reusing N10 with persistent technical-state doubles and local Qdrant. Missing
  Azure provisioning does not block those safe local checks. Do not rediscover
  credentials or replace approved model selection with another example.
- Rollback unit: the eight new source/test/check/guide files and seven scoped
  existing-file updates listed above together. Preserve prior N0-N9/N9A/user work
  and all historical checkpoints; tokenizer asset is ignored optional local data.
  No other repository/database, migration, live application-service call,
  credential discovery, commit, push, image publication, cloud resource or deployment.

## N10 prerequisite checkpoint — 2026-11-14 (preserved)

**N10: blocked before implementation — production embedding profile selection is
still required. N0-N9 and N9A remain complete on their recorded local boundaries.
Next task: N10 only, after the consumer confirms the effective embedding profile.**

### Reconciliation and blocking input

- Read applicable instructions, current README, the complete authoritative
  specification/plan, all preserved checkpoints and the N0 compatibility baseline;
  inspected git status and actual source through CodeGraph and targeted reads.
  Existing uncommitted implementation and user documents are preserved.
- N9's actual `chunk_content` and N9A's `rebuild_document_artifacts` implement the
  recorded structured-input boundaries. Their focused checks pass again below.
  Earlier task completion retains its recorded acceptance evidence; no wholesale
  rerun of N0-N9 or real-model inference was needed for this prerequisite check.
- N10 is the first incomplete task in dependency order. N9 and N9A are satisfied;
  the selected production embedding provider/model/deployment/dimensions/tokenizer
  prerequisite is not. Specification sections 12.1/20, plan N0/N10 and the N0/N9A
  handoffs explicitly leave it unresolved. The example AzureOpenAI profile is not
  approval. The actual index entry still exits 2 with `INDEXER_NOT_IMPLEMENTED`;
  project dependencies contain no production embedding or Qdrant adapter pin.
- Required next input: the intended production embedding profile, including
  provider, model/revision where applicable, deployment where required, dimensions
  and tokenizer. Verify its supported window/preprocessing against official pinned
  APIs when implementing. Do not infer values from fixtures or ambient credentials.
- Qdrant hosting/credentials and physical deployment identities remain separate
  pending configuration. They do not prevent local-Qdrant/stub verification once
  the embedding choice is supplied; no live-service access is needed for that work.

### Observed checks and scope

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_reviewed_content.py tests/unit/test_content_chunking.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

- **139 passed in 54.40s**; N0 probe printed both PASS lines for pinned APIs,
  confidence/backend boundaries, referenced-picture JSON reload and UUID vectors.
- Changed file in this continuation: **`docs/docling-rag-progress.md` only**.
  RED/GREEN is not applicable to this passive progress update. N10 acceptance,
  embedding API compatibility and local-Qdrant point-set tests are not yet run.
- No production behavior, dependency, README, Docker or CI change; no other task
  advanced. No credentials discovered, live application services called, database
  changes, migrations, commit, push, publication, provisioning or deployment.
- Resume **N10 only** after the focused profile-selection question is answered.
  N11 remains dependent on N10 acceptance; N10 is not marked complete.

## N9A checkpoint — 2026-11-14 (preserved)

**N9A: complete — reviewed Markdown preparation and corrected-transcript chunking
verified locally. Compatible N0-N9 remain complete. Next fresh session: N10 only,
after confirming the production embedding provider/model/deployment/dimensions/
tokenizer. No embedding or Qdrant mutation adapter was added in this session.**

### N9A prerequisite reconciliation

- Read applicable user/parent instructions (no repository-local AGENTS), current
  README, complete authoritative specification/plan, every preserved progress
  checkpoint and N0 baseline. CodeGraph preceded source exploration; targeted
  reads supplied omitted bodies and installed-library details.
- Actual entry/settings separation, strict contracts, extraction/section exporter,
  complete-set publisher, Speech/FFmpeg/YouTube/reliability paths and N9's saved
  document/transcript chunking match recorded N0-N9 evidence. Preserve those
  implementations; only the supplemental N9A seams were extended.
- The revised plan explicitly inserts N9A before N10. The prior checkpoint's
  next-task instruction below is historical and superseded by this checkpoint.
- Initial working tree already contained uncommitted N0-N9/user work and untracked
  docs. Preserved all earlier records and unrelated files. Baseline: **811 passed,
  1 failed, 18 skipped, 2 warnings in 51.84s**. The exact pre-existing failure was
  `tests/unit/test_content_contracts.py::test_all_complete_specification_json_examples_validate`:
  its classifier treated any `operation` as index, so revised `convert` examples
  failed. N9A updates only this affected classifier/count; all 11 complete current
  specification JSON examples now validate.

### N9A implementation and decisions

| Area | Implemented and verified behavior |
| --- | --- |
| Contracts/events | Document operation `convert` by default or `rebuildFromMarkdown`; extraction-review reference required only for rebuild. Reject non-Markdown rebuild input, draft/final or extraction/final path collision and true enrichment flags. Preserve strict seven-language validation without running OCR. Completed and recoverable failed document callbacks carry operation; media/index envelopes remain compatible. Legacy parser cannot downgrade extraction-review fields. |
| Reconstruction | Direct pinned native `MarkdownDocumentBackend`/`InputDocument`, no extraction pipeline or original JSON input. Marko AST spans remove only actual structural comments and insert existing N4 UUID markers at current headings. Fenced/indented/inline code stays literal. Preserve edited Markdown except markers, known-image relative rebasing and UTF-8/LF/BOM normalization. |
| Images/review | Read the report only from configured destination container. Require matching opaque contentKey/document extraction type and generated image references inside that report's artifact directory. Preserve its image inventory/files without copies; removed/changed/missing/local/remote/data/malformed image links never trigger resolution or failure solely for nonexistence. New final JSON/review/Markdown use a separate destination; new text has no inherited page/coordinate/confidence provenance. Original image page numbers remain explicitly original. |
| Parser boundary | Keep code, tables, formula text and heading edits representable by the native parser. Pinned Docling loses rich inline setext-heading attachment; convert only the backend input to equivalent ATX while preserving original source Markdown. Require complete heading count/level mapping before emitting sections. No PDF/layout round-trip promise; unsupported raw-HTML heading maps fail safely and final review records a normalization warning. |
| Publication/compatibility | Reuse N5/N8 source-free ready recovery, conditional creates, failure receipts, callback deduplication and owned cleanup/draining. Bind rebuild operation/report/container in material identity. Expand only the two new default fields when comparing old convert snapshots; preserve old complete convert results and reject changed source/options/payload. Rebuild packages contain only the three new files, never shared extraction images. |
| N9 verification | Actual extraction -> edited Markdown -> new JSON/review -> real N9 chunks proves renamed/added/deleted/reordered/repeated headings and corrected body text reach final chunks. Corrected transcript fixture changes only text and exercises both actual split and merged results, retaining IDs/order/origin/speaker/language/times. No N9 production change was needed. |
| Dependencies/API | Preserve all earlier pins and explicitly pin already-installed Marko **2.2.5**, within Docling-slim 2.141.0's >=2.1.2,<3 range. Context7 v2.141.0 plus exact official backend/InputDocument/Marko sources and actual installed signatures/spans verified. No installation or model/tokenizer download. Common imported model/datamodel definitions are not initialized extraction models; fresh-process traps distinguish these correctly. |
| Consumer boundary | Document freezing/approval lock, draft/transcript persistence, current-request callback handling, final section persistence and explicit indexing as future consumer/Akay.Be responsibilities. No editor, endpoint, approval state, database or automatic indexing added to Python. |

### N9A exact checks and observed results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Baseline and full
regressions explicitly disable live/model/quality opt-ins:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact check | Observed result |
| --- | --- |
| Opt-ins above plus `.venv\Scripts\python.exe -m pytest -q` before changes | **811 passed, 1 failed, 18 skipped, 2 warnings in 51.84s**. Pre-existing revised-example classifier failure identified above. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_reviewed_content.py -q --tb=short` before production implementation | **RED: 8 failed, 15 passed, 9 setup errors in 12.71s**. Missing operation/default/callback fields and absent rebuild module; invalid variants already reject unknown fields and N9 corrected-transcript checks already pass. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_reviewed_content.py tests/unit/test_content_contracts.py -q --tb=short` after initial implementation | **1 failed, 190 passed in 14.95s**. Structural marker removal left its standalone newline; removed that newline without removing code literals. |
| Same N9A-only command with setext/recovery/compatibility/fresh-process cases | **RED: 4 failed, 38 passed in 16.02s**. Real gaps: rich-inline setext attachment, recovered failure operation, old convert receipt snapshot compatibility. Fourth failure was harness-only: import guard confused relative `.azure` settings modules/optional probes with application service access. |
| Same N9A-only command after those fixes | **42 passed in 28.42s**. Fresh-process harness also supplies an empty fixture home and permits common inference utility definitions imported by pinned datamodels while forbidding actual extraction pipelines/concrete models. No model was initialized to satisfy the test. |
| Same N9A-only command after malformed-link/failure/cancellation/identity cases | **RED: 3 failed, 44 passed in 25.76s**. One production gap: `urlsplit` raises for a malformed user-edited image URL; leave it verbatim. Two harness errors expected FakeWebhook to append before raising; use AsyncMock call capture instead. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_reviewed_content.py tests/unit/test_content_contracts.py tests/unit/test_artifact_publication.py tests/unit/test_document_artifacts.py tests/unit/test_content_chunking.py -q --tb=short` | **321 passed in 32.49s**, including all 47 N9A cases and extraction/chunking/publication/contract regressions. |
| Final regression command below | **506 focused passed, 2 warnings in 48.85s**; **859 passed, 18 skipped, 2 warnings in 60.50s** overall. `pip check` printed no broken requirements. Combined shell reached its 120s limit before the final probe returned, so probe evidence is from the separate completed command below. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | **Passed** separately: no broken requirements; both PASS lines for pinned options/confidence/backend/Core reload and frozen section UUID vectors. |
| `git -c core.autocrlf=false diff --check`; for each of the 18 task files below, `git -c core.autocrlf=false diff --no-index --check -- NUL <path>`; `git status --short --untracked-files=all` | **Passed**, no whitespace diagnostics for tracked or new/untracked task files. Reviewed final status plus tracked README/dependency/legacy-seam diffs; pre-existing N0-N9/user files retained. No files staged or committed. |

Final regression command (after the three explicit opt-ins above):

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_reviewed_content.py tests/unit/test_content_contracts.py tests/unit/test_content_chunking.py tests/unit/test_document_artifacts.py tests/unit/test_docling_conversion.py tests/unit/test_artifact_publication.py tests/unit/test_media_artifacts.py tests/unit/test_worker_reliability.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

Installed API check (completed, no credentials or service clients):

```powershell
.venv\Scripts\python.exe -c 'from importlib.metadata import version; import inspect,marko; from docling.datamodel.backend_options import MarkdownBackendOptions; from docling.datamodel.document import InputDocument; from docling.backend.md_backend import MarkdownDocumentBackend; print({p:version(p) for p in ["docling","docling-core","marko","pydantic"]}); print("InputDocument",inspect.signature(InputDocument)); print("Markdown backend",inspect.signature(MarkdownDocumentBackend)); print("fetch flags",MarkdownBackendOptions(fetch_images=False,enable_local_fetch=False,enable_remote_fetch=False).model_dump()); ast=marko.Markdown(extensions=["gfm"]).parse("# Heading\n\n![image](image.png)\n"); print("heading source_span",ast.children[0].source_span); print("image dest_span",ast.children[-1].children[0].dest_span)'
```

Observed Docling **2.141.0**, Core **2.99.0**, Marko **2.2.5**, Pydantic **2.10.4**,
supported `backend_options`, all three fetch flags false, heading span `(0,10)`
and image destination span `(20,29)`. Exact official source links are in the
[reviewed-content guide](content-processing-reviewed-content.md).

Runtime evidence uses the actual document processor/publisher and persistent
conditional/leased Blob doubles. Ready/complete replay works after removing the
draft/report from the double; preserved crop bytes/ETags remain unchanged.
Permanent missing/foreign-review failures replay the same operation-specific event
without a new build. Native parse barriers prove event-loop responsiveness and
draining under repeated cancellation. Fresh-process import/resource traps prove
the direct reconstruction API needs no extraction pipeline, concrete extraction
model, Speech, external service or image access. Real-model OCR checks are neither
required nor claimed for reconstruction.

### N9A changed files, acceptance and handoff

- Source: new `conversion/markdown_rebuild.py`; scoped amendments to
  `contracts/requests.py`, `contracts/events.py`, `contracts/artifacts.py`,
  `conversion/document_artifacts.py`, `processing/published_document_processor.py`,
  `processing/document_processor.py`, `models/conversion_request.py`,
  `storage/artifact_publication.py` under `src/akay_convert_to_markdown/`.
- Tests/fixtures: new `tests/unit/test_reviewed_content.py`,
  `tests/fixtures/content_processing/reviewed-draft.md`,
  `tests/fixtures/content_processing/corrected-transcript.json`; amend only current
  specification-example dispatch/count in `tests/unit/test_content_contracts.py`.
- Docs/config: README, `docs/content-processing-contracts.md`, new
  `docs/content-processing-reviewed-content.md`, this preserved progress record,
  one direct Marko pin in `pyproject.toml`. Authoritative specification/plan and
  existing N9 chunking production code remain unchanged. Docker/CI require no N9A
  change; their implementation remains N12-N15.
- Acceptance met locally for N9A: corrected final text/headers/tables/code/formulas,
  regenerated structural IDs, extraction inventory/diagnostic preservation, null
  final text page confidence, no arbitrary resource fetching, strict operation and
  OCR-language contracts, compatible default convert/media behavior, deterministic
  replay, missing/wrong reports, publication recovery, corrected segment citations.
  No local N9A acceptance check remains failing or blocked.
- **Pending evidence:** actual Azure transport/lease expiry, real services,
  clean dependency installs/images, .NET draft/approval/transcript persistence and
  production embeddings/Qdrant remain external or later-task evidence. Same 18
  skips: 13 model opt-ins, 2 optical-quality diagnostics, Azure Blob opt-in,
  unavailable FFmpeg/FFprobe, missing Speech settings. Two warnings remain upstream
  OCR serialization deprecations. Previous measured OCR quality limitations are
  unchanged; no additional model checks are required by this parser-only task.
- **Next fresh session: N10 only**, with N9 and N9A complete. First obtain the
  production embedding provider/model/revision/deployment where required,
  dimensions, compatible tokenizer/window/preprocessing and authorized target
  configuration. Do not infer production settings from example profiles or discover
  ambient credentials. N10 is not implemented here.
- Rollback unit: the new rebuild module/tests/fixtures/guide, listed N9A contract/
  processor/publisher changes, Marko pin and current docs together. Preserve all
  pre-existing N0-N9/user bytes and earlier checkpoints. No other repository or
  database modified; no migration, service call, credential discovery, commit,
  push, image publication, resource creation or deployment.

## N9 checkpoint — 2026-11-14 (preserved)

**N9: complete — local structured chunking acceptance verified. N0-N8 remain
complete. Next fresh session: N10 only, after confirming the production embedding
provider/model/deployment/dimensions/tokenizer. The index runtime still fails
closed; no embedding or Qdrant mutation adapter is implemented by N9.**

### N9 task and prerequisite evidence

- Executed only N9, dependent on N2/N4/N6. Read applicable user/parent instructions
  (no repository-local AGENTS), current README, full specification/plan, the full
  preserved progress record and N0 baseline. CodeGraph preceded source exploration;
  targeted reads supplied omitted bodies and exact installed-library APIs.
- Actual N1 entry/settings separation, N2 source/profile/context/artifact schemas,
  N3 extraction, N4 UUID/heading/review exporter, N5 complete publication, N6 timed
  transcript exporter and N7/N8 source/reliability paths match recorded evidence.
  N0 API/UUID probe passes again. N9 chunking was absent; index entry remains an
  intentionally non-consuming bootstrap. Baseline rerun: **758 passed, 18 skipped,
  2 existing warnings in 44.16s**.
- Initial tree contained all uncommitted N0-N8/user work and untracked documents.
  Preserved every earlier checkpoint and unrelated change. No essential decision
  blocks N9's explicit test tokenizer; no production embedding choice is inferred.

### N9 implementation and decisions

| Area | Verified behavior |
| --- | --- |
| Local boundary | New synchronous `indexing.chunking.chunk_content(IndexRequest, bytes, tokenizer=..., tokenizer_id=..., review_raw=...)` returns internal typed chunks or a safe permanent error, never a partial list. No queue consumption, Blob download, extraction, ASR, embeddings, callbacks or Qdrant mutations. Future async callers must use existing drain-on-cancel and bounded downloads. |
| Saved documents | Strict finite/unique-key JSON plus actual Core schema validation. No original reconversion, image resolution or arbitrary local reads. Clear image objects/private origin URI/hyperlinks from chunk preparation; reject nonportable resource filenames. Keep available item/page refs. Without review, standard Core JSON does not encode original Blob identity/contentKey: origin remains null rather than invented. |
| Shared sections | Move N4's unchanged UUID function/namespace and heading serializer into Core-only `conversion/sections.py`; preserve aliases in `document_artifacts.py`. Same frozen vectors and all N4 regressions pass. Reproduce N4's exact inline-heading escaping for review validation; normalize inline-only heading text on the reloaded copy, not the stored artifact. |
| Principal boundaries | `fromReview` requires matching content key, source filename, artifact directory and complete ordered section inventory (UUID/ref/title/level/parent/page). Partition by structural identity before HybridChunker peer merging, including repeated titles. Preamble remains null; table-cell headings/furniture/comments cannot create domain sections. These checks establish structural consistency, not cryptographic authenticity of same-named originals. |
| Additional/generic contexts | `fixed` attaches supplied parent UUID/path and keeps internal headings. `none` leaves domain identity unset. One source per call; no scope/content/request metadata is tokenized. Heading-only content is retained with Core's supported `always_emit_headings`. |
| Transcripts/citations | Build actual Core text items from ordered saved segments; map each item to original segment ID/range/language/speaker. Preserve stable Blob/YouTube origin separately from technical JSON source. Split phrases cite the whole available original interval, never invented word timings. Merges retain every contributing segment; aggregate boundaries stay null if any contributing boundary is missing. |
| Token budget | Require an explicit BaseTokenizer with matching configured ID/capacity. Use that same counter for real HybridChunker/semchunk splitting, peer merges, complete contextual text and final validation. Context includes domain path/resource/internal headings/body as applicable. Fail safely for oversized context/final overflow; never silently drop headers or expose Core's content-bearing overflow warnings, including nonadditive counting. Disable optional table-header repetition because its separate line-splitting path omits the full external context. Table content and citations remain. |
| Dependencies/API evidence | Preserve Docling/Core/Azure pins; directly pin already-installed **semchunk 3.2.5** (inside Core 2.99.0's supported >=2.2,<4 range). Context7 plus official versioned Core/semchunk sources and installed signatures verify custom BaseTokenizer/counter, serializer provider, chunk/context and heading APIs. Provider is an ABC, not a Pydantic model. No install, tokenizer/model download or production model selection. |

### N9 exact checks and results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Baseline and full
regressions explicitly disable live/model/quality opt-ins:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact check | Observed result |
| --- | --- |
| Opt-ins above plus `.venv\Scripts\python.exe -m pytest -q` baseline | **758 passed, 18 skipped, 2 warnings in 44.16s**. No pre-existing failure. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py -q --tb=short` before production implementation | **RED: 1 failed, 33 setup errors in 11.74s**, missing `indexing` module. Initial implementation: **16 failed, 18 passed in 13.60s**; provider incorrectly used Pydantic Field and import harness wrongly forbade optional library probes. Correct ABC constructor and simulate absent optional tokenizers with ImportError; then **34 passed in 14.62s**. |
| Same N9 command after saved-package/path/merge/table edge tests | **RED: 4 failed, 41 passed in 14.46s**: inline-only heading lacked native text; local document resource names leaked into context. Normalize actual rendered heading on reloaded copy and reject invalid names. `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py tests/unit/test_document_artifacts.py -q --tb=short`: **75 passed in 18.98s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py -k actual_n4 -q --tb=short` | **RED: 1 failed, 1 passed, 44 deselected in 11.97s**. Inline punctuation used different Markdown escaping from N4; use exact shared export options. Next five-file focused regression: **338 passed in 37.22s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py -k "actual_n6 or final_full or empty_structured or inline_heading_links" -q --tb=short` | **RED: 2 failed, 3 passed, 46 deselected in 11.69s**. Inline heading fallback retained local file/drive hyperlink targets. Apply N4's local-link removal before collecting titles; retain exact N4 rendering for legitimate review matching. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py -k "heading_only" -q --tb=short` | **RED: 2 failed, 51 deselected in 10.26s**. Core defaults omit heading-only content; use `always_emit_headings` and preserve leaf title text/item provenance. Same N9 command then **53 passed in 15.99s**. |
| Pre-review full regression command below | **420 focused passed, 2 warnings in 40.10s**; **811 passed, 18 skipped, 2 warnings in 46.60s** overall; pip check and N0 probe passed. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py -k nonadditive -q --tb=short` | **RED: 1 failed, 53 deselected in 10.12s**. Review found Core's second overflow condition could recurse/drop headings and warn with content when token cost is nonadditive. Guard both actual length conditions before calling the pinned splitter. |
| Final exact regression/check command below | **421 passed, 2 warnings in 39.23s** focused; **812 passed, 18 skipped, 2 warnings in 54.18s** overall. All 758 baseline cases plus **54 N9 cases** pass. `pip check`: no broken requirements. N0 probe: both pinned API/backend/confidence/Core reload/frozen-UUID PASS lines. |

Final regression/check command (after the three explicit opt-ins above):

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py tests/unit/test_document_artifacts.py tests/unit/test_docling_conversion.py tests/unit/test_content_contracts.py tests/unit/test_media_artifacts.py tests/unit/test_artifact_publication.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

Runtime harness: actual pinned Core HybridChunker/semchunk and generated saved
JSON; actual N4 package -> JSON/review reload -> principal chunks, and actual N6
package -> transcript reload -> chunks. No original/source service is available
to those adapters. Resource-access traps cover malicious image references;
fresh-process import guard forbids Docling extraction/Azure/yt-dlp and simulates
absent optional Transformers/Torch. This proves no mandatory foreign runtime/model
import for this local API, not clean-install or image isolation (N12-N13).

Installed API checks:

```powershell
.venv\Scripts\python.exe -c 'from importlib.metadata import version; import inspect; from docling_core.transforms.chunker.hybrid_chunker import HybridChunker; from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer; print("docling-core",version("docling-core")); print("HybridChunker",inspect.signature(HybridChunker)); print("tokenizer",inspect.getsource(BaseTokenizer))'
.venv\Scripts\python.exe -c 'from importlib.metadata import version; import inspect,semchunk; from docling_core.transforms.chunker.hierarchical_chunker import ChunkingSerializerProvider; print("semchunk",version("semchunk")); print("chunkerify",inspect.signature(semchunk.chunkerify)); print("provider inheritance",ChunkingSerializerProvider.__mro__)'
```

Observed Core **2.99.0**, semchunk **3.2.5**, required BaseTokenizer's three methods,
callable token-counter support and non-Pydantic provider inheritance. Exact
official source links are in the chunking guide.

Whitespace/status check (includes new/untracked files):

Observed: no whitespace diagnostics across all 10 N9 files or existing tracked
changes. Reviewed complete final status and tracked README/dependency diffs;
preserved the original N0-N8/user file set. No unrelated file was removed.

```powershell
git -c core.autocrlf=false diff --check; foreach ($path in @('src/akay_convert_to_markdown/indexing/__init__.py', 'src/akay_convert_to_markdown/indexing/chunks.py', 'src/akay_convert_to_markdown/indexing/chunking.py', 'src/akay_convert_to_markdown/conversion/sections.py', 'src/akay_convert_to_markdown/conversion/document_artifacts.py', 'tests/unit/test_content_chunking.py', 'pyproject.toml', 'README.md', 'docs/content-processing-chunking.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }; git status --short --untracked-files=all
```

### N9 changed files, acceptance and next session

- New `indexing/__init__.py`, `indexing/chunks.py`, `indexing/chunking.py` and
  `conversion/sections.py` under `src/akay_convert_to_markdown/`; updated only the
  shared section imports in existing `conversion/document_artifacts.py`.
- New `tests/unit/test_content_chunking.py`, `docs/content-processing-chunking.md`;
  updated README, one `semchunk` dependency pin in pyproject and this preserved
  progress record. Specification/plan, other runtime paths and Docker/CI unchanged.
- N9 acceptance met locally: both saved formats, all section contexts, repeated/
  nested/inline headings, fixed parent/internal context, full token bounds,
  table/page refs, split/merged/nullable transcript citations, safe invalid/empty/
  context-overflow behavior, no image fetching and no source reconversion.
  No local N9 acceptance check remains failing or blocked.
- **Missing evidence/limits:** production tokenizer/model compatibility is not
  claimed from the test counter. Clean target installs/images and actual cloud
  boundaries remain later tasks. Same 18 skips: 13 model opt-ins, 2 optical-quality
  diagnostics, Azure Blob opt-in, unavailable FFmpeg/FFprobe and missing Speech
  settings. Two warnings remain upstream OCR serialization deprecations. Previous
  OCR-quality/service limitations are preserved; no model rerun is required here.
- **Next fresh session: N10 only.** First obtain the production embedding
  provider/model/revision/deployment (where required), dimensions and compatible
  tokenizer/window/preprocessing configuration. Do not assume the example profile
  is approved. Qdrant destination/authorization and physical deployment identities
  remain scoped inputs; do not discover ambient credentials or contact services.
- Rollback unit: the four new source modules, new tests/guide, section relocation,
  one dependency pin and current README/progress amendments together. Preserve
  N0-N8/user work and the old `document_artifacts` section aliases when relocating
  back. No other repository/database, migration, credential discovery, package or
  model download, live application call, commit, push, publication or deployment.

## N8 checkpoint — 2026-11-14 (preserved)

**N8: complete — local worker reliability acceptance verified. N0-N7 remain
complete. Next fresh session: N9 only. Cloud lock/lease expiry, actual codec/Speech/
YouTube interoperability and container termination remain external/later evidence.**

### N8 task and prerequisite evidence

- Executed only N8, dependent on completed N5-N7. Read applicable parent/user
  instructions (no repository-local AGENTS), README, full specification/plan,
  all current/preserved progress and N0 baseline. CodeGraph preceded source
  exploration; targeted reads supplied omitted bodies. Inspected actual N1
  entry/settings, N2 contracts, N3/N4 extraction/export, N5 receipt/fencing,
  N6 timed Speech/FFmpeg and N7 guarded YouTube/runtime code against recorded
  checks. Baseline rerun: **720 passed, 18 skipped, 2 warnings in 72.71s**.
- Initial tree contained uncommitted N0-N7 and user documentation/work. Preserved
  all earlier checkpoints and unrelated changes. No essential unresolved N8
  configuration blocks local work; embeddings/deployment inputs remain scoped.

### N8 implementation and decisions

| Area | Verified behavior |
| --- | --- |
| Admission/renewal | Disable SDK prefetch; receive at most active concurrency. Register renewal before parsing, including invalid-message callbacks. New whole-workflow deadline **4200s**, renewal default **4500s** instead of 900s; validate workflow >= extraction + configured callback attempt/delay allowance + 60s, renewal >= workflow + 60s. Positive/finite callback/concurrency settings. These are configurable validation floors, not capacity measurements. |
| Lock loss/settlement | Async failure callback plus public SDK error/expiry monitoring cancels/drains work. Do not process/settle known-lost locks. Complete only after processing/notification; transient failures abandon valid locks. Contain SDK/unexpected settlement errors without a second conflicting disposition or stopping the next message. Outer deadline is transient, not a new definitive failure after publication. |
| Stable outcomes | Extend existing leased/conditional publication receipt with per-request safe build-failure outcomes (old receipts default empty). Persist before HTTP; callback-only retry/recreation replays identical failed event without extraction/Speech/YouTube, even if source recovers. Completed/ready packages retain N5 reuse. New request IDs can try still-unpublished destinations; immutable request checks retained. No public artifact/schema/migration added. |
| Callback policy | Reuse allowlist/X-Api-Key/idempotency identity; extend bounded local retry from selected statuses to **all 5xx**, preserving 408/429/network/timeout behavior and one local attempt for ordinary client errors. A recorded notification skips repeat delivery; uncertain HTTP/receipt state can repeat the same event and requires receiver deduplication. |
| Ownership/cleanup | Shared owned-task drain prevents repeated cancellation/global runner shutdown from closing renewers/clients while native work continues. Hash inventories, legacy Markdown writes and cleanup drain executor Futures. Blob heartbeat loss interrupts async builds/callbacks; native work drains before lease release. N5 immutable ready uploads remain fenced. |
| Processes/shutdown | Shield FFmpeg/FFprobe creation until child handle ownership; kill/reap on cancellation, including repeated cancellation during exit. Reuse N7 YouTube process-tree handling. SIGINT/SIGTERM stops admission, drains active batch, returns a just-received unstarted batch, restores handlers; Windows main-thread signal fallback included. |
| Legacy compatibility | Keep mixed/dedicated legacy envelopes, formats and overwrite/reuse semantics. Move legacy completed callback outside extraction/upload timeout to prevent slow notification from converting an already-uploaded success into failed. Legacy jobs do not acquire new version-one durable failure receipts. |
| Safe observability | Failure logs retain safe event/code/class/correlation, not arbitrary exception messages/tracebacks or captured subprocess detail. Add `error_type` to JSON output; hide webhook key in settings repr. Document actual DLQ ownership/recovery without promising an unimplemented exhaustion callback. |
| API evidence | Context7/Microsoft Learn plus official **azure-servicebus_7.14.0** async renewer source and installed signatures verify register callback/async close/public lock state. That version may stop renewal on timeout without immediately invoking failure callback; monitor public error/expiry too. Context7 exact **HTTPX 0.28.1** verifies retained timeout/transport/redirect API. No dependency or SDK pin change. |

### N8 exact checks and results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Full/regression runs use:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact check | Observed result |
| --- | --- |
| Opt-ins above plus `.venv\Scripts\python.exe -m pytest -q` baseline | **720 passed, 18 skipped, 2 warnings in 72.71s**; no pre-existing failure. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -q --tb=short` before production changes | **RED: 19 failed, 1 passed in 2.77s**: unsafe budgets, absent invalid-message renewal/loss interruption/workflow deadline, escaping settlement errors, leaked exceptions, incomplete 5xx retry and non-durable failure. |
| First focused regression across reliability/consumer/publication/media/processing/webhook/boundaries | **215 passed in 33.50s** after initial changes. |
| Same N8-only command after additional ownership tests | **RED: 3 failed, 24 passed in 2.70s**: hung async builder after Blob lease loss, repeated process cancellation returned before exit, subprocess detail in logs. Fixed those production paths; next focused six-file regression **202 passed, 2 warnings in 22.77s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -k "spawn_cancellation or legacy_callback or lock_loss_during_callback or receipt_response" -q --tb=short` | **RED: 2 failed, 2 passed, 27 deselected in 3.34s**: cancellation during spawn returned before acquiring/reaping child; slow legacy callback emitted failed after upload. Shield/drain child creation and separate callback budget fix both. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -k "signal_fallback" -q --tb=short` | **RED: 1 failed, 31 deselected in 3.76s**; missing main-thread fallback/restoration helper. Implemented and verified in final regression. |
| Intermediate full regression after those fixes | **351 focused passed in 52.92s**; **752 passed, 18 skipped, 2 warnings in 61.27s** overall; pip/probe passed. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -k "unexpected_error_cannot or global_runner" -q --tb=short` | **RED: 1 failed, 1 passed, 32 deselected in 2.60s**: unexpected invalid-notification failure escaped consumer; global cancel-all/native ownership already passed. Added safe outer containment. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -k "settlement_failure" -q --tb=short` | **RED: 2 failed, 2 passed, 32 deselected in 2.61s**: non-SDK settlement failures escaped. Contain all settlement exceptions without another disposition. Test creates fresh exceptions per case to avoid inherited cross-test tracebacks. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -k "stop_during_receive" -q --tb=short` | **RED: 1 failed, 36 deselected in 3.08s**: batch arriving after stop was processed. Recheck stop after receive and return the unstarted batch. |
| Pre-review run of regression/check command below | **356 passed, 2 warnings in 44.16s** focused; **757 passed, 18 skipped, 2 warnings in 54.69s** overall; pip check and N0 probe pass. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py -k "during_lease_release" -q --tb=short` | **RED: 1 failed, 37 deselected in 3.01s**. Review found late cancellation swallowed while draining lease release. Added cleanup-specific shielding that finishes cleanup and then propagates cancellation; consumer/process cleanup use the same distinction. |
| Final exact regression/check command below | **357 passed, 2 warnings in 44.78s** focused; **758 passed, 18 skipped, 2 warnings in 49.36s** overall. All 720 baseline cases plus **38 N8 cases** pass. No broken requirements. N0 probe prints both pinned API/confidence/backend/reference/reload/frozen-UUID PASS lines. |
| Installed API command below | Actual **azure-servicebus 7.14.0**; `register` accepts optional async `on_lock_renew_failure`; `close` is coroutine; `ServiceBusReceivedMessage.locked_until_utc` is a property. No SDK client/credentials/network needed. |

Final regression/check command (after explicit opt-ins above):

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_worker_reliability.py tests/unit/test_consumer.py tests/unit/test_artifact_publication.py tests/unit/test_media_artifacts.py tests/unit/test_webhook.py tests/unit/test_processing.py tests/unit/test_process_runner.py tests/unit/test_worker_boundaries.py tests/unit/test_docling_conversion.py tests/unit/test_youtube_source.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

Installed API command:

```powershell
.venv\Scripts\python.exe -c "from importlib.metadata import version; import inspect; from azure.servicebus.aio import AutoLockRenewer; from azure.servicebus import ServiceBusReceivedMessage; print('azure-servicebus', version('azure-servicebus')); print('register:', inspect.signature(AutoLockRenewer.register)); print('close:', inspect.signature(AutoLockRenewer.close)); print('async close:', inspect.iscoroutinefunction(AutoLockRenewer.close)); print('locked_until_utc:', isinstance(ServiceBusReceivedMessage.locked_until_utc, property))"
```

Runtime harness: actual shared consumer, dedicated media composition and durable
publisher with conditional/leased persistent doubles, HTTPX MockTransport and
existing local FFmpeg/YouTube/Speech fixtures. Native executor barriers verify
event-loop progress, no early cleanup/renewer release under repeated cancellation,
lock loss, hashing and global `asyncio.run` shutdown. Real short-lived Python
subprocess regressions exercise exit/timeout; controlled spawn/exit doubles prove
the cancellation races. Failed-media retry proves one download/probe and zero
Speech calls; lost-lock completed-callback retry proves one Speech call/package.

Whitespace/status check (includes tracked and untracked N8 files):

Observed: no whitespace diagnostics across all 17 N8 files or tracked changes;
reviewed final status/diffs and preserved the earlier N0-N7/user file set.

```powershell
git -c core.autocrlf=false diff --check; foreach ($path in @('src/akay_convert_to_markdown/config/settings.py', 'src/akay_convert_to_markdown/messaging/service_bus_consumer.py', 'src/akay_convert_to_markdown/notifications/webhook_client.py', 'src/akay_convert_to_markdown/processing/blocking.py', 'src/akay_convert_to_markdown/processing/document_processor.py', 'src/akay_convert_to_markdown/processing/published_document_processor.py', 'src/akay_convert_to_markdown/processing/published_media_processor.py', 'src/akay_convert_to_markdown/storage/artifact_publication.py', 'src/akay_convert_to_markdown/services/process_runner.py', 'src/akay_convert_to_markdown/worker_runtime.py', 'src/akay_convert_to_markdown/logging.py', 'tests/unit/test_worker_reliability.py', 'tests/unit/test_consumer.py', 'README.md', 'docs/content-processing-reliability.md', 'docs/content-processing-publication.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }; git status --short --untracked-files=all
```

### N8 changed files, acceptance and next session

- Source under `src/akay_convert_to_markdown/`: updated `config/settings.py`,
  `messaging/service_bus_consumer.py`, `notifications/webhook_client.py`,
  `processing/blocking.py`, `processing/document_processor.py`,
  `processing/published_document_processor.py`, `processing/published_media_processor.py`,
  `storage/artifact_publication.py`, `services/process_runner.py`, `worker_runtime.py`,
  `logging.py`. New `tests/unit/test_worker_reliability.py`; existing consumer test
  changes only expected `prefetch_count=0`.
- New `docs/content-processing-reliability.md`; updated README, publication guide
  and this append-preserving progress record. Specification/plan, dependencies,
  Docker/CI, other repositories, databases and user documents are unchanged by N8.
- Acceptance met locally: repeated stable callbacks, permanent/transient outcomes,
  lost Service Bus/Blob ownership, settlement containment, shutdown/cancel-all/
  repeated cancellation, responsive loop and scoped temporary ownership/cleanup.
  No known local N8 acceptance failure remains.
- **Limits/missing evidence:** actual Azure renewal/settlement/replica lease expiry,
  production signals/container grace, codec decoding (FFmpeg/FFprobe unavailable),
  authorized Speech/YouTube interoperability and image isolation remain unverified.
  Native thread draining is not hard termination: a hung inference may exceed
  workflow and finite renewal budgets; cancellation does not send success.
  Ready artifacts retain create-only fencing. No cloud guarantee is inferred.
- Same 18 skips: 13 model opt-ins, 2 optical diagnostics, Azure Blob opt-in,
  unavailable FFmpeg/FFprobe and absent Speech configuration. Both warnings are
  existing upstream OCR serialization deprecations; N3 quality limits unchanged.
- Embedding provider/model/tokenizer and physical names/identities remain later
  inputs; no credentials discovered/reused, live application service called,
  package/model downloaded, migration, commit, push, publication or deployment.
- Rollback unit: the N8 source amendments, new reliability tests/guide, consumer
  assertion and current documentation changes together. Preserve N0-N7/user work;
  do not run older replicas over newly written failure receipts without an
  explicit compatibility plan. Existing receipts need no migration.
- **Next fresh session: N9 only**, dependent on N2/N4/N6. Adapt saved Docling JSON
  and timed transcripts to bounded, section-aware chunks with an explicit
  compatible test tokenizer/budget. No production embedding model is selected;
  that decision remains prerequisite to N10. No N9 code was implemented here.

## N7 checkpoint — 2026-11-13 (preserved)

**N7: complete — local mocked YouTube extraction, guarded network/limits and
media publication acceptance verified. N0-N6 remain complete. Next fresh session:
N8 only. Real YouTube/platform interoperability remains unverified.**

### N7 task and prerequisite evidence

- Executed only N7, dependent on completed N6 and reusing N5 publication. Read
  parent instructions (no repository-local AGENTS), current README, authoritative
  specification/plan, full current/preserved progress, N0 baseline and historical
  T0 progress. Inspected actual N1 entries/settings, N2 contracts, N3/N4 extraction/
  export boundaries, N5 receipts and N6 Speech/FFmpeg/media artifacts/runtime.
  CodeGraph was present and used first; targeted reads supplied omitted source.
- Prior completion is supported by actual code plus recorded offline acceptance,
  not task labels. Baseline rerun: **645 passed, 18 skipped, 2 existing warnings
  in 48.25s**. N7 was absent: dedicated media rejected all YouTube sources.
- Initial tree already contained uncommitted N0-N6 and user documentation/work.
  Preserved all checkpoints and unrelated changes. No essential N7 configuration
  decision blocked local implementation; embedding/deployment inputs remain later.

### N7 implementation and decisions

| Area | Verified behavior |
| --- | --- |
| Source contract | Shared `video_identity` validates one HTTPS watch/shorts/short-link video and exact 11-character ID. Reject playlists (including video+list), live URL paths, duplicate/unknown parameters, credentials, escapes, fragments and unsafe hosts/schemes/ports. Preserve original URL; send canonical full-video URL only to extraction. No crawling. |
| Dependencies | Optional `youtube` extra and offline `test` extra pin yt-dlp **2025.11.12**, its exact upstream EJS **0.3.1**, Deno **2.5.6**. Official versioned sources and installed APIs verified after Context7 lookup. Package install only; no job-time component downloads or nightly/latest updates. |
| Extractor boundary | Register only YouTube IE; request unprocessed metadata without yt-dlp downloading. Select direct HTTPS audio-only WebM/M4A/MP3/OGG, no video/fragment/DRM/generic fallback. Reject wrong identity, playlist, live/upcoming/archived-live, unavailable/restricted/private content and unknown/excessive duration. No guarantee for every public video. |
| Network | Override the pinned embedding `urlopen` boundary for all metadata/JS, with the same guarded transport for audio. Restricted YouTube/API/CDN hosts, validated redirects and all DNS answers, numeric-address pinning with original-host TLS/SNI. Reject private/link-local/loopback/metadata/multicast/reserved and IPv4-transition destinations. Never forward credential/cookie/Host overrides; no proxy/config fallback. Suppressed optional unsafe requests poison the result. |
| Limits/process | Audio declared/actual byte cap, bounded metadata/hops/redirects, dedicated finite timeout plus existing workflow/FFmpeg/Speech budgets, attempt-local temporary usage monitor and final quota check. Fresh isolated Python child with only OS-path/local temp/home/cache variables; pinned Deno/EJS without remote components or permission grants. Kill/wait process tree on timeout/cancellation before cleanup. Temp polling is not an OS disk quota and can briefly overshoot between samples. |
| Existing media reuse | Download audio only, then use N6's video strategy to probe measured duration, prepare audio and transcribe; retain Speech's measured-duration check and timed artifacts. Same media queue/worker, no Topic/extra queue or document/index changes. Blob/legacy paths and import isolation remain compatible. |
| Provenance/review | Transcript origin, review source and callback preserve original URL. Optional typed `review.youtube` records matching videoId/canonicalUrl and nullable available title (500-character cap); non-YouTube remains null. No signed CDN URLs/local paths or extra image/transcription inventory. |
| Publication/retry | Reuse N5 publisher unchanged. Check ready/complete before extraction; callback and partial-upload retries perform no second YouTube/FFmpeg/Speech work. Permanent safe policy/limit/unavailable errors fail explicitly; 429/5xx/network/incomplete-download/dependency failures remain transient, without definitive failed callback. |

### N7 exact checks and results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Every full/regression
pytest run uses these explicit opt-ins:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

| Exact check | Observed result |
| --- | --- |
| Baseline opt-ins plus `.venv\Scripts\python.exe -m pytest -q` | **645 passed, 18 skipped, 2 warnings in 48.25s**; no pre-existing failure. |
| `Test-Path -LiteralPath ".venv" && .venv\Scripts\python.exe -m pip install "yt-dlp==2025.11.12" "yt-dlp-ejs==0.3.1" "deno==2.5.6"` | Installed the three pinned packages successfully. Existing Docling/Azure pins untouched; no model downloads. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py -q --tb=short` before production changes | **RED: 13 failed, 4 passed, 33 errors in 6.18s**. Invalid individual URLs accepted, absent adapter/transport and unavailable runtime route. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py tests/unit/test_media_artifacts.py tests/unit/test_content_contracts.py tests/unit/test_worker_boundaries.py -q --tb=short` | Initially **1 failed, 311 passed in 27.75s**; harness incorrectly expected `remote_components=[]` after YoutubeDL normalizes it to a set. Corrected the assertion against installed behavior; same command then **325 passed in 28.65s**. |
| Same N7-only command after edge tests | **4 failed, 66 passed in 5.39s**. One real NAT64 guard gap; three harness setups supplied duplicate Speech keywords. Reject transition addresses and correct only fixture setup; then **70 passed in 8.30s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py -k "quick_download or real_offline" -q --tb=short` | **RED: 1 failed, 1 passed, 71 deselected in 3.70s**. Quick successful child escaped polling quota before the next sample; final usage check closes the race. Actual EJS lib/core evaluation in Deno passed. |
| Focused regression command below | **426 passed in 47.81s**, including guarded networking/extraction, media, storage/publication, contracts, worker and settlement regressions. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py -k "224.0.0.1 or ff02" -q --tb=short` | **RED: 2 failed, 73 deselected in 2.78s**. Python `is_global` alone permits multicast; explicitly reject multicast/reserved answers. |
| Final command below | **75 N7 tests passed in 8.84s**; **720 passed, 18 skipped, 2 warnings in 56.08s** overall. All 645 baseline cases retained (the old unsupported-until-N7 case now verifies explicit unavailable-source handling without source/Speech access). |
| Same final command: `pip check`, N0 probe, Deno version | No broken requirements; both pinned API/confidence/backend/Core reload/frozen section-UUID PASS lines. Actual **Deno 2.5.6 / V8 14.0.365.5-rusty / TypeScript 5.9.2**, Windows x86_64. |
| `git -c core.autocrlf=false diff --check`; `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for each of the 19 task files listed below; `git status --short --untracked-files=all` | No whitespace diagnostics across all task files, including untracked files. Inspected existing tracked diffs/file list; prior user/N0-N6 work preserved. |

Focused regression command:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py tests/unit/test_media_artifacts.py tests/unit/test_artifact_publication.py tests/unit/test_media_processors.py tests/unit/test_ffmpeg_service.py tests/unit/test_transcription.py tests/unit/test_worker_boundaries.py tests/unit/test_content_contracts.py tests/unit/test_consumer.py -q --tb=short
```

Final command (after the opt-ins above):

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py && .venv\Scripts\deno.exe --version
```

Runtime evidence: real pinned YoutubeDL/YouTube dispatch with mocked extraction
and in-process HTTPS fixtures; socket-resolution/connection traps prevent live
tests. Real EJS lib/core load and evaluate in real Deno with remote fetching and
permissions disabled. Actual local subprocesses verify controlled environment,
fixed output validation, time/temp limits, cancellation and descendant-writer
termination. Dedicated media composition/Speech HTTPX/FFmpeg strategies and N5
publication use existing local doubles; callback-only and ready-upload recovery
do not redownload/retranscribe. No live service called.

### N7 changed files, acceptance and next session

- New source under `src/akay_convert_to_markdown/`: `models/youtube.py`,
  `services/youtube_http.py`, `services/youtube_extractor.py`,
  `services/youtube_service.py`. New `tests/unit/test_youtube_source.py` and
  `docs/content-processing-youtube.md`.
- Updated `contracts/requests.py`, `contracts/artifacts.py`, `config/settings.py`,
  `media_main.py`, `processing/published_media_processor.py`,
  `processing/media_artifacts.py`; updated `tests/unit/test_media_artifacts.py`,
  `pyproject.toml`, README, contract/media/publication guides and this record.
  Specification/plan, document extraction, publisher, generic process runner,
  Docker/CI and unrelated files were not changed in N7.
- Local N7 acceptance is satisfied: source routing, unsafe URL/redirect/address,
  unavailable/private/unsupported/live result, timeout, hard audio-byte limit,
  metadata/temp budget, safe cleanup, stable source/review identity and completed
  package reuse all verified. No current local acceptance failure remains.
- **Missing external evidence:** actual YouTube website/player/challenge/CDN
  interoperability, real network TLS/DNS, codec decoding (FFmpeg/FFprobe absent),
  billable Speech and Azure. Real videos/services were not authorized and were
  not contacted. Linux process-group/isolated dependency/image checks remain
  N12-N13; CI/publication/deployment remain N14-N15. No three-image claim from
  optional dependency pins. N3 optical-quality limitations remain unchanged.
- Same 18 skips: 13 model opt-ins, 2 optical diagnostics, Azure Blob opt-in,
  missing FFmpeg/FFprobe, absent Speech configuration. Two warnings are the
  pre-existing upstream OCR serialization deprecations. No new skipped N7 test.
- Physical queues/storage/images/apps, credentials/identities and embeddings
  remain scoped inputs. No credentials discovered/reused, other repository or
  database modified, migration, commit, push, image publication or deployment.
- Rollback unit: the six new source/test/guide files plus the listed source,
  dependency and current-status documentation changes together, preserving
  N0-N6/user work. Revert only N7's small amendments to previously untracked files.
- **Next fresh session: N8 only**, dependent on completed N5-N7. Harden callbacks,
  settlement, stable outcomes, whole-workflow lock budgets and shutdown/lost-lock
  behavior. Do not proceed to indexing or another task in this session.

## N6 checkpoint — 2026-11-13 (preserved)

**N6: complete — local Blob media transcription/artifact/publication acceptance
verified. N0-N5 remain complete. Next fresh session: N7 only.**

### N6 task and prerequisite evidence

- Executed only N6, dependent on N2 and reusing N5 storage. Read applicable parent
  `../AGENTS.md`, current README, full authoritative specification/plan, every
  current/preserved checkpoint, the historical T0 record and N0 compatibility/
  frozen decisions. No repository-local AGENTS file exists. CodeGraph was present
  and used before implementation exploration; targeted reads filled omitted source.
- Verified actual N1 settings/entries, N2 typed media/transcript/review/events,
  N3 extraction/N4 exporter and N5 shared complete-set receipt/publication against
  recorded acceptance evidence. Reused all compatible work. Existing media entry
  still used the legacy Markdown-only processor; Speech discarded locale/speaker/
  duration and substituted zero for absent timings. No N6 producer existed.
- Baseline rerun: **580 passed, 18 skipped, 2 upstream warnings in 35.69s**.
  Initial tree already contained uncommitted N0-N5/user changes and untracked
  documents. All earlier progress and unrelated changes were preserved.

### N6 implementation and decisions

| Area | Verified behavior |
| --- | --- |
| Speech normalization | Retain phrase offsets/durations, per-phrase locale and speaker (including integer zero), measured total duration, and safe warnings. Pinned REST 2025-10-15 integer milliseconds validated strictly before conversion to the retained internal seconds API; round back without truncation in transcript JSON. No new SDK/model/locale or diarization feature selected. |
| Missing/invalid data | Unknown start/end/duration/language/speaker remain null. Calculate end only from available start plus duration. Reject negative/nonfinite/wrong-type measurements, malformed/empty responses, chronological regressions and boundaries beyond known duration with safe `SPEECH_TRANSCRIPTION_FAILED`. Actual zero and ordered overlapping speakers remain valid. |
| Canonical text | Use phrase text in both outputs, preserving order and trimming only outer whitespace. Combined-only content is retained untimed rather than discarded; differing combined/phrase text produces `SPEECH_COMBINED_TEXT_DIFFERS`. No generated chapters or invented word-level timing. |
| Artifacts | New local `export_media_artifacts` returns N2 `MediaArtifactResult`, writes exactly Markdown/transcript/review using `ArtifactLayout`, stable sequential segment IDs and original Blob provenance. Review contains measured duration, empty document inventories, null PDF/page measurements and engine/API version. Missing phrase boundaries produce `TRANSCRIPT_TIMESTAMPS_UNAVAILABLE`. |
| Strategy reuse | Existing audio/video strategies expose normalized `transcribe`, with legacy `to_markdown` delegating to it. Keep one probe, original media extension routing and audio-only WebM through existing FFmpeg copy/transcode commands. Audio without a track fails before Speech. Declared/actual download sizes, FFprobe and measured Speech duration limits are checked. |
| Runtime | Dedicated media entry selects `PublishedMediaProcessor`: strict version-one media parsing, legacy envelopes retained, no Docling/Qdrant imports. Unsupported document extensions and YouTube fail safely without source access/following URLs. YouTube retrieval remains N7. Mixed entry remains legacy. |
| Publication/settings | Reuse N5 publisher unchanged for exact Markdown/transcript/review sets and typed callbacks. Share its existing paired state settings/validator between dedicated document/media workers; absent values fail version-one Blob work transiently before source access. No inferred physical names/defaults. |
| Recovery/lifecycle | Complete/ready recovery retries callbacks/uploads after source removal without another Speech/FFmpeg call. Shared-parent stems remain independent. Move N3's existing drain primitive unchanged to `processing/blocking.py`, preserving its old import alias; media JSON writes run off-loop and keep files/lease until the thread stops under repeated cancellation. Broader N8 hardening was not implemented. |
| API evidence | Context7's exact HTTPX 0.28.1 transport/multipart documentation, Microsoft Learn Speech usage and versioned REST 2025-10-15 response definitions. Real installed HTTPX MockTransport exercises multipart/auth/version and real normalization; no Speech SDK migration or dependency installation/pin change. |

### N6 exact checks and results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. All test runs explicitly
disable Azure/model/quality opt-ins with the three assignments below.

| Exact check | Observed result |
| --- | --- |
| Baseline opt-ins plus `.venv\Scripts\python.exe -m pytest -q` | **580 passed, 18 skipped, 2 warnings in 35.69s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_media_artifacts.py -q --tb=short` before production changes | **RED: 50 failed, 2 passed, 7 errors in 11.93s**. Missing exporter; malformed/timing data accepted; media entry lacked version-one parsing/publication and ignored state settings. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_media_artifacts.py tests/unit/test_transcription.py tests/unit/test_media_processors.py tests/unit/test_markdown_builder.py tests/unit/test_worker_boundaries.py -q --tb=short` | **GREEN: 118 passed in 30.48s** after implementation; no intermediate implementation failure. |
| Focused regression command below, including added WebM wire/callback-order/transient/cancellation cases | **272 passed, 2 warnings in 67.80s**. |
| Final full regression/check command below | **645 passed, 18 skipped, 2 warnings in 73.64s**. All 580 baseline tests plus 65 N6 cases pass. `pip check`: no broken requirements. N0 probe: both PASS lines for pinned options/confidence/backend/Core references/reload/frozen UUID vectors. |
| `git -c core.autocrlf=false diff --check && git status --short --untracked-files=all` | No whitespace diagnostics; inspected complete changed-file list and preserved unrelated N0-N5/user work. |
| Per-file new/untracked whitespace command below | No diagnostics; includes all N6 new files and updated untracked implementation/guides/progress. |

Opt-ins (applied before every recorded pytest command):

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
```

Focused regression command:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_media_artifacts.py tests/unit/test_artifact_publication.py tests/unit/test_docling_conversion.py tests/unit/test_document_artifacts.py tests/unit/test_media_processors.py tests/unit/test_ffmpeg_service.py tests/unit/test_transcription.py tests/unit/test_markdown_builder.py tests/unit/test_worker_boundaries.py tests/unit/test_consumer.py -q --tb=short
```

Final full regression/check command:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

New/untracked whitespace check:

```powershell
git -c core.autocrlf=false diff --check; foreach ($path in @('src/akay_convert_to_markdown/processing/blocking.py', 'src/akay_convert_to_markdown/processing/media_artifacts.py', 'src/akay_convert_to_markdown/processing/published_media_processor.py', 'src/akay_convert_to_markdown/conversion/docling_converter.py', 'src/akay_convert_to_markdown/media_main.py', 'tests/unit/test_media_artifacts.py', 'docs/content-processing-media.md', 'docs/content-processing-publication.md', 'docs/content-processing-contracts.md', 'docs/content-processing-review.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }
```

Runtime harness: actual dedicated media composition/strict parser/consumer,
Speech HTTPX multipart client/response normalization, real strategy/Markdown/JSON
writer and N5 publisher with persistent conditional/leased local Blob doubles.
Sixteen extension variants verify routing, not codec decoding. Two additional
audio-only WebM cases use the actual FFmpeg adapter and fake subprocess runner to
verify `-map 0:a:0`, `-vn`, compatible copy and MP3 fallback, retaining original
provenance. Cancellation traps the actual JSON writer until explicit release,
proving no early lease/file cleanup or completed callback. No real service called.

### N6 changed files, acceptance and next session

- New source files under `src/akay_convert_to_markdown/processing/`:
  `media_artifacts.py`, `published_media_processor.py`, `blocking.py`.
- Updated `models/transcription.py`, `services/fast_transcription_service.py`,
  `services/markdown_builder.py`, `processing/audio_processor.py`,
  `processing/video_processor.py`, `config/settings.py`, `media_main.py` and the
  small helper relocation in `conversion/docling_converter.py`.
- New `tests/unit/test_media_artifacts.py`, `docs/content-processing-media.md`;
  updated README, contract/publication/review guides and this append-preserving record.
  Specification, plan, publisher implementation, dependencies, Docker/CI, existing
  tests and unrelated files were not changed by N6.
- Acceptance verified locally: preserved media routing/Speech/FFmpeg behavior,
  audio-only WebM, invalid/no-audio/declared-and-actual-size/duration/empty errors,
  nullable/strict temporal metadata and available locale/speaker, consistent text,
  exact media-only artifacts/callback refs, full set before notification,
  notification-only retry, partial-upload recovery, scoped cleanup/cancellation.
- No local N6 acceptance check is failing or blocked. **Missing external evidence**:
  actual FFmpeg/FFprobe decoding (executables unavailable on this host), authorized
  billable Speech/API interoperability, real Azure publication/replica expiry,
  isolated images/CI/deployment. Default tests deliberately use local doubles.
  The same 18 skips are 13 model opt-ins, 2 optical diagnostics, Azure Blob opt-in,
  absent FFmpeg/FFprobe and absent Speech configuration. Two warnings are the
  pre-existing upstream OCR serialization deprecations; N3 quality limits remain.
- Embedding settings, physical deployment/storage names/identities and production
  Speech locale policy remain scoped configuration inputs. No credentials or
  remote resources were discovered, no SDK/models downloaded, and no Docker/CI
  change is required until its assigned task. No other repository/database,
  migration, live service, commit, push, image publication or deployment.
- Rollback unit: the three new processing files, media test/guide and the listed
  strategy/model/parser/settings/entry/helper/doc changes together; restore the
  prior drain function in the converter if removing the shared helper. Preserve
  all earlier N0-N5/user work.
- **Next fresh session: N7 only**, dependent on completed N6. Add the explicit,
  bounded YouTube source adapter using the existing media artifacts/publication.
  Do not advance to N8 or indexing within this session.

## N5 checkpoint — 2026-11-13 (preserved)

**N5: complete — local complete-set publication, recovery and document-worker
integration acceptance verified. N0-N4 remain complete. Next fresh session: N6 only.**

### N5 task and prerequisite evidence

- Executed only N5, dependent on N4. Read applicable parent `../AGENTS.md`, current
  README, complete authoritative specification/plan, all current and historical
  progress, N0 frozen decisions and actual contracts, entry/settings, consumer,
  conversion/exporter, storage and webhook code. CodeGraph was checked first and
  used for source/impact exploration; targeted reads filled files it did not return.
- N0's compatibility/probe/coordination decisions, N1's isolated runtime boundaries,
  N2's strict contracts, N3's extraction and recorded offline inference evidence,
  and N4's real Core sections/review/reference tests substantiate completion. The
  initial storage code had only Markdown existence/reuse and single-file upload;
  no complete-set receipt/coordinator existed. Baseline rerun: **549 passed,
  18 skipped, 2 upstream warnings in 63.40s**; no pre-existing failure.
- Initial tree contained the earlier uncommitted N0-N4 implementation and user
  documents. Preserved that work and every previous checkpoint below. No dependency
  installation/pin change, model/cache discovery, service or credential access.

### N5 implementation and decisions

| Area | Verified behavior |
| --- | --- |
| Shared publisher | `BlobStorage.artifact_publisher` reuses its authenticated async client. `ArtifactPackage` is an exact local-file map reusable by N6, not another transcriber or generic framework. |
| Configuration | Dedicated document settings accept paired explicit `PUBLICATION_STATE_CONTAINER_NAME` / `PUBLICATION_STATE_PREFIX`. Partial/blank configuration fails validation. Neither configured: legacy behavior remains; valid version-one jobs fail transiently before source work. No physical values/defaults or provisioning inferred. |
| Coordination | Finite 60-second Blob leases, 20-second renewal plus guards; conditional receipt creation and leased ETag/If-Match state transitions. Technical receipt compares full exact target, source container/reference, contentKey/type and effective options; stores full canonical request snapshots and per-request notification outcome. |
| Namespace reservation | SHA-256 of compact Unicode JSON `[destinationContainer, artifactPrefix]` reserves the artifact namespace as well as the exact Markdown target stored in the receipt. This refines N0's exact-destination key to prevent `.md`/`.MD` same-stem sidecar collisions. Distinct stems in shared parents remain independent. |
| Fencing and recovery | Persist a draft's exact files/hashes/lengths, stage under a unique technical attempt, then freeze `ready` before any public write. Canonical files are create-only, byte-verified and owned by that ready attempt. A stale lease holder cannot overwrite a successor: it can at most finish identical frozen bytes. A receipt lease alone would not fence sidecars. |
| Complete-set proof | Store final ETags only after every canonical file is verified, then persist complete before callback. Reuse validates every recorded ETag/length; missing/changed published files fail safely. Neither an old Markdown nor writing Markdown last substitutes for the receipt. No public manifest/image inventory added. |
| Reuse/overwrite | Both overwrite modes reuse complete matching packages. Changed source/options/contentKey or an unowned legacy/sidecar output conflicts safely, even with overwrite; use another destination. No administrative rebinding/retirement or invisible replacement of accepted material. Source identity is its supplied container/reference, not automatic changed-original detection. |
| Drafts/cleanup | Interrupted drafts clean exact owned technical stage files and rebuild. Ready uploads resume without original/local files, including lost upload responses/complete-receipt failures. Complete stages are cleaned by metadata ownership and ETag; no canonical or broad consumer-prefix deletion. Killed in-flight drafts can leave unreferenced technical orphans; no unsafe sweeper added. |
| Document integration | Dedicated document entry supports strict version-one parsing and actual N3 extraction -> N4 export -> coordinated package -> typed callback, retaining its legacy envelopes. Consumer has a small optional processor parser hook; existing settlement/client behavior is reused. Mixed/media entries remain legacy; no N6 timed output/YouTube/indexing implemented. |
| Lifecycle | Existing inference/export draining retains local inputs and publisher ownership until the builder stops under repeated cancellation. Lease-loss/heartbeat failure cannot commit ready or send success. Whole-workflow Service Bus renewal budgets, transport lock loss and global shutdown hardening remain N8. |
| API verification | Context7/Microsoft Learn concurrency/lease guidance, official versioned async BlobClient source and installed `azure-storage-blob==12.24.1` signatures/docstrings. Real SDK + in-process HTTP transport verifies create-only, ETag/lease/metadata and renew/release headers; no network or live credentials. |

### N5 exact checks and results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. All regression runs
explicitly disable Azure, model and optical-quality opt-ins.

| Exact check | Observed result |
| --- | --- |
| Baseline opt-ins below with `.venv\Scripts\python.exe -m pytest -q` | **549 passed, 18 skipped, 2 warnings in 63.40s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_artifact_publication.py -q --tb=short` before production implementation | **RED: 19 setup errors in 2.30s**, absent `storage.artifact_publication`. |
| Same focused command after shared publisher | **19 passed in 2.11s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_artifact_publication.py -k "real_document_entry or partial_publication_configuration" -q --tb=short` before runtime/settings integration | **RED: 3 failed, 20 deselected in 5.86s**. Document consumer emitted the legacy invalid-message event instead of publishing; settings silently ignored incomplete state configuration. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_artifact_publication.py tests/unit/test_worker_boundaries.py tests/unit/test_docling_conversion.py tests/unit/test_consumer.py -q --tb=short` | **135 passed, 2 warnings in 33.20s**, after integration. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_artifact_publication.py -q --tb=short` after takeover/cancellation/crop/receipt-loss cases | **30 passed in 13.50s**, before adding the pinned SDK wire case. |
| Final focused/regression command below | **356 passed, 2 warnings in 30.53s**; **580 passed, 18 skipped, 2 warnings in 33.24s**. All 31 N5 cases and all 549 baseline tests pass. |
| Same final command: `pip check` and N0 probe | No broken requirements; both PASS lines for pinned APIs/backend/confidence/Core references/reload/frozen UUIDs. |
| Installed API command below | Blob SDK **12.24.1**; async upload/acquire/renew signatures observed; upload and download docstrings confirm lease/ETag/match conditions. |
| Final whitespace/status checks below | No whitespace diagnostics; full file list inspected, earlier user/implementation changes retained. |

Final focused/regression command:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_artifact_publication.py tests/unit/test_storage.py tests/unit/test_worker_boundaries.py tests/unit/test_content_contracts.py tests/unit/test_document_artifacts.py tests/unit/test_docling_conversion.py tests/unit/test_consumer.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

Installed API command:

```powershell
.venv\Scripts\python.exe -c "from importlib.metadata import version; import inspect; from azure.storage.blob.aio import BlobClient, BlobLeaseClient; print('azure-storage-blob:', version('azure-storage-blob')); print('upload:', inspect.signature(BlobClient.upload_blob)); print('lease:', inspect.signature(BlobClient.acquire_lease)); print('renew:', inspect.signature(BlobLeaseClient.renew)); print('upload documents lease/etag/match_condition:', all(term in inspect.getdoc(BlobClient.upload_blob) for term in ['lease', 'etag', 'match_condition'])); print('download documents etag/match_condition:', all(term in inspect.getdoc(BlobClient.download_blob) for term in ['etag', 'match_condition']))"
```

Final whitespace/status checks:

```powershell
git -c core.autocrlf=false diff --check; foreach ($path in @('src/akay_convert_to_markdown/storage/artifact_publication.py', 'src/akay_convert_to_markdown/processing/published_document_processor.py', 'src/akay_convert_to_markdown/document_main.py', 'tests/unit/test_artifact_publication.py', 'docs/content-processing-publication.md', 'docs/content-processing-contracts.md', 'docs/content-processing-docling.md', 'docs/content-processing-review.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }; git status --short --untracked-files=all
```

Harness corrections: the SDK transport double initially returned HTTP 201 for
renew/release instead of their 200 responses; then its assertion compared the
lease ID after `release()` had cleared it. Corrected only the double/status and
captured ID before release. The final 356/580 runs include the passing wire case;
these intermediate harness failures do not demonstrate a production defect.

### N5 changed files, acceptance and next session

- New `storage/artifact_publication.py`, `processing/published_document_processor.py`
  under `src/akay_convert_to_markdown/`; new `tests/unit/test_artifact_publication.py`
  and `docs/content-processing-publication.md`.
- Updated existing `storage/blob_storage.py`, `config/settings.py`,
  `document_main.py`, `messaging/service_bus_consumer.py`, README, contract/Docling/
  review guides and this progress record. Specification, plan, dependencies,
  Docker/CI and earlier implementations/checkpoints remain intact.
- Acceptance covered: full set before completion, midway upload/response/receipt
  recovery, shared parents and suffix namespace collision, destination contention,
  non-overwrite/overwrite reuse and incompatible conflicts, notification-only retry,
  lease loss/takeover/heartbeat failure, safe exact cleanup, real crop bytes and JSON
  reload with usable refs. Real dedicated entry + consumer retries successfully
  after deleting the source from the double; no second extraction is possible.
- No local N5 acceptance check remains failing or blocked. **External evidence is
  pending**: authorized Azure/emulator interoperability, actual cross-process
  crash/expiry, physical technical storage/RBAC, images/CI/deployment. No real
  storage resource was supplied/probed or created. Thirty-one tests use persistent
  local doubles/fixtures and a no-network real SDK transport, not a live cluster.
- Same 18 default skips: thirteen model integration opt-ins, two separate optical
  diagnostics, Azure Blob opt-in, unavailable FFmpeg/FFprobe and Speech configuration.
  The two warnings are the existing upstream OCR serialization deprecations.
  N3's measured OCR limitations remain unchanged; no model rerun was needed.
- **Next fresh session: N6 only**, dependent on N2 and N5's shared publication
  boundary. Preserve Speech/FFmpeg, produce validated timed transcript/review and
  consistent Markdown, and reuse this publisher. No N7/N8/N9+ implementation here.
- Rollback unit: these new publisher/processor/tests/guide files plus the small
  document settings/entry/parser/storage integration and current-status doc edits.
  Preserve earlier N0-N4/user work. No commits, push, image publication, deployment,
  other repository, database, migration, live-service call or ambient credentials.

## N4 checkpoint — 2026-11-13 (preserved)

**N4: complete — local principal sections, review metadata and portable artifact
generation verified. N0-N3 remain complete. Next fresh session: N5 only.**

### N4 task and prerequisites

- Executed only N4, dependent on N3. Read parent `../AGENTS.md`, current README,
  authoritative specification, full N0-N16 plan, all preserved progress, N0's
  frozen decisions and relevant Docling/contracts/runtime code via CodeGraph.
  No repository-local AGENTS file exists. N0's baseline/probe, actual N1 isolated
  entries/settings, N2 strict schemas and N3 adapter/recorded real offline evidence
  substantiate their completion; N4's generator was absent initially.
- Initial working tree contained all earlier uncommitted N0-N3 implementation
  and user documents. Preserved those bytes except the small current-status
  updates listed below; no previous checkpoint was removed. Baseline rerun:
  **519 passed, 18 skipped, 2 upstream warnings in 29.85s**.
- Reused installed Docling 2.141.0/Core 2.99.0 and N0's fixed section namespace.
  Consulted Context7 and official versioned serializer/confidence documentation,
  comparing the installed Core heading/image/traversal/export and Docling
  confidence/grade APIs. No dependency installation or pin change.

### N4 implementation and decisions

| Area | Verified behavior |
| --- | --- |
| Local API | `export_document_artifacts(extraction, request, fresh_directory)` returns N2 `DocumentArtifactResult` and writes Markdown, full Docling JSON, review and actual crop PNGs. Fresh directory represents the destination's parent; full Blob references come from existing `ArtifactLayout`. No Blob publication/runtime activation in N4. |
| Section identity | Single `section_id` function uses N0's namespace `bdac804b-e605-5299-872e-42443fecc0c9` and compact Unicode JSON `["section-v1", contentKey, doclingItemRef]`. All three frozen vectors pass; request ID/title do not affect IDs. |
| Markers/hierarchy | Override Core's documented heading-format extension point, not textual replacements. Emit markers and review mappings together only for `extractSections=true`. Preserve zero-based order, refs, available page and preceding lower-level parent. Core TitleItem maps to level 1; section-header native level maps to rendered level + 1. Gaps, repeats and inline heading text are supported. |
| Additional/general content | Additional documents keep internal headings with empty sections/no generated markers. No synthetic preamble section. Page headers/footers, furniture and rich table-cell headings are excluded from sections. Media remains governed by existing empty-section contracts. |
| Review | Statistical counts, table cell dictionaries/captions/provenance and available crop refs; image inventory only in review; retained extraction warnings and actual engine version. Missing table title stays null. No LLM or semantic taxonomy. |
| Confidence | Read `ConversionResult.confidence`; retain finite component and native aggregate values/grades, including flat overrides. Use pinned `_score_to_grade` because no public per-component grade properties exist. Null for missing/NaN/Infinity; real zero preserved. No calibrated-probability claim. |
| References/safety | Copy document; remove page-image/private origin/local hyperlink references. Export data-image crops with fixed generated filenames, not source-controlled paths. Never resolve source image URIs. JSON sidecar uses `images/...`; Markdown uses encoded `<destination-stem>.artifacts/images/...`, including literal percent signs. Original structured extraction is unchanged. Core reload validates without opening image refs. |
| Lifecycle/errors | Refuse occupied output directories. Safe export failures/partial results cannot produce review success; caller owns incomplete local attempts. Reuse N3's executor draining so cancellation cannot release ownership while the local writer continues. N5 owns durable publication/cleanup. |

### N4 exact checks and results

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. Default regression
explicitly sets Azure/model/optical-quality opt-ins to `false`.

| Exact check | Observed result |
| --- | --- |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; .venv\Scripts\python.exe -m pytest -q` (baseline) | **519 passed, 18 skipped, 2 upstream warnings in 29.85s**. |
| Same opt-ins, `.venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py -q --tb=short` before production implementation | **RED: 21 setup errors in 11.95s**, missing `conversion.document_artifacts`. |
| Same focused command after initial implementation | **1 failed, 20 passed, 2 warnings in 10.88s**: Core included body-layer page-header/footer labels. Warnings came from the test reading raw empty upstream aggregates; final test compares finite native values instead. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py -k "nested_repeated or literal_destination or spoof" -q --tb=short` before fixes | **RED: 2 failed, 3 passed, 20 deselected in 8.11s**. Body header/footer filtering and literal `%20` destination links failed. Explicit label exclusion and URI encoding fix these cases. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py -q --tb=short` after those fixes | **25 passed in 12.82s**. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py -k "inline_heading or windows_drive or incomplete_result" -q --tb=short` before final edge fixes | **RED: 2 failed, 3 passed, 25 deselected in 8.13s**. Inline-representation heading had empty native text; Windows-drive hyperlink was parsed as URL scheme `c`. Fallback to rendered inline heading text and explicit drive-scheme stripping fix them. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py -q --tb=short` | **30 passed in 16.66s**, no warnings. |
| Final focused/regression command below | **271 passed, 2 warnings in 31.99s**; then **549 passed, 18 skipped, 2 warnings in 34.90s**. Includes all 519 baseline tests. |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found. |
| `.venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | Both PASS lines: pinned options/confidence/backend/reference/reload and all frozen section UUID vectors. No inference or services. |
| Whitespace/status command below; `git -c core.autocrlf=false diff -- README.md`; final CodeGraph exploration of the new exporter | No whitespace diagnostics. Reviewed generator/source, README status changes and complete working-tree file list; prior user/N0-N3 files retained. |

Final focused/regression command:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py tests/unit/test_docling_conversion.py tests/unit/test_content_contracts.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py
```

Whitespace/status command (checks untracked task files as well as tracked diffs):

```powershell
git -c core.autocrlf=false diff --check; foreach ($path in @('src/akay_convert_to_markdown/conversion/document_artifacts.py', 'tests/unit/test_document_artifacts.py', 'docs/content-processing-review.md', 'docs/content-processing-docling.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }; git status --short --untracked-files=all
```

Runtime-boundary harness: actual HTML extraction -> N4 local package -> strict
review parse/Core document reload, with real PNG save/links and local fixtures.
This is not a Service Bus/Blob success path. N3 extraction and N1 worker-boundary
regressions pass; N4 writer cancellation is exercised independently.

### N4 changed files, acceptance and handoff

- New `src/akay_convert_to_markdown/conversion/document_artifacts.py` and
  `tests/unit/test_document_artifacts.py`; new
  `docs/content-processing-review.md`; updated README, Docling guide and this
  progress record. No authoritative specification/plan changes were needed.
- Acceptance verified: nested/repeated/idempotent markers and matching review
  mappings; additional documents/preamble; missing/nonfinite confidence; real
  referenced crops, safe JSON reload and original-object preservation. N4 is
  complete on this local boundary. No unverified N4 acceptance check remains.
- Same 18 default skips: thirteen opt-in model integration cases, two separate
  OCR-quality diagnostics and the original Azure Blob/FFmpeg/Speech omissions.
  Existing Spanish OCR-quality failures remain engine limitations; six other
  languages' optical quality is still unmeasured. No model rerun/download was
  needed for this serialization-only task. Two warnings are the existing upstream
  `force_full_page_ocr` deprecations, not N4 warnings.
- **Next fresh session: N5 only**, dependent on completed N4. Reuse this generator
  and existing layout/contracts for Blob coordination, coherent complete-set
  publication/reuse, conflict/race/recovery and callback-only retry tests. Keep
  version-one queue jobs fail-closed until that path is implemented.
- Embedding provider/model/tokenizer, deployment names/credentials and cloud
  checks remain inputs to later tasks; none blocks local N4. Docker/CI changes
  are not required for this task. No other repository/database/migration, live
  services, ambient credential discovery, commit, push, publication or deployment.
- Rollback unit: the new generator/tests/guide and N4 current-status documentation
  updates together; earlier N0-N3/user work remains independently reusable.

## N3 scope-correction checkpoint — 2026-11-13 (preserved)

**N3: complete for the user-clarified Docling integration scope. N0-N2 remain
complete. Next fresh session: N4 — principal sections and review metadata.**

### Scope correction and acceptance

- The user explicitly clarified that ConvertToMarkdown must be able to call
  Docling; repairing Docling/OCR recognition is outside this task. The earlier
  agent-imposed character-perfect Spanish OCR gate was an overreach. Updated
  specification section 6.2 and the N3 plan to make that boundary explicit.
- N3 acceptance covers the existing adapter/runtime integration, selected language
  and feature options, actual local engine invocation, retained returned content,
  structured results/confidence, export/reload, safe empty/partial/failure handling,
  resource boundaries and cancellation-safe inference. Previous model-free,
  worker-boundary and four real PDF/enrichment results below remain applicable.
- Added normal/corrupt-overlay Spanish raster integration cases: OCR recognizes
  actual raster content, Markdown exports, JSON reload preserves **the engine's
  returned text unchanged**, confidence is available and page image references
  are absent. No OCR postprocessing, retraining, model replacement, library patch
  or dependency/runtime change was made for this scope correction.
- Strict Spanish accent-fidelity assertions are retained as two explicit
  `RUN_DOCLING_QUALITY_DIAGNOSTICS=true` diagnostics, requiring local-model opt-in
  too. Their previously observed failures remain documented, not fixed or claimed
  passing. They are outside integration acceptance. Quality in eu/gl/ca/fr/en/de
  remains unmeasured; all seven resource selections initialize successfully.

### Verification after the correction

Commands from `C:\Develop\Akay\Akay.ConvertToMarkdown` in PowerShell:

| Exact check | Observed result |
| --- | --- |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "true"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; $env:DOCLING_TEST_ARTIFACTS_PATH = "$PWD\.local\docling-n3\models"; .venv\Scripts\python.exe -m pytest tests/integration/test_docling_models.py -k "not local_pdf_inference" -q --tb=short` | **9 passed, 2 skipped, 4 deselected, 17 upstream warnings in 64.39s**. Actual offline seven-language initialization and two raster/overlay integration cases pass. Two quality diagnostics explicitly disabled; four unchanged code/formula cases use their prior **4 passed in 880.09s** evidence rather than an unnecessary rerun. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; $env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"; .venv\Scripts\python.exe -m pytest -q` | **519 passed, 18 skipped, 2 upstream warnings in 41.67s**. All current default regressions pass. |
| `git -c core.autocrlf=false diff --check`; per-file `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for the six changed untracked test/doc files; `git status --short` | No whitespace diagnostics; existing working-tree changes preserved. |

Default omissions are thirteen opt-in model integration cases, two separate
optical-quality diagnostics and the original three external integration omissions
(Azure Blob disabled, FFmpeg/FFprobe absent, Speech configuration absent). The
actual-model evidence is from separate runs, not a claim that the default suite
ran inference. The quality diagnostics were not rerun after this classification;
their known accent failures remain in the preserved checkpoint below. No
production behavior changed here, so no artificial production RED/GREEN is claimed.

### Files changed, remaining limits and next task

- This correction changes only `tests/integration/test_docling_models.py`,
  `README.md`, `docs/content-processing-specification.md`,
  `docs/docling-rag-implementation-plan.md`, `docs/content-processing-contracts.md`,
  `docs/content-processing-docling.md` and this progress record. Earlier N0-N3 and
  user working-tree changes are preserved. No model downloads or live services.
- Existing known OCR imperfections are engine/fixture observations, not a pending
  requirement to improve recognition. Do not reintroduce that expanded scope.
- Version-one runtime jobs still fail closed until N4/N5 sections/review/coherent
  publication exist. N3 completion is not full-pipeline publication or deployment.
  Linux/image/cloud checks remain with their later tasks; N12-N13 were not run.
- **Next: N4 only in a fresh session.** Reuse this adapter, the amended N2
  `ocrLanguage` contract, N0's frozen section-ID decision and all passing evidence.
  No N4 code, commit, push, publication, database change or deployment in this session.

## OCR-language/model-verification checkpoint — 2026-11-13 (preserved)

**N2 OCR-language amendment: complete. N3: in progress — models available,
real Spanish scanned-OCR fidelity still fails. Next session: continue N3 only.**
The earlier missing-assets blocker is resolved for the inspected configuration.
Do not advance to N4 from passing contract/resource checks alone.

### Completed amendment and scope

- Reopened only the user-requested N2 slice: optional `documentOptions.ocrLanguage`
  accepts exactly es/eu/gl/ca/fr/en/de, defaults to es when omitted, rejects
  null/empty/whitespace/wrong-type/unsupported values, and enters the canonical
  effective request identity. No other contract/ordering behavior was replaced.
- N3 forwards exactly one `iso:<language>` value to real pinned RapidOCR options.
  Removed the global language setting/constructor wiring so it cannot override
  a request; legacy Markdown-only conversion uses the new es default. Dedicated
  entries retain their existing isolation and still reject version-one runtime
  jobs until sections/review/publication exist. No premature artifact success.
- Updated the authoritative specification, implementation plan, README and both
  contract/Docling guides. N12-N13 requirements now include local resources for
  all seven selections, deduplicated shared weights, offline/non-root verification
  and explicit quality omissions. **N12/N13 were not executed.**
- Source/tests/docs remain in ConvertToMarkdown. Previous checkpoints and all
  pre-existing uncommitted/user work are preserved. No migration, other repository,
  credentials, live service, reinstall, download, commit, push, publication or
  deployment. Public versioned documentation was consulted for API verification.

### Local models: observed compatibility and real verification

- Read-only inspection of the explicitly authorized HF cache found compatible
  layout, v2.3.0 TableFormer and CodeFormulaV2 snapshots; exact IDs remain in the
  restart handoff below and the [Docling guide](content-processing-docling.md).
  No project model-path environment override was configured. Repository
  `.venv-docling` and the default user Docling cache were absent; existing `.venv`
  already had the pinned versions.
- Audited and copied **19 necessary files**, excluding fast tables and unrelated
  SmolVLM, into `.local/docling-n3/models`. Original cache snapshots are unchanged.
  The HF hub root was not passed as `artifacts_path`. The helper refuses divergent
  existing target files and verifies hashes after copying.
- The three reused ONNX weights match RapidOCR 3.10.0 registry SHA-256. All 19
  local hashes/source paths/snapshot identities are in the ignored local technical
  `local-verification-audit.json`; this is not a consumer/public manifest. HF
  identities were checked locally, without claiming an online revision lookup.
- Actual registry resolution preserves each chosen language code and maps all
  seven to the same multilingual PP-OCRv6 det/rec files plus OCR orientation
  classification. This is not a substituted language or Docling picture
  classification. All seven actual OCR model initializations pass without network.
- Four actual native-Spanish PDF/code/formula combinations pass with headings,
  accurate table content, figure PNG/link export, JSON reload and absent page
  image references. Enabled formula yields LaTeX and enabled code restores line
  breaks. These checks do not certify code syntax or calibrated extraction quality.
- **Real Spanish raster-only OCR fails strict accent fidelity**: outputs include
  `fotosūntesis`, `energa`, `diøxido`, `oxøgeno`. The controlled corrupt-text-overlay
  variant has the same fidelity failure. Assertions remain failing; no replacement
  heuristic, silent language fallback, xfail or relaxed quality assertion was added.
- `eu/gl/ca/fr/en/de`: local resource initialization verified; real OCR quality
  **not tested** for each of these six languages. Spanish quality is **tested and
  failing**, not untested or blocked by missing weights. No required resource was
  missing for these checks, so there is no download command to approve.

### Exact checks and results in this amendment

PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`. The selected model tests
use `RUN_DOCLING_MODEL_TESTS=true` and
`DOCLING_TEST_ARTIFACTS_PATH="$PWD\.local\docling-n3\models"`; requests/socket
access is blocked and HF/Transformers offline mode is enabled within tests.

| Exact check | Observed result |
| --- | --- |
| Contract/mapping RED command in the preserved restart handoff | **27 failed, 11 passed, 165 deselected in 21.99s**, before production changes. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_contracts.py tests/unit/test_docling_conversion.py tests/unit/test_worker_boundaries.py -q --tb=short` | **241 passed, 2 warnings in 68.07s** after the contract/mapping changes. Includes opaque forwarding, strict validation, independent flags and worker regressions. These are not OCR quality checks. |
| `Test-Path -LiteralPath "." && .venv\Scripts\python.exe docs/checks/content_processing_n3_models.py --hf-cache "C:\Users\alvaro.caballero\.cache\huggingface\hub" --rapidocr-models ".venv\Lib\site-packages\rapidocr\models" --stage ".local\docling-n3\models"` | Initial 120s invocation timed out; same command with 600s timeout succeeded. 19 files audited/staged, three registry hashes matched, resources resolved for all seven selections. No network/download function used. |
| `.venv\Scripts\python.exe -m pytest tests/integration/test_docling_models.py::test_local_spanish_scanned_pdf_ocr -q --tb=short` | **1 failed, 5 warnings in 78.97s**: actual Spanish accent corruption; model loading/extraction/export ran offline. |
| `.venv\Scripts\python.exe -m pytest tests/integration/test_docling_models.py -q --tb=short` (initial full model attempt) | Harness terminated at **600s**, after seven resource passes and four failures printed. Not a completed suite. Initial structured-fixture assertion incorrectly required decoded formula text when disabled and literal contiguous `mc` in LaTeX. Corrected only those capability/format expectations before final four-case run; Spanish quality assertions unchanged. |
| `.venv\Scripts\python.exe -m pytest "tests/integration/test_docling_models.py::test_local_pdf_inference[False-False]" -q --tb=short` (diagnostic before assertion correction) | **1 failed, 5 warnings in 31.42s**, because formula-disabled output is the upstream `formula-not-decoded` placeholder. Exported native headings/table/code/figure were inspected. |
| `.venv\Scripts\python.exe -m pytest tests/integration/test_docling_models.py::test_local_ocr_resources_initialize_for_selected_language tests/integration/test_docling_models.py::test_local_broken_text_layer_behavior -q --tb=short` | **7 passed, 1 failed, 12 warnings in 34.01s**. All seven actual model initializations pass; broken-layer Spanish test fails accent fidelity. |
| `.venv\Scripts\python.exe -m pytest tests/integration/test_docling_models.py::test_local_pdf_inference -q --tb=short --durations=4` | **4 passed, 23 warnings in 880.09s**. Calls: 44.69s neither flag; 234.84s code; 215.98s formula; 384.27s both. No network or native crash diagnostics. No assertion for the two failing OCR-quality cases was weakened. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; .venv\Scripts\python.exe -m pytest -q && .venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | Final default regression: **519 passed, 16 skipped, 2 warnings in 38.87s**; no broken requirements; pinned API/backend/confidence/Core reload/UUID probes pass. Includes the later test guard against retired global language overriding request selection. |
| `git -c core.autocrlf=false diff --check`; `git check-ignore ".local/docling-n3/models/local-verification-audit.json"`; per-file `git -c core.autocrlf=false diff --no-index --check -- NUL <path>` for every new/untracked file in the amendment | Passed, no whitespace diagnostics; generated local model/audit directory is ignored. |

Sixteen default skips: thirteen explicitly opt-in model cases, original disabled
Azure Blob case, missing FFmpeg/FFprobe, and missing Speech configuration. The model
suite was tested separately as above; default skips do not hide its two known
failures. Warnings are upstream OCR serialization/deprecated font-path access and
Transformers rope configuration. No dependency pins changed in this amendment.

### Changed files and next work

- Contract/runtime: `contracts/requests.py`, `conversion/docling_converter.py`,
  `config/docling_settings.py`, `document_main.py`, `main.py` under
  `src/akay_convert_to_markdown/`.
- Tests: `tests/fixtures/content_processing/contracts.json`,
  `tests/unit/test_content_contracts.py`, `tests/unit/test_docling_conversion.py`,
  `tests/docling_fixtures.py`, `tests/integration/test_docling_models.py`.
- Docs/config: README, specification, plan, contract/Docling guides, this record,
  `docs/checks/content_processing_n3_models.py`, `.gitignore` (only the generated
  local verification directory). Reused models/technical audit are ignored, not
  committed or published. No CI/container implementation in this amendment.
- **Next fresh session: N3**, diagnose Spanish accent fidelity with representative
  controlled scans and record the engine/fixture limitation. Keep the two failing
  opt-in checks visible; do not declare N3 complete or start N4. Preserve existing
  passing extraction/cancellation/format behavior. Record any quality not verified
  per language; further downloads require command/destination disclosure first.
- Rollback unit: the OCR-language contract/default and N3 mapping/global-setting
  removal, affected tests/fixtures/docs and local audit helper together. Preserve
  the pre-existing N0-N3 implementation, older checkpoints and user documents.

## Restart handoff checkpoint — 2026-11-13 (preserved)

**Interrupted by user for computer restart. N2 OCR-language amendment is implemented
and focused tests pass; N3 remains in progress. Resume this checkpoint first.**

### Restart handoff: selectable OCR and authorized cache inspection

- User authorized inspection of `C:\Users\alvaro.caballero\.cache\huggingface\hub`
  and configured model paths. Do not reinstall Docling or download missing assets
  without first reporting the exact command and destination. Immediate real OCR
  verification must use Spanish. No models were downloaded, copied or staged in
  this continuation, and no real-model inference has run yet.
- Updated the authoritative specification and plan (including future N12-N13
  requirements only) for `documentOptions.ocrLanguage`: es/eu/gl/ca/fr/en/de,
  default es when omitted, strict rejection of null/empty/unsupported/wrong-type
  values, one selection per conversion, document OCR only. No later task executed.
- Added the strict Literal field/default in `contracts/requests.py`, the fixture
  field and round-trip/default/invalid-value/effective-identity tests. N3 maps the
  request to exactly one `iso:<language>` entry in pinned RapidOCR options.
  Removed the old global OCR-language constructor/settings/wiring so it cannot
  override request selection. Legacy Markdown-only conversion uses default es;
  version-one runtime jobs still fail closed until N4/N5 publication exists.
- Changed files in this interrupted continuation: `docs/content-processing-specification.md`,
  `docs/docling-rag-implementation-plan.md`, `tests/fixtures/content_processing/contracts.json`,
  `tests/unit/test_content_contracts.py`, `tests/unit/test_docling_conversion.py`,
  `src/akay_convert_to_markdown/contracts/requests.py`,
  `src/akay_convert_to_markdown/conversion/docling_converter.py`,
  `src/akay_convert_to_markdown/config/docling_settings.py`,
  `src/akay_convert_to_markdown/document_main.py`, `src/akay_convert_to_markdown/main.py`
  and this progress record. All earlier uncommitted/user work retained.

### Observed checks before interruption

| Exact check | Result |
| --- | --- |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_content_contracts.py tests/unit/test_docling_conversion.py -k "ocr_language or ocr_selection or document_flags or empty_document_options or pinned_pdf_configuration" -q --tb=short` | RED before production edits: **27 failed, 11 passed, 165 deselected in 21.99s**. Missing contract field/default and old required global language argument. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_content_contracts.py tests/unit/test_docling_conversion.py tests/unit/test_worker_boundaries.py -q --tb=short` | GREEN: **241 passed, 2 upstream deprecation warnings in 68.07s**. Uses real pinned option/resolver APIs, but OCR execution in these tests is mocked; not real OCR quality evidence. |

Actual installed pins remain Docling 2.141.0, Core 2.99.0, parser 7.26.0,
RapidOCR 3.10.0, ONNX Runtime 1.20.1. No project `DOCLING_*` model/language or
HF cache environment overrides were set in this process. `.venv-docling` is
absent under this repository; the project uses `.venv`. The standard
`C:\Users\alvaro.caballero\.cache\docling` directory is absent.

### Authorized artifacts found (compatibility inspection, not inference)

- HF layout `docling-project/docling-layout-heron`, cached main snapshot
  `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`: config, processor and safetensors present.
  Matches the default layout repository used by pinned PDF options.
- HF tables `docling-project/docling-models`, cached `v2.3.0` snapshot
  `fc0f2d45e2218ea24bce5045f58a389aed16dc23`: accurate/fast TableFormer configs and
  safetensors present. Pinned TableStructureModel expects this repo/revision;
  only accurate resources are needed for the configured path.
- HF `docling-project/CodeFormulaV2`, cached main snapshot
  `ecedbe111d15c2dc60bfd4a823cbe80127b58af4`: model/processor/tokenizer assets present.
  This is the pinned code/formula adapter's expected repo, not picture description.
- A SmolVLM snapshot also exists in the cache; it is unrelated and must not be
  included for picture description/classification or ASR.
- `.venv/Lib/site-packages/rapidocr/models/` contains
  `PP-OCRv6_det_small.onnx`, `ch_ppocr_mobile_v2.0_cls_mobile.onnx` and
  `PP-OCRv6_rec_small.onnx`. The real pinned `_resolve_rapidocr` and
  `_rapidocr_artifacts` registry resolves each `iso:es/eu/gl/ca/fr/en/de` to its
  own language code and PP-OCRv6, with **the same three file URLs** across all
  seven selections. Shared multilingual weights are upstream behavior, not a
  language substitution. Registry inspection involved no network/inference.
- RapidOCR registry expected SHA256 observed for det-small:
  `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`;
  rec-small: `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`.
  Local weight checksums/ONNX initialization remain to be verified.
- The HF hub root is NOT the expected bundle layout. Pinned loaders expect
  `docling-project--docling-layout-heron/`,
  `docling-project--docling-models/model_artifacts/tableformer/accurate/`,
  `docling-project--CodeFormulaV2/` and `RapidOcr/` below `artifacts_path`.
  Stage only the required existing files into a separate explicit verification
  bundle; do not mutate cache snapshots or point directly at the hub root.

### Resume next (not yet verified/completed)

1. Finish audit/checksums and assemble the explicit offline verification bundle
   from authorized existing files. No audit/staging script has been created yet.
   If anything is missing, report exact download command/destination first.
2. Update `tests/integration/test_docling_models.py` to use request language
   instead of removed constructor/global argument; its existing four opt-in cases
   are currently stale but disabled. Add/run controlled scanned Spanish OCR and
   remaining N3 PDF/table/figure/enrichment/broken-layer checks with network blocked.
3. Update README, `docs/content-processing-contracts.md` and
   `docs/content-processing-docling.md`: they still describe the previous global
   language configuration. Remove stale setup guidance, document per-request
   selection and shared model resources, and distinguish availability from quality.
4. Run full regression and whitespace checks after the remaining changes. Record
   any real-model failures honestly and each unverified language's quality.
5. Close only the affected N2 amendment once documentation/tests are coherent;
   N3 remains incomplete until its acceptance is demonstrated. Do not start N4.

## N3 verification continuation checkpoint — 2026-11-13 (preserved)

**N3: in progress — blocked on explicit local inference assets/language.**
This continuation revalidated the existing implementation; it does not complete
N3 or authorize N4. **Next fresh session: continue N3 only.**

### Continuation scope and decision

- Read applicable parent instructions, README, the authoritative specification,
  implementation plan, N0 baseline, Docling guide and all preserved checkpoints.
  Inspected actual settings/entry boundaries, typed request contracts, extraction
  adapter and local/unit inference tests using CodeGraph and targeted reads.
- N0-N2's implementation and recorded verification remain compatible. The first
  incomplete task is N3, dependent on N2; reuse its existing adapter and tests.
  Initial working tree contains uncommitted N1-N3 work and user documents; retain
  every prior change and checkpoint.
- The remaining acceptance requires real PDF/scanned/broken-layer/table/figure
  and code/formula inference, not another option-model or mock-only check. The
  existing four opt-in checks use a basic text PDF and cannot alone certify that
  matrix. No explicit local asset directory or OCR language was supplied in this
  request. Ask for that input before inference; do not inspect ambient caches,
  download weights or choose a production OCR language.
- Rechecked official Docling **v2.141.0** documentation through Context7: local
  `artifacts_path` and independent code/formula flags agree with the existing
  pinned adapter. No dependency, runtime, fixture, Docker or CI change is needed
  merely to restate this configuration blocker.

### Continuation verification

PowerShell commands from `C:\Develop\Akay\Akay.ConvertToMarkdown`:

| Exact check | Observed result |
| --- | --- |
| `git status --short`; `git rev-parse --show-toplevel`; `Test-Path -LiteralPath "C:\Develop\Akay\Akay.ConvertToMarkdown\.codegraph"` | Correct repository; CodeGraph present; existing modified/untracked work preserved. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; .venv\Scripts\python.exe -m pytest -q` | **493 passed, 7 skipped, 2 warnings in 35.44s**. No failures or native diagnostics. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | No broken requirements; pinned options/confidence/backend/reference/reload and section UUID probes pass. No inference or services. |
| `git -c core.autocrlf=false diff --no-index --check -- NUL "docs/docling-rag-progress.md"`; `git status --short` | No whitespace diagnostics; existing modified/untracked file set retained. |

The seven skips are four explicitly disabled local-model checks, one disabled
Azure Blob check, missing FFmpeg/FFprobe and missing Speech configuration. The
two warnings are upstream serialization deprecations for `force_full_page_ocr`.
No model-backed PDF inference was attempted; no missing evidence is credited as
passing. RED/GREEN is not applicable to this documentation-only continuation.

Changed file: **`docs/docling-rag-progress.md` only** in this continuation.
Pending: obtain explicit reproducible local assets (including OCR and the
code/formula assets for enabled flags) and their OCR language; extend/run the
controlled inference fixture matrix and record available asset identities and
measured results. N4 remains dependent on N3 completion. Embedding/deployment
configuration is unrelated to this blocker. No other repository, database,
credentials, live service, commit, push, publication or deployment was used.

## N3 implementation checkpoint — 2026-11-13 (preserved)

**N3: in progress — extraction implemented; model-backed PDF acceptance pending.**
N0-N2 remain complete. **Next fresh session: finish N3 verification before N4.**
The document and mixed entries now use Docling for their existing Markdown-only
contract. Rich local extraction/referenced export is available, but version-one
runtime jobs still fail closed until sections/review/publication exist.

### N3 scope and prerequisites

- Executed **N3 only**, dependent on N2. Read parent `../AGENTS.md` (no repository
  AGENTS file), current README, complete specification/plan, all current progress
  checkpoints, N0 baseline/historical dependency probes and actual N1/N2 code.
  CodeGraph was present and used before code exploration. Initial git state
  contained uncommitted N1/N2 work and user `docs/`; all prior work/history remains.
- N0's compatibility map, pinned probes and decisions satisfy its documentation
  exit. N1's actual entry/settings/dispatch boundaries and N2's actual typed
  contracts/builders/legacy downgrade guard agree with their verification records.
  Baseline regression rerun: **456 passed, 3 skipped in 23.79s**.
- No N4 section/review producer, N5 Blob publication, N6 media rewrite, database,
  other repository, Docker or CI changes. No live services, model/cache discovery,
  weight downloads, credentials, push, publication, resource creation or deployment.
  Public documentation/package retrieval was used for pinned API verification.

### N3 implementation and decisions

| Area | Observed implementation |
| --- | --- |
| Adapter and entry points | `DoclingDocumentConverter.convert(Path) -> str` replaces MarkItDown wiring in document and mixed entries. Existing processor/storage/callback contract retained. Old MarkItDown module/tests/dependency kept for N12 removal, not a fallback. Media/index startup isolation still passes. |
| Rich local extraction | `extract(Path, DocumentOptions)` retains full upstream ConversionResult/document/confidence and typed warnings. No domain/payload interpretation, review producer, section IDs or automatic index job. |
| Pinned PDF configuration | Standard/docling_parse, CPU, RapidOCR/ONNX PDF-aware regions, accurate tables, heading hierarchy/parsed pages, picture crops; no page-image export, picture classification/description, chart extraction, remote services or external plugins. All four independent code/formula option combinations verified against real pinned option models. |
| Formats/resources | Real DOCX/PPTX/HTML/HTM/TXT/MD fixtures preserve native content/headings/tables. HTML preamble stays in body; HTML/MD fetch controls disabled. Restrict each instance to the extension's InputFormat: Docling otherwise sniffs a renamed PDF in `.md`, bypassing the PDF asset guard. No speculative parser or MarkItDown fallback. |
| Model configuration | Document/mixed entries alone load `DOCLING_ARTIFACTS_PATH` and one `DOCLING_OCR_LANGUAGE`. No inferred production language or ambient model-cache fallback. PDF requires explicit local assets/language. Missing/broken initialization is retryable, not a permanently invalid source. Concrete weight hashes/language coverage remain unverified. |
| Native failure recovery | Reproduced a Windows access violation in `docling_parse_backend.unload` when models fail to initialize after opening native PDF threads. Initialize PDF pipeline **before parsing**; missing-model tests now fail safely without opening that backend. Final focused/full suites have no native diagnostics. This does not certify every parser/native failure path. |
| Outcomes | Empty, partial/failure status and reported errors never upload/send completed. Safe errors omit upstream messages/source contents/local paths. Non-PDF specialized enrichment reports `ENRICHMENT_NOT_APPLICABLE`; missing crops report `IMAGE_NOT_MATERIALIZED`. Native non-PDF code remains readable without pretending PDF recognition ran. |
| Referenced local export | Fresh attempt-owned directory only: Markdown, full Docling JSON, necessary crop PNGs. Copy clears page images, drops non-data image references without reading them, normalizes published JSON URI separators. Real Core PNG/export/reload test proves one crop, no page screenshots or mutation of extraction state. Final Blob paths/inventory are N4/N5. |
| Cancellation | Shield/drain an executor Future until inference/export really stops, including repeated cancel, timeout and asyncio.run cancel-all shutdown. A to_thread Task can itself be cancelled during runner shutdown while its native writer survives. No early cleanup/upload/callback; eventual cancellation wins over late inference errors. Draining is not a hard-kill timeout. |
| API/dependencies | Reused N0's Docling/slim 2.141.0 + Core 2.99.0; pin actual parser 7.26.0/RapidOCR 3.10.0. Required HTTPX 0.28.1/settings 2.14.0 incorporation retains Pydantic 2.10.4. Context7 v2.141.0 and exact official source verified converter/options/enrichment/offline resource/serialization APIs; links in the Docling guide. |

### N3 files changed

| Files | Change |
| --- | --- |
| `src/akay_convert_to_markdown/conversion/docling_converter.py` | Extraction/configuration, rich result, safe outcomes, local referenced export and cancellation draining. |
| `src/akay_convert_to_markdown/config/docling_settings.py` | Explicit document-only local model directory/language configuration. |
| `src/akay_convert_to_markdown/conversion/document_converter.py` | Update interface documentation without changing the legacy method contract. |
| `src/akay_convert_to_markdown/document_main.py`, `main.py` | Replace only the document adapter wiring and load its controlled model settings. |
| `pyproject.toml` | Add exact Docling/Core/parser/OCR pins and incorporate the already selected HTTPX/settings replacements. Existing scripts/Azure/Pydantic/MarkItDown pins preserved. |
| `tests/unit/test_docling_conversion.py`, `tests/docling_fixtures.py` | 37 local extraction/configuration/export/lifecycle/runtime cases and generated PDF fixture; no downloaded documents/models. |
| `tests/unit/test_worker_boundaries.py` | Update the existing document-adapter double's name; preserve N1's role/import/startup assertions. |
| `tests/integration/test_docling_models.py` | Four opt-in local PDF flag-combination checks, requiring explicit test assets/language and blocking network. Not run in this session. |
| `README.md`, `docs/content-processing-docling.md`, this record | Current runtime/setup/API/limits/evidence, preserving N0-N2 checkpoints below. |

### N3 verification — exact commands and results

Commands run in PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`.

| Exact check | Observed result |
| --- | --- |
| `git status --short`; `git rev-parse --show-toplevel`; `Test-Path -LiteralPath ".codegraph"` | Correct repository, existing modified/untracked N1/N2/user files preserved, CodeGraph present. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest -q` (baseline) | **456 passed, 3 skipped in 23.79s**; no pre-existing failure. |
| `Test-Path -LiteralPath ".venv" && .venv\Scripts\python.exe -m pip install "docling[rapidocr]==2.141.0" "docling-core==2.99.0" "httpx==0.28.1" "pydantic-settings==2.14.0" "pydantic==2.10.4"` | First attempt timed out after 120s during install; same command with 600s timeout completed. Old editable app metadata initially reported old pin conflicts; refreshed below, no requirements conflict remains. No model weights fetched. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_docling_conversion.py -q --tb=short` (before implementation) | **RED: 21 setup errors in 15.48s**, missing adapter. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_docling_conversion.py::test_document_entry_has_replaced_markitdown -q --tb=short` (before wiring change) | **RED: 1 failed in 22.50s**, entry still selected MarkItDown. Later real-entry/local-storage/webhook harness verifies actual Docling delivery. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_docling_conversion.py::test_disguised_pdf_cannot_bypass_local_model_policy -q --tb=short` (before per-format restriction) | **RED: 1 failed in 23.97s**; renamed PDF reached the trapped model initialization. Per-extension format restriction fixes it. |
| Focused/regression command below, before eager PDF initialization | Focused **73 passed, 2 warnings in 62.35s**; regression then **terminated with native Windows access violation** in `docling_parse_backend.py:407 unload` on model-initialization failure. An earlier 33-case focused run also printed a native diagnostic despite a passed summary; it was not accepted as clean evidence. |
| `.venv\Scripts\python.exe -m pytest tests/unit/test_docling_conversion.py::test_model_initialization_precedes_native_pdf_open -q --tb=short` (before fix) | **RED: 1 failed in 23.23s**; parser-open trap fired before model validation. Eager initialization fixes the ordering. |
| Final focused/regression command below | **75 passed, 2 warnings in 60.94s**; then **493 passed, 7 skipped, 2 warnings in 55.89s**. Includes all 456 baseline tests. No native diagnostics. |
| `Test-Path -LiteralPath ".venv" && .venv\Scripts\python.exe -m pip install --no-deps -e . && .venv\Scripts\python.exe -m pip check` | Editable 1.0.1 wheel built/installed successfully; no broken requirements. Console scripts regenerated. This is not isolated target/image build evidence. |
| `.venv\Scripts\python.exe -m pip check && .venv\Scripts\python.exe docs/checks/content_processing_n0_probe.py` | No broken requirements; pinned option/confidence/backend/frozen-UUID/Core referenced-picture/reload probes pass in the application environment, without inference. |
| Version/CPU/module check below | Application 1.0.1, Docling/slim 2.141.0, Core 2.99.0, parser 7.26.0, RapidOCR 3.10.0, ONNX Runtime 1.20.1, HTTPX 0.28.1, Pydantic 2.10.4, settings 2.14.0, PyTorch 2.15.0, Transformers 5.23.0; CUDA build `None`; Whisper module absent. |
| `git diff --check`; new/untracked-file whitespace command below | Passed; tracked Git checks emitted LF-to-CRLF notices only. |
| `git diff -- pyproject.toml src/akay_convert_to_markdown/conversion/document_converter.py src/akay_convert_to_markdown/main.py README.md`; `git status --short --untracked-files=all` | Reviewed intended N3 wiring/pins/documentation within the existing N1/N2/user working tree; other repositories and prior checkpoints untouched. |

Final focused/regression command:

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"; $env:RUN_DOCLING_MODEL_TESTS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_docling_conversion.py tests/unit/test_worker_boundaries.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q
```

Version/CPU/module check:

```powershell
.venv\Scripts\python.exe -c "from importlib.metadata import version; import importlib.util; import torch; print({p: version(p) for p in ['akay-convert-to-markdown','docling','docling-slim','docling-core','docling-parse','rapidocr','onnxruntime','httpx','pydantic','pydantic-settings','torch','transformers']}); print('CUDA build:', torch.version.cuda); print('Whisper module present:', importlib.util.find_spec('whisper') is not None)"
```

New/untracked-file whitespace command:

```powershell
foreach ($path in @('src/akay_convert_to_markdown/config/docling_settings.py', 'src/akay_convert_to_markdown/conversion/docling_converter.py', 'src/akay_convert_to_markdown/document_main.py', 'tests/unit/test_docling_conversion.py', 'tests/unit/test_worker_boundaries.py', 'tests/docling_fixtures.py', 'tests/integration/test_docling_models.py', 'docs/content-processing-docling.md', 'docs/docling-rag-progress.md')) { $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1); if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" } }
```

Intermediate harness corrections: web h1 is TITLE/h2 is SECTION_HEADER(1), not
two section-header items; Core reload converts portable JSON image strings back
to Windows Paths; network traps must be restored before pytest creates its next
Windows event loop; timeout test overrides the seconds property instead of
passing a fractional value to the existing integer minutes setting. Export now
recognizes real data-image content rather than assuming ImageRef.from_pil always
populates its private PIL cache. None of those corrections weakens acceptance.

### N3 acceptance status and next task

- Verified: pinned option wiring/four flag combinations, six real model-free
  formats, retained internal headings/preamble/tables, actual local PNG/reference
  export/reload without page renders, safe empty/partial failures, input-format
  isolation, fresh engines and real legacy entry/processing delivery with local
  storage/webhook doubles, and inference draining through cancel/timeout/shutdown.
- **Not complete:** real PDF/scanned/broken-text-layer/table/figure/enrichment
  inference has not run. No approved local weight set/hashes or production OCR
  language was supplied; no ambient asset cache was inspected or reused and no
  downloads were authorized. Four opt-in PDF model checks remain skipped; their
  basic text fixture alone will not establish all remaining quality criteria.
  Supply reproducible local assets/language, add/run the remaining controlled
  fixtures and record measured behavior before marking N3 complete.
- Known API limit: no universal broken-text-layer replacement flag. Empty/partial
  results fail; incorrect text reported upstream as success is not universally
  detectable. Code/formula PDF recognition is configured, not quality-certified.
- Final warnings: two upstream Pydantic serialization deprecation warnings for
  Docling's computed `force_full_page_ocr`; application uses the supported mode API.
  Final skips: four explicit local-model checks; original opt-in Blob check;
  missing FFmpeg/FFprobe and Speech configuration. No live test was performed.
- Eager initialization removes the reproduced missing-model native-unload path;
  other native extraction paths and Linux/CPU inference remain unverified. Drain
  safety is verified, not hard termination or whole-workflow lock renewal (N8).
- N4-N16 remain pending. Embedding provider/model/tokenizer and all deployment
  destinations/identities remain unrelated scoped configuration; no values guessed.
- Rollback unit: the new adapter/settings/tests/fixture/guide, entry wiring,
  dependency replacements and N3 README/progress changes together. Preserve
  pre-existing N0-N2/user files. No commit was made.
- **Next fresh session: N3 remaining inference acceptance**, reusing this adapter
  and evidence. **Do not start N4** until N3's missing evidence is satisfied.

## N2 checkpoint — 2026-11-13 (preserved)

**N2: complete. Next task: N3 — Implement document extraction through Docling.**
N0/N1 remain complete; N3-N16 remain pending. Version-one contracts are implemented
as service-independent schemas/builders. Current runtime entries remain legacy
Markdown-only and reject versioned jobs until their artifact-capable paths exist.

### N2 scope and prerequisite evidence

- Executed **N2 only**, dependent on N0/N1. Read applicable parent instructions,
  README, specification, plan, current/historical progress, N0 baseline, actual
  request/consumer/processor/startup/settings code and worker-boundary tests.
  N0's compatibility/API/decision evidence and N1's actual entry/settings/dispatch
  code agree with their recorded verification. Re-ran the existing suite:
  **316 passed, 3 skipped in 21.11s**. No pre-existing local failure.
- Initial working tree included all uncommitted N1 runtime/settings/tests/README
  changes and untracked user `docs/`. Preserved them and both earlier checkpoints
  below. No dependency, Docker, CI, database or other repository changes in N2.

### N2 implementation and decisions

| Area | Result |
| --- | --- |
| Typed inputs | Strict discriminated document, Blob/YouTube media, index/delete envelopes. Required schemaVersion/contentKey/requestId/callback; index scope/positive operationSequence, explicit full profile/target and fixed/fromReview/none section variants. Unknown fields/options and wrong types fail safely. |
| Domain neutrality | Preserve opaque content/scope/payload without parsing domain IDs, trimming or case-folding. Callback must select an explicitly supplied configured identity. Protect reserved metadata. Profile is a typed snapshot, not dynamic provider loading or production-model approval. |
| JSON and references | Reject NaN/Infinity recursively and duplicate JSON keys; use safe parse errors. Portable relative Blob references and Markdown destinations, reserving artifact directories. Common layout derives only the final Markdown suffix, preserving other dots/parents/case. Actual destination ownership remains N5. |
| Artifacts | Typed document/media refs and result bundles; review holds the sole figure inventory, sections/tables/confidence/warnings/processing. Timed transcript preserves nullable available measurements, origin, language/speaker and ordered validated ranges. Full upstream Docling JSON remains upstream's schema at N3/N9, not a replacement document engine. |
| Events | Exact completed document/media artifact variants, indexing/deletion, superseded and operation-specific failures. No duplicate image inventory or alternate transcript field. Builders forward identity/payload and validate destination/refs. New idempotency helper uses requestId + event type; existing legacy HTTP behavior is preserved. |
| Immutable identity / ordering contract | Frozen model fields plus a separate canonical effective-JSON snapshot (frozen is shallow). Serializable admission receipt with earlier request identities; pure admit/resume/replay/superseded/conflict decisions cover changed parameters, reused sequences/IDs and profile changes. This is **not** Blob persistence/leases, Qdrant mutation coordination or working indexing; N11 must implement and test those guarantees. |
| Runtime activation | Do not send the new contract into the Markdown-only processor or synthesize artifact success. Legacy parser rejects new contract identity/options/index fields, including snake_case aliases. Existing legacy envelopes/behavior pass regressions. N3-N6 must activate new boundaries together with the corresponding artifact-capable paths. |
| API verification | Kept Pydantic 2.10.4 and every project dependency pin. Consulted Context7's closest indexed 2.10.6, then exact official 2.10.4 strict-mode/unions docs and config source. Strict JSON UUID handling, nested discriminators, aliases, frozen semantics and finite validation verified against installed 2.10.4. Links are in the contract guide. |

### Files changed for N2

| Files | Change |
| --- | --- |
| `src/akay_convert_to_markdown/contracts/base.py` | Strict finite JSON, safe parsing, portable reference primitives. |
| `src/akay_convert_to_markdown/contracts/requests.py` | Input/profile/source/section variants and configured callback selection. |
| `src/akay_convert_to_markdown/contracts/artifacts.py` | Artifact layout/refs/bundles, review/transcript schemas and strict read parsers. |
| `src/akay_convert_to_markdown/contracts/events.py` | Webhook variants, builders, event parser and result-specific idempotency identity. |
| `src/akay_convert_to_markdown/contracts/ordering.py`, `__init__.py` | Serializable request/admission identity, pure ordering decisions and package exports. |
| `src/akay_convert_to_markdown/models/conversion_request.py` | Fail-closed versioned-field guard in the legacy parser. |
| `tests/fixtures/content_processing/contracts.json`, `tests/unit/test_content_contracts.py` | Local fixtures and 140 focused cases including all 10 complete normative JSON examples, ordering snapshots and real consumer boundary with doubles. |
| `README.md`, `docs/content-processing-contracts.md`, `docs/docling-rag-progress.md` | Runtime versus staged-contract status, consumer-facing contracts and preserved progress. |

### N2 verification — observed

PowerShell commands from `C:\Develop\Akay\Akay.ConvertToMarkdown`:

| Exact check | Result |
| --- | --- |
| `git status --short`; `git rev-parse --show-toplevel`; `Test-Path -LiteralPath ".codegraph"` | Correct repository; existing N1/user working tree retained; CodeGraph present and queried before code exploration. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest -q` (baseline) | **316 passed, 3 skipped in 21.11s**. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_content_contracts.py -q --tb=short` (before production changes) | **RED: 4 failed, 112 setup errors in 7.22s**. Four legacy-parser assertions proved the silent-downgrade bug; other cases reported the missing contracts module. |
| Same focused command (initial implementation) | 115 passed/1 failed: the historical request-ID reuse assertion exposed missing receipt history. Added serialized older identities and scope/sequence/identity consistency checks; **116 passed in 1.83s**. No durable state or index mutations added. |
| Same focused command (strict artifact-reader tests, before reader addition) | **RED: 2 failed, 133 passed in 10.62s**: absent parse_review/parse_transcript. Added shared strict read boundaries. |
| Same focused command (snake_case legacy-boundary tests, before guard extension) | **RED: 5 failed, 135 passed in 5.94s**: alternate field spellings were ignored. Extended only the guard's new-contract fields. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_content_contracts.py -q --tb=short && .venv\Scripts\python.exe -m pytest -q` | Final focused **140 passed in 4.93s**; regression **456 passed, 3 skipped in 38.43s**, including all 316 baseline tests. |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found. |
| `.venv\Scripts\python.exe -c "import pydantic; print('Pydantic', pydantic.__version__)"` | Actual test environment: **Pydantic 2.10.4**, matching the unchanged project pin. |
| `git diff --check` and new-file/progress checks below | Passed; repository LF-to-CRLF notices only. |
| `git diff -- README.md src/akay_convert_to_markdown/models/conversion_request.py`; `git status --short --untracked-files=all` | Reviewed only the intended N2 tracked diff plus new contracts/tests/docs; prior N1/user files remain present. |

New-file/progress whitespace validation:

```powershell
foreach ($path in @('src/akay_convert_to_markdown/contracts/base.py', 'src/akay_convert_to_markdown/contracts/requests.py', 'src/akay_convert_to_markdown/contracts/artifacts.py', 'src/akay_convert_to_markdown/contracts/events.py', 'src/akay_convert_to_markdown/contracts/ordering.py', 'src/akay_convert_to_markdown/contracts/__init__.py', 'tests/unit/test_content_contracts.py', 'tests/fixtures/content_processing/contracts.json', 'docs/content-processing-contracts.md', 'docs/docling-rag-progress.md')) {
    $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1)
    if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" }
}
```

### N2 acceptance, pending evidence and next task

- Contract acceptance met: all variants, invalid combinations/types/options,
  exact opaque forwarding, typed artifacts/events, safe finite JSON, null/absent
  measurements, immutable snapshots and serializable ordered-admission decisions
  are covered. All complete normative examples are parsed automatically, not
  copied into divergent hand-maintained schema documents.
- Runtime harness: four consumer tests use the real ServiceBusConsumer with
  existing local receiver/processor/lock-renewer doubles. Versioned jobs never
  reach processing/success; legacy startup, dispatch, webhook and settlement
  regressions still pass. No live service or ambient credential was used.
- Same integration omissions: `test_blob_round_trip` opt-in disabled;
  `test_ffmpeg_probes_and_prepares_wav` missing FFmpeg/FFprobe;
  `test_fast_transcription_round_trip` missing Speech configuration. These remain
  pending external evidence, not failed N2 contract checks.
- N3-N11 still own extraction, principal markers/review production, coherent
  publication, timed media production, bounded YouTube adapter, reliable transport,
  chunking, actual provider/profile compatibility and durable Qdrant ordering/races.
  No durable/cloud guarantee is credited from schema tests or serialized receipts.
- Embedding provider/model/deployment/tokenizer, authorized Qdrant/queue/image/app
  names and cloud identities remain scoped integration inputs; none blocks N2.
  No Docker/CI/publication/deployment is required or claimed for this task.
- Rollback unit: remove the six new contract modules, contract fixtures/tests/guide,
  the legacy parser's versioned guard and N2 README/progress changes together,
  preserving the pre-existing N0/N1 implementation and checkpoints. No commit made.
- **Next fresh session: N3 only**, prerequisite N2 now complete. Replace the
  document converter with pinned Docling, test controlled formats/flags and safe
  inference behavior; coordinate new runtime activation with the artifact
  requirements instead of treating Markdown-only legacy output as complete.

## N1 checkpoint — 2026-11-13 (preserved)

**N1: complete. Next task: N2 — Implement the new contracts.**
N0 remains complete; N2-N16 remain pending. Dedicated document/media entries
reuse the existing contract/adapters and Markdown-only publication. The index
entry is a deliberately non-consuming bootstrap, not a working indexer.

### N1 scope and prerequisite evidence

- Executed **N1 only**, dependent on N0. Read the specification/plan, current
  README, parent repository instructions, N0 baseline/progress and actual
  startup/settings/consumer/processor/storage/media code. No repository-local
  `AGENTS.md` exists. The single script/mixed wiring and lack of target settings
  confirmed N1 was incomplete; N0's compatibility map, fixed decisions and exact
  baseline/probe evidence satisfy its documentation-only exit criteria.
- Initial state: HEAD `f03c7a4`, ` M README.md`, `?? docs/`. Preserved the existing
  README status links and all untracked specifications, plan, probes, historical
  records and other user documents. No commit, publication or deployment.

### N1 implementation and decisions

| Area | Result |
| --- | --- |
| Entry points | Add `akay-convert-document`, `akay-transcribe-media`, `akay-index-content`; retain `akay-convert-to-markdown` as a backward-compatible mixed command, not a document-only alias. Python module execution is also available. |
| Settings | Reuse common auth/Blob/Service Bus/callback settings; conversion adds destination; media alone adds Speech/FFmpeg. Dedicated media requires non-blank Speech key/endpoint. Document defaults to one concurrent job. Legacy defaults/format behavior are preserved. Index bootstrap does not require destination, Speech, FFmpeg or a guessed embedding profile. |
| Routing | Require explicit `DOCUMENT_SERVICEBUS_QUEUE_NAME`, `MEDIA_SERVICEBUS_QUEUE_NAME`, `INDEX_SERVICEBUS_QUEUE_NAME`; no fallback to the mixed `SERVICEBUS_QUEUE_NAME`. Reject collisions with other locally configured routes (case/outer-whitespace insensitive), including from legacy startup. Physical values remain supplied by integration, not hard-coded resource names. |
| Shared boundary | Consumer depends on the minimal `RequestProcessor` protocol rather than concrete `DocumentProcessor`; parsing remains the existing conversion parser until N2. `worker_runtime.py` shares credential/client lifecycle, signals and consumer startup. `AsyncExitStack` closes acquired resources on startup/run failure. No generic job framework. |
| Dispatch/import isolation | Reuse the existing orchestration with an allowed-type guard before output reuse/download. Document wires only its existing converter. Media wires the existing audio/video/Speech/FFmpeg implementations with no document adapter. Move media-only processor type imports behind `TYPE_CHECKING`. Shared clients use common-settings annotations; media helpers use media-settings annotations. |
| Index bootstrap | Validate its common/queue settings, emit safe `INDEXER_NOT_IMPLEMENTED` log and return exit 2 **before** Azure credential construction, queue consumption, callbacks or mutations. There is no success/no-op index handler. Real contracts and index processing remain N2/N9-N11. |

Queue validation is a local configuration safeguard, not remote exclusivity:
each process must receive the known assignments, and integration must coordinate
the producer/legacy cutover. No live queue was inspected or created. This task
does not claim three dependency sets/images, Docling processing, multi-artifact
publication, timed JSON, YouTube or indexing.

### Files changed for N1

| Files | Change |
| --- | --- |
| `pyproject.toml` | Register three console scripts; keep existing dependency pins and legacy command. |
| `src/akay_convert_to_markdown/document_main.py`, `media_main.py`, `index_main.py` | Target-specific composition/entry points and fail-closed index bootstrap. |
| `src/akay_convert_to_markdown/worker_runtime.py`, `main.py` | Shared technical startup/resource lifecycle reused by the retained mixed command. |
| `src/akay_convert_to_markdown/config/settings.py` | Common/conversion/media/target settings and explicit local queue separation. |
| `src/akay_convert_to_markdown/processing/request_processor.py`, `messaging/service_bus_consumer.py` | Minimal processing protocol replacing the concrete consumer dependency. |
| `src/akay_convert_to_markdown/processing/document_processor.py` | Role restriction before reuse and optional document adapter; remove runtime media imports. |
| `src/akay_convert_to_markdown/notifications/webhook_client.py`, `storage/blob_storage.py` | Common-settings annotations for reusable clients. |
| `src/akay_convert_to_markdown/processing/_media.py`, `audio_processor.py`, `video_processor.py`, `services/fast_transcription_service.py`, `services/ffmpeg_service.py` | Media-settings annotations; existing processing behavior reused. |
| `tests/unit/test_worker_boundaries.py` | Isolated settings/import/startup/dispatch tests, local service doubles, resource failure cleanup, script registration. |
| `README.md`, `docs/docling-rag-progress.md` | Current command/configuration/cutover limits and this append-preserving checkpoint. |

Paths in grouped source rows are relative to `src/akay_convert_to_markdown/`.
Docker/CI changes belong to N12-N15 and were not required for N1.

### N1 verification — observed

Commands run in PowerShell from `C:\Develop\Akay\Akay.ConvertToMarkdown`.

| Exact check | Result |
| --- | --- |
| `git status --short`; `git rev-parse --show-toplevel`; `git log --oneline -5`; `git diff -- README.md` | Correct repository/HEAD and initial user changes as recorded above. |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found (baseline and after changes). |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest` | Before implementation: **278 passed, 3 skipped in 11.03s**, no pre-existing local failure. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest tests/unit/test_worker_boundaries.py -q --tb=short` | **RED before production edits: 35 failed, 3 passed in 5.31s**. Missing target settings/modules and console registrations; e.g. `test_target_requires_explicit_queue[...]`, `test_worker_dispatch_is_restricted_before_reuse[...]`, `test_three_console_scripts_and_legacy_command_are_registered`. Removed the three no-op same-target queue combinations and added legacy startup/two failure-cleanup cases afterwards. Final **GREEN: 38 passed in 20.74s**. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest -q` | **316 passed, 3 skipped in 32.11s**, including all 278 existing local tests. |
| `.venv\Scripts\python.exe -c "from importlib.metadata import version; import importlib.util; print({name: version(name) for name in ['pydantic', 'pydantic-settings', 'azure-identity', 'azure-servicebus', 'azure-storage-blob', 'httpx']}); print('hatchling available:', importlib.util.find_spec('hatchling') is not None)"` | Actual pins: `2.10.4`, `2.7.1`, `1.20.0`, `7.14.0`, `12.24.1`, `0.27.2`. Hatchling unavailable; no build dependency was downloaded. |
| `git diff --check` | No whitespace errors; existing LF-to-CRLF notices only. |
| `git diff -- src/akay_convert_to_markdown/messaging/service_bus_consumer.py src/akay_convert_to_markdown/notifications/webhook_client.py src/akay_convert_to_markdown/processing/_media.py src/akay_convert_to_markdown/processing/audio_processor.py src/akay_convert_to_markdown/processing/video_processor.py src/akay_convert_to_markdown/services/fast_transcription_service.py src/akay_convert_to_markdown/services/ffmpeg_service.py src/akay_convert_to_markdown/storage/blob_storage.py pyproject.toml README.md` | Inspected final shared-client/media annotation changes, scripts and current-runtime documentation. |
| `git status --short --untracked-files=all` | Only intended N1 runtime/tests/docs edits plus the preserved pre-existing user documents. No other repository/database changes. |

New-file/progress whitespace check (no diagnostics for any file):

```powershell
foreach ($path in @('src/akay_convert_to_markdown/document_main.py', 'src/akay_convert_to_markdown/media_main.py', 'src/akay_convert_to_markdown/index_main.py', 'src/akay_convert_to_markdown/worker_runtime.py', 'src/akay_convert_to_markdown/processing/request_processor.py', 'tests/unit/test_worker_boundaries.py', 'docs/docling-rag-progress.md')) {
    $diagnostics = @(git -c core.autocrlf=false diff --no-index --check -- NUL $path 2>&1)
    if ($diagnostics.Count -gt 0 -or $LASTEXITCODE -gt 1) { throw "Whitespace diagnostics for ${path}: $diagnostics" }
}
```

The initial whitespace wrapper incorrectly treated the normal no-index
added-file exit status 1 as a failure; the diagnostic-aware rerun above passes.

The 38 focused tests include four fresh subprocess startups (three new entries
and legacy) with forbidden foreign imports enforced by an import hook; all Azure
credential/client/consumer boundaries are doubles. Dispatch tests retain real
audio/video strategies with local Speech/FFmpeg doubles and exercise existing
output as well as fresh output. Consumer/bootstrap failures verify acquired
client cleanup. No live services or ambient credentials were used.

Harness corrections are not product evidence: the first RED invocation without
`--tb=short` also hit Windows asyncio `WinError 10106` because its scrubbed child
environment omitted `SYSTEMROOT`. Preserve only that OS path alongside explicit
fixture configuration; the recorded RED rerun then failed for missing N1 code.
The first implementation run had 37 passing/one failing test because the
queue-only media test omitted its required fixture Speech settings; corrected
that test setup before the final GREEN. No production requirement was relaxed.

API evidence: [pydantic-settings v2.7.1 official documentation](https://github.com/pydantic/pydantic-settings/blob/v2.7.1/docs/index.md)
confirms `BaseSettings`, `SettingsConfigDict`, `Field(validation_alias=...)`, no
prefix application to aliases and default case-insensitive environment names.
Context7 was also consulted; newer-only options were not adopted.
[Azure Identity 1.20.0 official source](https://github.com/Azure/azure-sdk-for-python/blob/azure-identity_1.20.0/sdk/identity/azure-identity/azure/identity/aio/_credentials/default.py)
and Microsoft Learn async credential examples confirm the retained
`managed_identity_client_id`/async lifecycle. No SDK pins or service calls change.

### N1 acceptance and remaining evidence

- Acceptance met for this scaffold: isolated startup/settings/role dispatch,
  converter without Speech/Qdrant wiring, transcriber without document/Docling/
  Qdrant wiring, index bootstrap without Speech/FFmpeg, and retained mixed startup.
  A working index consumer cannot be credited until N2/N9-N11; startup exits 2
  rather than acknowledging unsupported jobs.
- Same three integration skips: opt-in Blob test disabled; real FFmpeg/FFprobe
  unavailable; real Speech configuration absent. No live tests were authorized.
- Not run: wheel build/generated-console-executable smoke (Hatchling absent),
  clean target dependency installs, Docker builds, remote CI, queue/service/cloud
  tests or deployment. Script mappings and callable module startup are verified;
  installation/image evidence belongs to N12-N13. No missing local N1 test remains.
- Embedding provider/model/deployment/tokenizer, Qdrant destinations and physical
  queues/images/apps/identities remain the scoped pending inputs from N0. They
  do not block the current bootstrap and were not guessed.
- **Next fresh session: N2 only**, dependent on completed N0/N1. Add the specified
  typed contracts/fixtures to these entry boundaries without implementing N3
  extraction or N9-N11 index processing. Preserve this N1 scaffold and N0 history.

## N0 checkpoint — 2026-11-13 (preserved)

**N0: complete. Next task: N1 — Separate worker entry points and settings.**
N1-N16 remain pending. This checkpoint is baseline reconciliation only; it does
not claim that Docling conversion, new contracts, indexing or three images exist.

Authority: [specification](content-processing-specification.md) and
[N0-N16 plan](docling-rag-implementation-plan.md). Decisions and compatibility
map: [N0 baseline](content-processing-n0-baseline.md).
Preserved history: [old T0 progress](versión%20old/docling-rag-progress.md) and
[old dependency inputs](versión%20old/docling-rag-t0-inputs.md). The new plan
supersedes their task IDs and conflicting requirements; neither was erased.

### Task and decisions

- Executed **N0 only**, with no prerequisites. Actual entry points, contracts,
  converter, storage, media, settlement, Docker/workflow and prior evidence were
  inspected; the earlier T0 was pending, and no N0 record previously existed.
- Reuse the verified Docling/slim `2.141.0` + Core `2.99.0` API baseline; project
  dependencies remain unchanged. The old HTTPX/settings replacement evidence
  remains historical; N3/N12 perform installation/target-specific resolution.
- Freeze specification-compliant artifact naming, section UUID namespace and
  canonical serialization with checked vectors, and Blob lease/conditional-write
  coordination as detailed in the baseline. These are decisions, not runtime code.
- Reconcile old marker/inventory/fingerprint/two-worker assumptions against the
  authoritative specification. Typed contracts/fixtures belong to N2.
- Keep deployment names, embeddings, OCR assets/languages and other missing
  configuration explicitly scoped to dependent tasks. No essential N0 decision
  remains blocked; the example embedding profile is not production approval.

### Changed files in this session

| File | Change |
| --- | --- |
| `README.md` | Link the new progress record/specification while retaining current-runtime documentation. |
| `docs/content-processing-n0-baseline.md` | Compatibility/reuse map, frozen technical choices, exact-version findings and pending inputs. |
| `docs/checks/content_processing_n0_probe.py` | Reuse old no-inference probe; add backend/confidence checks and frozen UUID vectors. |
| `docs/docling-rag-progress.md` | This current N0 checkpoint and verification/next-task record. |

Initial git state was `?? docs/` at HEAD `f03c7a4`; existing untracked user
documents, specification, plan and old progress/probe/fixtures were preserved.
No application/test/dependency/Docker/workflow changes, commit, push, publication,
resource creation, database changes or deployment were performed.

### Verification — observed this session

Commands run from `C:\Develop\Akay\Akay.ConvertToMarkdown` in PowerShell.
The isolated Python below is the previously created probe environment, not the
project environment. It is not a reproducible transitive lock or inference image.

| Exact check | Observed result |
| --- | --- |
| `git status --short`; `git rev-parse --show-toplevel`; `git log --oneline -5` | `?? docs/`; correct repository; HEAD `f03c7a4`. |
| `.venv\Scripts\python.exe --version` | Python `3.12.10`. |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found. |
| `$env:RUN_AZURE_INTEGRATION_TESTS = "false"; .venv\Scripts\python.exe -m pytest` | **278 passed, 3 skipped in 15.07s**, 281 collected, no failures. External integration explicitly disabled. |
| `& "C:\Users\alvaro.caballero\AppData\Local\Temp\opencode\akay-docling-t0-api\Scripts\python.exe" "docs\versión old\checks\docling_t0_api_probe.py"` | PASS: pinned options, confidence, distinct heading references, actual synthetic referenced picture and JSON reload. |
| `& "C:\Users\alvaro.caballero\AppData\Local\Temp\opencode\akay-docling-t0-api\Scripts\python.exe" -m pip check` | No broken requirements found. |
| `& "C:\Users\alvaro.caballero\AppData\Local\Temp\opencode\akay-docling-t0-api\Scripts\python.exe" "docs\checks\content_processing_n0_probe.py"` | PASS: reused T0 checks plus ConversionResult confidence, disabled backend resource fetching, absent repair flag in all three PDF option models, and all three section UUID vectors. No inference or services. |
| `git diff --check` | Passed; LF-to-CRLF notice only. |
| `git diff --no-index --check -- NUL "docs/content-processing-n0-baseline.md"` | Passed; LF-to-CRLF notice only. |
| `git diff --no-index --check -- NUL "docs/docling-rag-progress.md"` | Passed; LF-to-CRLF notice only. |
| `git diff --no-index --check -- NUL "docs/checks/content_processing_n0_probe.py"` | Passed; LF-to-CRLF notice only. |
| `git diff -- README.md`; `git status --short --untracked-files=all` | README diff is the five-line status link; three new N0 files; existing untracked documents retained. No tracked runtime/configuration diff. |
| Manual document structure/link check | README links to current authority/progress; progress links to baseline/history; referenced probe and historical inputs exist. N0 decisions distinguish observed APIs, historical resolution and future acceptance checks. |

Integration omissions: `test_blob_round_trip` is opt-in disabled;
`test_ffmpeg_probes_and_prepares_wav` reports missing FFmpeg/FFprobe;
`test_fast_transcription_round_trip` reports Speech configuration absent.
These are recorded skip messages, not credential discovery or live-service tests.
No pre-existing local failure was observed.

RED/GREEN is not applicable: N0 changes documentation and passive API checks only, with no
runnable production behavior change. No artificial failing test is claimed.

### N0 acceptance

The exit criteria are met: an actual-code compatibility/reuse map, rechecked
pinned prerequisite APIs, fixed artifact/section/coordinator decisions, observed
local baseline checks and task-scoped pending configuration are recorded. No
N1-N16 implementation was used to make N0 appear complete. The historical pending
T0 is preserved rather than relabeled as completed production work.

### Pending evidence and next session

- Not run: actual Docling extraction/OCR/enrichment, broken-text-layer recovery,
  Linux/CPU resolution/model isolation, real image export/page exclusion,
  chunking, embeddings, Qdrant, durable coordination races, Docker builds,
  workflow runs, cloud access or deployment. These belong to their later tasks.
- Missing configuration and exact affected tasks are listed in the baseline;
  credentials/endpoints were not discovered from ambient configuration.
- **Next: N1**, with N0 now satisfied. Separate entry points/settings/shared
  technical interfaces and isolated startup/dispatch tests; preserve compatible
  media and current functionality. Follow focused RED/GREEN for deterministic
  behavior changes. Do not implement N2 contracts or N3 extraction in that session.
