from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.migrations.runner import MigrationRunner
from financial_variable_curation.database.settings import DatabaseSettings


@pytest.fixture
def sample_workbook(tmp_path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "MarketData"
    headers = [
        "date",
        "close_price",
        "close_price_2",
        "volume",
        "revenue",
        "constant_col",
        "empty_col",
        "high_missing",
        "note",
    ]
    sheet.append(headers)
    from datetime import date, timedelta

    start = date(2024, 1, 1)
    for index in range(25):
        day = start + timedelta(days=index)
        sheet.append(
            [
                day,
                100 + index,
                99 + index,
                1000 + index * 10,
                (index + 1) * 1000,
                7,
                None,
                123 if index == 0 else (456 if index == 24 else None),
                f"note-{index}" if index < 3 else None,
            ]
        )
    path = tmp_path / "sample.xlsx"
    workbook.save(path)
    return path


@pytest.fixture
def sample_rules_text(tmp_path: Path) -> Path:
    path = tmp_path / "selection_rules.txt"
    path.write_text(
        "\n".join(
            [
                "规则集名称: cross_industry_rules",
                "删除全空列",
                "删除恒定列",
                "删除缺失率高于 90% 的变量",
                "缺失率高于 50% 的变量进入复核",
                "同类指标无法确认经济含义时进入复核",
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def db_manager(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(
        DatabaseSettings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    )
    MigrationRunner(manager.engine).upgrade()
    yield manager
    manager.close()
