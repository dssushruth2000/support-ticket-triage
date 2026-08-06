"""Thin AgentMail SDK wrappers (create inbox, reply, webhook helpers)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def agentmail_configured() -> bool:
    return bool(settings.agentmail_api_key.strip())


def get_agentmail_client() -> Any:
    if not agentmail_configured():
        raise RuntimeError("AGENTMAIL_API_KEY is not set")
    from agentmail import AgentMail

    return AgentMail(api_key=settings.agentmail_api_key.strip())


def ensure_inbox(
    *,
    username: str | None = None,
    client: Any | None = None,
) -> str:
    """Create or reuse an inbox; return inbox_id (e.g. support-triage@agentmail.to)."""
    from agentmail.inboxes.types.create_inbox_request import CreateInboxRequest

    client = client or get_agentmail_client()
    username = (username or settings.agentmail_inbox_username).strip()
    client_id = f"{username}-inbox"
    try:
        inbox = client.inboxes.create(
            request=CreateInboxRequest(
                username=username,
                client_id=client_id,
                display_name="Support Ticket Triage",
            )
        )
        inbox_id = getattr(inbox, "inbox_id", None) or getattr(inbox, "id", None)
        if not inbox_id:
            raise RuntimeError(f"inbox create returned no id: {inbox!r}")
        return str(inbox_id)
    except Exception as exc:  # noqa: BLE001 — SDK raises varied errors
        msg = str(exc).lower()
        if "already exists" in msg or "conflict" in msg:
            return f"{username}@agentmail.to"
        raise


def register_webhook(
    *,
    url: str,
    inbox_id: str,
    client: Any | None = None,
) -> Any:
    """Register (or reuse) a message.received webhook for the inbox."""
    client = client or get_agentmail_client()
    username = settings.agentmail_inbox_username.strip() or "support-triage"
    return client.webhooks.create(
        url=url,
        event_types=["message.received"],
        inbox_ids=[inbox_id],
        client_id=f"{username}-webhook",
    )


def send_reply(
    *,
    inbox_id: str,
    message_id: str,
    to_email: str,
    text: str,
    client: Any | None = None,
) -> None:
    client = client or get_agentmail_client()
    client.inboxes.messages.reply(
        inbox_id=inbox_id,
        message_id=message_id,
        to=[to_email],
        text=text,
    )
    logger.info("AgentMail reply sent to %s (message_id=%s)", to_email, message_id)


def verify_webhook_signature(payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
    """Verify Svix signature when AGENTMAIL_WEBHOOK_SECRET is set.

    Returns the verified JSON payload as a dict. If no secret is configured,
    parses JSON without verification (local/dev convenience).
    """
    import json

    secret = settings.agentmail_webhook_secret.strip()
    if not secret:
        return json.loads(payload.decode("utf-8"))

    from svix.webhooks import Webhook, WebhookVerificationError

    try:
        wh = Webhook(secret)
        return wh.verify(payload, headers)
    except WebhookVerificationError:
        raise
