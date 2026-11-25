# Regenerate artifacts after editing Markdown

The dedicated document worker supports `rebuildFromMarkdown` on its existing
queue. It overwrites the existing Docling JSON and review from edited Markdown,
keeps referenced inventory images and deletes unused ones. It never writes the Markdown.
The local N9 API also consumes corrected transcript text with unchanged citations.
Neither path approves content or sends an index job automatically.

## Consumer integration

1. Convert the source to an initial destination such as `shared/extracted.md`.
   Its sections are provisional while editing is allowed.
2. Edit and save that same `shared/extracted.md`. Freeze it for the request; the
   consumer owns authorization, persistence and editing locks.
3. Send a new document request with a new `requestId`, the same `contentKey`,
    `operation=rebuildFromMarkdown`, and the edited source. Omit `destinationBlobName`
    and `extractionReviewBlobName`. The artifact prefix is `shared/extracted.artifacts/`.
4. Accept only the result of the current approval request. Persist its final
   sections before attaching additional content, then explicitly send the final
   JSON/review references to the indexer. An older extraction callback must not
   replace the final result or unlock editing.
5. Keep approved content immutable. Preparation/index failure remains retryable
   without publishing incomplete content. Subsequent content changes require
   deletion/new upload; existing additional content follows the specification's
   preservation/reassignment policy.

Without edits, reuse the coherent initial artifacts; another conversion is not
required. Editors, authorization, approval states, database writes and the
publication trigger above belong to the consumer/Akay.Be and are **not implemented
by these Python tests**.

The [specification's reconstruction example](content-processing-specification.md#63-reconstrucción-del-markdown-editado)
is validated automatically. Example fields for the existing version-one envelope:

```json
{
  "operation": "rebuildFromMarkdown",
  "source": {"type": "blob", "blobName": "shared/extracted.md"},
  "documentOptions": {"extractSections": true}
}
```

## Storage, identity and publication

| Boundary | Implemented rule |
| --- | --- |
| Draft input | Read only from configured `SOURCE_CONTAINER_NAME`. The producer must freeze bytes per request ID; do not edit a Blob underneath redelivery of the same operation. |
| Current review | Read `<source stem>.artifacts/review.json` from `DESTINATION_CONTAINER_NAME`. Validate document type, exact `contentKey` and image ownership. Accept both conversion and previous-rebuild reviews. If absent, rebuild text artifacts with an empty known image inventory. |
| Destination | Overwrite `document.docling.json` and `review.json` in that same prefix. No new Markdown, extraction report, backup or public generation is created. |
| Images | Keep inventory images still linked in the edited Markdown. Delete only unused inventory entries at exact owned paths. Never enumerate/delete an arbitrary Blob prefix or fetch image resources. |
| Retry | Stage the replacement JSON before deletion/writes. A leased technical receipt records the request and frozen bytes, so partial writes and callbacks resume without parsing again. It is internal retry state, not document history. |
| Identity | A new edit has a new UUID. Same UUID with changed parameters conflicts; replay of an older completed request does not restore its old JSON over a newer rebuild. |

Content keys and matching paths establish consistency within controlled storage;
they are not cryptographic authenticity or permission tokens. Deployment must grant
access only to authorized configured containers and protect current inventories from
untrusted writes. No new configuration, credentials or cloud resource is required
for this local behavior.

## What is regenerated and what is retained

- Use pinned Docling **2.141.0** `InputDocument` plus its declarative
  `MarkdownDocumentBackend` directly. No `DocumentConverter`, extraction pipeline,
  OCR, PDF/layout/table inference, enrichment or image loader is invoked. All image
  fetch options are explicitly false, including local, remote and data resources.
- Use the pinned **Marko 2.2.5** AST to ignore old structural section comments in
  the parser input and resolve image references. Literal markers/headings inside
  code blocks and spans stay content, never domain sections.
- Preserve the source Blob byte-for-byte, including BOM, line endings, comments
  and image links. Parser-only normalization is never uploaded as Markdown.
- Recognize inline/reference-style Markdown images and HTML `img src` links.
  Retain only paths resolving to the current image inventory. Removed, altered,
  remote, local, data, malformed and unknown targets are never fetched or repaired.
- Rebuild headings, section IDs and tables using the current document and existing
  N4 serializer/UUID function. Repeated titles remain distinct. No cross-parser or
  extraction-to-rebuild ID stability is promised. Final review references are what
  N9 validates and uses, including all changes to heading order and text.
- Set final text section/table pages and page count to null, confidence grades to
  null and confidence pages to `[]`. New JSON has no inherited original page or
  coordinate provenance. `processing.operation=rebuildFromMarkdown` identifies
  the update; there is no original-review reference. Retained image entries alone
  can keep their original page provenance.
- Send the same `document.conversion.completed` webhook, with `destinationBlobName`
  equal to the source Markdown name. Only then may the consumer index the current
  JSON/review. Lock editing during indexing; no indexing runs concurrently with edits.

### Actual parser limits

This is Markdown structure reconstruction, not a lossless PDF/layout round trip.
The native parser normalizes text/formatting and represents supported formulas as
literal text rather than running formula recognition. Removed/edited image links
remain in Markdown, but the no-fetch parser has no image bytes to embed in JSON.
The updated inventory contains only referenced existing crops. Markdown cannot
regenerate a deleted crop or create bytes for an arbitrary newly added image link.

Docling 2.141.0 fails to attach rich inline children correctly for setext headings.
The adapter feeds equivalent ATX syntax **only to the parser**, keeping the original
setext spelling in the untouched source. Original/backend heading counts and levels must
map completely before reporting sections; unsupported raw-HTML heading
structures fail safely rather than claiming coherent section mappings. A generic
`MARKDOWN_STRUCTURE_REBUILT` warning records the layout/normalization boundary.

The native backend imports common model/datamodel utility **definitions** through
Docling's package dependencies. Offline fresh-process checks forbid extraction
pipelines/concrete OCR/layout/table/code-formula modules, model/resource fetching
and foreign-service access. N12 separately verifies
[clean target installations](content-processing-packaging.md); N13/N14 verify
[image isolation and non-root Linux checks](content-processing-images.md).

## Corrected transcripts

Before approval the consumer may update only `text` of existing segments selected
by ID, enforcing nonempty text and its size limits. It must preserve segment IDs,
order, origin, speaker and available time boundaries, then save the corrected
`transcript.json` and regenerate Markdown from those same segments. It must freeze
both before sending `index-content`. No retranscription, new media operation,
extra queue or transcriber webhook is needed.

[Corrected fixture](../tests/fixtures/content_processing/corrected-transcript.json)
differs from the N9 original fixture only in segment text. Real HybridChunker
split/merge checks consume its corrected text and preserve the original range
citations. These times locate original audio segments; they do not provide
word-level alignment or promise corrected text is a literal audio quotation.

## Offline verification

`tests/unit/test_reviewed_content.py` exercises the local rebuild, actual native
Markdown/Core APIs, extraction -> edited final artifacts -> N9 chunking, corrected
transcripts, strict contracts, repeated cancellation and the real document
processor/publisher with persistent conditional Blob doubles. Resource loaders and
sockets are trapped; Speech and source extraction are unavailable to reconstruction.
It includes callback-only, partial-write and permanent-failure replay, old
conversion receipt compatibility and repeated rebuilds. `test_artifact_rebuild.py`
checks actual in-place JSON replacement, exact image pruning and unchanged Markdown
bytes/ETag/metadata with persistent conditional Blob doubles.

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_reviewed_content.py tests/unit/test_artifact_rebuild.py -q --tb=short
```

Exact observed RED/GREEN/regression results and pending external checks live in
[the progress record](docling-rag-progress.md). Production embeddings/Qdrant,
actual Azure Blob/queue expiry and .NET editor/state integration remain unverified.
N13/N14's isolated image checks are separate evidence; N16's
[handoff](content-processing-handoff.md) verifies the final local pipeline. Previous
OCR quality observations remain unchanged; rebuilding Markdown does not run extraction models.

### Pinned official API evidence

- [Docling 2.141.0 Markdown backend](https://github.com/docling-project/docling/blob/v2.141.0/docling/backend/md_backend.py)
- [Docling 2.141.0 InputDocument/backend lifecycle](https://github.com/docling-project/docling/blob/v2.141.0/docling/datamodel/document.py)
- [Marko 2.2.5 AST parser/source spans](https://github.com/frostming/marko/blob/v2.2.5/marko/parser.py)
- [Marko 2.2.5 image destination spans](https://github.com/frostming/marko/blob/v2.2.5/marko/inline.py)

Context7 versioned Docling documentation, these official sources and actual
installed signatures/behavior were checked. No dependency install or model/tokenizer
download was needed; all previous library pins are retained.
