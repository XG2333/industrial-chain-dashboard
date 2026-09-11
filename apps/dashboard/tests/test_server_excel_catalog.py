from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
DATA_PATHS = [
    REPO_ROOT / "data" / "processed" / "锡产业链数据_workflow_ai.xlsx",
    REPO_ROOT / "data" / "processed" / "硅产业链数据_workflow_ai.xlsx",
    REPO_ROOT / "data" / "processed" / "碳酸锂数据库_workflow_ai.xlsx",
]


def test_workbook_paths_use_workflow_ai_sources() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import server as server_module

    assert server_module.TIN_WORKBOOK_PATH.name == "锡产业链数据_workflow_ai.xlsx"
    assert server_module.SILICON_WORKBOOK_PATH.name == "硅产业链数据_workflow_ai.xlsx"
    assert server_module.LITHIUM_WORKBOOK_PATH.name == "碳酸锂数据库_workflow_ai.xlsx"


def _assert_valid_charts(charts: list[dict], sectors: set[str], prefix: str) -> None:
    effective_sectors = sectors | {f"{prefix}其他"}
    sec_counts = {}
    for c in charts:
        s = c.get("sector", "")
        sec_counts[s] = sec_counts.get(s, 0) + 1

    assert set(sec_counts).issubset(effective_sectors)
    assert sum(sec_counts.values()) == len(charts)
    assert all(c.get("category") for c in charts)
    assert all(c.get("freq") for c in charts)
    assert all("confidence" in c for c in charts)
    assert all("selected" in c for c in charts)
    assert all(isinstance(c.get("tags"), list) for c in charts)
    assert all(isinstance(tag, dict) for c in charts for tag in c.get("tags", []))
    confs = [c["confidence"] for c in charts if c.get("confidence") is not None]
    assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in confs)


@pytest.mark.skipif(
    not all(path.exists() for path in DATA_PATHS),
    reason="local processed workbooks are not present",
)
def test_server_loads_charts_from_workbook() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import server as server_module

    server_module._load_all_workbooks()

    assert all(server_module._SOURCE_CHARTS[source] for source in ("tin", "silicon", "lithium"))

    _assert_valid_charts(
        server_module._SOURCE_CHARTS["tin"],
        server_module._SOURCE_SECTORS["tin"],
        "tin",
    )
    _assert_valid_charts(
        server_module._SOURCE_CHARTS["silicon"],
        server_module._SOURCE_SECTORS["silicon"],
        "silicon",
    )
    _assert_valid_charts(
        server_module._SOURCE_CHARTS["lithium"],
        server_module._SOURCE_SECTORS["lithium"],
        "lithium",
    )
    for source in ("lithium", "silicon", "tin"):
        sub_counts = {"进口": 0, "出口": 0, "净出口": 0}
        for chart in server_module._SOURCE_CHARTS[source]:
            if chart.get("major") == "进出口" and chart.get("selected"):
                sub = chart.get("sub")
                if sub in sub_counts:
                    sub_counts[sub] += 1
        assert len(set(sub_counts.values())) == 1, (
            f"{source} selected import/export counts: {sub_counts}"
        )
    assert len(server_module._excel_cache["__all__"]["charts"]) == sum(
        len(server_module._SOURCE_CHARTS[source])
        for source in ("tin", "silicon", "lithium")
    )


def test_resolve_source() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import server as server_module

    assert server_module._resolve_source("锡", None) == "tin"
    assert server_module._resolve_source("硅", None) == "silicon"
    assert server_module._resolve_source("锂", None) == "lithium"
    assert server_module._resolve_source("工业硅", None) == "silicon"
    assert server_module._resolve_source("锡锭", None) == "tin"
    assert server_module._resolve_source("碳酸锂", None) == "lithium"


def test_read_published_source_paths(tmp_path, monkeypatch) -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import server as server_module

    current = tmp_path / "current.json"
    published_file = tmp_path / "published.xlsx"
    published_file.write_bytes(b"published")
    current.write_text(
        json.dumps(
            {
                "run_id": "r1",
                "status": "success",
                "industry": "tin",
                "dashboard_data_path": str(published_file),
                "source_files": {"tin": str(published_file)},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKFLOW_CURRENT_PATH", str(current))
    assert server_module._read_published_source_paths() == {
        "tin": str(published_file)
    }


def test_read_published_source_paths_malformed(tmp_path, monkeypatch) -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import server as server_module

    current = tmp_path / "current.json"
    current.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("WORKFLOW_CURRENT_PATH", str(current))
    assert server_module._read_published_source_paths() == {}


def test_classify_category():
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    import server as server_module

    assert server_module._classify_category("SHFE: 锡: 主力合约: 收盘价: 日度") == "其他"
    assert server_module._classify_category("SMM: 沪锡期现价差: 当月合约: 收盘价: 日度") == "一、价格"
    assert server_module._classify_category("SHFE: 锡: 主力合约: 成交量: 日度") == "五、量价"
    assert server_module._classify_category("SHFE: 锡: 仓单日报: 期货: 日度") == "三、供需-库存"
    assert server_module._classify_category("SMM: 锡矿矿端平衡: 缅甸矿进口金属量: 月度") == "三、供需-进出口"
    assert server_module._classify_category("SMM: 国内锡市平衡(新): 产量: 月度") == "二、供需-供应"
    assert server_module._classify_category("SMM: 国内锡市平衡(新): 表观消费量: 月度") == "二、供需-需求"
    assert server_module._classify_category("SMM: 部分自产矿锡锭冶炼企业平均现金成本: 月度") == "四、成本利润"
