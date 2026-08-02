"""Tool registry: the single place the agent discovers and invokes tools.

Each tool carries a JSON-schema ``parameters`` spec (the same shape the LLM
needs for function calling) plus the Python callable that runs it. The registry
gives the agent loop two things: ``specs()`` to advertise tools to the model,
and ``dispatch()`` to actually run a chosen tool safely.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.tools import tools as impl


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., dict[str, Any]]

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self._tools.values()]

    def has(self, name: str) -> bool:
        return name in self._tools

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"unknown tool: {name}"}
        try:
            return tool.fn(**(args or {}))
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - tools must never crash the loop
            return {"error": f"tool {name} failed: {exc}"}


def build_default_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                name="get_account_orders",
                description="Fetch a customer's order and billing history by customer_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "The customer's ID, e.g. CUST-1001.",
                        }
                    },
                    "required": ["customer_id"],
                },
                fn=impl.get_account_orders,
            ),
            Tool(
                name="search_knowledge_base",
                description="Search policy docs and FAQs for relevant information.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language search query.",
                        }
                    },
                    "required": ["query"],
                },
                fn=impl.search_knowledge_base,
            ),
            Tool(
                name="check_system_status",
                description="Check current system/service status for technical issues.",
                parameters={"type": "object", "properties": {}},
                fn=impl.check_system_status,
            ),
            Tool(
                name="flag_for_escalation",
                description="Hand the ticket off to a human, with a reason.",
                parameters={
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why this ticket needs a human.",
                        }
                    },
                    "required": ["reason"],
                },
                fn=impl.flag_for_escalation,
            ),
            Tool(
                name="log_resolution",
                description="Record the final outcome of a ticket for auditing.",
                parameters={
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "outcome": {"type": "string"},
                    },
                    "required": ["ticket_id", "outcome"],
                },
                fn=impl.log_resolution,
            ),
        ]
    )
