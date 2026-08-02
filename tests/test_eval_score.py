"""Unit tests for the Phase 3 scoring helpers (no LLM, no network)."""

from __future__ import annotations

from evals.score import EvalPrediction, score


def _p(
    tid: str,
    gold_cat: str,
    gold_action: str,
    pred_cat: str,
    pred_action: str,
    conf: float = 0.9,
) -> EvalPrediction:
    return EvalPrediction(
        ticket_id=tid,
        gold_category=gold_cat,
        gold_action=gold_action,
        pred_category=pred_cat,
        pred_confidence=conf,
        pred_action=pred_action,
    )


def test_perfect_scores():
    preds = [
        _p("1", "billing", "escalate_to_human", "billing", "escalate_to_human"),
        _p("2", "faq", "auto_respond", "faq", "auto_respond"),
        _p("3", "password_reset", "auto_respond", "password_reset", "auto_respond"),
    ]
    report = score(preds)
    assert report.category_accuracy == 1.0
    assert report.action_accuracy == 1.0
    assert report.missed_escalation_rate == 0.0
    assert report.false_escalation_rate == 0.0
    assert report.high_risk_auto_respond_rate == 0.0


def test_missed_escalation_detected():
    # Gold is billing (must escalate) but agent drafted for review.
    preds = [
        _p("1", "billing", "escalate_to_human", "billing", "draft_for_review"),
        _p("2", "faq", "auto_respond", "faq", "auto_respond"),
    ]
    report = score(preds)
    assert report.missed_escalation_rate == 1.0
    assert report.high_risk_auto_respond_rate == 0.0


def test_high_risk_never_auto_respond_metric():
    preds = [
        _p("1", "refund", "escalate_to_human", "refund", "auto_respond"),
    ]
    report = score(preds)
    assert report.high_risk_auto_respond_rate == 1.0


def test_false_escalation_detected():
    preds = [
        _p("1", "faq", "auto_respond", "faq", "escalate_to_human"),
        _p("2", "billing", "escalate_to_human", "billing", "escalate_to_human"),
    ]
    report = score(preds)
    assert report.false_escalation_rate == 1.0


def test_per_category_precision_recall():
    preds = [
        _p("1", "billing", "escalate_to_human", "billing", "escalate_to_human"),
        _p("2", "billing", "escalate_to_human", "faq", "auto_respond"),  # miss
        _p("3", "faq", "auto_respond", "faq", "auto_respond"),
    ]
    report = score(preds)
    # billing: 1 TP, 0 FP, 1 FN -> P=1.0, R=0.5
    assert report.per_category_precision["billing"] == 1.0
    assert report.per_category_recall["billing"] == 0.5
    # faq: 1 TP, 1 FP (the misclassified billing), 0 FN -> P=0.5, R=1.0
    assert report.per_category_precision["faq"] == 0.5
    assert report.per_category_recall["faq"] == 1.0


def test_errors_are_excluded_from_accuracy():
    preds = [
        _p("1", "faq", "auto_respond", "faq", "auto_respond"),
        EvalPrediction(
            ticket_id="2",
            gold_category="billing",
            gold_action="escalate_to_human",
            pred_category=None,
            pred_confidence=None,
            pred_action=None,
            error="APIError: 429",
        ),
    ]
    report = score(preds)
    assert report.n == 2
    assert report.n_scored == 1
    assert report.errors == 1
    assert report.category_accuracy == 1.0
