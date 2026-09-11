from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _import_server():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import server as server_module
    return server_module


def _write_workbook(path: Path, header: list[str], catalog_rows: list[list[object]]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "目录"
    ws.append(header)
    for row in catalog_rows:
        ws.append(row)
    data = wb.create_sheet("测试sheet")
    data.append(["测试指标", "元", "月度"])
    data.append(["", "", ""])
    data.append(["", "", ""])
    data.append(["2026-01-01", 1.0])
    wb.save(path)


OLD_HEADER = [
    "#",
    "Sheet Name",
    "Freq",
    "Col",
    "Indicator Name",
    "Unit",
    "板块",
    "大类",
    "子类",
    "数据性质",
    "置信度",
    "是否选中",
    "状态说明",
]

NEW_HEADER = [
    "#",
    "Sheet Name",
    "Freq",
    "Col",
    "Indicator Name",
    "Unit",
    "板块",
    "大类",
    "子类",
    "数据性质",
    "是否选中",
    "状态说明",
    "指标标签",
]


def _old_rows() -> list[list[object]]:
    return [
        ["月度 (1 sht 1 ind)", None, None, None, None, None, None, "其他", "其他", None, None, "否", None],
        ["测试sheet", None, "月度", None, None, None, "测试板块", "价格", "现货价格", None, None, "否", None],
        ["1", None, "月度", "1", "测试指标", "元", None, "价格", "现货价格", "水平值", "0.8", "是", "测试原因"],
    ]


def _new_rows() -> list[list[object]]:
    return [
        ["月度 (1 sht 1 ind)", None, None, None, None, None, None, "其他", "其他", None, "否", None, None],
        ["测试sheet", None, "月度", None, None, None, "测试板块", "价格", "现货价格", None, "否", None, None],
        ["1", None, "月度", "1", "测试指标", "元", None, "价格", "现货价格", "水平值", "是", "测试原因", '{"产品": "测试"}'],
    ]


def test_old_schema_reads(tmp_path):
    server = _import_server()
    path = tmp_path / "old.xlsx"
    _write_workbook(path, OLD_HEADER, _old_rows())

    charts, sectors = server._load_excel_workbook(path, "test")

    assert charts is not None
    assert len(charts) == 1
    chart = charts[0]
    assert chart["confidence"] == 0.8
    assert chart["selected"] is True
    assert chart["selection_reason"] == "测试原因"
    assert chart["tags"] == []


def test_new_workflow_schema_reads(tmp_path):
    server = _import_server()
    path = tmp_path / "new.xlsx"
    _write_workbook(path, NEW_HEADER, _new_rows())

    charts, sectors = server._load_excel_workbook(path, "test")

    assert charts is not None
    assert len(charts) == 1
    chart = charts[0]
    assert chart["confidence"] is None
    assert chart["selected"] is True
    assert chart["selection_reason"] == "测试原因"
    assert chart["tags"] == [{"category": "产品", "value": "测试"}]


def test_selected_value_is_not_parsed_as_confidence(tmp_path):
    server = _import_server()
    path = tmp_path / "selected.xlsx"
    _write_workbook(path, NEW_HEADER, _new_rows())

    charts, _ = server._load_excel_workbook(path, "test")

    assert charts is not None
    assert not isinstance(charts[0]["confidence"], str)
    assert charts[0]["confidence"] is None


def test_missing_required_column_reports_schema_error(tmp_path, caplog):
    server = _import_server()
    path = tmp_path / "missing.xlsx"
    header = [name for name in NEW_HEADER if name != "Col"]
    rows = [[value for idx, value in enumerate(row) if idx != 3] for row in _new_rows()]
    _write_workbook(path, header, rows)

    with caplog.at_level(logging.ERROR, logger="server"):
        charts, sectors = server._load_excel_workbook(path, "test")

    assert charts is None
    assert sectors is None
    assert "missing required catalog column" in caplog.text


def test_header_order_can_change(tmp_path):
    server = _import_server()
    path = tmp_path / "reordered.xlsx"
    header = [
        "Indicator Name",
        "Freq",
        "#",
        "Unit",
        "是否选中",
        "Col",
        "板块",
        "大类",
        "子类",
        "数据性质",
        "状态说明",
        "Sheet Name",
        "指标标签",
    ]
    rows = [
        [None, None, "月度 (1 sht 1 ind)", None, "否", None, None, "其他", "其他", None, None, None, None],
        [None, None, "测试sheet", None, "否", None, "测试板块", "价格", "现货价格", None, None, None, None],
        ["测试指标", "月度", "1", "元", "是", "1", None, "价格", "现货价格", "水平值", "测试原因", None, '{"产品": "测试"}'],
    ]
    _write_workbook(path, header, rows)

    charts, _ = server._load_excel_workbook(path, "test")

    assert charts is not None
    assert len(charts) == 1
    assert charts[0]["title"] == "测试指标"
    assert charts[0]["selected"] is True
