"""Decision logic for Meta's GET verification handshake.

Meta (Graph API webhooks "Verification Requests") sends a GET with:
  * ``hub.mode``: always ``subscribe``
  * ``hub.verify_token``: the string configured in the app dashboard
  * ``hub.challenge``: an integer the endpoint must echo back
The endpoint must check the token and respond with the challenge.

Design choices (documented in docs/PHASE_4_FOUNDATION.md):
  * no configured token => nothing can ever verify (fail closed, never ``None == None``);
  * wrong mode, missing token or wrong token all give the same outcome, FORBIDDEN, so the
    response does not tell a caller which part was wrong;
  * only a caller that already knows the token learns that the challenge is missing/invalid.
"""

from __future__ import annotations

import enum
import hmac

MAX_CHALLENGE_LENGTH = 256


class HandshakeOutcome(enum.Enum):
    OK = "ok"
    FORBIDDEN = "forbidden"
    BAD_REQUEST = "bad_request"


def _tokens_match(provided: str, configured: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


def _challenge_is_acceptable(challenge: str | None) -> bool:
    return (
        challenge is not None
        and 0 < len(challenge) <= MAX_CHALLENGE_LENGTH
        and challenge.isprintable()
    )


def evaluate_handshake(
    mode: str | None,
    verify_token: str | None,
    challenge: str | None,
    configured_token: str | None,
) -> HandshakeOutcome:
    if not configured_token:
        return HandshakeOutcome.FORBIDDEN
    if mode != "subscribe":
        return HandshakeOutcome.FORBIDDEN
    if verify_token is None or not _tokens_match(verify_token, configured_token):
        return HandshakeOutcome.FORBIDDEN
    if not _challenge_is_acceptable(challenge):
        return HandshakeOutcome.BAD_REQUEST
    return HandshakeOutcome.OK
