"""Tests for Phase 4 metrics / observability endpoints."""

from __future__ import annotations


def test_metrics_summary_empty(client):
    resp = client.get("/metrics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticket_count"] == 0
    assert data["avg_cost_usd"] == 0.0


def test_metrics_summary_after_tickets(client):
    client.post(
        "/tickets",
        json={
            "subject": "Charged twice for my subscription",
            "body": "I was charged twice. customer_id: CUST-1001",
            "customer_id": "CUST-1001",
        },
    )
    client.post(
        "/tickets",
        json={"subject": "Can't log in", "body": "I forgot my password, how do I reset it?"},
    )

    summary = client.get("/metrics/summary").json()
    assert summary["ticket_count"] == 2
    assert summary["by_action"]
    assert "cheap" in summary["by_tier"] or "strong" in summary["by_tier"]

    recent = client.get("/metrics/recent").json()
    assert len(recent) == 2
    assert recent[0]["model_tier"] in ("cheap", "strong")


def test_health_includes_routing(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert "model_routing" in data
