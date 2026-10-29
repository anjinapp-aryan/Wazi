"""Outbound layer: sending replies to WhatsApp users. The only package that imports httpx.

Knows how to talk to Meta's Cloud API (or to pretend, in dry-run mode). Knows nothing about
the webhook, the agent, storage or retries: it makes one attempt and reports success or a
classified ``SendError``.
"""

from wazi.outbound.client import DryRunSender, WhatsAppCloudClient

__all__ = ["DryRunSender", "WhatsAppCloudClient"]
