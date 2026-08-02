"""Tests for the agent tools and registry."""

from __future__ import annotations

from app.tools import build_default_registry


def test_get_account_orders_finds_duplicate_charge():
    reg = build_default_registry()
    result = reg.dispatch("get_account_orders", {"customer_id": "CUST-1001"})
    assert result["found"] is True
    assert result["order_count"] == 2
    # Two charges of the same amount indicate the duplicate.
    amounts = [o["amount_usd"] for o in result["orders"]]
    assert amounts.count(29.00) == 2


def test_get_account_orders_unknown_customer():
    reg = build_default_registry()
    result = reg.dispatch("get_account_orders", {"customer_id": "NOPE"})
    assert result["found"] is False
    assert result["order_count"] == 0


def test_search_knowledge_base_returns_relevant_docs():
    reg = build_default_registry()
    result = reg.dispatch("search_knowledge_base", {"query": "duplicate charge refund policy"})
    assert result["match_count"] >= 1
    assert "refund" in result["results"][0]["content"].lower()


def test_check_system_status():
    reg = build_default_registry()
    result = reg.dispatch("check_system_status", {})
    assert result["overall"] == "operational"


def test_dispatch_unknown_tool_is_safe():
    reg = build_default_registry()
    result = reg.dispatch("does_not_exist", {})
    assert "error" in result


def test_dispatch_bad_arguments_is_safe():
    reg = build_default_registry()
    # missing required customer_id
    result = reg.dispatch("get_account_orders", {})
    assert "error" in result


def test_registry_exposes_all_five_tools():
    reg = build_default_registry()
    names = set(reg.names())
    assert names == {
        "get_account_orders",
        "search_knowledge_base",
        "check_system_status",
        "flag_for_escalation",
        "log_resolution",
    }
