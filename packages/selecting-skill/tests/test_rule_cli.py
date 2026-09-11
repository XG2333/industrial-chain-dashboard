from __future__ import annotations

from pathlib import Path

from financial_variable_curation.cli import main
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import RuleSetRepository
from financial_variable_curation.database.settings import DatabaseSettings


RULES_TEXT = """价格 > 价差 > 库存 > 产量 > 进口 > 出口
缺失率超过40%的变量删除
同一指标只保留一个
最终最多保留30个变量
"""


def _write_rules(tmp_path: Path, text: str = RULES_TEXT) -> Path:
    path = tmp_path / "rules.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_rules_cli_mock_success(tmp_path: Path, capsys) -> None:
    rules = _write_rules(tmp_path)
    db_path = tmp_path / "rules.db"
    code = main(
        [
            "validate-rules",
            "--rules",
            str(rules),
            "--provider",
            "mock",
            "--database",
            str(db_path),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Rules parsed:" in output
    assert "Can compile: true" in output


def test_compile_rules_cli_mock_success(tmp_path: Path) -> None:
    rules = _write_rules(tmp_path)
    db_path = tmp_path / "compiled.db"
    code = main(
        [
            "compile-rules",
            "--rules",
            str(rules),
            "--name",
            "cli_rules",
            "--version",
            "1",
            "--provider",
            "mock",
            "--database",
            str(db_path),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        with manager.session_scope() as session:
            saved = RuleSetRepository(session).get_by_name_version("cli_rules", "1")
            assert saved is not None
            assert saved.status == "VALIDATED"
    finally:
        manager.close()


def test_compile_rules_cli_dry_run_does_not_persist(tmp_path: Path) -> None:
    rules = _write_rules(tmp_path)
    db_path = tmp_path / "dry.db"
    code = main(
        [
            "compile-rules",
            "--rules",
            str(rules),
            "--name",
            "dry_cli_rules",
            "--version",
            "1",
            "--provider",
            "mock",
            "--database",
            str(db_path),
            "--dry-run",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        with manager.session_scope() as session:
            assert RuleSetRepository(session).get_by_name_version("dry_cli_rules", "1") is None
    finally:
        manager.close()


def test_compile_rules_cli_activate_valid_rules(tmp_path: Path) -> None:
    rules = _write_rules(tmp_path)
    db_path = tmp_path / "active.db"
    code = main(
        [
            "compile-rules",
            "--rules",
            str(rules),
            "--name",
            "active_cli_rules",
            "--version",
            "1",
            "--provider",
            "mock",
            "--database",
            str(db_path),
            "--activate",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 0
    manager = DatabaseManager(DatabaseSettings(database_url=f"sqlite:///{db_path}"))
    try:
        with manager.session_scope() as session:
            saved = RuleSetRepository(session).get_by_name_version("active_cli_rules", "1")
            assert saved is not None
            assert saved.status == "ACTIVE"
    finally:
        manager.close()


def test_compile_rules_cli_activate_blocked_by_conflict(tmp_path: Path) -> None:
    rules = tmp_path / "conflict.txt"
    rules.write_text("价格 > 库存\n库存 > 价格\n", encoding="utf-8")
    db_path = tmp_path / "blocked.db"
    code = main(
        [
            "compile-rules",
            "--rules",
            str(rules),
            "--name",
            "blocked_cli_rules",
            "--version",
            "1",
            "--provider",
            "mock",
            "--database",
            str(db_path),
            "--activate",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ]
    )
    assert code == 1
