from __future__ import annotations

from sqlalchemy import Connection, text

from financial_variable_curation.database.base import Base
import financial_variable_curation.database.models  # noqa: F401


def _column_names(connection: Connection, table: str) -> set[str]:
    rows = connection.execute(text(f"PRAGMA table_info({table})")).all()
    return {str(row[1]) for row in rows}


def _add_column(connection: Connection, table: str, column: str, definition: str) -> None:
    if column not in _column_names(connection, table):
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def _drop_column(connection: Connection, table: str, column: str) -> None:
    if column in _column_names(connection, table):
        connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))


def upgrade(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)
    for column, definition in (
        ("source_file_name", "VARCHAR(255)"),
        ("source_language", "VARCHAR(40)"),
        ("provider", "VARCHAR(80)"),
        ("model", "VARCHAR(120)"),
        ("prompt_version", "VARCHAR(80)"),
        ("taxonomy_version", "VARCHAR(80)"),
        ("schema_version", "VARCHAR(80)"),
        ("compiled_hash", "VARCHAR(80)"),
        ("activated_at", "DATETIME"),
        ("deprecated_at", "DATETIME"),
    ):
        _add_column(connection, "rule_sets", column, definition)


def downgrade(connection: Connection) -> None:
    for column in (
        "source_file_name",
        "source_language",
        "provider",
        "model",
        "prompt_version",
        "taxonomy_version",
        "schema_version",
        "compiled_hash",
        "activated_at",
        "deprecated_at",
    ):
        _drop_column(connection, "rule_sets", column)
    for table in (
        "rule_conflicts",
        "rules",
        "rule_parse_cache",
        "rule_parse_runs",
    ):
        connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
