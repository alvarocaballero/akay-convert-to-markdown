# Embed and replace point sets locally (N10)

N10 implements an Azure OpenAI embedding adapter and a Qdrant point-set API over
N9's saved-artifact chunking. **Locally verified is not production integrated.**
N11 supplies [durable ordering and queue delivery](content-processing-ordering.md).
Without explicit runtime configuration the entry still exits 2 before clients.

| Status | Evidence or remaining input |
| --- | --- |
| Approved initial selection | AzureOpenAI, `text-embedding-3-small`, 1536 dimensions, `cl100k_base`. No model revision was selected. |
| Implemented | Configurable Azure REST/authentication; local tokenizer; immutable profile and collection-space bindings; bounded embedding/upsert batches, UUID points and scoped tail cleanup. |
| Locally verified | Stub vectors and persistent Qdrant client local mode, final N9A document/review and corrected transcripts, actual offline tokenizer and HTTPX MockTransport. |
| Pending Azure | No resource or embedding deployment exists. Provisioning, actual endpoint/deployment/authentication, quotas and authorized live verification remain pending. |
| Ordered runtime | N11 adds durable admission, in-flight acknowledgement barriers, scoped delete/reassignment and callback replay. Uncertain mutations block takeover for explicit recovery. N12 verifies isolated installs; N13–N15 own images/CI/deployment. |

## Local checks

Use the full-development setup in [README](../README.md#local-setup) for this suite,
which also verifies final document artifacts. For an index-only runtime, use its
separate lock from the [packaging guide](content-processing-packaging.md).

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_content_indexing.py -q --tb=short
```

These default tests forbid external network connections, use synthetic settings
and embeddings, and exercise actual **qdrant-client 1.19.1** persistent local mode.
Their test counter is explicitly synthetic; it is not the production tokenizer.
The separate check below uses the actual approved tokenizer with network blocked.

Prefetch the public tokenizer data **before** testing/processing, into a controlled
local path. This downloads static vocabulary data, not model weights or embeddings:

```powershell
Test-Path -LiteralPath ".local" && curl.exe --fail --silent --show-error --output ".local/cl100k_base.tiktoken" "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
.venv\Scripts\python.exe docs/checks/content_processing_n10_probe.py --tokenizer ".local/cl100k_base.tiktoken"
```

The ignored asset is read-only during the probe. Its required SHA-256, copied
from **tiktoken 0.12.0**, is:
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`.
Missing/corrupt assets fail transiently without looking in ambient caches or
downloading. The probe compares token IDs against the pinned upstream encoding
constructor for Unicode, whitespace and special-looking strings, then indexes
actual rebuilt document artifacts and corrected transcript JSON with stub vectors
and local Qdrant. It reopens the database to verify persistence and removes only
its temporary database/files. No Azure settings or credentials are discovered.

## Azure configuration and authentication

`config.indexing_settings.AzureOpenAISettings` loads these settings only when
explicitly constructed. There is no `.env` file, resource-name lookup or auth
fallback. Other workers do not require these values. The N11 index entry requires
them together with its explicit technical-state/Qdrant/profile configuration.

| Environment variable | Requirement / behavior |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Required HTTPS resource origin; no credentials, path, query or fragment. No default. |
| `AZURE_OPENAI_DEPLOYMENT` | Required actual deployment name, matching the approved profile snapshot. No default. |
| `AZURE_OPENAI_AUTH_MODE` | Required `apiKey` or `entra`. |
| `AZURE_OPENAI_API_KEY` | Required secret only for `apiKey`; excluded from settings repr. Must be absent for `entra`. |
| `AZURE_OPENAI_API_VERSION` | Pinned supported REST version `2024-10-21`. |
| `AZURE_OPENAI_TIMEOUT_SECONDS` | Finite positive per-attempt HTTP timeout; default 30. |
| `AZURE_OPENAI_RETRY_COUNT` | 1–10 attempts; default 3. |
| `AZURE_OPENAI_RETRY_DELAY_SECONDS` | Exponential delay with 30-second cap; default base 1. |
| `AZURE_OPENAI_BATCH_SIZE` | 1–2048 inputs per HTTP call; default 32. |
| `AZURE_OPENAI_MAX_BATCH_TOKENS` | Aggregate token bound, at most 300000; default 65536. |
| `AZURE_OPENAI_MAX_RESPONSE_BYTES` | Bounded response body; default 16 MiB. |

`indexing.azure_embeddings.AzureOpenAIEmbeddings` is an async context manager over
the existing pinned **HTTPX 0.28.1**. It posts float-format inputs/dimensions to
`/openai/deployments/{configured-deployment}/embeddings?api-version=2024-10-21`.
It uses `api-key` or an explicitly supplied async `token_provider` returning a
Bearer token. The caller must configure authorized token acquisition, correct
resource audience, refresh and credential lifetime. The adapter never constructs
`DefaultAzureCredential`, reads developer credentials or falls back between modes.

HTTP proxy/environment trust and redirects are disabled. Missing Entra acquisition
fails before HTTP. Deployment/profile mismatch fails before mutation or HTTP.
Retries cover transport failures, 408, 429 and 5xx. Ordinary rejected requests fail
permanently; 401/403/404 are safe retryable *configuration* failures without a tight
local retry loop. Cancellation propagates. Raw responses, credentials and input
text are not included in adapter errors or logs.

## Profiles, tokenizer and local API

The caller supplies all effective `IndexProfile` fields from controlled immutable
configuration to `indexing.profiles.ProfileCatalog`. Its ID, collection, distance
and chunk policy have no production defaults. Keep used snapshots in that
configuration: a changed model/deployment/dimensions/tokenizer/policy requires a
new profile ID. `resolve` compares the complete request snapshot, not dimensions
alone. Unknown profiles/providers and any unapproved model revision are rejected.

Construct `Cl100kTokenizer.from_file(explicit_path)` for the real adapter/indexer.
It implements Core's `BaseTokenizer`, treats special-looking input as ordinary
text, and never adds query/document prefixes. The selected model's limit is
8192 tokens per input. N9 counts the **entire contextualized string** through
splitting/merging; the Azure adapter checks it again and also limits aggregate
batch tokens. No silent truncation or model/tokenizer substitution occurs.
Query-side consumers must use compatible tokenization/context preprocessing and
the same embedding space; Python does not implement the .NET query path.

Compose `PointSetIndexer(catalog, embeddings, QdrantPointStore(explicit_client),
tokenizer=..., tokenizer_id="cl100k_base")`, then call its async
`index(request, saved_json_bytes, review_raw=...)`. Supply review bytes for
`fromReview`. After a rebuild completes, reload the updated JSON and review at the same paths;
corrected transcripts are read as saved, without Speech or source reconversion.
The caller owns authenticated bounded Blob reads, authorization and when approved
artifacts may be indexed. The API snapshots/revalidates mutable nested metadata
before its first await, and runs CPU chunking through existing cancellation drain.

`QdrantPointStore` receives an explicit client: it does not default to localhost,
discover a URL or read Qdrant credentials. Target collection names must match the
controlled catalog. New collections store technical `akayIndexV1` metadata with
the embedding-space binding and full used profile snapshots. Existing unbound or
incompatible collections are rejected, not adopted because dimensions match.
The binding includes endpoint, deployment, model/revision, tokenizer, dimensions
and preprocessing; moving endpoints conservatively requires a compatible new
target/migration decision. It cannot detect undisclosed changes to remote weights.
Metadata is technical state, not a domain table, public artifact or fingerprint.

## Replacement and completion boundary

- Point IDs are UUIDv5 in the namespace derived from URL namespace and
  `urn:akay:content-indexer:point:v1`. The name is compact UTF-8 JSON
  `["point-v1", scopeKey, contentKey, profileId, chunkIndex]`, with no request ID,
  sequence, title or domain parsing. Distinct scopes/contents/profiles do not mix.
- Payload retains scope/content/profile/sequence, clean and contextualized text,
  section/path/internal headings, technical source, original origin, resource
  name and item/page/segment/time provenance. Caller metadata is nested and cannot
  replace technical fields. No image/video binaries are stored.
- Validate vector count/order/model, dimension, finite numeric values and float32
  normalizability. Booleans, zero vectors and overflow/underflow are rejected.
- Ensure keyword indexes for scope/content/profile/section and integer indexes
  for chunkIndex/operationSequence. The local engine explicitly does **not**
  accelerate payload indexes; tests verify API requests, not server index behavior.
- Upsert deterministic chunks in bounded batches with `wait=True`. Then delete
  only the exact scope/content/profile's tail (`chunkIndex >= newCount`). A shorter
  set leaves no stale tail; changing section context overwrites the same IDs.
  Other content/profile/scope points survive. No Blob deletion is involved.
- Require `UpdateStatus.COMPLETED` on indexes/upserts/cleanup before returning
  the existing `content.indexing.completed` event with profileId/chunkCount.
  Returning the event does not send a webhook. The caller owns result delivery.

Calls must be externally serialized. The API is not an atomic multi-batch swap:
partial points may be visible after failure, but no completed result is returned.
Retry under serialized ownership converges, including lost responses. Direct
repeated calls may regenerate embeddings. Durable confirmed-outcome reuse,
cross-replica profile registration, stale operations and callback-only replay are
provided by the separate N11 coordinator. Its durable mutation acknowledgement
barrier blocks uncertain takeovers; Blob leases alone cannot fence Qdrant. Do not
bypass that coordinator with concurrent direct N10 writers on the same target.

## Exact API evidence and remaining external checks

- [Azure REST 2024-10-21 embeddings](https://learn.microsoft.com/azure/ai-foundry/openai/reference#embeddings)
  — deployment path, dimensions and float output; no migration to a speculative SDK.
- [Azure embedding limits](https://learn.microsoft.com/azure/foundry/openai/how-to/embeddings#best-practices)
  — 8192 per input, 2048 inputs and 300000 aggregate tokens; actual quota is pending.
- [Qdrant client 1.19.1](https://github.com/qdrant/qdrant-client/tree/v1.19.1)
  — actual installed async create/update collection metadata, indexes, filters,
  UUID upsert/delete/wait signatures and persistent local behavior were checked.
- [tiktoken 0.12.0 encoding source](https://github.com/openai/tiktoken/blob/0.12.0/tiktoken_ext/openai_public.py)
  — cl100k_base data/hash/pattern/IDs; actual local loading and counts verified.

No production Azure integration, semantic retrieval quality, remote deployment
model identity, real quota/RBAC/token audience, Qdrant-server index acceleration,
network/replica behavior or container build is claimed from these local checks.
N12 separately verifies clean Windows target installs. See
[progress](docling-rag-progress.md) for exact commands and results.
The next implementation task is **N13 only**, in a fresh session.
