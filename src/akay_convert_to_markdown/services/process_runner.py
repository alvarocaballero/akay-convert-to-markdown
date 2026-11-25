"""Small, cancellable asyncio subprocess runner.

Used to drive FFmpeg/FFprobe. It captures stdout and stderr, checks
the exit code, honours a maximum timeout, terminates the child process on
cancellation, and bounds the amount of output retained in memory.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from contextlib import suppress

from akay_convert_to_markdown.processing.blocking import await_cleanup, drain_task


class ProcessError(Exception):
    """Base error raised by the subprocess runner."""


class ProcessTimeoutError(ProcessError):
    """The subprocess exceeded its configured timeout."""


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


def _truncate(text: str, limit: int) -> str:
    """Keep only the trailing ``limit`` characters of ``text``."""
    if len(text) <= limit:
        return text
    return "...(truncated)...\n" + text[-limit:]


async def run_process(
    command: list[str],
    *,
    timeout_seconds: float,
    max_log_bytes: int,
) -> ProcessResult:
    """Run ``command`` and return its result.

    Raises :class:`ProcessTimeoutError` on timeout. Cancellation is propagated
    after terminating the child process, so no orphan is left behind.

    The command line is never embedded in exceptions or logs: it may contain
    externally supplied paths or URLs. Only the executable name is included.
    """
    executable = command[0] if command else "<unknown>"
    spawning = asyncio.create_task(asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    ))
    try:
        process = await asyncio.shield(spawning)
    except asyncio.CancelledError:
        await drain_task(spawning)
        if not spawning.cancelled() and spawning.exception() is None:
            process = spawning.result()
            with suppress(ProcessLookupError):
                process.kill()
            await await_cleanup(process.wait())
        raise
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        with suppress(ProcessLookupError):
            process.kill()
        await await_cleanup(process.wait())
        raise ProcessTimeoutError(
            f"{executable} timed out after {timeout_seconds}s."
        ) from exc
    except asyncio.CancelledError:
        with suppress(ProcessLookupError):
            process.kill()
        await await_cleanup(process.wait())
        raise

    return ProcessResult(
        returncode=process.returncode or 0,
        stdout=_truncate(stdout.decode("utf-8", errors="replace"), max_log_bytes),
        stderr=_truncate(stderr.decode("utf-8", errors="replace"), max_log_bytes),
    )
