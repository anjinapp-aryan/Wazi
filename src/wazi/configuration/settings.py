"""Application settings, read from environment variables.

Design rules:
* Secrets are never given defaults. A missing secret means "not configured", and every
  security check treats "not configured" as "reject" (fail closed).
* Secret fields are excluded from ``repr`` so an accidental ``print(settings)`` or log line
  cannot leak them.
* Only the standard library is used (no settings framework), to keep the dependency list short.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

ENV_VERIFY_TOKEN = "WAZI_WHATSAPP_VERIFY_TOKEN"
ENV_APP_SECRET = "WAZI_WHATSAPP_APP_SECRET"
ENV_ACCESS_TOKEN = "WAZI_WHATSAPP_ACCESS_TOKEN"
ENV_PHONE_NUMBER_ID = "WAZI_WHATSAPP_PHONE_NUMBER_ID"
ENV_GRAPH_API_VERSION = "WAZI_GRAPH_API_VERSION"
ENV_IDEMPOTENCY_DB = "WAZI_IDEMPOTENCY_DB"

DEFAULT_MAX_BODY_BYTES = 1_048_576  # 1 MiB. Real WhatsApp payloads are a few KiB.
DEFAULT_IDEMPOTENCY_MAX_ENTRIES = 50_000
# Meta documents retries for up to 7 days (WhatsApp webhooks page); keep ids at least that long.
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600
# Latest version on Meta's changelog page when this was written (2026-10-29); override by env.
DEFAULT_GRAPH_API_VERSION = "v26.0"


def _clean(value: str | None) -> str | None:
    """Treat unset, empty and whitespace-only values as 'not configured'."""
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    # Inbound security (Phase 4)
    verify_token: str | None = field(default=None, repr=False)
    app_secret: str | None = field(default=None, repr=False)
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    idempotency_max_entries: int = DEFAULT_IDEMPOTENCY_MAX_ENTRIES
    idempotency_ttl_seconds: float = DEFAULT_IDEMPOTENCY_TTL_SECONDS
    # Outbound (Phase 5). Both must be set to send for real; otherwise replies are dry-run.
    access_token: str | None = field(default=None, repr=False)
    phone_number_id: str | None = None
    graph_api_version: str = DEFAULT_GRAPH_API_VERSION
    # Persistent idempotency: a SQLite file path. None keeps the in-memory store.
    idempotency_db_path: str | None = None
    # Background processing
    worker_threads: int = 4
    max_pending: int = 100
    outbound_max_attempts: int = 3

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        return cls(
            verify_token=_clean(env.get(ENV_VERIFY_TOKEN)),
            app_secret=_clean(env.get(ENV_APP_SECRET)),
            access_token=_clean(env.get(ENV_ACCESS_TOKEN)),
            phone_number_id=_clean(env.get(ENV_PHONE_NUMBER_ID)),
            graph_api_version=_clean(env.get(ENV_GRAPH_API_VERSION)) or DEFAULT_GRAPH_API_VERSION,
            idempotency_db_path=_clean(env.get(ENV_IDEMPOTENCY_DB)),
        )

    @property
    def verification_configured(self) -> bool:
        return self.verify_token is not None

    @property
    def signature_configured(self) -> bool:
        return self.app_secret is not None

    @property
    def outbound_configured(self) -> bool:
        return self.access_token is not None and self.phone_number_id is not None
