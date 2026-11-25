"""Pinned yt-dlp boundary, run in a credential-free disposable child process."""

import contextlib
from importlib.metadata import version
import io
import json
import math
from pathlib import Path
import sys

from akay_convert_to_markdown.errors.exceptions import MediaTooLongError, PermanentError, TransientError
from akay_convert_to_markdown.models.youtube import video_identity
from akay_convert_to_markdown.services.youtube_http import YouTubeError, YouTubeHTTP


PINS = {"yt-dlp": "2025.11.12", "yt-dlp-ejs": "0.3.1", "deno": "2.5.6"}


class QuietLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def extract_audio(url: str, directory: Path, *, max_bytes: int, max_duration: float,
                  timeout: float = 300, network=None):
    identity, canonical = video_identity(url)
    if any(version(name) != pin for name, pin in PINS.items()):
        raise RuntimeError("Install the pinned YouTube dependencies.")
    from deno import find_deno_bin
    from yt_dlp import YoutubeDL
    from yt_dlp.globals import all_plugins_loaded, plugin_dirs
    from yt_dlp.networking.common import Response
    from yt_dlp.networking.exceptions import HTTPError, TransportError

    # The embedding API otherwise discovers installed/home plugins at construction.
    # This global change is restricted to the dedicated, one-attempt child process.
    plugin_dirs.value = []
    all_plugins_loaded.value = True
    from yt_dlp.extractor.youtube import YoutubeIE

    network = network or YouTubeHTTP(max_bytes=max_bytes, timeout=timeout)

    class GuardedYoutubeDL(YoutubeDL):
        def urlopen(self, request):
            try:
                body, final_url, headers, status = network.metadata(request.url, method=request.method,
                                                                    data=request.data, headers=dict(request.headers))
                response = Response(io.BytesIO(body), final_url, headers, status=status)
                if status >= 400:
                    raise HTTPError(response)
                return response
            except (PermanentError, TransientError):
                raise TransportError("YouTube request rejected or unavailable.") from None

    options = dict(quiet=True, no_warnings=True, logger=QuietLogger(), noplaylist=True, cachedir=False,
                   proxy="", cookiefile=None, usenetrc=False, remote_components=[],
                   js_runtimes={"deno": {"path": str(find_deno_bin())}}, extractor_retries=0,
                   retries=0, skip_download=True, socket_timeout=10, geo_bypass=False,
                   extract_flat=False, check_formats=False)
    try:
        with GuardedYoutubeDL(options, auto_init=False) as ydl:
            ydl.add_info_extractor(YoutubeIE())
            result = ydl.extract_info(canonical, download=False, process=False)
        if network.failure:
            raise network.failure
    except (PermanentError, TransientError):
        raise
    except Exception:
        if network.failure:
            raise network.failure from None
        raise YouTubeError("The video is unavailable, restricted, or unsupported by the pinned extractor.") from None
    if (not isinstance(result, dict) or result.get("_type", "video") != "video" or result.get("id") != identity
            or result.get("is_live") or result.get("live_status") not in {None, "not_live"}
            or result.get("availability") not in {None, "public", "unlisted"}):
        raise YouTubeError("Only available individual non-live YouTube videos are supported.")
    duration = result.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise YouTubeError("The video's duration is unavailable.")
    if duration > max_duration:
        raise MediaTooLongError("The video exceeds the configured duration limit.")
    formats = [fmt for fmt in result.get("formats", []) if fmt.get("protocol") == "https"
               and fmt.get("vcodec") == "none" and fmt.get("acodec") not in {None, "none"}
               and fmt.get("ext") in {"webm", "m4a", "mp3", "ogg"} and not fmt.get("has_drm")]
    if not formats:
        raise YouTubeError("The video has no supported direct audio-only format.", code="YOUTUBE_FORMAT_UNSUPPORTED")
    selected = max(formats, key=lambda fmt: fmt.get("abr") or 0)
    path = directory / ("source." + selected["ext"])
    network.download(selected["url"], path)
    title = result.get("title")
    return dict(videoId=identity, canonicalUrl=canonical, title=title[:500] if isinstance(title, str) and title.strip() else None,
                fileName=path.name)


def main():
    # Only this small, worker-generated configuration crosses the child boundary.
    try:
        config = json.loads(sys.stdin.read(8192))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = extract_audio(config["url"], Path.cwd(), max_bytes=config["maxBytes"],
                                   max_duration=config["maxDuration"], timeout=config["timeout"])
        response = {"result": result}
    except PermanentError as exc:
        response = {"error": exc.code}
    except TransientError:
        response = {"error": "YOUTUBE_TEMPORARILY_UNAVAILABLE"}
    except Exception:
        response = {"error": "YOUTUBE_DEPENDENCY_UNAVAILABLE"}
    print(json.dumps(response, ensure_ascii=True))


if __name__ == "__main__":
    main()
