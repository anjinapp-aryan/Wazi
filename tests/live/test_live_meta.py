"""LIVE checks against the real Meta Graph API. NOT RUN BY DEFAULT.

    WAZI_LIVE_META=1 \
    WAZI_WHATSAPP_ACCESS_TOKEN=... WAZI_WHATSAPP_PHONE_NUMBER_ID=... WAZI_LIVE_TEST_RECIPIENT=... \
    .venv/Scripts/python -m pytest -m live_meta tests/live -v

These tests were written in Phase 6 but have NEVER been executed: no Meta credentials were
available. Treat the first run as an experiment, not as a verified test.

* ``test_credentials_and_phone_number_id_are_accepted`` is read-only (no message is sent).
* ``test_real_text_send_to_the_allowed_test_recipient`` SENDS ONE REAL WHATSAPP MESSAGE to
  ``WAZI_LIVE_TEST_RECIPIENT`` (your own number, added as a recipient of the Meta test number).
  Free-form text only succeeds if that user messaged the test number within the last 24 hours
  (customer service window); otherwise Meta answers code 131047 and the test reports it.
  Check Meta's current pricing before running it on a non-test number.

Nothing here prints a token, a phone number or a message body.
"""

from __future__ import annotations

import time

import httpx
import pytest

from tests.live.conftest import require_env
from wazi.configuration.settings import DEFAULT_GRAPH_API_VERSION
from wazi.messaging import OutboundReply
from wazi.outbound import WhatsAppCloudClient
from wazi.ports import SendError

pytestmark = pytest.mark.live_meta


def test_credentials_and_phone_number_id_are_accepted():
    env = require_env("WAZI_WHATSAPP_ACCESS_TOKEN", "WAZI_WHATSAPP_PHONE_NUMBER_ID")
    version = DEFAULT_GRAPH_API_VERSION
    response = httpx.get(
        f"https://graph.facebook.com/{version}/{env['WAZI_WHATSAPP_PHONE_NUMBER_ID']}",
        headers={"Authorization": f"Bearer {env['WAZI_WHATSAPP_ACCESS_TOKEN']}"},
        timeout=15,
        follow_redirects=False,
    )
    # On failure show only the status code: the body may contain account details.
    assert response.status_code == 200, f"Graph API answered HTTP {response.status_code}"
    assert response.json().get("id") == env["WAZI_WHATSAPP_PHONE_NUMBER_ID"]


def test_real_text_send_to_the_allowed_test_recipient():
    env = require_env(
        "WAZI_WHATSAPP_ACCESS_TOKEN", "WAZI_WHATSAPP_PHONE_NUMBER_ID", "WAZI_LIVE_TEST_RECIPIENT"
    )
    client = WhatsAppCloudClient(
        env["WAZI_WHATSAPP_ACCESS_TOKEN"],
        env["WAZI_WHATSAPP_PHONE_NUMBER_ID"],
        api_version=DEFAULT_GRAPH_API_VERSION,
    )
    reply = OutboundReply(
        recipient_id=env["WAZI_LIVE_TEST_RECIPIENT"],
        text=f"Wazi live test {int(time.time())}",
    )
    try:
        result = client.send(reply)
    except SendError as err:
        pytest.fail(
            f"send failed: http={err.status_code} code={err.error_code} retryable={err.retryable}"
        )
    finally:
        client.close()
    assert result.message_id, "Meta accepted the request but returned no message id"
