"""Outbound WhatsApp client, driven by httpx.MockTransport (no network)."""

from __future__ import annotations

import contextlib
import json
import logging

import httpx
import pytest

from tests.fakes import FAKE_ACCESS_TOKEN, FAKE_PHONE_NUMBER_ID
from wazi.messaging import OutboundReply
from wazi.outbound import DryRunSender, WhatsAppCloudClient
from wazi.ports import ReplySender, SendError

RECIPIENT = "15550001111"
OK_BODY = {
    "messaging_product": "whatsapp",
    "contacts": [{"input": RECIPIENT, "wa_id": RECIPIENT}],
    "messages": [{"id": "wamid.FAKESENT001"}],
}


class Recorder:
    def __init__(self, response: httpx.Response | Exception | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.response = response if response is not None else httpx.Response(200, json=OK_BODY)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def make_client(recorder: Recorder, **kwargs) -> WhatsAppCloudClient:
    return WhatsAppCloudClient(
        FAKE_ACCESS_TOKEN,
        FAKE_PHONE_NUMBER_ID,
        transport=httpx.MockTransport(recorder),
        **kwargs,
    )


def reply(text: str = "hello", to: str = RECIPIENT) -> OutboundReply:
    return OutboundReply(recipient_id=to, text=text, in_reply_to="wamid.IN001")


# ---- request shape (official Meta documentation) --------------------------------------------


def test_request_matches_documented_send_text_call():
    recorder = Recorder()
    result = make_client(recorder).send(reply("Hello there"))
    assert result.message_id == "wamid.FAKESENT001"
    (request,) = recorder.requests
    assert request.method == "POST"
    assert str(request.url) == f"https://graph.facebook.com/v26.0/{FAKE_PHONE_NUMBER_ID}/messages"
    assert request.headers["authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": RECIPIENT,
        "type": "text",
        "text": {"preview_url": False, "body": "Hello there"},
    }


def test_api_version_is_configurable():
    recorder = Recorder()
    make_client(recorder, api_version="v25.0").send(reply())
    assert "/v25.0/" in str(recorder.requests[0].url)


def test_long_text_is_truncated_to_the_documented_maximum():
    recorder = Recorder()
    make_client(recorder).send(reply("x" * 5000))
    assert len(json.loads(recorder.requests[0].content)["text"]["body"]) == 4096


def test_success_without_a_message_id_in_the_body_is_still_success():
    recorder = Recorder(httpx.Response(200, json={"unexpected": True}))
    assert make_client(recorder).send(reply()).message_id is None


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_empty_body_is_rejected_without_a_request(text):
    recorder = Recorder()
    with pytest.raises(SendError) as info:
        make_client(recorder).send(reply(text))
    assert info.value.retryable is False
    assert recorder.requests == []


@pytest.mark.parametrize(
    "recipient", ["", "abc", "../etc", "1555 000 1111", "+15550001111", "1" * 21]
)
def test_invalid_recipient_is_rejected_without_a_request(recipient):
    recorder = Recorder()
    with pytest.raises(SendError) as info:
        make_client(recorder).send(reply(to=recipient))
    assert info.value.retryable is False
    assert recorder.requests == []


# ---- error classification -------------------------------------------------------------------


def error_response(status: int, code: int | None, headers: dict | None = None) -> httpx.Response:
    body = {"error": {"message": "secret-looking-detail", "type": "OAuthException", "code": code}}
    return httpx.Response(status, json=body, headers=headers or {})


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, 100, False),  # invalid parameter
        (401, 190, False),  # token expired
        (400, 131047, False),  # outside the 24-hour window
        (400, 131026, False),  # undeliverable
        (403, 131030, False),
        (400, 130429, True),  # throughput rate limit
        (400, 131056, True),  # pair rate limit
        (400, 80007, True),  # account rate limit
        (400, 131000, True),  # unknown error, "try again"
        (429, None, True),
        (500, None, True),
        (502, None, True),
        (503, 2, True),
    ],
)
def test_error_classification(status, code, retryable):
    with pytest.raises(SendError) as info:
        make_client(Recorder(error_response(status, code))).send(reply())
    assert info.value.retryable is retryable
    assert info.value.status_code == status
    assert info.value.error_code == code


def test_non_json_error_body_is_handled():
    with pytest.raises(SendError) as info:
        make_client(Recorder(httpx.Response(502, text="<html>bad gateway</html>"))).send(reply())
    assert info.value.retryable is True
    assert info.value.error_code is None


def test_retry_after_header_is_parsed_and_capped():
    cases = {"7": 7.0, "99999": 60.0, "soon": None}
    for header, expected in cases.items():
        recorder = Recorder(error_response(429, 130429, {"retry-after": header}))
        with pytest.raises(SendError) as info:
            make_client(recorder).send(reply())
        assert info.value.retry_after == expected


def test_timeout_and_connection_errors_are_retryable():
    for failure in (httpx.ReadTimeout("slow"), httpx.ConnectError("refused")):
        with pytest.raises(SendError) as info:
            make_client(Recorder(failure)).send(reply())
        assert info.value.retryable is True


def test_redirects_are_not_followed():
    recorder = Recorder(httpx.Response(302, headers={"location": "https://evil.example/steal"}))
    with pytest.raises(SendError):
        make_client(recorder).send(reply())
    assert len(recorder.requests) == 1  # the Authorization header never went anywhere else


# ---- secrets never leak ---------------------------------------------------------------------


def test_errors_and_repr_never_contain_token_recipient_text_or_response_body():
    failures = [
        error_response(401, 190),
        error_response(500, None),
        httpx.ConnectError(f"cannot reach https://graph.facebook.com/{FAKE_ACCESS_TOKEN}"),
        httpx.ReadTimeout("slow"),
    ]
    secrets = [FAKE_ACCESS_TOKEN, RECIPIENT, "very private reply", "secret-looking-detail"]
    for failure in failures:
        client = make_client(Recorder(failure))
        with pytest.raises(SendError) as info:
            client.send(reply("very private reply"))
        shown = f"{info.value} {info.value!r} {client!r}"
        for secret in secrets:
            assert secret not in shown


def test_outbound_logs_never_contain_token_recipient_or_text(caplog):
    with caplog.at_level(logging.DEBUG):
        for response in (httpx.Response(200, json=OK_BODY), error_response(429, 130429)):
            with contextlib.suppress(SendError):
                make_client(Recorder(response)).send(reply("very private reply"))
    logged = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("wazi"))
    assert logged, "expected the client to log the rejected send"
    for secret in (FAKE_ACCESS_TOKEN, RECIPIENT, "very private reply", "secret-looking-detail"):
        assert secret not in logged


# ---- construction and dry-run ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"access_token": ""},
        {"access_token": "   "},
        {"phone_number_id": "abc"},
        {"phone_number_id": "123/../456"},
        {"phone_number_id": ""},
        {"api_version": "26.0"},
        {"api_version": "v26"},
        {"api_version": "v26.0/../x"},
        {"base_url": "http://graph.facebook.com"},
    ],
)
def test_invalid_configuration_is_rejected(kwargs):
    args = {"access_token": FAKE_ACCESS_TOKEN, "phone_number_id": FAKE_PHONE_NUMBER_ID, **kwargs}
    with pytest.raises(ValueError):
        WhatsAppCloudClient(**args)


def test_both_senders_satisfy_the_sender_protocol():
    assert isinstance(make_client(Recorder()), ReplySender)
    assert isinstance(DryRunSender(), ReplySender)


def test_dry_run_sender_keeps_replies_locally_and_logs_no_content(caplog):
    sender = DryRunSender(keep_last=2)
    with caplog.at_level(logging.DEBUG):
        for i in range(3):
            assert sender.send(reply(f"private {i}")).message_id == "dry-run"
    assert [r.text for r in sender.sent] == ["private 1", "private 2"]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "private" not in logged and RECIPIENT not in logged
