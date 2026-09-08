# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from import_export_rules import (  # noqa: E402
    deduplicate_import_export_selection,
    find_missing_net_export_pairs,
    flow_dimension,
    is_total_import_export,
    metric_key,
)


def _row(sheet, title, frequency="月度", major="供需-进出口", unit="吨", col=1, selected=True, sub=None):
    return {
        "sheet": sheet,
        "title": title,
        "frequency": frequency,
        "major": major,
        "sub": sub or ("进口" if "进口" in title and "出口" not in title else "出口" if "出口" in title and "进口" not in title else "净出口" if "净出口" in title else "进出口"),
        "unit": unit,
        "col": col,
        "selected": selected,
    }


def test_finds_pair_across_separate_import_export_sheets():
    rows = [
        _row("碳酸锂进口-月", "中国海关: 碳酸锂进口量: 总计: 月度", col=2),
        _row("碳酸锂出口-月", "中国海关: 碳酸锂出口量: 总计: 月度", col=3),
        _row("碳酸锂进口-月", "中国海关: 碳酸锂进口量: 澳大利亚: 月度", col=4),
    ]
    missing = find_missing_net_export_pairs(rows)
    assert len(missing) == 1
    assert missing[0]["dimension"] == "数量"
    assert "碳酸锂" in missing[0]["key"]
    assert missing[0]["import_row"]["col"] == 2
    assert missing[0]["export_row"]["col"] == 3


def test_finds_total_in_country_breakdown_sheet():
    rows = [
        _row("六氟磷酸锂进出口分国别-月", "中国海关: 六氟磷酸锂进口量: 总计: 月度", col=2),
        _row("六氟磷酸锂出口-月", "中国海关: 六氟磷酸锂出口量: 月度", col=3),
    ]
    missing = find_missing_net_export_pairs(rows)
    assert len(missing) == 1
    assert "六氟磷酸锂" in missing[0]["key"]


def test_uses_title_frequency_when_catalog_frequency_is_wrong():
    rows = [
        _row("日本碳酸锂进出口-月", "日本海关: 碳酸锂进口量: 总计: 月度", frequency="日度", col=2),
        _row("日本碳酸锂进出口-月", "日本海关: 碳酸锂出口量: 总计: 月度", frequency="日度", col=3),
    ]
    missing = find_missing_net_export_pairs(rows)
    assert len(missing) == 1
    assert "碳酸锂" in missing[0]["key"]


def test_does_not_pair_value_with_quantity():
    rows = [
        _row("碳酸锂进口-月", "中国海关: 碳酸锂进口量: 总计: 月度", col=2),
        _row("碳酸锂出口-月", "中国海关: 碳酸锂出口额: 总计: 月度", col=3),
    ]
    assert flow_dimension(rows[0]["title"]) == "数量"
    assert flow_dimension(rows[1]["title"]) == "金额"
    assert find_missing_net_export_pairs(rows) == []


def test_metric_key_preserves_source_name():
    key = metric_key("日本海关: 碳酸锂进口量: 总计: 月度")
    assert "日本" in key
    assert "日" in key


def test_net_amount_key_matches_import_export_amount_key():
    net_key = metric_key("中国海关: NCM前驱体净出口额: 月度")
    flow_key = metric_key("中国海关: NCM前驱体进口额: 总计: 月度")
    assert net_key == flow_key


def test_metal_lithium_china_prefix_is_normalized():
    assert metric_key("中国海关: 中国金属锂进口量: 月度") == metric_key("中国海关: 金属锂出口量: 月度")


def test_average_price_import_export_is_unselected():
    rows = [
        _row("碳酸锂进口-月", "中国海关: 碳酸锂进口均价: 总计: 月度"),
        _row("碳酸锂出口-月", "中国海关: 碳酸锂出口均价: 总计: 月度"),
    ]
    deduplicate_import_export_selection(rows)
    assert rows[0]["selected"] is False
    assert rows[1]["selected"] is False
    assert rows[0]["reason"] == "进出口均价指标不保留"


def test_non_import_export_total_is_unselected():
    rows = [
        _row("锂矿航运-月", "SMM: 锂矿航运: 澳洲黑德兰港锂辉石精矿出港: 总计: 月度"),
    ]
    deduplicate_import_export_selection(rows)
    assert rows[0]["selected"] is False
    assert rows[0]["reason"] == "非进出口总量（出港/到港/贸易流向等）不选中"


def test_unpaired_import_removes_existing_net_export():
    rows = [
        _row("碳酸锂进口-月", "中国海关: 碳酸锂进口量: 总计: 月度"),
        _row("净出口计算", "中国海关: 碳酸锂净出口: 月度"),
    ]
    deduplicate_import_export_selection(rows)
    assert rows[0]["selected"] is False
    assert rows[0]["reason"] == "进出口无配对（只有进口或只有出口），不选中"
    assert rows[1]["selected"] is False
    assert rows[1]["reason"] == "进出口无配对（只有进口或只有出口），不选中"


def test_duplicate_import_prefers_explicit_import_sub():
    rows = [
        _row("金属锂进出口-月", "中国海关: 中国金属锂进口量: 总计: 月度", sub="进口"),
        _row("金属锂进出口-月", "中国海关: 金属锂进口: 总计-进口总额: 月度", sub="进出口"),
        _row("金属锂进出口-月", "中国海关: 中国金属锂出口量: 总计: 月度", sub="出口"),
    ]
    deduplicate_import_export_selection(rows)
    # 无净出口配对 → 整组不选中（保证进出口三子类选中数量均衡）
    assert all(not r["selected"] for r in rows)
    assert rows[0]["reason"] == "进出口无净出口配对，不选中"

def test_is_total_import_export_accepts_bare_export_monthly_total():
    assert is_total_import_export(
        "中国海关: 未锻轧的非合金锡出口: 月度",
        "未锻轧的非合金锡进出口-月",
    )
    assert not is_total_import_export("SMM: 锡矿进口盈亏水平: 日度")


def test_finds_pair_with_bare_export_title():
    rows = [
        _row("未锻轧的非合金锡进出口-月", "中国海关: 未锻轧的非合金锡进口量: 月度", col=2),
        _row("未锻轧的非合金锡进出口-月", "中国海关: 未锻轧的非合金锡出口: 月度", col=3),
    ]
    missing = find_missing_net_export_pairs(rows)
    assert len(missing) == 1
    assert "未锻轧的非合金锡" in missing[0]["key"]


def test_dedup_selects_unselected_net_and_bare_export_pair():
    rows = [
        _row("未锻轧的非合金锡进出口-月", "中国海关: 未锻轧的非合金锡进口量: 月度", selected=True),
        _row("未锻轧的非合金锡进出口-月", "中国海关: 未锻轧的非合金锡出口: 月度", selected=True),
        _row("净出口计算", "中国海关 未锻轧的非合金锡净出口: 月度", selected=False),
    ]
    deduplicate_import_export_selection(rows)
    assert all(row["selected"] for row in rows)
    assert rows[0]["reason"] == "进出口仅保留总量月度"
    assert rows[2]["reason"] == "进出口仅保留总量月度"


def test_dedup_selects_one_existing_net_export_duplicate():
    rows = [
        _row("未锻轧的非合金锡进出口-月", "中国海关: 未锻轧的非合金锡进口量: 月度", selected=True),
        _row("未锻轧的非合金锡进出口-月", "中国海关: 未锻轧的非合金锡出口: 月度", selected=True),
        _row("未锻轧的非合金锡进出口-月", "未锻轧的非合金锡净出口", selected=False),
        _row("净出口计算", "中国海关 未锻轧的非合金锡净出口: 月度", selected=False),
    ]
    deduplicate_import_export_selection(rows)
    assert rows[2]["selected"] is False
    assert rows[3]["selected"] is True
    assert rows[3]["reason"] == "进出口仅保留总量月度"

def test_is_total_import_export_excludes_country_and_overseas_details():
    assert not is_total_import_export(
        "韩国海关: 精炼锡进口量_中国: 月度",
        "韩国精炼锡进出口-日",
    )
    assert not is_total_import_export(
        "SMM: 锡锭比利时出口量: 月度",
        "海外精炼锡进出口-月",
    )
    assert is_total_import_export(
        "中国海关: 其他铅蓄电池进口量: 月度",
        "铅蓄电池进出口-月",
    )


def test_dedup_selects_net_without_source_prefix():
    rows = [
        _row("铅蓄电池进出口-月", "中国海关: 其他铅蓄电池进口量: 月度", selected=True),
        _row("铅蓄电池进出口-月", "中国海关: 其他铅蓄电池出口量: 月度", selected=True),
        _row("铅蓄电池进出口-月", "其他铅蓄电池净出口-月", selected=False),
    ]
    deduplicate_import_export_selection(rows)
    assert all(row["selected"] for row in rows)
    assert rows[2]["reason"] == "进出口仅保留总量月度"


def test_import_export_quantity_units_are_kept_regardless_of_unit():
    rows = [
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口量: 总计: 月度", unit="吨"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口量: 总计: 月度", unit="吨"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口量: 总计: 月度", unit="千克"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口量: 总计: 月度", unit="千克"),
    ]
    deduplicate_import_export_selection(rows)
    # 无净出口配对 → 整组不选中（保证进出口三子类选中数量均衡）
    assert all(not r["selected"] for r in rows)
    assert rows[0]["reason"] == "进出口无净出口配对，不选中"


def test_mixed_unit_pair_is_selected():
    rows = [
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口量: 总计: 月度", unit="吨"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口量: 总计: 月度", unit="千克"),
    ]
    deduplicate_import_export_selection(rows)
    # 无净出口配对 → 整组不选中（保证进出口三子类选中数量均衡）
    assert all(not r["selected"] for r in rows)
    assert rows[0]["reason"] == "进出口无净出口配对，不选中"


def test_net_export_pairing_does_not_require_tone_unit():
    rows = [
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口量: 总计: 月度", unit="千克"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口量: 总计: 月度", unit="千克"),
    ]
    missing = find_missing_net_export_pairs(rows)
    assert len(missing) == 1
    assert missing[0]["dimension"] == "数量"


def test_import_export_amount_rows_are_unselected():
    rows = [
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口额: 总计: 月度"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口额: 总计: 月度"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口总额: 总计: 月度"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口总额: 总计: 月度"),
    ]
    deduplicate_import_export_selection(rows)
    assert [row["selected"] for row in rows] == [False, False, False, False]
    assert rows[0]["reason"] == "进出口金额指标不保留"
    assert rows[2]["reason"] == "进出口金额指标不保留"


def test_net_export_pairing_skips_amount_rows():
    rows = [
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂进口额: 总计: 月度"),
        _row("碳酸锂进出口-月", "中国海关: 碳酸锂出口额: 总计: 月度"),
    ]
    assert find_missing_net_export_pairs(rows) == []

