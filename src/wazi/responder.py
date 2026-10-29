"""Phase 5 fake responder: proves the loop without any model.

NOT IMPLEMENTED (future): the real agent (LangGraph, memory, RAG, tools) will implement the
same ``Responder`` protocol from ``wazi.ports``.
"""

from __future__ import annotations

from wazi.messaging import NormalizedMessage, OutboundReply

MAX_ECHO_CHARS = 500


class EchoResponder:
    def respond(self, message: NormalizedMessage) -> OutboundReply | None:
        if message.text is None:
            return None
        text = message.text.strip()
        if not text:
            return None
        return OutboundReply(
            recipient_id=message.sender_id,
            text=f"Wazi skeleton echo: {text[:MAX_ECHO_CHARS]}",
            in_reply_to=message.message_id,
        )
