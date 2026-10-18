"""The hand-off point between the ingress foundation and the (future) agent.

Phase 4 defines only the contract. No agent, LLM, memory or queue exists yet, so the default
dispatcher does nothing. Later phases plug a real dispatcher in without touching the webhook.

Contract for implementations:
  * ``dispatch`` must return quickly: it should only hand the message to something that does
    the slow work later (a background task, a queue, a worker). It is called inside the HTTP
    request, before Meta gets its acknowledgement.
  * If it raises, the webhook answers 5xx and releases the message's idempotency claim so that
    Meta's retry will be processed rather than discarded as a duplicate.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from wazi.messaging import NormalizedMessage


@runtime_checkable
class MessageDispatcher(Protocol):
    def dispatch(self, message: NormalizedMessage) -> None: ...


class NullDispatcher:
    """Phase 4 default: accepts messages and does nothing with them (NOT IMPLEMENTED: agent)."""

    def dispatch(self, message: NormalizedMessage) -> None:
        return None
