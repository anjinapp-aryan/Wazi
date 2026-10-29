"""Composition root: the one place that knows which concrete pieces are plugged together.

Run locally with:
    uvicorn --factory wazi.bootstrap:build_server_app --host 127.0.0.1 --port 8099 --no-access-log

Choices made here, from configuration:
* idempotency store: SQLite file if ``WAZI_IDEMPOTENCY_DB`` is set, else in-memory;
* sender: the real WhatsApp Cloud API client only if BOTH ``WAZI_WHATSAPP_ACCESS_TOKEN`` and
  ``WAZI_WHATSAPP_PHONE_NUMBER_ID`` are set, else a dry-run sender (nothing leaves the machine);
* responder: the fake echo responder (NOT IMPLEMENTED: the real agent).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from wazi.configuration import Settings
from wazi.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    SqliteIdempotencyStore,
)
from wazi.outbound import DryRunSender, WhatsAppCloudClient
from wazi.ports import ReplySender, Responder
from wazi.responder import EchoResponder
from wazi.webhook import create_app
from wazi.worker import BackgroundDispatcher, RetryPolicy

logger = logging.getLogger("wazi.bootstrap")

ENV_LOG_LEVEL = "WAZI_LOG_LEVEL"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Make Wazi's own log lines visible when running as a server. Idempotent.

    Wazi's loggers never contain secrets or personal data (tests enforce it), so INFO is safe to
    print. Deliberately NOT called by ``build_app``: the test-suite captures logs at DEBUG and
    must not have the "wazi" logger level changed under it.
    """
    wazi_logger = logging.getLogger("wazi")
    wazi_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not any(getattr(h, "_wazi", False) for h in wazi_logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        handler._wazi = True  # type: ignore[attr-defined]
        wazi_logger.addHandler(handler)
        wazi_logger.propagate = False  # avoid duplicate lines through the root logger


def build_server_app() -> FastAPI:
    """Entry point for ``uvicorn --factory``: logging configured, then the normal app."""
    configure_logging(os.environ.get(ENV_LOG_LEVEL, "INFO"))
    return build_app()


def build_app(
    settings: Settings | None = None,
    *,
    sender: ReplySender | None = None,
    responder: Responder | None = None,
    store: IdempotencyStore | None = None,
) -> FastAPI:
    """Assemble the application. Every collaborator can be overridden (tests do)."""
    settings = settings if settings is not None else Settings.from_env()

    if store is None:
        if settings.idempotency_db_path:
            store = SqliteIdempotencyStore(
                settings.idempotency_db_path, ttl_seconds=settings.idempotency_ttl_seconds
            )
        else:
            store = InMemoryIdempotencyStore(
                max_entries=settings.idempotency_max_entries,
                ttl_seconds=settings.idempotency_ttl_seconds,
            )
            logger.warning("idempotency store is in-memory: duplicates are forgotten on restart")

    if sender is None:
        if settings.outbound_configured:
            assert settings.access_token and settings.phone_number_id  # for type checkers
            sender = WhatsAppCloudClient(
                settings.access_token,
                settings.phone_number_id,
                api_version=settings.graph_api_version,
            )
        else:
            sender = DryRunSender()
            logger.warning("outbound is DRY-RUN: replies are not sent to WhatsApp")

    dispatcher = BackgroundDispatcher(
        responder if responder is not None else EchoResponder(),
        sender,
        completion=store if hasattr(store, "mark_done") else None,  # type: ignore[arg-type]
        max_workers=settings.worker_threads,
        max_pending=settings.max_pending,
        retry=RetryPolicy(max_attempts=settings.outbound_max_attempts),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        dispatcher.close(wait=True)  # finish queued replies, then release the sender

    app = create_app(settings, store=store, dispatcher=dispatcher, lifespan=lifespan)
    app.state.dispatcher = dispatcher  # lets tests wait for background work
    app.state.sender = sender
    app.state.store = store
    return app
