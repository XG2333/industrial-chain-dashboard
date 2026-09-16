from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Protocol, Sequence

from .models import KnowledgeChunk, SearchHit


class VectorStore(Protocol):
    def upsert(self, chunks: Sequence[KnowledgeChunk], embeddings: Sequence[Sequence[float]]) -> None: ...

    def search(
        self,
        query: str,
        query_embedding: Sequence[float],
        *,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[SearchHit]: ...

    def list_documents(self, *, filters: dict[str, str] | None = None) -> list[dict[str, Any]]: ...


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text.lower()))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _matches(metadata: dict[str, Any], filters: dict[str, str] | None) -> bool:
    if not filters:
        return True
    return all(not value or str(metadata.get(key, "")) == str(value) for key, value in filters.items())


class SQLiteVectorStore:
    """Small, local hybrid store backed by SQLite.

    Dense vectors are stored as JSON and ranked in Python. This backend is
    designed for the repository's rule/document corpus, not large production
    datasets. Chroma can be selected when a dedicated vector index is needed.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
                    source_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_document
                    ON knowledge_chunks(document_id, chunk_index);
                CREATE TABLE IF NOT EXISTS intelligence_tool_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def upsert(self, chunks: Sequence[KnowledgeChunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")
        grouped: dict[str, list[tuple[KnowledgeChunk, Sequence[float]]]] = {}
        for chunk, embedding in zip(chunks, embeddings):
            grouped.setdefault(chunk.document_id, []).append((chunk, embedding))
        with self._connect() as connection:
            for document_id, rows in grouped.items():
                first = rows[0][0]
                connection.execute("DELETE FROM knowledge_documents WHERE document_id = ?", (document_id,))
                connection.execute(
                    "INSERT INTO knowledge_documents(document_id, source_path, title, metadata_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        document_id,
                        first.source_path,
                        first.title,
                        json.dumps(first.metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )
                connection.executemany(
                    "INSERT INTO knowledge_chunks(chunk_id, document_id, source_path, title, content, "
                    "chunk_index, metadata_json, embedding_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            chunk.chunk_id,
                            chunk.document_id,
                            chunk.source_path,
                            chunk.title,
                            chunk.content,
                            chunk.chunk_index,
                            json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True),
                            json.dumps(list(embedding)),
                        )
                        for chunk, embedding in rows
                    ],
                )

    def search(
        self,
        query: str,
        query_embedding: Sequence[float],
        *,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[SearchHit]:
        query_tokens = _tokens(query)
        scored: list[SearchHit] = []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT chunk_id, source_path, title, content, metadata_json, embedding_json "
                "FROM knowledge_chunks"
            ).fetchall()
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            if not _matches(metadata, filters):
                continue
            content_tokens = _tokens(row["content"])
            overlap = len(query_tokens & content_tokens) / max(1, len(query_tokens))
            dense = (_cosine(query_embedding, json.loads(row["embedding_json"])) + 1.0) / 2.0
            score = 0.65 * dense + 0.35 * overlap
            scored.append(
                SearchHit(
                    chunk_id=row["chunk_id"],
                    source_path=row["source_path"],
                    title=row["title"],
                    content=row["content"],
                    score=score,
                    metadata=metadata,
                )
            )
        return sorted(scored, key=lambda item: (-item.score, item.source_path, item.chunk_id))[:limit]

    def list_documents(self, *, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT document_id, source_path, title, metadata_json FROM knowledge_documents "
                "ORDER BY source_path"
            ).fetchall()
        result = []
        for row in rows:
            metadata = json.loads(row["metadata_json"])
            if _matches(metadata, filters):
                result.append(
                    {
                        "document_id": row["document_id"],
                        "source_path": row["source_path"],
                        "title": row["title"],
                        "metadata": metadata,
                    }
                )
        return result

    def record_tool_call(self, tool_name: str, arguments: dict[str, Any], status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO intelligence_tool_audit(tool_name, arguments_json, status) VALUES (?, ?, ?)",
                (tool_name, json.dumps(arguments, ensure_ascii=False, sort_keys=True), status),
            )


class ChromaVectorStore:
    def __init__(self, path: Path, collection_name: str = "industry_knowledge") -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("Install industry-intelligence[rag] to use Chroma.") from exc
        Path(path).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    @staticmethod
    def _flat_metadata(chunk: KnowledgeChunk) -> dict[str, str | int | float | bool]:
        metadata: dict[str, str | int | float | bool] = {
            "document_id": chunk.document_id,
            "source_path": chunk.source_path,
            "title": chunk.title,
            "chunk_index": chunk.chunk_index,
        }
        for key, value in chunk.metadata.items():
            if isinstance(value, (str, int, float, bool)):
                metadata[key] = value
        return metadata

    def upsert(self, chunks: Sequence[KnowledgeChunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")
        if not chunks:
            return
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=[chunk.content for chunk in chunks],
            embeddings=[list(vector) for vector in embeddings],
            metadatas=[self._flat_metadata(chunk) for chunk in chunks],
        )

    @staticmethod
    def _where(filters: dict[str, str] | None):
        pairs = [{key: value} for key, value in (filters or {}).items() if value]
        if not pairs:
            return None
        return pairs[0] if len(pairs) == 1 else {"$and": pairs}

    def search(
        self,
        query: str,
        query_embedding: Sequence[float],
        *,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[SearchHit]:
        result = self.collection.query(
            query_embeddings=[list(query_embedding)],
            n_results=limit,
            where=self._where(filters),
            include=["documents", "metadatas", "distances"],
        )
        hits: list[SearchHit] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for chunk_id, content, metadata, distance in zip(ids, documents, metadatas, distances):
            metadata = dict(metadata or {})
            hits.append(
                SearchHit(
                    chunk_id=chunk_id,
                    source_path=str(metadata.pop("source_path", "")),
                    title=str(metadata.pop("title", "")),
                    content=content or "",
                    score=1.0 / (1.0 + max(0.0, float(distance))),
                    metadata=metadata,
                )
            )
        return hits

    def list_documents(self, *, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        result = self.collection.get(where=self._where(filters), include=["metadatas"])
        documents: dict[str, dict[str, Any]] = {}
        for metadata in result.get("metadatas") or []:
            metadata = dict(metadata or {})
            document_id = str(metadata.pop("document_id", ""))
            if not document_id:
                continue
            documents[document_id] = {
                "document_id": document_id,
                "source_path": metadata.pop("source_path", ""),
                "title": metadata.pop("title", ""),
                "metadata": metadata,
            }
        return sorted(documents.values(), key=lambda item: str(item["source_path"]))


def build_vector_store(backend: str, *, sqlite_path: Path, chroma_path: Path) -> VectorStore:
    if backend == "sqlite":
        return SQLiteVectorStore(sqlite_path)
    if backend == "chroma":
        return ChromaVectorStore(chroma_path)
    raise ValueError(f"Unsupported vector backend: {backend}")
