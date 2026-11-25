# Install one worker with its locked dependencies

N12 separates the three installation targets while keeping one Python package and
the existing commands. Use a fresh Python **3.12 x86_64** environment and the
matching target/platform lock. Windows installations are verified; Linux locks
are resolved for **glibc >= 2.28**. N13 now verifies their Linux/amd64 images and
offline runtimes; see the [image guide](content-processing-images.md).

## Quick path

Example: install only the media worker on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements/media-windows.txt
.venv\Scripts\python.exe -m pip install --no-deps .
.venv\Scripts\python.exe -m pip check
```

For Linux, substitute `bin/python` and `media-linux.txt`. Select the corresponding
`document` or `index` file for those workers. Install only one target per runtime.
Supply that worker's existing settings before launching its command. No physical
queue, endpoint, model deployment, credential or cloud resource is selected here.

| Install set | Includes | Excludes |
| --- | --- | --- |
| Base | Azure identity/Service Bus/Blob clients, HTTPX, Pydantic/settings | All extraction, media-extractor and indexing engines |
| `document` | Granular Docling slim document/PDF/local-model/RapidOCR extras; Core, parser, CPU Torch/vision, Transformers, ONNX, Marko | Speech/FFmpeg wiring, YouTube, Qdrant, ASR and picture-description/classification weights |
| `media` | Existing Speech HTTP integration, pinned yt-dlp/EJS/Deno | Docling/Core, Torch/ONNX, Qdrant; FFmpeg/FFprobe are system tools supplied separately |
| `index` | Core `chunking-openai`, semchunk, tiktoken, Qdrant, technical Azure clients | Full Docling extraction, Torch, Transformers, ONNX/OCR, YouTube and FFmpeg |

The extras describe dependency ownership; the generated `requirements/*-*.txt`
files lock every resolved runtime dependency and its hashes. Installing a plain
extra alone does not reproduce transitive versions or guarantee CPU selection on
Linux. Use the locks. The `youtube` extra remains a compatible adapter alias;
`test` remains test tooling/adapter fixtures, not an all-runtime installation.
For full development, install the three locks together, then `pip install -e ".[test]"`.
The retained legacy mixed command requires the document/media union. The current
Dockerfile uses exactly that union; it is not three-image acceptance.

## Compatibility choices

- Preserve Docling slim **2.141.0**, Core **2.99.0**, parser **7.26.0**, RapidOCR
  **3.10.0**, ONNX Runtime **1.20.1** and the measured numerical/model stack. Slim's
  feature extras avoid its `standard`, `all`, audio and description-model bundles.
  MarkItDown and its retired adapter-only tests are removed; existing Docling
  format, error, cancellation, export and runtime regressions remain.
- `docling-slim` owns the `docling` import namespace. Both artifact exporters read
  this distribution's version; the `docling` metapackage is no longer required.
- Core 2.99's OpenAI chunking path imports `huggingface_hub` unconditionally from
  its optional Hugging Face module. Pin **1.33.0** in the index set without adding
  Transformers/Torch or invoking its default remote tokenizer. The real local
  `cl100k_base` tokenizer is still required explicitly.
- CPU Torch **2.15.0+cpu** and torchvision **0.29.2+cpu** are bound to exact official
  wheel URLs/hashes in `cpu-wheels.json`. uv 0.11.16's `--torch-backend cpu` does not
  emit that index into requirements output. The compiler verifies its resolved
  version/hash before binding those URLs, so pip needs no extra index or backend
  inference. No CUDA/NVIDIA/Triton packages occur in the target locks.
- The build backend is pinned to Hatchling **1.30.1**. The wheel still registers
  all four existing scripts; installing one target does not make foreign commands
  usable without their dependencies. No runtime package framework was introduced.

## Lock and verify resources without downloads

`requirements/document-models.json` records the 19 files already exercised in N3:
immutable cached Hugging Face snapshot identities, file lengths and SHA-256 for
layout, accurate TableFormer, CodeFormulaV2 and three shared RapidOCR ONNX files.
It contains no local source/cache paths. These are build inputs, not public
conversion artifacts or another image inventory. Snapshot identities came from
the audited local assets, not a new remote model-revision lookup.

Each of `es/eu/gl/ca/fr/en/de` retains its own recognizer selection and shares the
same three OCR weights; Spanish remains the per-request default. Spanish's
observed accent errors remain documented. Quality in **eu, gl, ca, fr, en and de**
is individually unmeasured. Successful model loading is not quality certification.
CodeFormulaV2 uses upstream VLM infrastructure internally for the approved
code/formula features; no picture-description/classification or ASR model is added.

`requirements/index-tokenizer.json` retains the official vocabulary URL and hash
already verified in N10. Reuse the explicit local bundle/tokenizer:

```powershell
.venv\Scripts\python.exe tools/verify_assets.py --document-dir .local/docling-n3/models --tokenizer-file .local/cl100k_base.tiktoken
```

This verifier only reads supplied files and committed locks. It rejects missing,
changed or escaping resources; it never searches ambient caches or downloads.
N13 stages these exact resources and verifies their non-root Linux availability.

## Reproduce packaging evidence

Use uv **0.11.16** and Python 3.12:

```powershell
.venv\Scripts\python.exe tools/lock_dependencies.py --check
.venv\Scripts\python.exe tools/check_installations.py --tokenizer-file .local/cl100k_base.tiktoken --label fresh
```

The first command regenerates all six locks, checks exact bytes and fails on
drift. The second builds the wheel, creates fresh ignored `.local/n12/*-fresh`
venvs, installs hashed dependencies plus that wheel, runs `pip check`, prints
installed distributions/import roots, and exercises startup with service doubles.
Tool processes receive only OS paths, a fresh tool home and explicit public
package indexes. No application credential discovery is permitted. The probes
block sockets except Windows asyncio's internal stdlib loopback socketpair.

The document probe runs real Markdown conversion/reconstruction/Core reload;
the index probe runs real saved-transcript HybridChunker/tokenizer and persistent
local Qdrant. Media composes its real Speech/FFmpeg/YouTube adapters with no live
requests. Target dependencies from the other workers are absent, not merely
hidden with import mocks. An optional document-only check loads existing models:

```powershell
.local\n12\document-fresh\Scripts\python.exe -I tools/target_probe.py document --tokenizer-file .local/cl100k_base.tiktoken --document-models .local/docling-n3/models
```

It initializes seven OCR selections and the PDF pipeline with both enrichment
flags enabled, offline; it does not evaluate new OCR quality. `--resume` on the
installation checker is only for its own interrupted, initially clean labeled
venvs. It does not remove existing directories. On this host uv cache-directory
rename failures required pip installation, and an interrupted pip install was
resumed before recording success. See [progress](docling-rag-progress.md) for exact
observed commands, harness corrections and pending checks.

## Evidence boundaries and next step

Windows wheel installs and N13 Linux/amd64 images verify distribution/import
separation, local engines and locked resources. N13 also records FFmpeg execution,
offline inference, non-root/read-only operation and actual image sizes, with a
separate native Linux formula-layout diagnostic. CI publication, cloud deployment,
termination under production load and live services remain unverified.
The next task is **N14 only**; reuse these locks/images and their explicit inputs.

Official API/package evidence:

- [Docling slim v2.141.0 extras](https://github.com/docling-project/docling/blob/v2.141.0/pyproject.toml)
- [Core v2.99.0 OpenAI chunking extra](https://github.com/docling-project/docling-core/blob/v2.99.0/pyproject.toml)
- [Core's mandatory hub import / optional Transformers](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/transforms/chunker/tokenizer/huggingface.py)
- [uv 0.11.0 platform resolution](https://github.com/astral-sh/uv/blob/0.11.0/docs/concepts/resolution.md), cross-checked with the actual 0.11.16 CLI
- [uv requirements locking/hashes](https://docs.astral.sh/uv/pip/compile/) and [CPU selection](https://docs.astral.sh/uv/guides/integration/pytorch/)
- Official [Torch](https://download.pytorch.org/whl/cpu/torch/) and [torchvision](https://download.pytorch.org/whl/cpu/torchvision/) wheel indexes; filenames and SHA-256 checked directly
