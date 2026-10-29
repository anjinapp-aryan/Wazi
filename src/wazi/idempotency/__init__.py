"""Idempotency layer: remember which message ids were already accepted.

Standard library only. Knows nothing about WhatsApp, HTTP or agents: keys are opaque strings.
"""

from wazi.idempotency.sqlite_store import SqliteIdempotencyStore
from wazi.idempotency.store import (
    CompletionRecorder,
    IdempotencyStore,
    InMemoryIdempotencyStore,
)

__all__ = [
    "CompletionRecorder",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "SqliteIdempotencyStore",
]
