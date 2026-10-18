"""Architectural security invariants. If any of these fail, the foundation is unsafe.

Each test is named after the rule it protects.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from tests.helpers import (
    TEST_APP_SECRET,
    TEST_VERIFY_TOKEN,
    RecordingDispatcher,
    fixture_bytes,
    signed_headers,
)
from wazi.configuration import Settings
from wazi.idempotency import InMemoryIdempotencyStore
from wazi.security import SIGNATURE_HEADER, compute_signature
from wazi.webhook import WEBHOOK_PATH, create_app

# A well-formed but wrong signature; it must never be echoed into responses or logs.
ATTACKER_SIGNATURE = "sha256=" + "deadbeef" * 8


def post(client, body: bytes, headers=None):
    return client.post(
        WEBHOOK_PATH, content=body, headers=signed_headers(body) if headers is None else headers
    )


def test_no_signature_means_rejected(client, dispatcher):
    response = post(client, fixture_bytes("text_message"), headers={})
    assert response.status_code == 403
    assert dispatcher.messages == []


def test_invalid_signature_means_rejected(client, dispatcher):
    response = post(
        client, fixture_bytes("text_message"), headers={SIGNATURE_HEADER: "sha256=" + "a" * 64}
    )
    assert response.status_code == 403
    assert dispatcher.messages == []


def test_valid_signature_but_modified_body_means_rejected(client, dispatcher):
    original = fixture_bytes("text_message")
    headers = signed_headers(original)  # signature of the ORIGINAL bytes
    tampered = original.replace(b"Hello Wazi", b"Jello Wazi")
    assert tampered != original
    response = post(client, tampered, headers=headers)
    assert response.status_code == 403
    assert dispatcher.messages == []


def test_missing_verification_token_configuration_means_rejected():
    client = TestClient(
        create_app(Settings(verify_token=None, app_secret=TEST_APP_SECRET)),
        raise_server_exceptions=False,
    )
    params = {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "42"}
    assert client.get(WEBHOOK_PATH, params=params).status_code == 403
    del params["hub.verify_token"]
    assert client.get(WEBHOOK_PATH, params=params).status_code == 403


def test_missing_app_secret_configuration_means_nothing_is_processed():
    dispatcher = RecordingDispatcher()
    client = TestClient(
        create_app(Settings(verify_token="t", app_secret=None), dispatcher=dispatcher),
        raise_server_exceptions=False,
    )
    body = fixture_bytes("text_message")
    # Even a signature computed with an empty key must not get a message through.
    response = post(client, body, headers={SIGNATURE_HEADER: compute_signature(body, "")})
    assert response.status_code == 503
    assert dispatcher.messages == []


def test_signature_is_checked_on_raw_bytes_not_on_reserialised_json(client, dispatcher):
    original = fixture_bytes("text_message")
    reserialised = json.dumps(json.loads(original)).encode()  # same meaning, different bytes
    assert reserialised != original
    # Sender signed the original bytes; the receiver is handed different bytes => reject.
    assert post(client, reserialised, headers=signed_headers(original)).status_code == 403
    # Conversely, unusual-but-valid bytes signed exactly as sent must be accepted.
    odd = (
        b'{"entry":[{"changes":[{"value":{"metadata":{"phone_number_id":"1"},'
        b'"messages":[{"id":"wamid.ODD","from":"15550003333","timestamp":"1749416383",'
        rb'"type":"text","text":{"body":"caf\u00e9"}}]},"field":"messages"}]}],'
        b'"object":"whatsapp_business_account"}'
    )
    response = post(client, odd)
    assert response.status_code == 200
    assert dispatcher.messages[-1].text == "café"


def test_signature_is_checked_before_json_is_parsed(client):
    # Garbage with a bad signature must look the same as any unauthenticated request (403),
    # not like a parse error (400), so unauthenticated callers learn nothing about parsing.
    assert (
        post(client, b"not json", headers={SIGNATURE_HEADER: "sha256=" + "0" * 64}).status_code
        == 403
    )


def test_duplicate_message_never_reaches_downstream_twice(client, dispatcher):
    body = fixture_bytes("text_message")
    statuses = [post(client, body).status_code for _ in range(5)]
    assert statuses == [200] * 5
    assert len(dispatcher.messages) == 1


def _all_kinds_of_requests(client):
    good = fixture_bytes("text_message")
    yield client.get(
        WEBHOOK_PATH,
        params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "1"},
    )
    yield client.get(
        WEBHOOK_PATH,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TEST_VERIFY_TOKEN,
            "hub.challenge": "1",
        },
    )
    yield client.get(WEBHOOK_PATH)
    yield post(client, good)
    yield post(client, good)  # duplicate
    yield post(client, good, headers={})
    yield post(client, good, headers={SIGNATURE_HEADER: "sha256=zz"})
    yield post(client, good, headers={SIGNATURE_HEADER: ATTACKER_SIGNATURE})
    yield post(client, b"not json")
    yield post(client, b'{"x": 1}')
    yield post(client, b"x" * 2_000_000, headers={})  # oversized


def test_secrets_and_signatures_never_appear_in_any_response(client):
    forbidden = [
        TEST_APP_SECRET,
        TEST_VERIFY_TOKEN,
        compute_signature(fixture_bytes("text_message"), TEST_APP_SECRET),
    ]
    for response in _all_kinds_of_requests(client):
        haystack = response.text + json.dumps(dict(response.headers))
        for secret in forbidden:
            assert secret not in haystack
        assert "Traceback" not in response.text


def test_error_responses_are_generic(client):
    for response in _all_kinds_of_requests(client):
        if response.status_code >= 400:
            assert set(response.json()) == {"error"}


def test_logs_never_contain_secrets_signatures_bodies_or_personal_data(caplog):
    settings = Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)
    client = TestClient(
        create_app(settings, store=InMemoryIdempotencyStore(), dispatcher=RecordingDispatcher()),
        raise_server_exceptions=False,
    )
    body = fixture_bytes("text_message")
    signature = compute_signature(body, TEST_APP_SECRET)
    with caplog.at_level(logging.DEBUG):  # DEBUG is the most verbose we ever log
        for _ in _all_kinds_of_requests(client):
            pass
    # Only Wazi's own loggers are checked. Third-party loggers are a deployment concern: for
    # example the HTTP test client (httpx) and uvicorn's access log both print the full request
    # URL, and Meta's GET handshake carries hub.verify_token in the query string. Production
    # runs must disable or filter the server access log (see docs/PHASE_4_FOUNDATION.md).
    logged = "\n".join(
        record.getMessage() for record in caplog.records if record.name.startswith("wazi")
    )
    assert logged, "expected the webhook to log something"
    for forbidden in (
        TEST_APP_SECRET,
        TEST_VERIFY_TOKEN,
        signature,
        signature.removeprefix("sha256="),
        ATTACKER_SIGNATURE,
        "deadbeef",
        "Hello Wazi",  # message text
        "15550001111",  # sender phone number
        "15550002222",  # business display number
        "100000000000001",  # phone_number_id
        "wamid.FAKETEXT001",  # raw message id (only a fingerprint may be logged)
        "Fake User",  # profile name
    ):
        assert forbidden not in logged


def test_settings_repr_does_not_leak_secrets():
    text = repr(Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET))
    assert TEST_VERIFY_TOKEN not in text
    assert TEST_APP_SECRET not in text


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_blank_environment_values_count_as_not_configured(value):
    settings = Settings.from_env(
        {"WAZI_WHATSAPP_VERIFY_TOKEN": value, "WAZI_WHATSAPP_APP_SECRET": value}
    )
    assert settings.verify_token is None and settings.app_secret is None
