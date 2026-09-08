# -*- coding: utf-8 -*-
"""Phase 2b：evaluation_dataset_export.py 测试（fake provider，不触网）。"""

import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluation_dataset_export import (  # noqa: E402
    DEFAULT_SCHEMA_VERSION,
    build_items,
    export_dataset,
    stable_item_id,
)


def _case(vid, name, decision="CONFIRMED", major="价格", sub="现货价格", selected="是",
          crosscheck="OK", case_id="priority_tin_TIN_0"):
    return {
        "source_case_id": case_id, "original_name": name, "physical_variable_id": vid,
        "match_method": "NAME_UNIQUE_RUN_LOCAL", "human_decision": decision,
        "human_major": major, "human_sub": sub, "human_selected": selected,
        "human_notes": "", "audit_crosscheck": crosscheck, "workflow_run_id": "run1",
        "sheet": "价格-日", "unit": "元/吨", "frequency": "日度",
    }


def _twenty_five():
    return [_case(f"{i:016x}", f"指标{i}", case_id=f"priority_tin_TIN_{i}") for i in range(25)]


def _write_cases(tmp_path, rows):
    p = tmp_path / "human_cases.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return p


class FakeProvider:
    """记录调用；get_dataset_items 首次返回 None（Dataset 不存在）。"""

    def __init__(self, existing=None, exists_first=False):
        self.items: dict[str, dict] = existing or {}
        self.created: list[str] = []
        self.upserted: list[str] = []
        self.dataset_created = False
        self.exists_first = exists_first

    def get_dataset_items(self, name):
        if not self.exists_first and not self.dataset_created:
            return None if not self.items else self.items
        return self.items

    def ensure_dataset(self, name, description, metadata):
        self.dataset_created = True

    def upsert_item(self, name, item):
        self.items[item["id"]] = {
            "input": item["input"], "expected_output": item["expected_output"],
            "metadata": item["metadata"],
        }
        self.upserted.append(item["id"])


# ── 11. 25 item 稳定导入 ───────────────────────────────────

def test_25_items_stable_import(tmp_path):
    rows = _twenty_five()
    items = build_items(rows, {})
    assert len(items) == 25
    ids = [i["id"] for i in items]
    assert len(set(ids)) == 25  # id 唯一
    assert ids[0] == stable_item_id("unknown", "UNKNOWN", "0000000000000000")
    # id 与行序无关（同一 vid 同 id）
    items2 = build_items(list(reversed(rows)), {})
    assert {i["id"] for i in items2} == set(ids)


# ── 12. 重跑无重复 ─────────────────────────────────────────

def test_rerun_idempotent(tmp_path):
    items = build_items(_twenty_five(), {})
    provider = FakeProvider()
    stats1 = export_dataset(items=items, provider=provider, dataset_name="classification/human_confirmed", apply=True)
    assert stats1["created"] == 25 and stats1["unchanged"] == 0
    assert len(provider.upserted) == 25

    # 重跑：相同内容（imported_at 变化）→ unchanged，不重复创建
    for item in items:
        item["metadata"]["imported_at"] = "2026-09-02T00:00:00+00:00"
    provider2 = FakeProvider(existing=provider.items, exists_first=True)
    stats2 = export_dataset(items=items, provider=provider2, dataset_name="classification/human_confirmed", apply=True)
    assert stats2["created"] == 0 and stats2["unchanged"] == 25 and stats2["updated"] == 0
    assert provider2.upserted == []


# ── 13. expected_output 不自动补全 ─────────────────────────

def test_expected_output_not_auto_filled(tmp_path):
    rows = [_case("a" * 16, "指标A", major="供给", sub="", selected="是")]
    items = build_items(rows, {})
    assert items[0]["expected_output"] == {"大类": "供给", "是否选中": "是"}  # 子类空 → 不写
    # golden 中 null 的字段绝不推断
    rows2 = [_case("b" * 16, "指标B", major="", sub="", selected="")]
    items2 = build_items(rows2, {})
    assert items2[0]["expected_output"] == {}


# ── 14. NO_AUDIT case 正确保留 ─────────────────────────────

def test_no_audit_preserved(tmp_path):
    rows = [
        _case("a" * 16, "指标A", crosscheck="OK"),
        _case("b" * 16, "指标B", crosscheck="NO_AUDIT"),
    ]
    items = build_items(rows, {})
    meta = {i["metadata"]["physical_variable_id"]: i["metadata"] for i in items}
    assert meta["b" * 16]["audit_crosscheck"] == "NO_AUDIT"
    assert meta["a" * 16]["audit_crosscheck"] == "OK"
    assert all(i["metadata"]["source"] == "human_review" for i in items)
    assert all(i["metadata"]["schema_version"] == DEFAULT_SCHEMA_VERSION for i in items)


# ── 补充：candidates 上下文与 expected 只含人工字段 ────────

def test_input_context_and_expected_fields(tmp_path):
    rows = [_case("c" * 16, "指标C", major="进出口", sub="进口", selected="是")]
    pack = {"指标C": {"industry": "tin", "commodity": "TIN", "candidates": [{"大类": "进出口", "子类": "进口"}]}}
    items = build_items(rows, pack)
    assert items[0]["input"]["industry"] == "tin"
    assert items[0]["input"]["commodity"] == "TIN"
    assert items[0]["input"]["candidates"] == [{"大类": "进出口", "子类": "进口"}]
    assert items[0]["id"] == stable_item_id("tin", "TIN", "c" * 16)
    assert set(items[0]["expected_output"]) <= {"大类", "子类", "是否选中"}


# ── 15/16. disabled provider 不影响业务输出 ────────────────

def test_dry_run_no_provider_no_business_change(tmp_path):
    rows = _twenty_five()
    cases = _write_cases(tmp_path, rows)
    final = tmp_path / "final_output.xlsx"
    final.write_bytes(b"business-output")
    from evaluation_dataset_export import main

    rc = main([
        "--human-cases", str(cases), "--run-dir", str(tmp_path / "run1"),
        "--dry-run",
    ])
    assert rc == 0
    out = tmp_path / "run1" / "audit" / "evaluation"
    assert (out / "dataset_items.jsonl").exists()
    assert (out / "dataset_export_report.json").exists()
    report = json.loads((out / "dataset_export_report.json").read_text(encoding="utf-8"))
    assert report["total_candidates"] == 25
    assert report["mode"] == "dry_run"
    assert final.read_bytes() == b"business-output"  # workflow 输出不变
