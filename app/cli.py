"""Command-line demo runner for the triage agent.

Runs tickets through the agent loop and prints a readable trace of every step
(LLM turns, tool calls, and the final decision). Uses the pure agent loop, so
it works with zero setup and no database.

Usage:
  python -m app.cli                         # run all sample tickets
  python -m app.cli --subject "..." --body "..." [--customer-id CUST-1001]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agent.guardrails import check_guardrails
from app.agent.llm import get_provider, resolve_model_for_tier
from app.agent.loop import AgentRunResult, run_agent
from app.agent.router import route_ticket
from app.config import settings
from app.tools import build_default_registry

SAMPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_tickets.json"


def _print_run(
    subject: str,
    customer_id: str | None,
    result: AgentRunResult,
    *,
    tier: str | None,
    model_name: str | None,
    route_reason: str | None,
) -> None:
    print("=" * 72)
    print(f"TICKET: {subject}   (customer_id={customer_id or 'UNKNOWN'})")
    if tier or model_name:
        print(f"ROUTE : tier={tier or '-'}  model={model_name or '-'}")
        if route_reason:
            print(f"        {route_reason}")
    print("-" * 72)
    for step in result.steps:
        if step.kind == "tool":
            print(f"  [{step.step}] TOOL  {step.tool_name}({json.dumps(step.tool_args)})")
            print(f"        -> {json.dumps(step.tool_result)}")
        elif step.kind == "llm":
            print(f"  [{step.step}] LLM   decided to call tool(s)  "
                  f"[tokens={step.tokens}, ${step.cost_usd:.6f}]")
        else:  # final
            print(f"  [{step.step}] FINAL [tokens={step.tokens}, ${step.cost_usd:.6f}]")
    d = result.decision
    guardrail = check_guardrails(d.category, d.confidence)
    print("-" * 72)
    print(f"  category   : {d.category}")
    print(f"  urgency    : {d.urgency}")
    print(f"  confidence : {d.confidence}")
    print(f"  action     : {guardrail.action}  ({guardrail.reason})")
    print(f"  draft      : {d.draft_response}")
    print(f"  reasoning  : {d.reasoning}")
    print(f"  totals     : {result.total_tokens} tokens, "
          f"${result.total_cost_usd:.6f}, {result.total_latency_ms} ms, "
          f"{len(result.steps)} steps")
    print("=" * 72)
    print()


def _provider_for(subject: str, body: str):
    if settings.enable_model_routing:
        decision = route_ticket(subject, body)
        model_name = resolve_model_for_tier(decision.tier)
        if settings.llm_provider.lower().strip() == "gemini":
            return get_provider(model=model_name), decision, model_name
        return get_provider(), decision, model_name
    p = get_provider()
    return p, None, getattr(p, "_model", settings.llm_provider)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the support-ticket triage agent.")
    parser.add_argument("--subject")
    parser.add_argument("--body")
    parser.add_argument("--customer-id")
    args = parser.parse_args()

    print(
        f"(LLM provider: {settings.llm_provider}, "
        f"routing={'on' if settings.enable_model_routing else 'off'})\n"
    )
    registry = build_default_registry()

    if args.subject and args.body:
        provider, route, model_name = _provider_for(args.subject, args.body)
        result = run_agent(args.subject, args.body, args.customer_id, provider, registry)
        _print_run(
            args.subject,
            args.customer_id,
            result,
            tier=route.tier if route else None,
            model_name=model_name,
            route_reason=route.reason if route else None,
        )
        return

    tickets = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    for t in tickets:
        provider, route, model_name = _provider_for(t["subject"], t["body"])
        result = run_agent(t["subject"], t["body"], t.get("customer_id"), provider, registry)
        _print_run(
            t["subject"],
            t.get("customer_id"),
            result,
            tier=route.tier if route else None,
            model_name=model_name,
            route_reason=route.reason if route else None,
        )


if __name__ == "__main__":
    main()
