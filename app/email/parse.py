"""Parse AgentMail webhook payloads into a normalized inbound email."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_FROM_RE = re.compile(r"^(?P<name>.*?)\s*<(?P<email>[^>]+)>\s*$")
_CUSTOMER_ID_RE = re.compile(
    r"\b(?:customer[_ ]?id|cust(?:omer)?)\s*[:=]?\s*([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IncomingEmail:
    message_id: str
    inbox_id: str
    thread_id: str | None
    from_email: str
    from_name: str
    subject: str
    body: str
    to: list[str]
    event_type: str


def parse_from_field(from_field: str) -> tuple[str, str]:
    """Return (email, display_name) from a From header value."""
    raw = (from_field or "").strip()
    if not raw:
        return "", ""
    m = _FROM_RE.match(raw)
    if m:
        email = m.group("email").strip()
        name = m.group("name").strip().strip('"') or email.split("@")[0]
        return email, name
    if "@" in raw:
        return raw, raw.split("@")[0]
    return raw, raw


def extract_customer_id(subject: str, body: str, from_email: str) -> str | None:
    """Best-effort customer id from ticket text; fall back to email local-part."""
    blob = f"{subject}\n{body}"
    m = _CUSTOMER_ID_RE.search(blob)
    if m:
        return m.group(1)
    # Common demo ids like CUST-1001 without a label.
    m2 = re.search(r"\b(CUST-\d+)\b", blob, re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    if from_email and "@" in from_email:
        return from_email
    return None


def _message_body(message: dict[str, Any]) -> str:
    text = message.get("text") or message.get("body") or ""
    if isinstance(text, str) and text.strip():
        return text.strip()
    html = message.get("html") or ""
    if isinstance(html, str) and html.strip():
        # Light strip for triage; not a full HTML→text converter.
        cleaned = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", cleaned).strip()
    preview = message.get("preview") or message.get("snippet") or ""
    return str(preview).strip()


def parse_agentmail_payload(payload: dict[str, Any]) -> IncomingEmail | None:
    """Normalize a webhook JSON body. Returns None for ignore/invalid events."""
    event_type = payload.get("event_type") or payload.get("type") or ""
    if event_type and event_type not in ("message.received",):
        return None

    message = payload.get("message") or {}
    if not isinstance(message, dict):
        return None

    message_id = message.get("message_id") or message.get("id") or ""
    inbox_id = message.get("inbox_id") or payload.get("inbox_id") or ""
    from_field = message.get("from_") or message.get("from") or ""
    if not message_id or not inbox_id or not from_field:
        return None

    from_email, from_name = parse_from_field(str(from_field))
    if not from_email:
        return None

    to_raw = message.get("to") or []
    if isinstance(to_raw, str):
        to_list = [to_raw]
    elif isinstance(to_raw, list):
        to_list = [str(x) for x in to_raw]
    else:
        to_list = []

    subject = str(message.get("subject") or "(no subject)").strip()
    body = _message_body(message)
    thread_id = message.get("thread_id") or message.get("threadId")

    return IncomingEmail(
        message_id=str(message_id),
        inbox_id=str(inbox_id),
        thread_id=str(thread_id) if thread_id else None,
        from_email=from_email,
        from_name=from_name,
        subject=subject,
        body=body or subject,
        to=to_list,
        event_type=str(event_type or "message.received"),
    )
