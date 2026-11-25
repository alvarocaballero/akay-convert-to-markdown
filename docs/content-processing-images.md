# Build and check the three worker images locally

N13 adds three Linux/amd64 targets in `Dockerfile.workers`, using N12's CPU locks
and existing verified assets. Each image runs as UID/GID **10001**, exposes no
ports and installs only its own worker engines. The original `Dockerfile` remains
the legacy mixed image for explicit local builds. N14's
[CI workflow](content-processing-ci.md) now checks the three dedicated targets
and prepares explicitly gated publication.

## Quick path

Start a local Linux Docker engine with Buildx. Reuse the explicit N3 model bundle
and N10 tokenizer; the command verifies and stages only their locked files:

```powershell
.venv\Scripts\python.exe tools/check_images.py --docker-host "npipe:////./pipe/dockerDesktopLinuxEngine" --buildx-plugin "C:\Users\alvaro.caballero\.docker\cli-plugins\docker-buildx.exe" --document-models .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken
```

On Linux use `--docker-host unix:///var/run/docker.sock` and the corresponding
Python path; omit `--buildx-plugin` when Buildx is installed in a system CLI plugin
directory. That optional argument copies only the explicitly supplied executable,
not the user's Docker configuration. The checker creates an empty Docker config
and an allowlisted subprocess environment, with no registry/cloud credentials.

| Target | Local test tag | Entry point | Assets/system tools |
| --- | --- | --- | --- |
| `document-converter` | `akay-n13-document:local` | `akay-convert-document` | 19 locked layout/accurate-table/OCR/CodeFormulaV2 files; Liberation fonts/fontconfig; no FFmpeg |
| `media-transcriber` | `akay-n13-media:local` | `akay-transcribe-media` | FFmpeg/FFprobe, pinned yt-dlp/EJS/Deno; no extraction/tokenizer weights |
| `content-indexer` | `akay-n13-index:local` | `akay-index-content` | Local hash-verified `cl100k_base`; no extraction models or FFmpeg |

These are local test names, not production GHCR/app/queue settings. The tool builds
and loads locally, never pushes or deploys. Public base images, Debian packages
and hashed Python wheels are build-time inputs, not application-service calls.

## Reproducible, bounded inputs

- Python **3.12.12 slim/bookworm** and the Dockerfile frontend are digest-pinned.
  Python runtime/transitive dependencies use the unchanged hashed N12 Linux locks.
  The wheel builder has a separate hashed `requirements/image-build-linux.txt`;
  Hatchling and its build dependencies do not enter worker site-packages.
- Debian packages resolve from the fixed **20261110T000000Z** snapshot. Liberation
  fonts restore native PDF heading rendering absent from the minimal base.
  FFmpeg **5.1.9-0+deb12u1** and its required shared libraries stay media-only.
  The selected Deno **2.5.6** Linux wheel installs its executable as 0644; the
  media image sets 0755 and executes its version check at build time.
- Named contexts `document_assets` and `tokenizer_assets` receive only staged,
  verified local files. Unrelated cache files/audit records never enter images.
  No broad model downloader or runtime fetch is used. A separate verified asset
  stage avoids duplicating the document weights in a chmod layer of the runtime.
- `.dockerignore` allowlists build inputs, excluding local venvs, Git metadata,
  `.env` files, models and evidence. This also bounds the legacy build context.
- Reproduction means pinned inputs and behavior, not a claim of bit-identical
  image digests across independent builders/timestamps. Check the local image IDs
  in each result record; actual registry publication/digests remain external work
  behind N14's prepared authorization gate.

If an explicitly supplied asset is missing, reuse/fetch exactly the file/revision
in `requirements/document-models.json` or `index-tokenizer.json` into a controlled
bundle before building. The checker never searches ambient caches or downloads
replacement weights. See [packaging](content-processing-packaging.md).

## Offline smoke checks and results

All smoke containers use `--network none`, read-only root, no capabilities,
`no-new-privileges`, 2 CPUs, 4 GiB RAM, 256 PIDs and a **1 GiB** UID-owned tmpfs at
`/tmp/akay`. Socket traps also reject connections. These are fixture measurement
limits, not approved production capacity. For actual worker runs provide that
bounded writable mount and the worker's explicit settings; an image alone does
not impose an aggregate writable-layer quota. `DOCLING_ARTIFACTS_PATH` is included;
configure the indexer's tokenizer path as `/opt/tokenizers/cl100k_base.tiktoken`.

| Check | Actual local evidence |
| --- | --- |
| Installed engines/startup | All three real compositions run with service doubles; installed distribution/import inventories exclude foreign engines. Missing index adapter config exits 2 before credentials. No service/queue is contacted. |
| Document operations | Real Markdown extraction/export/rebuild/Core reload; separate fresh process rebuild blocks extraction pipeline/model imports and resource fetching. |
| Local models | Exact non-root file hashes/inventory; all seven OCR selections initialize individually; layout/accurate-table/code/formula initialization succeeds. |
| Spanish OCR | Raster-only and corrupt-overlay fixtures invoke OCR, retain confidence and reload returned text without page-image artifacts. Accent fidelity remains a separate known limitation. |
| Native PDF | Four flag combinations retain native headings/body, tables, figures, code and portable crop links. Enabled code yields multiline text. Linux does **not** classify this fixture's formula as a formula. |
| Formula availability | Separate ground-truth fixture crops run the actual initialized CodeFormulaV2 stage for code and formula, producing nonempty recognized text. No production classification, result or backend is patched. |
| Media tools | Actual audio-only WebM -> probe -> OGG extraction; real offline bundled EJS evaluation in Deno with no permissions granted. Speech/YouTube remain doubles. |
| Index | Real saved corrected transcript -> HybridChunker/local tokenizer -> persistent local Qdrant, without Docling extraction/Torch/FFmpeg. Embeddings/services are not called. |

Final uncompressed `docker image inspect .Size`: document **4,647,693,910**,
media **1,264,185,849**, index **658,554,112 bytes**. See the
[progress record](docling-rag-progress.md) for IDs and exact commands.
They are measured image sizes, not registry transfer
sizes. The document inference run took **505.56 s**, with **984.03 CPU s**,
**3,678,504 KiB max process RSS** and **2,908,274,688 bytes cgroup memory peak**
under the limits above. RSS and cgroup counters are distinct Linux measurements;
neither is a general capacity guarantee. No OOM occurred.

Full native-fixture optical/layout parity is not asserted: the original strict
formula-classification assertion remains reproducible as a separate diagnostic:

```powershell
.venv\Scripts\python.exe tools/check_images.py --docker-host "npipe:////./pipe/dockerDesktopLinuxEngine" --document-models .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken --target document --skip-build --smoke layout-diagnostic
```

This intentionally returns a failing result for the observed Linux classification
limitation, rather than an xfail or a model-repair fallback. The original N3 tests
are unchanged. OCR quality in **eu, gl, ca, fr, en and de** is individually
unmeasured; Spanish accent errors remain recorded. Successful resource loading
and crop inference do not certify document recognition accuracy.

Use `--target document|media|index`, `--skip-build` and `--smoke startup` to repeat
only a relevant check. Document-only `rebuild`, `models`, `inference` and
`layout-diagnostic` selections reject other targets. Run directories under ignored
`.local/n13/` contain exact commands, image IDs/byte sizes, smoke logs and exit/OOM
state/resource observations. The checker removes only its own named containers.

## Handoff and remaining external work

N15 prepares [separately gated deployment](content-processing-deployment.md) from
complete N14 digest records. N16 supplies the [local handoff](content-processing-handoff.md).
Cloud deployment, authorized live services, real termination under load and
production sizing remain external evidence. Local image checks do not publish,
create resources, select physical settings or implement Akay.Be.

Official references: Docker [named contexts](https://docs.docker.com/build/building/context/#named-contexts),
[multi-stage targets](https://docs.docker.com/build/building/multi-stage/),
[tmpfs mounts](https://docs.docker.com/engine/storage/tmpfs/),
and pinned Docling [CodeFormulaVlmModel v2.141.0](https://github.com/docling-project/docling/blob/v2.141.0/docling/models/stages/code_formula/code_formula_vlm_model.py).
