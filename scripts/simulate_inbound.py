"""Developer tool: POST a correctly SIGNED Meta-style inbound text message to a Wazi webhook.

Why it exists: it lets you test the whole receive -> reply path, and the duplicate/restart
behaviour, BEFORE a public tunnel or Meta's own deliveries are involved. It is NOT Meta: the
payload is built here and signed with YOUR app secret, so it proves Wazi's behaviour, not
Meta's. Real inbound messages from a real phone are the only proof of Meta's behaviour.

Standard library only. Reads the app secret from WAZI_WHATSAPP_APP_SECRET (never from argv, so
it does not end up in shell history). Prints only the HTTP status and the JSON counts.

Examples (the server must already be running):
    python scripts/simulate_inbound.py --sender 15550001111 --text "Hello Wazi"
    # replay the SAME message id => must be reported as a duplicate, no second reply:
    python scripts/simulate_inbound.py --sender 15550001111 --text "Hello Wazi" --message-id wamid.X
    python scripts/simulate_inbound.py --sender 15550001111 --text "Hello Wazi" --message-id wamid.X

With --sender set to your real allowed test number and real outbound credentials configured
on the server, this triggers one REAL outbound WhatsApp message.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def build_payload(sender: str, text: str, message_id: str, phone_number_id: str) -> bytes:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "100000000000002",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550002222",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Simulated"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": message_id,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8099/webhook")
    parser.add_argument("--sender", required=True, help="digits only, e.g. 15550001111")
    parser.add_argument("--text", default="Hello Wazi")
    parser.add_argument("--message-id", default=None, help="reuse an id to test duplicates")
    parser.add_argument("--phone-number-id", default="100000000000001")
    parser.add_argument("--tamper", action="store_true", help="change the body after signing")
    parser.add_argument("--no-signature", action="store_true")
    parser.add_argument("--allow-remote", action="store_true", help="allow a non-loopback URL")
    args = parser.parse_args()

    host = urllib.parse.urlparse(args.url).hostname
    if host not in LOOPBACK and not args.allow_remote:
        print("refusing a non-loopback URL without --allow-remote", file=sys.stderr)
        return 2
    if not args.sender.isdigit():
        print("--sender must be digits only", file=sys.stderr)
        return 2
    secret = os.environ.get("WAZI_WHATSAPP_APP_SECRET", "").strip()
    if not secret and not args.no_signature:
        print("set WAZI_WHATSAPP_APP_SECRET (same value as the server)", file=sys.stderr)
        return 2

    message_id = args.message_id or f"wamid.SIM{uuid.uuid4().hex[:20].upper()}"
    body = build_payload(args.sender, args.text, message_id, args.phone_number_id)
    headers = {"Content-Type": "application/json"}
    if not args.no_signature:
        headers["X-Hub-Signature-256"] = sign(body, secret)
    if args.tamper:
        body = body.replace(args.text.encode(), (args.text + "!").encode(), 1)

    request = urllib.request.Request(args.url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            status, text = response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        status, text = err.code, err.read().decode()
    print(f"message_id={message_id} -> HTTP {status} {text}")
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
