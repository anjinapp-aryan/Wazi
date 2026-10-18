"""Webhook layer: the only package that knows about HTTP (FastAPI).

It wires the other layers together in a fixed order and contains no business logic:
raw body -> signature gate -> JSON parsing -> normalisation -> idempotency -> dispatch -> ACK.
"""

from wazi.webhook.app import WEBHOOK_PATH, create_app

__all__ = ["WEBHOOK_PATH", "create_app"]
