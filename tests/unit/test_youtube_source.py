"""N7: offline source policy, pinned extractor transport and publication reuse."""

from __future__ import annotations

import asyncio
import importlib
import io
import json
import os
import socket
import sys

import pytest
from pydantic import ValidationError

from akay_convert_to_markdown.contracts.artifacts import parse_review, parse_transcript
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError, WebhookError
from akay_convert_to_markdown.models.conversion_result import ProcessingResult
from tests.unit.test_media_artifacts import job, runtime  # reusable offline runtime fixture


URL = "https://youtu.be/abcdefghijk"
CANONICAL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("N7 tests must never resolve or connect to external services")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.parametrize("url", [
    "https://youtube.com/playlist?list=abc", "https://youtube.com/watch?v=abcdefghijk&list=abc",
    "https://youtube.com/live/abcdefghijk", "https://youtu.be/short", "https://youtu.be/abcdefghijk/extra",
    "https://youtube.com/watch?v=abcdefghijk&v=other123456", "https://youtube.com/watch?v=abcdefghijk&cookies=secret",
    "https://youtube.com/redirect?q=http://127.0.0.1", "https://youtu.be/%61bcdefghijk",
    "https://youtube.com/watch?v=abcdefghijk#fragment", "https://youtu.be/abcdefghijk\n",
    "https://youtu.be/abcdefghijk?list=abc", "https://www.youtube.com.evil.invalid/watch?v=abcdefghijk",
    "http://youtu.be/abcdefghijk", "file:///abcdefghijk", "https://user:secret@youtu.be/abcdefghijk",
])
def test_reject_non_individual_and_unsafe_sources_at_contract_boundary(url):
    with pytest.raises(ValidationError):
        job(content_type="video", source={"type": "youtube", "url": url})


@pytest.fixture
def extractor():
    return importlib.import_module("akay_convert_to_markdown.services.youtube_extractor")


@pytest.fixture
def http_api():
    return importlib.import_module("akay_convert_to_markdown.services.youtube_http")


class Reply(io.BytesIO):
    def __init__(self, content=b"fixture audio", status=200, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


def transport(api, replies, *, addresses=("142.250.184.14",), max_bytes=100):
    connections = []

    def resolve(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in addresses]

    def connect(host, address, timeout):
        class Connection:
            def request(self, method, path, body=None, headers=None):
                connections.append((host, address, method, path, headers))

            def getresponse(self):
                return replies.pop(0)

            def close(self):
                pass

        return Connection()

    return api.YouTubeHTTP(max_bytes=max_bytes, timeout=5, resolver=resolve, connector=connect), connections


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.100.100.200",
                                      "::1", "::ffff:127.0.0.1", "fc00::1", "0.0.0.0",
                                      "64:ff9b::7f00:1", "2002:7f00:1::", "2001::1", "224.0.0.1", "ff02::1"])
def test_private_resolved_addresses_never_connect(http_api, address):
    network, connections = transport(http_api, [], addresses=(address,))
    with pytest.raises(PermanentError):
        network.metadata(CANONICAL)
    assert not connections


def test_mixed_dns_answers_fail_closed_and_public_address_is_pinned(http_api):
    network, connections = transport(http_api, [], addresses=("142.250.184.14", "10.0.0.1"))
    with pytest.raises(PermanentError):
        network.metadata(CANONICAL)
    assert not connections
    network, connections = transport(http_api, [Reply(b"metadata")])
    assert network.metadata(CANONICAL)[0] == b"metadata"
    assert connections[0][:2] == ("www.youtube.com", "142.250.184.14")


@pytest.mark.parametrize("target", ["http://www.youtube.com/watch?v=abcdefghijk", "https://127.0.0.1/",
                                      "https://metadata.google.internal/", "https://evil.invalid/", "file:///etc/passwd",
                                      "https://user:secret@www.youtube.com/", "https://www.youtube.com:444/"])
def test_redirects_are_validated_before_following(http_api, target):
    network, connections = transport(http_api, [Reply(status=302, headers={"Location": target})])
    with pytest.raises(PermanentError):
        network.metadata(CANONICAL)
    assert len(connections) == 1


def test_relative_redirect_and_headers_use_guarded_transport(http_api):
    network, connections = transport(http_api, [Reply(status=302, headers={"Location": "/next"}), Reply(b"ok")])
    assert network.metadata(CANONICAL, headers={"Cookie": "secret", "Authorization": "secret", "Host": "evil"})[0] == b"ok"
    assert len(connections) == 2 and connections[1][3] == "/next"
    assert all(not {k.lower() for k in c[4]} & {"cookie", "authorization", "host"} for c in connections)


@pytest.mark.parametrize("declared", [None, "2", "1000"])
def test_download_limits_actual_bytes_not_only_metadata(http_api, tmp_path, declared):
    headers = {} if declared is None else {"Content-Length": declared}
    network, _ = transport(http_api, [Reply(b"01234567890", headers=headers)], max_bytes=10)
    with pytest.raises(PermanentError):
        network.download("https://r1.googlevideo.com/videoplayback?sig=private", tmp_path / "audio.webm")
    assert not (tmp_path / "audio.webm").exists()


def test_download_success_and_truncated_body_detection(http_api, tmp_path):
    network, _ = transport(http_api, [Reply(b"audio", headers={"Content-Length": "5"})])
    network.download("https://r1.googlevideo.com/videoplayback", tmp_path / "audio.webm")
    assert (tmp_path / "audio.webm").read_bytes() == b"audio"
    network, _ = transport(http_api, [Reply(b"bad", headers={"Content-Length": "5"})])
    with pytest.raises(TransientError):
        network.download("https://r1.googlevideo.com/videoplayback", tmp_path / "bad.webm")
    assert not (tmp_path / "bad.webm").exists()


def info(**changes):
    value = dict(id="abcdefghijk", title="Fixture title", live_status="not_live", duration=18.5,
                 formats=[dict(url="https://r1.googlevideo.com/videoplayback?sig=temporary", protocol="https",
                               vcodec="none", acodec="opus", ext="webm", abr=128)])
    value.update(changes)
    return value


def test_pinned_ytdlp_uses_only_our_network_and_youtube_extractor(extractor, monkeypatch, tmp_path):
    import yt_dlp
    from yt_dlp.networking.common import Request

    network_calls = []

    class Network:
        failure = None

        def metadata(self, url, **kwargs):
            network_calls.append(url)
            return b"page", url, {}, 200

        def download(self, url, path):
            path.write_bytes(b"audio")

    def extract(ydl, url, download, process):
        assert url == CANONICAL and download is False and process is False
        assert list(ydl._ies) == ["Youtube"]
        assert not ydl.params["remote_components"] and ydl.params["cachedir"] is False
        assert set(ydl.params["js_runtimes"]) == {"deno"}
        assert ydl.urlopen(Request(CANONICAL)).read() == b"page"
        return info()

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", extract)
    value = extractor.extract_audio(URL, tmp_path, max_bytes=100, max_duration=30, network=Network())
    assert value == {"videoId": "abcdefghijk", "title": "Fixture title", "canonicalUrl": CANONICAL,
                     "fileName": "source.webm"}
    assert network_calls == [CANONICAL] and (tmp_path / "source.webm").read_bytes() == b"audio"


@pytest.mark.parametrize("changes", [dict(_type="playlist", entries=[]), dict(id="other123456"),
                                      dict(is_live=True), dict(live_status="is_upcoming"), dict(live_status="was_live"),
                                      dict(availability="private"), dict(duration=31), dict(duration=None),
                                      dict(formats=[dict(url="file:///tmp/secret", protocol="file", vcodec="none", acodec="opus", ext="webm")]),
                                      dict(formats=[dict(url="https://r1.googlevideo.com/video", protocol="https", vcodec="vp9", acodec="opus", ext="webm")])])
def test_extractor_rejects_unsupported_results_before_audio_download(extractor, monkeypatch, tmp_path, changes):
    import yt_dlp

    class Network:
        failure = None

        def download(self, *args):
            pytest.fail("Unsupported result must not download")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", lambda *a, **kw: info(**changes))
    with pytest.raises(PermanentError):
        extractor.extract_audio(URL, tmp_path, max_bytes=100, max_duration=30, network=Network())


async def test_youtube_runtime_publishes_stable_origin_and_retries_notification_only(runtime, monkeypatch):
    from akay_convert_to_markdown import media_main

    calls = []

    class Adapter:
        async def download(self, source, directory):
            calls.append(source.url)
            directory.mkdir()
            path = directory / "source.webm"
            path.write_bytes(b"audio only")
            return path, {"videoId": "abcdefghijk", "title": "Fixture title", "canonicalUrl": CANONICAL}

    monkeypatch.setattr(media_main, "YouTubeService", lambda _: Adapter(), raising=False)
    request = job(content_type="video", source={"type": "youtube", "url": URL})
    runtime.webhook.error = WebhookError("retry")
    with pytest.raises(WebhookError):
        await runtime.build().process(request)
    runtime.webhook.error = None
    assert await runtime.build().process(request) is ProcessingResult.COMPLETED
    assert calls == [URL] and len(runtime.calls) == 1 and not runtime.storage.downloads
    event = runtime.webhook.calls[0][1]
    assert event["source"] == {"type": "youtube", "url": URL}
    refs = event["artifacts"]
    transcript = parse_transcript(runtime.blobs.data[("markdown", refs["transcriptJsonBlobName"])][0])
    review_bytes = runtime.blobs.data[("markdown", refs["reviewBlobName"])][0]
    review = parse_review(review_bytes)
    assert transcript.origin == request.source and review.source == request.source
    assert review.youtube.video_id == "abcdefghijk" and review.youtube.title == "Fixture title"
    assert b"temporary" not in review_bytes and not list(runtime.settings.temp_directory.rglob("*"))


async def test_subprocess_timeout_and_cancellation_are_drained(extractor, tmp_path):
    service_api = importlib.import_module("akay_convert_to_markdown.services.youtube_service")
    from tests.helpers import make_settings

    settings = make_settings()
    settings_data = settings.model_dump()
    settings_data.update(youtube_timeout_seconds=0.1)
    from akay_convert_to_markdown.config.settings import MediaWorkerSettings
    settings_data.pop("servicebus_queue_name")
    settings_data.update(MEDIA_SERVICEBUS_QUEUE_NAME="media", speech_resource_key="fixture", speech_endpoint="https://speech.invalid")
    settings = MediaWorkerSettings(**settings_data)
    service = service_api.YouTubeService(settings)
    # Real child process, no network/import of an extractor; fake just the command.
    import sys
    service._command = lambda: [sys.executable, "-I", "-c", "import time; time.sleep(60)"]
    with pytest.raises(PermanentError, match="time"):
        await service.download(job(content_type="video", source={"type": "youtube", "url": URL}).source, tmp_path / "timeout")
    settings.youtube_timeout_seconds = 10
    task = asyncio.create_task(service.download(job(content_type="video", source={"type": "youtube", "url": URL}).source,
                                                tmp_path / "cancel"))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._active_process is None


def test_actual_ytdlp_extract_info_with_mocked_extractor_and_guarded_http(extractor, http_api, monkeypatch, tmp_path):
    from yt_dlp.extractor.youtube import YoutubeIE
    from yt_dlp.networking.common import Request

    network, connections = transport(http_api, [Reply(b"fixture metadata"), Reply(b"audio only")])

    def extract(ie, url):
        assert ie._downloader.urlopen(Request(url)).read() == b"fixture metadata"
        return info()

    monkeypatch.setattr(YoutubeIE, "_real_extract", extract)
    result = extractor.extract_audio(URL, tmp_path, max_bytes=100, max_duration=30, network=network)
    assert result["fileName"] == "source.webm" and len(connections) == 2
    assert connections[1][0] == "r1.googlevideo.com"
    assert (tmp_path / "source.webm").read_bytes() == b"audio only"


@pytest.mark.parametrize("status,transient", [(403, False), (404, False), (429, True), (503, True)])
def test_http_failure_classification_is_safe(http_api, tmp_path, status, transient):
    network, _ = transport(http_api, [Reply(b"private diagnostic", status=status)])
    with pytest.raises(TransientError if transient else PermanentError) as error:
        network.download("https://r1.googlevideo.com/videoplayback?secret=signature", tmp_path / "audio.webm")
    assert "secret" not in str(error.value) and "diagnostic" not in str(error.value)


def test_redirect_loop_metadata_budget_and_deadline(http_api):
    network, connections = transport(http_api, [Reply(status=302, headers={"Location": "/next"}) for _ in range(5)])
    with pytest.raises(PermanentError):
        network.metadata(CANONICAL)
    assert len(connections) == 5
    network, _ = transport(http_api, [Reply(b"a" * (8 * 1024 * 1024 + 1))])
    with pytest.raises(PermanentError):
        network.metadata(CANONICAL)
    network, connections = transport(http_api, [])
    network.deadline = 0
    with pytest.raises(PermanentError):
        network.metadata(CANONICAL)
    assert not connections


def test_tls_connects_to_validated_ip_but_verifies_original_hostname(http_api, monkeypatch):
    from types import SimpleNamespace

    calls = []
    raw = SimpleNamespace(close=lambda: None)
    context = SimpleNamespace(wrap_socket=lambda sock, server_hostname: calls.append((sock, server_hostname)) or "tls-socket")
    monkeypatch.setattr(http_api.ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(http_api.socket, "create_connection", lambda address, timeout: calls.append((address, timeout)) or raw)
    monkeypatch.setattr(http_api.http.client, "HTTPSConnection", lambda host, **kwargs: SimpleNamespace(_context=kwargs["context"]))
    connection = http_api._connect("www.youtube.com", "142.250.184.14", 3)
    assert calls == [(("142.250.184.14", 443), 3), (raw, "www.youtube.com")]
    assert connection.sock == "tls-socket"


@pytest.mark.parametrize("url", [URL, CANONICAL, "https://m.youtube.com/watch?v=abcdefghijk&t=12",
                                 "https://www.youtube.com/shorts/abcdefghijk?si=share"])
def test_supported_individual_urls_preserve_original_but_resolve_canonically(url):
    from akay_convert_to_markdown.models.youtube import video_identity

    request = job(content_type="video", source={"type": "youtube", "url": url})
    assert request.source.url == url and video_identity(url) == ("abcdefghijk", CANONICAL)


def test_extractor_does_not_swallow_guard_failure(extractor, monkeypatch, tmp_path):
    import yt_dlp
    from akay_convert_to_markdown.services.youtube_http import YouTubeError

    class Network:
        failure = YouTubeError("unsafe", code="YOUTUBE_UNSAFE_DESTINATION")

        def download(self, *args):
            pytest.fail("A suppressed unsafe fetch must poison the extraction")

    monkeypatch.setattr(yt_dlp.YoutubeDL, "extract_info", lambda *a, **kw: info())
    with pytest.raises(PermanentError) as error:
        extractor.extract_audio(URL, tmp_path, max_bytes=100, max_duration=30, network=Network())
    assert error.value.code == "YOUTUBE_UNSAFE_DESTINATION"


async def test_youtube_partial_publication_resumes_without_downloading(runtime, monkeypatch):
    from akay_convert_to_markdown import media_main
    from akay_convert_to_markdown.errors.exceptions import BlobStorageError

    calls = []

    class Adapter:
        async def download(self, source, directory):
            calls.append(source.url)
            directory.mkdir()
            path = directory / "source.webm"
            path.write_bytes(b"audio")
            return path, {"videoId": "abcdefghijk", "canonicalUrl": CANONICAL, "title": None}

    monkeypatch.setattr(media_main, "YouTubeService", lambda _: Adapter())
    request = job(content_type="video", source={"type": "youtube", "url": URL})
    runtime.blobs.fail_name = "shared/lesson.artifacts/review.json"
    with pytest.raises(BlobStorageError):
        await runtime.build().process(request)
    assert await runtime.build().process(request) is ProcessingResult.COMPLETED
    assert calls == [URL] and len(runtime.calls) == 1


async def test_youtube_measured_duration_enforced_before_speech(runtime, monkeypatch):
    from akay_convert_to_markdown import media_main

    class Adapter:
        async def download(self, source, directory):
            directory.mkdir()
            path = directory / "source.webm"
            path.write_bytes(b"audio")
            return path, {"videoId": "abcdefghijk", "canonicalUrl": CANONICAL}

    monkeypatch.setattr(media_main, "YouTubeService", lambda _: Adapter())
    runtime.ffmpeg.duration = runtime.settings.max_media_duration_seconds + 1
    result = await runtime.build().process(job(content_type="video", source={"type": "youtube", "url": URL}))
    assert result is ProcessingResult.FAILED_PERMANENT
    assert runtime.webhook.calls[0][1]["error"]["code"] == "MEDIA_TOO_LONG"
    assert not runtime.calls and not list(runtime.settings.temp_directory.rglob("*"))


async def test_subprocess_passes_only_controlled_environment_and_validates_result(extractor, tmp_path, monkeypatch):
    from akay_convert_to_markdown.services.youtube_service import YouTubeService
    from tests.helpers import make_settings
    from akay_convert_to_markdown.config.settings import MediaWorkerSettings

    values = make_settings().model_dump(exclude={"servicebus_queue_name", "speech_resource_key", "speech_endpoint"})
    settings = MediaWorkerSettings(**values, MEDIA_SERVICEBUS_QUEUE_NAME="media", speech_resource_key="fixture",
                                   speech_endpoint="https://speech.invalid")
    monkeypatch.setenv("SPEECH_RESOURCE_KEY", "ambient-secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://unsafe.invalid")
    monkeypatch.setenv("YTDLP_PLUGIN_DIRS", "unsafe-directory")
    service = YouTubeService(settings)
    # A real local child stands in for extraction. It checks the actual process
    # boundary, consumes only controlled JSON and writes the fixed expected file.
    script = ("import os,sys,json,pathlib; c=json.load(sys.stdin); "
              "assert not any(k in os.environ for k in ['SPEECH_RESOURCE_KEY','HTTPS_PROXY','YTDLP_PLUGIN_DIRS']); "
              "assert c['url']=='https://www.youtube.com/watch?v=abcdefghijk'; "
              "pathlib.Path('source.webm').write_bytes(b'audio'); "
              "print(json.dumps({'result':{'videoId':'abcdefghijk','canonicalUrl':c['url'],'title':None,'fileName':'source.webm'}}))")
    service._command = lambda: [sys.executable, "-I", "-c", script]
    source = job(content_type="video", source={"type": "youtube", "url": URL}).source
    path, metadata = await service.download(source, tmp_path / "child")
    assert path.read_bytes() == b"audio" and metadata["videoId"] == "abcdefghijk"


async def test_timeout_terminates_descendant_writers_before_return(extractor, tmp_path):
    from akay_convert_to_markdown.services.youtube_service import YouTubeService
    from tests.helpers import make_settings
    from akay_convert_to_markdown.config.settings import MediaWorkerSettings

    values = make_settings().model_dump(exclude={"servicebus_queue_name", "speech_resource_key", "speech_endpoint"})
    settings = MediaWorkerSettings(**values, MEDIA_SERVICEBUS_QUEUE_NAME="media", speech_resource_key="fixture",
                                   speech_endpoint="https://speech.invalid", youtube_timeout_seconds=0.8)
    service = YouTubeService(settings)
    writer = "import pathlib,time; p=pathlib.Path('alive'); exec('while True:\\n p.write_text(str(time.time()))\\n time.sleep(0.02)')"
    script = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-I','-c',{writer!r}]); time.sleep(60)"
    service._command = lambda: [sys.executable, "-I", "-c", script]
    source = job(content_type="video", source={"type": "youtube", "url": URL}).source
    directory = tmp_path / "tree"
    with pytest.raises(PermanentError):
        await service.download(source, directory)
    assert (directory / "alive").exists()
    final_write = (directory / "alive").read_bytes()
    await asyncio.sleep(0.2)
    assert (directory / "alive").read_bytes() == final_write


async def test_temp_budget_stops_local_extractor_and_rejects_escaped_output(extractor, tmp_path):
    from akay_convert_to_markdown.services.youtube_service import YouTubeService
    from tests.helpers import make_settings
    from akay_convert_to_markdown.config.settings import MediaWorkerSettings

    values = make_settings().model_dump(exclude={"servicebus_queue_name", "speech_resource_key", "speech_endpoint"})
    settings = MediaWorkerSettings(**values, MEDIA_SERVICEBUS_QUEUE_NAME="media", speech_resource_key="fixture",
                                   speech_endpoint="https://speech.invalid", youtube_max_temp_mb=1)
    service = YouTubeService(settings)
    service._command = lambda: [sys.executable, "-I", "-c",
                               "import pathlib,time; pathlib.Path('cache').write_bytes(b'x'*1048577); time.sleep(60)"]
    source = job(content_type="video", source={"type": "youtube", "url": URL}).source
    with pytest.raises(PermanentError) as error:
        await service.download(source, tmp_path / "quota")
    assert error.value.code == "YOUTUBE_TEMP_LIMIT" and service._active_process is None
    response = {"result": {"videoId": "abcdefghijk", "canonicalUrl": CANONICAL, "fileName": "../escape.webm"}}
    service._command = lambda: [sys.executable, "-I", "-c", f"print({json.dumps(response)!r})"]
    with pytest.raises(PermanentError, match="invalid"):
        await service.download(source, tmp_path / "escape")


async def test_real_offline_js_dependencies_are_usable(extractor, tmp_path):
    from deno import find_deno_bin
    from yt_dlp_ejs.yt import solver
    from yt_dlp.extractor.youtube.jsc._builtin.vendor import VERSION
    from importlib.metadata import version

    assert {name: version(name) for name in extractor.PINS} == extractor.PINS
    assert VERSION == "0.3.1"
    environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
    environment["DENO_DIR"] = str(tmp_path / "cache")
    # Execute the pinned bundled solver library offline with Deno's permissions
    # disabled, rather than merely asserting that a package/binary exists.
    process = await asyncio.create_subprocess_exec(str(find_deno_bin()), "run", "--no-config", "--no-remote",
                                                   "--no-npm", "--cached-only", "--no-prompt", "--ext=js", "-",
                                                   stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE, env=environment)
    script = solver.lib() + "\nObject.assign(globalThis, lib);\n" + solver.core() + "\nconsole.log(typeof jsc);"
    output, errors = await asyncio.wait_for(process.communicate(script.encode()), 10)
    assert process.returncode == 0, errors.decode()
    assert output.strip() == b"function"


async def test_quick_download_cannot_escape_final_temp_quota(extractor, tmp_path):
    from akay_convert_to_markdown.services.youtube_service import YouTubeService
    from tests.helpers import make_settings
    from akay_convert_to_markdown.config.settings import MediaWorkerSettings

    values = make_settings().model_dump(exclude={"servicebus_queue_name", "speech_resource_key", "speech_endpoint"})
    settings = MediaWorkerSettings(**values, MEDIA_SERVICEBUS_QUEUE_NAME="media", speech_resource_key="fixture",
                                   speech_endpoint="https://speech.invalid", youtube_max_temp_mb=1)
    service = YouTubeService(settings)
    response = {"result": {"videoId": "abcdefghijk", "canonicalUrl": CANONICAL, "fileName": "source.webm"}}
    script = f"import pathlib; pathlib.Path('source.webm').write_bytes(b'x'*1048577); print({json.dumps(response)!r})"
    service._command = lambda: [sys.executable, "-I", "-c", script]
    source = job(content_type="video", source={"type": "youtube", "url": URL}).source
    with pytest.raises(PermanentError) as error:
        await service.download(source, tmp_path / "quota")
    assert error.value.code == "YOUTUBE_TEMP_LIMIT"


async def test_youtube_transient_failure_cleans_without_failed_callback(runtime, monkeypatch):
    from akay_convert_to_markdown import media_main
    from akay_convert_to_markdown.services.youtube_http import YouTubeTransientError

    class Adapter:
        async def download(self, source, directory):
            directory.mkdir()
            (directory / "partial").write_bytes(b"partial audio")
            raise YouTubeTransientError("Temporarily unavailable.")

    monkeypatch.setattr(media_main, "YouTubeService", lambda _: Adapter())
    request = job(content_type="video", source={"type": "youtube", "url": URL})
    with pytest.raises(TransientError):
        await runtime.build().process(request)
    assert not runtime.webhook.calls and not runtime.calls and not list(runtime.settings.temp_directory.rglob("*"))
