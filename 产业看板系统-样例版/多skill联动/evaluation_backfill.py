# -*- coding: utf-8 -*-
"""Phase 2a：Verifier case ↔ Langfuse generation 自动 evaluation backfill（dry-run）。

只读流程：
1. 扫描 run-root（默认 workflow_runs/）下带 audit_report.json 的 run。
2. 用 run 短 id 推导 trace id（md5(短id)；兼容旧版零填充 id），从 Langfuse
   拉取 trace 与 generation input（items）。
3. run 内重建关联（evaluation_correlation.correlate_items），输出
   audit/evaluation/correlation_index.jsonl。
4. 汇总 dry-run 统计（匹配/歧义/未匹配/自动可评/人工可评），
   **不调用任何 Langfuse score API**。

输出（workflow_runs/<run>/audit/evaluation/）：
- correlation_index.jsonl
- evaluation_dry_run.json / evaluation_dry_run.csv
- unmatched_cases.csv / ambiguous_cases.csv
- human_cases.csv（--human-pack 时：人工确认身份恢复）

用法：
  python scripts/evaluation_backfill.py [--run-root workflow_runs] [--run <目录名>]
      [--no-langfuse] [--human-pack <xlsx> --human-run <run目录> --human-raw-file-hash <hash>]
      [--human-audit-manifest <外部 audit_report.json>] [--human-findings <外部 audit_report.json>]
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from evaluation_correlation import (  # noqa: E402
    MATCH_METHOD_AMBIGUOUS_NAME,
    MATCH_METHOD_AMBIGUOUS_TRIPLE,
    MATCH_METHOD_EXACT,
    MATCH_METHOD_NAME_UNIQUE,
    MATCH_METHOD_UNMATCHED_NAME,
    MATCH_METHOD_UNMATCHED_TRIPLE,
    classify_evaluability,
    compute_dry_run,
    correlate_human_rows,
    correlate_items,
    dump_correlation_index,
    dump_csv,
    evaluation_key,
    load_directory_rows,
    parse_generation_input,
    parse_generation_output,
    physical_variable_id,
    score_id,
)

EVAL_DIR_NAME = "evaluation"
MATCHED_METHODS = (MATCH_METHOD_EXACT, MATCH_METHOD_NAME_UNIQUE)
AMBIGUOUS_METHODS = (MATCH_METHOD_AMBIGUOUS_TRIPLE, MATCH_METHOD_AMBIGUOUS_NAME)
UNMATCHED_METHODS = (MATCH_METHOD_UNMATCHED_TRIPLE, MATCH_METHOD_UNMATCHED_NAME)

DRY_RUN_COLUMNS = [
    "workflow_run_id", "industry", "stage", "physical_variable_id", "original_name",
    "sheet", "col", "unit", "frequency", "match_method", "generation_observation_id",
    "batch_index", "prompt_name", "prompt_version", "prompt_hash", "model",
    "verdicts", "final_dispositions", "issue_types", "golden_status",
    "human_decision", "automatic_evaluable", "automatic_not_evaluable_reason",
    "human_evaluable", "human_not_evaluable_reason", "evaluation_key",
    "score_id_verifier_status", "score_id_human_decision",
]


def short_run_id(run_dir_name: str) -> str:
    """run 目录名末段（<UTC>_<12hex> → 12hex 短 id）。"""
    return run_dir_name.rsplit("_", 1)[-1]


def trace_id_candidates(short_id: str) -> list[str]:
    """trace id 候选：md5(短id)（现行）；旧版零填充 32 位（历史兼容）。"""
    candidates = [hashlib.md5(short_id.encode("utf-8")).hexdigest()]
    if len(short_id) == 12 and all(c in "0123456789abcdef" for c in short_id):
        candidates.append(short_id.zfill(32))
    return candidates


class LangfuseReader:
    """Langfuse 公共 API 只读访问（Basic auth；无 SDK 依赖；429 退避重试）。"""

    def __init__(self, base_url: str, public_key: str, secret_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        self.timeout = timeout

    def _get(self, url: str, retries: int = 5) -> Any:
        import time

        for attempt in range(1, retries + 1):
            req = urllib.request.Request(url, headers={"Authorization": f"Basic {self.token}"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < retries:
                    time.sleep(5 * attempt)  # 分钟级配额，较长退避
                    continue
                if exc.code == 404:
                    raise
                raise
        raise RuntimeError(f"GET {url} failed after {retries} attempts")

    def fetch_trace(self, trace_id: str) -> dict | None:
        """拉取单条 trace；404 → None（无此 trace）。"""
        try:
            return self._get(f"{self.base_url}/api/public/traces/{trace_id}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def fetch_all_traces(self) -> dict[str, dict]:
        """一次性拉取全部 trace（list 分页 + 逐条完整内容），返回 {trace_id: trace}。"""
        trace_ids: list[str] = []
        page = 1
        while True:
            data = self._get(f"{self.base_url}/api/public/traces?limit=100&page={page}")
            batch = data.get("data", [])
            trace_ids.extend(t.get("id") for t in batch if t.get("id"))
            meta = data.get("meta", {})
            if page >= meta.get("totalPages", 1) or not batch:
                break
            page += 1
        out: dict[str, dict] = {}
        for tid in trace_ids:
            out[tid] = self._get(f"{self.base_url}/api/public/traces/{tid}")
        return out


def extract_generations(trace: dict) -> list[dict]:
    """从 trace 中提取带 input 的 GENERATION 观测。"""
    gens = []
    for obs in trace.get("observations", []):
        if obs.get("type") != "GENERATION":
            continue
        gens.append(obs)
    return gens


def build_correlation_for_run(
    *,
    run_dir: Path,
    run_name: str,
    industry: str,
    raw_file_hash: str,
    reader: LangfuseReader | None,
    traces_by_id: dict[str, dict] | None = None,
) -> tuple[dict, list[dict]]:
    """处理单个 run：从预加载 trace 中关联 items → 返回 (run 统计, correlation rows)。"""
    short_id = short_run_id(run_name)
    trace = None
    trace_found = None
    metadata_run_id = ""
    if traces_by_id is not None:
        for tid in trace_id_candidates(short_id):
            if tid in traces_by_id:
                trace = traces_by_id[tid]
                trace_found = tid
                break

    rows: list[dict] = []
    generations = 0
    items_total = 0
    stat = {
        "run_id": run_name,
        "short_run_id": short_id,
        "industry": industry,
        "trace_found": trace_found,
        "generations": 0,
        "items_total": 0,
    }
    if trace is None:
        stat["trace_status"] = "NO_TRACE" if reader is not None else "LANGFUSE_DISABLED"
        return stat, rows

    stat["trace_status"] = "TRACE_FOUND"
    # metadata 校验（观测 metadata 的 workflow_run_id 应等于短 id）
    for obs in trace.get("observations", []):
        md = obs.get("metadata") or {}
        if md.get("workflow_run_id"):
            metadata_run_id = md["workflow_run_id"]
            break
    stat["trace_metadata_run_id"] = metadata_run_id
    if metadata_run_id and metadata_run_id != short_id:
        stat["trace_metadata_mismatch"] = True

    catalog = load_directory_rows(run_dir / "02_financial_variable_curation" / "directory_marked.xlsx")
    catalog_index = {"triple": {}, "name": {}}
    for r in catalog:
        catalog_index["triple"].setdefault((r["sheet"], r["name"], r["unit"]), []).append(r)
        catalog_index["name"].setdefault(r["name"], []).append(r)
    stat["catalog_rows"] = len(catalog)

    gens = extract_generations(trace)
    generations = len(gens)
    stat["generations"] = generations
    batch_start = 0
    for gen in gens:
        md = gen.get("metadata") or {}
        prompt_name = md.get("prompt_name") or gen.get("name") or ""
        prompt_version = md.get("prompt_version") or ""
        prompt_hash = md.get("prompt_hash") or ""
        model = gen.get("model") or ""
        stage = md.get("stage") or ""
        items = parse_generation_input(gen.get("input"))
        items_total += len(items)
        if stage == "ai_disambiguation" and items:
            new_rows = correlate_items(
                workflow_run_id=short_id,
                industry=industry,
                stage=stage,
                observation_id=gen.get("id") or "",
                trace_id=trace_found or "",
                batch_index_start=batch_start,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                model=model,
                items=items,
                catalog_index=catalog_index,
                raw_file_hash=raw_file_hash,
            )
            # AI 结果（generation output）回联：本地 variable_id → major/sub
            ai_map = parse_generation_output(gen.get("output"))
            if ai_map:
                for r in new_rows:
                    ai = ai_map.get(r.get("item_variable_id", ""))
                    if ai:
                        r["ai_major"] = ai["major"]
                        r["ai_sub"] = ai["sub"]
            rows.extend(new_rows)
        batch_start += len(items)
    stat["items_total"] = items_total
    return stat, rows


def load_golden_index(path: Path) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    if not path.exists():
        return idx
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        cid = str(case.get("case_id") or "")
        suffix = cid.rsplit("_", 1)[-1]
        if len(suffix) == 16 and all(c in "0123456789abcdef" for c in suffix):
            idx.setdefault(suffix, case)
    return idx


def load_findings_index(path: Path) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    if not path.exists():
        return idx
    report = json.loads(path.read_text(encoding="utf-8"))
    for f in report.get("findings", []):
        vid = f.get("physical_variable_id")
        if vid:
            idx.setdefault(vid, []).append(f)
    return idx


def crosscheck_human_vids(human_rows: list[dict], findings: dict[str, list[dict]]) -> None:
    """人工恢复的 vid 与（外部）审计 findings 交叉验证：OK / MISMATCH / NO_AUDIT。"""
    name_to_vids: dict[str, set[str]] = {}
    for vid, lst in findings.items():
        for f in lst:
            name = str(f.get("original_name") or "").strip()
            if name:
                name_to_vids.setdefault(name, set()).add(vid)
    for hr in human_rows:
        vid = hr.get("physical_variable_id", "")
        if not vid or hr.get("match_method") != MATCH_METHOD_NAME_UNIQUE:
            hr["audit_crosscheck"] = "-"
            continue
        if vid in findings:
            hr["audit_crosscheck"] = "OK"
        else:
            audit_vids = name_to_vids.get(hr.get("original_name", ""), set())
            hr["audit_crosscheck"] = "MISMATCH" if audit_vids and vid not in audit_vids else "NO_AUDIT"


def load_human_pack(path: Path) -> list[dict]:
    """priority_review_pack.xlsx → human 行（case_id/原始指标/人工值）。"""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    hdr = [str(c or "").strip() for c in rows[0]]
    idx = {name: i for i, name in enumerate(hdr)}
    out = []
    for r in rows[1:]:
        if not r or not r[0]:
            continue
        out.append(
            {
                "case_id": str(r[idx["case_id"]] or "").strip(),
                "original_name": str(r[idx["原始指标"]] or "").strip(),
                "human_decision": str(r[idx["Human decision"]] or "").strip(),
                "human_major": str(r[idx["Human 大类"]] or "").strip(),
                "human_sub": str(r[idx["Human 子类"]] or "").strip(),
                "human_selected": str(r[idx["Human 是否选中"]] or "").strip(),
                "human_notes": str(r[idx["Human notes"]] or "").strip(),
            }
        )
    return out


def planned_scores(row: dict, cls: dict, human_row: dict | None, audit_run_id: str) -> list[dict]:
    """dry-run 计划写入的 score 清单（不调用 API；value_hint 仅供审阅）。"""
    vid = row.get("physical_variable_id", "")
    key = evaluation_key(vid, row.get("prompt_version", ""), row.get("prompt_hash", ""))
    out = []
    if cls["automatic_evaluable"]:
        for name, hint in (("verifier_status", cls["golden_status"] or "NOT_EVALUATED"),
                           ("verifier_verdict", ",".join(cls["verdicts"])),
                           ("error_type", ",".join(cls["issue_types"]))):
            out.append({
                "score_name": name, "score_source": "verifier", "data_type": "CATEGORICAL",
                "score_id": score_id(key, audit_run_id, "verifier", name), "value_hint": hint,
            })
    if cls["human_evaluable"] and human_row:
        for name, hint, dtype in (
            ("human_decision", human_row.get("human_decision", ""), "CATEGORICAL"),
            ("human_classification_correct", "NEEDS_OUTPUT_JOIN", "BOOLEAN"),
            ("expected_output", json.dumps(
                {"大类": human_row.get("human_major", ""), "子类": human_row.get("human_sub", ""),
                 "是否选中": human_row.get("human_selected", "")}, ensure_ascii=False), "CORRECTION"),
        ):
            out.append({
                "score_name": name, "score_source": "human", "data_type": dtype,
                "score_id": score_id(key, audit_run_id, "human", name), "value_hint": hint,
            })
    return out


def process_run(
    *,
    run_dir: Path,
    run_name: str,
    reader: LangfuseReader | None,
    traces_by_id: dict[str, dict] | None,
    human_pack: list[dict] | None,
    human_run_catalog: Path | None,
    human_raw_file_hash: str,
    human_findings: dict[str, list[dict]] | None,
) -> dict:
    audit_dir = run_dir / "audit"
    manifest: dict = {}
    report_data: dict = {}
    manifest_path = audit_dir / "audit_manifest.json"
    report_path = audit_dir / "audit_report.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if report_path.exists():
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
    raw_file_hash = (
        manifest.get("raw_file_hash")
        or report_data.get("manifest", {}).get("raw_file_hash", "")
        or human_raw_file_hash
    )
    industry = manifest.get("industry") or report_data.get("manifest", {}).get("industry", "unknown")

    stat, corr_rows = build_correlation_for_run(
        run_dir=run_dir, run_name=run_name, industry=industry,
        raw_file_hash=raw_file_hash, reader=reader, traces_by_id=traces_by_id,
    )

    golden = load_golden_index(audit_dir / "golden" / "golden_cases.jsonl")
    findings = load_findings_index(audit_dir / "audit_report.json")

    # 人工：仅当 pack 的 source run 就是本 run 时才做 run 内恢复
    human_rows: list[dict] = []
    if human_pack is not None and human_run_catalog is not None and human_raw_file_hash:
        catalog = load_directory_rows(human_run_catalog)
        catalog_index = {"triple": {}, "name": {}}
        for r in catalog:
            catalog_index["triple"].setdefault((r["sheet"], r["name"], r["unit"]), []).append(r)
            catalog_index["name"].setdefault(r["name"], []).append(r)
        human_rows = correlate_human_rows(
            workflow_run_id=short_run_id(run_name), industry=industry,
            human_rows=human_pack, catalog_index=catalog_index,
            raw_file_hash=human_raw_file_hash,
        )
        if human_findings is not None:
            crosscheck_human_vids(human_rows, human_findings)
        else:
            for hr in human_rows:
                hr["audit_crosscheck"] = "-"

    human_by_vid = {hr["physical_variable_id"]: hr for hr in human_rows if hr["physical_variable_id"]}

    # 汇总 + 可评性 + 计划 score
    stats = compute_dry_run(
        correlation_rows=corr_rows,
        findings_by_vid=findings,
        golden_by_vid=golden,
        human_by_vid=human_by_vid,
    )
    audit_run_id = report_data.get("manifest", {}).get("audit_run_id", "")
    for row in corr_rows:
        if row["physical_variable_id"]:
            cls = classify_evaluability(
                row, findings.get(row["physical_variable_id"], []),
                golden.get(row["physical_variable_id"]),
                human_by_vid.get(row["physical_variable_id"]),
            )
            row["_class"] = cls
            human_row = human_by_vid.get(row["physical_variable_id"])
            row["_planned_scores"] = planned_scores(row, cls, human_row, audit_run_id)

    # 输出
    eval_dir = audit_dir / EVAL_DIR_NAME
    eval_dir.mkdir(parents=True, exist_ok=True)
    dump_correlation_index(corr_rows, eval_dir / "correlation_index.jsonl")

    csv_rows = []
    for row in corr_rows:
        cls = row.get("_class") or {}
        vid = row.get("physical_variable_id", "")
        key = evaluation_key(vid, row.get("prompt_version", ""), row.get("prompt_hash", ""))
        human_row = next((hr for hr in human_rows if hr["physical_variable_id"] == vid), None)
        csv_rows.append({
            "workflow_run_id": row.get("workflow_run_id"), "industry": row.get("industry"),
            "stage": row.get("stage"), "physical_variable_id": vid,
            "original_name": row.get("original_name"), "sheet": row.get("sheet"),
            "col": row.get("catalog_col", ""), "unit": row.get("unit"),
            "frequency": row.get("frequency"), "match_method": row.get("match_method"),
            "generation_observation_id": row.get("generation_observation_id"),
            "batch_index": row.get("batch_index"), "prompt_name": row.get("prompt_name"),
            "prompt_version": row.get("prompt_version"), "prompt_hash": row.get("prompt_hash"),
            "model": row.get("model"), "verdicts": ",".join(cls.get("verdicts", [])),
            "final_dispositions": ",".join(cls.get("final_dispositions", [])),
            "issue_types": ",".join(cls.get("issue_types", [])),
            "golden_status": cls.get("golden_status", ""),
            "human_decision": (human_row or {}).get("human_decision", ""),
            "automatic_evaluable": cls.get("automatic_evaluable", False),
            "automatic_not_evaluable_reason": cls.get("automatic_not_evaluable_reason", ""),
            "human_evaluable": cls.get("human_evaluable", False),
            "human_not_evaluable_reason": cls.get("human_not_evaluable_reason", ""),
            "evaluation_key": key,
            "score_id_verifier_status": score_id(key, manifest.get("audit_run_id", ""), "verifier", "verifier_status"),
            "score_id_human_decision": score_id(key, manifest.get("audit_run_id", ""), "human", "human_decision"),
        })
    dump_csv(csv_rows, eval_dir / "evaluation_dry_run.csv", DRY_RUN_COLUMNS)

    unmatched = [r for r in corr_rows if r["match_method"] in UNMATCHED_METHODS]
    dump_csv(
        [{"run_id": r["workflow_run_id"], "original_name": r["original_name"], "sheet": r["sheet"],
          "unit": r["unit"], "reason": r["match_method"]} for r in unmatched],
        eval_dir / "unmatched_cases.csv",
        ["run_id", "original_name", "sheet", "unit", "reason"],
    )
    ambiguous = [r for r in corr_rows if r["match_method"] in AMBIGUOUS_METHODS]
    dump_csv(
        [{"run_id": r["workflow_run_id"], "original_name": r["original_name"], "sheet": r["sheet"],
          "unit": r["unit"], "candidate_cols": ",".join(str(c) for c in r.get("candidate_cols", []))}
         for r in ambiguous],
        eval_dir / "ambiguous_cases.csv",
        ["run_id", "original_name", "sheet", "unit", "candidate_cols"],
    )
    if human_rows:
        dump_csv(human_rows, eval_dir / "human_cases.csv",
                 ["source_case_id", "workflow_run_id", "original_name", "physical_variable_id",
                  "match_method", "sheet", "unit", "frequency",
                  "human_decision", "human_major", "human_sub", "human_selected",
                  "human_notes", "audit_crosscheck"])

    run_report = {
        "run_id": run_name,
        "short_run_id": short_run_id(run_name),
        "industry": industry,
        **stat,
        "golden_cases": len(golden),
        "findings_variables": len(findings),
        "stats": stats,
        "human_cases": {
            "total": len(human_rows),
            "matched": sum(1 for h in human_rows if h["match_method"] == MATCH_METHOD_NAME_UNIQUE),
            "ambiguous": sum(1 for h in human_rows if h["match_method"] == MATCH_METHOD_AMBIGUOUS_NAME),
            "unmatched": sum(1 for h in human_rows if h["match_method"] == MATCH_METHOD_UNMATCHED_NAME),
        },
    }
    (eval_dir / "evaluation_dry_run.json").write_text(
        json.dumps(run_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return run_report, corr_rows, human_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 2a evaluation backfill (dry-run, 只读)")
    parser.add_argument("--run-root", default=str(PROJECT_ROOT / "workflow_runs"))
    parser.add_argument("--run", default=None, help="只处理指定 run 目录名")
    parser.add_argument("--no-langfuse", action="store_true", help="不访问 Langfuse（跳过 trace 拉取）")
    parser.add_argument("--human-pack", default=None, help="priority_review_pack.xlsx 路径")
    parser.add_argument("--human-run", default=None, help="人工 pack 所属 run 目录")
    parser.add_argument("--human-raw-file-hash", default=None, help="人工 pack 所属 run 的 raw_file_hash")
    parser.add_argument("--human-audit-manifest", default=None, help="从外部 audit_report.json 取 raw_file_hash")
    parser.add_argument("--human-findings", default=None, help="外部 audit_report.json（交叉验证人工恢复的 vid）")
    args = parser.parse_args(argv)

    reader = None
    if not args.no_langfuse:
        base = os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        if pk and sk:
            reader = LangfuseReader(base, pk, sk)
        else:
            print("WARNING: LANGFUSE keys 未配置，按 --no-langfuse 处理", file=sys.stderr)

    run_root = Path(args.run_root).resolve()
    run_dirs = sorted(d for d in run_root.iterdir() if d.is_dir())
    if args.run:
        run_dirs = [d for d in run_dirs if d.name == args.run]

    # 一次性预加载全部 Langfuse traces（避免逐 run 轮询触发限流）
    traces_by_id: dict[str, dict] = {}
    if reader is not None:
        try:
            traces_by_id = reader.fetch_all_traces()
            print(f"preloaded {len(traces_by_id)} traces", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: Langfuse 预加载失败，按 --no-langfuse 处理: {exc}", file=sys.stderr)
            reader = None
            traces_by_id = {}

    human_pack = load_human_pack(Path(args.human_pack)) if args.human_pack else None
    human_run_name = Path(args.human_run).name if args.human_run else ""
    human_run_catalog = None
    human_raw_hash = args.human_raw_file_hash or ""
    human_findings = None
    if human_pack and human_run_name:
        human_run_catalog = Path(args.human_run) / "02_financial_variable_curation" / "directory_marked.xlsx"
        if args.human_audit_manifest:
            ext = json.loads(Path(args.human_audit_manifest).read_text(encoding="utf-8"))
            human_raw_hash = ext.get("manifest", {}).get("raw_file_hash") or human_raw_hash
    if args.human_findings:
        human_findings = load_findings_index(Path(args.human_findings))

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "phase": "2a",
        "langfuse": "disabled" if reader is None else "enabled",
        "runs_scanned": len(run_dirs),
        "runs_with_audit": 0,
        "runs_with_trace": 0,
        "runs_with_generations": 0,
        "totals": {
            "matched_generation_cases": 0, "ambiguous_cases": 0, "unmatched_cases": 0,
            "automatic_evaluable": 0, "automatic_not_evaluable": 0,
            "human_evaluable": 0, "human_not_evaluable": 0,
        },
        "runs": [],
    }
    for run_dir in run_dirs:
        has_audit = (run_dir / "audit" / "audit_report.json").exists()
        is_human_run = run_dir.name == human_run_name
        if not (has_audit or (is_human_run and human_pack)):
            continue
        if has_audit:
            report["runs_with_audit"] += 1
        try:
            run_report, _rows, _hrows = process_run(
                run_dir=run_dir, run_name=run_dir.name, reader=reader,
                traces_by_id=traces_by_id,
                human_pack=human_pack,
                human_run_catalog=human_run_catalog if is_human_run else None,
                human_raw_file_hash=human_raw_hash if is_human_run else "",
                human_findings=human_findings if is_human_run else None,
            )
        except Exception as exc:  # noqa: BLE001 —— best-effort，单 run 失败不阻断
            run_report = {"run_id": run_dir.name, "error": str(exc)[:300]}
        report["runs"].append(run_report)
        if run_report.get("trace_found"):
            report["runs_with_trace"] += 1
        if run_report.get("generations", 0) > 0:
            report["runs_with_generations"] += 1
        st = run_report.get("stats") or {}
        for k in report["totals"]:
            report["totals"][k] += st.get(k, 0)

    # 孤儿 trace（有 generation 但无本地 run dir）——仅信息，不评分
    orphan: list[dict] = []
    local_short_ids = {r.get("short_run_id") for r in report["runs"] if r.get("short_run_id")}
    for tid, t in traces_by_id.items():
        gens = extract_generations(t)
        if not gens:
            continue
        md = gens[0].get("metadata") or {}
        run_id = md.get("workflow_run_id") or ""
        if run_id in local_short_ids:
            continue
        items = sum(len(parse_generation_input(g.get("input"))) for g in gens)
        orphan.append({
            "trace_id": tid, "run_id": run_id, "stage": md.get("stage") or "",
            "generations": len(gens), "items": items,
        })
    report["orphan_traces"] = orphan

    out_path = Path(args.run_root).resolve() / "evaluation_dry_run_summary.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 紧凑控制台摘要
    t = report["totals"]
    human = next((r for r in report["runs"] if r.get("human_cases", {}).get("total")), None)
    print(json.dumps({
        "mode": report["mode"], "langfuse": report["langfuse"],
        "runs_scanned": report["runs_scanned"], "runs_with_audit": report["runs_with_audit"],
        "runs_with_trace": report["runs_with_trace"],
        "runs_with_generations": report["runs_with_generations"],
        "totals": t,
        "human_confirmed_recovered": (human or {}).get("human_cases"),
        "orphan_traces": len(orphan),
        "errors": [r["error"][:120] for r in report["runs"] if r.get("error")],
    }, ensure_ascii=False, indent=2))
    return 0


# ── Phase 2c：生产 Evaluation 闭环（workflow 自然流程内自动执行）──────────

_HUMAN_EVALUABLE_DECISIONS = frozenset({"CONFIRMED", "CORRECTED"})


_OBS_MODULE = None


def _load_observability_module():
    """惰性加载 workflow/observability（避免触发 workflow/__init__）。"""
    global _OBS_MODULE
    if _OBS_MODULE is None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "workflow_observability",
            str(PROJECT_ROOT / "workflow" / "observability.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        _OBS_MODULE = mod
    return _OBS_MODULE


def _load_record_evaluation():
    return _load_observability_module().record_evaluation


def flush_observability() -> None:
    """进程退出前冲刷 score 事件（异步批量发送，不 flush 会丢）。"""
    try:
        _load_observability_module().flush()
    except Exception:  # noqa: BLE001
        pass


def auto_write_scores(
    *,
    corr_rows: list[dict],
    human_rows: list[dict],
    findings: dict[str, list[dict]],
    golden: dict[str, dict],
    audit_run_id: str,
    record_fn=None,
) -> dict:
    """对满足门控的 case 自动写 verifier / human scores（Phase 2c）。

    门控（与 record_evaluation 内部门控一致，这里做第一层过滤）：
    - 仅 unique correlation（EXACT_TRIPLE）且有真实 generation 的 case
    - correctness 类：存在明确 expected output（golden 期望字段）+ AI 结果可回联
      + verifier 状态可裁定（classify_evaluability 已压制 forbidden 状态）
    - human UNRESOLVED → 只写 human_decision
    - 无 generation 的历史 human case → 不写（skip: HUMAN_NO_GENERATION）
    """
    record_fn = record_fn or _load_record_evaluation()
    human_by_vid = {h["physical_variable_id"]: h for h in human_rows if h.get("physical_variable_id")}
    written: list[dict] = []
    skipped: list[dict] = []
    if not audit_run_id:
        return {
            "written": [], "written_count": 0, "skipped_count": len(corr_rows),
            "skip_reasons": {"NO_AUDIT_RUN_ID": len(corr_rows)},
        }

    def _skip(vid, name, reason, extra=None):
        skipped.append({"vid": vid, "original_name": name, "reason": reason, **(extra or {})})

    for row in corr_rows:
        vid = row.get("physical_variable_id", "")
        name = row.get("original_name", "")
        if row.get("match_method") != MATCH_METHOD_EXACT or not vid:
            _skip(vid, name, row.get("match_method", "NO_CORRELATION"))
            continue
        if not row.get("generation_observation_id"):
            _skip(vid, name, "NO_GENERATION")
            continue
        obs_id = row.get("generation_observation_id")
        run_id = row.get("workflow_run_id", "")
        stage = row.get("stage", "")
        cls = classify_evaluability(row, findings.get(vid, []), golden.get(vid), human_by_vid.get(vid))

        # verifier 非 correctness 分（无 correctness 门控）
        status = cls["golden_status"] or (
            "CONFIRMED_ERROR" if "CONFIRMED_ERROR" in cls["final_dispositions"]
            else ("NEEDS_HUMAN_REVIEW" if "NEEDS_HUMAN_REVIEW" in cls["final_dispositions"] else "NOT_EVALUATED")
        )
        common_meta = {"verifier_status": status}
        written.append({"vid": vid, "name": name, "score_name": "verifier_status", "value": status})
        record_fn(
            physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
            observation_id=obs_id, score_name="verifier_status", value=status,
            data_type="CATEGORICAL", source="verifier", audit_run_id=audit_run_id,
            metadata=common_meta,
        )
        if cls["verdicts"]:
            value = ";".join(cls["verdicts"])
            written.append({"vid": vid, "name": name, "score_name": "verifier_verdict", "value": value})
            record_fn(
                physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
                observation_id=obs_id, score_name="verifier_verdict", value=value,
                data_type="CATEGORICAL", source="verifier", audit_run_id=audit_run_id,
                metadata=common_meta,
            )
        if cls["issue_types"]:
            value = ";".join(cls["issue_types"])
            written.append({"vid": vid, "name": name, "score_name": "verifier_error_type", "value": value})
            record_fn(
                physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
                observation_id=obs_id, score_name="verifier_error_type", value=value,
                data_type="CATEGORICAL", source="verifier", audit_run_id=audit_run_id,
                metadata=common_meta,
            )

        # verifier correctness（严格门控）
        if cls["automatic_evaluable"]:
            g = golden.get(vid) or {}
            exp_cat, exp_sub = g.get("expected_category"), g.get("expected_subcategory")
            ai_major, ai_sub = row.get("ai_major"), row.get("ai_sub")
            if ai_major is None or exp_cat is None:
                _skip(vid, name, "NO_AI_RESULT_OR_EXPECTED",
                      {"ai_major": ai_major, "expected_category": exp_cat})
            else:
                correct = bool(ai_major == exp_cat and (exp_sub is None or ai_sub == exp_sub))
                written.append({"vid": vid, "name": name, "score_name": "verifier_classification_correct", "value": correct})
                record_fn(
                    physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
                    observation_id=obs_id, score_name="verifier_classification_correct",
                    value=correct, data_type="BOOLEAN", source="verifier",
                    audit_run_id=audit_run_id,
                    expected_output={"大类": exp_cat, "子类": exp_sub},
                    metadata={**common_meta, "ai_result": {"大类": ai_major, "子类": ai_sub}},
                )
        else:
            _skip(vid, name, cls["automatic_not_evaluable_reason"])

        # human scores（仅当该 vid 存在 generation 关联）
        hr = human_by_vid.get(vid)
        if hr:
            decision = hr.get("human_decision", "")
            if decision:
                written.append({"vid": vid, "name": name, "score_name": "human_decision", "value": decision})
                record_fn(
                    physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
                    observation_id=obs_id, score_name="human_decision", value=decision,
                    data_type="CATEGORICAL", source="human", audit_run_id=audit_run_id,
                    metadata={"human_decision": decision,
                              "source_record_id": hr.get("source_case_id") or f"human_{vid}"},
                )
            if decision in _HUMAN_EVALUABLE_DECISIONS:
                human_out = {k: v for k, v in (
                    ("大类", hr.get("human_major")), ("子类", hr.get("human_sub")),
                    ("是否选中", hr.get("human_selected"))) if v}
                if human_out:
                    written.append({"vid": vid, "name": name, "score_name": "human_expected_output", "value": human_out})
                    record_fn(
                        physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
                        observation_id=obs_id, score_name="human_expected_output",
                        value=json.dumps(human_out, ensure_ascii=False),
                        data_type="CORRECTION", source="human", audit_run_id=audit_run_id,
                        expected_output=human_out,
                        metadata={"human_decision": decision,
                                  "source_record_id": hr.get("source_case_id") or f"human_{vid}"},
                    )
                    ai_major, ai_sub = row.get("ai_major"), row.get("ai_sub")
                    if ai_major is not None and hr.get("human_major"):
                        correct = bool(
                            ai_major == str(hr["human_major"]).strip()
                            and (not hr.get("human_sub") or ai_sub == str(hr["human_sub"]).strip())
                        )
                        written.append({"vid": vid, "name": name, "score_name": "human_classification_correct", "value": correct})
                        record_fn(
                            physical_variable_id=vid, stage=stage, workflow_run_id=run_id,
                            observation_id=obs_id, score_name="human_classification_correct",
                            value=correct, data_type="BOOLEAN", source="human",
                            audit_run_id=audit_run_id, expected_output=human_out,
                            metadata={"human_decision": decision,
                                      "source_record_id": hr.get("source_case_id") or f"human_{vid}"},
                        )
                else:
                    _skip(vid, name, "HUMAN_NO_EXPECTED_VALUES")
            elif decision == "UNRESOLVED":
                _skip(vid, name, "HUMAN_UNRESOLVED")  # decision 已写，correctness 不写
        # 历史 human case 无 generation（corr_rows 无此 vid）→ 自然跳过（不在循环内）

    skip_reasons: dict[str, int] = {}
    for s in skipped:
        skip_reasons[s["reason"]] = skip_reasons.get(s["reason"], 0) + 1
    return {
        "written": written,
        "written_count": len(written),
        "skipped_count": len(skipped),
        "skip_reasons": dict(sorted(skip_reasons.items())),
    }


def run_auto_evaluation(
    *,
    run_dir: str | Path,
    write_scores: bool = True,
    record_fn=None,
) -> dict:
    """workflow run 完成后的自动 Evaluation 步骤（best-effort，不抛异常）。

    - 生成 correlation index + dry-run 报告（workflow_runs/<run>/audit/evaluation/）
    - write_scores=True 时对门控 case 调用 record_evaluation()
    - 任何失败都不影响业务 workflow（调用方 try/except 兜底）
    """
    run_dir = Path(run_dir).resolve()
    reader = None
    traces_by_id: dict[str, dict] = {}
    base = os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    if pk and sk:
        try:
            reader = LangfuseReader(base, pk, sk)
            # 只拉当前 run 的候选 trace（md5 / 旧版零填充），避免全量预加载触发限流
            for tid in trace_id_candidates(short_run_id(run_dir.name)):
                fetched = reader.fetch_trace(tid)
                if fetched is not None:
                    traces_by_id[tid] = fetched
        except Exception as exc:  # noqa: BLE001
            reader = None
            traces_by_id = {}
            print(f"WARNING: evaluation auto 无法访问 Langfuse（跳过 trace 关联）: {exc}", file=sys.stderr)

    report, corr_rows, human_rows = process_run(
        run_dir=run_dir, run_name=run_dir.name, reader=reader,
        traces_by_id=traces_by_id,
        human_pack=None, human_run_catalog=None, human_raw_file_hash="", human_findings=None,
    )

    # record_evaluation 需从 correlation index 解析 —— 指向本 run 所在的 run root
    os.environ.setdefault("EVAL_RUN_ROOT", str(run_dir.parent))

    result: dict = {"correlation": report, "scores": None}
    if write_scores and corr_rows:
        findings = load_findings_index(run_dir / "audit" / "audit_report.json")
        golden = load_golden_index(run_dir / "audit" / "golden" / "golden_cases.jsonl")
        audit_run_id = ""
        report_data = json.loads((run_dir / "audit" / "audit_report.json").read_text(encoding="utf-8"))
        audit_run_id = report_data.get("manifest", {}).get("audit_run_id", "")
        try:
            result["scores"] = auto_write_scores(
                corr_rows=corr_rows, human_rows=human_rows,
                findings=findings, golden=golden,
                audit_run_id=audit_run_id, record_fn=record_fn,
            )
            if record_fn is None:
                flush_observability()  # score 事件是异步批量，进程退出前必须 flush
        except Exception as exc:  # noqa: BLE001 —— 写分失败不影响 workflow
            result["scores"] = {"error": str(exc)[:300]}
    return result


if __name__ == "__main__":
    sys.exit(main())
