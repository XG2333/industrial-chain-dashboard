from __future__ import annotations

from .config import IntelligenceSettings
from .domain_tools import DomainToolRegistry
from .rag import build_rag


def create_server(settings: IntelligenceSettings | None = None):
    settings = settings or IntelligenceSettings()
    settings.require("mcp")
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("Install industry-intelligence[mcp] to run the MCP server.") from exc

    _, retriever, store = build_rag(settings)
    registry = DomainToolRegistry(settings, retriever, store)
    server = MCPServer("Industry Chain Intelligence")

    @server.tool()
    def search_industry_knowledge(query: str, industry: str = "", limit: int = 5) -> dict:
        """Search approved business rules and project documentation."""
        return registry.execute(
            "search_industry_knowledge",
            {"query": query, "industry": industry, "limit": limit},
        )

    @server.tool()
    def list_rule_documents(industry: str = "") -> dict:
        """List indexed rule documents for an optional industry filter."""
        return registry.execute("list_rule_documents", {"industry": industry})

    @server.tool()
    def get_indicator_catalog(industry: str, sector: str = "", limit: int = 50) -> dict:
        """Read the catalog sheet of a processed workbook without modifying it."""
        return registry.execute(
            "get_indicator_catalog",
            {"industry": industry, "sector": sector, "limit": limit},
        )

    @server.tool()
    def get_pipeline_run_status(run_id: str = "latest") -> dict:
        """Read a workflow run summary without changing runtime state."""
        return registry.execute("get_pipeline_run_status", {"run_id": run_id})

    @server.resource("industry://rules/{industry}")
    def industry_rules(industry: str) -> str:
        """JSON index of approved rule documents for one industry."""
        import json

        return json.dumps(
            registry.execute("list_rule_documents", {"industry": industry}),
            ensure_ascii=False,
        )

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
