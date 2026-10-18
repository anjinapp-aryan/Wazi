"""Translate a parsed WhatsApp Cloud API webhook body into ``NormalizedMessage`` objects.

Payload shape used (official WhatsApp Cloud API webhook example):

    {"object": "whatsapp_business_account",
     "entry": [{"id": "...",
                "changes": [{"field": "messages",
                             "value": {"messaging_product": "whatsapp",
                                       "metadata": {"display_phone_number": "...",
                                                    "phone_number_id": "..."},
                                       "contacts": [{"profile": {"name": "..."}, "wa_id": "..."}],
                                       "messages": [{"from": "...", "id": "wamid...",
                                                     "timestamp": "1749416383", "type": "text",
                                                     "text": {"body": "..."}}],
                                       "statuses": [...]}}]}]}

Differences from Ava's handler (which read only ``entry[0].changes[0].value.messages[0]``):
all entries, changes and messages are processed; ``statuses`` are counted, not treated as
errors; unknown types are classified rather than crashing.

Error policy:
  * Structurally broken envelope  -> ``PayloadError`` (the HTTP layer answers 400).
  * One broken message item inside an otherwise valid envelope -> skipped and counted in
    ``invalid_messages``. Rejecting the whole payload would make Meta retry a body that can
    never become valid.

Only the ``type`` string and, for text, ``text.body`` are read from each message. Per-type
fields (media ids, coordinates, button replies) are not parsed because Phase 4 does not
process them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from wazi.messaging.models import (
    MessageType,
    NormalizationResult,
    NormalizedMessage,
    PayloadError,
)

EXPECTED_OBJECT = "whatsapp_business_account"
_MAX_ID_LENGTH = 512

_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "audio": MessageType.AUDIO,
    "video": MessageType.VIDEO,
    "document": MessageType.DOCUMENT,
    "location": MessageType.LOCATION,
    "interactive": MessageType.INTERACTIVE,
}


def _require_dict(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PayloadError(f"{what} must be an object")
    return value


def _require_list(value: Any, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise PayloadError(f"{what} must be an array")
    return value


def _non_empty_str(value: Any) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= _MAX_ID_LENGTH:
        return value
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    """Meta sends Unix seconds as a string, for example "1749416383"."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _normalize_message(item: Any, phone_number_id: str) -> NormalizedMessage | None:
    """Return None when the item lacks the fields needed to identify and order it."""
    if not isinstance(item, dict):
        return None
    message_id = _non_empty_str(item.get("id"))
    sender_id = _non_empty_str(item.get("from"))
    provider_type = item.get("type")
    timestamp = _parse_timestamp(item.get("timestamp"))
    if message_id is None or sender_id is None or timestamp is None:
        return None
    if not isinstance(provider_type, str) or not provider_type:
        return None

    message_type = _TYPE_MAP.get(provider_type, MessageType.UNKNOWN)
    text: str | None = None
    if message_type is MessageType.TEXT:
        body = item.get("text")
        text = body.get("body") if isinstance(body, dict) else None
        if not isinstance(text, str):
            return None  # a "text" message without a body is malformed

    return NormalizedMessage(
        message_id=message_id,
        sender_id=sender_id,
        message_type=message_type,
        provider_type=provider_type,
        text=text,
        timestamp=timestamp,
        phone_number_id=phone_number_id,
    )


def normalize_payload(payload: Any) -> NormalizationResult:
    """Convert a decoded JSON webhook body. Raises ``PayloadError`` if the envelope is invalid."""
    body = _require_dict(payload, "payload")
    if body.get("object") != EXPECTED_OBJECT:
        raise PayloadError("unexpected payload object")

    messages: list[NormalizedMessage] = []
    status_events = 0
    ignored_changes = 0
    invalid_messages = 0

    for entry in _require_list(body.get("entry"), "entry"):
        entry = _require_dict(entry, "entry item")
        for change in _require_list(entry.get("changes"), "changes"):
            change = _require_dict(change, "change item")
            if change.get("field") != "messages":
                ignored_changes += 1
                continue

            value = _require_dict(change.get("value"), "value")
            metadata = _require_dict(value.get("metadata"), "metadata")
            phone_number_id = _non_empty_str(metadata.get("phone_number_id"))
            if phone_number_id is None:
                raise PayloadError("metadata.phone_number_id missing")

            statuses = value.get("statuses")
            if statuses is not None:
                status_events += len(_require_list(statuses, "statuses"))

            raw_messages = value.get("messages")
            if raw_messages is None:
                continue
            for item in _require_list(raw_messages, "messages"):
                message = _normalize_message(item, phone_number_id)
                if message is None:
                    invalid_messages += 1
                else:
                    messages.append(message)

    return NormalizationResult(
        messages=tuple(messages),
        status_events=status_events,
        ignored_changes=ignored_changes,
        invalid_messages=invalid_messages,
    )
