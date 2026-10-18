from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.helpers import fixture_json
from wazi.messaging import MessageType, NormalizedMessage, PayloadError, normalize_payload


def only_message(name: str) -> NormalizedMessage:
    result = normalize_payload(fixture_json(name))
    assert len(result.messages) == 1
    return result.messages[0]


def test_text_message():
    message = only_message("text_message")
    assert message.message_type is MessageType.TEXT
    assert message.text == "Hello Wazi, this is a test."
    assert message.message_id == "wamid.FAKETEXT001"
    assert message.sender_id == "15550001111"
    assert message.phone_number_id == "100000000000001"
    assert message.provider_type == "text"
    assert message.timestamp == datetime.fromtimestamp(1749416383, tz=UTC)
    assert message.timestamp.tzinfo is not None


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("image_message", MessageType.IMAGE),
        ("audio_message", MessageType.AUDIO),
        ("video_message", MessageType.VIDEO),
        ("document_message", MessageType.DOCUMENT),
        ("location_message", MessageType.LOCATION),
        ("interactive_message", MessageType.INTERACTIVE),
    ],
)
def test_recognised_non_text_types_are_classified_without_content(fixture, expected):
    message = only_message(fixture)
    assert message.message_type is expected
    assert message.text is None  # no media/coordinates/replies are parsed in Phase 4


@pytest.mark.parametrize("fixture", ["unknown_message", "unsupported_message"])
def test_unknown_types_become_unknown_and_keep_the_provider_type(fixture):
    message = only_message(fixture)
    assert message.message_type is MessageType.UNKNOWN
    assert message.provider_type in {"sticker", "unsupported"}
    assert message.text is None


def test_status_update_yields_no_messages_but_is_counted():
    result = normalize_payload(fixture_json("status_update"))
    assert result.messages == ()
    assert result.status_events == 1
    assert result.invalid_messages == 0


def test_multiple_messages_and_statuses_in_one_payload():
    result = normalize_payload(fixture_json("multi_message"))
    assert [m.message_type for m in result.messages] == [
        MessageType.TEXT,
        MessageType.TEXT,
        MessageType.IMAGE,
    ]
    assert result.status_events == 1


def test_non_message_field_is_ignored_not_an_error():
    result = normalize_payload(fixture_json("other_field_change"))
    assert result.messages == ()
    assert result.ignored_changes == 1


def test_one_broken_item_is_skipped_and_counted_others_survive():
    result = normalize_payload(fixture_json("invalid_message_item"))
    assert result.invalid_messages == 1
    assert [m.text for m in result.messages] == ["still valid"]


def test_repr_hides_personal_data():
    message = only_message("text_message")
    text = repr(message)
    assert "15550001111" not in text
    assert "Hello Wazi" not in text
    assert "wamid" not in text


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "string",
        42,
        {},
        {"object": "page", "entry": []},
        {"object": "whatsapp_business_account"},
        {"object": "whatsapp_business_account", "entry": {}},
        {"object": "whatsapp_business_account", "entry": ["x"]},
        {"object": "whatsapp_business_account", "entry": [{}]},
        {"object": "whatsapp_business_account", "entry": [{"changes": "x"}]},
        {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages"}]}]},
        {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": {"messages": []}}]}],
        },  # no metadata
        {
            "object": "whatsapp_business_account",
            "entry": [
                {"changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": ""}}}]}
            ],
        },
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {"metadata": {"phone_number_id": "1"}, "messages": "x"},
                        }
                    ]
                }
            ],
        },
    ],
)
def test_broken_envelopes_raise_payload_error(payload):
    with pytest.raises(PayloadError):
        normalize_payload(payload)


def _single(item) -> object:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {"metadata": {"phone_number_id": "1"}, "messages": [item]},
                    }
                ]
            }
        ],
    }


@pytest.mark.parametrize(
    "item",
    [
        "not an object",
        None,
        {},
        {"id": "a", "from": "b", "type": "text", "timestamp": "1", "text": {}},  # no body
        {"id": "a", "from": "b", "type": "text", "timestamp": "1", "text": "hi"},  # body not object
        {"id": "a", "from": "b", "type": "text", "timestamp": "1", "text": {"body": 5}},
        {"id": "", "from": "b", "type": "text", "timestamp": "1", "text": {"body": "x"}},
        {"id": "a", "from": "", "type": "text", "timestamp": "1", "text": {"body": "x"}},
        {"id": 7, "from": "b", "type": "text", "timestamp": "1", "text": {"body": "x"}},
        {
            "id": "a",
            "from": "b",
            "type": "text",
            "timestamp": "not-a-number",
            "text": {"body": "x"},
        },
        {"id": "a", "from": "b", "type": "text", "timestamp": True, "text": {"body": "x"}},
        {
            "id": "a",
            "from": "b",
            "type": "text",
            "timestamp": "99999999999999999999",
            "text": {"body": "x"},
        },
        {"id": "a", "from": "b", "type": "", "timestamp": "1"},
        {"id": "a", "from": "b", "type": 5, "timestamp": "1"},
        {"id": "a" * 513, "from": "b", "type": "image", "timestamp": "1"},
    ],
)
def test_malformed_message_items_are_counted_not_raised(item):
    result = normalize_payload(_single(item))
    assert result.messages == ()
    assert result.invalid_messages == 1
