from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect

from financial_variable_curation.database.exceptions import RepositoryError
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.migrations.runner import MigrationRunner
from financial_variable_curation.database.repositories import SourceSheetRepository
from financial_variable_curation.database.schemas import SourceSheetDTO
from financial_variable_curation.database.settings import DatabaseSettings
from financial_variable_curation.database.types import utcnow


def test_migration_upgrades_empty_database_and_can_repeat(tmp_path: Path) -> None:
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{tmp_path / 'fresh.db'}"))
    try:
        runner = MigrationRunner(manager.engine)
        assert runner.get_current_version() is None
        assert runner.upgrade() == ["0001", "0002", "0003", "0004", "0005", "0006"]
        assert runner.get_current_version() == "0006"
        assert runner.upgrade() == []
    finally:
        manager.close()


def test_initial_schema_contains_core_and_future_tables(db_manager: DatabaseManager) -> None:
    tables = set(sa_inspect(db_manager.engine).get_table_names())
    required = {
        "pipeline_runs",
        "pipeline_steps",
        "source_files",
        "source_sheets",
        "variables",
        "variable_quality",
        "run_files",
        "run_variables",
        "audit_events",
        "llm_calls",
        "variable_classifications",
        "classification_cache",
        "rule_sets",
        "selection_runs",
        "variable_selection_results",
        "review_items",
        "rules",
        "rule_conflicts",
        "rule_parse_runs",
        "rule_parse_cache",
        "export_runs",
        "exported_variables",
        "schema_migrations",
    }
    assert required.issubset(tables)


def test_migration_downgrade_to_base_removes_schema(tmp_path: Path) -> None:
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{tmp_path / 'downgrade.db'}"))
    try:
        runner = MigrationRunner(manager.engine)
        assert runner.upgrade() == ["0001", "0002", "0003", "0004", "0005", "0006"]
        assert runner.downgrade("base") == ["0006", "0005", "0004", "0003", "0002", "0001"]
        assert runner.get_current_version() is None
        tables = set(sa_inspect(manager.engine).get_table_names())
        assert "pipeline_runs" not in tables
    finally:
        manager.close()


def test_sqlite_foreign_keys_are_enabled(db_manager: DatabaseManager) -> None:
    with db_manager.engine.connect() as connection:
        enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert enabled == 1


def test_invalid_foreign_key_is_converted_to_repository_error(db_manager: DatabaseManager) -> None:
    now = utcnow()
    sheet = SourceSheetDTO(
        sheet_id="sheet_missing",
        file_id="file_missing",
        sheet_name="Data",
        sheet_index=0,
        status="PROCESSED",
        review_reasons_json=[],
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(RepositoryError):
        with db_manager.unit_of_work() as uow:
            SourceSheetRepository(uow.session).bulk_upsert("file_missing", [sheet])
