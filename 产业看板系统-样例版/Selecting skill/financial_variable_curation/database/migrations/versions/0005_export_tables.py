from __future__ import annotations

from sqlalchemy import Connection, text

from financial_variable_curation.database.base import Base
import financial_variable_curation.database.models  # noqa: F401


def upgrade(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)


def downgrade(connection: Connection) -> None:
    connection.execute(text("DROP TABLE IF EXISTS exported_variables"))
    connection.execute(text("DROP TABLE IF EXISTS export_runs"))
