"""Patch gold labels for informational intents and re-score the Gemini cache.

No LLM calls — recomputes guardrail actions from cached predictions + ticket text.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.guardrails import AUTO_RESPOND, check_guardrails
from evals.score import EvalPrediction, format_report, score

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "data" / "eval_tickets.jsonl"
CACHE = ROOT / "evals" / "results" / "cache_gemini_gemini-flash-lite-latest.jsonl"
REPORT = ROOT / "evals" / "results" / "report_gemini.json"

# Informational Bitext intents that should not be treated as high-risk gold.
REMAP_INTENTS = {
    "check_payment_methods": "faq",
    "check_refund_policy": "faq",
}


def _expected_action(category: str) -> str:
    from app.agent.guardrails import (
        AUTO_RESPOND_CATEGORIES,
        DRAFT_FOR_REVIEW,
        ESCALATE_TO_HUMAN,
        HIGH_RISK_CATEGORIES,
    )

    if category in HIGH_RISK_CATEGORIES:
        return ESCALATE_TO_HUMAN
    if category in AUTO_RESPOND_CATEGORIES:
        return AUTO_RESPOND
    return DRAFT_FOR_REVIEW


def patch_tickets() -> int:
    rows = [
        json.loads(line)
        for line in TICKETS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    changed = 0
    for row in rows:
        intent = row.get("source_intent")
        if intent in REMAP_INTENTS:
            new_cat = REMAP_INTENTS[intent]
            if row.get("gold_category") != new_cat:
                row["gold_category"] = new_cat
                row["gold_action"] = _expected_action(new_cat)
                changed += 1
    TICKETS.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return changed


def rescore() -> None:
    tickets = {
        json.loads(line)["id"]: json.loads(line)
        for line in TICKETS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    cache_rows = [
        json.loads(line)
        for line in CACHE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    predictions: list[EvalPrediction] = []
    updated_cache: list[dict] = []
    for row in cache_rows:
        tid = row["ticket_id"]
        ticket = tickets[tid]
        gold_cat = ticket["gold_category"]
        gold_action = ticket["gold_action"]
        pred_cat = row.get("pred_category")
        pred_conf = row.get("pred_confidence")
        if row.get("error") or pred_cat is None:
            action = row.get("pred_action")
        else:
            action = check_guardrails(
                pred_cat,
                pred_conf,
                subject=ticket.get("subject", ""),
                body=ticket.get("body", ""),
            ).action

        new_row = dict(row)
        new_row["gold_category"] = gold_cat
        new_row["gold_action"] = gold_action
        new_row["pred_action"] = action
        updated_cache.append(new_row)

        predictions.append(
            EvalPrediction(
                ticket_id=tid,
                gold_category=gold_cat,
                gold_action=gold_action,
                pred_category=pred_cat,
                pred_confidence=pred_conf,
                pred_action=action,
                cost_usd=float(row.get("cost_usd") or 0.0),
                latency_ms=int(row.get("latency_ms") or 0),
                error=row.get("error"),
            )
        )

    CACHE.write_text(
        "".join(json.dumps(r) + "\n" for r in updated_cache),
        encoding="utf-8",
    )
    report = score(predictions)
    REPORT.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(format_report(report))
    print(f"Wrote report -> {REPORT}")


def main() -> None:
    n = patch_tickets()
    print(f"Patched gold labels on {n} tickets")
    rescore()


if __name__ == "__main__":
    main()
