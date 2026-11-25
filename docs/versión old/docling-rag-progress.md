# Docling / RAG implementation progress

## Current checkpoint — 2026-11-12

**T0: pending.** Repository baseline and selected dependency APIs checked;
section-marker syntax received, identifier rules remain to be confirmed.
T1-T14 have not started.
Details: [T0 inputs and dependency evidence](docling-rag-t0-inputs.md).

### Decisions recorded

- Select Docling/docling-slim `2.141.0` and docling-core `2.99.0` as the exact API
  baseline for Python 3.12. Incorporation requires future HTTPX `0.28.1` and
  pydantic-settings `2.14.0` pins; keep Pydantic `2.10.4` in the verified set.
- Preserve the plan's additive contracts, opaque payload, separate acceptance
  trigger and unchanged media behavior. No semantic tags, embedding provider or
  Azure/GHCR destination is inferred from examples.
- Use relative image artifact directories; normalize portable publication URIs.
  Keep unknown confidence absent/null. Record the limited OCR repair support
  rather than inventing an unsupported setting.
- User confirmed paired HTML comments `section:start` / `section:end` with a
  matching `id`, explicitly requesting the shorter `section` name. Preserve the
  supplied example in [the marker fixture](fixtures/section-markers.md).
  Identifier generation/stability and general boundary rules remain open.

### Checks and observed results

Run from the repository root with the existing `.venv`:

| Check | Observed result |
| --- | --- |
| `git status --short` before work | `?? docs/`; existing documentation preserved. Baseline `f03c7a4`. |
| `.venv\Scripts\python.exe --version` | Python 3.12.10. |
| `.venv\Scripts\python.exe -m pip check` | No broken requirements found. |
| `.venv\Scripts\python.exe -m pytest` | **278 passed, 3 skipped in 13.17s** (281 collected). |
| Integration skips | Azure integration opt-in disabled; FFmpeg/FFprobe unavailable on PATH; Speech credentials absent. No live integration run. |
| Existing pins + selected Docling/core dry-run | Expected failure: core requires `pydantic-settings>=2.14.0`, conflicting with `2.7.1`. Metadata also shows standard requires HTTPX `>=0.28`. |
| Revised pins dry-run | Successful Windows/Python 3.12 resolution with Docling RapidOCR extra, selected core, HTTPX/settings replacements, existing Pydantic and Azure client pins. No installation into the project. |
| Isolated exact-version API probe | Passed options/defaults, grade availability, repeated-heading identity, referenced picture export and JSON reload. Synthetic structure only; no inference/models or chunking. |
| Isolated `pip check` | No broken requirements found. |
| `git diff --check` and `git diff --no-index --check -- NUL <new-file>` for all three new files | No whitespace errors; only the repository's LF-to-CRLF notices. Final status shows no tracked application/configuration changes. |

Successful resolution command (append to `.venv\Scripts\python.exe -m pip install`):

```text
--dry-run --ignore-installed --no-cache-dir --only-binary=:all: docling[rapidocr]==2.141.0 docling-core==2.99.0 httpx==0.28.1 pydantic-settings==2.14.0 pydantic==2.10.4 azure-identity==1.20.0 azure-servicebus==7.14.0 azure-storage-blob[aio]==12.24.1
```

For the reproduced conflict, the same dry-run used `docling==2.141.0`,
`docling-core==2.99.0`, `httpx==0.27.2` and `pydantic-settings==2.7.1`.

The isolated probe environment is outside the checkout at
`%LOCALAPPDATA%\Temp\opencode\akay-docling-t0-api`. Its first install timed out;
the completed retry and subsequent package/API checks succeeded. It installed
`docling-slim==2.141.0 docling-core==2.99.0 pydantic==2.10.4 pydantic-settings==2.14.0`,
without model extras. To repeat with an existing isolated Python 3.12 environment:

```powershell
& "$probePython" -m pip install "docling-slim==2.141.0" "docling-core==2.99.0" "pydantic==2.10.4" "pydantic-settings==2.14.0"
& "$probePython" "docs/checks/docling_t0_api_probe.py"
& "$probePython" -m pip check
```

`$probePython` must point at that isolated environment's Python, not the project's.
The exploratory probe first exposed absolute/local URIs with an absolute
`artifacts_dir`, then a Windows JSON/Markdown separator difference. The final
check uses a relative directory and compares normalized URI separators.
Unknown confidence emits an upstream NumPy warning; the check filters only that
expected warning after asserting NaN/`unspecified` behavior.

Not run: real Docling PDF/OCR inference, model downloads, Linux/CPU image builds,
HybridChunker/token limits, embeddings, Qdrant, Azure calls, publishing or deployment.
These are not reported as successful T0 extraction or end-to-end checks.

### Remaining T0 work and next-task blockers

1. Complete the marker specification: confirm identifier generation/stability and
   general section-boundary rules. Syntax and reference example are now recorded;
   semantic labels have not been specified. Freeze the affected review contract.
2. Confirm production embedding provider/model/deployment/dimensions and complete
   the technical profile, fingerprint rules and explicit indexing/security scope.
3. Finish versioned review/index schemas, fixture messages and webhook examples.
   These remain T0 deliverables; this checkpoint does not freeze incomplete schemas.
4. Confirm deployment inputs or keep each external input explicitly pending for
   its dependent task. Azure inputs do not block local converter work, and the
   embedding provider does not block the converter.

The user restricted this run to T0. Do not proceed to T1 while waiting for input.
Changes in this checkpoint are documentation and an isolated API-check script;
application source, project pins, README, Docker and workflows retain their baseline.

### Marker clarification checkpoint — 2026-11-12

- Added the user-supplied Markdown fixture using `section` in all six delimiters.
- Manually checked three distinct IDs, three matching start/end pairs and the
  unmarked subheading retained inside the third section.
- Content search found only the confirmed `section` delimiters, with no old
  prefixed marker name. Whitespace checks passed; only LF-to-CRLF notices appeared.
- Documentation/fixture change only; the earlier 278-pass baseline remains the
  recorded runtime result. No converter behavior or new parser was implemented.
