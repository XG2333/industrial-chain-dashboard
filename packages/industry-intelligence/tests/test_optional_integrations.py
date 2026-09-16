from __future__ import annotations

from pathlib import Path

import pytest

from industry_intelligence.config import IntelligenceSettings
from industry_intelligence.domain_tools import DomainToolRegistry
from industry_intelligence.embeddings import HashEmbeddingProvider
from industry_intelligence.graph import build_research_graph
from industry_intelligence.mcp_server import create_server
from industry_intelligence.models import KnowledgeChunk
from industry_intelligence.rag import HybridRetriever
from industry_intelligence.vector_store import ChromaVectorStore, SQLiteVectorStore
from industry_intelligence.chunking import split_markdown


def settings(tmp_path: Path) -> IntelligenceSettings:
    return IntelligenceSettings(
        repo_root=tmp_path,
        enabled=True,
        rag_enabled=True,
        tool_calling_enabled=True,
        langgraph_enabled=True,
        mcp_enabled=True,
        vector_backend="sqlite",
        embedding_provider="hash",
        embedding_model="",
        openai_model="test-model",
    )


def seeded(tmp_path: Path):
    store = SQLiteVectorStore(tmp_path / "runtime" / "intelligence" / "knowledge.sqlite3")
    embeddings = HashEmbeddingProvider()
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_path="pipeline/rules/example.md",
        title="Example",
        content="净出口等于出口量减去进口量。",
        chunk_index=0,
        metadata={"industry": "lithium", "document_type": "rule"},
    )
    store.upsert([chunk], embeddings.embed_documents([chunk.content]))
    retriever = HybridRetriever(store, embeddings)
    return store, retriever


def test_langgraph_sidecar_runs_without_touching_pipeline(tmp_path):
    pytest.importorskip("langgraph")
    configured = settings(tmp_path)
    store, retriever = seeded(tmp_path)
    registry = DomainToolRegistry(configured, retriever, store)
    graph = build_research_graph(configured, retriever, registry)
    result = graph.invoke(
        {
            "query": "净出口如何计算",
            "industry": "lithium",
            "requested_tools": [],
        }
    )
    assert result["retrieved_context"]
    assert "pipeline/rules/example.md" in result["answer"]


def test_mcp_server_can_be_constructed(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    configured = settings(tmp_path)
    monkeypatch.setenv("INDUSTRY_INTELLIGENCE_RUNTIME_DIR", str(tmp_path / "runtime" / "mcp"))
    server = create_server(configured)
    assert server is not None


def test_chroma_backend_round_trip(tmp_path):
    pytest.importorskip("chromadb")
    embeddings = HashEmbeddingProvider()
    store = ChromaVectorStore(tmp_path / "chroma")
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_path="docs/example.md",
        title="Example",
        content="库存下降意味着去库。",
        chunk_index=0,
        metadata={"industry": "tin", "document_type": "documentation"},
    )
    store.upsert([chunk], embeddings.embed_documents([chunk.content]))
    hits = store.search("库存去库", embeddings.embed_query("库存去库"), limit=1)
    assert hits and hits[0].source_path == "docs/example.md"


def test_langchain_splitter_path_is_optional(tmp_path):
    pytest.importorskip("langchain_text_splitters")
    path = tmp_path / "example.md"
    path.write_text("# 规则\n\n" + ("碳酸锂净出口计算规则。" * 40), encoding="utf-8")
    chunks = split_markdown(
        path,
        tmp_path,
        chunk_size=120,
        overlap=20,
        prefer_langchain=True,
    )
    assert chunks
    assert all(chunk.content for chunk in chunks)
