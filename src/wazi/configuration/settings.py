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

DEFAULT_MAX_BODY_BYTES = 1_048_576  # 1 MiB. Real WhatsApp payloads are a few KiB.
DEFAULT_IDEMPOTENCY_MAX_ENTRIES = 50_000
# Meta documents retries for up to 7 days (WhatsApp webhooks page); keep ids at least that long.
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600


def _clean(value: str | None) -> str | None:
    """Treat unset, empty and whitespace-only values as 'not configured'."""
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    verify_token: str | None = field(default=None, repr=False)
    app_secret: str | None = field(default=None, repr=False)
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    idempotency_max_entries: int = DEFAULT_IDEMPOTENCY_MAX_ENTRIES
    idempotency_ttl_seconds: float = DEFAULT_IDEMPOTENCY_TTL_SECONDS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        return cls(
            verify_token=_clean(env.get(ENV_VERIFY_TOKEN)),
            app_secret=_clean(env.get(ENV_APP_SECRET)),
        )

    @property
    def verification_configured(self) -> bool:
        return self.verify_token is not None

    @property
    def signature_configured(self) -> bool:
        return self.app_secret is not None
