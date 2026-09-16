from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .chunking import split_markdown
from .config import IntelligenceSettings
from .embeddings import EmbeddingProvider, build_embedding_provider
from .models import SearchHit
from .vector_store import VectorStore, build_vector_store


class KnowledgeIndexer:
    def __init__(
        self,
        settings: IntelligenceSettings,
        store: VectorStore,
        embeddings: EmbeddingProvider,
    ) -> None:
        self.settings = settings
        self.store = store
        self.embeddings = embeddings

    def discover(self) -> list[Path]:
        files: list[Path] = []
        for root in self.settings.knowledge_roots:
            if not root.exists():
                continue
            files.extend(path for path in root.rglob("*") if path.suffix.lower() in {".md", ".txt"})
        return sorted(set(path.resolve() for path in files))

    def index(self, paths: Iterable[Path] | None = None) -> dict[str, int]:
        self.settings.require("rag")
        document_count = 0
        chunk_count = 0
        for path in paths or self.discover():
            resolved = Path(path).resolve()
            resolved.relative_to(self.settings.repo_root.resolve())
            chunks = split_markdown(resolved, self.settings.repo_root)
            if not chunks:
                continue
            vectors = self.embeddings.embed_documents([chunk.content for chunk in chunks])
            self.store.upsert(chunks, vectors)
            document_count += 1
            chunk_count += len(chunks)
        return {"documents": document_count, "chunks": chunk_count}


class HybridRetriever:
    def __init__(self, store: VectorStore, embeddings: EmbeddingProvider) -> None:
        self.store = store
        self.embeddings = embeddings

    def search(
        self,
        query: str,
        *,
        industry: str = "",
        document_type: str = "",
        limit: int = 5,
    ) -> list[SearchHit]:
        cleaned = query.strip()
        if not cleaned:
            raise ValueError("Query must not be empty.")
        bounded_limit = max(1, min(int(limit), 20))
        filters = {
            key: value
            for key, value in {"industry": industry, "document_type": document_type}.items()
            if value
        }
        return self.store.search(
            cleaned,
            self.embeddings.embed_query(cleaned),
            limit=bounded_limit,
            filters=filters,
        )


def build_rag(settings: IntelligenceSettings) -> tuple[KnowledgeIndexer, HybridRetriever, VectorStore]:
    store = build_vector_store(
        settings.vector_backend,
        sqlite_path=settings.sqlite_path,
        chroma_path=settings.chroma_path,
    )
    embeddings = build_embedding_provider(settings.embedding_provider, settings.embedding_model)
    return (
        KnowledgeIndexer(settings, store, embeddings),
        HybridRetriever(store, embeddings),
        store,
    )
