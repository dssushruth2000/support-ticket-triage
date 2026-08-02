"""LLM provider abstraction.

The agent loop talks to an ``LLMProvider`` through one small interface, so the
underlying model can be swapped with a single config change:

* ``MockProvider``  — deterministic, no API key, keeps the whole project
  runnable and the tests reproducible.
* ``GeminiProvider`` — Google Gemini (free tier) via the ``google-genai`` SDK.

This same seam is where Phase-4 "cheap vs. strong model routing" will plug in.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

# --- Normalized message + result types -------------------------------------

# A "message" is a plain dict with a role and content:
#   {"role": "system"|"user"|"assistant"|"tool", "content": str,
#    "tool_calls": [ToolCall...]?, "name": str?}


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class LLMResult:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0
    cost_usd: float = 0.0
    raw: Any = None
    # The provider's native assistant turn, replayed verbatim on the next
    # request so opaque data (e.g. Gemini thought signatures + thought parts)
    # survives the round-trip. ``None`` for providers that don't need it.
    raw_content: Any = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResult:
        """Given the conversation so far and available tool specs, return the
        model's next step: either tool calls or a final text answer."""


# --- Mock provider ----------------------------------------------------------


class MockProvider(LLMProvider):
    """A deterministic stand-in for a real LLM.

    It classifies the ticket with simple keyword rules, calls the tools a real
    agent would plausibly call (once each), then emits a final JSON decision.
    This lets the full agent loop — tool calling included — run and be tested
    without any network access or API key.
    """

    name = "mock"

    BILLING_WORDS = ("charg", "invoice", "payment", "billed", "subscription")
    REFUND_WORDS = ("refund",)
    CANCEL_WORDS = ("cancel",)
    TECH_WORDS = ("down", "error", "not working", "outage", "crash", "bug", "slow", "load")
    PASSWORD_WORDS = ("password", "reset", "log in", "login", "can't sign in", "cant sign in")
    ACCOUNT_WORDS = ("account", "profile", "sign up", "signup", "register")

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResult:
        ticket_text = self._ticket_text(messages).lower()
        called = self._tools_already_called(messages)
        category = self._classify(ticket_text)

        tokens = max(20, len(ticket_text.split()))

        # Decide the next tool to call, mimicking sensible agent behavior.
        if category == "billing" and "get_account_orders" not in called:
            return LLMResult(
                tool_calls=[ToolCall("get_account_orders", {"customer_id": self._customer_id(messages)})],
                tokens=tokens,
            )
        if category in ("refund", "cancellation") and "get_account_orders" not in called:
            return LLMResult(
                tool_calls=[ToolCall("get_account_orders", {"customer_id": self._customer_id(messages)})],
                tokens=tokens,
            )
        if category == "technical" and "check_system_status" not in called:
            return LLMResult(
                tool_calls=[ToolCall("check_system_status", {})],
                tokens=tokens,
            )
        if "search_knowledge_base" not in called:
            query = {
                "billing": "duplicate charge refund policy",
                "refund": "refund policy",
                "cancellation": "cancellation policy",
                "technical": "service outage troubleshooting",
                "password_reset": "how to reset password",
                "faq": "general help",
                "account": "account help",
            }.get(category, "general help")
            return LLMResult(
                tool_calls=[ToolCall("search_knowledge_base", {"query": query})],
                tokens=tokens,
            )

        # Enough info gathered -> produce the final structured decision.
        return LLMResult(text=self._final_json(category, ticket_text), tokens=tokens)

    # -- helpers --

    def _ticket_text(self, messages: list[dict[str, Any]]) -> str:
        for m in messages:
            if m.get("role") == "user":
                return str(m.get("content", ""))
        return ""

    def _customer_id(self, messages: list[dict[str, Any]]) -> str:
        for m in messages:
            if m.get("role") == "user":
                match = re.search(r"customer[_ ]?id[:=]?\s*([A-Za-z0-9\-]+)", str(m.get("content", "")), re.I)
                if match:
                    return match.group(1)
        return "UNKNOWN"

    def _tools_already_called(self, messages: list[dict[str, Any]]) -> set[str]:
        called: set[str] = set()
        for m in messages:
            if m.get("role") == "tool" and m.get("name"):
                called.add(str(m["name"]))
        return called

    def _classify(self, text: str) -> str:
        if any(w in text for w in self.PASSWORD_WORDS):
            return "password_reset"
        if any(w in text for w in self.REFUND_WORDS):
            return "refund"
        if any(w in text for w in self.CANCEL_WORDS):
            return "cancellation"
        if any(w in text for w in self.BILLING_WORDS):
            return "billing"
        if any(w in text for w in self.TECH_WORDS):
            return "technical"
        if any(w in text for w in self.ACCOUNT_WORDS):
            return "account"
        return "faq"

    def _final_json(self, category: str, text: str) -> str:
        urgency = "high" if category in ("billing", "refund", "cancellation", "technical") else "low"
        confidence = {
            "password_reset": 0.93,
            "faq": 0.9,
            "billing": 0.82,
            "refund": 0.85,
            "cancellation": 0.84,
            "technical": 0.8,
            "account": 0.78,
        }.get(category, 0.7)
        draft = {
            "password_reset": "You can reset your password using the 'Forgot password' link on the sign-in page. I've included the steps and a reset link.",
            "faq": "Thanks for reaching out! Here's the information you're looking for based on our help center.",
            "billing": "I looked into your account and can see the charges in question. Here's what our policy allows and the next steps.",
            "refund": "I've reviewed your refund request against our policy and outlined the next steps below.",
            "cancellation": "I've looked up your plan and cancellation options. Here's what happens if you cancel.",
            "technical": "Thanks for flagging this. I checked system status and here's what I found, along with troubleshooting steps.",
            "account": "I can help with your account request. Here's what I found and the next steps.",
        }.get(category, "Thanks for contacting support — here's what I can share.")
        decision = {
            "category": category,
            "urgency": urgency,
            "confidence": confidence,
            "draft_response": draft,
            "reasoning": f"Classified as {category}; gathered account/policy/status context via tools before responding.",
        }
        return json.dumps(decision)


# --- Gemini provider --------------------------------------------------------

# Rough public pricing (USD per 1M tokens) for cost estimation. These are
# approximate and meant for relative cost tracking, not billing — update when
# confirmed against current Google pricing. ``_DEFAULT_PRICE`` keeps cost from
# silently reading $0 for a model that isn't listed here.
_GEMINI_PRICES = {
    "gemini-1.5-flash": {"in": 0.075, "out": 0.30},
    "gemini-1.5-pro": {"in": 1.25, "out": 5.00},
    "gemini-2.0-flash": {"in": 0.10, "out": 0.40},
    "gemini-2.0-flash-lite": {"in": 0.075, "out": 0.30},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
    # Newer flash line (3.x + rolling "-latest" aliases).
    "gemini-flash-latest": {"in": 0.30, "out": 2.50},
    "gemini-flash-lite-latest": {"in": 0.10, "out": 0.40},
    "gemini-3.1-flash-lite": {"in": 0.10, "out": 0.40},
    "gemini-3.5-flash": {"in": 0.30, "out": 2.50},
}
_DEFAULT_PRICE = {"in": 0.30, "out": 2.50}


class GeminiProvider(LLMProvider):
    """Google Gemini via the ``google-genai`` SDK.

    NOTE: This path requires a GEMINI_API_KEY and the ``google-genai`` package.
    It should be validated once a key is available; until then the project
    defaults to the mock provider.
    """

    name = "gemini"

    def __init__(self, model: str | None = None) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc

        self._genai = genai
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = model or settings.gemini_model
        # Free-tier pacing: retry transient 429/503 with exponential backoff.
        self._max_retries = 5
        self._base_backoff_s = 2.0

    def generate(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMResult:
        from google.genai import types
        import google.genai.errors as genai_errors

        system_instruction = "\n\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "system"
        )
        contents = self._to_contents(messages, types)
        tool_config = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("parameters"),
                    )
                    for t in tools
                ]
            )
        ] if tools else None

        config = types.GenerateContentConfig(
            system_instruction=system_instruction or None,
            tools=tool_config,
            temperature=0.2,
        )

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                break
            except genai_errors.APIError as exc:
                last_exc = exc
                code = getattr(exc, "code", None)
                # Retry rate-limit / overload; fail fast on auth / bad-request.
                if code not in (429, 503) or attempt >= self._max_retries:
                    raise
                delay = self._backoff_seconds(exc, attempt)
                time.sleep(delay)
        else:  # pragma: no cover — loop always breaks or raises
            assert last_exc is not None
            raise last_exc

        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        candidate = (response.candidates or [None])[0]
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    tool_calls.append(ToolCall(name=fc.name, args=dict(fc.args or {})))
                elif getattr(part, "text", None):
                    text_parts.append(part.text)

        tokens, cost = self._usage(response)
        return LLMResult(
            text="".join(text_parts) or None,
            tool_calls=tool_calls,
            tokens=tokens,
            cost_usd=cost,
            raw=response,
            raw_content=candidate.content if candidate else None,
        )

    def _backoff_seconds(self, exc: Exception, attempt: int) -> float:
        """Prefer the API's RetryInfo delay when present; else exponential backoff."""
        message = str(exc)
        match = re.search(r"[Rr]etry(?:Delay)?[^\d]*(\d+(?:\.\d+)?)\s*s", message)
        if match:
            return float(match.group(1)) + 0.5
        return self._base_backoff_s * (2**attempt)

    def _to_contents(self, messages: list[dict[str, Any]], types) -> list[Any]:
        contents: list[Any] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            if role == "user":
                contents.append(
                    types.Content(role="user", parts=[types.Part(text=str(m.get("content", "")))])
                )
            elif role == "assistant":
                # Preferred path: replay the model's own turn verbatim so opaque
                # thought signatures / thought parts round-trip intact.
                raw_content = m.get("raw_content")
                if raw_content is not None:
                    contents.append(raw_content)
                    continue
                # Fallback (e.g. mock provider): rebuild from normalized fields.
                parts = []
                if m.get("content"):
                    parts.append(types.Part(text=str(m["content"])))
                for tc in m.get("tool_calls", []) or []:
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(name=tc.name, args=tc.args)
                        )
                    )
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                result = m.get("content")
                try:
                    result_obj = json.loads(result) if isinstance(result, str) else result
                except (TypeError, ValueError):
                    result_obj = {"result": result}
                if not isinstance(result_obj, dict):
                    result_obj = {"result": result_obj}
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=m.get("name", "tool"), response=result_obj
                                )
                            )
                        ],
                    )
                )
        return contents

    def _usage(self, response: Any) -> tuple[int, float]:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return 0, 0.0
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        # Thinking models bill hidden reasoning as output, reported separately.
        out_tok = (getattr(usage, "candidates_token_count", 0) or 0) + (
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        total = getattr(usage, "total_token_count", 0) or (in_tok + out_tok)
        prices = _GEMINI_PRICES.get(self._model, _DEFAULT_PRICE)
        cost = (in_tok * prices["in"] + out_tok * prices["out"]) / 1_000_000
        return total, cost


# --- Factory ----------------------------------------------------------------


def get_provider(model: str | None = None) -> LLMProvider:
    """Return the configured provider.

    ``model`` overrides the default Gemini model (used by Phase 4 routing).
    Ignored for the mock provider.
    """
    provider = settings.llm_provider.lower().strip()
    if provider == "gemini":
        return GeminiProvider(model=model)
    return MockProvider()


def resolve_model_for_tier(tier: str) -> str:
    """Map a routing tier to the concrete Gemini model name."""
    if tier == "cheap":
        return settings.gemini_model_cheap
    if tier == "strong":
        return settings.gemini_model_strong
    return settings.gemini_model
