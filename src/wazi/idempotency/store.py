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

``InMemoryIdempotencyStore`` is for a single process and is lost on restart. That is fine for
Phase 4 and for tests. A multi-process or restart-safe store (a database, a cache server...)
only has to implement the same two methods; nothing else in Wazi depends on the technology.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class IdempotencyStore(Protocol):
    def claim(self, key: str) -> bool:
        """Atomically record ``key``. True the first time (go ahead), False if already claimed."""
        ...

    def release(self, key: str) -> None:
        """Forget ``key`` (used when processing failed and a retry should be allowed)."""
        ...


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
        self._claimed: OrderedDict[str, float] = OrderedDict()  # key -> claim time, oldest first
        self._lock = threading.Lock()

    def claim(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            self._expire(now)
            if key in self._claimed:
                return False
            self._claimed[key] = now
            while len(self._claimed) > self._max_entries:
                self._claimed.popitem(last=False)
            return True

    def release(self, key: str) -> None:
        with self._lock:
            self._claimed.pop(key, None)

    def _expire(self, now: float) -> None:
        # Entries are ordered by claim time, so expired ones are always at the front.
        while self._claimed:
            oldest_key, claimed_at = next(iter(self._claimed.items()))
            if now - claimed_at < self._ttl:
                break
            del self._claimed[oldest_key]

    def __len__(self) -> int:
        with self._lock:
            return len(self._claimed)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._claimed
