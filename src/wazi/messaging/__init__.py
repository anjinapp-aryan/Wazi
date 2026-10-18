"""Messaging layer: Wazi's own message model and the translation from Meta's webhook payload.

Nothing outside this package should need to know what a Meta payload looks like.
No HTTP framework, no storage, no agent, no LLM imports here.
"""

from wazi.messaging.models import (
    MessageType,
    NormalizationResult,
    NormalizedMessage,
    PayloadError,
)
from wazi.messaging.normalizer import normalize_payload

__all__ = [
    "MessageType",
    "NormalizationResult",
    "NormalizedMessage",
    "PayloadError",
    "normalize_payload",
]
