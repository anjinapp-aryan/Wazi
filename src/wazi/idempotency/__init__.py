"""Idempotency layer: remember which message ids were already accepted.

Standard library only. Knows nothing about WhatsApp, HTTP or agents: keys are opaque strings.
"""

from wazi.idempotency.store import IdempotencyStore, InMemoryIdempotencyStore

__all__ = ["IdempotencyStore", "InMemoryIdempotencyStore"]
