from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import KnowledgeChunk


def _document_metadata(relative_path: str, text: str) -> dict[str, str]:
    lowered = f"{relative_path}\n{text[:1200]}".lower()
    industry = ""
    for key, aliases in {
        "lithium": ("lithium", "锂", "碳酸锂"),
        "tin": ("tin", "锡"),
        "silicon": ("silicon", "硅"),
    }.items():
        if any(alias in lowered for alias in aliases):
            industry = key
            break
    kind = "rule" if "/rules/" in f"/{relative_path.replace('\\', '/')}" else "documentation"
    return {"industry": industry, "document_type": kind}


def _fallback_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
            continue
        start = 0
        step = max(1, chunk_size - overlap)
        while start < len(paragraph):
            chunks.append(paragraph[start : start + chunk_size])
            start += step
        current = ""
    if current:
        chunks.append(current)
    return chunks


def split_markdown(
    path: Path,
    repo_root: Path,
    *,
    chunk_size: int = 1200,
    overlap: int = 160,
    prefer_langchain: bool = True,
) -> list[KnowledgeChunk]:
    text = path.read_text(encoding="utf-8-sig")
    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    metadata = _document_metadata(relative, text)

    parts: list[str]
    if prefer_langchain:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                separators=["\n## ", "\n### ", "\n\n", "\n", "。", "；", " "],
            )
            parts = splitter.split_text(text)
        except ImportError:
            parts = _fallback_split(text, chunk_size, overlap)
    else:
        parts = _fallback_split(text, chunk_size, overlap)

    document_id = hashlib.sha256(relative.encode("utf-8")).hexdigest()
    chunks: list[KnowledgeChunk] = []
    for index, content in enumerate(parts):
        normalized = content.strip()
        if not normalized:
            continue
        chunk_id = hashlib.sha256(
            f"{relative}\0{index}\0{normalized}".encode("utf-8")
        ).hexdigest()
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                source_path=relative,
                title=title,
                content=normalized,
                chunk_index=index,
                metadata=dict(metadata),
            )
        )
    return chunks
