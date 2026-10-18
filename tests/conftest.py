from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from tests.helpers import TEST_APP_SECRET, TEST_VERIFY_TOKEN, RecordingDispatcher
from wazi.configuration import Settings
from wazi.idempotency import InMemoryIdempotencyStore
from wazi.webhook import create_app


@pytest.fixture(autouse=True)
def _offline_guard(monkeypatch):
    """Phase 4 must run fully offline: any attempt to reach a non-loopback host fails the test."""
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError(f"test attempted a network connection to {host!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def settings() -> Settings:
    return Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)


@pytest.fixture
def dispatcher() -> RecordingDispatcher:
    return RecordingDispatcher()


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


@pytest.fixture
def client(settings, dispatcher, store) -> TestClient:
    app = create_app(settings, store=store, dispatcher=dispatcher)
    return TestClient(app, raise_server_exceptions=False)
