from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _repo_root() -> Path:
    configured = os.getenv("INDUSTRY_REPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class IntelligenceSettings:
    """Configuration for the optional intelligence layer.

    Every feature flag defaults to ``False`` so installing the package alone
    cannot alter the deterministic pipeline or dashboard responses.
    """

    repo_root: Path = field(default_factory=_repo_root)
    enabled: bool = field(default_factory=lambda: _env_bool("INDUSTRY_INTELLIGENCE_ENABLED"))
    rag_enabled: bool = field(default_factory=lambda: _env_bool("INDUSTRY_RAG_ENABLED"))
    tool_calling_enabled: bool = field(
        default_factory=lambda: _env_bool("INDUSTRY_TOOL_CALLING_ENABLED")
    )
    langgraph_enabled: bool = field(default_factory=lambda: _env_bool("INDUSTRY_LANGGRAPH_ENABLED"))
    mcp_enabled: bool = field(default_factory=lambda: _env_bool("INDUSTRY_MCP_ENABLED"))
    vector_backend: str = field(
        default_factory=lambda: os.getenv("INDUSTRY_VECTOR_BACKEND", "sqlite").strip().lower()
    )
    embedding_provider: str = field(
        default_factory=lambda: os.getenv("INDUSTRY_EMBEDDING_PROVIDER", "hash").strip().lower()
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("INDUSTRY_EMBEDDING_MODEL", "").strip()
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("INDUSTRY_OPENAI_MODEL", "").strip()
    )

    @property
    def runtime_dir(self) -> Path:
        configured = os.getenv("INDUSTRY_INTELLIGENCE_RUNTIME_DIR")
        return (
            Path(configured).expanduser().resolve()
            if configured
            else self.repo_root / "runtime" / "intelligence"
        )

    @property
    def sqlite_path(self) -> Path:
        return self.runtime_dir / "knowledge.sqlite3"

    @property
    def chroma_path(self) -> Path:
        return self.runtime_dir / "chroma"

    @property
    def knowledge_roots(self) -> tuple[Path, ...]:
        return (
            self.repo_root / "docs",
            self.repo_root / "pipeline" / "rules",
            self.repo_root / "pipeline" / "docs",
        )

    def require(self, feature: str) -> None:
        flag = {
            "rag": self.rag_enabled,
            "tool_calling": self.tool_calling_enabled,
            "langgraph": self.langgraph_enabled,
            "mcp": self.mcp_enabled,
        }.get(feature)
        if not self.enabled or flag is not True:
            raise RuntimeError(
                f"Optional feature '{feature}' is disabled. Enable INDUSTRY_INTELLIGENCE_ENABLED "
                f"and the matching feature flag explicitly."
            )
