"""Supported embedding space and controlled immutable profile snapshots."""

import json
import math
import struct

from akay_convert_to_markdown.contracts.requests import IndexProfile
from akay_convert_to_markdown.errors.exceptions import PermanentError, TransientError

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
TOKENIZER = "cl100k_base"
MAX_INPUT_TOKENS = 8192


class IndexProfileError(PermanentError):
    code = "INDEX_PROFILE_INCOMPATIBLE"


def supported_profile(profile: IndexProfile) -> None:
    if (profile.provider != "AzureOpenAI" or profile.model != MODEL or profile.dimensions != DIMENSIONS
            or profile.tokenizer != TOKENIZER or profile.model_revision is not None or not profile.deployment
            or not 0 < profile.max_chunk_tokens <= MAX_INPUT_TOKENS):
        raise IndexProfileError("The profile is incompatible with the configured embedding adapter.")


def canonical_profile(profile: IndexProfile) -> str:
    return json.dumps(profile.model_dump(mode="json", by_alias=True), sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False)


class ProfileCatalog:
    """Consumer-owned configuration, not a database lookup or a mutable registry.

    Preserve used snapshots in controlled configuration. Collection metadata also
    retains bindings; N11 owns serialization of concurrent profile/point mutations.
    """

    def __init__(self, profiles: list[IndexProfile]):
        self._snapshots = {}
        for profile in profiles:
            snapshot = canonical_profile(profile)
            profile = IndexProfile.model_validate_json(snapshot)
            supported_profile(profile)
            if profile.id in self._snapshots:
                raise IndexProfileError("Configured profile identities must be unique.")
            self._snapshots[profile.id] = snapshot
        if not self._snapshots:
            raise IndexProfileError("At least one explicitly configured profile is required.")

    def resolve(self, incoming: IndexProfile) -> IndexProfile:
        snapshot = self._snapshots.get(incoming.id)
        if snapshot is None or snapshot != canonical_profile(incoming):
            raise IndexProfileError("The request does not match an immutable configured profile.")
        return IndexProfile.model_validate_json(snapshot)

    def resolve_target(self, target, *, previous: dict[str, str]) -> None:
        """Allow explicit cleanup of configured or previously used destinations."""
        snapshot = self._snapshots.get(target.profile_id)
        collection = previous.get(target.profile_id) or (json.loads(snapshot)["collection"] if snapshot else None)
        if collection != target.collection:
            raise IndexProfileError("The deletion target is not an authorized profile destination.")


def validate_vectors(vectors, count: int, dimensions: int) -> list[list[float]]:
    """Reject malformed, nonfinite, zero or float32-overflowing dense vectors."""
    if not isinstance(vectors, list) or len(vectors) != count:
        raise TransientError("The embedding service returned an invalid vector set.")
    result = []
    for vector in vectors:
        try:
            if (not isinstance(vector, list) or len(vector) != dimensions
                    or any(type(v) not in {int, float} or not math.isfinite(v) for v in vector)):
                raise ValueError()
            # Qdrant stores float32. Finite JSON numbers alone do not prevent
            # overflow/underflow (including cosine normalization to a zero vector).
            stored = [struct.unpack("<f", struct.pack("<f", v))[0] for v in vector]
            squared_norm = sum(v * v for v in stored)
            if not 1.401298464324817e-45 <= squared_norm <= 3.4028234663852886e38:
                raise ValueError()
        except (ValueError, TypeError, OverflowError, struct.error):
            raise TransientError("The embedding service returned an invalid vector.") from None
        result.append([float(v) for v in vector])
    return result
