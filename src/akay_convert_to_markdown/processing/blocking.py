"""Drain owned synchronous work before callers release files or coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def drain_task(task: asyncio.Future) -> None:
    """Wait for an owned task's actual exit despite repeated caller cancellation.

    Callers decide whether to cancel it first and propagate their original cause.
    Retrieve late exceptions so cleanup never leaves an unobserved failure.
    """
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not task.cancelled():
        task.exception()


async def await_owned(awaitable):
    """Cancel and drain asynchronous work before relinquishing its resources."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        task.cancel()
        await drain_task(task)
        raise


async def await_cleanup(awaitable):
    """Finish cleanup without cancelling it, then propagate caller cancellation."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await drain_task(task)
        raise


async def drain_on_cancel(function: Callable[[], T]) -> T:
    """Cancellation waits for the writer, including repeated/shutdown cancellation.

    Executor futures are not Tasks: asyncio.run's cancel-all cannot mark a
    still-running writer finished. This is cooperative draining, not hard kill.
    """
    task = asyncio.get_running_loop().run_in_executor(None, function)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise
