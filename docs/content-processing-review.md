# Local document sections and review packages (N4)

`export_document_artifacts(extraction, request, fresh_directory)` generates the
local document artifact set from N3's `ExtractedDocument` and N2's validated
`DocumentRequest`. It returns `DocumentArtifactResult`. N4 is complete; N5 now
reuses it for [coherent Blob publication](content-processing-publication.md)
and version-one jobs in the dedicated document worker.

## Local API

```python
from pathlib import Path

from akay_convert_to_markdown.contracts.requests import parse_request
from akay_convert_to_markdown.conversion.docling_converter import DoclingDocumentConverter
from akay_convert_to_markdown.conversion.document_artifacts import export_document_artifacts


async def prepare_review(request_json: str, source_path: Path, fresh_directory: Path):
    request = parse_request(request_json, worker="document", callbacks={"local-review"})
    extraction = await DoclingDocumentConverter().extract(source_path, request.document_options)
    return await export_document_artifacts(extraction, request, fresh_directory)
```

The example accepts model-free formats; PDF extraction additionally requires an
explicit compatible `artifacts_path` as documented in the [Docling guide](content-processing-docling.md).
Use `callback: "local-review"` in the example request; this local API does not
invoke callbacks. The caller pairs the extraction with the same source/options
request and owns the fresh directory, including incomplete files after failure.
An existing directory is refused, preserving its contents. Cancellation waits for
the local writer to stop before propagating, reusing N3's draining boundary.

The fresh directory represents the **destination's parent**, not the Blob root.
For destination `topics/25/manual.v2.md`, it contains:

```text
manual.v2.md
manual.v2.artifacts/
  document.docling.json
  review.json
  images/figure-001.png       # only when a materialized crop exists
```

The returned artifact references and review image `blobName` values retain the
full `topics/25/...` paths. JSON image URIs are relative to its sidecar directory
(`images/figure-001.png`); Markdown links are relative to the Markdown
(`manual.v2.artifacts/images/figure-001.png`). Spaces, parentheses, Unicode and
literal percent signs in destination names are URI-encoded correctly.

## Sections and reading order

| Rule | Behavior |
| --- | --- |
| `extractSections=true` | Core's actual heading serializer emits one `akay-section:start` marker immediately before each body heading and records its mapping in review. |
| `extractSections=false` | No generated markers or review sections; ordinary headings remain. Media contracts also retain `sections=[]`. |
| IDs | One `section_id(content_key, docling_item_ref)` function implements N0's fixed UUIDv5 namespace and compact Unicode JSON; titles and request IDs do not participate. |
| Levels | Preserve Core 2.99's rendered hierarchy: `TitleItem` is level 1; `SectionHeaderItem.level + 1` is its Markdown/review level. Level gaps are retained. |
| Parents/order | Nearest preceding lower-level heading; zero-based reading order. Repeated titles retain distinct structural IDs. |
| General content | Content before the first heading stays in the document, with no synthetic section; its section identity is null when assigned later by the indexer. |
| Exclusions | Page headers/footers, furniture-layer headings and headings serialized inside rich table cells do not create sections. |

Markers are generated during structural serialization, without searching or
rewriting heading strings. The Docling JSON is not modified to embed markers;
its original item references remain usable on reload. Re-exporting the same
extraction into another fresh directory produces the same package. Reference
stability is limited to the same source and pinned processing configuration.

## Review and image safety

- Review contains statistical counts, ordered sections, upstream table cells and
  captions/provenance, image inventory, extraction warnings and engine version.
  Table titles absent from the pinned data model remain null; no title is invented.
- Confidence comes from `ConversionResult`, not the Docling document. Available
  per-page component scores/grades and aggregate grades are retained. Absent,
  NaN or infinite scores/grades become null, never fabricated zero. Real zero is
  retained. No probability calibration or quality guarantee is added.
- Pinned Docling exposes component scores without public component-grade
  properties. The adapter uses its exact `_score_to_grade` helper; native
  mean/low aggregates, including flat-report overrides, are preserved. Tests
  protect this version-sensitive boundary.
- Only data-image crops are written with generated `figure-NNN.png` or
  `table-NNN.png` names. Table crop files, when available, also appear in review's
  image inventory; their table record may reference that same Blob. No second
  public image inventory or webhook field is introduced.
- Page image references are cleared on a copy. Source image Path/file/HTTP URIs
  are never dereferenced or exposed; missing crops produce safe structured
  warnings. Private origin paths and local hyperlinks are removed from exported
  technical references. Original text, tables and the extraction object remain
  intact. Source text/captions/cells are untrusted content for the future renderer.
- JSON is finite and revalidated by pinned `DoclingDocument.model_validate`
  without fetching images. The future indexer can consume structure without
  opening local image paths or reconverting the original.

## Verification and next boundary

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_document_artifacts.py -q --tb=short
```

Thirty local cases cover fixed UUID vectors, repeated/nested/rich headings,
principal/additional behavior, preamble, retries, confidence, actual PNGs,
portable references and JSON reload, safe errors, partial-result rejection and
cancellation. The HTML case uses actual N3 extraction/Core serialization; external
services and model inference are not required. Exact RED/GREEN and regression
results are recorded in [progress](docling-rag-progress.md).

The N5 [publication guide](content-processing-publication.md) describes the
dedicated worker integration and separate race/recovery/callback evidence.
Legacy Markdown-only behavior is preserved. Local N4 output alone does not prove
publication or deployment. N6 also reuses that publisher for
[timed Blob media packages](content-processing-media.md), without document sections
or PDF confidence. The current next task is recorded in [progress](docling-rag-progress.md).

## Pinned API evidence

Context7 documentation was cross-checked with the installed pins and official
versioned sources:

- [Core 2.99 Markdown serializer and documented `_format_heading` extension point](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/transforms/serializer/markdown.py)
- [Core 2.99 document traversal, dictionary export and reload models](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/types/doc/document.py)
- [Core 2.99 image URI loading behavior](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/types/doc/common/reference.py)
- [Docling 2.141 confidence fields, aggregation and grading helper](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/base_models.py)
- [Docling 2.141 confidence documentation](https://github.com/docling-project/docling/blob/v2.141.0/docs/concepts/confidence_scores.md)
