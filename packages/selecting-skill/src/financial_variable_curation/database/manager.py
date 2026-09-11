from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from financial_variable_curation.database.settings import DatabaseSettings
from financial_variable_curation.database.unit_of_work import UnitOfWork


def _sqlite_datetime_adapter(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat(sep=" ")


sqlite3.register_adapter(datetime, _sqlite_datetime_adapter)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


class DatabaseManager:
    def __init__(self, settings: DatabaseSettings | None = None) -> None:
        self.settings = settings or DatabaseSettings.from_env()
        self.engine = self._create_engine(self.settings)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
            future=True,
        )

    def _create_engine(self, settings: DatabaseSettings) -> Engine:
        url = make_url(settings.database_url)
        engine_kwargs: dict[str, object] = {"echo": settings.echo}
        if url.drivername == "sqlite":
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if url.database in (None, "", ":memory:"):
                engine_kwargs["poolclass"] = StaticPool
            else:
                database_path = Path(url.database).expanduser()
                database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(settings.database_url, **engine_kwargs)
        if url.drivername == "sqlite":
            event.listen(engine, "connect", _enable_sqlite_foreign_keys)
        return engine

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def unit_of_work(self) -> Iterator[UnitOfWork]:
        session = self.session_factory()
        try:
            session.begin()
            yield UnitOfWork(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        self.engine.dispose()
