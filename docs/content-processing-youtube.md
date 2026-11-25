# Bounded YouTube audio transcription (N7)

The dedicated `akay-transcribe-media` entry accepts explicit version-one YouTube
jobs on the existing media queue. It retrieves one audio-only file, reuses
FFprobe/FFmpeg and Azure Speech, and publishes the same Markdown/transcript/review
set as [Blob media](content-processing-media.md). Conversion never starts indexing.

## Configure and send

Install the pinned optional adapter with `pip install -e ".[youtube]"`; use
`pip install -e ".[test]"` for all offline tests, including the adapter. The pins
are **yt-dlp 2025.11.12**, **yt-dlp-ejs 0.3.1**, **Deno 2.5.6**. The extractor's
versioned dependency definition requires that exact EJS release. This fixed
compatibility baseline is not a promise of continued YouTube platform support.
Do not update the extractor alone: rerun its transport/runtime tests with any change.

Use the dedicated media/Speech/callback and paired publication-state settings.
Blob storage remains necessary for output even when input is a URL. No new queue,
Topic, cookie, account or credential is configured for YouTube.

```json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca007",
  "contentKey": "manual:authorized-video",
  "source": {"type": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghijk"},
  "destinationBlobName": "manuals/video.md",
  "contentType": "video",
  "callback": "configured-result",
  "payload": {"callerData": "forwarded unchanged"}
}
```

The ID above is a fixture, not an instruction to contact a real video. Process
authorized material under the platform's applicable conditions. Real YouTube,
Speech and Azure verification requires separate authorization.

## Supported source and limits

| Boundary | Current policy |
| --- | --- |
| Input | HTTPS `youtube.com`, `www.youtube.com`, `m.youtube.com` `/watch?v=<11-character-ID>`, their `/shorts/<ID>` form, or `youtu.be/<ID>`. ASCII video ID `[A-Za-z0-9_-]{11}`. Optional single `t`, `si`, `feature` query values are presentation hints; extraction uses the complete canonical video. |
| Rejected URLs | Playlists, including video URLs containing `list`; `/live`, redirects as input, other paths/hosts/schemes/ports, URL credentials, fragments, duplicate/unknown query fields, escapes, controls, whitespace and local paths. Other public URL forms are not implicitly supported. |
| Video metadata | Exactly the requested ID, non-live (including no archived-live/upcoming streams), public/unlisted availability and a finite positive duration within `MAX_MEDIA_DURATION_MINUTES`. Unavailable, private, age/account/region-restricted or extractor-blocked videos fail explicitly; no access-control bypass. |
| Audio | One direct HTTPS audio-only format (`webm`, `m4a`, `mp3`, `ogg`), highest available reported audio bitrate. No video download, manifest/fragment downloader, DRM, external downloader or generic-site fallback. If no supported direct audio exists, return `YOUTUBE_FORMAT_UNSUPPORTED`. |
| Size | `MAX_INPUT_SIZE_MB` checks declared and actual audio bytes. Streaming refuses a block before writing beyond the input limit, removes partial downloads and detects incomplete bodies. Source metadata is not trusted as proof of size/duration. FFprobe validates measured duration before Speech; Speech duration is checked again. |
| Time | `YOUTUBE_TIMEOUT_SECONDS`, positive finite seconds, default **300**; covers child startup, extraction, JS and download. Individual HTTPS socket waits are at most 10 seconds. Existing whole-process/Speech/FFmpeg budgets also apply. |
| Temporary storage | `YOUTUBE_MAX_TEMP_MB`, positive integer, default **256**. A fresh attempt-owned directory includes audio and Deno cache; usage is monitored every 50 ms and checked on completion. Audio has its separate strict streaming cap. Polling is an application rejection limit, not an OS filesystem quota: a cache write can briefly exceed it before termination. Container volume/resource enforcement belongs to N13. |
| Metadata/network budget | At most 64 HTTPS hops, four redirects per fetch, 8 MiB per metadata response and 16 MiB total metadata. Compressed responses are rejected rather than decompressed without a bound. |

## Network and process boundary

- Only the YouTube video extractor is registered, with plugins, disk cache,
  netrc, cookie files, geo bypass and remote EJS component fetching disabled.
  EJS scripts come from the installed package; Deno comes from its pinned wheel,
  not a message or arbitrary PATH command. The existing mixed worker remains legacy.
- All extractor metadata/JavaScript and audio HTTPS requests use the guarded
  transport. Allowed destinations are the three YouTube hosts above,
  `youtubei.googleapis.com` and one-label `*.googlevideo.com` CDN hosts. A future
  platform host change requires explicit policy/test changes; no general outbound
  fallback is enabled.
- Every redirect is validated before the next request. Resolve every hop, reject
  **any** non-global/private/link-local/loopback/metadata answer and IPv4-mapped,
  NAT64/6to4/Teredo transition addresses. Connect to the validated numeric IP while
  preserving original hostname SNI and TLS certificate verification, avoiding a
  second hostname lookup. Cookies, Authorization, Proxy-Authorization and Host
  overrides are never forwarded. A suppressed optional unsafe fetch still fails
  the extraction.
- The isolated Python child inherits only Windows OS-path variables when needed
  and explicit attempt-local home/temp/Deno-cache settings. No ambient cloud
  secrets, proxies, browser sessions, user configuration or message arguments are
  passed. Deno's fixed upstream runner uses no remote imports or network/file/env
  grants. No cookies, credentials, shell command or executable options are accepted
  from the request, including opaque `payload`.
- Timeout/cancellation kills and awaits the child process tree (including JS)
  before returning ownership for cleanup. Repeated cancellation drains cleanup.
  POSIX uses a new process group; Windows uses a process tree termination command
  from the OS system directory. No extractor diagnostics/content or signed download
  URLs are exposed in callbacks/logs.

## Artifacts, errors and retry

`source.url` is preserved verbatim in callback, transcript `origin` and review
`source`. Only the extraction request is canonicalized. Review adds an optional
`youtube` object, for example:

```json
{
  "videoId": "abcdefghijk",
  "canonicalUrl": "https://www.youtube.com/watch?v=abcdefghijk",
  "title": "Available resource title"
}
```

Missing title is null; available title is limited to 500 characters and remains
untrusted display content. Non-YouTube reviews have `youtube=null`. No temporary
signed CDN URL, local path or duplicate transcription/image inventory is stored.
Webhook artifact properties remain `transcriptJsonBlobName` and `reviewBlobName`.

| Outcome | Handling |
| --- | --- |
| Invalid envelope/source URL | Existing safe `INVALID_MESSAGE` path. |
| Unsupported/unavailable/private/restricted source | `YOUTUBE_SOURCE_UNAVAILABLE`; definitive failed callback. |
| Unsafe network hop/address | `YOUTUBE_UNSAFE_DESTINATION`; definitive failed callback. |
| Missing direct audio-only format | `YOUTUBE_FORMAT_UNSUPPORTED`; definitive failed callback. |
| Input/duration/time/temp limit | `DOCUMENT_TOO_LARGE`, `MEDIA_TOO_LONG`, `PROCESSING_TIMEOUT`, `YOUTUBE_TEMP_LIMIT`; no completed package. |
| 429/5xx, network interruption, incomplete audio, unavailable/incompatible dependencies | Safe transient error; no definitive failure notification for that delivery. Service Bus redelivery/DLQ policy applies. |

N5's ready/complete receipt is checked **before** extraction. Partial-publication
recovery and callback retry reuse the frozen package without YouTube, FFmpeg or
Speech. No document link is ever crawled automatically.

## Offline evidence and remaining checks

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"
$env:RUN_DOCLING_MODEL_TESTS = "false"
$env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
.venv\Scripts\python.exe -m pytest tests/unit/test_youtube_source.py tests/unit/test_media_artifacts.py -q --tb=short
```

The harness uses the real pinned YoutubeDL/YouTube extractor dispatch with mocked
video extraction and guarded HTTP fixtures; it never contacts YouTube. It executes
both packaged EJS scripts in real Deno with remote fetching and permissions
disabled. Real local child processes demonstrate sanitized environment, timeout,
descendant-writer termination, cancellation and temporary quotas. Media publication
and Speech/FFmpeg use the existing local doubles. See [progress](docling-rag-progress.md)
for exact RED/GREEN/regression results.

Real public-video extraction/challenges/platform compatibility, TLS/DNS interaction
with the real platform, billable Speech and Azure interoperability remain
**unverified**. N12-N14 separately verify installed/image isolation, real media
codec extraction and bundled Deno/EJS offline. N16's [handoff](content-processing-handoff.md)
uses an explicit YouTube retrieval double, not the real platform. Publication and
deployment remain independently authorized external work.

### Version-specific API sources

- [yt-dlp 2025.11.12 dependency pins](https://github.com/yt-dlp/yt-dlp/blob/2025.11.12/pyproject.toml)
- [Embedding API and runtime options](https://github.com/yt-dlp/yt-dlp/blob/2025.11.12/yt_dlp/YoutubeDL.py)
- [Networking Request/Response/error boundary](https://github.com/yt-dlp/yt-dlp/blob/2025.11.12/yt_dlp/networking/common.py)
- [Pinned Deno runner and denied-by-default permissions](https://github.com/yt-dlp/yt-dlp/blob/2025.11.12/yt_dlp/extractor/youtube/jsc/_builtin/deno.py)
- [EJS package version/hash validation and remote-component gates](https://github.com/yt-dlp/yt-dlp/blob/2025.11.12/yt_dlp/extractor/youtube/jsc/_builtin/ejs.py)

Context7 examples were cross-checked against these exact versioned sources and
installed APIs. No default nightly/latest update or job-time dependency download.
