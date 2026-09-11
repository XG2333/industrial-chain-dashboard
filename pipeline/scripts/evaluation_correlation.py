# -*- coding: utf-8 -*-
"""Phase 2a：Verifier case ↔ Langfuse generation 稳定 correlation index（纯逻辑）。

- 唯一变量级主身份 physical_variable_id（与 Result_audit 审计 findings 同源，
  3493/3493 实测命中）：
    physical_variable_id = sha256(f"{raw_file_hash}|{sheet.strip()}|{int(col)}|{name.strip()}")[:16]
- 关联键：
    evaluation_key = sha256(f"{physical_variable_id}|{prompt_version}|{prompt_hash}")[:32]
    score_id       = sha256(f"{evaluation_key}|{audit_run_id}|{score_source}|{score_name}")[:32]
- run 内重建关联：generation input items 与本 run 目录表以 (sheet, name, unit) 精确匹配；
  人工 pack（缺 sheet/unit）以 run 内名称唯一性（NAME_UNIQUE_RUN_LOCAL）恢复。
- 禁止跨 run 名称匹配。AMBIGUOUS / UNMATCHED 不允许评分。
- 正确性规则：HUMAN > VERIFIER；ERROR / NEEDS_HUMAN_REVIEW 等一律不推导 correctness。
本模块不触网、不写任何外部系统（纯函数，可单测）。
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

# ── 身份函数 ────────────────────────────────────────────────


def physical_variable_id(file_hash: str, sheet: str, col: Any, name: str) -> str:
    """变量级主身份（与 Result_audit utils.physical_variable_id 公式一致）。"""
    payload = f"{file_hash}|{str(sheet or '').strip()}|{int(col)}|{str(name or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def evaluation_key(physical_variable_id: str, prompt_version: str, prompt_hash: str) -> str:
    """跨 run 聚合键：同一变量 + 同一 prompt 版本 → 同一 key。"""
    payload = f"{physical_variable_id}|{prompt_version}|{prompt_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def score_id(evaluation_key: str, audit_run_id: str, score_source: str, score_name: str) -> str:
    """幂等 score 键：同 run 重跑/回填不重复，不同 run 保留历史。"""
    payload = f"{evaluation_key}|{audit_run_id}|{score_source}|{score_name}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


# ── 目录表读取（directory_marked / slim 目录表布局）──────────


def load_directory_rows(xlsx_path: str | Path) -> list[dict]:
    """读取目录表为行记录：sheet(节头) / col / name / unit / freq。

    布局：表头行含 Indicator Name 等列；非数字首列的"节头行"定义当前 sheet。
    """
    from openpyxl import load_workbook

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return []
    hdr = [str(c or "").strip() for c in rows[0]]
    try:
        i_name = hdr.index("Indicator Name")
        i_col = hdr.index("Col")
    except ValueError:
        return []
    i_sheet = hdr.index("Sheet Name") if "Sheet Name" in hdr else None
    i_unit = hdr.index("Unit") if "Unit" in hdr else None
    i_freq = hdr.index("Freq") if "Freq" in hdr else None

    out: list[dict] = []
    current_sheet = ""
    for row in rows[1:]:
        first = str(row[0] or "").strip() if row[0] is not None else ""
        if first and not first.replace(".", "", 1).isdigit():
            current_sheet = first
            continue
        name = str(row[i_name] or "").strip() if i_name is not None else ""
        if not name:
            continue
        col = row[i_col] if i_col is not None else None
        try:
            int(col)
        except (TypeError, ValueError):
            continue
        sheet = str(row[i_sheet] or "").strip() if i_sheet is not None else ""
        out.append(
            {
                "sheet": sheet or current_sheet,
                "col": int(col),
                "name": name,
                "unit": str(row[i_unit] or "").strip() if i_unit is not None else "",
                "freq": str(row[i_freq] or "").strip() if i_freq is not None else "",
            }
        )
    return out


def index_catalog(rows: list[dict]) -> dict:
    """目录索引：triple=(sheet,name,unit) 与 name 两个键，均映射到候选行。"""
    triple_idx: dict[tuple, list[dict]] = {}
    name_idx: dict[str, list[dict]] = {}
    for r in rows:
        triple_idx.setdefault((r["sheet"], r["name"], r["unit"]), []).append(r)
        name_idx.setdefault(r["name"], []).append(r)
    return {"triple": triple_idx, "name": name_idx}


# ── generation input 解析 ───────────────────────────────────


def parse_generation_input(input_value: Any) -> list[dict]:
    """从 generation input（messages 列表）提取 items 数组。

    ai_disambiguation 的 user message content 是 JSON：{"provider","model",
    "prompt_version","items":[...]}；解析失败返回空列表。
    """
    if not isinstance(input_value, list):
        return []
    for m in input_value:
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        content = m.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except Exception:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            items = payload["items"]
            if items and isinstance(items[0], dict):
                return items
    return []


# ── 关联构建 ────────────────────────────────────────────────

MATCH_METHOD_EXACT = "EXACT_TRIPLE"
MATCH_METHOD_NAME_UNIQUE = "NAME_UNIQUE_RUN_LOCAL"
MATCH_METHOD_AMBIGUOUS_TRIPLE = "AMBIGUOUS_TRIPLE"
MATCH_METHOD_AMBIGUOUS_NAME = "AMBIGUOUS_NAME"
MATCH_METHOD_UNMATCHED_TRIPLE = "UNMATCHED_TRIPLE"
MATCH_METHOD_UNMATCHED_NAME = "UNMATCHED_NAME"
MATCH_METHOD_NO_INPUT = "NO_ITEMS_IN_GENERATION"


def _corr_row(
    *,
    workflow_run_id: str,
    industry: str,
    stage: str,
    observation_id: str,
    batch_index: int,
    prompt_name: str,
    prompt_version: str,
    prompt_hash: str,
    model: str,
    raw_file_hash: str,
    item: dict | None = None,
    catalog_row: dict | None = None,
    match_method: str,
) -> dict:
    row = {
        "workflow_run_id": workflow_run_id,
        "industry": industry,
        "stage": stage,
        "generation_observation_id": observation_id,
        "batch_index": batch_index,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "model": model,
        "original_name": (item or {}).get("name", ""),
        "sheet": (item or {}).get("sheet", ""),
        "unit": (item or {}).get("unit", ""),
        "frequency": (item or {}).get("frequency", ""),
        "match_method": match_method,
        "physical_variable_id": "",
    }
    if catalog_row is not None:
        row["physical_variable_id"] = physical_variable_id(
            raw_file_hash, catalog_row["sheet"], catalog_row["col"], catalog_row["name"]
        )
    return row


def correlate_items(
    *,
    workflow_run_id: str,
    industry: str,
    stage: str,
    observation_id: str,
    trace_id: str = "",
    batch_index_start: int,
    prompt_name: str,
    prompt_version: str,
    prompt_hash: str,
    model: str,
    items: list[dict],
    catalog_index: dict,
    raw_file_hash: str,
) -> list[dict]:
    """一个 generation（batch）的 items 与本 run 目录做 run 内精确关联。

    多个 physical_variable_id 可指向同一 generation_observation_id（不拆分
    为虚假 generation）。AMBIGUOUS / UNMATCHED 行的 physical_variable_id 留空，
    不允许评分。trace_id 记录 Langfuse 真实 trace 关联（record_evaluation 使用，
    不构造/不推导）。
    """
    triple_idx = catalog_index["triple"]
    out: list[dict] = []
    for i, item in enumerate(items):
        name = str(item.get("name") or "").strip()
        sheet = str(item.get("sheet") or "").strip()
        unit = str(item.get("unit") or "").strip()
        cands = triple_idx.get((sheet, name, unit), [])
        item_variable_id = str(item.get("variable_id") or "")  # AI 脚本本地 id（output 回联用）
        if len(cands) == 1:
            row = _corr_row(
                workflow_run_id=workflow_run_id, industry=industry, stage=stage,
                observation_id=observation_id, batch_index=batch_index_start + i,
                prompt_name=prompt_name, prompt_version=prompt_version,
                prompt_hash=prompt_hash, model=model, raw_file_hash=raw_file_hash,
                item=item, catalog_row=cands[0], match_method=MATCH_METHOD_EXACT,
            )
            row["catalog_col"] = cands[0]["col"]
        elif len(cands) > 1:
            row = _corr_row(
                workflow_run_id=workflow_run_id, industry=industry, stage=stage,
                observation_id=observation_id, batch_index=batch_index_start + i,
                prompt_name=prompt_name, prompt_version=prompt_version,
                prompt_hash=prompt_hash, model=model, raw_file_hash=raw_file_hash,
                item=item, match_method=MATCH_METHOD_AMBIGUOUS_TRIPLE,
            )
            row["candidate_cols"] = sorted(r["col"] for r in cands)
        else:
            row = _corr_row(
                workflow_run_id=workflow_run_id, industry=industry, stage=stage,
                observation_id=observation_id, batch_index=batch_index_start + i,
                prompt_name=prompt_name, prompt_version=prompt_version,
                prompt_hash=prompt_hash, model=model, raw_file_hash=raw_file_hash,
                item=item, match_method=MATCH_METHOD_UNMATCHED_TRIPLE,
            )
        if trace_id:
            row["trace_id"] = trace_id
        row["item_variable_id"] = item_variable_id
        out.append(row)
    return out


def parse_generation_output(output: Any) -> dict[str, dict]:
    """从 generation output（JSON 字符串 {"results":[{variable_id, major, sub,...}]}）
    提取 {本地 variable_id: {major, sub}}，用于 correctness 的 AI 结果比对。"""
    if not isinstance(output, str):
        return {}
    try:
        payload = json.loads(output)
    except Exception:  # noqa: BLE001
        return {}
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return {}
    out: dict[str, dict] = {}
    for r in results:
        if isinstance(r, dict) and r.get("variable_id"):
            out[str(r["variable_id"])] = {
                "major": str(r.get("major") or "").strip(),
                "sub": str(r.get("sub") or "").strip(),
            }
    return out


def correlate_human_rows(
    *,
    workflow_run_id: str,
    industry: str,
    human_rows: list[dict],
    catalog_index: dict,
    raw_file_hash: str,
) -> list[dict]:
    """人工确认行（pack 无 sheet/unit）→ run 内名称唯一性恢复身份。

    名称在 run 目录中唯一 → MATCHED（NAME_UNIQUE_RUN_LOCAL）；
    多个候选 → AMBIGUOUS_NAME；无候选 → UNMATCHED_NAME。
    返回行含 human_* 字段与恢复的 physical_variable_id。
    """
    name_idx = catalog_index["name"]
    out: list[dict] = []
    for hr in human_rows:
        name = str(hr.get("original_name") or hr.get("name") or "").strip()
        cands = name_idx.get(name, [])
        base = {
            "workflow_run_id": workflow_run_id,
            "industry": industry,
            "stage": "HUMAN_REVIEW",
            "generation_observation_id": "",
            "batch_index": -1,
            "prompt_name": "",
            "prompt_version": "",
            "prompt_hash": "",
            "model": "",
            "original_name": name,
            "sheet": "",
            "unit": "",
            "frequency": "",
            "human_decision": hr.get("human_decision", ""),
            "human_major": hr.get("human_major", ""),
            "human_sub": hr.get("human_sub", ""),
            "human_selected": hr.get("human_selected", ""),
            "human_notes": hr.get("human_notes", ""),
            "source_case_id": hr.get("case_id", ""),
        }
        if len(cands) == 1:
            cr = cands[0]
            vid = physical_variable_id(raw_file_hash, cr["sheet"], cr["col"], cr["name"])
            base.update(
                {
                    "physical_variable_id": vid,
                    "match_method": MATCH_METHOD_NAME_UNIQUE,
                    "sheet": cr["sheet"],
                    "unit": cr["unit"],
                    "frequency": cr["freq"],
                    "catalog_col": cr["col"],
                }
            )
        elif len(cands) > 1:
            base.update(
                {
                    "physical_variable_id": "",
                    "match_method": MATCH_METHOD_AMBIGUOUS_NAME,
                    "candidate_cols": sorted(r["col"] for r in cands),
                }
            )
        else:
            base.update({"physical_variable_id": "", "match_method": MATCH_METHOD_UNMATCHED_NAME})
        out.append(base)
    return out


# ── 可评性分类（HUMAN > VERIFIER，strict）──────────────────

AUTO_NEVER_CORRECT_DISPOSITIONS = frozenset(
    {"NEEDS_HUMAN_REVIEW", "RULE_SPEC_MISSING", "RULE_SPEC_AMBIGUOUS", "IDENTITY_AMBIGUOUS"}
)
AUTO_NEVER_CORRECT_VERDICTS = frozenset({"REVIEW_REQUIRED", "ERROR", "AMBIGUOUS"})
HUMAN_EVALUABLE_DECISIONS = frozenset({"CONFIRMED", "CORRECTED"})


def classify_evaluability(corr_row: dict, findings: list[dict], golden: dict | None, human: dict | None) -> dict:
    """按正确性规则判定一个已关联 case 的可评性（不产生 correctness 值）。

    - automatic_evaluable 仅当：有 generation（matched）∧ 规则明确 approved
      （golden expected_status=CONFIRMED 或 expected_rule_ids 非空）∧ 存在明确
      expected output（golden expected_category/subcategory/selected 任一非空）。
    - 以下一律 automatic_not_evaluable，不得推导 correctness：
      PENDING_HUMAN_REVIEW / REVIEW_REQUIRED / ERROR / AMBIGUOUS /
      NEEDS_HUMAN_REVIEW（shadow 审计是风险发现器，不是自动最终裁判）。
    - human_evaluable 仅当：有人工行 ∧ decision ∈ {CONFIRMED, CORRECTED}。
    """
    has_generation = bool(corr_row.get("generation_observation_id"))
    verdicts = sorted({f.get("verdict") for f in findings if f.get("verdict")})
    dispositions = sorted({f.get("final_disposition") for f in findings if f.get("final_disposition")})
    issue_types = sorted({f.get("issue_type") for f in findings if f.get("issue_type")})
    golden_status = (golden or {}).get("expected_status", "")

    # 自动可评：存在明确 expected output 且规则 approved
    has_expected_output = any(
        (golden or {}).get(k)
        for k in ("expected_category", "expected_subcategory", "expected_selected")
    )
    rule_approved = golden_status == "CONFIRMED" or bool((golden or {}).get("expected_rule_ids"))
    if not has_generation:
        auto_eval, auto_reason = False, "NO_GENERATION"
    elif not has_expected_output:
        auto_eval, auto_reason = False, "GOLDEN_NO_EXPECTED_OUTPUT"
    elif not rule_approved:
        auto_eval, auto_reason = False, "GOLDEN_NOT_RULE_APPROVED"
    else:
        auto_eval, auto_reason = True, ""
    # 上述任一"永远不判对错"状态均压制自动 correctness（即使有期望输出）
    if auto_eval and (
        golden_status == "PENDING_HUMAN_REVIEW"
        or any(v in AUTO_NEVER_CORRECT_VERDICTS for v in verdicts)
        or any(d in AUTO_NEVER_CORRECT_DISPOSITIONS for d in dispositions)
    ):
        auto_eval, auto_reason = False, "VERIFIER_FLAGGED_NEEDS_REVIEW"

    # 人工可评
    if not has_generation:
        human_eval, human_reason = False, "NO_GENERATION"
    elif human is None:
        human_eval, human_reason = False, "NO_HUMAN"
    elif (human.get("human_decision") or "") in HUMAN_EVALUABLE_DECISIONS:
        human_eval, human_reason = True, ""
    else:
        human_eval, human_reason = False, "HUMAN_UNRESOLVED"

    return {
        "verdicts": verdicts,
        "final_dispositions": dispositions,
        "issue_types": issue_types,
        "golden_status": golden_status,
        "automatic_evaluable": auto_eval,
        "automatic_not_evaluable_reason": auto_reason,
        "human_evaluable": human_eval,
        "human_not_evaluable_reason": human_reason,
    }


# ── 报告生成 ────────────────────────────────────────────────


def compute_dry_run(
    *,
    correlation_rows: list[dict],
    findings_by_vid: dict[str, list[dict]],
    golden_by_vid: dict[str, dict],
    human_by_vid: dict[str, dict],
) -> dict:
    """汇总 dry-run 统计（仅对 MATCHED 且带 generation 的行评可评性）。"""
    matched = [r for r in correlation_rows if r["physical_variable_id"] and r["match_method"] in (MATCH_METHOD_EXACT, MATCH_METHOD_NAME_UNIQUE)]
    ambiguous = [r for r in correlation_rows if r["match_method"] in (MATCH_METHOD_AMBIGUOUS_TRIPLE, MATCH_METHOD_AMBIGUOUS_NAME)]
    unmatched = [r for r in correlation_rows if r["match_method"] in (MATCH_METHOD_UNMATCHED_TRIPLE, MATCH_METHOD_UNMATCHED_NAME)]

    auto_eval = auto_not = human_eval = human_not = 0
    not_eval_reasons: dict[str, int] = {}
    by_verdict: dict[str, int] = {}
    by_disposition: dict[str, int] = {}
    by_industry: dict[str, int] = {}
    by_stage: dict[str, int] = {}

    for row in matched:
        vid = row["physical_variable_id"]
        cls = classify_evaluability(row, findings_by_vid.get(vid, []), golden_by_vid.get(vid), human_by_vid.get(vid))
        row["_class"] = cls
        if cls["automatic_evaluable"]:
            auto_eval += 1
        else:
            auto_not += 1
            reason = cls["automatic_not_evaluable_reason"]
            not_eval_reasons[f"auto:{reason}"] = not_eval_reasons.get(f"auto:{reason}", 0) + 1
        if cls["human_evaluable"]:
            human_eval += 1
        else:
            human_not += 1
            reason = cls["human_not_evaluable_reason"]
            not_eval_reasons[f"human:{reason}"] = not_eval_reasons.get(f"human:{reason}", 0) + 1
        by_industry[row["industry"]] = by_industry.get(row["industry"], 0) + 1
        by_stage[row["stage"]] = by_stage.get(row["stage"], 0) + 1
        for v in cls["verdicts"]:
            by_verdict[v] = by_verdict.get(v, 0) + 1
        for d in cls["final_dispositions"]:
            by_disposition[d] = by_disposition.get(d, 0) + 1
        if not cls["verdicts"]:
            by_verdict["NO_FINDINGS"] = by_verdict.get("NO_FINDINGS", 0) + 1
        if not cls["final_dispositions"]:
            by_disposition["NO_FINDINGS"] = by_disposition.get("NO_FINDINGS", 0) + 1

    return {
        "matched_generation_cases": len(matched),
        "ambiguous_cases": len(ambiguous),
        "unmatched_cases": len(unmatched),
        "automatic_evaluable": auto_eval,
        "automatic_not_evaluable": auto_not,
        "human_evaluable": human_eval,
        "human_not_evaluable": human_not,
        "not_evaluable_reasons": dict(sorted(not_eval_reasons.items())),
        "by_industry": dict(sorted(by_industry.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "by_verdict": dict(sorted(by_verdict.items())),
        "by_final_disposition": dict(sorted(by_disposition.items())),
    }


def dump_correlation_index(rows: list[dict], path: str | Path) -> None:
    """correlation_index.jsonl（去掉内部 _class 字段）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")


def dump_csv(rows: list[dict], path: str | Path, columns: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in columns})
