"""Run the triage agent over the labeled eval set and score the results.

Features for free-tier friendliness:
* JSONL result cache — re-runs skip tickets already completed
* ``--limit N`` for a smoke/baseline slice before the full 250
* Progress + periodic summary

Usage:
  # mock (no key, fast — validates the harness)
  python -m evals.run_eval --provider mock --limit 30

  # real Gemini baseline
  python -m evals.run_eval --provider gemini --limit 30

  # full set (resumes from cache)
  python -m evals.run_eval --provider gemini
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.agent.guardrails import check_guardrails
from app.agent.llm import GeminiProvider, MockProvider
from app.agent.loop import run_agent
from app.tools import build_default_registry
from evals.score import EvalPrediction, format_report, score

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TICKETS = ROOT / "data" / "eval_tickets.jsonl"
DEFAULT_CACHE = ROOT / "evals" / "results" / "cache.jsonl"
DEFAULT_REPORT = ROOT / "evals" / "results" / "latest_report.json"


def _load_tickets(path: Path) -> list[dict]:
    tickets = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tickets.append(json.loads(line))
    return tickets


def _load_cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    cached: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cached[row["ticket_id"]] = row
    return cached


def _append_cache(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _get_provider(name: str):
    if name == "gemini":
        return GeminiProvider()
    return MockProvider()


def _prediction_from_cache(row: dict) -> EvalPrediction:
    return EvalPrediction(
        ticket_id=row["ticket_id"],
        gold_category=row["gold_category"],
        gold_action=row["gold_action"],
        pred_category=row.get("pred_category"),
        pred_confidence=row.get("pred_confidence"),
        pred_action=row.get("pred_action"),
        cost_usd=float(row.get("cost_usd") or 0.0),
        latency_ms=int(row.get("latency_ms") or 0),
        error=row.get("error"),
    )


def run_eval(
    tickets_path: Path,
    cache_path: Path,
    report_path: Path,
    provider_name: str,
    limit: int | None,
    sleep_s: float,
) -> None:
    tickets = _load_tickets(tickets_path)
    if limit is not None:
        tickets = tickets[:limit]

    cache = _load_cache(cache_path)
    provider = _get_provider(provider_name)
    registry = build_default_registry()

    predictions: list[EvalPrediction] = []
    print(f"Eval: {len(tickets)} tickets | provider={provider_name} | cache={cache_path}", flush=True)

    for i, ticket in enumerate(tickets, start=1):
        tid = ticket["id"]
        if tid in cache:
            pred = _prediction_from_cache(cache[tid])
            predictions.append(pred)
            status = "CACHE"
            if pred.error:
                status = "CACHE-ERR"
            print(
                f"  [{i}/{len(tickets)}] {status} {tid}  "
                f"gold={ticket['gold_category']} pred={pred.pred_category} "
                f"action={pred.pred_action}",
                flush=True,
            )
            continue

        t0 = time.perf_counter()
        row: dict = {
            "ticket_id": tid,
            "gold_category": ticket["gold_category"],
            "gold_action": ticket["gold_action"],
            "provider": provider_name,
        }
        try:
            result = run_agent(
                subject=ticket["subject"],
                body=ticket["body"],
                customer_id=ticket.get("customer_id"),
                provider=provider,
                registry=registry,
            )
            d = result.decision
            guard = check_guardrails(
                d.category,
                d.confidence,
                subject=ticket["subject"],
                body=ticket["body"],
            )
            row.update(
                {
                    "pred_category": d.category,
                    "pred_confidence": d.confidence,
                    "pred_action": guard.action,
                    "pred_urgency": d.urgency,
                    "cost_usd": result.total_cost_usd,
                    "latency_ms": result.total_latency_ms,
                    "steps": len(result.steps),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 — keep the eval running
            row.update(
                {
                    "pred_category": None,
                    "pred_confidence": None,
                    "pred_action": None,
                    "cost_usd": 0.0,
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        _append_cache(cache_path, row)
        cache[tid] = row
        pred = _prediction_from_cache(row)
        predictions.append(pred)
        mark = "OK" if not pred.error else "ERR"
        print(
            f"  [{i}/{len(tickets)}] {mark} {tid}  "
            f"gold={ticket['gold_category']} pred={pred.pred_category} "
            f"action={pred.pred_action}"
            + (f"  err={pred.error}" if pred.error else ""),
            flush=True,
        )

        if sleep_s > 0 and provider_name == "gemini":
            time.sleep(sleep_s)

    report = score(predictions)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print()
    print(format_report(report))
    print(f"\nWrote report -> {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval suite.")
    parser.add_argument("--tickets", type=Path, default=DEFAULT_TICKETS)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--provider", choices=["mock", "gemini"], default="mock")
    parser.add_argument("--limit", type=int, default=None, help="Only first N tickets.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.5,
        help="Seconds between Gemini calls (free-tier pacing). Ignored for mock.",
    )
    args = parser.parse_args()

    if not args.tickets.exists():
        raise SystemExit(
            f"Missing {args.tickets}. Run: python -m evals.prepare_dataset"
        )

    # Use a provider+model-specific cache so mock/gemini/model swaps don't collide.
    cache = args.cache
    if cache == DEFAULT_CACHE:
        model_tag = "mock"
        if args.provider == "gemini":
            from app.config import settings

            model_tag = settings.gemini_model.replace("/", "_")
        cache = ROOT / "evals" / "results" / f"cache_{args.provider}_{model_tag}.jsonl"

    report = args.report
    if report == DEFAULT_REPORT:
        report = ROOT / "evals" / "results" / f"report_{args.provider}.json"

    run_eval(
        tickets_path=args.tickets,
        cache_path=cache,
        report_path=report,
        provider_name=args.provider,
        limit=args.limit,
        sleep_s=args.sleep,
    )


if __name__ == "__main__":
    main()
