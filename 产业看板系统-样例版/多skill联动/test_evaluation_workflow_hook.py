# -*- coding: utf-8 -*-
"""Phase 2c：生产 Evaluation 闭环（auto correlation + auto scores）测试（不触网）。"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluation_backfill import auto_write_scores, run_auto_evaluation  # noqa: E402
from evaluation_correlation import (  # noqa: E402
    correlate_items,
    index_catalog,
    physical_variable_id,
)

RAW_HASH = "ab" * 32
SHORT_ID = "abcdef123456"
RUN_NAME = f"20260831T060000Z_{SHORT_ID}"
VID = physical_variable_id(RAW_HASH, "价格-日", 3, "SMM: 碳酸锂价格: 日度")
PROMPT_VERSION = "ai_assisted_curation_v1"
PROMPT_HASH = "h" * 64
OBS_ID = "obs1234567890abcdef"


def _catalog_rows():
    return [{"sheet": "价格-日", "col": 3, "name": "SMM: 碳酸锂价格: 日度", "unit": "元/吨", "freq": "日度"}]


def _items():
    return [{"variable_id": "local000000000001", "name": "SMM: 碳酸锂价格: 日度",
             "sheet": "价格-日", "unit": "元/吨", "frequency": "日度",
             "sector": "", "current_major": "", "current_sub": ""}]


def _gen_input(items):
    return [{"role": "user", "content": json.dumps({"provider": "deepseek", "model": "m", "items": items})}]


def _trace_with_generations(n=1):
    gens = []
    for i in range(n):
        gens.append({
            "id": OBS_ID if i == 0 else f"obs_other{i}",
            "type": "GENERATION", "name": "llm.ai_disambiguation",
            "model": "deepseek-v4-flash",
            "metadata": {"workflow_run_id": SHORT_ID, "stage": "ai_disambiguation",
                         "prompt_name": "ai_disambiguation", "prompt_version": PROMPT_VERSION,
                         "prompt_hash": PROMPT_HASH},
            "input": _gen_input(_items()),
            "output": json.dumps({"results": [{"variable_id": "local000000000001",
                                               "major": "价格", "sub": "现货价格", "nature": "水平值"}]}),
        })
    return {"id": hashlib.md5(SHORT_ID.encode()).hexdigest(), "name": "workflow.lithium", "observations": gens}


def _corr_rows():
    return correlate_items(
        workflow_run_id=SHORT_ID, industry="lithium", stage="ai_disambiguation",
        observation_id=OBS_ID, trace_id=hashlib.md5(SHORT_ID.encode()).hexdigest(),
        batch_index_start=0, prompt_name="ai_disambiguation", prompt_version=PROMPT_VERSION,
        prompt_hash=PROMPT_HASH, model="deepseek-v4-flash", items=_items(),
        catalog_index=index_catalog(_catalog_rows()), raw_file_hash=RAW_HASH,
    )


def _finding(vid, verdict="PASS", disposition="EXPECTED_TRANSFORMATION", issue="X"):
    return {"finding_id": f"a:V:{issue}:{vid}", "physical_variable_id": vid,
            "original_name": "SMM: 碳酸锂价格: 日度", "verdict": verdict,
            "final_disposition": disposition, "issue_type": issue}


def _golden(vid, status="CONFIRMED", expected=None):
    return {"case_id": f"golden_lithium_LI_{vid}", "expected_status": status,
            "expected_category": (expected or {}).get("category"),
            "expected_subcategory": (expected or {}).get("subcategory"),
            "expected_selected": (expected or {}).get("selected"),
            "expected_rule_ids": ["AI_001"]}


def _human(vid, decision="CONFIRMED", major="价格", sub="现货价格"):
    return {"physical_variable_id": vid, "original_name": "SMM: 碳酸锂价格: 日度",
            "human_decision": decision, "human_major": major, "human_sub": sub,
            "human_selected": "是", "source_case_id": "priority_tin_TIN_0",
            "match_method": "NAME_UNIQUE_RUN_LOCAL"}


class Recorder:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)


# ── 1. evaluation disabled → workflow unchanged ────────────

def test_evaluation_disabled_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_EVALUATION_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    # 未开启时 pipeline 不调用 hook —— 直接验证 gate 逻辑
    import run_industry_pipeline

    assert run_industry_pipeline.evaluation_enabled(False) is False
    monkeypatch.setenv("LANGFUSE_EVALUATION_ENABLED", "true")
    assert run_industry_pipeline.evaluation_enabled(False) is True
    assert run_industry_pipeline.evaluation_enabled(True) is True


# ── 2. Langfuse unavailable → workflow unchanged ───────────

def test_langfuse_unavailable_no_crash(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    run_dir = tmp_path / RUN_NAME
    (run_dir / "audit").mkdir(parents=True)
    (run_dir / "audit" / "audit_report.json").write_text(json.dumps(
        {"manifest": {"audit_run_id": "audit_t"}, "findings": []}), encoding="utf-8")
    (run_dir / "audit" / "golden").mkdir(parents=True)
    (run_dir / "audit" / "golden" / "golden_cases.jsonl").write_text("", encoding="utf-8")
    result = run_auto_evaluation(run_dir=run_dir, write_scores=True)
    assert result["correlation"]["trace_status"] == "LANGFUSE_DISABLED"
    assert result["scores"] is None or result["scores"].get("written_count", 0) == 0
    final = tmp_path / "final_output.xlsx"
    final.write_bytes(b"out")
    assert final.read_bytes() == b"out"


# ── 3. correlation auto generated ──────────────────────────

def test_correlation_auto_generated(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    run_dir = tmp_path / RUN_NAME
    (run_dir / "audit" / "golden").mkdir(parents=True)
    (run_dir / "audit" / "audit_report.json").write_text(json.dumps(
        {"manifest": {"audit_run_id": "audit_t", "raw_file_hash": RAW_HASH, "industry": "lithium"},
         "findings": [_finding(VID)]}), encoding="utf-8")
    (run_dir / "audit" / "golden" / "golden_cases.jsonl").write_text(
        json.dumps(_golden(VID)) + "\n", encoding="utf-8")
    (run_dir / "02_financial_variable_curation").mkdir(parents=True)
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["#", "Sheet Name", "Freq", "Col", "Indicator Name", "Unit"])
    ws.append(["价格-日", None, None, None, None, None])
    ws.append([1, "价格-日", "日度", 3, "SMM: 碳酸锂价格: 日度", "元/吨"])
    wb.save(run_dir / "02_financial_variable_curation" / "directory_marked.xlsx")

    import evaluation_backfill

    _trace = _trace_with_generations()
    monkeypatch.setattr(
        evaluation_backfill.LangfuseReader, "fetch_trace",
        lambda self, tid: _trace if tid == _trace["id"] else None,
    )
    result = run_auto_evaluation(run_dir=run_dir, write_scores=False)
    eval_dir = run_dir / "audit" / "evaluation"
    assert (eval_dir / "correlation_index.jsonl").exists()
    assert (eval_dir / "evaluation_dry_run.json").exists()
    assert result["correlation"]["trace_status"] == "TRACE_FOUND"
    assert result["correlation"]["generations"] == 1


# ── 4. no generation → no score ────────────────────────────

def test_no_generation_no_score():
    rec = Recorder()
    result = auto_write_scores(
        corr_rows=[], human_rows=[_human(VID)], findings={}, golden={},
        audit_run_id="audit_t", record_fn=rec,
    )
    assert result["written_count"] == 0
    assert rec.calls == []


# ── 5. unique generation → score ───────────────────────────

def test_unique_generation_writes_score():
    rec = Recorder()
    rows = _corr_rows()
    rows[0]["ai_major"], rows[0]["ai_sub"] = "价格", "现货价格"
    result = auto_write_scores(
        corr_rows=rows, human_rows=[_human(VID)], findings={VID: [_finding(VID)]},
        golden={VID: _golden(VID, expected={"category": "价格", "subcategory": "现货价格"})},
        audit_run_id="audit_t", record_fn=rec,
    )
    names = {c["score_name"] for c in rec.calls}
    assert result["written_count"] >= 5
    assert "verifier_status" in names
    assert "verifier_classification_correct" in names  # 期望存在 + AI 结果 → 可写
    assert "human_decision" in names and "human_classification_correct" in names


# ── 6. ambiguous → no score ────────────────────────────────

def test_ambiguous_no_score():
    rec = Recorder()
    cat = _catalog_rows() + [{"sheet": "价格-日", "col": 9, "name": "SMM: 碳酸锂价格: 日度",
                              "unit": "元/吨", "freq": "日度"}]
    rows = correlate_items(
        workflow_run_id=SHORT_ID, industry="lithium", stage="ai_disambiguation",
        observation_id=OBS_ID, batch_index_start=0, prompt_name="ai_disambiguation",
        prompt_version=PROMPT_VERSION, prompt_hash=PROMPT_HASH, model="m", items=_items(),
        catalog_index=index_catalog(cat), raw_file_hash=RAW_HASH,
    )
    result = auto_write_scores(
        corr_rows=rows, human_rows=[], findings={}, golden={},
        audit_run_id="audit_t", record_fn=rec,
    )
    assert result["written_count"] == 0
    assert result["skip_reasons"].get("AMBIGUOUS_TRIPLE", 0) == 1


# ── 7. verifier ERROR → no correctness ─────────────────────

def test_verifier_error_no_correctness():
    rec = Recorder()
    rows = _corr_rows()
    rows[0]["ai_major"], rows[0]["ai_sub"] = "价格", "现货价格"
    result = auto_write_scores(
        corr_rows=rows, human_rows=[], findings={VID: [_finding(VID, verdict="ERROR",
                                                                disposition="CONFIRMED_ERROR")]},
        golden={VID: _golden(VID, expected={"category": "价格", "subcategory": "现货价格"})},
        audit_run_id="audit_t", record_fn=rec,
    )
    names = {c["score_name"] for c in rec.calls}
    assert "verifier_status" in names  # 非 correctness 仍写
    assert "verifier_classification_correct" not in names  # ERROR 不推导 false
    assert result["skip_reasons"].get("VERIFIER_FLAGGED_NEEDS_REVIEW", 0) == 1


# ── 8. human UNRESOLVED → decision only ────────────────────

def test_human_unresolved_decision_only():
    rec = Recorder()
    rows = _corr_rows()
    rows[0]["ai_major"], rows[0]["ai_sub"] = "价格", "现货价格"
    result = auto_write_scores(
        corr_rows=rows, human_rows=[_human(VID, decision="UNRESOLVED")],
        findings={}, golden={}, audit_run_id="audit_t", record_fn=rec,
    )
    names = {c["score_name"] for c in rec.calls}
    assert "human_decision" in names
    assert "human_classification_correct" not in names
    assert result["skip_reasons"].get("HUMAN_UNRESOLVED", 0) == 1


# ── 9. repeated run → idempotent score payload ─────────────

def test_repeated_run_idempotent_scores():
    rec1, rec2 = Recorder(), Recorder()
    rows = _corr_rows()
    rows[0]["ai_major"], rows[0]["ai_sub"] = "价格", "现货价格"
    kwargs = dict(corr_rows=rows, human_rows=[], findings={VID: [_finding(VID)]},
                  golden={VID: _golden(VID, expected={"category": "价格", "subcategory": "现货价格"})},
                  audit_run_id="audit_t")
    auto_write_scores(**kwargs, record_fn=rec1)
    auto_write_scores(**kwargs, record_fn=rec2)
    # 两次调用 payload 完全一致（score_id 由 record_evaluation 内部按幂等键生成）
    assert rec1.calls == rec2.calls
    assert len(rec1.calls) > 0


# ── 10. Dataset does not auto-grow ─────────────────────────

def test_dataset_not_auto_grown(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    run_dir = tmp_path / RUN_NAME
    (run_dir / "audit").mkdir(parents=True)
    (run_dir / "audit" / "audit_report.json").write_text(json.dumps(
        {"manifest": {"audit_run_id": "audit_t"}, "findings": []}), encoding="utf-8")
    (run_dir / "audit" / "golden").mkdir(parents=True)
    (run_dir / "audit" / "golden" / "golden_cases.jsonl").write_text("", encoding="utf-8")
    run_auto_evaluation(run_dir=run_dir, write_scores=True)
    # hook 不产生任何 dataset 产物 / 调用
    assert not (run_dir / "audit" / "evaluation" / "dataset_items.jsonl").exists()
    assert not (run_dir / "audit" / "evaluation" / "dataset_export_report.json").exists()


# ── 11. workflow final output unchanged ────────────────────

def test_workflow_output_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    run_dir = tmp_path / RUN_NAME
    (run_dir / "audit").mkdir(parents=True)
    (run_dir / "audit" / "audit_report.json").write_text(json.dumps(
        {"manifest": {"audit_run_id": "audit_t"}, "findings": []}), encoding="utf-8")
    (run_dir / "audit" / "golden").mkdir(parents=True)
    (run_dir / "audit" / "golden" / "golden_cases.jsonl").write_text("", encoding="utf-8")
    final = run_dir / "final" / "final_output.xlsx"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"business-output")
    run_auto_evaluation(run_dir=run_dir, write_scores=True)
    assert final.read_bytes() == b"business-output"
