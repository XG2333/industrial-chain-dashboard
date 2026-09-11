# -*- coding: utf-8 -*-
"""Phase 4：Golden Dataset Expansion + Coverage Evaluation。

- 普查真实生产分类空间（lithium/tin/silicon 的 final_output / directory_marked 目录）
- 建立 Coverage Matrix（industry × major × difficulty）
- 生成人工审核候选池（P0/P1/P2/P3，semantic family 去重 + 上限）
- 输出 golden_review_pack.xlsx（Human 字段保持空白，不预填推断答案）
- Dataset quality metrics（industry/major/sub coverage、hard ratio 等）

重要：
- 98.7% 等 accuracy 仅指当前 25 条人工确认 production-context 子集，
  不是生产总体分类准确率（代码/README 均已注明）。
- verifier 结果只用于 P0 优先级标记，不自动成为 expected（人工真值）。
- 只有人工确认后的 case 才能进入 classification/human_confirmed。

用法：
  python scripts/golden_coverage.py --run-root workflow_runs
      --golden-items <enriched_items.jsonl>
      --tin-audit <外部 tin_phasec_audit/audit_report.json>（可选，tin verifier 标记）
      --out-dir workflow_runs/experiments/golden_coverage
      [--pool-size 60] [--family-cap 3]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

INDUSTRY_BY_FILE = {"碳酸锂数据库": "lithium", "锡数据库": "tin", "硅产业链数据": "silicon"}
ALLOWED_MAJORS = {
    "价格", "成本利润", "进出口", "库存", "需求", "供给", "平衡", "其他",
    "供需-进出口", "供需-库存", "供需-需求", "供需-供给", "供需-平衡",
}
VERIFIER_FLAG_DISPOSITIONS = frozenset(
    {"CONFIRMED_ERROR", "RULE_SPEC_AMBIGUOUS", "IDENTITY_AMBIGUOUS", "NEEDS_HUMAN_REVIEW"}
)
VERIFIER_FLAG_VERDICTS = frozenset({"ERROR", "AMBIGUOUS"})


# ── 普查源发现 ─────────────────────────────────────────────


def _industry_of_run(run_dir: Path) -> str:
    manifest = run_dir / "audit" / "audit_manifest.json"
    if manifest.exists():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8")).get("raw_file", "")
            for key, ind in INDUSTRY_BY_FILE.items():
                if key in raw:
                    return ind
        except Exception:  # noqa: BLE001
            pass
    summary = run_dir / "workflow_summary.json"
    if summary.exists():
        try:
            s = json.loads(summary.read_text(encoding="utf-8"))
            raw = str(s.get("input_file") or "")
            for key, ind in INDUSTRY_BY_FILE.items():
                if key in raw:
                    return ind
        except Exception:  # noqa: BLE001
            pass
    return ""


def discover_sources(run_root: Path, tin_audit: Path | None = None) -> dict[str, dict]:
    """每产业取最新有 final_output 的 run（回退 directory_marked）+ 可选 audit。"""
    best: dict[str, dict] = {}
    for run_dir in sorted(run_root.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("20"):
            continue
        ind = _industry_of_run(run_dir)
        if not ind:
            continue
        final = run_dir / "final" / "final_output.xlsx"
        directory = run_dir / "02_financial_variable_curation" / "directory_marked.xlsx"
        catalog = final if final.exists() else (directory if directory.exists() else None)
        if catalog is None:
            continue
        raw_hash = ""
        manifest = run_dir / "audit" / "audit_manifest.json"
        if manifest.exists():
            try:
                raw_hash = json.loads(manifest.read_text(encoding="utf-8")).get("raw_file_hash", "")
            except Exception:  # noqa: BLE001
                pass
        cur = best.get(ind)
        audit_path = run_dir / "audit" / "audit_report.json"
        audit = audit_path if audit_path.exists() else None
        if cur is None or run_dir.name > cur["run"]:
            best[ind] = {
                "run": run_dir.name, "catalog": catalog,
                "catalog_kind": "final" if final.exists() else "directory_marked",
                "raw_file_hash": raw_hash,
                "audit": audit,
            }
    if tin_audit is not None:
        if "tin" in best:
            best["tin"]["audit"] = tin_audit
    return best


# ── 目录普查 ───────────────────────────────────────────────


def load_catalog(path: Path, industry: str, raw_file_hash: str) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    header = [str(c.value or "").strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    i_name = header.index("Indicator Name")
    i_major = header.index("大类") if "大类" in header else None
    i_sub = header.index("子类") if "子类" in header else None
    i_unit = header.index("Unit") if "Unit" in header else None
    i_freq = header.index("Freq") if "Freq" in header else None
    i_sheet = header.index("Sheet Name") if "Sheet Name" in header else None
    i_col = header.index("Col") if "Col" in header else None
    i_tag = header.index("指标标签") if "指标标签" in header else None
    out: list[dict] = []
    cur_sheet = ""
    for row in ws.iter_rows(min_row=2, values_only=True):
        first = str(row[0] or "").strip() if row[0] is not None else ""
        if first and not first.replace(".", "", 1).isdigit():
            cur_sheet = first
            continue
        name = str(row[i_name] or "").strip() if i_name is not None else ""
        if not name:
            continue
        tags: dict = {}
        if i_tag is not None and row[i_tag] is not None:
            try:
                tags = json.loads(str(row[i_tag]).strip()) or {}
            except Exception:  # noqa: BLE001
                tags = {}
        combos = tags.get("候选分类组合") if isinstance(tags, dict) else None
        majors = tags.get("候选大类") if isinstance(tags, dict) else None
        subs = tags.get("候选子类") if isinstance(tags, dict) else None
        candidates = combos if combos else (
            [{"大类": m, "子类": "其他"} for m in majors] if majors else None
        )
        if candidates is None and subs:
            candidates = [{"大类": "其他", "子类": s} for s in subs]
        vid = ""
        if raw_file_hash and i_sheet is not None and i_col is not None:
            sheet = str(row[i_sheet] or "").strip() or cur_sheet
            col = row[i_col]
            try:
                import hashlib

                vid = hashlib.sha256(
                    f"{raw_file_hash}|{sheet}|{int(col)}|{name}".encode("utf-8")
                ).hexdigest()[:16]
            except Exception:  # noqa: BLE001
                pass
        out.append({
            "industry": industry,
            "physical_variable_id": vid,
            "name": name, "sheet": str(row[i_sheet] or "").strip() or cur_sheet,
            "unit": str(row[i_unit] or "").strip() if i_unit is not None else "",
            "frequency": str(row[i_freq] or "").strip() if i_freq is not None else "",
            "major": str(row[i_major] or "").strip() if i_major is not None else "",
            "sub": str(row[i_sub] or "").strip() if i_sub is not None else "",
            "candidates": candidates or [],
            "candidate_count": len(candidates) if candidates else 0,
        })
    wb.close()
    return out


def load_audit_flags(audit_path: Path) -> dict[str, dict]:
    """findings → per vid: verdicts/dispositions/issues + flagged 布尔。"""
    if audit_path is None or not audit_path.exists():
        return {}
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for f in report.get("findings", []):
        vid = f.get("physical_variable_id")
        if not vid:
            continue
        entry = out.setdefault(vid, {"verdicts": [], "dispositions": [], "issues": []})
        if f.get("verdict") and f["verdict"] not in entry["verdicts"]:
            entry["verdicts"].append(f["verdict"])
        if f.get("final_disposition") and f["final_disposition"] not in entry["dispositions"]:
            entry["dispositions"].append(f["final_disposition"])
        if f.get("issue_type") and f["issue_type"] not in entry["issues"]:
            entry["issues"].append(f["issue_type"])
    for entry in out.values():
        entry["flagged"] = bool(
            any(v in VERIFIER_FLAG_VERDICTS for v in entry["verdicts"])
            or any(d in VERIFIER_FLAG_DISPOSITIONS for d in entry["dispositions"])
        )
    return out


# ── difficulty / family ────────────────────────────────────


def difficulty(candidate_count: int, verifier_flagged: bool, human_corrected: bool = False) -> str:
    if candidate_count == 0:
        return "UNKNOWN"
    if candidate_count >= 3 or verifier_flagged or human_corrected:
        return "HARD"
    if candidate_count == 2:
        return "MEDIUM"
    return "EASY"


def family_id(industry: str, name: str) -> str:
    """semantic family：industry + 名称前两段（: 分隔）——同一 family 去重与上限。"""
    core = ": ".join([s.strip() for s in str(name or "").split(":")][:2])
    return f"{industry}|{core}"


# ── Coverage Matrix ────────────────────────────────────────


def build_coverage_matrix(space: list[dict], golden: list[dict]) -> dict:
    prod: Counter = Counter()
    for v in space:
        d = difficulty(v["candidate_count"], False)
        prod[(v["industry"], v["major"] or "未分类", d)] += 1
    gold: Counter = Counter()
    for g in golden:
        md = g.get("metadata") or {}
        cand = g["input"].get("candidates") or []
        d = difficulty(len(cand), md.get("audit_crosscheck") == "NO_AUDIT",
                       _human_corrected(g))
        gold[(g["input"].get("industry", ""), (g["expected_output"].get("大类") or "未分类"), d)] += 1
    cells = []
    for key in sorted(set(prod) | set(gold)):
        ind, major, d = key
        p = prod[key]
        gc = gold[key]
        cells.append({
            "industry": ind, "major_category": major, "difficulty": d,
            "production_count": p, "golden_count": gc,
            "coverage_rate": round(gc / p, 4) if p else None,
        })
    return {"cells": cells,
            "totals": {
                "production_variables": sum(prod.values()),
                "golden_cases": sum(gold.values()),
            }}


def _human_corrected(g: dict) -> bool:
    cur_major = str(g["input"].get("current_major") or "").strip()
    exp_major = str(g["expected_output"].get("大类") or "").strip()
    return bool(cur_major and exp_major and cur_major != exp_major)


# ── 候选池选择 ─────────────────────────────────────────────


def select_review_pool(
    space: list[dict],
    audit_flags: dict[str, dict],
    golden_vids: set[str],
    *,
    pool_size: int,
    family_cap: int,
    seed: int = 42,
) -> list[dict]:
    p0, p1, p2, p3 = [], [], [], []
    covered_cells = set()
    # P2 未覆盖 cell 判定由调用方传入 golden 后计算（这里用空集，调用方再补）
    for v in space:
        if v["physical_variable_id"] in golden_vids:
            continue
        flags = audit_flags.get(v["physical_variable_id"], {})
        flagged = flags.get("flagged", False)
        count = v["candidate_count"]
        majors = {c.get("大类") for c in v["candidates"] if isinstance(c, dict)}
        category_conflict = len(majors) > 1
        rule_affected = any(k in v["name"] for k in
                            ("进出口盈亏", "进口盈亏", "出口盈亏", "进口利润", "出口利润",
                             "进口成本", "出口成本", "盈亏测算", "利润测算"))
        item = {**v, "verifier_flags": flags}
        if flagged:
            item["priority"] = "P0"
            p0.append(item)
        elif count >= 3 or category_conflict or rule_affected:
            item["priority"] = "P1"
            p1.append(item)
        elif count in (1, 2):
            item["priority"] = "P3"
            p3.append(item)
        else:
            item["priority"] = "P2"
            p2.append(item)

    # family 去重 + 上限（跨优先级全局计数，P0 优先）+ per-industry 配额
    # （防单产业主导审核池，保证覆盖均衡）；main 池与 control 池分开配额。
    prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    rng = random.Random(seed)
    control_size = max(5, pool_size // 8)
    main_budget = pool_size - control_size
    n_industries = max(1, len({c["industry"] for c in p0 + p1 + p2 + p3}))
    ind_quota = max(5, -(-main_budget // n_industries))  # ceil

    def _pick(cands: list[dict], cap: int, quota: int, budget: int) -> list[dict]:
        fam_count: Counter = Counter()
        ind_count: Counter = Counter()
        picked: list[dict] = []
        for c in sorted(cands, key=lambda x: (prio_order[x["priority"]], -x["candidate_count"], x["name"])):
            if len(picked) >= budget:
                break
            fam = family_id(c["industry"], c["name"])
            if fam_count[fam] >= cap or ind_count[c["industry"]] >= quota:
                continue
            fam_count[fam] += 1
            ind_count[c["industry"]] += 1
            picked.append(c)
        return picked

    main = _pick(p0 + p1 + p2, family_cap, ind_quota, main_budget)
    p3_sorted = list(p3)
    rng.shuffle(p3_sorted)
    control = _pick(p3_sorted[: control_size * 2], family_cap,
                    max(2, control_size), control_size)
    pool = (main + control)[:pool_size]
    # 汇总 family 报告
    fam_sizes: Counter = Counter()
    for c in pool:
        fam_sizes[family_id(c["industry"], c["name"])] += 1
    return {
        "pool": pool,
        "priority_counts": Counter(c["priority"] for c in pool),
        "family_report": {
            "unique_families": len(fam_sizes),
            "max_family_size": max(fam_sizes.values()) if fam_sizes else 0,
            "families_over_cap": {k: v for k, v in fam_sizes.items() if v > family_cap},
        },
    }


# ── review pack / quality metrics ──────────────────────────


def write_review_pack(pool: list[dict], path: Path, ai_outputs: dict[str, str] | None = None) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "golden_review"
    cols = [
        "physical_variable_id", "industry", "commodity", "original_name", "sheet",
        "unit", "frequency", "current_major", "current_sub", "candidates",
        "candidate_count", "AI_output", "verifier_status", "verifier_reason",
        "difficulty", "selection_priority", "semantic_family",
        "Human decision", "Expected major", "Expected sub", "Human comment",
    ]
    ws.append(cols)
    for c in pool:
        flags = c.get("verifier_flags") or {}
        ai_out = (ai_outputs or {}).get(c["physical_variable_id"], "")
        ws.append([
            c.get("physical_variable_id", ""), c.get("industry", ""), c.get("commodity", ""),
            c.get("name", ""), c.get("sheet", ""), c.get("unit", ""), c.get("frequency", ""),
            c.get("major", ""), c.get("sub", ""),
            json.dumps(c.get("candidates") or [], ensure_ascii=False), c.get("candidate_count", 0),
            ai_out,
            ";".join(flags.get("verdicts", [])) or "",
            ";".join(flags.get("dispositions", [])) or "",
            difficulty(c.get("candidate_count", 0), bool(flags.get("flagged", False))),
            c.get("priority", ""),
            family_id(c.get("industry", ""), c.get("name", "")),
            "", "", "", "",  # Human 字段保持空白，绝不预填
        ])
    wb.save(path)
    wb.close()


def quality_metrics(golden: list[dict], space: list[dict]) -> dict:
    inds = {v["industry"] for v in space}
    majors = {v["major"] or "未分类" for v in space}
    subs = {(v["major"] or "未分类", v["sub"] or "未分类") for v in space}
    gold_inds = {g["input"].get("industry", "") for g in golden}
    gold_majors = {g["expected_output"].get("大类") or "未分类" for g in golden}
    gold_subs = {(g["expected_output"].get("大类") or "未分类",
                  g["expected_output"].get("子类") or "未分类") for g in golden}
    n = len(golden)
    fams = {family_id(g["input"].get("industry", ""), g["input"].get("original_name", "")) for g in golden}
    hard = sum(1 for g in golden
               if difficulty(len(g["input"].get("candidates") or []),
                             (g.get("metadata") or {}).get("audit_crosscheck") == "NO_AUDIT",
                             _human_corrected(g)) == "HARD")
    multi = sum(1 for g in golden if len(g["input"].get("candidates") or []) >= 2)
    corrected = sum(1 for g in golden if _human_corrected(g))
    eic = sum(1 for g in golden if (g.get("metadata") or {}).get("expected_in_candidates") is True)
    return {
        "golden_total": n,
        "industry_coverage": round(len(gold_inds) / len(inds), 4) if inds else None,
        "major_category_coverage": round(len(gold_majors) / len(majors), 4) if majors else None,
        "subcategory_coverage": round(len(gold_subs) / len(subs), 4) if subs else None,
        "hard_case_ratio": round(hard / n, 4) if n else None,
        "multi_candidate_ratio": round(multi / n, 4) if n else None,
        "human_corrected_ratio": round(corrected / n, 4) if n else None,
        "family_diversity": round(len(fams) / n, 4) if n else None,
        "expected_in_candidates_rate": round(eic / n, 4) if n else None,
        "industry_golden_counts": dict(Counter(g["input"].get("industry", "") for g in golden)),
        "major_golden_counts": dict(Counter(g["expected_output"].get("大类") or "未分类" for g in golden)),
    }


# ── CLI ────────────────────────────────────────────────────


def load_golden_items(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 golden coverage")
    parser.add_argument("--run-root", default=str(PROJECT_ROOT / "workflow_runs"))
    parser.add_argument("--golden-items", required=True)
    parser.add_argument("--tin-audit", default=None)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pool-size", type=int, default=60)
    parser.add_argument("--family-cap", type=int, default=3)
    args = parser.parse_args(argv)

    sources = discover_sources(Path(args.run_root), Path(args.tin_audit) if args.tin_audit else None)
    space: list[dict] = []
    audit_all: dict[str, dict] = {}
    for ind, src in sources.items():
        vars_ = load_catalog(src["catalog"], ind, src["raw_file_hash"])
        for v in vars_:
            v["commodity"] = {"lithium": "LI", "tin": "TIN", "silicon": "SI"}.get(ind, ind.upper())
        space.extend(vars_)
        if src["audit"] is not None:
            audit_all.update(load_audit_flags(src["audit"]))

    golden = load_golden_items(Path(args.golden_items))
    golden_vids = {g["input"].get("physical_variable_id") for g in golden}
    matrix = build_coverage_matrix(space, golden)
    pool_result = select_review_pool(
        space, audit_all, golden_vids,
        pool_size=args.pool_size, family_cap=args.family_cap,
    )
    quality = quality_metrics(golden, space)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    write_review_pack(pool_result["pool"], out_dir / "golden_review_pack.xlsx")

    space_by_ind = Counter(v["industry"] for v in space)
    major_counts = Counter((v["industry"], v["major"] or "未分类") for v in space)
    cand_buckets = Counter(
        "3+" if v["candidate_count"] >= 3 else (str(v["candidate_count"]) if v["candidate_count"] else "0")
        for v in space
    )
    ai_amb = sum(1 for v in space if v["candidate_count"] >= 2)
    flagged = sum(1 for v in space if audit_all.get(v["physical_variable_id"], {}).get("flagged"))
    report = {
        "sources": {k: {kk: (str(vv) if not isinstance(vv, (str, Path)) else str(vv))
                        for kk, vv in v.items()} for k, v in sources.items()},
        "classification_space": {
            "industries": dict(space_by_ind),
            "major_counts": {f"{k[0]}:{k[1]}": v for k, v in major_counts.items()},
            "candidate_count_buckets": dict(cand_buckets),
            "ai_ambiguity_potential": ai_amb,
            "verifier_flagged": flagged,
        },
        "coverage_matrix": matrix,
        "quality_metrics": quality,
        "review_pool": {
            "total": len(pool_result["pool"]),
            "priority_counts": dict(pool_result["priority_counts"]),
            "family_report": pool_result["family_report"],
            "difficulty_distribution": dict(Counter(
                difficulty(c["candidate_count"], bool((c.get("verifier_flags") or {}).get("flagged")))
                for c in pool_result["pool"])),
        },
        "out_dir": str(out_dir),
    }
    (out_dir / "golden_coverage_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "coverage_matrix.csv").write_text(
        _matrix_csv(matrix["cells"]), encoding="utf-8-sig")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _matrix_csv(cells: list[dict]) -> str:
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["industry", "major_category", "difficulty",
                                             "production_count", "golden_count", "coverage_rate"])
    writer.writeheader()
    for c in cells:
        writer.writerow(c)
    return buf.getvalue()


if __name__ == "__main__":
    sys.exit(main())
