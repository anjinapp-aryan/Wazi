"""Phase 6: behaviour that follows directly from Meta's CURRENT documentation (checked 2026-10-29).

Each test names the documented statement it protects. They run offline against fake values;
the only real-Meta checks live in tests/live/ and never run by default.
"""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from tests.fakes import FakeSender
from tests.helpers import (
    TEST_APP_SECRET,
    TEST_VERIFY_TOKEN,
    RecordingDispatcher,
    fixture_bytes,
    signed_headers,
)
from wazi.bootstrap import build_app
from wazi.configuration import Settings
from wazi.messaging import MessageType, normalize_payload
from wazi.responder import EchoResponder
from wazi.safe_logging import fingerprint
from wazi.webhook import WEBHOOK_PATH, create_app
from wazi.worker import BackgroundDispatcher

MB = 1_000_000


def post(client, body: bytes):
    return client.post(WEBHOOK_PATH, content=body, headers=signed_headers(body))


def text_payload_with(messages: list[dict]) -> bytes:
    payload = json.loads(fixture_bytes("text_message"))
    payload["entry"][0]["changes"][0]["value"]["messages"] = messages
    return json.dumps(payload).encode()


def text_message(n: int, body: str = "hi") -> dict:
    return {
        "from": "15550001111",
        "id": f"wamid.FAKEBATCH{n:05d}",
        "timestamp": "1749416383",
        "type": "text",
        "text": {"body": body},
    }


# "Webhook payloads can be up to 3 MB."


def test_default_body_limit_accepts_the_documented_maximum_payload():
    settings = Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)
    assert settings.max_body_bytes >= 3 * MB
    dispatcher = RecordingDispatcher()
    client = TestClient(create_app(settings, dispatcher=dispatcher), raise_server_exceptions=False)
    body = text_payload_with([text_message(1, "x" * (3 * MB - 2000))])
    assert 2.9 * MB < len(body) <= 3 * MB
    response = post(client, body)
    assert response.status_code == 200 and response.json()["accepted"] == 1
    assert len(dispatcher.messages) == 1


def test_a_payload_far_above_the_documented_maximum_is_still_refused():
    settings = Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    assert post(client, b"x" * (5 * MB)).status_code == 413


# "Batches have a maximum of 1000 updates."


def test_a_maximal_batch_of_1000_messages_fits_the_default_queue():
    settings = Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)
    sender = FakeSender()
    dispatcher = BackgroundDispatcher(
        EchoResponder(), sender, max_pending=settings.max_pending, max_workers=4
    )
    client = TestClient(create_app(settings, dispatcher=dispatcher), raise_server_exceptions=False)
    body = text_payload_with([text_message(n) for n in range(1000)])
    response = post(client, body)
    assert response.status_code == 200
    assert response.json()["accepted"] == 1000
    assert dispatcher.wait_idle(30)
    assert len(sender.replies) == 1000
    dispatcher.close()


def test_default_queue_capacity_matches_the_documented_batch_size():
    assert Settings().max_pending >= 1000


# Meta's own example payload (copied from the WhatsApp webhook reference) must parse.


def test_meta_documented_example_payload_normalises():
    result = normalize_payload(json.loads(fixture_bytes("meta_documented_example_text")))
    (message,) = result.messages
    assert message.message_type is MessageType.TEXT
    assert message.text == "Does it come in another color?"
    assert message.sender_id == "16505551234"
    assert message.phone_number_id == "106540352242922"
    assert result.invalid_messages == 0


def test_meta_documented_example_flows_through_the_whole_skeleton():
    # Same bytes Meta documents, signed with a fake secret as Meta would sign them.
    app = build_app(Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET))
    body = fixture_bytes("meta_documented_example_text")
    with TestClient(app) as client:
        assert post(client, body).json()["accepted"] == 1
        assert app.state.dispatcher.wait_idle(5)
    (reply,) = app.state.sender.sent
    assert reply.recipient_id == "16505551234"
    assert reply.text == "Wazi skeleton echo: Does it come in another color?"


# GET: "respond with HTTP status 200 and the hub.challenge value"; otherwise anything but 200.


def test_handshake_returns_exactly_the_challenge_with_status_200():
    settings = Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)
    client = TestClient(create_app(settings))
    params = {
        "hub.mode": "subscribe",
        "hub.challenge": "1158201444",
        "hub.verify_token": TEST_VERIFY_TOKEN,
    }
    response = client.get(WEBHOOK_PATH, params=params)
    assert (response.status_code, response.content) == (200, b"1158201444")
    params["hub.verify_token"] = "wrong"
    assert client.get(WEBHOOK_PATH, params=params).status_code != 200


# Unsupported inbound types carry an "errors" array (code 131051) and must simply be acknowledged.


def test_unsupported_message_type_with_errors_array_is_acknowledged_without_reply():
    app = build_app(Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET))
    body = fixture_bytes("unsupported_message")
    with TestClient(app) as client:
        response = post(client, body)
        assert response.status_code == 200 and response.json()["unsupported"] == 1
        assert app.state.dispatcher.wait_idle(5)
    assert list(app.state.sender.sent) == []


# Observability: one inbound message is traceable webhook -> worker -> Meta's id for our reply.


def test_one_message_can_be_traced_across_layers_without_leaking_identifiers(caplog):
    class SendsWithMetaId(FakeSender):
        pass

    sender = SendsWithMetaId()
    app = build_app(
        Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET), sender=sender
    )
    body = fixture_bytes("text_message")
    with caplog.at_level(logging.INFO), TestClient(app) as client:
        post(client, body)
        assert app.state.dispatcher.wait_idle(5)
    lines = [r.getMessage() for r in caplog.records if r.name.startswith("wazi")]
    tag = fingerprint("wamid.FAKETEXT001")
    queued = [line for line in lines if line.startswith("message queued")]
    sent = [line for line in lines if line.startswith("reply sent")]
    assert queued == [f"message queued id={tag}"]
    assert len(sent) == 1 and f"id={tag}" in sent[0]
    assert f"sent_id={fingerprint('wamid.FAKESENT')}" in sent[0]  # Meta's id for OUR reply
    joined = "\n".join(lines)
    for forbidden in ("wamid.FAKETEXT001", "wamid.FAKESENT", "15550001111", "Hello Wazi"):
        assert forbidden not in joined


# Server logging: opt-in entry point only; build_app must not touch logger configuration.


def test_build_app_does_not_change_logger_configuration():
    import logging as _logging

    wazi_logger = _logging.getLogger("wazi")
    before = (wazi_logger.level, list(wazi_logger.handlers), wazi_logger.propagate)
    build_app(Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET))
    assert (wazi_logger.level, list(wazi_logger.handlers), wazi_logger.propagate) == before


def test_configure_logging_is_idempotent_and_restorable(monkeypatch):
    import logging as _logging

    from wazi.bootstrap import configure_logging

    wazi_logger = _logging.getLogger("wazi")
    saved = (wazi_logger.level, list(wazi_logger.handlers), wazi_logger.propagate)
    try:
        configure_logging("INFO")
        configure_logging("INFO")
        ours = [h for h in wazi_logger.handlers if getattr(h, "_wazi", False)]
        assert len(ours) == 1 and wazi_logger.level == _logging.INFO
    finally:
        wazi_logger.setLevel(saved[0])
        wazi_logger.handlers[:] = saved[1]
        wazi_logger.propagate = saved[2]
