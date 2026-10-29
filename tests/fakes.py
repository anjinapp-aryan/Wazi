"""Fakes for the Phase 5 (walking skeleton) tests. All values are fake."""

from __future__ import annotations

import threading

from wazi.messaging import OutboundReply
from wazi.ports import SendError, SendResult

FAKE_ACCESS_TOKEN = "fake-access-token-for-tests-EAAxxxxxxxx"
FAKE_PHONE_NUMBER_ID = "100000000000001"


class FakeSender:
    """Records replies. Can be scripted to fail, and can block until released."""

    def __init__(self, script: list[Exception | None] | None = None, block: bool = False) -> None:
        self.script = list(script or [])
        self.replies: list[OutboundReply] = []
        self.attempts = 0
        self.closed = False
        self.release_event = threading.Event()
        if not block:
            self.release_event.set()
        self.started = threading.Event()

    def send(self, reply: OutboundReply) -> SendResult:
        self.attempts += 1
        self.started.set()
        self.release_event.wait(timeout=5)
        if self.script:
            outcome = self.script.pop(0)
            if outcome is not None:
                raise outcome
        self.replies.append(reply)
        return SendResult(message_id="wamid.FAKESENT")

    def close(self) -> None:
        self.closed = True


def transient_error(**kw) -> SendError:
    return SendError("transient", retryable=True, **kw)


def permanent_error(**kw) -> SendError:
    return SendError("permanent", retryable=False, **kw)
