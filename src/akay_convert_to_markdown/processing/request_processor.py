"""The processing boundary used by the existing Service Bus consumer."""

from __future__ import annotations

import logging
from typing import Protocol

from akay_convert_to_markdown.models.conversion_request import ConversionRequest
from akay_convert_to_markdown.models.conversion_result import ProcessingResult


class RequestProcessor(Protocol):
    async def process(self, request: ConversionRequest) -> ProcessingResult: ...

    async def notify_invalid_message(self, identity: dict, log: logging.LoggerAdapter) -> None: ...
