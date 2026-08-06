"""AgentMail parse + webhook intake tests (no live AgentMail calls)."""

from __future__ import annotations

from app.email.handler import handle_agentmail_event, process_inbound_email
from app.email.parse import (
    extract_customer_id,
    parse_agentmail_payload,
    parse_from_field,
)


def test_parse_from_field_with_name():
    email, name = parse_from_field('Ada Lovelace <ada@example.com>')
    assert email == "ada@example.com"
    assert name == "Ada Lovelace"


def test_parse_from_field_bare():
    email, name = parse_from_field("bob@example.com")
    assert email == "bob@example.com"
    assert name == "bob"


def test_extract_customer_id_labeled():
    assert (
        extract_customer_id("Help", "Please look up customer_id: CUST-1001", "x@y.com")
        == "CUST-1001"
    )


def test_parse_payload_message_received():
    payload = {
        "event_type": "message.received",
        "message": {
            "message_id": "msg_1",
            "inbox_id": "support-triage@agentmail.to",
            "from_": "Cust One <cust@example.com>",
            "subject": "Business hours?",
            "text": "What are your support hours?",
            "to": ["support-triage@agentmail.to"],
        },
    }
    email = parse_agentmail_payload(payload)
    assert email is not None
    assert email.message_id == "msg_1"
    assert email.from_email == "cust@example.com"
    assert email.subject == "Business hours?"


def test_parse_payload_ignores_sent():
    assert (
        parse_agentmail_payload(
            {"event_type": "message.sent", "message": {"message_id": "x"}}
        )
        is None
    )


def test_process_faq_auto_replies(session):
    sent: list[dict] = []

    def fake_reply(**kwargs):
        sent.append(kwargs)

    payload = {
        "event_type": "message.received",
        "message": {
            "message_id": "msg_faq_1",
            "inbox_id": "support-triage@agentmail.to",
            "from_": "user@example.com",
            "subject": "Business hours?",
            "text": "What are your support hours?",
        },
    }
    result = handle_agentmail_event(session, payload, reply_fn=fake_reply)
    assert result["status"] == "triaged"
    assert result["action"] == "auto_respond"
    assert result["replied"] is True
    assert len(sent) == 1
    assert sent[0]["to_email"] == "user@example.com"
    assert "hour" in sent[0]["text"].lower() or sent[0]["text"]


def test_process_billing_does_not_auto_reply(session):
    sent: list[dict] = []

    def fake_reply(**kwargs):
        sent.append(kwargs)

    payload = {
        "event_type": "message.received",
        "message": {
            "message_id": "msg_bill_1",
            "inbox_id": "support-triage@agentmail.to",
            "from_": "user@example.com",
            "subject": "Charged twice",
            "text": "I was billed twice, customer_id: CUST-1001",
        },
    }
    result = handle_agentmail_event(session, payload, reply_fn=fake_reply)
    assert result["status"] == "triaged"
    assert result["action"] == "escalate_to_human"
    assert result["replied"] is False
    assert sent == []


def test_duplicate_message_id_skipped(session):
    sent: list[dict] = []

    def fake_reply(**kwargs):
        sent.append(kwargs)

    payload = {
        "event_type": "message.received",
        "message": {
            "message_id": "msg_dup_1",
            "inbox_id": "support-triage@agentmail.to",
            "from_": "user@example.com",
            "subject": "Business hours?",
            "text": "What are your support hours?",
        },
    }
    first = handle_agentmail_event(session, payload, reply_fn=fake_reply)
    second = handle_agentmail_event(session, payload, reply_fn=fake_reply)
    assert first["status"] == "triaged"
    assert second["status"] == "duplicate"
    assert len(sent) == 1


def test_webhook_endpoint_accepts_payload(client):
    resp = client.post(
        "/webhooks/agentmail",
        json={
            "event_type": "message.received",
            "message": {
                "message_id": "msg_api_1",
                "inbox_id": "support-triage@agentmail.to",
                "from_": "user@example.com",
                "subject": "Business hours?",
                "text": "What are your support hours?",
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Background task should have persisted the ticket.
    tickets = client.get("/tickets").json()
    assert any(t.get("external_id") == "msg_api_1" for t in tickets)


def test_health_reports_agentmail(client):
    data = client.get("/health").json()
    assert "agentmail_configured" in data
    assert data["agentmail_configured"] is False
