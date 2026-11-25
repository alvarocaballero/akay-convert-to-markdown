"""Strict index/delete queue boundary; saved artifacts only, no source conversion."""

from uuid import UUID

from pydantic import TypeAdapter

from akay_convert_to_markdown.contracts.base import validate_wire
from akay_convert_to_markdown.contracts.requests import parse_request
from akay_convert_to_markdown.errors.exceptions import InvalidMessageError


class IndexProcessor:
    def __init__(self, settings, storage, coordinator, webhook):
        self.settings, self.storage, self.coordinator, self.webhook = settings, storage, coordinator, webhook

    def parse_message(self, raw):
        return parse_request(raw, worker="index", callbacks=self.settings.webhook_callbacks)

    async def process(self, request):
        async def load(job):
            source = await self.storage.read_bytes(self.settings.source_container_name, job.source.blob_name,
                                                   max_bytes=self.settings.max_input_size_bytes)
            review = None
            if job.section_context.mode == "fromReview":
                review = await self.storage.read_bytes(self.settings.source_container_name, job.section_context.review_blob_name,
                                                       max_bytes=self.settings.max_input_size_bytes)
            return source, review

        return await self.coordinator.deliver(request, load, self.webhook.send)

    @staticmethod
    def recover_invalid_message_identity(raw):
        try:
            fields = validate_wire(TypeAdapter(dict), raw)
            identity = dict(requestId=str(UUID(str(fields.get("requestId")))))
        except (InvalidMessageError, ValueError, TypeError):
            return None
        if fields.get("operation") not in {"index", "delete"}:
            return None
        identity["operation"] = fields["operation"]
        for key in ("callback", "scopeKey", "contentKey"):
            if isinstance(fields.get(key), str) and fields[key].strip():
                identity[key] = fields[key]
        if type(fields.get("schemaVersion")) is int and fields["schemaVersion"] == 1:
            identity["schemaVersion"] = 1
        if type(fields.get("operationSequence")) is int and fields["operationSequence"] > 0:
            identity["operationSequence"] = fields["operationSequence"]
        if isinstance(fields.get("payload"), dict):
            identity["payload"] = fields["payload"]
        return identity

    async def notify_invalid_message(self, identity, log):
        callback = identity.get("callback")
        if not isinstance(callback, str) or not self.webhook.is_configured(callback):
            log.error("index.invalid_callback")
            return
        event_type = "content.indexing.failed" if identity["operation"] == "index" else "content.index.deletion.failed"
        event = {key: value for key, value in identity.items() if key != "callback"}
        event.update(eventType=event_type, error=dict(code="INVALID_MESSAGE", message="Message has missing or invalid contract fields."))
        await self.webhook.send(callback, event, f"{identity['requestId']}:{event_type}")
