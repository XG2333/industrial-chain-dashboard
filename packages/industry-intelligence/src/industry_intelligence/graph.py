from __future__ import annotations

from typing import Any, Callable, TypedDict

from .config import IntelligenceSettings
from .domain_tools import DomainToolRegistry
from .rag import HybridRetriever


class ResearchState(TypedDict, total=False):
    query: str
    industry: str
    requested_tools: list[dict[str, Any]]
    retrieved_context: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    answer: str


def build_research_graph(
    settings: IntelligenceSettings,
    retriever: HybridRetriever,
    registry: DomainToolRegistry,
    *,
    synthesizer: Callable[[ResearchState], str] | None = None,
):
    """Build a sidecar LangGraph; it is never inserted into the legacy pipeline."""

    settings.require("langgraph")
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("Install industry-intelligence[graph] to use LangGraph.") from exc

    def retrieve(state: ResearchState) -> dict[str, Any]:
        hits = retriever.search(
            state["query"],
            industry=state.get("industry", ""),
            limit=5,
        )
        return {"retrieved_context": [hit.as_dict() for hit in hits]}

    def run_tools(state: ResearchState) -> dict[str, Any]:
        results = []
        for request in state.get("requested_tools", []):
            name = str(request.get("name", ""))
            arguments = request.get("arguments") or {}
            results.append({"name": name, "result": registry.execute(name, arguments)})
        return {"tool_results": results}

    def synthesize(state: ResearchState) -> dict[str, str]:
        if synthesizer is not None:
            return {"answer": synthesizer(state)}
        sources = [item.get("source_path", "") for item in state.get("retrieved_context", [])]
        return {
            "answer": json_safe_summary(state.get("query", ""), sources, state.get("tool_results", []))
        }

    builder = StateGraph(ResearchState)
    builder.add_node("retrieve", retrieve)
    builder.add_node("run_tools", run_tools)
    builder.add_node("synthesize", synthesize)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "run_tools")
    builder.add_edge("run_tools", "synthesize")
    builder.add_edge("synthesize", END)
    return builder.compile()


def json_safe_summary(query: str, sources: list[str], tool_results: list[dict[str, Any]]) -> str:
    source_text = ", ".join(source for source in sources if source) or "none"
    return f"query={query}; sources={source_text}; tool_results={len(tool_results)}"
