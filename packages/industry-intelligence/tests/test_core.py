from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from industry_intelligence.chunking import split_markdown
from industry_intelligence.config import IntelligenceSettings
from industry_intelligence.domain_tools import DomainToolRegistry
from industry_intelligence.embeddings import HashEmbeddingProvider
from industry_intelligence.openai_agent import run_tool_calling_query
from industry_intelligence.rag import HybridRetriever, KnowledgeIndexer
from industry_intelligence.vector_store import SQLiteVectorStore


def enabled_settings(repo_root: Path, **overrides) -> IntelligenceSettings:
    values = {
        "repo_root": repo_root,
        "enabled": True,
        "rag_enabled": True,
        "tool_calling_enabled": False,
        "langgraph_enabled": False,
        "mcp_enabled": False,
        "vector_backend": "sqlite",
        "embedding_provider": "hash",
        "embedding_model": "",
        "openai_model": "",
    }
    values.update(overrides)
    return IntelligenceSettings(**values)


def test_features_are_disabled_by_default(monkeypatch, tmp_path):
    for name in (
        "INDUSTRY_INTELLIGENCE_ENABLED",
        "INDUSTRY_RAG_ENABLED",
        "INDUSTRY_TOOL_CALLING_ENABLED",
        "INDUSTRY_LANGGRAPH_ENABLED",
        "INDUSTRY_MCP_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = IntelligenceSettings(repo_root=tmp_path)
    assert not settings.enabled
    with pytest.raises(RuntimeError, match="disabled"):
        settings.require("rag")


def test_hash_embeddings_are_deterministic():
    provider = HashEmbeddingProvider(dimensions=32)
    first = provider.embed_query("碳酸锂 净出口")
    assert first == provider.embed_query("碳酸锂 净出口")
    assert pytest.approx(sum(value * value for value in first), rel=1e-6) == 1.0


def test_index_search_is_read_only_and_returns_sources(tmp_path):
    rules = tmp_path / "pipeline" / "rules"
    rules.mkdir(parents=True)
    source = rules / "net_export_rules.md"
    source.write_text("# 碳酸锂净出口规则\n\n净出口等于出口量减去进口量。", encoding="utf-8")
    before = source.read_bytes()
    settings = enabled_settings(tmp_path)
    store = SQLiteVectorStore(settings.sqlite_path)
    embeddings = HashEmbeddingProvider()
    summary = KnowledgeIndexer(settings, store, embeddings).index()
    hits = HybridRetriever(store, embeddings).search("净出口计算", industry="lithium")
    assert summary == {"documents": 1, "chunks": 1}
    assert hits and hits[0].source_path == "pipeline/rules/net_export_rules.md"
    assert source.read_bytes() == before


def test_splitter_fallback_has_stable_ids(tmp_path):
    path = tmp_path / "docs" / "a.md"
    path.parent.mkdir()
    path.write_text("# 标题\n\n第一段。\n\n第二段。", encoding="utf-8")
    first = split_markdown(path, tmp_path, prefer_langchain=False)
    second = split_markdown(path, tmp_path, prefer_langchain=False)
    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]


class FakeStore:
    def __init__(self):
        self.audit = []

    def list_documents(self, *, filters=None):
        return [{"source_path": "pipeline/rules/example.md", "metadata": filters or {}}]

    def record_tool_call(self, name, arguments, status):
        self.audit.append((name, arguments, status))


class FakeRetriever:
    def search(self, query, **kwargs):
        return []


def test_registry_exposes_only_allowlisted_read_only_tools(tmp_path):
    store = FakeStore()
    registry = DomainToolRegistry(enabled_settings(tmp_path), FakeRetriever(), store)
    assert registry.names() == [
        "get_indicator_catalog",
        "get_pipeline_run_status",
        "list_rule_documents",
        "search_industry_knowledge",
    ]
    result = registry.execute("list_rule_documents", {"industry": "tin"})
    assert result["documents"]
    assert store.audit[-1][2] == "SUCCESS"
    with pytest.raises(ValueError, match="disallowed"):
        registry.execute("run_shell", {})


class FakeResponses:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            item = SimpleNamespace(
                type="function_call",
                name="list_rule_documents",
                arguments=json.dumps({"industry": "tin"}),
                call_id="call-1",
            )
            return SimpleNamespace(output=[item], output_text="", id="response-1")
        return SimpleNamespace(output=[], output_text="完成", id="response-2")


def test_function_calling_loop_executes_registry(tmp_path):
    settings = enabled_settings(tmp_path, tool_calling_enabled=True, openai_model="test-model")
    registry = DomainToolRegistry(settings, FakeRetriever(), FakeStore())
    client = SimpleNamespace(responses=FakeResponses())
    result = run_tool_calling_query("列出锡规则", settings, registry, client=client)
    assert result.text == "完成"
    assert result.tool_calls[0]["name"] == "list_rule_documents"
