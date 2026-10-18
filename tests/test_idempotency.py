from __future__ import annotations

import threading

import pytest

from wazi.idempotency import IdempotencyStore, InMemoryIdempotencyStore


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_first_claim_accepted():
    assert InMemoryIdempotencyStore().claim("wamid.A") is True


def test_same_key_rejected_second_time():
    store = InMemoryIdempotencyStore()
    assert store.claim("wamid.A") is True
    assert store.claim("wamid.A") is False
    assert store.claim("wamid.A") is False


def test_different_key_accepted():
    store = InMemoryIdempotencyStore()
    assert store.claim("wamid.A") is True
    assert store.claim("wamid.B") is True


def test_release_allows_reclaim():
    store = InMemoryIdempotencyStore()
    store.claim("wamid.A")
    store.release("wamid.A")
    assert store.claim("wamid.A") is True


def test_release_of_unknown_key_is_harmless():
    InMemoryIdempotencyStore().release("never-claimed")


def test_entries_expire_after_ttl():
    clock = FakeClock()
    store = InMemoryIdempotencyStore(ttl_seconds=60, clock=clock)
    store.claim("wamid.A")
    clock.now += 59
    assert store.claim("wamid.A") is False
    clock.now += 2  # 61s after the claim
    assert store.claim("wamid.A") is True


def test_store_is_bounded_and_evicts_oldest_first():
    store = InMemoryIdempotencyStore(max_entries=2)
    store.claim("a")
    store.claim("b")
    store.claim("c")  # evicts "a"
    assert len(store) == 2
    assert "a" not in store
    assert "b" in store and "c" in store


def test_invalid_construction_arguments():
    with pytest.raises(ValueError):
        InMemoryIdempotencyStore(max_entries=0)
    with pytest.raises(ValueError):
        InMemoryIdempotencyStore(ttl_seconds=0)


def test_exactly_one_winner_under_concurrency():
    store = InMemoryIdempotencyStore()
    results: list[bool] = []
    barrier = threading.Barrier(16)

    def worker() -> None:
        barrier.wait()
        results.append(store.claim("wamid.RACE"))

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == 1
    assert results.count(False) == 15


def test_implementation_satisfies_the_protocol_so_it_can_be_swapped():
    assert isinstance(InMemoryIdempotencyStore(), IdempotencyStore)

    class OtherBackend:  # stands in for a future database/cache-backed store
        def claim(self, key: str) -> bool:
            return True

        def release(self, key: str) -> None:
            return None

    assert isinstance(OtherBackend(), IdempotencyStore)
