"""Helpers so log lines never carry secrets or personal data.

Policy for the webhook (enforced by tests/test_security_invariants.py):
  * never log: app secret, verify token, signature header, raw body, message text, phone numbers;
  * log counts and outcomes, and at most a short one-way fingerprint of an identifier.
"""

from __future__ import annotations

import hashlib


def fingerprint(value: str) -> str:
    """Short one-way tag (8 hex chars) that lets two log lines be correlated without exposing
    the identifier. Not a security control on its own: ids with little entropy (phone numbers)
    can be brute-forced from a fingerprint, so prefer logging fingerprints of message ids only.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
