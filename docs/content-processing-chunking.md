# Prepare bounded chunks from saved content (N9)

`indexing.chunking.chunk_content` prepares documents and transcripts locally with
Docling Core **2.99.0** HybridChunker and **semchunk 3.2.5**. It reloads saved JSON,
preserves structural sections and citations, and checks the complete embedding
text against an explicitly supplied tokenizer. It never reconverts a source,
runs OCR/ASR, loads model weights or fetches referenced images.

## Local API

Parse an `IndexRequest` with the existing strict contract parser. Supply its
downloaded JSON bytes, a controlled local `BaseTokenizer` instance, its exact
configured identity and, for `fromReview`, the downloaded review bytes:

```python
from akay_convert_to_markdown.indexing.chunking import chunk_content

chunks = chunk_content(request, source_bytes,
                       tokenizer=local_tokenizer,
                       tokenizer_id=configured_tokenizer_id,
                       review_raw=review_bytes)
```

For `fixed`/`none`, omit `review_raw`. The function is synchronous CPU work;
future asynchronous runtime callers must use the existing `drain_on_cancel`
helper and bounded artifact downloads. It returns a fully validated list or a
safe `ChunkingError` (`PermanentError`), never a partial list.

There is no tokenizer default, model-name lookup or asset download. Its supplied
identity must equal `indexProfile.tokenizer`; its declared capacity must cover
`maxChunkTokens`. N9 tests use an explicit **test-only character counter**, with
budgets of 90–300 characters. This is not a selected production tokenizer or
proof of compatibility with a particular embedding model. The separate
[N10 API](content-processing-indexing.md) validates the approved model, tokenizer,
preprocessing and model window together, with an explicit local cl100k_base asset.

## Sections and contextual text

| Context | Assignment and boundaries |
| --- | --- |
| `fromReview` | Require a document review in the same artifact directory. Validate content key, source filename, complete ordered sections, deterministic IDs, hierarchy, titles, item refs and available page numbers against the actual Core document. Partition by structural identity **before** HybridChunker runs. Equal heading strings cannot merge different domain sections. Preamble remains unassigned. |
| `fixed` | Every chunk inherits the supplied section UUID and parent heading path. Preserve internal document headings as additional context. |
| `none` | No domain section is invented. Internal document headings remain available. |

Section UUID generation and heading serialization are shared with N4 in
`conversion/sections.py`; the previous `document_artifacts` imports remain
compatible. Rich inline headings use N4's exact rendered-title fallback; rich
table-cell headings do not create domain sections. Page furniture is excluded.
Markdown comments are never parsed for section identity. Heading-only content
is retained through Core's `always_emit_headings` option.

`text` contains Core's clean serialized body (including its table/list/code
representation). `contextualizedText` joins nonempty parts with blank lines:
domain heading path (` > `), original resource name, internal heading path
(`fixed`/`none`), then body text. `fromReview` already provides that heading
ancestry, so it is not repeated. Scope/content keys, metadata and request IDs
are not added to embedding text.

Counting uses that exact full string during splitting/merging and once again
before returning each chunk. Context overflow fails with
`CHUNK_CONTEXT_TOO_LARGE`; unexpected final overflow fails with
`CHUNK_TOKEN_LIMIT`. Required headings are not silently truncated or discarded.
Core's optional table-header repetition is disabled: its separate line splitter
does not include this complete external context budget. Core still serializes
and splits table content, with table/item/page provenance.

## Citations and identity limits

Each internal `ContentChunk` records its zero-based chunk index, section context,
internal headings, clean/contextualized text, measured token count, technical
source JSON reference, available original origin and provenance. These are not
new public artifacts or webhook fields.

- Documents retain available item refs and page numbers. No page is invented for
  unpaginated content. `fromReview` supplies the original Blob origin. Without
  review, standard Docling JSON supplies a resource filename but no complete Blob
  identity; `origin` stays null rather than reconstructing a path.
- Transcript segments become Core text items in original order. Each contributing
  item maps to the original segment ID, available start/end, language and speaker.
  Splitting a phrase retains its **whole original interval**, not fabricated
  word-level times; merging retains all contributing segment citations.
- An aggregate start/end is available only when every contributing segment has
  that boundary. Otherwise it stays null, while individual known values remain.
  Blob/YouTube origin remains distinct from the technical transcript JSON source.
- Review/mapping checks establish structural consistency, not cryptographic
  authenticity of two same-named originals. Generic saved Docling JSON has no
  embedded consumer `contentKey`. Authorized artifact selection and N5 publication
  receipts remain the source of that association; no extra identity is invented.

Reload validates strict finite JSON with unique keys and the upstream Core schema.
Private source URIs, image objects and local hyperlink targets are not propagated into
chunk context. Local filename/path misuse fails safely. Resource bytes are never
opened, including hostile local/file/HTTP image references.

## Verification and next boundary

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_content_chunking.py -q --tb=short
```

The offline tests use actual pinned Core/semchunk, generated documents/tables,
actual N4/N6 saved packages, resource-access traps and a fresh-process import test
with extraction/cloud packages forbidden and optional model-tokenizer libraries
absent. Detailed RED/GREEN and regression evidence is in
[progress](docling-rag-progress.md).

The index entry exits **2** before credential creation or consumption when adapter
configuration is missing. N10 supplies the embedding/Qdrant API; N11 adds durable
ordering and configured queue delivery. The provider/model/dimensions/tokenizer
are approved, but Azure provisioning/deployment/authentication and live integration
remain pending. N12 verifies [isolated installs](content-processing-packaging.md);
N13-N15 add local image checks and gated CI/deployment preparation. N16's
[handoff](content-processing-handoff.md) connects reviewed final inputs to actual
local ordered indexing and records remaining external verification.

## Exact-version API references

- [Core 2.99.0 HybridChunker](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/transforms/chunker/hybrid_chunker.py)
  — supplied tokenizer, contextual counting, peer merging and overflow behavior.
- [Core 2.99.0 tokenizer interface](https://github.com/docling-project/docling-core/blob/v2.99.0/docling_core/transforms/chunker/tokenizer/base.py)
  and [dependency ranges](https://github.com/docling-project/docling-core/blob/v2.99.0/pyproject.toml).
- [semchunk 3.2.5 usage](https://github.com/isaacus-dev/semchunk/blob/v3.2.5/README.md)
  — callable counter support and treatment of splitting whitespace.
