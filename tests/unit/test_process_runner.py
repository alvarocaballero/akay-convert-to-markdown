"""Subprocess runner tests (real short-lived processes)."""

from __future__ import annotations

import asyncio
import sys

import pytest

from akay_convert_to_markdown.services.process_runner import ProcessTimeoutError, run_process


async def test_success_captures_output_and_returncode():
    result = await run_process(
        [sys.executable, "-c", "import sys; print('hello'); print('err', file=sys.stderr)"],
        timeout_seconds=30,
        max_log_bytes=1024,
    )
    assert result.returncode == 0
    assert "hello" in result.stdout
    assert "err" in result.stderr


async def test_nonzero_returncode_is_returned_not_raised():
    result = await run_process(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        timeout_seconds=30,
        max_log_bytes=1024,
    )
    assert result.returncode == 3


async def test_timeout_raises_process_timeout_error():
    with pytest.raises(ProcessTimeoutError) as exc_info:
        await run_process(
            [sys.executable, "-c", "import time; time.sleep(30)", "secret-arg"],
            timeout_seconds=0.2,
            max_log_bytes=1024,
        )
    assert "secret-arg" not in str(exc_info.value)
    assert sys.executable in str(exc_info.value)


async def test_cancellation_terminates_child():
    task = asyncio.create_task(
        run_process(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            timeout_seconds=60,
            max_log_bytes=1024,
        )
    )
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_long_output_is_truncated():
    result = await run_process(
        [sys.executable, "-c", "print('A' * 10000)"],
        timeout_seconds=30,
        max_log_bytes=100,
    )
    assert len(result.stdout) < 1000
