"""Scoring helpers for the eval suite.

Metrics (what interviewers ask about):
* category accuracy
* per-category precision / recall
* false-escalation rate  — non-high-risk gold tickets that escalated
* missed-escalation rate — high-risk gold tickets that did *not* escalate
* high-risk auto-respond rate — must be 0 (billing/refund/cancellation never auto-send)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.agent.guardrails import (
    AUTO_RESPOND,
    ESCALATE_TO_HUMAN,
    HIGH_RISK_CATEGORIES,
)


@dataclass
class EvalPrediction:
    ticket_id: str
    gold_category: str
    gold_action: str
    pred_category: str | None
    pred_confidence: float | None
    pred_action: str | None
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: str | None = None


@dataclass
class ScoreReport:
    n: int
    n_scored: int
    category_accuracy: float
    per_category_precision: dict[str, float]
    per_category_recall: dict[str, float]
    false_escalation_rate: float
    missed_escalation_rate: float
    high_risk_auto_respond_rate: float
    action_accuracy: float
    total_cost_usd: float
    avg_latency_ms: float
    errors: int
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "n_scored": self.n_scored,
            "category_accuracy": round(self.category_accuracy, 4),
            "per_category_precision": {
                k: round(v, 4) for k, v in sorted(self.per_category_precision.items())
            },
            "per_category_recall": {
                k: round(v, 4) for k, v in sorted(self.per_category_recall.items())
            },
            "false_escalation_rate": round(self.false_escalation_rate, 4),
            "missed_escalation_rate": round(self.missed_escalation_rate, 4),
            "high_risk_auto_respond_rate": round(self.high_risk_auto_respond_rate, 4),
            "action_accuracy": round(self.action_accuracy, 4),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "errors": self.errors,
            "confusion": self.confusion,
        }


def score(predictions: list[EvalPrediction]) -> ScoreReport:
    scored = [p for p in predictions if p.error is None and p.pred_category is not None]
    errors = len(predictions) - len(scored)

    correct = sum(1 for p in scored if p.pred_category == p.gold_category)
    cat_acc = (correct / len(scored)) if scored else 0.0

    # Confusion + per-category precision/recall.
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    labels = {p.gold_category for p in scored} | {
        p.pred_category for p in scored if p.pred_category
    }

    for p in scored:
        assert p.pred_category is not None
        confusion[p.gold_category][p.pred_category] += 1
        if p.pred_category == p.gold_category:
            tp[p.gold_category] += 1
        else:
            fp[p.pred_category] += 1
            fn[p.gold_category] += 1

    precision = {
        lab: (tp[lab] / (tp[lab] + fp[lab])) if (tp[lab] + fp[lab]) else 0.0
        for lab in sorted(labels)
    }
    recall = {
        lab: (tp[lab] / (tp[lab] + fn[lab])) if (tp[lab] + fn[lab]) else 0.0
        for lab in sorted(labels)
    }

    # Safety metrics use gold category (what the ticket *is*), not the prediction.
    high_risk = [p for p in scored if p.gold_category in HIGH_RISK_CATEGORIES]
    non_high = [p for p in scored if p.gold_category not in HIGH_RISK_CATEGORIES]

    missed = sum(1 for p in high_risk if p.pred_action != ESCALATE_TO_HUMAN)
    false_esc = sum(1 for p in non_high if p.pred_action == ESCALATE_TO_HUMAN)
    high_risk_auto = sum(1 for p in high_risk if p.pred_action == AUTO_RESPOND)

    action_correct = sum(1 for p in scored if p.pred_action == p.gold_action)

    total_cost = sum(p.cost_usd for p in predictions)
    avg_lat = (
        sum(p.latency_ms for p in scored) / len(scored) if scored else 0.0
    )

    return ScoreReport(
        n=len(predictions),
        n_scored=len(scored),
        category_accuracy=cat_acc,
        per_category_precision=precision,
        per_category_recall=recall,
        false_escalation_rate=(false_esc / len(non_high)) if non_high else 0.0,
        missed_escalation_rate=(missed / len(high_risk)) if high_risk else 0.0,
        high_risk_auto_respond_rate=(high_risk_auto / len(high_risk)) if high_risk else 0.0,
        action_accuracy=(action_correct / len(scored)) if scored else 0.0,
        total_cost_usd=total_cost,
        avg_latency_ms=avg_lat,
        errors=errors,
        confusion={g: dict(preds) for g, preds in confusion.items()},
    )


def format_report(report: ScoreReport) -> str:
    d = report.to_dict()
    lines = [
        f"Eval report  n={d['n']}  scored={d['n_scored']}  errors={d['errors']}",
        f"  category_accuracy          : {d['category_accuracy']:.1%}",
        f"  action_accuracy            : {d['action_accuracy']:.1%}",
        f"  false_escalation_rate      : {d['false_escalation_rate']:.1%}",
        f"  missed_escalation_rate     : {d['missed_escalation_rate']:.1%}",
        f"  high_risk_auto_respond_rate: {d['high_risk_auto_respond_rate']:.1%}  (must be 0%)",
        f"  total_cost_usd (estimate)  : ${d['total_cost_usd']:.4f}",
        f"  avg_latency_ms             : {d['avg_latency_ms']:.0f}",
        "  per-category precision / recall:",
    ]
    cats = sorted(
        set(d["per_category_precision"]) | set(d["per_category_recall"])
    )
    for cat in cats:
        p = d["per_category_precision"].get(cat, 0.0)
        r = d["per_category_recall"].get(cat, 0.0)
        lines.append(f"    {cat:16s}  P={p:.2f}  R={r:.2f}")
    return "\n".join(lines)
