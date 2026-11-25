# Test and build the complete worker image set

N14 prepares `.github/workflows/build-and-push.yml` for the three N13 targets.
Pull requests, pushes to `main` and manual runs test first, then build and smoke
all three images. **Publication is disabled by default.** No remote workflow or
registry publication is credited by local validation; deployment belongs to N15.

## Normal verification path

1. `test`: actionlint **1.7.7** (digest-pinned image, including ShellCheck), Python
   **3.12.12**, the three hashed Linux runtime locks and hashed build tooling.
   Install the pinned test extra, run `pip check`, the default pytest suite and N0
   API/UUID probe. Azure, host model inference and optical-quality opt-ins are false.
2. `images`, only after tests pass: Buildx **0.38.1**, local Docker driver, exact
   public assets, and the unchanged N13 `tools/check_images.py` harness. Build all
   three targets and run all normal phases: document startup/rebuild/models/
   inference; media tools/startup; saved-transcript/tokenizer/local-Qdrant index
   startup. Containers are non-root, offline, read-only and resource-bounded.
3. `tools/ci_release.py` verifies every phase's exit/OOM state and measurements and
   retains the exact image IDs. Its default mode needs no repositories, login or
   registry access. An incomplete set cannot become a publication candidate.
4. Upload only logs, commands, measurements and release JSON for 14 days, including
   failed-run evidence. Hidden `.local` paths are explicitly enabled, but model
   files, Python environments and Docker authentication directories are excluded
   by the positive file list.

The test host intentionally installs the runtime union for regressions. Image
smoke checks independently verify target isolation in the actual installed images.
Known Spanish accent errors, unmeasured eu/gl/ca/fr/en/de optical quality and the
separate failing Linux formula-layout diagnostic retain their N3/N13 classification.
The strict layout diagnostic is not silently enabled, hidden as a pass or repaired
by this workflow; actual code/formula crop inference remains in the normal smoke.

## Exact public build assets and cache

`tools/ci_assets.py` maps only the 19 existing model-lock files and one tokenizer.
Hugging Face URLs contain the exact existing snapshot revisions; RapidOCR URLs
come from its **v3.10.0** registry. Every cached/downloaded file must match N12's
SHA-256 and recorded size when available. Missing assets require the explicit
`--download-public-assets` flag; corrupt existing files fail instead of being
silently replaced. Transfers stream into bounded temporary files and become
build inputs only after verification. No inference-time downloader is introduced.

To inspect the exact source list without downloading:

```powershell
.venv\Scripts\python.exe tools/ci_assets.py --directory .local/n14/assets --list-sources
```

CI's prepared acquisition command is:

```text
python tools/ci_assets.py --directory .local/n14/assets --download-public-assets
```

This is a public static-weight/tokenizer download, not a call to Speech, embeddings,
YouTube or an application service. It uses no HF token, proxy discovery, `.netrc`,
Azure login or user model cache. HTTPS redirects support the public hosts' CDN
delivery and cannot downgrade to HTTP. No downloader credentials are supplied to
the build or image layers.

The only shared data cache contains these public files. Its exact key includes
the OS, both asset locks and acquisition code, with no broad restore prefix.
Verification runs even on a cache hit. Build layers use only the job's local
Docker cache; no authenticated or cross-PR layer cache is exported. N13's empty
Docker config and explicit plugin-copy boundary are retained. Existing local
assets can be reused for local builds; this session does not need to download
another model set. Remote availability of the pinned URLs remains unverified
until an authorized CI run actually fetches them.

## Explicit GHCR publication

Publication requires **all** of these conditions, after the full local build/smoke:

- A manual `workflow_dispatch` on `refs/heads/main`, with boolean `publish=true`.
- Repository variable `GHCR_PUBLICATION_ENABLED` exactly `true`.
- Repository variable `GHCR_IMAGE_REPOSITORIES` containing a JSON object with
  exactly `document`, `media`, `index` mapped to three distinct authorized,
  lowercase `ghcr.io/<owner>/<repository>` names, without tags or digests.

No physical repository names are selected here. Before enabling this switch,
confirm these destinations and the workflow token's package permissions. With the
switch absent or false, even a dispatch with `publish=true` does not log in or push.
`GITHUB_TOKEN` is supplied only to the gated login action in a dedicated runner-temp
Docker config. The images job declares `packages: write`; other jobs/default
permissions are read-only. Checkouts never persist Git credentials. The login
action logs out during its post step; auth config is never an artifact/cache.

All three images share this release identity/tag:

```text
sha-<full-40-character-commit>-<github-run-id>-<github-run-attempt>
```

The run attempt makes reruns non-reusing, avoiding semantic-version allocation
races and overwriting a SHA-only tag when rebuild metadata differs. Workflow
concurrency serializes the same ref without cancelling an active publisher.
There is no `latest`, branch alias, Git tag, automatic release or deployment.
GHCR tags are not claimed to have registry-enforced immutability: consumers must
pin the recorded **repository@sha256:digest**, not a mutable lookup.

The publisher first inspects all three exact tested IDs, then tags/pushes those
IDs without rebuilding. Each successful push must supply a matching RepoDigest.
Only after all three succeed does it write `release.json` with `status=complete`,
commit, shared release identity, image IDs, tags and immutable digest references.
`publication.json` journals confirmed partial progress. Reusing an existing local
publication/success record fails before Docker mutations.

### Failure and retry

Three pushes are not a registry transaction. If a later push/digest check fails,
earlier images may exist, but no complete release record is emitted. Do not deploy
that partial set. Retain the failed-run evidence; rerun the workflow with a new
run attempt, retest/rebuild the complete set and obtain a new complete digest
record. No automatic remote deletion or rollback is attempted. A successful
build-only run has `build-verification.json`, never a fabricated release digest.

## Evidence and remaining integration

Local RED/GREEN, actionlint/ShellCheck and actual three-image build/smoke commands
are recorded in [progress](docling-rag-progress.md). They verify prepared logic,
not GitHub-hosted execution, remote asset availability, package permissions or
GHCR transport. The first real run must also measure runner disk/time capacity
for the document image. No registry token or application credential was discovered
for local verification. Publication, cloud resources and deployments were not run.

N15 now prepares [separately gated Container Apps deployment configuration](content-processing-deployment.md)
using explicit physical settings and complete digest records. GHCR push and Azure
image-pull authentication remain distinct integration inputs. Real deployment is
unverified; the next implementation task is N16 in a fresh session.

Official API references: [Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[artifact v4 behavior](https://github.com/actions/upload-artifact/tree/v4),
[Buildx action v3 inputs](https://github.com/docker/setup-buildx-action/blob/v3/action.yml),
[Docker CLI v29.9.3 push](https://github.com/docker/cli/blob/v29.9.3/docs/reference/commandline/image_push.md),
[actionlint 1.7.7](https://github.com/rhysd/actionlint/blob/v1.7.7/docs/usage.md),
[RapidOCR v3.10.0 registry](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml).
