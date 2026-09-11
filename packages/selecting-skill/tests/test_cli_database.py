from __future__ import annotations

import json
from pathlib import Path

from financial_variable_curation.cli import main
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.settings import DatabaseSettings
from financial_variable_curation.database.services import RunQueryService


def _first_run_dir(artifacts: Path) -> Path:
    return next(artifacts.iterdir())


def _run_id_from_artifacts(run_dir: Path) -> str:
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    return request["run_id"]


def test_inspect_cli_with_database_persists(
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "inspect.db"
    code = main(
        [
            "inspect",
            "--input",
            str(sample_workbook),
            "--artifacts-dir",
            str(artifacts),
            "--database",
            str(db_path),
            "--persist",
        ]
    )
    assert code == 0
    run_dir = _first_run_dir(artifacts)
    run_id = _run_id_from_artifacts(run_dir)
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        summary = RunQueryService(manager).get_run_summary(run_id)
        assert summary.run.status == "COMPLETED"
        assert summary.file_count == 1
        assert summary.variable_count > 0
    finally:
        manager.close()


def test_inspect_database_flag_alone_persists(
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "inspect-alone.db"
    code = main(
        [
            "inspect",
            "--input",
            str(sample_workbook),
            "--artifacts-dir",
            str(artifacts),
            "--database",
            str(db_path),
        ]
    )
    assert code == 0
    assert db_path.exists()


def test_inspect_persist_without_database_returns_usage_error(
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    code = main(
        [
            "inspect",
            "--input",
            str(sample_workbook),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--persist",
        ]
    )
    assert code == 2


def test_persist_inspection_cli_reads_existing_artifacts(
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    assert (
        main(
            [
                "inspect",
                "--input",
                str(sample_workbook),
                "--artifacts-dir",
                str(artifacts),
            ]
        )
        == 0
    )
    run_dir = _first_run_dir(artifacts)
    run_id = _run_id_from_artifacts(run_dir)
    db_path = tmp_path / "persist-existing.db"
    code = main(
        [
            "persist-inspection",
            "--artifacts",
            str(run_dir),
            "--database",
            str(db_path),
        ]
    )
    assert code == 0
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        summary = RunQueryService(manager).get_run_summary(run_id)
        assert summary.run.status == "COMPLETED"
        assert summary.variable_count > 0
    finally:
        manager.close()


def test_show_run_cli_outputs_run_counts(
    sample_workbook: Path,
    tmp_path: Path,
    capsys,
) -> None:
    artifacts = tmp_path / "artifacts"
    db_path = tmp_path / "show.db"
    assert (
        main(
            [
                "inspect",
                "--input",
                str(sample_workbook),
                "--artifacts-dir",
                str(artifacts),
                "--database",
                str(db_path),
            ]
        )
        == 0
    )
    run_id = _run_id_from_artifacts(_first_run_dir(artifacts))
    capsys.readouterr()
    code = main(["show-run", "--run-id", run_id, "--database", str(db_path)])
    assert code == 0
    output = capsys.readouterr().out
    assert "Status: COMPLETED" in output
    assert "Variables:" in output
    assert "DB records:" in output


def test_db_migration_cli_upgrade_current_and_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "migrate.db"
    assert main(["db-upgrade", "--database", str(db_path)]) == 0
    assert main(["db-current", "--database", str(db_path)]) == 0
    assert main(["db-downgrade", "--database", str(db_path), "--revision", "base"]) == 0
    assert main(["db-current", "--database", str(db_path)]) == 0
