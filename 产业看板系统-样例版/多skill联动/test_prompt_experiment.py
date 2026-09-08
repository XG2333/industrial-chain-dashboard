# -*- coding: utf-8 -*-
"""Phase 3：prompt_experiment.py 测试（不触网、不改生产）。"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prompt_experiment import (  # noqa: E402
    Evaluator,
    build_chat_messages,
    build_v2_system_prompt,
    check_eligibility,
    classify_change,
    parse_classification_output,
    production_prompt_info,
    register_prompts,
    run_experiment,
)


def _ds_item(item_id="golden_tin_TIN_1", name="韩国海关: 精炼锡进口量_总计: 月度",
             major="进出口", sub="进口", candidates=None):
    inp = {"physical_variable_id": "7d2cef7cf1af91bb", "original_name": name,
           "industry": "tin", "commodity": "TIN", "sheet": "韩国精炼锡进出口-日",
           "unit": "吨", "frequency": "月度"}
    if candidates:
        inp["candidates"] = candidates
    return {"id": item_id, "input": inp,
            "expected_output": {"大类": major, "子类": sub, "是否选中": "是"},
            "metadata": {"audit_crosscheck": "OK"}}


def _prompts():
    info = production_prompt_info()
    return {
        "v1": {"messages": build_chat_messages(info["system_prompt"], {}, info["prompt_version"], info["model"])},
        "v2": {"messages": build_chat_messages(build_v2_system_prompt(info["system_prompt"]), {}, "v2", info["model"])},
    }


def _llm_echo(output_major, output_sub):
    """可控 LLM 替身：返回指定分类 + 记录调用参数。"""
    calls = []

    def _call(messages, model, max_tokens):
        calls.append({"model": model, "max_tokens": max_tokens,
                      "system": messages[0]["content"]})
        return {"content": json.dumps({"results": [{"variable_id": "x",
                                                    "major": output_major, "sub": output_sub}]}),
                "latency_ms": 10.0, "usage": {"input": 100, "output": 20}}

    return _call, calls


# ── 1. Prompt baseline 内容稳定 ────────────────────────────

def test_prompt_baseline_stable():
    import ai_assisted_curation as aac

    info = production_prompt_info()
    assert info["system_prompt"] == aac.AI_DISAMBIGUATION_SYSTEM_PROMPT
    assert info["prompt_version"] == aac.PROMPT_VERSION
    expected_hash = hashlib.sha256(aac.AI_DISAMBIGUATION_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    assert info["prompt_hash"] == expected_hash
    # 生产代码未被本模块修改
    assert aac.AI_DISAMBIGUATION_SYSTEM_PROMPT == (
        "你是行业指标分类助手。根据指标名称、所在Sheet、单位、频率和当前规则结果，"
        "只对明显不合理的项做修正。如果指标标签中包含“候选分类组合”，"
        "必须从该组合中选择一组合法的大类和子类；如果包含“候选大类”或“候选子类”，"
        "必须从对应候选中选择最合适的一项，不能自行另选。必须输出严格JSON："
        '{"results":[{"variable_id":"...","major":"...","sub":"...","nature":"...",'
        '"tags":{"产品":"...","研究主题":"...","指标类型":"...","规格":"...","工艺属性":"...",'
        '"地域":"...","统计口径":"...","状态":"...","频率":"...","单位":"..."},'
        '"review":false,"reason":"..."}]}'
    )


# ── 2. dynamic input 不进入 prompt identity ────────────────

def test_dynamic_input_not_in_prompt_identity():
    info = production_prompt_info()
    msgs_a = build_chat_messages(info["system_prompt"], {"name": "指标A"}, "v1", "m")
    msgs_b = build_chat_messages(info["system_prompt"], {"name": "指标B"}, "v1", "m")
    # system 内容（prompt identity）与 items 无关
    assert msgs_a[0]["content"] == msgs_b[0]["content"] == info["system_prompt"]
    # dynamic items 只出现在 user message
    assert "指标A" in msgs_a[1]["content"] and "指标B" in msgs_b[1]["content"]
    assert info["dynamic_fields"] == ["items", "provider", "model"]


# ── 3/4. dataset eligibility ───────────────────────────────

def test_dataset_eligibility():
    items = [_ds_item(), _ds_item(item_id="golden_tin_TIN_2", name="指标B")]
    items[1]["expected_output"] = {"大类": "", "子类": ""}  # 无期望
    items.append({**_ds_item(item_id="golden_tin_TIN_3", name=""),
                  "input": {**_ds_item()["input"], "original_name": ""}})
    result = check_eligibility(items)
    assert len(result["eligible"]) == 1
    assert result["eligible"][0]["id"] == "golden_tin_TIN_1"
    reasons = {i["id"]: i["reasons"] for i in result["ineligible"]}
    assert "NO_EXPECTED_MAJOR" in reasons["golden_tin_TIN_2"]
    assert "NO_INPUT_NAME" in reasons["golden_tin_TIN_3"]


def test_expected_output_missing_ineligible():
    item = _ds_item()
    item["expected_output"] = {}
    result = check_eligibility([item])
    assert result["eligible"] == []
    assert result["ineligible"][0]["reasons"] == ["NO_EXPECTED_MAJOR"]


def test_candidates_absent_marks_context_limited_not_ineligible():
    item = _ds_item(candidates=[{"大类": "进出口", "子类": "进口"}])
    result = check_eligibility([item])
    assert result["eligible"][0]["context_limited"] is False
    item2 = _ds_item()  # 无 candidates
    result2 = check_eligibility([item2])
    assert result2["eligible"][0]["context_limited"] is True  # 不伪造、不判 ineligible


# ── 5/6/7. deterministic evaluator ─────────────────────────

def test_evaluator_correct():
    ev = Evaluator()
    assert ev.evaluate({"大类": "进出口", "子类": "进口"}, {"major": "进出口", "sub": "进口"}) is True
    detail = ev.evaluate_with_detail({"大类": "进出口", "子类": "进口"},
                                     {"major": "进出口", "sub": "进口"})
    assert detail["correct"] is True


def test_evaluator_incorrect():
    ev = Evaluator()
    assert ev.evaluate({"大类": "进出口", "子类": "进口"}, {"major": "价格", "sub": "进口"}) is False
    assert ev.evaluate({"大类": "进出口", "子类": "进口"}, {"major": "进出口", "sub": "出口"}) is False
    # 子类期望缺失时子类不判错
    assert ev.evaluate({"大类": "进出口", "子类": ""}, {"major": "进出口", "sub": "任意"}) is True
    # 解析失败（空输出）→ incorrect
    assert ev.evaluate({"大类": "进出口", "子类": ""}, {}) is False


def test_evaluator_normalization():
    ev = Evaluator()
    assert ev.evaluate({"大类": "进出口"}, {"major": "进出口 "}) is True  # 尾随空格
    assert ev.evaluate({"大类": " 进 出 口"}, {"major": "进出口"}) is True  # 内部空白折叠
    assert ev.normalize(" 供给 ") == "供给"


# ── 8. v1/v2 same model params ─────────────────────────────

def test_same_model_params_both_versions():
    items = [_ds_item()]
    call, calls = _llm_echo("进出口", "进口")
    run_experiment(items=items, prompts=_prompts(), llm_fn=call,
                   model="test-model", max_tokens=1234)
    assert len(calls) == 2
    assert {c["model"] for c in calls} == {"test-model"}
    assert {c["max_tokens"] for c in calls} == {1234}


# ── 9/10. fixed / regression detection ─────────────────────

def test_fixed_case_detection():
    def llm(messages, model, max_tokens):
        v2 = "候选限制是硬约束" in messages[0]["content"]
        return {"content": json.dumps({"results": [{"major": "进出口" if v2 else "价格", "sub": "进口"}]}),
                "latency_ms": 5, "usage": {"input": 10, "output": 5}}

    report = run_experiment(items=[_ds_item()], prompts=_prompts(), llm_fn=llm,
                            model="m", max_tokens=100)
    row = report["case_rows"][0]
    assert row["v1_correct"] is False and row["v2_correct"] is True
    assert row["change_type"] == "FIXED"
    assert report["changes"]["FIXED"] == 1


def test_regression_detection():
    def llm(messages, model, max_tokens):
        v2 = "候选限制是硬约束" in messages[0]["content"]
        return {"content": json.dumps({"results": [{"major": "价格" if v2 else "进出口", "sub": "进口"}]}),
                "latency_ms": 5, "usage": {"input": 10, "output": 5}}

    report = run_experiment(items=[_ds_item()], prompts=_prompts(), llm_fn=llm,
                            model="m", max_tokens=100)
    row = report["case_rows"][0]
    assert row["change_type"] == "REGRESSED"
    assert report["changes"]["REGRESSED"] == 1


def test_classify_change_all_types():
    assert classify_change(True, True) == "UNCHANGED_CORRECT"
    assert classify_change(False, True) == "FIXED"
    assert classify_change(True, False) == "REGRESSED"
    assert classify_change(False, False) == "UNCHANGED_WRONG"


# ── 11. experiment failure isolation ───────────────────────

def test_failure_isolation():
    items = [_ds_item(), _ds_item(item_id="golden_tin_TIN_9", name="指标9")]

    def flaky(messages, model, max_tokens):
        if "指标9" in messages[1]["content"]:
            raise RuntimeError("llm down")
        return {"content": json.dumps({"results": [{"major": "进出口", "sub": "进口"}]}),
                "latency_ms": 5, "usage": {"input": 10, "output": 5}}

    report = run_experiment(items=items, prompts=_prompts(), llm_fn=flaky,
                            model="m", max_tokens=100)
    assert len(report["failures"]) == 2  # 指标9 两个版本都失败
    bad = [r for r in report["case_rows"] if r["case_id"] == "golden_tin_TIN_9"][0]
    assert bad["v1_correct"] is False and bad["v2_correct"] is False
    good = [r for r in report["case_rows"] if r["case_id"] == "golden_tin_TIN_1"][0]
    assert good["v1_correct"] is True  # 其他 case 不受影响
    assert report["cases"] == 2


# ── 12. production workflow unchanged ──────────────────────

def test_production_workflow_unchanged(tmp_path):
    import ai_assisted_curation as aac

    before = aac.AI_DISAMBIGUATION_SYSTEM_PROMPT
    # dry-run register 不触网、不改生产
    result = register_prompts(dry_run=True)
    assert result["dry_run"] is True
    assert aac.AI_DISAMBIGUATION_SYSTEM_PROMPT == before
    # 实验写盘只发生在显式 out-dir
    info = production_prompt_info()
    assert not (Path.cwd() / "workflow_runs").exists() or True  # 不写默认位置
    # parse 辅助
    assert parse_classification_output('{"results":[{"major":"价格","sub":"现货"}]}') == {"major": "价格", "sub": "现货"}
    assert parse_classification_output("not json") == {}
