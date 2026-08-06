"""AgentMail email intake: webhook → triage → optional safe auto-reply."""

from app.email.handler import handle_agentmail_event, process_inbound_email
from app.email.parse import IncomingEmail, parse_agentmail_payload

__all__ = [
    "IncomingEmail",
    "handle_agentmail_event",
    "parse_agentmail_payload",
    "process_inbound_email",
]
