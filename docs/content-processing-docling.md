# Docling extraction: local API and current limits

N3 replaces the document adapter in both document-capable entries. Six model-free
formats and real offline PDF/table/figure/code/formula extraction are exercised.
**N3 integration is complete.** ConvertToMarkdown invokes Docling with selected
options, retains returned data and handles errors/statuses. Spanish scanned OCR
has observed accent errors; the other six languages have no measured OCR quality
yet. Repairing the engine or guaranteeing character-perfect recognition is outside
N3, as clarified by the user and recorded in the specification.
See [progress](docling-rag-progress.md) for exact checks and remaining evidence.

## Runtime boundary

- `DocumentConverter.convert(Path) -> str` remains compatible with the legacy
  Markdown-only processor. Both document and mixed entries use Docling, with no
  parser fallback. N12 removes the retired MarkItDown adapter, dependency and its
  adapter-only tests; the Docling extraction/compatibility tests remain.
- `DoclingDocumentConverter.extract(Path, DocumentOptions)` returns an
  `ExtractedDocument` with the full `ConversionResult`, structured `document`,
  raw `confidence` and typed warnings. It does not interpret contentKey/payload
  or assign principal sections. The separate [N4 artifact exporter](content-processing-review.md)
  adds section mappings and normalized confidence to a local review package.
- `ExtractedDocument.export_referenced(fresh_directory)` writes only local
  `document.md`, `document.docling.json` and figure/table crops under `images/`.
  It clears page renders on a copy, accepts only materialized data-image content,
  and does not resolve arbitrary local/remote image references. JSON URIs use `/`;
  Core reload may represent them as platform-native `Path` objects.
- The dedicated document entry now uses N4's exporter and N5's
  [complete-set publication](content-processing-publication.md) for version-one
  jobs with explicit technical storage configuration. The mixed entry remains
  legacy Markdown-only. A standalone local export does not send a success webhook.

## Pinned extraction API

| Dependency | Pin |
| --- | --- |
| docling-slim (provides the `docling` modules) | `2.141.0` |
| docling-core | `2.99.0` |
| docling-parse | `7.26.0` |
| RapidOCR | `3.10.0` |
| HTTPX | `0.28.1` (required by the retained Docling baseline) |
| Pydantic / pydantic-settings | `2.10.4` / `2.14.0` |

N12 retains this API baseline using granular slim extras instead of the broader
`docling` metapackage. It adds separate Windows/Linux CPU dependency locks and a
portable model-file lock; see the [packaging guide](content-processing-packaging.md).
Clean Windows installation and offline model loading pass. N13/N14 verify Linux
image/non-root model loading and inference within the documented quality limits;
see [images](content-processing-images.md). Engine versions are read from `docling-slim`.

## PDF configuration and offline operation

Supply `DOCLING_ARTIFACTS_PATH` for the document/mixed entries. The local adapter
accepts `artifacts_path`; its constructor does not read environment variables.
The media/index entries do not load this setting. The former global
`DOCLING_OCR_LANGUAGE` setting and constructor argument are retired: OCR selection
comes exclusively from `DocumentOptions.ocr_language` / wire `ocrLanguage`.

Allowed selections are `es/eu/gl/ca/fr/en/de`; default `es` is an explicit contract
decision. Null/empty/unsupported/wrong-type values fail validation. Each request
maps to one `RapidOcrOptions.lang=["iso:<language>"]` entry (canonicalized by Docling
to `iso:<language>-Latn`), never seven entries or another language's fallback.
This is document OCR, not translation or Speech. Legacy Markdown-only conversion
uses `DocumentOptions()` and therefore Spanish. Version-one jobs in the dedicated
document entry preserve each request's options through extraction and publication.

The PDF engine is `StandardPdfPipeline` / `ThreadedDoclingParseDocumentBackend`.
It enables accurate tables, heading hierarchy with retained parsed pages,
RapidOCR `onnxruntime` in `PDF_AWARE_LAYOUT_REGIONS` mode, and picture crops.
Page-image export, picture classification/description, chart extraction, remote
services and external plugins are disabled. HTML/Markdown resource fetching is
disabled; HTML preamble stays in the body. No document links are crawled.

Each extraction creates a fresh engine restricted to the source extension's
format. Restricting the global format list alone was insufficient: Docling can
recognize renamed PDF bytes in an `.md` file. Such mismatches now fail before
initializing another format's models. TXT uses the pinned Markdown backend.

PDF models are initialized **before** opening native parser threads. An observed
Windows access violation in `docling_parse_backend.unload` followed model
initialization failure after parsing had started; eager initialization removes
that failure ordering. Missing/incompatible local assets raise retryable
`DocumentModelConfigurationError`. This is not proof that all native parser
failure paths are safe; controlled model-backed inference is described below.

## Options, outcomes and cancellation

| Case | Behavior |
| --- | --- |
| Four code/formula flag combinations | Real offline PDF fixture passes all four. Enabled formula recognition yields LaTeX; disabled recognition exports the upstream placeholder. Enabled code recognition restores line breaks; this does not certify executable code correctness. |
| Code/formula requested on other formats | Native content retained; `ENRICHMENT_NOT_APPLICABLE` warning, not a pretend model run. |
| Source image without a materialized crop | `IMAGE_NOT_MATERIALIZED` warning; no arbitrary file/network fetching during export. |
| Empty extraction, partial/failure status, or reported conversion errors | Safe `DOCUMENT_CONVERSION_FAILED`; no upload/completed callback. Partial text is not treated as a successful document. |
| Missing/uninitializable PDF model configuration | Transient error before source processing; no permanent failed webhook for missing operator assets. |
| Cancel, timeout or runner shutdown | Keep awaiting the executor future until inference/export actually stops, then propagate cancellation. No source cleanup, upload or notification while inference still owns its inputs. |

Draining is not a hard-kill deadline: an unresponsive native call can delay
timeout/shutdown. Whole-workflow lock budgets and termination policy still need
N8 evidence. Executor futures are intentional: cancelling every asyncio Task
at runner shutdown would also cancel a shielded `to_thread` Task without stopping
its underlying writer.

There is no `replace_broken_text_layer` option in the pinned API. Empty/partial
results fail explicitly; a successful but incorrectly decoded text layer cannot
be diagnosed universally. The controlled corrupt-overlay fixture invokes OCR and
exports/reloads its result successfully; Spanish accent fidelity is imperfect.
This observation is not a guarantee of universal text-layer repair.
Web backends represent h1 as `TITLE` and
h2 as `SECTION_HEADER(level=1)`; consumers must preserve upstream structure,
not infer that every visible heading is a section-header item.

## Integration verification and engine limitations

Default tests exercise real DOCX/PPTX/HTML/HTM/TXT/MD extraction with network
traps, repeated/nested headings, preamble and tables; real Core picture export
and reload; result policies; option isolation; and repeated cancellation,
processing timeout and `asyncio.run` shutdown using local inference doubles.
These tests do not establish PDF extraction quality or a production OCR language.

`tests/integration/test_docling_models.py` has thirteen integration cases plus two
separately enabled optical-quality diagnostics. Integration requires
`RUN_DOCLING_MODEL_TESTS=true` and `DOCLING_TEST_ARTIFACTS_PATH`; socket and requests
access is blocked, with Hugging Face/Transformers offline mode. No live services,
downloads or library reinstall were used.

| Evidence | Observed result |
| --- | --- |
| Actual RapidOCR initialization for each of `es/eu/gl/ca/fr/en/de` | All seven pass with local weights and selected native code preserved. This measures availability/loading, not recognition quality. |
| Real Spanish scanned PDF, with and without corrupt text overlay | Two integration cases pass: raster text reaches OCR, confidence is available, Markdown exports and JSON reload preserves returned text. No correction of upstream recognition output. |
| Real Spanish native PDF, all four code/formula combinations | Four pass: heading hierarchy, table data, actual code/formula output, figure PNG/link export, JSON reload, no page image references. CPU calls measured 44.69s / 234.84s / 215.98s / 384.27s in the final four-case run. Not an image-size/memory benchmark. |
| Real raster-only Spanish page | Strict text assertion fails: accents become e.g. `fotosūntesis`, `energa`, `diøxido`, `oxøgeno`. No post-hoc replacement or weaker assertion. |
| Spanish page with deliberately corrupt invisible text overlay | Also fails accent fidelity. This fixture does not establish universal repair of corrupt text layers. |
| Real OCR quality for `eu/gl/ca/fr/en/de` | Not tested; resource compatibility is not a quality claim. |

The strict quality assertions are retained with the separate explicit
`RUN_DOCLING_QUALITY_DIAGNOSTICS=true` opt-in, not converted to xfail or reported as
passing. Their prior accent-fidelity failures remain recorded. They measure
upstream optical quality and do not gate N3 integration acceptance. No OCR/model
repair, post-hoc text correction or new quality guarantee is included. N4 now
provides [principal sections/review](content-processing-review.md), and N5 adds
[complete-set publication](content-processing-publication.md). Current task status
and next work are recorded in [progress](docling-rag-progress.md).

## Reuse of the explicitly authorized local caches

The authorized Hugging Face hub was inspected read-only. No configured project
model path was set. `.venv-docling` was absent under this repository; the existing
`.venv` already contained the pinned versions. The hub root itself is **not** an
`artifacts_path` bundle. The helper below audits and copies only needed files to
an ignored, explicit local verification directory, leaving snapshots unchanged:

```powershell
.venv\Scripts\python.exe docs/checks/content_processing_n3_models.py --hf-cache "C:\Users\alvaro.caballero\.cache\huggingface\hub" --rapidocr-models ".venv\Lib\site-packages\rapidocr\models" --stage ".local\docling-n3\models"
$env:RUN_DOCLING_MODEL_TESTS = "true"
$env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
$env:DOCLING_TEST_ARTIFACTS_PATH = "$PWD\.local\docling-n3\models"
.venv\Scripts\python.exe -m pytest tests/integration/test_docling_models.py -q --tb=short
```

The command runs integration acceptance and skips the two optical-quality
diagnostics. Set `RUN_DOCLING_QUALITY_DIAGNOSTICS=true` to request those diagnostics
too; their known fidelity failures are not integration regressions. Enrichment
tests are CPU-intensive (the unchanged four-case run took 880.09 seconds). For
default regression, set both opt-in flags to `false` explicitly.

| Bundle subdirectory | Existing resources reused |
| --- | --- |
| `docling-project--docling-layout-heron/` | HF snapshot `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` (cached main). |
| `docling-project--docling-models/model_artifacts/tableformer/accurate/` | HF `v2.3.0`, snapshot `fc0f2d45e2218ea24bce5045f58a389aed16dc23`. Fast-mode weights are excluded. |
| `docling-project--CodeFormulaV2/` | HF snapshot `ecedbe111d15c2dc60bfd4a823cbe80127b58af4` (cached main), with tokenizer/processor configuration. Specialized code/formula recognition only, not picture description. |
| `RapidOcr/` | Three existing ONNX files from installed RapidOCR 3.10.0, verified against its registry SHA-256. |

RapidOCR 3.10.0's actual registry resolves all seven requested languages to their
own language code, **sharing the same multilingual PP-OCRv6 small det/rec URLs**
and the PP-OCRv4 orientation classifier. This classifier is an OCR component,
not Docling picture classification. The selected language is still forwarded;
shared weights do not mean that seven language entries are enabled together.

All 19 staged files have local SHA-256 recorded in
`.local/docling-n3/models/local-verification-audit.json` (technical local evidence,
not a published consumer artifact). Cached HF revisions are locally identified;
no online revision lookup was used. ONNX registry matches:

| File | SHA-256 |
| --- | --- |
| `PP-OCRv6_det_small.onnx` | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| `PP-OCRv6_rec_small.onnx` | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |
| `ch_ppocr_mobile_v2.0_cls_mobile.onnx` | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

N12 promotes these same bytes/revisions into the portable, committed
`requirements/document-models.json`, without local cache paths. Its offline
checksum verifier confirms all 19 existing files. All seven OCR selections and
layout/accurate-table/code/formula models also initialize in the clean slim
installation with sockets blocked; that loading check does not remeasure quality.

No required resource was missing for these checks, so no download is proposed.
If future assets are missing, report their exact targeted download command and
destination before running it; do not use an all-model download. N13 still
owns image asset staging, non-root availability and image builds.
Their amended requirements include all seven selections with shared resources
deduplicated; no ASR/Whisper or picture description/classification models.

## Official versioned references

- [Converter / initialize_pipeline / format allowlist](https://github.com/docling-project/docling/blob/v2.141.0/docling/document_converter.py)
- [Pipeline options](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/pipeline_options.py)
- [Heading hierarchy](https://github.com/docling-project/docling/blob/v2.141.0/docs/usage/heading_levels.md)
- [Code/formula enrichments](https://github.com/docling-project/docling/blob/v2.141.0/docs/usage/enrichments.md)
- [Backend resource controls](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/backend_options.py)
- [RapidOCR offline artifact behavior](https://github.com/docling-project/docling/blob/v2.141.0/docling/models/stages/ocr/rapid_ocr_model.py)
- [OCR language selection](https://github.com/docling-project/docling/blob/v2.141.0/docs/concepts/OCR.md), cross-checked against the installed RapidOCR 3.10.0 model registry for the actual shared resources.
- [SimplePipeline](https://github.com/docling-project/docling/blob/v2.141.0/docling/pipeline/simple_pipeline.py)
- [Core image references](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/types/doc/common/reference.py)
- [Core referenced serialization](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/types/doc/document.py)
