"""End-to-end tests of the POST path through the real FastAPI app (in process, offline)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.helpers import (
    TEST_APP_SECRET,
    FailingDispatcher,
    fixture_bytes,
    signed_headers,
)
from wazi.configuration import Settings
from wazi.idempotency import InMemoryIdempotencyStore
from wazi.messaging import MessageType
from wazi.security import SIGNATURE_HEADER
from wazi.webhook import WEBHOOK_PATH, create_app


def post(client, body: bytes, headers=None):
    return client.post(
        WEBHOOK_PATH, content=body, headers=signed_headers(body) if headers is None else headers
    )


# ---- valid requests ---------------------------------------------------------------------


def test_valid_text_message_is_accepted_and_dispatched_once(client, dispatcher):
    response = post(client, fixture_bytes("text_message"))
    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "accepted": 1,
        "duplicates": 0,
        "unsupported": 0,
        "statuses": 0,
        "invalid": 0,
    }
    assert [m.text for m in dispatcher.messages] == ["Hello Wazi, this is a test."]
    assert dispatcher.messages[0].message_type is MessageType.TEXT


def test_status_update_is_acknowledged_without_dispatch(client, dispatcher):
    response = post(client, fixture_bytes("status_update"))
    assert response.status_code == 200
    assert response.json()["statuses"] == 1
    assert dispatcher.messages == []


def test_non_text_messages_are_acknowledged_but_not_processed(client, dispatcher):
    for name in ("image_message", "audio_message", "location_message", "unknown_message"):
        response = post(client, fixture_bytes(name))
        assert response.status_code == 200, name
        assert response.json()["unsupported"] == 1, name
    assert dispatcher.messages == []


def test_batch_only_text_messages_are_dispatched(client, dispatcher):
    response = post(client, fixture_bytes("multi_message"))
    assert response.status_code == 200
    body = response.json()
    assert (body["accepted"], body["unsupported"], body["statuses"]) == (2, 1, 1)
    assert [m.text for m in dispatcher.messages] == ["first", "second"]


def test_other_webhook_fields_and_broken_items_do_not_cause_errors(client, dispatcher):
    assert post(client, fixture_bytes("other_field_change")).status_code == 200
    response = post(client, fixture_bytes("invalid_message_item"))
    assert response.status_code == 200
    assert response.json()["invalid"] == 1
    assert [m.text for m in dispatcher.messages] == ["still valid"]


# ---- duplicates -------------------------------------------------------------------------


def test_duplicate_delivery_is_acknowledged_but_not_dispatched_again(client, dispatcher):
    body = fixture_bytes("text_message")
    first = post(client, body)
    second = post(client, body)
    assert first.status_code == 200 and second.status_code == 200  # 200 so Meta stops retrying
    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0 and second.json()["duplicates"] == 1
    assert len(dispatcher.messages) == 1


def test_different_message_is_not_a_duplicate(client, dispatcher):
    post(client, fixture_bytes("text_message"))
    post(client, fixture_bytes("multi_message"))
    assert len(dispatcher.messages) == 3


def test_duplicate_inside_one_payload_is_dispatched_once(client, dispatcher):
    payload = json.loads(fixture_bytes("text_message"))
    value = payload["entry"][0]["changes"][0]["value"]
    value["messages"] = value["messages"] * 2
    body = json.dumps(payload).encode()
    response = post(client, body)
    assert response.json()["accepted"] == 1 and response.json()["duplicates"] == 1
    assert len(dispatcher.messages) == 1


# ---- rejected requests ------------------------------------------------------------------


def test_missing_signature_rejected(client, dispatcher):
    response = post(
        client, fixture_bytes("text_message"), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 403
    assert dispatcher.messages == []


def test_invalid_signature_rejected(client, dispatcher):
    headers = {SIGNATURE_HEADER: "sha256=" + "0" * 64}
    assert post(client, fixture_bytes("text_message"), headers=headers).status_code == 403
    assert dispatcher.messages == []


def test_signature_made_with_wrong_secret_rejected(client, dispatcher):
    body = fixture_bytes("text_message")
    response = post(client, body, headers=signed_headers(body, secret="attacker-guess"))
    assert response.status_code == 403
    assert dispatcher.messages == []


def test_malformed_json_with_valid_signature_is_400(client, dispatcher):
    for body in (b"", b"not json", b"{", b"\xff\xfe\x00", b"[1,2,3]", b"null"):
        response = post(client, body)
        assert response.status_code == 400, body
    assert dispatcher.messages == []


def test_valid_json_but_wrong_structure_is_400(client, dispatcher):
    for body in (b'{"hello": "world"}', b'{"object":"whatsapp_business_account","entry":"x"}'):
        assert post(client, body).status_code == 400
    assert dispatcher.messages == []


def test_deeply_nested_json_is_a_clean_400(client):
    body = b"[" * 100_000 + b"]" * 100_000
    assert post(client, body).status_code == 400


def test_oversized_body_rejected_before_signature_work():
    settings = Settings(verify_token="t", app_secret=TEST_APP_SECRET, max_body_bytes=100)
    small_client = TestClient(create_app(settings), raise_server_exceptions=False)
    body = b"x" * 101
    assert post(small_client, body).status_code == 413


def test_missing_app_secret_configuration_rejects_everything(dispatcher):
    unconfigured = TestClient(
        create_app(Settings(verify_token="t", app_secret=None), dispatcher=dispatcher),
        raise_server_exceptions=False,
    )
    body = fixture_bytes("text_message")
    assert post(unconfigured, body).status_code == 503
    assert post(unconfigured, body, headers={"Content-Type": "application/json"}).status_code == 503
    assert dispatcher.messages == []


# ---- failure handling -------------------------------------------------------------------


def test_dispatch_failure_gives_5xx_and_retry_is_not_treated_as_duplicate(settings):
    dispatcher = FailingDispatcher(failures=1)
    client = TestClient(
        create_app(settings, store=InMemoryIdempotencyStore(), dispatcher=dispatcher),
        raise_server_exceptions=False,
    )
    body = fixture_bytes("text_message")
    failed = post(client, body)
    assert failed.status_code == 500
    assert failed.json() == {"error": "internal_error"}
    assert "secret-detail-must-not-leak" not in failed.text

    retry = post(client, body)  # Meta retries the same delivery
    assert retry.status_code == 200
    assert retry.json()["accepted"] == 1 and retry.json()["duplicates"] == 0
    assert len(dispatcher.messages) == 1


def test_unexpected_internal_error_is_generic_500(settings, dispatcher):
    class ExplodingStore:
        def claim(self, key: str) -> bool:
            raise MemoryError("internal-detail-must-not-leak")

        def release(self, key: str) -> None:
            return None

    client = TestClient(
        create_app(settings, store=ExplodingStore(), dispatcher=dispatcher),
        raise_server_exceptions=False,
    )
    response = post(client, fixture_bytes("text_message"))
    assert response.status_code == 500
    assert response.json() == {"error": "internal_error"}
    assert "internal-detail-must-not-leak" not in response.text


# ---- surface ----------------------------------------------------------------------------


def test_no_documentation_endpoints_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_other_methods_not_allowed(client):
    assert client.put(WEBHOOK_PATH).status_code == 405
    assert client.delete(WEBHOOK_PATH).status_code == 405
