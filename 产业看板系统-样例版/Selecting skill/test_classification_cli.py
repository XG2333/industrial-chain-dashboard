from __future__ import annotations

from pathlib import Path

from financial_variable_curation.cli import main
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.migrations.runner import MigrationRunner
from financial_variable_curation.database.repositories import (
    LlmCallRepository,
    VariableClassificationRepository,
)
from financial_variable_curation.database.services import InspectionPersistenceService
from financial_variable_curation.database.settings import DatabaseSettings
from financial_variable_curation.models.artifacts import RequestRecord
from financial_variable_curation.pipeline.inspect import run_inspection


def _persist_for_cli(db_path: Path, sample_workbook: Path, run_id: str) -> None:
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        MigrationRunner(manager.engine).upgrade()
        result = run_inspection(sample_workbook, run_id=run_id)
        InspectionPersistenceService(manager).persist(
            result,
            request_record=RequestRecord(
                run_id=run_id,
                input_path=str(sample_workbook),
                file_hash=result.workbook_profile.file_hash,
                cli_args={},
            ),
            artifacts_dir=Path("artifacts"),
            run_id=run_id,
        )
    finally:
        manager.close()


def test_classify_cli_mock_limit(sample_workbook: Path, tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "classify.db"
    _persist_for_cli(db_path, sample_workbook, "run-cli-mock")
    code = main(
        [
            "classify",
            "--run-id",
            "run-cli-mock",
            "--database",
            str(db_path),
            "--provider",
            "mock",
            "--limit",
            "2",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Variables selected: 2" in output
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        with manager.session_scope() as session:
            assert VariableClassificationRepository(session).count_for_run("run-cli-mock") == 2
    finally:
        manager.close()


def test_classify_cli_dry_run_creates_no_llm_calls(
    sample_workbook: Path,
    tmp_path: Path,
    capsys,
) -> None:
    db_path = tmp_path / "dry.db"
    _persist_for_cli(db_path, sample_workbook, "run-cli-dry")
    code = main(
        [
            "classify",
            "--run-id",
            "run-cli-dry",
            "--database",
            str(db_path),
            "--provider",
            "mock",
            "--limit",
            "3",
            "--dry-run",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Dry run: true" in output
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        with manager.session_scope() as session:
            assert LlmCallRepository(session).count() == 0
            assert VariableClassificationRepository(session).count_for_run("run-cli-dry") == 0
    finally:
        manager.close()


def test_classify_cli_openai_without_real_switch_fails(
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "disabled.db"
    _persist_for_cli(db_path, sample_workbook, "run-cli-disabled")
    code = main(
        [
            "classify",
            "--run-id",
            "run-cli-disabled",
            "--database",
            str(db_path),
            "--provider",
            "openai",
            "--limit",
            "1",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 1


def test_classify_cli_openai_dry_run_does_not_call_network(
    sample_workbook: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "openai-dry.db"
    _persist_for_cli(db_path, sample_workbook, "run-cli-openai-dry")
    monkeypatch.setenv("REAL_LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-dry-run")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    code = main(
        [
            "classify",
            "--run-id",
            "run-cli-openai-dry",
            "--database",
            str(db_path),
            "--provider",
            "openai",
            "--limit",
            "2",
            "--dry-run",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        with manager.session_scope() as session:
            assert LlmCallRepository(session).count() == 0
    finally:
        manager.close()
