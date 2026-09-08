from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from classification_candidates import candidate_plan  # noqa: E402
from lithium_rules import classify_major as lithium_major, classify_sub as lithium_sub  # noqa: E402
from tin_rules import (  # noqa: E402
    classify_major as tin_major,
    classify_sub as tin_sub,
    evaluate_selection,
)


def test_tin_trading_metrics_are_price() -> None:
    plan = candidate_plan("锡主力合约成交持仓比", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "成交持仓比")

    plan = candidate_plan("SHFE: 锡: 主力合约: 成交量: 日度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "成交量")

    plan = candidate_plan("SHFE: 锡: 主力合约: 持仓量: 日度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "持仓")


def test_lme_tin_trading_metrics_are_price() -> None:
    plan = candidate_plan("LME锡成交持仓比", "LME锡价格-日", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "成交持仓比")

    plan = candidate_plan("LME: 锡_成交量（手）: 日度", "LME锡价格-日", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "成交量")

    plan = candidate_plan("LME: 锡_持仓量: 日度", "LME锡价格-日", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "持仓")


def test_lithium_trading_metrics_use_same_public_rule() -> None:
    plan = candidate_plan("碳酸锂主力合约成交持仓比", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "成交持仓比")


def test_tin_trading_metric_selection() -> None:
    assert evaluate_selection("价格", "成交持仓比", "锡主力合约成交持仓比", "日度")[0]
    assert evaluate_selection("价格", "成交量", "SHFE: 锡: 主力合约: 成交量: 日度", "日度")[0]
    assert not evaluate_selection("价格", "成交量", "LME: 锡_成交量（手）: 日度", "日度")[0]


def test_basis_merged_into_spread_for_lithium_tin() -> None:
    plan = candidate_plan(
        "SMM: 电池级碳酸锂期现价差（现货-期货）: 日度",
        "碳酸锂基差-日",
        "lithium_tin",
    )
    assert (plan["major"], plan["sub"]) == ("价格", "价差")


def test_basis_merged_into_spot_spread_for_silicon() -> None:
    plan = candidate_plan(
        "SMM: 多晶硅期现价差: 当月合约: 收盘价: 日度",
        "工业硅期货价格+基差+月差-日",
        "silicon",
    )
    assert (plan["major"], plan["sub"]) == ("价格", "现货价差")


def test_net_export_is_deterministic_subclass() -> None:
    plan = candidate_plan("日本海关 碳酸锂净出口: 月度", "净出口计算", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("进出口", "净出口")

    plan = candidate_plan("中国海关 多晶硅净出口: 月度", "净出口计算", "silicon")
    assert (plan["major"], plan["sub"]) == ("进出口", "净出口")


def test_import_export_amount_is_price_trade_amount() -> None:
    plan = candidate_plan("中国海关: 锂精矿月度进口额", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "贸易金额")

    plan = candidate_plan("中国海关: 磷酸出口额", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "贸易金额")

    plan = candidate_plan("中国海关: 多晶硅进口总额", "", "silicon")
    assert (plan["major"], plan["sub"]) == ("价格", "贸易金额")


def test_import_export_average_is_price_spot() -> None:
    plan = candidate_plan("中国海关: 碳酸锂进口均价: 月度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("价格", "现货价格")


def test_import_export_profit_wins_over_trade_keyword() -> None:
    plan = candidate_plan("SMM: 碳酸锂进口利润: 月度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("成本利润", "利润")

    plan = candidate_plan("SMM: 精炼锡出口盈亏: 月度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("成本利润", "利润")


def test_import_export_quantity_stays_in_trade_flow() -> None:
    plan = candidate_plan("中国海关: 碳酸锂进口量: 月度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("进出口", "进口")

    plan = candidate_plan("中国海关: 碳酸锂净出口量: 月度", "", "lithium_tin")
    assert (plan["major"], plan["sub"]) == ("进出口", "净出口")


def test_lithium_and_tin_rules_reclassify_amount() -> None:
    for classify_major, classify_sub in ((lithium_major, lithium_sub), (tin_major, tin_sub)):
        assert classify_major("中国海关: 锂精矿进口额", "") == "价格"
        assert classify_sub("价格", "中国海关: 锂精矿进口额", "") == "贸易金额"
        assert classify_major("中国海关: 锂精矿进口均价", "") == "价格"
        assert classify_sub("价格", "中国海关: 锂精矿进口均价", "") == "现货价格"
        assert classify_major("SMM: 锡矿进口利润", "") == "成本利润"
        assert classify_sub("成本利润", "SMM: 锡矿进口利润", "") == "利润"


def test_parenthetical_market_share_does_not_override_core_metric() -> None:
    plan = candidate_plan("SMM: 样本锂云母矿山总产量（市占率约65%）: 月度", "")
    assert (plan["major"], plan["sub"]) == ("供给", "产量")

    plan = candidate_plan(
        "SMM: 样本锂云母矿山总产量（市占率约65%）: 月度",
        "",
        "lithium_tin",
        "碳酸锂当量（吨）",
    )
    assert (plan["major"], plan["sub"]) == ("供给", "产量")

    plan = candidate_plan("样本辉石矿山产量", "")
    assert (plan["major"], plan["sub"]) == ("供给", "产量")

    plan = candidate_plan("锂云母总产量", "")
    assert (plan["major"], plan["sub"]) == ("供给", "产量")


def test_cr5_share_is_not_plain_production() -> None:
    plan = candidate_plan("氢氧化锂产量CR5占比", "")
    assert plan["major"] == "供给"
    assert plan["sub"] != "产量"
    assert plan["sub"] == "集中度"

    plan = candidate_plan("氢氧化锂产量CR5占比", "", "lithium_tin", "%")
    assert plan["sub"] == "集中度"

    plan = candidate_plan("氢氧化锂产量CR5占比", "", "lithium_tin", "吨")
    assert plan["sub"] != "产量"


def test_consumer_artificial_graphite_price_is_price_not_demand() -> None:
    for grade in ("中端", "低端", "高端"):
        plan = candidate_plan(
            f"SMM: {grade}消费人造石墨 - 平均价: 日度",
            "负极价格-日",
            unit="元/吨",
        )
        assert (plan["major"], plan["sub"]) == ("价格", "现货价格")

    plan = candidate_plan("SMM: 碳酸锂消费量: 月度", "", unit="吨")
    assert plan["major"] == "需求"

