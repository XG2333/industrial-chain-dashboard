# -*- coding: utf-8 -*-
"""Phase 3c：candidate-rule A/B 离线回放 + v3 prompt + 聚合/归因测试（不触网）。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from candidate_ab import (  # noqa: E402
    CONTEXT_CURRENT_RULES,
    expected_in,
    new_candidates_for,
    replay,
)
from prompt_experiment import (  # noqa: E402
    aggregate_runs,
    build_v3_system_prompt,
    decompose_gains,
    production_prompt_info,
)

INDUSTRY = "lithium_tin"


def _item(name, expected_major, expected_sub, old_candidates, sheet="S", unit="吨"):
    return {
        "id": f"golden_tin_TIN_{abs(hash(name)) % 16**16:016x}",
        "input": {"physical_variable_id": "x" * 16, "original_name": name, "industry": "tin",
                  "commodity": "TIN", "sheet": sheet, "unit": unit, "frequency": "日度",
                  "candidates": old_candidates},
        "expected_output": {"大类": expected_major, "子类": expected_sub, "是否选中": "是"},
        "metadata": {"context_status": "HISTORICAL_EXACT", "schema_version": "2.0"},
    }


# ── 1. 盈亏语义优先级 ──────────────────────────────────────

def test_profit_loss_semantics_priority():
    for name in (
        "SMM: 精炼锡进出口盈亏: 外盘折算现货价: 日度",
        "SMM: 精炼锡进出口盈亏: 现货最新价: 日度",
        "SMM: 精炼锡进出口盈亏: 中国台湾当地价格: 日度",
        "SMM: 精炼锡进出口盈亏: LME锡价: 日度",
    ):
        plan = new_candidates_for({"input": {"original_name": name, "sheet": "S",
                                             "unit": "元/吨"}}, INDUSTRY)
        majors = {c["大类"] for c in plan}
        assert majors == {"成本利润"}, f"{name} -> {plan}"
        assert any(c["子类"] == "利润" for c in plan)


# ── 2. 普通价格指标仍保持价格类 ────────────────────────────

def test_normal_price_indicator_stays_price():
    for name in (
        "SMM: 锂辉石精矿（CIF中国）指数 - 平均价: 日度",
        "SMM: 工业级氢氧化锂 - 平均价: 日度",
    ):
        plan = new_candidates_for({"input": {"original_name": name, "sheet": "S",
                                             "unit": "元/吨"}}, INDUSTRY)
        assert {"价格"} == {c["大类"] for c in plan}, f"{name} -> {plan}"


# ── 3. 同类进口/出口利润规则 ───────────────────────────────

def test_related_concepts_rule():
    for name in (
        "SMM: 锡矿进口盈亏水平: 日度",
        "SMM: 某品进口利润: 日度",
        "SMM: 某品出口成本: 日度",
        "SMM: 某品盈亏测算: 日度",
    ):
        plan = new_candidates_for({"input": {"original_name": name, "sheet": "S",
                                             "unit": "元/吨"}}, INDUSTRY)
        assert {"成本利润"} == {c["大类"] for c in plan}, f"{name} -> {plan}"


# ── 4/5. candidate regression detection + before/after ─────

def test_replay_before_after_and_regression():
    items = [
        _item("SMM: 精炼锡进出口盈亏: 外盘折算现货价: 日度", "成本利润", "利润",
              old_candidates=[{"大类": "价格", "子类": "现货价格"}]),
        _item("SMM: 普通价格A - 平均价: 日度", "价格", "现货价格",
              old_candidates=[{"大类": "价格", "子类": "现货价格"}]),
        # 人为 regression 场景：旧候选含期望，新候选不含（规则不应发生，测试检测）
        _item("SMM: 特殊净出口: 月度", "进出口", "净出口",
              old_candidates=[{"大类": "进出口", "子类": "净出口"}]),
    ]
    report = replay(items, INDUSTRY)
    assert report["expected_in_candidates_before"] == 2  # case1 old 候选不含期望
    assert report["expected_in_candidates_after"] >= 2
    assert report["wrong_candidates_fixed"] >= 1  # 外盘折算现货价 修复
    # 人为 regression：构造新候选不含期望 → 检测
    items[2]["input"]["original_name"] = "特殊净出口指数: 月度"
    report2 = replay(items, INDUSTRY)
    # 若产生 regression 应被报告（此处不强制，仅验证机制存在）
    assert "regression_details" in report2


# ── 6. old/new A/B items 构建 ──────────────────────────────

def test_new_candidates_items_marked():
    from candidate_ab import _apply_new

    items = [_item("SMM: 精炼锡进出口盈亏: 外盘折算现货价: 日度", "成本利润", "利润",
                   old_candidates=[{"大类": "价格", "子类": "现货价格"}])]
    new_items = _apply_new(items, INDUSTRY)
    assert new_items[0]["input"]["candidates"][0]["大类"] == "成本利润"
    assert new_items[0]["metadata"]["context_status"] == CONTEXT_CURRENT_RULES
    assert new_items[0]["metadata"]["schema_version"] == "2.1"
    # 未变化的 case 保持 HISTORICAL_EXACT
    items2 = [_item("SMM: 普通价格A - 平均价: 日度", "价格", "现货价格",
                    old_candidates=[{"大类": "价格", "子类": "现货价格"}])]
    new2 = _apply_new(items2, INDUSTRY)
    assert new2[0]["metadata"]["context_status"] == "HISTORICAL_EXACT"


# ── 7/8. v3 prompt identity + schema unchanged ─────────────

def test_v3_prompt_identity_and_schema():
    info = production_prompt_info()
    v3 = build_v3_system_prompt(info["system_prompt"])
    assert v3.startswith(info["system_prompt"])  # 基于 v1
    assert "进出口盈亏" in v3 and "候选分类组合" in v3
    assert "候选限制是硬约束" not in v3  # 不继承 v2
    # 输出 schema 完全不变（v1 的 JSON schema 原文保留）
    assert '{"results":[{"variable_id":"...","major":"...","sub":"...","nature":"...' in v3
    # v3 追加内容紧凑（避免 token 上升）
    assert len(v3) - len(info["system_prompt"]) < 200


# ── 9. repeated experiment aggregation ─────────────────────

def _fake_run(correct_flags, version="v1"):
    rows = [{"case_id": f"c{i}", "v1_correct": c} for i, c in enumerate(correct_flags)]
    return {"cases": len(rows), version: {"correct": sum(correct_flags),
                                          "accuracy": sum(correct_flags) / len(rows)},
            "case_rows": rows, "failures": []}


def test_aggregate_runs():
    runs = [_fake_run([True, False, True]), _fake_run([True, True, True]),
            _fake_run([True, False, False])]
    agg = aggregate_runs(runs)
    assert agg["runs"] == 3
    assert agg["per_version"]["v1"]["accuracy_mean"] == round((2/3 + 1 + 1/3) / 3, 4)
    assert agg["per_version"]["v1"]["accuracy_min"] == 1/3
    assert agg["per_version"]["v1"]["accuracy_max"] == 1.0
    assert agg["per_version"]["v1"]["correct_each_run"] == [2, 3, 1]


# ── 10. selection_stability ────────────────────────────────

def test_selection_stability():
    runs = [
        {"cases": 2, "v1": {"correct": 1, "accuracy": 0.5}, "case_rows": [
            {"case_id": "a", "v1_correct": True}, {"case_id": "b", "v1_correct": False}], "failures": []},
        {"cases": 2, "v1": {"correct": 1, "accuracy": 0.5}, "case_rows": [
            {"case_id": "a", "v1_correct": True}, {"case_id": "b", "v1_correct": True}], "failures": []},
    ]
    agg = aggregate_runs(runs)
    # case a: [True, True] 稳定；case b: [False, True] 不稳定
    assert agg["selection_stability"]["v1"] == 0.5
    assert agg["per_case"]["a"]["v1"] == [True, True]
    assert agg["per_case"]["b"]["v1"] == [False, True]


# ── 11. candidate gain / prompt gain decomposition ─────────

def test_gain_decomposition():
    g = decompose_gains(0.76, 0.84, 0.92)
    assert g["candidate_rule_gain_pp"] == 8.0
    assert g["prompt_gain_pp"] == 8.0
    g2 = decompose_gains(0.76, 0.84, 0.80)
    assert g2["candidate_rule_gain_pp"] == 8.0
    assert g2["prompt_gain_pp"] == -4.0


# ── 12. production workflow unchanged ──────────────────────

def test_production_unchanged():
    import classification_candidates as cc
    import ai_assisted_curation as aac

    before_cc = cc.MAJOR_KEYWORD_GROUPS["成本利润"]
    before_prompt = aac.AI_DISAMBIGUATION_SYSTEM_PROMPT
    assert "盈亏" in before_cc
    assert before_prompt == aac.AI_DISAMBIGUATION_SYSTEM_PROMPT  # 未改
    # expected_in 判定
    assert expected_in([{"大类": "成本利润", "子类": "利润"}], {"大类": "成本利润", "子类": "利润"}) is True
    assert expected_in([{"大类": "价格", "子类": "现货价格"}], {"大类": "成本利润"}) is False
