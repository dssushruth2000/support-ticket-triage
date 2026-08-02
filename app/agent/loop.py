"""The agent reasoning loop.

This is the heart of the project: a plain Python loop (no framework) that lets
the LLM decide which tools to call, runs them, feeds results back, and repeats
until the model returns a final decision or a safety cap is hit.

The loop is deliberately free of database/HTTP concerns — it takes a ticket and
returns a structured result plus a full step trace. Callers (the API, the CLI,
the tests) decide what to persist.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.agent.llm import LLMProvider, ToolCall
from app.agent.prompts import SYSTEM_PROMPT, build_ticket_message
from app.config import settings
from app.tools.registry import ToolRegistry


@dataclass
class StepRecord:
    step: int
    kind: str  # "llm" | "tool" | "final"
    content: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class AgentDecision:
    category: str | None = None
    urgency: str | None = None
    confidence: float | None = None
    draft_response: str | None = None
    reasoning: str | None = None


@dataclass
class AgentRunResult:
    decision: AgentDecision
    steps: list[StepRecord] = field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    raw_final_text: str | None = None
    hit_step_limit: bool = False


def run_agent(
    subject: str,
    body: str,
    customer_id: str | None,
    provider: LLMProvider,
    registry: ToolRegistry,
    max_steps: int | None = None,
) -> AgentRunResult:
    max_steps = max_steps or settings.max_agent_steps
    tool_specs = registry.specs()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_ticket_message(subject, body, customer_id)},
    ]

    steps: list[StepRecord] = []
    step_no = 0

    for _ in range(max_steps):
        t0 = time.perf_counter()
        result = provider.generate(messages, tool_specs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if result.wants_tools:
            step_no += 1
            steps.append(
                StepRecord(
                    step=step_no,
                    kind="llm",
                    content=result.text,
                    tokens=result.tokens,
                    cost_usd=result.cost_usd,
                    latency_ms=latency_ms,
                )
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": result.text or "",
                    "tool_calls": result.tool_calls,
                    # Opaque provider-native turn, replayed verbatim if present
                    # (preserves Gemini thought signatures across tool calls).
                    "raw_content": result.raw_content,
                }
            )
            for tc in result.tool_calls:
                step_no += 1
                t_tool = time.perf_counter()
                tool_result = registry.dispatch(tc.name, tc.args)
                tool_latency = int((time.perf_counter() - t_tool) * 1000)
                steps.append(
                    StepRecord(
                        step=step_no,
                        kind="tool",
                        tool_name=tc.name,
                        tool_args=tc.args,
                        tool_result=tool_result,
                        latency_ms=tool_latency,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "name": tc.name,
                        "content": json.dumps(tool_result),
                    }
                )
            continue

        # No tool calls -> this is the final answer.
        step_no += 1
        steps.append(
            StepRecord(
                step=step_no,
                kind="final",
                content=result.text,
                tokens=result.tokens,
                cost_usd=result.cost_usd,
                latency_ms=latency_ms,
            )
        )
        decision = _parse_decision(result.text)
        return _finalize(decision, steps, result.text, hit_limit=False)

    # Ran out of steps without a final decision -> safe fallback.
    fallback = AgentDecision(
        category="other",
        urgency="high",
        confidence=0.0,
        draft_response=None,
        reasoning="Agent hit the step limit without producing a final decision.",
    )
    return _finalize(fallback, steps, None, hit_limit=True)


def _finalize(
    decision: AgentDecision,
    steps: list[StepRecord],
    raw_final_text: str | None,
    hit_limit: bool,
) -> AgentRunResult:
    return AgentRunResult(
        decision=decision,
        steps=steps,
        total_tokens=sum(s.tokens for s in steps),
        total_cost_usd=round(sum(s.cost_usd for s in steps), 8),
        total_latency_ms=sum(s.latency_ms for s in steps),
        raw_final_text=raw_final_text,
        hit_step_limit=hit_limit,
    )


def _parse_decision(text: str | None) -> AgentDecision:
    """Extract the JSON decision from the model's final message.

    Tolerates code fences and surrounding prose; falls back to a low-confidence
    'other' decision if nothing parseable is found.
    """
    if not text:
        return AgentDecision(category="other", confidence=0.0, reasoning="Empty final response.")

    raw = _extract_json(text)
    if raw is None:
        return AgentDecision(
            category="other",
            confidence=0.0,
            draft_response=text.strip() or None,
            reasoning="Could not parse a JSON decision from the model output.",
        )

    conf = raw.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None

    return AgentDecision(
        category=raw.get("category"),
        urgency=raw.get("urgency"),
        confidence=conf,
        draft_response=raw.get("draft_response"),
        reasoning=raw.get("reasoning"),
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    # Strip common code fences.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        # Fall back to the first balanced-looking {...} block.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
    if candidate is None:
        return None
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
