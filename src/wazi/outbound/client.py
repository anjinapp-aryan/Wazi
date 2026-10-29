"""WhatsApp Cloud API sender: one text message per ``send`` call, one HTTP attempt per call.

Request (official Meta documentation, fetched 2026-10-29):

    POST https://graph.facebook.com/<version>/<phone_number_id>/messages
    Authorization: Bearer <access token>        Content-Type: application/json
    {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "<wa_id>",
     "type": "text", "text": {"preview_url": false, "body": "<up to 4096 characters>"}}

A 2xx response only means Meta *accepted* the request; delivery status arrives later through
the webhook. Error responses carry ``{"error": {"code": <int>, "message": ..., ...}}``. Meta's
pages do not state HTTP statuses for Cloud API error codes, so classification uses both the
HTTP status and the documented ``code`` (see ``_RETRYABLE_CODES``).

Free-form text can only be sent inside the 24-hour customer-service window; outside it Meta
answers with code 131047. A reply to a message that just arrived is always inside the window.

Security rules (tested):
* the access token lives only in the Authorization header; it is not in ``repr``, errors or logs;
* ``SendError`` carries status/code only; no response body, recipient or message text;
* base URL must be https; redirects are not followed; the phone-number id, API version and
  recipient are validated before they are placed in a URL or body;
* every call has a timeout.

Patterns adapted (no code copied) from AleBrito's whatsapp-ai-agent (MIT): a transport that
can be swapped for a dry-run one so a checkout never calls Meta with missing credentials, and
a synchronous httpx client used from a worker thread. Differences: classified errors instead
of ``None``, no response text in logs.
"""

from __future__ import annotations

import collections
import logging
import re
from typing import Any

import httpx

from wazi.messaging import OutboundReply
from wazi.ports import SendError, SendResult

logger = logging.getLogger("wazi.outbound")

DEFAULT_BASE_URL = "https://graph.facebook.com"
MAX_TEXT_CHARS = 4096  # documented maximum body length

_VERSION_RE = re.compile(r"^v\d{1,3}\.\d{1,2}$")
_RECIPIENT_RE = re.compile(r"^\d{5,20}$")

# Meta error codes where waiting and trying again can help (Meta's error-codes page):
# 2 temporary downtime, 4 app rate limit, 80007 account rate limit, 130429 throughput,
# 131000 unknown error ("try again"), 131016 / 133004 service temporarily unavailable,
# 131056 pair rate limit ("wait and retry").
_RETRYABLE_CODES = frozenset({2, 4, 80007, 130429, 131000, 131016, 131056, 133004})
_MAX_RETRY_AFTER = 60.0


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, min(float(raw), _MAX_RETRY_AFTER))
    except ValueError:
        return None


def _error_code(response: httpx.Response) -> int | None:
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


class WhatsAppCloudClient:
    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        *,
        api_version: str = "v26.0",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not access_token or not access_token.strip():
            raise ValueError("access_token is required")
        if not phone_number_id.isdigit():
            raise ValueError("phone_number_id must be digits only")
        if not _VERSION_RE.match(api_version):
            raise ValueError("api_version must look like 'v26.0'")
        if not base_url.startswith("https://"):
            raise ValueError("base_url must use https")
        self._url = f"{base_url.rstrip('/')}/{api_version}/{phone_number_id}/messages"
        self._http = httpx.Client(
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={
                "Authorization": f"Bearer {access_token.strip()}",
                "Content-Type": "application/json",
            },
        )

    def __repr__(self) -> str:  # never show the token
        return "WhatsAppCloudClient(configured=True)"

    def close(self) -> None:
        self._http.close()

    def send(self, reply: OutboundReply) -> SendResult:
        if not _RECIPIENT_RE.match(reply.recipient_id):
            raise SendError("invalid recipient id", retryable=False)
        text = reply.text[:MAX_TEXT_CHARS]
        if not text.strip():
            raise SendError("empty message body", retryable=False)

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": reply.recipient_id,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
        try:
            response = self._http.post(self._url, json=payload)
        except httpx.TimeoutException as exc:
            raise SendError("timeout while sending", retryable=True) from exc
        except httpx.HTTPError as exc:
            # Connection problems and the like. Do not include str(exc): it can contain the URL.
            raise SendError(f"transport error ({type(exc).__name__})", retryable=True) from exc

        status = response.status_code
        if 200 <= status < 300:
            return SendResult(message_id=self._message_id(response))

        code = _error_code(response)
        retryable = status == 429 or status >= 500 or code in _RETRYABLE_CODES
        logger.warning("send rejected http=%s code=%s retryable=%s", status, code, retryable)
        raise SendError(
            f"send rejected (http={status}, code={code})",
            retryable=retryable,
            status_code=status,
            error_code=code,
            retry_after=_retry_after_seconds(response),
        )

    @staticmethod
    def _message_id(response: httpx.Response) -> str | None:
        try:
            body = response.json()
            first = body["messages"][0]["id"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        return first if isinstance(first, str) else None


class DryRunSender:
    """Used when no WhatsApp credentials are configured: nothing leaves the machine.

    Keeps the most recent replies in memory so a developer or a test can inspect them.
    Logs only a count, never the text or the recipient.
    """

    def __init__(self, keep_last: int = 100) -> None:
        self.sent: collections.deque[OutboundReply] = collections.deque(maxlen=keep_last)

    def send(self, reply: OutboundReply) -> SendResult:
        self.sent.append(reply)
        logger.info("dry-run: reply not sent (no WhatsApp credentials configured)")
        return SendResult(message_id="dry-run")

    def close(self) -> None:
        return None
