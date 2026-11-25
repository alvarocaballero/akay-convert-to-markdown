"""Serializable admission contract; N11 must supply durable state and ownership."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, model_validator

from akay_convert_to_markdown.contracts.base import Contract, NonEmpty, Uuid
from akay_convert_to_markdown.contracts.requests import DeleteRequest, IndexRequest, Request


class RequestIdentity(Contract):
    request_id: Uuid
    canonical_request: NonEmpty

    @classmethod
    def capture(cls, request: Request) -> RequestIdentity:
        # Snapshot the complete effective contract, including defaults and opaque
        # JSON. Later mutations of nested caller dictionaries cannot alter it.
        canonical = json.dumps(request.model_dump(mode="json", by_alias=True), ensure_ascii=False,
                               sort_keys=True, separators=(",", ":"), allow_nan=False)
        return cls(request_id=request.request_id, canonical_request=canonical)


class IndexReceipt(Contract):
    identity: RequestIdentity
    status: Literal["admitted", "completed"]
    previous_requests: list[RequestIdentity] = Field(default_factory=list)

    @model_validator(mode="after")
    def _valid_identity(self):
        request = self.request()
        if request.request_id != self.identity.request_id or RequestIdentity.capture(request) != self.identity:
            raise ValueError("Receipt identity does not match its canonical request.")
        request_ids = {request.request_id}
        sequences = {request.operation_sequence}
        for identity in self.previous_requests:
            previous = _identity_request(identity)
            if ((previous.scope_key, previous.content_key) != (request.scope_key, request.content_key)
                    or previous.operation_sequence >= request.operation_sequence
                    or previous.request_id in request_ids or previous.operation_sequence in sequences):
                raise ValueError("Receipt history must contain distinct older operations for the same content and scope.")
            request_ids.add(previous.request_id)
            sequences.add(previous.operation_sequence)
        return self

    def request(self) -> IndexRequest | DeleteRequest:
        return _identity_request(self.identity)


def _identity_request(identity: RequestIdentity) -> IndexRequest | DeleteRequest:
    from akay_convert_to_markdown.contracts.requests import REQUEST_ADAPTERS

    request = REQUEST_ADAPTERS["index"].validate_json(identity.canonical_request)
    if RequestIdentity.capture(request) != identity:
        raise ValueError("Invalid canonical request identity.")
    return request


Admission = Literal["admit", "resume", "replay", "superseded", "conflict"]


def index_admission(request: IndexRequest | DeleteRequest, latest: IndexReceipt | None) -> Admission:
    """Evaluate an already-read durable receipt; this does not acquire a lock.

    The coordinator must call under ownership of exact scope/content state,
    persist admission before mutation, retain request history and guard/drain
    in-flight writes. This pure function alone offers no concurrency guarantee.
    """
    if latest is None:
        return "admit"
    previous = latest.request()
    if (request.scope_key, request.content_key) != (previous.scope_key, previous.content_key):
        raise ValueError("Receipt belongs to another scope/content identity.")
    incoming = RequestIdentity.capture(request)
    for identity in [latest.identity, *latest.previous_requests]:
        recorded = _identity_request(identity)
        if (incoming.request_id == identity.request_id or request.operation_sequence == recorded.operation_sequence) and incoming != identity:
            return "conflict"
    if request.operation_sequence < previous.operation_sequence:
        return "superseded"
    if request.operation_sequence == previous.operation_sequence:
        if incoming != latest.identity:
            return "conflict"
        return "replay" if latest.status == "completed" else "resume"
    return "admit"
