"""Internal message model. The future agent layer receives these, never raw Meta JSON."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class MessageType(enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    INTERACTIVE = "interactive"
    UNKNOWN = "unknown"


class PayloadError(ValueError):
    """The webhook body is not a structurally valid WhatsApp webhook envelope.

    The message is a short fixed description. It never contains payload content, so it is
    safe to log, but callers should still not return it verbatim to the HTTP client.
    """


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    """One inbound user message, independent of Meta's payload layout.

    Fields come from the documented WhatsApp Cloud API webhook:
      message_id        ``messages[].id`` (the ``wamid...`` value); the de-duplication key
      sender_id         ``messages[].from``, the sender's WhatsApp id (a phone number)
      message_type      Wazi's classification of ``messages[].type``
      provider_type     the original Meta type string (kept for diagnostics, e.g. "sticker")
      text              ``messages[].text.body`` for text messages, otherwise None
      timestamp         ``messages[].timestamp`` (Unix seconds in Meta's payload) as UTC datetime
      phone_number_id   ``metadata.phone_number_id``: which business number received it

    Deliberately NOT stored: the raw payload, the sender's profile name, media ids/URLs.
    ``repr`` hides the sender and the text so a stray log line cannot leak personal data.
    """

    message_id: str
    sender_id: str
    message_type: MessageType
    provider_type: str
    text: str | None
    timestamp: datetime
    phone_number_id: str

    def __repr__(self) -> str:  # personal data is redacted on purpose
        return (
            f"NormalizedMessage(type={self.message_type.value}, has_text={self.text is not None})"
        )


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Everything extracted from one webhook body."""

    messages: tuple[NormalizedMessage, ...] = ()
    status_events: int = 0  # delivery/read receipts: valid, ignored
    ignored_changes: int = 0  # change objects whose ``field`` is not "messages"
    invalid_messages: int = 0  # message items missing required fields: skipped
