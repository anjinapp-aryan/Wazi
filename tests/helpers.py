"""Shared test helpers. All values are fake; nothing here touches the network."""

from __future__ import annotations

import json
from pathlib import Path

from wazi.messaging import NormalizedMessage
from wazi.security import SIGNATURE_HEADER, compute_signature

FIXTURES = Path(__file__).parent / "fixtures"

# Obviously fake secrets. Tests also assert these strings never appear in responses or logs.
TEST_APP_SECRET = "fake-app-secret-for-tests-0123456789"
TEST_VERIFY_TOKEN = "fake-verify-token-for-tests"


def fixture_bytes(name: str) -> bytes:
    """The fixture file's exact bytes, which is what Meta would sign."""
    return (FIXTURES / f"{name}.json").read_bytes()


def fixture_json(name: str) -> dict:
    return json.loads(fixture_bytes(name))


def signed_headers(body: bytes, secret: str = TEST_APP_SECRET) -> dict[str, str]:
    return {SIGNATURE_HEADER: compute_signature(body, secret), "Content-Type": "application/json"}


class RecordingDispatcher:
    """Stands in for the future agent: records what reached the downstream hand-off."""

    def __init__(self) -> None:
        self.messages: list[NormalizedMessage] = []

    def dispatch(self, message: NormalizedMessage) -> None:
        self.messages.append(message)


class FailingDispatcher:
    """Raises on the first N calls, then succeeds. Simulates a downstream outage."""

    def __init__(self, failures: int = 1) -> None:
        self.remaining_failures = failures
        self.messages: list[NormalizedMessage] = []

    def dispatch(self, message: NormalizedMessage) -> None:
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise RuntimeError("downstream unavailable: secret-detail-must-not-leak")
        self.messages.append(message)
