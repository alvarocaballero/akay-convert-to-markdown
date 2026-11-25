# Timed Blob media transcription (N6)

`akay-transcribe-media` accepts version-one Blob audio/video jobs, retains Speech
phrases and publishes Markdown, `transcript.json` and `review.json` before its
completed callback. It reuses the existing audio/video strategies, FFmpeg adapter,
Speech REST client and [N5 publisher](content-processing-publication.md).

## Configuration and request

Use the existing Blob, callback and Speech settings, a distinct
`MEDIA_SERVICEBUS_QUEUE_NAME` and both `PUBLICATION_STATE_CONTAINER_NAME` /
`PUBLICATION_STATE_PREFIX`. The technical container must already exist and have
the permissions described in the publication guide. Neither its name nor a Speech
locale/credential is inferred. Partial/blank state configuration fails startup;
absent state settings cause version-one Blob jobs to fail transiently before
source work. Legacy envelopes continue to publish Markdown only.

```json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca002",
  "contentKey": "manual:media-example",
  "source": {"type": "blob", "blobName": "manuals/clip.webm"},
  "destinationBlobName": "manuals/clip.md",
  "contentType": "video",
  "overwriteDestination": false,
  "callback": "configured-result",
  "payload": {"callerData": "forwarded unchanged"}
}
```

The callback identity must be configured locally. `contentType` is `audio` or
`video`. Existing MP3/WAV/AAC/M4A/OGG/OPUS/FLAC and MP4/MOV/MKV/WebM/AVI/M4V/MPG/
MPEG/WMV routing remains available. WebM can contain audio only: the video strategy
still probes once, selects its first audio stream and prepares audio with `-vn`.
There is no visual-video analysis. Unsupported document extensions fail before
source access. N7 now supports explicit `source.type=youtube` video jobs through
the [bounded YouTube adapter](content-processing-youtube.md), reusing this same
transcription/package/publication path.

For this example, the callback contains exactly:

```json
{
  "transcriptJsonBlobName": "manuals/clip.artifacts/transcript.json",
  "reviewBlobName": "manuals/clip.artifacts/review.json"
}
```

These are the `artifacts` fields; `destinationBlobName` still references the
Markdown. No Docling JSON, image inventory, page screenshots or other public
manifest is produced. Conversion does not trigger indexing or domain acceptance.

## Text and temporal rules

| Available Speech data | Produced behavior |
| --- | --- |
| Phrase text | Canonical text for both Markdown and transcript, preserving phrase order and stripping outer whitespace only. No word-level resegmentation or generated chapters. |
| Offset and duration | Nonnegative integer milliseconds; end = offset + duration. The internal legacy seconds API remains available; JSON uses rounded milliseconds, not truncated floats. |
| Missing offset or duration | Nullable start/end; an end is calculated only when both inputs exist. No zero/full-file interval is invented. Review includes `TRANSCRIPT_TIMESTAMPS_UNAVAILABLE`. |
| Measured zero | Retained as zero, including a zero-duration phrase. |
| Speaker | Preserve available integer speaker identity as a string, including `0`; otherwise null. No diarization option is newly enabled. |
| Locale | Preserve each phrase's locale. Top-level language is set only if every phrase has the same available language; mixed/unknown stays null. It is never inferred from configured locale candidates. |
| Full duration | Retain Speech's measured `durationMilliseconds`; absent stays null. FFprobe still enforces the existing pre-transcription duration limit, and the worker checks Speech's measured duration too. |
| Combined text only | Retain as untimed content with the missing-times warning, rather than producing an empty Markdown body. |
| Combined text differs | Retain phrase text consistently in both outputs and add safe `SPEECH_COMBINED_TEXT_DIFFERS`, without embedding raw response content in the warning. |
| Empty/malformed response or invalid ranges | Safe `SPEECH_TRANSCRIPTION_FAILED`; no completed publication. Wrong types, numeric strings, booleans, negative/nonfinite measurements, out-of-order starts and endpoints beyond measured duration are rejected. Overlapping speakers are allowed when starts remain ordered. |

Segments receive stable sequential `segment-0001` IDs within the transcription;
these are not Topic sections. Markdown keeps the existing `Transcripción` heading
and known `HH:MM:SS` display anchors; exact millisecond citations live in JSON.
Untimed phrases have no false timestamp heading. Text remains untrusted content
for the eventual renderer.

Review contains statistical duration, empty sections/tables/images, null page
count/PDF grades, safe warnings and processing engine
`azure-speech-fast-transcription` / configured REST API version. `origin` and
review source retain the original Blob reference, never the extracted local file.

## Publication and recovery

- Dedicated media parsing is strict; document options are not accepted. The mixed
  legacy entry continues to reject version-one jobs.
- Enforce declared and actual downloaded input size, FFprobe duration, no-audio
  and invalid-media failures using existing boundaries. Speech throttling remains
  transient and does not emit a permanent failed callback.
- Publish through N5's leased, conditional complete-set receipt. A legacy Markdown
  alone is incomplete; conflicting destination reuse fails safely. Both overwrite
  modes reuse an already complete matching publication.
- After ready/publication, retry uploads or callbacks without the original file,
  FFmpeg or another Speech call. Receivers must deduplicate repeated callbacks.
- Local JSON writing runs off the event loop using the existing cancellation
  draining primitive, now shared without importing Docling. Cancellation retains
  files and publication ownership until the writer stops, then cleans its attempt.
  [N8 reliability](content-processing-reliability.md) supplies whole-workflow lock
  budgets, global shutdown and stable failure receipts.

## Local verification and API evidence

```powershell
$env:RUN_AZURE_INTEGRATION_TESTS = "false"
$env:RUN_DOCLING_MODEL_TESTS = "false"
$env:RUN_DOCLING_QUALITY_DIAGNOSTICS = "false"
.venv\Scripts\python.exe -m pytest tests/unit/test_media_artifacts.py tests/unit/test_media_processors.py tests/unit/test_ffmpeg_service.py tests/unit/test_transcription.py tests/unit/test_markdown_builder.py -q --tb=short
```

The worker/consumer harness uses real HTTPX **0.28.1** with `MockTransport`, real
Speech normalization and publication, persistent local Blob doubles and a fake
FFmpeg subprocess boundary. It verifies all existing media extensions at routing
level, audio-only WebM copy/transcode commands, exact phrase content/measurements,
callback-only and partial-upload recovery, cancellation and safe failures. These
are not actual codec-decoding or billable Speech measurements.

REST **2025-10-15** fields, multipart request and speaker type were checked against
[the versioned REST reference](https://learn.microsoft.com/en-us/rest/api/speechtotext/transcriptions/transcribe?view=rest-speechtotext-2025-10-15)
and [official usage guidance](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create).
HTTPX APIs were checked against its [0.28.1 transport documentation](https://github.com/encode/httpx/blob/0.28.1/docs/advanced/transports.md)
through Context7 and the installed package. No new Speech SDK, dependency upgrade,
model or locale choice is required. Service limits vary by API/region; the worker's
configured limits are not a claim of service capacity.

Host FFmpeg/FFprobe integration remains skipped; actual decoding/extraction passes
in the [media image checks](content-processing-images.md). Authorized Speech/Azure
and live YouTube interoperability/deployment remain external evidence. See
[progress](docling-rag-progress.md) for exact commands/results and the
[N16 handoff](content-processing-handoff.md) for the complete local media/index flow.
