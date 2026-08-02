"""Pydantic request/response models for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=512)
    body: str = Field(..., min_length=1)
    customer_id: str | None = None
    external_id: str | None = None
    channel: str = "email"


class DecisionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: int
    kind: str
    tool_name: str | None
    tool_args: dict | None
    tool_result: dict | None
    content: str | None
    tokens: int
    cost_usd: float
    latency_ms: int


class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str | None
    urgency: str | None
    confidence: float | None
    action: str | None
    draft_response: str | None
    reasoning: str | None
    steps_taken: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    model_tier: str | None = None
    model_name: str | None = None
    route_reason: str | None = None


class MetricsSummaryOut(BaseModel):
    ticket_count: int
    avg_cost_usd: float
    total_cost_usd: float
    avg_latency_ms: float
    escalation_rate: float
    auto_respond_rate: float
    draft_rate: float
    cheap_tier_share: float
    strong_tier_share: float
    by_category: dict[str, int]
    by_action: dict[str, int]
    by_tier: dict[str, int]


class RecentTicketMetricOut(BaseModel):
    id: int
    subject: str
    category: str | None
    action: str | None
    confidence: float | None
    cost_usd: float
    latency_ms: int
    model_tier: str | None
    model_name: str | None
    created_at: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    customer_id: str | None
    subject: str
    body: str
    channel: str
    status: str
    created_at: datetime
    resolution: ResolutionOut | None = None


class TicketDetailOut(TicketOut):
    decision_logs: list[DecisionLogOut] = []
