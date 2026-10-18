"""Security layer: webhook signature and verification-handshake logic.

Pure functions. This package knows nothing about HTTP frameworks, WhatsApp message content,
agents or storage, so every rule in it can be tested with plain bytes and strings.
"""

from wazi.security.handshake import HandshakeOutcome, evaluate_handshake
from wazi.security.signature import SIGNATURE_HEADER, compute_signature, verify_signature

__all__ = [
    "SIGNATURE_HEADER",
    "HandshakeOutcome",
    "compute_signature",
    "evaluate_handshake",
    "verify_signature",
]
