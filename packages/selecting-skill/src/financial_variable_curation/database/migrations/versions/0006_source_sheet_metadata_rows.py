from __future__ import annotations

from sqlalchemy import Connection, text


def _column_names(connection: Connection, table: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA table_info({table})")).all()
    return {str(row[1]) for row in rows}


def upgrade(connection: Connection) -> None:
    if "metadata_row_count" not in _column_names(connection, "source_sheets"):
        connection.execute(
            text(
                "ALTER TABLE source_sheets "
                "ADD COLUMN metadata_row_count INTEGER NOT NULL DEFAULT 1"
            )
        )


def downgrade(connection: Connection) -> None:
    if "metadata_row_count" in _column_names(connection, "source_sheets"):
        connection.execute(text("ALTER TABLE source_sheets DROP COLUMN metadata_row_count"))
