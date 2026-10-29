"""Contracts between the processing worker and the things it calls.

Kept separate from the implementations so the worker depends only on these small interfaces:
the (future) agent behind ``Responder`` and the WhatsApp delivery behind ``ReplySender`` can be
replaced or faked independently. Depends on ``messaging`` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from wazi.messaging import NormalizedMessage, OutboundReply


@runtime_checkable
class Responder(Protocol):
    """Turns one inbound message into a reply. Phase 5: a fake. Later phases: the agent."""

    def respond(self, message: NormalizedMessage) -> OutboundReply | None:
        """Return the reply, or None when no reply should be sent."""
        ...


@dataclass(frozen=True, slots=True)
class SendResult:
    message_id: str | None  # the provider's id for the sent message, when known


class SendError(Exception):
    """Delivery failed. Carries only classification, never request/response content.

    retryable   True when trying again later could succeed (network trouble, rate limits,
                server errors); False for permanent problems (bad token, bad recipient,
                outside the 24-hour window, invalid request).
    retry_after seconds the provider asked us to wait, when it said so.
    """

    def __init__(
        self,
        description: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        error_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(description)
        self.retryable = retryable
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after = retry_after


@runtime_checkable
class ReplySender(Protocol):
    """Delivers a reply to the user. One attempt per call; the caller decides about retries."""

    def send(self, reply: OutboundReply) -> SendResult:
        """Raise ``SendError`` on failure."""
        ...
