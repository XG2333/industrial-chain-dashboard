from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .config import IntelligenceSettings
from .domain_tools import DomainToolRegistry


@dataclass(frozen=True)
class AgentResult:
    text: str
    tool_calls: tuple[dict[str, Any], ...]
    response_id: str | None = None


def run_tool_calling_query(
    query: str,
    settings: IntelligenceSettings,
    registry: DomainToolRegistry,
    *,
    client=None,
    max_rounds: int = 6,
) -> AgentResult:
    """Run an opt-in OpenAI Responses function-calling loop.

    Existing dashboard endpoints do not call this function. It is a separate
    integration surface so enabling or testing it cannot change legacy output.
    """

    settings.require("tool_calling")
    if not settings.openai_model:
        raise RuntimeError("INDUSTRY_OPENAI_MODEL must be configured for tool calling.")
    if client is None:
        from openai import OpenAI

        client = OpenAI()

    input_items: list[Any] = [{"role": "user", "content": query}]
    calls: list[dict[str, Any]] = []
    response = None
    for _ in range(max_rounds):
        response = client.responses.create(
            model=settings.openai_model,
            instructions=(
                "Answer only from tool results and approved project knowledge. "
                "Never invent unavailable observations. Include source_path values when using retrieved text."
            ),
            input=input_items,
            tools=registry.responses_schemas(),
            tool_choice="auto",
            parallel_tool_calls=False,
            store=False,
        )
        function_calls = [item for item in response.output if getattr(item, "type", "") == "function_call"]
        if not function_calls:
            return AgentResult(
                text=getattr(response, "output_text", "") or "",
                tool_calls=tuple(calls),
                response_id=getattr(response, "id", None),
            )
        input_items.extend(response.output)
        for item in function_calls:
            arguments = json.loads(getattr(item, "arguments", "{}") or "{}")
            result = registry.execute(item.name, arguments)
            calls.append({"name": item.name, "arguments": arguments})
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    raise RuntimeError(f"Tool-calling loop exceeded {max_rounds} rounds.")
