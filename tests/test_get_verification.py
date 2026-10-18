"""GET verification: pure decision function plus the HTTP endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import TEST_APP_SECRET, TEST_VERIFY_TOKEN
from wazi.configuration import Settings
from wazi.security import HandshakeOutcome, evaluate_handshake
from wazi.webhook import WEBHOOK_PATH, create_app

OK_PARAMS = {
    "hub.mode": "subscribe",
    "hub.verify_token": TEST_VERIFY_TOKEN,
    "hub.challenge": "1158201444",
}


# ---- decision function ------------------------------------------------------------------


def test_function_correct_token():
    assert evaluate_handshake("subscribe", "tok", "123", "tok") is HandshakeOutcome.OK


def test_function_wrong_token():
    assert evaluate_handshake("subscribe", "bad", "123", "tok") is HandshakeOutcome.FORBIDDEN


def test_function_missing_token():
    assert evaluate_handshake("subscribe", None, "123", "tok") is HandshakeOutcome.FORBIDDEN


def test_function_missing_mode_and_wrong_mode():
    assert evaluate_handshake(None, "tok", "123", "tok") is HandshakeOutcome.FORBIDDEN
    assert evaluate_handshake("unsubscribe", "tok", "123", "tok") is HandshakeOutcome.FORBIDDEN


def test_function_missing_challenge():
    assert evaluate_handshake("subscribe", "tok", None, "tok") is HandshakeOutcome.BAD_REQUEST
    assert evaluate_handshake("subscribe", "tok", "", "tok") is HandshakeOutcome.BAD_REQUEST


def test_function_oversized_or_unprintable_challenge():
    assert evaluate_handshake("subscribe", "tok", "9" * 257, "tok") is HandshakeOutcome.BAD_REQUEST
    assert evaluate_handshake("subscribe", "tok", "12\n3", "tok") is HandshakeOutcome.BAD_REQUEST


def test_function_missing_configuration_never_verifies():
    # The Ava bug: None == None passed the check. Here it must not.
    assert evaluate_handshake("subscribe", None, "123", None) is HandshakeOutcome.FORBIDDEN
    assert evaluate_handshake("subscribe", "", "123", "") is HandshakeOutcome.FORBIDDEN
    assert evaluate_handshake("subscribe", "anything", "123", None) is HandshakeOutcome.FORBIDDEN


# ---- HTTP endpoint ----------------------------------------------------------------------


def test_http_correct_token_echoes_challenge_as_plain_text(client):
    response = client.get(WEBHOOK_PATH, params=OK_PARAMS)
    assert response.status_code == 200
    assert response.text == "1158201444"
    assert response.headers["content-type"].startswith("text/plain")


def test_http_wrong_token_rejected(client):
    response = client.get(WEBHOOK_PATH, params={**OK_PARAMS, "hub.verify_token": "nope"})
    assert response.status_code == 403
    assert "1158201444" not in response.text


def test_http_missing_token_rejected(client):
    params = {k: v for k, v in OK_PARAMS.items() if k != "hub.verify_token"}
    assert client.get(WEBHOOK_PATH, params=params).status_code == 403


def test_http_missing_mode_rejected(client):
    params = {k: v for k, v in OK_PARAMS.items() if k != "hub.mode"}
    assert client.get(WEBHOOK_PATH, params=params).status_code == 403


def test_http_missing_challenge_is_bad_request(client):
    params = {k: v for k, v in OK_PARAMS.items() if k != "hub.challenge"}
    assert client.get(WEBHOOK_PATH, params=params).status_code == 400


def test_http_no_parameters_at_all(client):
    assert client.get(WEBHOOK_PATH).status_code == 403


def test_http_missing_configuration_rejects_everything():
    unconfigured = TestClient(
        create_app(Settings(verify_token=None, app_secret=TEST_APP_SECRET)),
        raise_server_exceptions=False,
    )
    # A request with the "right" token cannot succeed because no token is configured,
    # and a request with no token must not succeed either (None == None).
    assert unconfigured.get(WEBHOOK_PATH, params=OK_PARAMS).status_code == 403
    no_token = {k: v for k, v in OK_PARAMS.items() if k != "hub.verify_token"}
    assert unconfigured.get(WEBHOOK_PATH, params=no_token).status_code == 403
    assert (
        unconfigured.get(WEBHOOK_PATH, params={**OK_PARAMS, "hub.verify_token": ""}).status_code
        == 403
    )


def test_http_empty_environment_means_not_configured():
    settings = Settings.from_env({})
    assert settings.verify_token is None and settings.app_secret is None
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    assert client.get(WEBHOOK_PATH, params=OK_PARAMS).status_code == 403


def test_http_error_responses_do_not_contain_the_token(client):
    response = client.get(WEBHOOK_PATH, params={**OK_PARAMS, "hub.verify_token": "nope"})
    assert TEST_VERIFY_TOKEN not in response.text
