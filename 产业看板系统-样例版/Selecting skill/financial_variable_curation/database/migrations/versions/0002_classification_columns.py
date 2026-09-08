from __future__ import annotations

from sqlalchemy import Connection, text


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
    _add_column(connection, "llm_calls", "batch_id", "VARCHAR(120)")
    _add_column(connection, "llm_calls", "taxonomy_version", "VARCHAR(80)")
    _add_column(connection, "llm_calls", "response_id", "VARCHAR(120)")
    _add_column(connection, "llm_calls", "total_tokens", "INTEGER")
    _add_column(connection, "llm_calls", "request_artifact_path", "TEXT")
    _add_column(connection, "llm_calls", "response_artifact_path", "TEXT")
    _add_column(connection, "llm_calls", "error_message", "TEXT")
    _add_column(connection, "llm_calls", "attempt_count", "INTEGER NOT NULL DEFAULT 1")
    _add_column(connection, "llm_calls", "completed_at", "DATETIME")

    _add_column(connection, "variable_classifications", "llm_call_id", "VARCHAR(80)")
    _add_column(connection, "variable_classifications", "batch_id", "VARCHAR(120)")
    _add_column(connection, "variable_classifications", "provider", "VARCHAR(80)")
    _add_column(connection, "variable_classifications", "model", "VARCHAR(120)")
    _add_column(connection, "variable_classifications", "prompt_version", "VARCHAR(80)")
    _add_column(connection, "variable_classifications", "taxonomy_version", "VARCHAR(80)")
    _add_column(connection, "variable_classifications", "schema_version", "VARCHAR(80)")
    _add_column(connection, "variable_classifications", "response_id", "VARCHAR(120)")
    _add_column(connection, "variable_classifications", "comparison_group_components_json", "TEXT")
    _add_column(
        connection,
        "variable_classifications",
        "review_reasons_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column(connection, "variable_classifications", "is_derived", "BOOLEAN NOT NULL DEFAULT 0")
    _add_column(connection, "variable_classifications", "parent_metric", "VARCHAR(255)")

    _add_column(connection, "classification_cache", "taxonomy_version", "VARCHAR(80)")
    _add_column(connection, "classification_cache", "schema_version", "VARCHAR(80)")
    _add_column(connection, "classification_cache", "input_hash", "VARCHAR(80)")
    _add_column(connection, "classification_cache", "request_artifact_path", "TEXT")
    _add_column(connection, "classification_cache", "response_artifact_path", "TEXT")
    connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_llm_calls_batch_id ON llm_calls (batch_id)")
    )


def downgrade(connection: Connection) -> None:
    connection.execute(text("DROP INDEX IF EXISTS ix_llm_calls_batch_id"))
    for column in (
        "batch_id",
        "taxonomy_version",
        "response_id",
        "total_tokens",
        "request_artifact_path",
        "response_artifact_path",
        "error_message",
        "attempt_count",
        "completed_at",
    ):
        _drop_column(connection, "llm_calls", column)
    for column in (
        "llm_call_id",
        "batch_id",
        "provider",
        "model",
        "prompt_version",
        "taxonomy_version",
        "schema_version",
        "response_id",
        "comparison_group_components_json",
        "review_reasons_json",
        "is_derived",
        "parent_metric",
    ):
        _drop_column(connection, "variable_classifications", column)
    for column in (
        "taxonomy_version",
        "schema_version",
        "input_hash",
        "request_artifact_path",
        "response_artifact_path",
    ):
        _drop_column(connection, "classification_cache", column)
