"""Verification of Meta's ``X-Hub-Signature-256`` webhook signature.

What Meta documents (checked 2026-10-29):
  * Graph API webhooks "Validating Payloads": the signature is sent in the ``X-Hub-Signature-256``
    header, "preceded with ``sha256=``", generated with "the payload and your app's App Secret";
  * WhatsApp "Create a webhook endpoint" page: "HMAC-SHA256 hash, calculated using the post body
    payload and your app secret as the secret key".

What the pages still do not state: that the bytes are the **raw** HTTP body (they say "JSON
payload"), and nothing is said about Unicode escaping. Signing the exact received bytes is the
standard construction used by independent open-source implementations (pywa, AleBrito's
whatsapp-ai-agent; both MIT) and is the only construction that cannot be fooled by
re-serialisation. It has not been checked against a live Meta delivery (Phase 6 is the first
chance); it is covered by tests against an independent published HMAC test vector.

Rules enforced here:
  * fail closed: no secret, no header, wrong prefix, wrong length, non-hex, or mismatch => False;
  * constant-time comparison (``hmac.compare_digest``) so timing does not leak the digest;
  * never raise on attacker-controlled input and never log it.
"""

from __future__ import annotations

import hashlib
import hmac
import string

SIGNATURE_HEADER = "X-Hub-Signature-256"
_PREFIX = "sha256="
_DIGEST_HEX_LENGTH = 64  # SHA-256 = 32 bytes = 64 hex characters
_HEX_DIGITS = frozenset(string.hexdigits)


def compute_signature(raw_body: bytes, app_secret: str) -> str:
    """Return the header value Meta would send: ``sha256=<hex>``.

    Used by tests and by any future local simulator. Not used to authenticate requests.
    """
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return _PREFIX + digest


def verify_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str | None,
) -> bool:
    """Return True only if ``signature_header`` is the correct signature of ``raw_body``.

    ``raw_body`` MUST be the original request bytes, before any JSON parsing or
    re-serialisation (whitespace, key order and Unicode escaping would change the bytes).
    """
    if not app_secret:
        return False
    if not isinstance(raw_body, bytes | bytearray):
        return False
    if not isinstance(signature_header, str) or not signature_header.startswith(_PREFIX):
        return False

    provided = signature_header[len(_PREFIX) :]
    if len(provided) != _DIGEST_HEX_LENGTH or not _HEX_DIGITS.issuperset(provided):
        return False

    expected = hmac.new(app_secret.encode("utf-8"), bytes(raw_body), hashlib.sha256).hexdigest()
    # Both values are ASCII hex here, so encoding cannot fail. Compare case-insensitively.
    return hmac.compare_digest(expected.encode("ascii"), provided.lower().encode("ascii"))
