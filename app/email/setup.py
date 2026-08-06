"""One-shot setup: create AgentMail inbox + register webhook URL.

Usage:
  python -m app.email.setup --webhook-url https://xxxx.ngrok-free.app/webhooks/agentmail

Prints inbox id and webhook signing secret; write them into .env.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create AgentMail inbox + webhook")
    parser.add_argument(
        "--webhook-url",
        required=True,
        help="Public HTTPS URL ending in /webhooks/agentmail (ngrok or deployed API)",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Inbox username (default: AGENTMAIL_INBOX_USERNAME / support-triage)",
    )
    args = parser.parse_args(argv)

    from app.config import settings
    from app.email.client import (
        agentmail_configured,
        ensure_inbox,
        get_agentmail_client,
        register_webhook,
    )

    if not agentmail_configured():
        print("ERROR: set AGENTMAIL_API_KEY in .env first", file=sys.stderr)
        return 1

    url = args.webhook_url.strip().rstrip("/")
    if not url.endswith("/webhooks/agentmail"):
        print(
            "WARNING: URL should usually end with /webhooks/agentmail "
            f"(got {url})",
            file=sys.stderr,
        )

    client = get_agentmail_client()
    username = args.username or settings.agentmail_inbox_username
    inbox_id = ensure_inbox(username=username, client=client)
    print(f"Inbox: {inbox_id}")

    try:
        webhook = register_webhook(url=url, inbox_id=inbox_id, client=client)
    except Exception as exc:  # noqa: BLE001
        if "already exists" in str(exc).lower():
            print(f"Webhook already exists for this client_id; update URL in console if needed.")
            print(f"Set AGENTMAIL_INBOX_ID={inbox_id} in .env")
            return 0
        raise

    secret = getattr(webhook, "secret", None) or ""
    webhook_id = getattr(webhook, "webhook_id", None) or getattr(webhook, "id", None)

    print(f"Webhook id: {webhook_id}")
    print(f"Webhook URL: {url}")
    print()
    print("Add these to your .env:")
    print(f"AGENTMAIL_INBOX_ID={inbox_id}")
    if secret:
        print(f"AGENTMAIL_WEBHOOK_SECRET={secret}")
    else:
        print("# Fetch signing secret via AgentMail console / webhooks.get if needed")
    print()
    print(f"Send a test email to: {inbox_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
