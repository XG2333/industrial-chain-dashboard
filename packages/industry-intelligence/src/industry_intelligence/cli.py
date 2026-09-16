from __future__ import annotations

import argparse
import json
from typing import Any

from .config import IntelligenceSettings
from .domain_tools import DomainToolRegistry
from .rag import build_rag


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optional industry intelligence sidecar.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Show feature flags and local runtime paths.")
    subparsers.add_parser("index", help="Index approved rule and documentation roots.")

    search = subparsers.add_parser("search", help="Search the local knowledge index.")
    search.add_argument("query")
    search.add_argument("--industry", choices=("", "lithium", "tin", "silicon"), default="")
    search.add_argument("--limit", type=int, default=5)

    subparsers.add_parser("tool-schemas", help="Print allow-listed Responses API function schemas.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = IntelligenceSettings()
    if args.command == "status":
        _print(
            {
                "enabled": settings.enabled,
                "rag_enabled": settings.rag_enabled,
                "tool_calling_enabled": settings.tool_calling_enabled,
                "langgraph_enabled": settings.langgraph_enabled,
                "mcp_enabled": settings.mcp_enabled,
                "vector_backend": settings.vector_backend,
                "embedding_provider": settings.embedding_provider,
                "runtime_dir": settings.runtime_dir,
                "legacy_pipeline_integration": "none",
            }
        )
        return 0

    indexer, retriever, store = build_rag(settings)
    if args.command == "index":
        _print(indexer.index())
        return 0
    if args.command == "search":
        settings.require("rag")
        _print(
            {
                "results": [
                    hit.as_dict()
                    for hit in retriever.search(
                        args.query,
                        industry=args.industry,
                        limit=args.limit,
                    )
                ]
            }
        )
        return 0
    if args.command == "tool-schemas":
        registry = DomainToolRegistry(settings, retriever, store)
        _print(registry.responses_schemas())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
