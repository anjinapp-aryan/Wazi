"""SQLite idempotency store: persistence, atomicity, expiry, states."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing

import pytest

from wazi.idempotency import (
    CompletionRecorder,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    SqliteIdempotencyStore,
)


class WallClock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def db(tmp_path):
    return tmp_path / "idempotency.db"


def test_first_claim_accepted_then_duplicate_rejected(db):
    store = SqliteIdempotencyStore(db)
    assert store.claim("wamid.A") is True
    assert store.claim("wamid.A") is False
    assert store.claim("wamid.B") is True


def test_claims_survive_a_restart(db):
    SqliteIdempotencyStore(db).claim("wamid.A")
    after_restart = SqliteIdempotencyStore(db)  # a brand-new object on the same file
    assert after_restart.claim("wamid.A") is False
    assert after_restart.claim("wamid.NEW") is True


def test_release_allows_reclaim_even_across_instances(db):
    SqliteIdempotencyStore(db).claim("wamid.A")
    SqliteIdempotencyStore(db).release("wamid.A")
    assert SqliteIdempotencyStore(db).claim("wamid.A") is True


def test_release_of_unknown_key_is_harmless(db):
    SqliteIdempotencyStore(db).release("never-claimed")


def test_entries_expire_after_ttl_and_are_purged(db):
    clock = WallClock()
    store = SqliteIdempotencyStore(db, ttl_seconds=60, clock=clock)
    store.claim("old")
    clock.now += 59
    assert store.claim("old") is False
    clock.now += 2  # 61 s after the claim
    assert store.claim("other") is True  # this claim purges "old"
    assert len(store) == 1
    assert store.claim("old") is True


def test_states_claimed_done_failed(db):
    store = SqliteIdempotencyStore(db)
    assert store.state_of("wamid.A") is None
    store.claim("wamid.A")
    assert store.state_of("wamid.A") == "claimed"
    store.mark_done("wamid.A")
    assert store.state_of("wamid.A") == "done"
    store.claim("wamid.B")
    store.mark_failed("wamid.B")
    assert store.state_of("wamid.B") == "failed"


def test_marking_an_unknown_key_does_not_create_it(db):
    store = SqliteIdempotencyStore(db)
    store.mark_done("ghost")
    assert store.state_of("ghost") is None
    assert len(store) == 0


def test_unfinished_keys_lists_only_claimed_and_respects_age(db):
    clock = WallClock()
    store = SqliteIdempotencyStore(db, clock=clock)
    store.claim("stuck")
    store.claim("finished")
    store.mark_done("finished")
    clock.now += 100
    store.claim("recent")
    assert store.unfinished_keys() == ["stuck", "recent"]
    assert store.unfinished_keys(older_than_seconds=50) == ["stuck"]


def test_exactly_one_winner_with_many_threads_sharing_one_store(db):
    store = SqliteIdempotencyStore(db)
    results: list[bool] = []
    barrier = threading.Barrier(12)

    def worker() -> None:
        barrier.wait()
        results.append(store.claim("wamid.RACE"))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1 and results.count(False) == 11


def test_exactly_one_winner_with_separate_store_objects_on_one_file(db):
    # Like several worker processes opening the same database file.
    SqliteIdempotencyStore(db)  # create the schema once
    results: list[bool] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        own_store = SqliteIdempotencyStore(db)
        barrier.wait()
        results.append(own_store.claim("wamid.RACE2"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 1 and results.count(False) == 7


def test_in_memory_path_and_bad_ttl_are_rejected(db):
    with pytest.raises(ValueError):
        SqliteIdempotencyStore(":memory:")
    with pytest.raises(ValueError):
        SqliteIdempotencyStore(db, ttl_seconds=0)


def test_database_stores_no_message_content_only_keys_states_and_times(db):
    SqliteIdempotencyStore(db).claim("wamid.A")
    with closing(sqlite3.connect(db)) as con:
        columns = [row[1] for row in con.execute("PRAGMA table_info(claims)")]
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    assert columns == ["key", "state", "claimed_at", "updated_at"]
    assert tables == ["claims"]


def test_both_stores_satisfy_both_protocols(db):
    for store in (SqliteIdempotencyStore(db), InMemoryIdempotencyStore()):
        assert isinstance(store, IdempotencyStore)
        assert isinstance(store, CompletionRecorder)


def test_in_memory_store_tracks_states_too():
    store = InMemoryIdempotencyStore()
    store.claim("wamid.A")
    assert store.state_of("wamid.A") == "claimed"
    store.mark_done("wamid.A")
    assert store.state_of("wamid.A") == "done"
    store.mark_failed("wamid.A")
    assert store.state_of("wamid.A") == "failed"
    store.mark_done("ghost")
    assert store.state_of("ghost") is None
