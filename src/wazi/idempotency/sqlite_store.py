"""Restart-safe idempotency store on SQLite (standard library, no new dependency).

Why SQLite: the standard library already ships it, it needs no server, it gives an atomic
``INSERT`` (the property ``claim`` needs), and it survives restarts. AleBrito's
whatsapp-ai-agent (MIT) uses the same idea (pattern only; no code copied).

Limits, stated plainly:
* One database file is safe for several threads and several processes on one machine (SQLite
  locking). It is not a network database: several machines need a different store behind the
  same protocols.
* Only the claim key (the provider's message id), a state and two timestamps are stored. No
  message text, no phone numbers. The file still reveals *that* messages were received, so keep
  it out of version control (``*.db`` is git-ignored) and out of backups you do not trust.
* Each call opens a short-lived connection (like AleBrito) so no connection is shared between
  threads. That is plenty for a webhook's rate; a busy deployment would reuse connections.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from wazi.idempotency.store import STATE_CLAIMED, STATE_DONE, STATE_FAILED

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    key        TEXT PRIMARY KEY,
    state      TEXT NOT NULL,
    claimed_at REAL NOT NULL,
    updated_at REAL NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_claims_claimed_at ON claims (claimed_at);
"""


class SqliteIdempotencyStore:
    def __init__(
        self,
        path: str | Path,
        ttl_seconds: float = 7 * 24 * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if str(path) == ":memory:":
            raise ValueError("an in-memory SQLite database is per-connection; use a file path")
        self._path = str(path)
        self._ttl = ttl_seconds
        self._clock = clock  # wall-clock time: it must stay meaningful across restarts
        with closing(self._connect()) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None => autocommit; transactions are explicit below.
        return sqlite3.connect(self._path, timeout=5.0, isolation_level=None)

    def claim(self, key: str) -> bool:
        now = self._clock()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")  # take the write lock: purge + insert are one unit
            try:
                con.execute("DELETE FROM claims WHERE claimed_at < ?", (now - self._ttl,))
                cursor = con.execute(
                    "INSERT OR IGNORE INTO claims (key, state, claimed_at, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (key, STATE_CLAIMED, now, now),
                )
                won = cursor.rowcount == 1
                con.execute("COMMIT")
                return won
            except BaseException:
                con.execute("ROLLBACK")
                raise

    def release(self, key: str) -> None:
        with closing(self._connect()) as con:
            con.execute("DELETE FROM claims WHERE key = ?", (key,))

    def mark_done(self, key: str) -> None:
        self._set_state(key, STATE_DONE)

    def mark_failed(self, key: str) -> None:
        self._set_state(key, STATE_FAILED)

    def state_of(self, key: str) -> str | None:
        with closing(self._connect()) as con:
            row = con.execute("SELECT state FROM claims WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def unfinished_keys(self, older_than_seconds: float = 0.0) -> list[str]:
        """Keys still in ``claimed``: accepted but never marked done/failed.

        After a restart these are the messages that may have been lost mid-processing.
        Re-processing them needs the message content, which is deliberately not stored yet.
        """
        cutoff = self._clock() - older_than_seconds
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT key FROM claims WHERE state = ? AND claimed_at <= ? ORDER BY claimed_at",
                (STATE_CLAIMED, cutoff),
            ).fetchall()
        return [row[0] for row in rows]

    def _set_state(self, key: str, state: str) -> None:
        with closing(self._connect()) as con:
            con.execute(
                "UPDATE claims SET state = ?, updated_at = ? WHERE key = ?",
                (state, self._clock(), key),
            )

    def __len__(self) -> int:
        with closing(self._connect()) as con:
            return con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
