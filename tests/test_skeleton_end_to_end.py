"""The walking skeleton end to end, fully offline.

signed Meta webhook -> verify -> normalise -> claim -> background worker -> fake responder
-> WhatsApp Cloud API client (httpx MockTransport standing in for graph.facebook.com)

Nothing here touches the network (the autouse guard in conftest.py enforces it).
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.fakes import FAKE_ACCESS_TOKEN, FAKE_PHONE_NUMBER_ID, FakeSender
from tests.helpers import (
    TEST_APP_SECRET,
    TEST_VERIFY_TOKEN,
    fixture_bytes,
    signed_headers,
)
from wazi.bootstrap import build_app
from wazi.configuration import Settings
from wazi.idempotency import InMemoryIdempotencyStore, SqliteIdempotencyStore
from wazi.outbound import DryRunSender, WhatsAppCloudClient
from wazi.responder import EchoResponder
from wazi.webhook import WEBHOOK_PATH, create_app
from wazi.worker import BackgroundDispatcher, RetryPolicy

MESSAGE_ID = "wamid.FAKETEXT001"


class FakeMeta:
    """Stands in for graph.facebook.com: records requests, answers from a script."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []
        self.responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return httpx.Response(200, json={"messages": [{"id": "wamid.FAKESENT"}]})


def settings_for(tmp_path, **overrides) -> Settings:
    base = {
        "verify_token": TEST_VERIFY_TOKEN,
        "app_secret": TEST_APP_SECRET,
        "access_token": FAKE_ACCESS_TOKEN,
        "phone_number_id": FAKE_PHONE_NUMBER_ID,
        "idempotency_db_path": str(tmp_path / "idempotency.db"),
    }
    return Settings(**{**base, **overrides})


def app_with_fake_meta(settings: Settings, meta: FakeMeta):
    sender = WhatsAppCloudClient(
        FAKE_ACCESS_TOKEN, FAKE_PHONE_NUMBER_ID, transport=httpx.MockTransport(meta)
    )
    return build_app(settings, sender=sender)


def post(client, name: str = "text_message"):
    body = fixture_bytes(name)
    return client.post(WEBHOOK_PATH, content=body, headers=signed_headers(body))


def finish(app) -> None:
    assert app.state.dispatcher.wait_idle(timeout=5), "background work did not finish"


# ---- the full loop --------------------------------------------------------------------------


def test_text_message_produces_exactly_one_documented_reply_request(tmp_path):
    meta = FakeMeta()
    app = app_with_fake_meta(settings_for(tmp_path), meta)
    with TestClient(app) as client:
        response = post(client)
        assert response.status_code == 200 and response.json()["accepted"] == 1
        finish(app)
    (request,) = meta.requests
    assert str(request.url) == f"https://graph.facebook.com/v26.0/{FAKE_PHONE_NUMBER_ID}/messages"
    assert request.headers["authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "15550001111",
        "type": "text",
        "text": {"preview_url": False, "body": "Wazi skeleton echo: Hello Wazi, this is a test."},
    }
    assert app.state.store.state_of(MESSAGE_ID) == "done"


def test_the_webhook_acknowledges_before_the_reply_is_sent(tmp_path):
    sender = FakeSender(block=True)
    app = build_app(settings_for(tmp_path), sender=sender)
    with TestClient(app) as client:
        response = post(client)  # returns although sending is blocked
        assert response.status_code == 200
        assert sender.started.wait(5)
        assert sender.replies == []
        assert app.state.store.state_of(MESSAGE_ID) == "claimed"
        sender.release_event.set()
        finish(app)
    assert len(sender.replies) == 1
    assert app.state.store.state_of(MESSAGE_ID) == "done"


def test_non_text_and_status_events_get_no_reply(tmp_path):
    meta = FakeMeta()
    app = app_with_fake_meta(settings_for(tmp_path), meta)
    with TestClient(app) as client:
        for name in ("image_message", "audio_message", "location_message", "status_update"):
            assert post(client, name).status_code == 200
        finish(app)
    assert meta.requests == []


# ---- duplicates and persistence -------------------------------------------------------------


def test_duplicate_delivery_sends_one_reply(tmp_path):
    meta = FakeMeta()
    app = app_with_fake_meta(settings_for(tmp_path), meta)
    with TestClient(app) as client:
        assert post(client).json()["accepted"] == 1
        second = post(client)
        assert second.status_code == 200 and second.json()["duplicates"] == 1
        finish(app)
    assert len(meta.requests) == 1


def test_a_duplicate_after_a_restart_is_still_a_duplicate(tmp_path):
    settings = settings_for(tmp_path)
    first_meta = FakeMeta()
    first = app_with_fake_meta(settings, first_meta)
    with TestClient(first) as client:
        assert post(client).json()["accepted"] == 1
        finish(first)
    assert len(first_meta.requests) == 1

    # "Restart": a completely new application object, same database file.
    second_meta = FakeMeta()
    second = app_with_fake_meta(settings, second_meta)
    with TestClient(second) as client:
        again = post(client)
        assert again.status_code == 200
        assert again.json()["accepted"] == 0 and again.json()["duplicates"] == 1
        finish(second)
    assert second_meta.requests == []  # Meta's retry did not cause a second reply


def test_the_in_memory_store_forgets_on_restart_which_is_why_sqlite_exists(tmp_path):
    settings = settings_for(tmp_path, idempotency_db_path=None)
    meta_a, meta_b = FakeMeta(), FakeMeta()
    for meta in (meta_a, meta_b):
        app = app_with_fake_meta(settings, meta)
        with TestClient(app) as client:
            post(client)
            finish(app)
    assert len(meta_a.requests) == 1 and len(meta_b.requests) == 1  # replied twice


def test_the_configured_database_is_a_sqlite_store(tmp_path):
    app = build_app(settings_for(tmp_path), sender=DryRunSender())
    assert isinstance(app.state.store, SqliteIdempotencyStore)
    app.state.dispatcher.close()


# ---- failures -------------------------------------------------------------------------------


def test_permanent_send_failure_still_acks_marks_failed_and_is_not_retried(tmp_path):
    error = {"error": {"code": 131047, "message": "re-engagement"}}
    meta = FakeMeta(httpx.Response(400, json=error))
    app = app_with_fake_meta(settings_for(tmp_path), meta)
    with TestClient(app) as client:
        assert post(client).status_code == 200  # the webhook's job was done
        finish(app)
    assert len(meta.requests) == 1
    assert app.state.store.state_of(MESSAGE_ID) == "failed"


def test_transient_send_failures_are_retried_then_succeed(tmp_path):
    rate_limited = httpx.Response(429, json={"error": {"code": 130429}})
    meta = FakeMeta(rate_limited, httpx.Response(500))
    store = SqliteIdempotencyStore(tmp_path / "retry.db")
    sender = WhatsAppCloudClient(
        FAKE_ACCESS_TOKEN, FAKE_PHONE_NUMBER_ID, transport=httpx.MockTransport(meta)
    )
    sleeps: list[float] = []
    dispatcher = BackgroundDispatcher(
        EchoResponder(),
        sender,
        completion=store,
        retry=RetryPolicy(max_attempts=3),
        sleep=sleeps.append,
    )
    app = create_app(
        Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET),
        store=store,
        dispatcher=dispatcher,
    )
    with TestClient(app) as client:
        assert post(client).status_code == 200
        assert dispatcher.wait_idle(5)
    assert len(meta.requests) == 3  # two failures, one success
    assert sleeps == [0.5, 1.0]
    assert store.state_of(MESSAGE_ID) == "done"
    dispatcher.close()


def test_full_queue_partially_accepts_a_batch_then_meta_retry_completes_it(tmp_path):
    sender = FakeSender(block=True)
    store = SqliteIdempotencyStore(tmp_path / "busy.db")
    dispatcher = BackgroundDispatcher(
        EchoResponder(), sender, completion=store, max_pending=2, max_workers=2
    )
    app = create_app(
        Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET),
        store=store,
        dispatcher=dispatcher,
    )
    client = TestClient(app, raise_server_exceptions=False)
    assert post(client, "text_message").status_code == 200  # takes 1 of the 2 slots
    assert sender.started.wait(5)

    # A batch with two texts ("first", "second"): only one more fits in the queue.
    overloaded = post(client, "multi_message")
    assert overloaded.status_code == 500  # 5xx so that Meta retries the delivery
    assert overloaded.json() == {"error": "internal_error"}
    assert store.state_of("wamid.FAKEMULTI1") == "claimed"  # accepted and queued
    assert store.state_of("wamid.FAKEMULTI2") is None  # claim released: a retry is not a duplicate

    sender.release_event.set()
    assert dispatcher.wait_idle(5)

    retry = post(client, "multi_message")  # Meta's retry of the same delivery
    body = retry.json()
    assert retry.status_code == 200
    assert (body["accepted"], body["duplicates"]) == (1, 1)  # no double reply for MULTI1
    assert dispatcher.wait_idle(5)
    assert len(sender.replies) == 3  # TEXT001, MULTI1 once, MULTI2 once
    dispatcher.close()


# ---- configuration and lifecycle ------------------------------------------------------------


def test_without_whatsapp_credentials_outbound_is_dry_run_and_nothing_is_sent():
    settings = Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET)
    assert settings.outbound_configured is False
    app = build_app(settings)
    assert isinstance(app.state.sender, DryRunSender)
    with TestClient(app) as client:
        assert post(client).json()["accepted"] == 1
        finish(app)
    (reply,) = app.state.sender.sent
    assert reply.recipient_id == "15550001111"
    assert reply.text.startswith("Wazi skeleton echo:")


def test_half_configured_outbound_is_treated_as_dry_run():
    only_token = Settings(access_token=FAKE_ACCESS_TOKEN)
    only_id = Settings(phone_number_id=FAKE_PHONE_NUMBER_ID)
    assert not only_token.outbound_configured and not only_id.outbound_configured


def test_shutdown_drains_queued_work_and_closes_the_sender(tmp_path):
    sender = FakeSender()
    app = build_app(settings_for(tmp_path), sender=sender)
    with TestClient(app) as client:
        post(client)
    # leaving the "with" block runs the lifespan shutdown
    assert len(sender.replies) == 1
    assert sender.closed is True


def test_settings_from_environment_includes_the_new_options():
    env = {
        "WAZI_WHATSAPP_ACCESS_TOKEN": "tok",
        "WAZI_WHATSAPP_PHONE_NUMBER_ID": "123",
        "WAZI_GRAPH_API_VERSION": "v25.0",
        "WAZI_IDEMPOTENCY_DB": "x.db",
    }
    settings = Settings.from_env(env)
    assert settings.outbound_configured
    assert (settings.graph_api_version, settings.idempotency_db_path) == ("v25.0", "x.db")
    assert Settings.from_env({}).graph_api_version == "v26.0"
    assert "tok" not in repr(settings)


# ---- security across the whole loop ---------------------------------------------------------


def test_access_token_never_appears_in_responses_or_wazi_logs(tmp_path, caplog):
    meta = FakeMeta(httpx.Response(500), httpx.Response(200, json={"messages": [{"id": "x"}]}))
    app = app_with_fake_meta(settings_for(tmp_path, outbound_max_attempts=2), meta)
    collected = []
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        for name in ("text_message", "text_message", "image_message"):
            r = post(client, name)
            collected.append(r.text + json.dumps(dict(r.headers)))
        finish(app)
    logged = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("wazi"))
    for secret in (FAKE_ACCESS_TOKEN, TEST_APP_SECRET, "Hello Wazi", "15550001111"):
        assert secret not in logged
        assert all(secret not in text for text in collected)


def test_fake_responder_and_store_can_be_swapped_without_touching_the_webhook():
    class Shouter:
        def respond(self, message):
            from wazi.messaging import OutboundReply

            return OutboundReply(message.sender_id, message.text.upper(), message.message_id)

    sender = DryRunSender()
    app = build_app(
        Settings(verify_token=TEST_VERIFY_TOKEN, app_secret=TEST_APP_SECRET),
        sender=sender,
        responder=Shouter(),
        store=InMemoryIdempotencyStore(),
    )
    with TestClient(app) as client:
        post(client)
        finish(app)
    assert sender.sent[0].text == "HELLO WAZI, THIS IS A TEST."


@pytest.mark.parametrize("name", ["text_message"])
def test_unsigned_request_never_reaches_the_worker_or_meta(tmp_path, name):
    meta = FakeMeta()
    app = app_with_fake_meta(settings_for(tmp_path), meta)
    with TestClient(app) as client:
        response = client.post(WEBHOOK_PATH, content=fixture_bytes(name))
        assert response.status_code == 403
        finish(app)
    assert meta.requests == []
