"""Process inbound AgentMail events through the existing triage pipeline."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ticket
from app.email.client import agentmail_configured, send_reply
from app.email.parse import IncomingEmail, extract_customer_id, parse_agentmail_payload
from app.service import triage_ticket

logger = logging.getLogger(__name__)


def _is_from_our_inbox(email: IncomingEmail) -> bool:
    """Skip our own outbound traffic if it ever shows up as received."""
    configured = (settings.agentmail_inbox_id or "").strip().lower()
    if configured and email.from_email.lower() == configured.lower():
        return True
    username = settings.agentmail_inbox_username.strip().lower()
    if username and email.from_email.lower().startswith(f"{username}@"):
        return True
    return False


def _already_processed(session: Session, message_id: str) -> Ticket | None:
    return session.scalar(
        select(Ticket).where(Ticket.external_id == message_id).limit(1)
    )


def process_inbound_email(
    session: Session,
    email: IncomingEmail,
    *,
    reply_fn: Any | None = None,
) -> dict[str, Any]:
    """Triage an inbound email; auto-reply only when action is auto_respond.

    ``reply_fn`` is injectable for tests: ``(inbox_id, message_id, to, text) -> None``.
    """
    if _is_from_our_inbox(email):
        logger.info("Ignoring email from our own inbox: %s", email.from_email)
        return {"status": "ignored", "reason": "own_inbox"}

    existing = _already_processed(session, email.message_id)
    if existing is not None:
        logger.info("Duplicate message_id=%s ticket_id=%s", email.message_id, existing.id)
        return {
            "status": "duplicate",
            "ticket_id": existing.id,
            "action": existing.resolution.action if existing.resolution else None,
        }

    customer_id = extract_customer_id(email.subject, email.body, email.from_email)
    ticket = triage_ticket(
        session,
        subject=email.subject,
        body=email.body,
        customer_id=customer_id,
        external_id=email.message_id,
        channel="email",
    )
    resolution = ticket.resolution
    action = resolution.action if resolution else None
    draft = (resolution.draft_response if resolution else None) or ""

    replied = False
    should_reply = (
        settings.agentmail_auto_reply
        and action == "auto_respond"
        and bool(draft.strip())
    )
    if should_reply and (reply_fn is not None or agentmail_configured()):
        try:
            if reply_fn is not None:
                reply_fn(
                    inbox_id=email.inbox_id,
                    message_id=email.message_id,
                    to_email=email.from_email,
                    text=draft,
                )
            else:
                send_reply(
                    inbox_id=email.inbox_id,
                    message_id=email.message_id,
                    to_email=email.from_email,
                    text=draft,
                )
            replied = True
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send AgentMail auto-reply")

    return {
        "status": "triaged",
        "ticket_id": ticket.id,
        "category": resolution.category if resolution else None,
        "action": action,
        "replied": replied,
        "from_email": email.from_email,
    }


def handle_agentmail_event(
    session: Session,
    payload: dict[str, Any],
    *,
    reply_fn: Any | None = None,
) -> dict[str, Any]:
    email = parse_agentmail_payload(payload)
    if email is None:
        return {"status": "ignored", "reason": "unhandled_or_invalid_event"}
    return process_inbound_email(session, email, reply_fn=reply_fn)
