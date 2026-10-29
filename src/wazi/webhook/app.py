"""FastAPI application factory for the WhatsApp webhook (local use, no deployment).

Request handling order for POST (each step can stop the request):

    HTTP request
      -> body size limit              413   (read as a stream; never buffers more than the limit)
      -> app secret configured?       503   (server misconfigured; nothing is processed)
      -> RAW BODY + signature gate    403   (header missing, malformed or wrong)
      -> strict UTF-8 + JSON parsing  400
      -> envelope validation          400
      -> normalisation, de-duplication, dispatch of TEXT messages
      -> fast ACK                     200   (also for duplicates, unsupported types, statuses)
      -> unexpected failure           500   (generic body, nothing leaked)

Status-code reasoning (also in docs/PHASE_4_FOUNDATION.md):
  * Meta retries any non-200 response (for up to 7 days according to the WhatsApp webhooks page),
    so 200 is returned for everything that is final: accepted, duplicate, unsupported type,
    status receipts. A 409 for a duplicate would only trigger more retries.
  * 4xx is used only for requests that can never become valid by retrying (bad signature,
    malformed body) and that should not be processed.
  * 5xx is used only when a retry could succeed (dispatch failure, unexpected error).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from wazi.configuration import Settings
from wazi.dispatch import MessageDispatcher, NullDispatcher
from wazi.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from wazi.messaging import MessageType, normalize_payload
from wazi.safe_logging import fingerprint
from wazi.security import SIGNATURE_HEADER, HandshakeOutcome, evaluate_handshake, verify_signature

WEBHOOK_PATH = "/webhook"

logger = logging.getLogger("wazi.webhook")


class _BodyTooLarge(Exception):
    pass


def _error(status_code: int, code: str) -> JSONResponse:
    """Fixed, generic error body. Never includes request data, secrets or exception text."""
    return JSONResponse({"error": code}, status_code=status_code)


async def _read_body_limited(request: Request, max_bytes: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise _BodyTooLarge
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise _BodyTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(
    settings: Settings | None = None,
    *,
    store: IdempotencyStore | None = None,
    dispatcher: MessageDispatcher | None = None,
    lifespan: Any = None,
) -> FastAPI:
    """Build the app. All collaborators can be injected, which keeps tests offline and simple."""
    settings = settings if settings is not None else Settings.from_env()
    store = (
        store
        if store is not None
        else InMemoryIdempotencyStore(
            max_entries=settings.idempotency_max_entries,
            ttl_seconds=settings.idempotency_ttl_seconds,
        )
    )
    dispatcher = dispatcher if dispatcher is not None else NullDispatcher()

    # No interactive docs or OpenAPI schema: a webhook needs no extra public surface.
    app = FastAPI(
        title="Wazi webhook",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.get(WEBHOOK_PATH)
    async def verify(request: Request) -> Response:
        params = request.query_params
        challenge = params.get("hub.challenge")
        outcome = evaluate_handshake(
            mode=params.get("hub.mode"),
            verify_token=params.get("hub.verify_token"),
            challenge=challenge,
            configured_token=settings.verify_token,
        )
        if outcome is HandshakeOutcome.OK:
            logger.info("webhook verification succeeded")
            # text/plain, so the echoed value can never be interpreted as HTML.
            return PlainTextResponse(challenge or "", status_code=200)
        logger.warning("webhook verification rejected (%s)", outcome.value)
        if outcome is HandshakeOutcome.BAD_REQUEST:
            return _error(400, "invalid_request")
        return _error(403, "forbidden")

    @app.post(WEBHOOK_PATH)
    async def receive(request: Request) -> Response:
        try:
            return await _handle_post(request)
        except Exception as exc:  # last resort: never leak details, always a clean 500
            logger.error("unexpected failure while handling webhook (%s)", type(exc).__name__)
            return _error(500, "internal_error")

    async def _handle_post(request: Request) -> Response:
        if not settings.signature_configured:
            logger.error("rejected: app secret is not configured")
            return _error(503, "not_configured")

        try:
            raw_body = await _read_body_limited(request, settings.max_body_bytes)
        except _BodyTooLarge:
            logger.warning("rejected: body too large")
            return _error(413, "payload_too_large")

        # Signature check on the ORIGINAL bytes, before any parsing.
        if not verify_signature(
            raw_body, request.headers.get(SIGNATURE_HEADER), settings.app_secret
        ):
            logger.warning("rejected: missing or invalid signature")
            return _error(403, "forbidden")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
            result = normalize_payload(payload)
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            # json.JSONDecodeError and PayloadError are both ValueError subclasses.
            logger.warning("rejected: malformed payload (%s)", type(exc).__name__)
            return _error(400, "invalid_payload")

        accepted = duplicates = unsupported = failures = 0
        for message in result.messages:
            if message.message_type is not MessageType.TEXT:
                unsupported += 1  # recognised and counted, deliberately not processed in Phase 4
                continue
            if not store.claim(message.message_id):
                duplicates += 1
                continue
            try:
                dispatcher.dispatch(message)
            except Exception as exc:
                store.release(message.message_id)  # let Meta's retry through
                failures += 1
                logger.error(
                    "dispatch failed (%s) id=%s",
                    type(exc).__name__,
                    fingerprint(message.message_id),
                )
                continue
            accepted += 1
            logger.debug("accepted id=%s", fingerprint(message.message_id))

        if failures:
            return _error(500, "internal_error")  # 5xx on purpose: a retry can succeed

        logger.info(
            "webhook accepted accepted=%d duplicates=%d unsupported=%d statuses=%d "
            "invalid=%d ignored_changes=%d",
            accepted,
            duplicates,
            unsupported,
            result.status_events,
            result.invalid_messages,
            result.ignored_changes,
        )
        return JSONResponse(
            {
                "status": "accepted",
                "accepted": accepted,
                "duplicates": duplicates,
                "unsupported": unsupported,
                "statuses": result.status_events,
                "invalid": result.invalid_messages,
            },
            status_code=200,
        )

    return app
