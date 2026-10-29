"""Duplicate detection.

Meta documents that webhook deliveries are retried when the endpoint does not answer 200,
and that retries can produce duplicate notifications, so the receiver must de-duplicate.

Interface choice: ``claim`` / ``release`` instead of ``has`` / ``mark_processed``.
With two separate calls, two concurrent deliveries of the same message can both see
"not processed" and both proceed (a check-then-act race). ``claim`` is one atomic
operation: exactly one caller gets ``True`` for a given key. This is the same idea as
AleBrito's whatsapp-ai-agent, which uses an atomic ``INSERT`` and treats a constraint
violation as "duplicate" (MIT; pattern only, no code copied).

``release`` exists for failure handling: if the downstream hand-off fails after a claim,
the key is released so that Meta's retry of the same message is not mistaken for a duplicate.

Phase 5 adds an optional second interface, ``CompletionRecorder``: once the webhook has
acknowledged a message, the background worker records whether processing ended in ``done`` or
``failed``. A key that stays in ``claimed`` after a restart means "accepted but never finished",
which is how a lost-in-a-crash message becomes visible (recovery itself is future work).

``InMemoryIdempotencyStore`` is for a single process and is lost on restart. The restart-safe
version is ``SqliteIdempotencyStore``; both satisfy the same protocols.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Protocol, runtime_checkable

STATE_CLAIMED = "claimed"
STATE_DONE = "done"
STATE_FAILED = "failed"


@runtime_checkable
class IdempotencyStore(Protocol):
    def claim(self, key: str) -> bool:
        """Atomically record ``key``. True the first time (go ahead), False if already claimed."""
        ...

    def release(self, key: str) -> None:
        """Forget ``key`` (used when processing failed and a retry should be allowed)."""
        ...


@runtime_checkable
class CompletionRecorder(Protocol):
    def mark_done(self, key: str) -> None: ...

    def mark_failed(self, key: str) -> None: ...


class InMemoryIdempotencyStore:
    """Thread-safe, bounded, expiring set of claimed keys.

    * ``max_entries``: oldest claims are evicted first when full. After eviction an old
      duplicate would be accepted again, which is an accepted trade-off for bounded memory.
    * ``ttl_seconds``: claims older than this expire.
    * ``clock``: injectable monotonic clock so tests do not need to sleep.
    """

    def __init__(
        self,
        max_entries: int = 50_000,
        ttl_seconds: float = 7 * 24 * 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._clock = clock
        # key -> [claim time, state], ordered oldest first
        self._claimed: OrderedDict[str, list] = OrderedDict()
        self._lock = threading.Lock()

    def claim(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            self._expire(now)
            if key in self._claimed:
                return False
            self._claimed[key] = [now, STATE_CLAIMED]
            while len(self._claimed) > self._max_entries:
                self._claimed.popitem(last=False)
            return True

    def release(self, key: str) -> None:
        with self._lock:
            self._claimed.pop(key, None)

    def mark_done(self, key: str) -> None:
        self._set_state(key, STATE_DONE)

    def mark_failed(self, key: str) -> None:
        self._set_state(key, STATE_FAILED)

    def state_of(self, key: str) -> str | None:
        with self._lock:
            entry = self._claimed.get(key)
            return entry[1] if entry else None

    def _set_state(self, key: str, state: str) -> None:
        with self._lock:
            entry = self._claimed.get(key)
            if entry is not None:
                entry[1] = state

    def _expire(self, now: float) -> None:
        # Entries are ordered by claim time, so expired ones are always at the front.
        while self._claimed:
            oldest_key, (claimed_at, _state) = next(iter(self._claimed.items()))
            if now - claimed_at < self._ttl:
                break
            del self._claimed[oldest_key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._claimed)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._claimed
