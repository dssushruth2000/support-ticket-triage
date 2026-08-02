"""End-to-end API tests via FastAPI's TestClient."""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_ticket_runs_agent_and_persists(client):
    resp = client.post(
        "/tickets",
        json={
            "subject": "Charged twice for my subscription",
            "body": "I was charged twice. customer_id: CUST-1001",
            "customer_id": "CUST-1001",
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    assert data["id"] > 0
    assert data["status"] == "triaged"
    assert data["resolution"]["category"] == "billing"
    assert data["resolution"]["draft_response"]

    # The full decision trace is persisted and includes tool calls.
    tool_steps = [s for s in data["decision_logs"] if s["kind"] == "tool"]
    tool_names = {s["tool_name"] for s in tool_steps}
    assert "get_account_orders" in tool_names
    assert "search_knowledge_base" in tool_names


def test_get_ticket_by_id(client):
    created = client.post(
        "/tickets",
        json={"subject": "Business hours?", "body": "What are your support hours?"},
    ).json()

    resp = client.get(f"/tickets/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["resolution"]["category"] == "faq"


def test_get_missing_ticket_returns_404(client):
    assert client.get("/tickets/99999").status_code == 404
