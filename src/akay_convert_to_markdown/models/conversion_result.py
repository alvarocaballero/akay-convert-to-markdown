"""Result of a single conversion request."""

from __future__ import annotations

from enum import Enum


class ProcessingResult(Enum):
    """Outcome of processing one request.

    Both values lead to Service Bus message completion; the difference is only
    which webhook event was delivered. Transient failures are not represented
    here — they are raised as exceptions instead.
    """

    COMPLETED = "completed"
    FAILED_PERMANENT = "failed_permanent"
