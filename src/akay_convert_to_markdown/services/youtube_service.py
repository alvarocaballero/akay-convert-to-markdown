"""Async lifetime/limits for the single-attempt YouTube extractor process tree."""

import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from akay_convert_to_markdown.config.settings import MediaWorkerSettings
from akay_convert_to_markdown.contracts.requests import YouTubeSource
from akay_convert_to_markdown.errors.exceptions import ProcessingTimeoutError
from akay_convert_to_markdown.models.youtube import video_identity
from akay_convert_to_markdown.services.youtube_http import YouTubeError, YouTubeTransientError


class YouTubeService:
    def __init__(self, settings: MediaWorkerSettings):
        self._settings = settings
        self._active_process = None

    def _command(self):
        return [sys.executable, "-I", "-m", "akay_convert_to_markdown.services.youtube_extractor"]

    async def _stop(self, process):
        if os.name == "nt":
            # Includes Deno descendants. No URL, credentials or message-controlled args.
            killer = await asyncio.create_subprocess_exec(str(Path(os.environ["SYSTEMROOT"]) / "System32/taskkill.exe"),
                                                          "/PID", str(process.pid), "/T", "/F",
                                                          stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await killer.wait()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.returncode is None:
            process.kill()
        await process.wait()

    async def download(self, source: YouTubeSource, directory: Path):
        identity, canonical = video_identity(source.url)
        directory = directory.resolve()
        directory.mkdir(parents=True, exist_ok=False)
        # Python isolated mode and a minimal environment exclude ambient config,
        # proxies, cookies, plugin paths, cloud credentials and user Deno settings.
        environment = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR") if key in os.environ}
        environment.update(HOME=str(directory), USERPROFILE=str(directory), TMP=str(directory), TEMP=str(directory),
                           DENO_DIR=str(directory / "deno-cache"), NO_COLOR="1", YTDLP_NO_PLUGINS="1")
        config = json.dumps(dict(url=canonical, maxBytes=self._settings.max_input_size_bytes,
                                 maxDuration=self._settings.max_media_duration_seconds,
                                 timeout=self._settings.youtube_timeout_seconds)).encode()
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = await asyncio.create_subprocess_exec(*self._command(), cwd=directory, env=environment,
                                                       stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.DEVNULL, **options)
        self._active_process = process

        def check_temp():
            total = 0
            for path in directory.rglob("*"):
                try:
                    if path.is_symlink():
                        raise YouTubeError("The extractor produced an unsafe local path.")
                    if path.is_file():
                        total += path.stat().st_size
                except FileNotFoundError:
                    # Deno can remove its own temporary cache files between scans.
                    continue
            if total > self._settings.youtube_max_temp_mb * 1024 * 1024:
                raise YouTubeError("YouTube temporary storage exceeded its limit.", code="YOUTUBE_TEMP_LIMIT")

        async def watch():
            while process.returncode is None:
                check_temp()
                await asyncio.sleep(0.05)

        async def exchange():
            process.stdin.write(config)
            await process.stdin.drain()
            process.stdin.close()
            output = await process.stdout.read(4097)
            if len(output) > 4096:
                raise YouTubeError("The extractor returned an invalid result.")
            await process.wait()
            return output

        monitor, communication = asyncio.create_task(watch()), asyncio.create_task(exchange())
        try:
            async with asyncio.timeout(self._settings.youtube_timeout_seconds):
                done, _ = await asyncio.wait({monitor, communication}, return_when=asyncio.FIRST_COMPLETED)
                if monitor in done:
                    monitor.result()
                output = await communication
            if process.returncode:
                raise YouTubeTransientError("The extractor process stopped unexpectedly.")
            check_temp()
            response = json.loads(output)
            error = response.get("error")
            if error in {"YOUTUBE_DEPENDENCY_UNAVAILABLE", "YOUTUBE_TEMPORARILY_UNAVAILABLE"}:
                raise YouTubeTransientError("The YouTube dependency or source is temporarily unavailable.")
            if error:
                codes = {"YOUTUBE_SOURCE_UNAVAILABLE", "YOUTUBE_UNSAFE_DESTINATION", "YOUTUBE_FORMAT_UNSUPPORTED",
                         "MEDIA_TOO_LONG", "DOCUMENT_TOO_LARGE", "PROCESSING_TIMEOUT"}
                raise YouTubeError("The YouTube source could not be retrieved within the supported policy.",
                                   code=error if error in codes else "YOUTUBE_SOURCE_UNAVAILABLE")
            result = response["result"]
            filename = result.pop("fileName")
            if (filename not in {"source.webm", "source.m4a", "source.mp3", "source.ogg"}
                    or result.get("videoId") != identity or result.get("canonicalUrl") != canonical):
                raise ValueError
            path = directory / filename
            if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= self._settings.max_input_size_bytes:
                raise ValueError
            return path, result
        except TimeoutError:
            raise ProcessingTimeoutError("YouTube retrieval exceeded its time budget.") from None
        except (ValueError, KeyError, TypeError):
            raise YouTubeError("The extractor returned an invalid result.") from None
        finally:
            # Repeated cancellation must not release publisher ownership while a
            # child or its JS runtime can still write into this attempt directory.
            async def finish():
                if process.returncode is None:
                    await self._stop(process)
                monitor.cancel()
                communication.cancel()
                await asyncio.gather(monitor, communication, return_exceptions=True)

            cleanup = asyncio.create_task(finish())
            cancelled = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cancelled = True
            self._active_process = None
            cleanup.result()
            if cancelled:
                raise asyncio.CancelledError
