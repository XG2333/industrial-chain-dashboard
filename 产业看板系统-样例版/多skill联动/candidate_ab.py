# -*- coding: utf-8 -*-
"""Phase 3c：deterministic candidate-rule A/B 离线回放（不跑 LLM）。

对 production-equivalent Dataset 的每条 case：
- old candidates：历史 run 候选（enriched item，HISTORICAL_EXACT）
- new candidates：当前 classification_candidates.candidate_plan（确定性规则）

输出：
- expected_in_candidates_before / after
- candidate_changed_cases（含 WRONG_CANDIDATES 是否修复、新 regression）
- 供实验用的 items 文件（schema_version=2.1；changed case 标记
  CURRENT_RULE_RECONSTRUCTED，provenance 记录 current_rules）

用法：
  python scripts/candidate_ab.py --enriched-items <enriched_items.jsonl>
      --out-dir <dir> [--industry lithium_tin]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from classification_candidates import candidate_plan  # noqa: E402

SCHEMA_VERSION_NEW = "2.1"
CONTEXT_CURRENT_RULES = "CURRENT_RULE_RECONSTRUCTED"


def new_candidates_for(item: dict, industry: str) -> list[dict]:
    inp = item["input"]
    plan = candidate_plan(
        inp.get("original_name", ""), inp.get("sheet", ""), industry, inp.get("unit", "")
    )
    return plan["combinations"]


def expected_in(candidates: list[dict], expected: dict) -> bool:
    exp_major = str(expected.get("大类") or "").strip()
    exp_sub = str(expected.get("子类") or "").strip()
    if not exp_major:
        return False
    return any(
        str(c.get("大类") or "").strip() == exp_major
        and (not exp_sub or str(c.get("子类") or "").strip() == exp_sub)
        for c in candidates
        if isinstance(c, dict)
    )


def replay(items: list[dict], industry: str) -> dict:
    changed: list[dict] = []
    regressions: list[dict] = []
    fixed: list[dict] = []
    before = after = 0
    new_items: list[dict] = []
    for it in items:
        expected = it["expected_output"]
        old = it["input"].get("candidates") or []
        new = new_candidates_for(it, industry)
        old_in = expected_in(old, expected)
        new_in = expected_in(new, expected)
        before += 1 if old_in else 0
        after += 1 if new_in else 0
        if old != new:
            entry = {
                "id": it["id"],
                "original_name": it["input"].get("original_name"),
                "expected": expected,
                "old_candidates": old,
                "new_candidates": new,
                "expected_in_before": old_in,
                "expected_in_after": new_in,
            }
            changed.append(entry)
            if old_in and not new_in:
                regressions.append(entry)
            if not old_in and new_in:
                fixed.append(entry)
        # 构建实验用 items（new candidates；changed → CURRENT_RULE_RECONSTRUCTED）
        new_item = json.loads(json.dumps(it))
        new_item["input"]["candidates"] = new
        md = new_item["metadata"]
        if old != new:
            md["context_status"] = CONTEXT_CURRENT_RULES
            md["candidate_provenance"] = "current_rules:classification_candidates.py"
            md["schema_version"] = SCHEMA_VERSION_NEW
            md["previous_candidates"] = old
        new_items.append(new_item)
    return {
        "total": len(items),
        "expected_in_candidates_before": before,
        "expected_in_candidates_after": after,
        "candidate_changed_cases": len(changed),
        "wrong_candidates_fixed": len(fixed),
        "new_regressions": len(regressions),
        "changed_details": changed,
        "regression_details": regressions,
        "fixed_details": fixed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3c candidate-rule offline replay")
    parser.add_argument("--enriched-items", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--industry", default="lithium_tin")
    args = parser.parse_args(argv)

    items = [json.loads(l) for l in
             open(args.enriched_items, encoding="utf-8").read().splitlines() if l.strip()]
    report = replay(items, args.industry)
    report["mode"] = "offline_replay"
    report["generated_at"] = datetime.now(timezone.utc).isoformat()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidate_ab_report.json").write_text(
        json.dumps({k: v for k, v in report.items()
                    if k not in ("changed_details", "regression_details", "fixed_details")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "candidate_ab_details.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    new_items = _apply_new(items, args.industry)
    (out_dir / "new_candidates_items.jsonl").write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in new_items) + "\n",
        encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("changed_details", "regression_details", "fixed_details")},
                     ensure_ascii=False, indent=2))
    return 0


def _apply_new(items: list[dict], industry: str) -> list[dict]:
    out = []
    for it in items:
        new_item = json.loads(json.dumps(it))
        new_item["input"]["candidates"] = new_candidates_for(it, industry)
        md = new_item["metadata"]
        if new_item["input"]["candidates"] != it["input"].get("candidates"):
            md["context_status"] = CONTEXT_CURRENT_RULES
            md["candidate_provenance"] = "current_rules:classification_candidates.py"
            md["schema_version"] = SCHEMA_VERSION_NEW
        out.append(new_item)
    return out


if __name__ == "__main__":
    sys.exit(main())
