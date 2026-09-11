# -*- coding: utf-8 -*-
"""Phase 3b：dataset_enrich.py + prompt_experiment 生产上下文映射测试（不触网）。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dataset_enrich import (  # noqa: E402
    ALLOWED_MAJORS,
    CONTEXT_HISTORICAL_EXACT,
    CONTEXT_UNAVAILABLE,
    enrich_case,
    load_directory_tags,
    summarize,
)
from prompt_experiment import (  # noqa: E402
    check_eligibility,
    experiment_item_from_dataset,
)


def _hc(name="韩国海关: 精炼锡进口量_总计: 月度", vid="7d2cef7cf1af91bb", major="进出口",
        sub="进口", crosscheck="OK", run="run123"):
    return {
        "source_case_id": "priority_tin_TIN_1", "workflow_run_id": run,
        "original_name": name, "physical_variable_id": vid,
        "match_method": "NAME_UNIQUE_RUN_LOCAL", "sheet": "韩国精炼锡进出口-日",
        "unit": "吨", "frequency": "月度", "human_decision": "CONFIRMED",
        "human_major": major, "human_sub": sub, "human_selected": "是",
        "human_notes": "", "audit_crosscheck": crosscheck,
        "industry": "tin", "commodity": "TIN",
    }


def _dir_info(name, combos=None, major="进出口", sub="进口"):
    combos = combos if combos is not None else [{"大类": "进出口", "子类": "进口"}]
    return {name: {"tags": {"候选分类组合": combos,
                            "候选大类": [c["大类"] for c in combos],
                            "候选子类": [c["子类"] for c in combos]},
                   "major": major, "sub": sub}}


def _enriched(hc=None, combos=None, v1=None):
    return enrich_case(hc or _hc(), _dir_info((hc or _hc())["original_name"], combos), v1)


# ── 1. production input schema ─────────────────────────────

def test_experiment_item_maps_candidates_to_tags():
    item = {"id": "x", "input": {
        "physical_variable_id": "vid1", "original_name": "指标A", "industry": "tin",
        "commodity": "TIN", "sheet": "S", "unit": "吨", "frequency": "月度",
        "current_major": "其他", "current_sub": "其他",
        "candidates": [{"大类": "进出口", "子类": "进口"}],
        "current_tags": {"候选大类": ["进出口"]},
    }, "expected_output": {"大类": "进出口"}}
    exp = experiment_item_from_dataset(item)
    assert exp["current_tags"]["候选分类组合"] == [{"大类": "进出口", "子类": "进口"}]
    assert exp["current_major"] == "其他" and exp["current_sub"] == "其他"
    assert exp["name"] == "指标A" and exp["unit"] == "吨"


# ── 2. historical exact recovery ───────────────────────────

def test_historical_exact_recovery(tmp_path):
    # final_output.xlsx（原 run 的 indicator_tags 产物）→ 候选恢复
    from openpyxl import Workbook

    xlsx = tmp_path / "final_output.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "指标目录"
    ws.append(["#", "Sheet Name", "Freq", "Col", "Indicator Name", "Unit", "板块",
               "大类", "子类", "数据性质", "是否选中", "状态说明", "指标标签"])
    ws.append([1, "S", "月度", 1, "韩国海关: 精炼锡进口量_总计: 月度", "吨", "tin",
               "进出口", "进口", "水平值", "是", "", json.dumps(
                   {"候选分类组合": [{"大类": "进出口", "子类": "进口"}],
                    "候选大类": ["进出口"], "候选子类": ["进口"]}, ensure_ascii=False)])
    wb.save(xlsx)
    info = load_directory_tags(xlsx)
    assert info["韩国海关: 精炼锡进口量_总计: 月度"]["tags"]["候选分类组合"] == [
        {"大类": "进出口", "子类": "进口"}]
    item = enrich_case(_hc(), info, None)
    assert item["metadata"]["context_status"] == CONTEXT_HISTORICAL_EXACT
    assert item["input"]["candidates"] == [{"大类": "进出口", "子类": "进口"}]
    assert item["input"]["current_major"] == "进出口"


# ── 3. unavailable context 不伪造 ──────────────────────────

def test_unavailable_context_not_fabricated():
    hc = _hc(name="找不到的指标", vid="ffffffffffffffff")
    item = enrich_case(hc, {}, None)
    assert item["metadata"]["context_status"] == CONTEXT_UNAVAILABLE
    assert item["input"]["candidates"] == []
    assert item["metadata"]["eligibility"] == "context_limited"


# ── 4. expected output 不参与 candidate reconstruction ────

def test_expected_not_used_in_candidates():
    # 期望是 成本利润/利润，但 run 候选是 进出口/进口 —— 候选不得被期望改写
    hc = _hc(major="成本利润", sub="利润")
    item = enrich_case(hc, _dir_info(hc["original_name"],
                                     combos=[{"大类": "进出口", "子类": "进口"}]), None)
    assert item["input"]["candidates"] == [{"大类": "进出口", "子类": "进口"}]
    assert item["expected_output"]["大类"] == "成本利润"  # expected 保持独立
    assert item["metadata"]["expected_in_candidates"] is False


# ── 5. context provenance ──────────────────────────────────

def test_context_provenance_fields():
    item = _enriched()
    md = item["metadata"]
    assert md["context_status"] == CONTEXT_HISTORICAL_EXACT
    assert md["candidate_provenance"] == "run_artifact:indicator_tags:final_output.xlsx"
    assert md["source_artifact"] == "final/final_output.xlsx"
    assert md["reconstruction_version"] == "2.0"
    assert md["schema_version"] == "2.0"
    assert md["source_case_id"] == "priority_tin_TIN_1"


# ── 6. expected_in_candidates ──────────────────────────────

def test_expected_in_candidates():
    item = _enriched()
    assert item["metadata"]["expected_in_candidates"] is True
    item2 = _enriched(combos=[{"大类": "价格", "子类": "现货价格"}])
    assert item2["metadata"]["expected_in_candidates"] is False


# ── 7/8. eligibility 分层 ─────────────────────────────────

def test_eligibility_layers():
    pe = _enriched()
    pe_item = {"id": pe["id"], "input": pe["input"], "expected_output": pe["expected_output"],
               "metadata": pe["metadata"]}
    cl = enrich_case(_hc(name="无候选指标", vid="aaaa000000000000"), {}, None)
    cl_item = {"id": cl["id"], "input": cl["input"], "expected_output": cl["expected_output"],
               "metadata": cl["metadata"]}
    result = check_eligibility([pe_item, cl_item])
    layers = {i["eligibility"] for i in result["eligible"]}
    assert "production_equivalent" in layers
    assert "context_limited" in layers
    # context_limited 不进 production_equivalent 子集
    pe_subset = [i for i in result["eligible"] if i["eligibility"] == "production_equivalent"]
    assert len(pe_subset) == 1 and pe_subset[0]["id"] == pe["id"]


# ── 9. root cause classification ───────────────────────────

def test_root_cause_classification():
    hc = _hc()
    # WRONG_CANDIDATES：候选存在但期望不在
    w = enrich_case(hc, _dir_info(hc["original_name"], combos=[{"大类": "价格", "子类": "现货"}]),
                    {"v1_correct": False, "v1_output": {"major": "价格", "sub": "现货"}})
    assert w["metadata"]["root_cause"] == "WRONG_CANDIDATES"
    # PROMPT_SELECTION_ERROR：期望在候选但模型选错
    p = enrich_case(hc, _dir_info(hc["original_name"]), {"v1_correct": False, "v1_output": {"major": "价格"}})
    assert p["metadata"]["root_cause"] == "PROMPT_SELECTION_ERROR"
    # OUTPUT_PARSE_ERROR：期望在候选但输出不可解析
    o = enrich_case(hc, _dir_info(hc["original_name"]), {"v1_correct": False, "v1_output": {}})
    assert o["metadata"]["root_cause"] == "OUTPUT_PARSE_ERROR"
    # CORRECT
    c = enrich_case(hc, _dir_info(hc["original_name"]), {"v1_correct": True, "v1_output": {"major": "进出口"}})
    assert c["metadata"]["root_cause"] == "CORRECT"
    # 无实验输出 → UNKNOWN_NO_EXPERIMENT
    u = enrich_case(hc, _dir_info(hc["original_name"]), None)
    assert u["metadata"]["root_cause"] == "UNKNOWN_NO_EXPERIMENT"
    # 期望不在合法大类 → EXPECTED_LABEL_MISMATCH
    e = enrich_case(_hc(major="不存在的类", sub="x"), _dir_info(hc["original_name"],
                                                              combos=[{"大类": "不存在的类", "子类": "x"}]),
                    {"v1_correct": False, "v1_output": {"major": "不存在的类"}})
    assert e["metadata"]["root_cause"] == "EXPECTED_LABEL_MISMATCH"
    assert "进出口" in ALLOWED_MAJORS


# ── 10. Dataset v1 preserved ───────────────────────────────

def test_dataset_v1_preserved():
    item = _enriched()
    assert item["metadata"]["preserved_v1"] == {
        "schema_version": "1.0",
        "expected_output": {"大类": "进出口", "子类": "进口", "是否选中": "是"},
    }


# ── 11. production workflow unchanged ──────────────────────

def test_production_workflow_unchanged(tmp_path):
    import ai_assisted_curation as aac

    before = aac.AI_DISAMBIGUATION_SYSTEM_PROMPT
    items = [_enriched(), _enriched(hc=_hc(name="B", vid="bbbbbbbbbbbbbbbb"))]
    summary = summarize(items)
    assert summary["eligible_layers"]["production_equivalent"] == 2
    assert aac.AI_DISAMBIGUATION_SYSTEM_PROMPT == before  # 生产 Prompt 未动
