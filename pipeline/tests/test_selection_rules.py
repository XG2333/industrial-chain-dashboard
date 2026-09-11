# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lithium_selection_rules import (  # noqa: E402
    metric_base,
    select_rows as lithium_select_rows,
)
from classification_candidates import candidate_plan  # noqa: E402
from lithium_rules import classify_indicator_sector  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from selection_utils import (  # noqa: E402
    apply_common_price_rules,
    exclude_import_export_amount_rows,
    exclude_import_export_average_rows,
    exclude_yoy_mom_share_rows,
    ensure_unique_selected_rows,
    ensure_volume_position_pairing,
    frequency_comparison_key,
    normalize_comparison_text,
    volume_position_ratio_key,
)
from silicon_selection_rules import select_rows as silicon_select_rows  # noqa: E402
from tin_rules import select_rows as tin_select_rows  # noqa: E402
from volume_position_ratio import (  # noqa: E402
    compute_ratio_series,
    find_missing_volume_position_ratio_pairs,
)


COST_PROFIT = "成本利润"
COST = "成本"
PROFIT = "利润"
OTHER = "其他"
ANNUAL = "年度"
QUARTERLY = "季度"
MONTHLY = "月度"
WEEKLY = "周度"
DAILY = "日度"


def _row(sub: str, title: str, frequency: str, major: str = COST_PROFIT) -> dict:
    return {
        "sheet": "S",
        "title": title,
        "frequency": frequency,
        "major": major,
        "sub": sub,
    }


def test_lithium_profit_keeps_only_highest_frequency() -> None:
    rows = [
        _row(PROFIT, f"SMM: 示例利润: {ANNUAL}", ANNUAL),
        _row(PROFIT, f"SMM: 示例利润: {QUARTERLY}", QUARTERLY),
        _row(PROFIT, f"SMM: 示例利润: {MONTHLY}", MONTHLY),
        _row(PROFIT, f"SMM: 示例利润: {DAILY}", DAILY),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [False, False, False, True]
    assert processed[3]["reason"] == "成本利润仅保留最高频"


def test_lithium_ore_chemical_formula_unified_for_frequency() -> None:
    # "锂辉石（中国现货 Li2O: 3%-4%）" 与 "锂辉石（中国现货 3%-4%）" 为同一指标，
    # 化学式仅为品位标注：日度/周度/月度同组去重，只保留最高频（日度）
    rows = [
        _row("现货价格", "SMM: 锂辉石（中国现货 Li2O: 3%-4%） - 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 锂辉石（中国现货 3%-4%） -平均价: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 锂辉石（中国现货 3%-4%） -平均价: 月度", MONTHLY, major="价格"),
        # 下标 ₂ 写法同样归一化
        _row("现货价格", "SMM: 锂云母精矿（中国现货）（Li₂O: 1.5%-2.0%） - 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 锂云母精矿（中国现货）（Li2O: 1.5%-2.0%） -平均价: 周度", WEEKLY, major="价格"),
    ]
    # 规格标签差异也要归一化：日度版规格 "Li2O: 3%-4%; 3%-4%" 与
    # 周度版 "3%-4%" 应视为同一规格
    rows[0]["tags"] = {"规格": "Li2O: 3%-4%; 3%-4%"}
    rows[1]["tags"] = {"规格": "3%-4%"}
    rows[2]["tags"] = {"规格": "3%-4%"}
    rows[3]["tags"] = {"规格": "Li₂O: 1.5%-2.0%; 1.5%-2.0%"}
    rows[4]["tags"] = {"规格": "Li2O: 1.5%-2.0%; 1.5%-2.0%"}
    apply_common_price_rules(rows)
    assert [r["selected"] for r in rows] == [True, False, False, True, False]


def test_chemical_formula_normalization_does_not_affect_other_letters() -> None:
    # 精确匹配化学式字样：NMP/DMC/SC6 等含其他英文字母的指标不受影响
    nmp = _row("现货价格", "SMM: NMP - 平均价: 日度", DAILY, major="价格")
    dmc = _row("现货价格", "SMM: 碳酸二甲酯DMC (出厂价）- 平均价: 日度", DAILY, major="价格")
    sc6 = _row("现货价格", "SMM: 巴西锂辉石精矿样本平均每吨SC6生产成本（FOB）: 季度", QUARTERLY, major="价格")
    for row in (nmp, dmc, sc6):
        apply_common_price_rules([row])
        assert row["selected"] is True


def test_contract_filter_only_applies_to_contract_subs() -> None:
    # 方案C：合约过滤仅限 期货价格/成交量/持仓 子类，
    # 期现价差（现货-期货）含"期货"字样但非合约行，走价差规则保留
    spread = _row("价差", "SMM: 电池级碳酸锂期现价差（现货-期货）: 日度", DAILY, major="价格")
    apply_common_price_rules([spread])
    assert spread["selected"] is True

    # 交割库容（含"期货"字样但 sub=库容）不再被合约规则筛除
    capacity = _row("库容", "GFEX: 广期所碳酸锂期货交割库容: 交割仓库库容: 月度", MONTHLY, major="价格")
    apply_common_price_rules([capacity])
    assert capacity["selected"] is True

    # 真合约行过滤不变：非主力/01/05/09 合约仍筛除
    rows = [
        _row("期货价格", "GFEX: 碳酸锂: 二月合约: 收盘价: 日度", DAILY, major="价格"),
        _row("期货价格", "GFEX: 碳酸锂: 主力合约: 收盘价: 日度", DAILY, major="价格"),
        _row("成交量", "GFEX: 碳酸锂: 二月合约: 成交量: 日度", DAILY, major="价格"),
        _row("持仓", "GFEX: 碳酸锂: 主力合约: 持仓量: 日度", DAILY, major="价格"),
    ]
    apply_common_price_rules(rows)
    assert [r["selected"] for r in rows] == [False, True, False, True]


def test_cobalt_price_daily_kept_over_weekly() -> None:
    """4.45V钴酸锂(国产)-日度 与 钴酸锂 4.45V-周度 视为同一产品，
    公共价格规则只保留最高频（日度）。"""
    rows = [
        _row("现货价格", "SMM: 4.45V钴酸锂(国产)- 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 钴酸锂 4.45V-平均价: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 钴酸锂 4.45V-平均价: 月度", MONTHLY, major="价格"),
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, False, False]
    assert rows[0]["reason"] == "公共价格规则：仅保留最高频"


def test_cobalt_price_trailing_zero_voltage_unified() -> None:
    """电压尾零归一化：4.40V钴酸锂(国产)-日度 与 钴酸锂4.4V-周度 视为同一产品。"""
    rows = [
        _row("现货价格", "SMM: 4.40V钴酸锂(国产) - 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 钴酸锂4.4V -平均价: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 4.50V钴酸锂(国产) - 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 钴酸锂4.5V -平均价: 周度", WEEKLY, major="价格"),
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, False, True, False]


def test_cobalt_electrolyte_not_affected_by_normalization() -> None:
    """电解液（钴酸锂用）等含"钴酸锂"但非电压序列的标题不应被合并。"""
    rows = [
        _row("现货价格", "SMM: 电解液（钴酸锂用）-平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 电解液（钴酸锂用）-平均价: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 钴酸锂电芯（4.0-5.0Ah） - 平均价: 周度", WEEKLY, major="价格"),
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, False, True]


def test_lithium_duplicate_profit_keeps_one_row() -> None:
    rows = [
        _row(PROFIT, f"SMM: 示例利润: {DAILY}", DAILY),
        _row(PROFIT, f"SMM: 示例利润: {DAILY}", DAILY),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False]
    assert processed[1]["reason"] == "成本利润同频重复，只保留一条"


def test_lithium_storage_ratio_total_alias_keeps_one_row() -> None:
    rows = [
        _row("库销比", "SMM: 储能电芯库销比: 月度", MONTHLY, major="库存"),
        _row("库销比", "SMM: 储能电芯库销比: 总计: 月度", MONTHLY, major="库存"),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False]
    assert processed[1]["reason"] == "锂电专属规则：储能电芯库销比重复，只保留一条"


def test_lithium_spot_futures_basis_is_kept() -> None:
    rows = [
        _row(
            "价差",
            "SMM: 电池级碳酸锂期现价差（现货-期货）: 日度",
            DAILY,
            major="价格",
        )
    ]

    processed = lithium_select_rows(rows)

    assert processed[0]["selected"] is True
    assert processed[0]["reason"] == "期现价差（现货-期货）保留"


def test_lithium_spot_price_keeps_only_highest_frequency() -> None:
    rows = [
        _row("现货价格", "SMM: 示例现货: 月度", MONTHLY, major="价格"),
        _row("现货价格", "SMM: 示例现货: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 示例现货: 日度", DAILY, major="价格"),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [False, False, True]
    assert processed[2]["reason"] == "现货价格仅保留最高频"


def test_lithium_balance_priority_classifies_balance_balance() -> None:
    plan = candidate_plan(
        "SMM: 锂矿供需平衡（锂辉石、锂云母）: 产量: 月度",
        "",
        "lithium",
    )

    assert plan["major"] == "平衡"
    assert plan["sub"] == "平衡"


def test_processing_fee_classifies_as_supply() -> None:
    generic = candidate_plan(
        "SMM: 锡精矿加工费_云南40%: 日度",
        "",
        "lithium_tin",
    )
    silicon = candidate_plan(
        "SMM: 硅片加工费: 日度",
        "",
        "silicon",
    )

    assert generic["major"] == "供给"
    assert generic["sub"] == "加工费"
    assert silicon["major"] == "供给"
    assert silicon["sub"] == "加工费"


def test_processing_fee_wins_when_price_keyword_also_matches() -> None:
    plan = candidate_plan(
        "SMM: NMP净水加工费 - 平均价: 日度",
        "",
        "lithium",
    )

    assert plan["major"] == "供给"
    assert plan["sub"] == "加工费"


def test_balance_category_priority_is_common() -> None:
    from lithium_rules import classify_category as lithium_category
    from silicon_catalog import classify_category as silicon_category
    from tin_rules import classify_category as tin_category

    assert lithium_category("锂矿供需平衡-产量-月") == "三、供需-平衡"
    assert tin_category("锡供需平衡-产量-月") == "三、供需-平衡"
    assert silicon_category("多晶硅供需平衡-产量-月") == "三、供需-平衡"


def test_lithium_spot_price_normalizes_dash_spacing() -> None:
    rows = [
        _row("现货价格", "SMM: 5系三元前驱体（多晶/消费型） - 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 5系三元前驱体（多晶/消费型） -平均价: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 5系三元前驱体（多晶/消费型） -平均价: 月度", MONTHLY, major="价格"),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False, False]
    assert processed[0]["reason"] == "现货价格仅保留最高频"


def test_lithium_spot_price_normalizes_colon_hyphen_and_parentheses() -> None:
    rows = [
        _row("现货价格", "SMM: 黄磷: 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 黄磷-平均价: 周度", WEEKLY, major="价格"),
        _row("现货价格", "SMM: 碳酸丙烯酯PC (出厂价)-平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 碳酸丙烯酯PC (出厂价)平均价: 月度", MONTHLY, major="价格"),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False, True, False]


def test_metric_base_normalizes_exchange_prefix_and_month() -> None:
    shfe_key = metric_base("SHFE: 碳酸锂: 一月合约: 价格: 日度")
    gfex_key = metric_base("GFEX: 碳酸锂: 01合约: 价格: 周度")

    assert shfe_key == gfex_key == "碳酸锂01合约价格"


def test_metric_base_keeps_variable_words_distinct() -> None:
    assert metric_base("SMM: 碳酸锂: 价格: 日度") != metric_base("SMM: 碳酸锂: 成交量: 日度")


def test_metric_base_keeps_decimal_specs_distinct() -> None:
    assert metric_base("SMM: 1.2μm: 价格: 日度") != metric_base("SMM: 12μm: 价格: 日度")


def test_lithium_spot_price_keeps_density_specs_distinct() -> None:
    rows = [
        _row("现货价格", "SMM: 磷酸铁锂(储能型压实密度≥2.40g/cm³)-平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 磷酸铁锂(储能型压实密度≥2.50g/cm³)-平均价: 日度", DAILY, major="价格"),
    ]

    processed = lithium_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, True]


def test_lithium_non_month_basis_is_still_rejected() -> None:
    rows = [
        _row(
            "价差",
            "SMM: 碳酸锂期现价差: 连一合约: 收盘价: 日度",
            DAILY,
            major="价格",
        )
    ]

    processed = lithium_select_rows(rows)

    assert processed[0]["selected"] is False
    assert processed[0]["reason"] == "基差仅保留当月期现/现货升贴水"


def test_tin_cost_keeps_only_highest_frequency() -> None:
    rows = [
        _row(COST, f"SMM: 示例成本: {ANNUAL}", ANNUAL),
        _row(COST, f"SMM: 示例成本: {MONTHLY}", MONTHLY),
        _row(COST, f"SMM: 示例成本: {DAILY}", DAILY),
    ]

    processed = tin_select_rows(rows)

    assert [row["selected"] for row in processed] == [False, False, True]


def test_tin_duplicate_profit_whitelist_keeps_one_row() -> None:
    title = f"SMM: 锡矿进口盈亏水平: {DAILY}"
    rows = [
        _row(PROFIT, title, DAILY),
        _row(PROFIT, title, DAILY),
    ]

    processed = tin_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False]
    assert processed[1]["reason"] == "成本利润同频重复，只保留一条"


def test_silicon_other_keeps_only_highest_frequency() -> None:
    rows = [
        _row(OTHER, f"SMM: 示例成本消耗: {ANNUAL}", ANNUAL),
        _row(OTHER, f"SMM: 示例成本消耗: {QUARTERLY}", QUARTERLY),
        _row(OTHER, f"SMM: 示例成本消耗: {MONTHLY}", MONTHLY),
        _row(OTHER, f"SMM: 示例成本消耗: {DAILY}", DAILY),
    ]

    processed = silicon_select_rows(rows)

    assert [row["selected"] for row in processed] == [False, False, False, True]


def test_silicon_duplicate_cost_keeps_one_row() -> None:
    rows = [
        _row(COST, f"SMM: 示例成本: {DAILY}", DAILY),
        _row(COST, f"SMM: 示例成本: {DAILY}", DAILY),
    ]

    processed = silicon_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False]
    assert processed[1]["reason"] == "成本利润同频重复，只保留一条"


def test_silicon_uses_title_frequency_for_rank() -> None:
    rows = [
        _row(COST, f"SMM: 示例成本: {DAILY}", ANNUAL),
        _row(COST, f"SMM: 示例成本: {MONTHLY}", ANNUAL),
    ]

    processed = silicon_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False]


def test_silicon_spot_price_normalizes_dash_spacing() -> None:
    rows = [
        _row("现货价格", "SMM: 木片 - 平均价: 日度", DAILY, major="价格"),
        _row("现货价格", "SMM: 木片-平均价: 周度", WEEKLY, major="价格"),
    ]

    processed = silicon_select_rows(rows)

    assert [row["selected"] for row in processed] == [True, False]


def test_silicon_volume_and_position_are_one_to_one() -> None:
    contracts = [
        "主力合约",
        "一月合约",
        "二月合约",
        "三月合约",
        "四月合约",
        "五月合约",
        "六月合约",
        "七月合约",
        "八月合约",
        "九月合约",
        "十月合约",
        "十一月合约",
        "十二月合约",
    ]
    rows = []
    for contract in contracts:
        rows.append(
            _row(
                "成交量",
                f"GFEX: 工业硅: {contract}: 成交量: 日度",
                DAILY,
                major="价格",
            )
        )
        rows.append(
            _row(
                "持仓",
                f"GFEX: 工业硅: {contract}: 持仓量: 日度",
                DAILY,
                major="价格",
            )
        )

    processed = silicon_select_rows(rows)

    volume_contracts = {
        row["title"].split(": ")[2]
        for row in processed
        if row["sub"] == "成交量" and row["selected"]
    }
    position_contracts = {
        row["title"].split(": ")[2]
        for row in processed
        if row["sub"] == "持仓" and row["selected"]
    }
    assert volume_contracts == position_contracts == {"主力合约", "一月合约", "五月合约", "九月合约"}


def test_volume_position_pairing_removes_unmatched_rows() -> None:
    rows = [
        {
            "title": "GFEX: 工业硅: 主力合约: 成交量: 日度",
            "sub": "成交量",
            "frequency": "日度",
            "selected": True,
        },
        {
            "title": "GFEX: 工业硅: 主力合约: 持仓量: 日度",
            "sub": "持仓",
            "frequency": "日度",
            "selected": True,
        },
        {
            "title": "GFEX: 工业硅: 二月合约: 成交量: 日度",
            "sub": "成交量",
            "frequency": "日度",
            "selected": True,
        },
    ]

    ensure_volume_position_pairing(rows)

    assert [row["selected"] for row in rows] == [True, True, False]
    assert rows[2]["reason"] == "成交量/持仓量无对应持仓/成交量，不选中"


def test_ensure_unique_selected_rows_keeps_exact_duplicate_once() -> None:
    rows = [
        {
            "sheet": "电池及碳酸锂期现价差-日",
            "title": "SMM: 电池级碳酸锂期现价差（现货-期货）: 日度",
            "frequency": "日度",
            "major": "价格",
            "sub": "价差",
            "selected": True,
        },
        {
            "sheet": "碳酸锂基差-日",
            "title": "SMM: 电池级碳酸锂期现价差（现货-期货）: 日度",
            "frequency": "日度",
            "major": "价格",
            "sub": "价差",
            "selected": True,
        },
    ]

    ensure_unique_selected_rows(rows)

    assert [row["selected"] for row in rows] == [True, False]
    assert rows[1]["reason"] == "同指标重复，只保留一条"


def test_ensure_unique_selected_rows_keeps_price_and_volume_distinct() -> None:
    rows = [
        {"sheet": "S", "title": "SMM: 碳酸锂: 价格: 日度", "frequency": "日度", "major": "价格", "sub": "现货价格", "selected": True},
        {"sheet": "S", "title": "SMM: 碳酸锂: 成交量: 日度", "frequency": "日度", "major": "价格", "sub": "成交量", "selected": True},
    ]

    ensure_unique_selected_rows(rows)

    assert [row["selected"] for row in rows] == [True, True]


def test_common_price_rules_keeps_tin_spot_highest_frequency() -> None:
    rows = [
        {"major": "价格", "sub": "现货价格", "title": "SMM: 1#锡-平均价: 日度", "frequency": "日度", "selected": False},
        {"major": "价格", "sub": "现货价格", "title": "SMM: 1#锡-平均价: 周度", "frequency": "周度", "selected": False},
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, False]
    assert rows[0]["reason"] == "公共价格规则：仅保留最高频"


def test_common_price_rules_unicode_subscript_spacing_keeps_daily() -> None:
    rows = [
        {
            "major": "价格",
            "sub": "现货价格",
            "sector": "锂矿",
            "unit": "元/吨",
            "title": "SMM: 磷锂铝石（中国现货）（Li₂O: 6%-7%） - 平均价: 日度",
            "frequency": "日度",
            "selected": False,
        },
        {
            "major": "价格",
            "sub": "现货价格",
            "sector": "锂矿",
            "unit": "元/吨",
            "title": "SMM: 磷锂铝石（中国现货）（Li2O: 6%-7%）-平均价: 周度",
            "frequency": "周度",
            "selected": False,
        },
        {
            "major": "价格",
            "sub": "现货价格",
            "sector": "锂矿",
            "unit": "元/吨",
            "title": "SMM: 磷锂铝石（中国现货）（Li2O: 6%-7%） - 平均价: 月度",
            "frequency": "月度",
            "selected": False,
        },
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, False, False]
    assert rows[1]["reason"] == "公共价格规则：仅保留最高频"
    assert rows[2]["reason"] == "公共价格规则：仅保留最高频"


def test_common_price_rules_keeps_different_specs_separate() -> None:
    rows = [
        {
            "major": "价格",
            "sub": "现货价格",
            "sector": "锂矿",
            "unit": "元/吨",
            "title": "SMM: 磷锂铝石（中国现货）（Li₂O: 6%-7%） - 平均价: 日度",
            "frequency": "日度",
            "selected": False,
        },
        {
            "major": "价格",
            "sub": "现货价格",
            "sector": "锂矿",
            "unit": "元/吨",
            "title": "SMM: 磷锂铝石（中国现货）（Li2O: 7%-8%）-平均价: 周度",
            "frequency": "周度",
            "selected": False,
        },
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, True]


def test_common_price_rules_preserves_source_unit_and_region() -> None:
    base = {
        "major": "价格",
        "sub": "现货价格",
        "sector": "锂矿",
        "unit": "元/吨",
        "title": "SMM: 磷锂铝石（中国现货）（Li2O: 6%-7%）-平均价: 日度",
        "frequency": "日度",
        "selected": False,
        "tags": {"地域": "中国"},
    }
    rows = [
        dict(base),
        {
            **base,
            "title": "Mysteel: 磷锂铝石（中国现货）（Li2O: 6%-7%）-平均价: 周度",
            "frequency": "周度",
        },
        {
            **base,
            "title": "SMM: 磷锂铝石（中国现货）（Li2O: 6%-7%）-平均价: 周度",
            "frequency": "周度",
            "unit": "美元/吨",
        },
        {
            **base,
            "title": "SMM: 磷锂铝石（中国现货）（Li2O: 6%-7%）-平均价: 周度",
            "frequency": "周度",
            "tags": {"地域": "日本"},
        },
    ]

    apply_common_price_rules(rows)

    assert [row["selected"] for row in rows] == [True, True, True, True]


def test_normalize_comparison_text_is_idempotent() -> None:
    left = "Li₂O: 6%-7%"
    right = "Li2O：6 % - 7 %"
    normalized = normalize_comparison_text(left)
    assert normalized == normalize_comparison_text(right)
    assert normalize_comparison_text(normalized) == normalized


def test_frequency_comparison_key_strips_frequency_and_keeps_specs() -> None:
    daily = {
        "title": "SMM: 磷锂铝石（中国现货）（Li₂O: 6%-7%） - 平均价: 日度",
        "major": "价格",
        "sub": "现货价格",
        "sector": "锂矿",
        "unit": "元/吨",
    }
    weekly = {
        "title": "SMM: 磷锂铝石（中国现货）（Li2O: 6%-7%）-平均价: 周度",
        "major": "价格",
        "sub": "现货价格",
        "sector": "锂矿",
        "unit": "元/吨",
    }
    other_spec = {
        "title": "SMM: 磷锂铝石（中国现货）（Li2O: 7%-8%）-平均价: 周度",
        "major": "价格",
        "sub": "现货价格",
        "sector": "锂矿",
        "unit": "元/吨",
    }

    assert frequency_comparison_key(daily) == frequency_comparison_key(weekly)
    assert frequency_comparison_key(daily) != frequency_comparison_key(other_spec)


def test_common_price_rules_filters_non_target_futures() -> None:
    rows = [
        {"major": "价格", "sub": "期货价格", "title": "SHFE: 锡: 二月合约: 收盘价: 日度", "frequency": "日度", "selected": True},
    ]

    apply_common_price_rules(rows)

    assert rows[0]["selected"] is False
    assert rows[0]["reason"] == "公共价格规则：仅保留主力/01/05/09合约"


def test_common_price_rules_filters_non_target_basis_under_spread() -> None:
    rows = [
        {"major": "价格", "sub": "价差", "title": "SMM: 碳酸锂期现价差: 连一合约: 收盘价: 日度", "frequency": "日度", "selected": True},
    ]

    apply_common_price_rules(rows)

    assert rows[0]["selected"] is False
    assert rows[0]["reason"] == "公共价格规则：基差仅保留当月期现/现货升贴水"


def test_common_price_rules_keeps_generic_spread() -> None:
    rows = [
        {"major": "价格", "sub": "现货价差", "title": "SMM: 国内外ADC12即时价差: 日度", "frequency": "日度", "selected": False},
    ]

    apply_common_price_rules(rows)

    assert rows[0]["selected"] is True
    assert rows[0]["reason"] == "公共价格规则：仅保留最高频"


def test_exclude_yoy_mom_share_rows() -> None:
    rows = [
        {"title": "SMM: 碳酸锂价格同比: 日度", "selected": True},
        {"title": "SMM: 碳酸锂价格环比: 日度", "selected": True},
        {"title": "SMM: 磷酸铁锂占比: 月度", "selected": True},
        {"title": "SMM: 碳酸锂价格: 日度", "selected": True},
    ]

    exclude_yoy_mom_share_rows(rows)

    assert [row["selected"] for row in rows] == [False, False, False, True]
    assert rows[0]["reason"] == "同比/环比/占比指标不保留"


def test_exclude_supply_yoy_rows() -> None:
    rows = [
        {"major": "供给", "title": "SMM: 碳酸锂产量同比: 月度", "selected": True},
    ]

    exclude_yoy_mom_share_rows(rows)

    assert rows[0]["selected"] is False
    assert rows[0]["reason"] == "供给大类同环比指标不保留"


def test_exclude_import_export_average_rows() -> None:
    rows = [
        {"title": "中国海关: 碳酸锂进口均价: 总计: 月度", "selected": True},
        {"title": "中国海关: 碳酸锂出口均价: 总计: 月度", "selected": True},
    ]

    exclude_import_export_average_rows(rows)

    assert [row["selected"] for row in rows] == [False, False]
    assert rows[0]["reason"] == "进出口均价指标不保留"


def test_exclude_import_export_amount_rows() -> None:
    rows = [
        {"major": "进出口", "title": "中国海关: 碳酸锂进口额: 总计: 月度", "selected": True},
        {"major": "进出口", "title": "中国海关: 碳酸锂出口额: 总计: 月度", "selected": True},
        {"major": "价格", "title": "SMM: 碳酸锂价格: 日度", "selected": True},
    ]

    exclude_import_export_amount_rows(rows)

    assert [row["selected"] for row in rows] == [False, False, True]
    assert rows[0]["reason"] == "进出口金额指标不保留"


def test_lithium_excludes_electrolytic_copper() -> None:
    rows = [
        {
            "sheet": "电解铜-日",
            "title": "SMM: 电解铜价格: 日度",
            "frequency": "日度",
            "major": "价格",
            "sub": "现货价格",
        }
    ]

    processed = lithium_select_rows(rows)

    assert processed[0]["selected"] is False
    assert processed[0]["reason"] == "锂电专属规则：电解铜指标不保留"


def test_chuhuo_and_tender_classification() -> None:
    chuhuo = candidate_plan("SMM: 碳酸锂出货量: 月度", "", "lithium")
    tender = candidate_plan("SMM: 碳酸锂招标: 月度", "", "lithium")
    winning = candidate_plan("SMM: 碳酸锂中标: 月度", "", "lithium")

    assert chuhuo["major"] == "需求"
    assert chuhuo["sub"] == "出货量"
    assert tender["major"] == "需求"
    assert tender["sub"] == "招标"
    assert winning["major"] == "需求"
    assert winning["sub"] == "中标"


def test_lithium_chloride_belongs_to_salt_sector() -> None:
    assert classify_indicator_sector("锂矿-日", "SMM: 氯化锂: 价格: 日度") == "其他锂盐"


def test_volume_position_ratio_key_matches_volume_position_and_ratio() -> None:
    volume_key = volume_position_ratio_key(
        "GFEX: 工业硅: 主力合约: 成交量: 日度", "日度"
    )
    ratio_key = volume_position_ratio_key("工业硅主力合约成交持仓比", "日度")

    assert volume_key == ratio_key == "工业硅|主力合约|日度"


def test_volume_position_ratio_key_normalizes_chinese_contract_names() -> None:
    volume_key = volume_position_ratio_key(
        "GFEX: 工业硅: 一月合约: 成交量: 日度", "日度"
    )
    ratio_key = volume_position_ratio_key("工业硅01合约成交持仓比", "日度")

    assert volume_key == ratio_key == "工业硅|01合约|日度"


def test_compute_volume_position_ratio_series() -> None:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "数据"
    ws.append(["日期", "成交量", "持仓量"])
    ws.append(["", "", ""])
    ws.append(["", "", ""])
    ws.append(["2024-01-01", 100, 50])

    series = compute_ratio_series(workbook, "数据", 1, "数据", 2)

    assert series == [{"date": "2024-01-01", "value": 2.0}]


class _Cell:
    def __init__(self, value):
        self.value = value


class _FakeRow:
    def __init__(self, values):
        self.cells = [_Cell(value) for value in values]

    def __getitem__(self, index):
        return self.cells[index]


def test_find_missing_volume_position_ratio_pairs() -> None:
    volume_row = _FakeRow([None, None, "日度", 1, None, None, "工业硅", "价格", "成交量"])
    position_row = _FakeRow([None, None, "日度", 2, None, None, "工业硅", "价格", "持仓"])
    records = [
        {
            "sheet": "GFEX: 工业硅",
            "title": "GFEX: 工业硅: 主力合约: 成交量: 日度",
            "frequency": "日度",
            "sub": "成交量",
            "selected": True,
            "_row": volume_row,
        },
        {
            "sheet": "GFEX: 工业硅",
            "title": "GFEX: 工业硅: 主力合约: 持仓量: 日度",
            "frequency": "日度",
            "sub": "持仓",
            "selected": True,
            "_row": position_row,
        },
    ]

    missing = find_missing_volume_position_ratio_pairs(records)

    assert len(missing) == 1
    assert missing[0]["product"] == "工业硅"
    assert missing[0]["contract"] == "主力合约"
    assert missing[0]["volume_col"] == 1
    assert missing[0]["position_col"] == 2


def test_existing_numeric_ratio_contract_is_not_recomputed() -> None:
    volume_row = _FakeRow([None, None, "日度", 1, None, None, "工业硅", "价格", "成交量"])
    position_row = _FakeRow([None, None, "日度", 2, None, None, "工业硅", "价格", "持仓"])
    records = [
        {
            "sheet": "GFEX: 工业硅",
            "title": "GFEX: 工业硅: 一月合约: 成交量: 日度",
            "frequency": "日度",
            "sub": "成交量",
            "selected": True,
            "_row": volume_row,
        },
        {
            "sheet": "GFEX: 工业硅",
            "title": "GFEX: 工业硅: 一月合约: 持仓量: 日度",
            "frequency": "日度",
            "sub": "持仓",
            "selected": True,
            "_row": position_row,
        },
        {
            "sheet": "GFEX: 工业硅",
            "title": "工业硅01合约成交持仓比",
            "frequency": "日度",
            "sub": "成交持仓比",
            "selected": True,
        },
    ]

    assert find_missing_volume_position_ratio_pairs(records) == []
