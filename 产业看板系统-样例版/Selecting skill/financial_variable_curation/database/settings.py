from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATABASE_URL = "sqlite:///data/financial_variable_curation.db"


def _normalize_database_url(database_url: str) -> str:
    if "://" in database_url:
        return database_url
    if database_url == ":memory:":
        return "sqlite:///:memory:"
    return "sqlite:///" + Path(database_url).expanduser().resolve().as_posix()


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str = DEFAULT_DATABASE_URL
    echo: bool = False

    @classmethod
    def from_env(cls, database_url: str | None = None) -> DatabaseSettings:
        url = _normalize_database_url(database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
        echo = os.getenv("DATABASE_ECHO", "false").strip().lower() in {"1", "true", "yes"}
        return cls(database_url=url, echo=echo)
