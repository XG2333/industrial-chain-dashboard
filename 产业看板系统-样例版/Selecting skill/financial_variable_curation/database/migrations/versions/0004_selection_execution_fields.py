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


def _drop_table_indexes(connection: Connection, table: str) -> None:
    rows = connection.execute(text(f"PRAGMA index_list({table})")).all()
    for row in rows:
        if str(row[1]).startswith("sqlite_autoindex"):
            continue
        connection.execute(text(f"DROP INDEX IF EXISTS {row[1]}"))


def upgrade(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)
    selection_run_columns = (
        ("classification_run_id", "VARCHAR(80)"),
        ("rule_set_version", "VARCHAR(40)"),
        ("compiled_hash", "VARCHAR(80)"),
        ("started_at", "DATETIME"),
        ("failed_at", "DATETIME"),
        ("total_variables", "INTEGER NOT NULL DEFAULT 0"),
        ("candidate_variables", "INTEGER NOT NULL DEFAULT 0"),
        ("selected_count", "INTEGER NOT NULL DEFAULT 0"),
        ("rejected_count", "INTEGER NOT NULL DEFAULT 0"),
        ("duplicate_count", "INTEGER NOT NULL DEFAULT 0"),
        ("needs_review_count", "INTEGER NOT NULL DEFAULT 0"),
        ("not_selected_count", "INTEGER NOT NULL DEFAULT 0"),
        ("error_type", "VARCHAR(160)"),
        ("error_message", "TEXT"),
        ("artifacts_path", "TEXT"),
        ("updated_at", "DATETIME"),
    )
    for column, definition in selection_run_columns:
        _add_column(connection, "selection_runs", column, definition)

    result_columns = (
        ("selection_result_id", "VARCHAR(80)"),
        ("final_status", "VARCHAR(40)"),
        ("category_rank", "INTEGER"),
        ("subcategory_rank", "INTEGER"),
        ("frequency_rank", "INTEGER"),
        ("source_rank", "INTEGER"),
        ("quality_rank", "INTEGER"),
        ("category_score", "FLOAT NOT NULL DEFAULT 0"),
        ("frequency_score", "FLOAT NOT NULL DEFAULT 0"),
        ("quality_score", "FLOAT NOT NULL DEFAULT 0"),
        ("source_score", "FLOAT NOT NULL DEFAULT 0"),
        ("recency_score", "FLOAT NOT NULL DEFAULT 0"),
        ("coverage_score", "FLOAT NOT NULL DEFAULT 0"),
        ("user_preference_score", "FLOAT NOT NULL DEFAULT 0"),
        ("redundancy_penalty", "FLOAT NOT NULL DEFAULT 0"),
        ("overall_rank", "INTEGER"),
        ("comparison_group_key", "VARCHAR(255)"),
        ("group_rank", "INTEGER"),
        ("primary_reason_code", "VARCHAR(120)"),
        ("primary_reason_text", "TEXT"),
        ("matched_rule_ids_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("execution_trace_path", "TEXT"),
        ("updated_at", "DATETIME"),
    )
    for column, definition in result_columns:
        _add_column(connection, "variable_selection_results", column, definition)
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_variable_selection_results_result_id "
            "ON variable_selection_results (selection_result_id)"
        )
    )


def downgrade(connection: Connection) -> None:
    _drop_table_indexes(connection, "selection_runs")
    _drop_table_indexes(connection, "variable_selection_results")
    connection.execute(text("DROP INDEX IF EXISTS uq_variable_selection_results_result_id"))
    connection.execute(text("DROP INDEX IF EXISTS ix_selection_runs_classification_run_id"))
    for column, _ in (
        ("classification_run_id", "VARCHAR(80)"),
        ("rule_set_version", "VARCHAR(40)"),
        ("compiled_hash", "VARCHAR(80)"),
        ("started_at", "DATETIME"),
        ("failed_at", "DATETIME"),
        ("total_variables", "INTEGER NOT NULL DEFAULT 0"),
        ("candidate_variables", "INTEGER NOT NULL DEFAULT 0"),
        ("selected_count", "INTEGER NOT NULL DEFAULT 0"),
        ("rejected_count", "INTEGER NOT NULL DEFAULT 0"),
        ("duplicate_count", "INTEGER NOT NULL DEFAULT 0"),
        ("needs_review_count", "INTEGER NOT NULL DEFAULT 0"),
        ("not_selected_count", "INTEGER NOT NULL DEFAULT 0"),
        ("error_type", "VARCHAR(160)"),
        ("error_message", "TEXT"),
        ("artifacts_path", "TEXT"),
        ("updated_at", "DATETIME"),
    ):
        _drop_column(connection, "selection_runs", column)
    for column, _ in (
        ("selection_result_id", "VARCHAR(80)"),
        ("final_status", "VARCHAR(40)"),
        ("category_rank", "INTEGER"),
        ("subcategory_rank", "INTEGER"),
        ("frequency_rank", "INTEGER"),
        ("source_rank", "INTEGER"),
        ("quality_rank", "INTEGER"),
        ("category_score", "FLOAT NOT NULL DEFAULT 0"),
        ("frequency_score", "FLOAT NOT NULL DEFAULT 0"),
        ("quality_score", "FLOAT NOT NULL DEFAULT 0"),
        ("source_score", "FLOAT NOT NULL DEFAULT 0"),
        ("recency_score", "FLOAT NOT NULL DEFAULT 0"),
        ("coverage_score", "FLOAT NOT NULL DEFAULT 0"),
        ("user_preference_score", "FLOAT NOT NULL DEFAULT 0"),
        ("redundancy_penalty", "FLOAT NOT NULL DEFAULT 0"),
        ("overall_rank", "INTEGER"),
        ("comparison_group_key", "VARCHAR(255)"),
        ("group_rank", "INTEGER"),
        ("primary_reason_code", "VARCHAR(120)"),
        ("primary_reason_text", "TEXT"),
        ("matched_rule_ids_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("execution_trace_path", "TEXT"),
        ("updated_at", "DATETIME"),
    ):
        if column == "selection_result_id":
            continue
        _drop_column(connection, "variable_selection_results", column)
