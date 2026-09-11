# -*- coding: utf-8 -*-
"""Unified entry point for the industry Excel workflow.

Composes:
1. Workflow: Skill1 catalog + Skill2 financial variable curation.
2. Industry-specific deterministic calibration (lithium/tin; silicon already
   includes deterministic reclassification and tags in its workflow).
3. Optional AI-assisted curation using ai_assisted_curation.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def evaluation_enabled(cli_flag: bool) -> bool:
    """Evaluation 闭环开关：--langfuse-evaluation 或 LANGFUSE_EVALUATION_ENABLED=true。
    独立于 tracing（LANGFUSE_ENABLED），可单独关闭。"""
    return cli_flag or os.getenv(
        "LANGFUSE_EVALUATION_ENABLED", ""
    ).strip().lower() in ("1", "true", "yes", "on")
sys.path.insert(0, str(PROJECT_ROOT))

from workflow.snapshots import (  # noqa: E402
    save_immutable_final,
    save_stage_snapshot,
)
from workflow.shadow_audit import run_shadow_audit  # noqa: E402


# 部署可移植：使用当前解释器（部署包内自动用本机 venv 的 python）
PYTHON = Path(sys.executable)

WORKFLOW_CONFIGS = {
    "lithium": PROJECT_ROOT / "configs" / "workflow_lithium.yaml",
    "tin": PROJECT_ROOT / "configs" / "workflow_tin.yaml",
    "silicon": PROJECT_ROOT / "configs" / "workflow_silicon.yaml",
}

CALIBRATION_SCRIPTS = {
    "lithium": PROJECT_ROOT / "scripts" / "apply_lithium_curation.py",
    "tin": PROJECT_ROOT / "scripts" / "apply_tin_curation.py",
    "silicon": None,
}

AI_SCRIPT = PROJECT_ROOT / "scripts" / "ai_assisted_curation.py"
SELECTION_SCRIPT = PROJECT_ROOT / "scripts" / "apply_industry_selection.py"
VERIFY_SCRIPT = PROJECT_ROOT / "scripts" / "verify_frequency.py"
CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check_classification_consistency.py"
SORT_SCRIPT = PROJECT_ROOT / "skills" / "dashboard-data-sorter" / "scripts" / "sort_catalog.py"
CATALOG_TOOL = PROJECT_ROOT / "scripts" / "catalog_sheet_tool.py"


def cleanup_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                print(f"  removed {path.name}")
        except OSError as exc:
            print(f"  warning: cannot remove {path}: {exc}")


def run_cmd(cmd: list[str], *, dry_run: bool, label: str) -> None:
    print(f"[{label}]")
    print("  " + " ".join(str(c) for c in cmd))
    if dry_run:
        return
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    if proc.returncode != 0:
        raise SystemExit(f"{label} failed with exit {proc.returncode}")


def read_latest_run_dir(run_root: Path) -> Path:
    pointer = run_root / "latest.json"
    if not pointer.exists():
        raise SystemExit("workflow_runs/latest.json missing; workflow did not record its run dir.")
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    run_dir = Path(payload["run_dir"])
    if not run_dir.exists():
        raise SystemExit(f"Workflow run dir from latest.json does not exist: {run_dir}")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full industry processing pipeline.")
    parser.add_argument("--industry", choices=["lithium", "tin", "silicon"], required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--provider", choices=["mock", "deepseek", "openai"], default="mock")
    parser.add_argument("--model", default=None)
    parser.add_argument("--ai", action="store_true", help="Run the AI-assisted curation layer.")
    parser.add_argument("--ai-batch-size", type=int, default=int(os.getenv("DEEPSEEK_BATCH_SIZE", "20")))
    parser.add_argument("--ai-max-concurrency", type=int, default=int(os.getenv("DEEPSEEK_MAX_CONCURRENCY", "4")))
    parser.add_argument("--ai-max-tokens", type=int, default=int(os.getenv("DEEPSEEK_MAX_TOKENS", "32000")))
    parser.add_argument("--ai-timeout", type=float, default=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "120")))
    parser.add_argument("--ai-max-retries", type=int, default=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")))
    parser.add_argument("--ai-database", default=None)
    parser.add_argument(
        "--langfuse-evaluation", action="store_true",
        help="Run 完成后自动执行 Evaluation 闭环（correlation index + 门控 score 写入；"
        "也可用 LANGFUSE_EVALUATION_ENABLED=true 开启；独立于 tracing）",
    )
    parser.add_argument("--config", default=None,
                        help="Override the workflow YAML config (deployable package: path-rewritten temp yaml).")
    parser.add_argument("--run-root", default=None,
                        help="Override the workflow run root; used by the Workflow project.")
    parser.add_argument("--skip-audit", action="store_true",
                        help="Skip the shadow audit so the Workflow project can run Result Audit separately.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-intermediates", action="store_true")
    args = parser.parse_args(argv)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Input file does not exist: {input_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output).resolve() if args.output else (
        PROJECT_ROOT / "output" / f"{input_path.stem}_workflow.xlsx"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stem = output_path.stem
    step1 = output_path.parent / f"{stem}_step1.xlsx"
    # 精简文件链：workflow 输出完整文件后，把目录表提取为 slim 文件，
    # 后续只碰目录表的步骤（校准/校验/一致性/筛选/排序）都在 slim 上跑，
    # 最后一次性 merge 回完整文件（scripts/catalog_sheet_tool.py）。
    slim = output_path.parent / f"{stem}_slim.xlsx"
    calibrated = output_path.parent / f"{stem}_calibrated.xlsx"
    verified = output_path.parent / f"{stem}_verified.xlsx"
    checked = output_path.parent / f"{stem}_checked.xlsx"
    selected = output_path.parent / f"{stem}_selected.xlsx"
    ai_slim = output_path.parent / f"{stem}_ai_slim.xlsx"
    post_sel = output_path.parent / f"{stem}_postsel.xlsx"

    # observability 上下文注入：industry 供 workflow 子进程及其步骤继承；
    # WORKFLOW_RUN_ID 由 workflow 创建时写入 env（cli.py）与
    # workflow_runs/current_run_id.txt（供本进程外围步骤读取，不用 latest.json）。
    os.environ["INDUSTRY"] = args.industry

    config = Path(args.config).resolve() if args.config else WORKFLOW_CONFIGS[args.industry]
    workflow_provider = args.provider
    if args.ai and args.provider != "mock":
        print("Warning: --ai runs one real AI pass after deterministic rules; forcing workflow provider=mock to avoid duplicate LLM calls.")
        workflow_provider = "mock"
    workflow_cmd = [
        str(PYTHON),
        "-m",
        "workflow",
        "--config",
        str(config),
        "--input",
        str(input_path),
        "--output",
        str(step1),
        "--provider",
        workflow_provider,
    ]
    if args.run_root:
        workflow_cmd += ["--run-root", str(Path(args.run_root).resolve())]
    if args.model:
        workflow_cmd += ["--model", args.model]
    run_cmd(workflow_cmd, dry_run=args.dry_run, label="1. Skill1 + Skill2 + Skill3 + Skill4 workflow")
    run_dir = None if args.dry_run else read_latest_run_dir(
        Path(args.run_root).resolve() if args.run_root else PROJECT_ROOT / "workflow_runs"
    )
    # 当前 run_id（workflow 创建时写入 current_run_id.txt）注入外围步骤 env，
    # 与 workflow_runs/<run_id> 严格对应（不使用 latest.json 的 run_id 语义）
    if not args.dry_run:
        current_run_id_file = (
            Path(args.run_root).resolve() if args.run_root else PROJECT_ROOT / "workflow_runs"
        ) / "current_run_id.txt"
        try:
            current_run_id = current_run_id_file.read_text(encoding="utf-8").strip()
            if current_run_id:
                os.environ["WORKFLOW_RUN_ID"] = current_run_id
        except OSError:
            pass

    # 从完整文件提取目录表为精简文件（同目录保存 <基础名>__full_template.xlsx
    # 模板），后续只碰目录表的步骤在精简文件上跑，大幅减少 openpyxl 全量序列化
    extract_cmd = [
        str(PYTHON),
        str(CATALOG_TOOL),
        "extract",
        str(step1),
        str(slim),
    ]
    run_cmd(extract_cmd, dry_run=args.dry_run, label="1.5 Extract catalog sheet (slim)")

    calibration_script = CALIBRATION_SCRIPTS[args.industry]
    ai_input = slim
    if calibration_script is not None:
        calibration_cmd = [
            str(PYTHON),
            str(calibration_script),
            "--input",
            str(ai_input),
            "--output",
            str(calibrated),
            "--report",
            str(calibrated.parent / f"{calibrated.stem}_report.md"),
        ]
        run_cmd(calibration_cmd, dry_run=args.dry_run, label="2. Deterministic calibration")
        if run_dir is not None:
            save_stage_snapshot(
                run_dir,
                stage="INDUSTRY_CURATION",
                source_path=calibrated,
                operation="apply_tin_curation",
                input_stage="DIRECTORY_MARK",
                script_or_operation=calibration_script.name,
            )
        ai_input = calibrated
    else:
        if not args.dry_run:
            shutil.copy2(slim, calibrated)

    verify_cmd = [
        str(PYTHON),
        str(VERIFY_SCRIPT),
        "--input",
        str(ai_input),
        "--output",
        str(verified),
        "--report",
        str(verified.parent / f"{verified.stem}_report.md"),
        # 频率推断需要读数据 sheets（日期序列），从完整文件读取
        "--data-file",
        str(step1),
    ]
    run_cmd(verify_cmd, dry_run=args.dry_run, label="3. Frequency interval verification")
    if run_dir is not None:
        save_stage_snapshot(
            run_dir,
            stage="FREQUENCY_VERIFY",
            source_path=verified,
            operation="verify_frequency",
            input_stage="INDUSTRY_CURATION",
            script_or_operation=VERIFY_SCRIPT.name,
        )
    ai_input = verified

    check_cmd = [
        str(PYTHON),
        str(CHECK_SCRIPT),
        "--input",
        str(ai_input),
        "--output",
        str(checked),
        "--report",
        str(checked.parent / f"{checked.stem}_report.md"),
        "--industry",
        args.industry,
    ]
    run_cmd(check_cmd, dry_run=args.dry_run, label="4. Classification consistency check")
    if run_dir is not None:
        save_stage_snapshot(
            run_dir,
            stage="CLASSIFICATION_CHECK",
            source_path=checked,
            operation="check_classification_consistency",
            input_stage="FREQUENCY_VERIFY",
            script_or_operation=CHECK_SCRIPT.name,
        )
    ai_input = checked

    selection_cmd = [
        str(PYTHON),
        str(SELECTION_SCRIPT),
        "--input",
        str(ai_input),
        "--output",
        str(selected),
        "--industry",
        args.industry,
        "--report",
        str(selected.parent / f"{selected.stem}_selection_report.md"),
        # 成交持仓比计算需要读数据 sheets（成交量/持仓量）：
        # 从完整文件（step1）以 read_only 读取，写入仍在精简文件
        "--data-file",
        str(step1),
    ]
    run_cmd(selection_cmd, dry_run=args.dry_run, label="5. Industry-specific selection")
    if run_dir is not None:
        save_stage_snapshot(
            run_dir,
            stage="INDUSTRY_SELECTION",
            source_path=selected,
            operation="apply_industry_selection",
            input_stage="CLASSIFICATION_CHECK",
            script_or_operation=SELECTION_SCRIPT.name,
        )
    ai_input = selected

    if args.ai:
        os.environ["STAGE"] = "ai_disambiguation"
        ai_cmd = [
            str(PYTHON),
            str(AI_SCRIPT),
            "--input",
            str(ai_input),
            "--industry",
            args.industry,
            "--provider",
            "deepseek",
            "--batch-size",
            str(args.ai_batch_size),
            "--max-concurrency",
            str(args.ai_max_concurrency),
            "--max-tokens",
            str(args.ai_max_tokens),
            "--timeout",
            str(args.ai_timeout),
            "--max-retries",
            str(args.ai_max_retries),
            "--output",
            str(ai_slim),
            "--report",
            str(ai_slim.parent / f"{ai_slim.stem}_ai_report.md"),
        ]
        if args.ai_database:
            ai_cmd += ["--database", str(Path(args.ai_database).resolve())]
        run_cmd(ai_cmd, dry_run=args.dry_run, label="6. AI-assisted curation")
        if run_dir is not None:
            save_stage_snapshot(
                run_dir,
                stage="AI_CURATION",
                source_path=ai_slim,
                operation="ai_assisted_curation",
                input_stage="INDUSTRY_SELECTION",
                script_or_operation=AI_SCRIPT.name,
            )
        post_sel_cmd = [
            str(PYTHON),
            str(SELECTION_SCRIPT),
            "--input",
            str(ai_slim),
            "--output",
            str(post_sel),
            "--industry",
            args.industry,
            "--report",
            str(post_sel.parent / f"{post_sel.stem}_report.md"),
            "--data-file",
            str(step1),
        ]
        run_cmd(post_sel_cmd, dry_run=args.dry_run, label="7. Post-AI selection re-evaluation")
        if run_dir is not None:
            save_stage_snapshot(
                run_dir,
                stage="FINAL_SELECTION",
                source_path=post_sel,
                operation="post_ai_selection",
                input_stage="AI_CURATION",
                script_or_operation=SELECTION_SCRIPT.name,
            )
        final_slim = post_sel
    else:
        final_slim = selected

    # 最终排序只在精简文件上跑一次（selection 追加成交持仓比行之后），
    # 结果与原流程（workflow 内 + 末尾各排一次）等价
    sort_cmd = [
        str(PYTHON),
        str(SORT_SCRIPT),
        "--input",
        str(final_slim),
        "--output",
        str(final_slim),
        "--add-normalized-column",
        "--add-sort-reason-column",
    ]
    run_cmd(sort_cmd, dry_run=args.dry_run, label="Final Skill4 dashboard sort (slim)")

    # 合并回完整文件（模板 = <基础名>__full_template.xlsx，extract 时保存的 step1 副本）
    merge_cmd = [
        str(PYTHON),
        str(CATALOG_TOOL),
        "merge",
        str(final_slim),
        str(output_path),
    ]
    run_cmd(merge_cmd, dry_run=args.dry_run, label="Merge catalog sheet into full workbook")

    if run_dir is not None:
        save_stage_snapshot(
            run_dir,
            stage="FINAL_DASHBOARD_SORT",
            source_path=output_path,
            operation="dashboard_data_sorter",
            input_stage="FINAL_SELECTION" if args.ai else "INDUSTRY_SELECTION",
            script_or_operation=SORT_SCRIPT.name,
        )
        save_stage_snapshot(
            run_dir,
            stage="FINAL_OUTPUT",
            source_path=output_path,
            operation="final_output_copy",
            input_stage="FINAL_DASHBOARD_SORT",
            script_or_operation="run_industry_pipeline",
        )
        save_immutable_final(
            run_dir,
            output_path,
            artifact_name="final_output.xlsx",
            workflow_run_id=run_dir.name,
        )
        if not args.skip_audit:
            audit = run_shadow_audit(
                run_dir=run_dir,
                raw_file=input_path,
                final_output=output_path,
            )
            print("WORKFLOW: SUCCESS")
            print(f"AUDIT: {audit.get('audit_status', 'UNKNOWN')}")
            print(f"Confirmed errors: {audit.get('confirmed_errors', 0)}")
            print(f"Review required: {audit.get('review_required', 0)}")
            print(f"Ambiguous: {audit.get('ambiguous', 0)}")
            print(f"Audit report: {run_dir / 'audit' / 'audit_report.json'}")
        else:
            print("WORKFLOW: SUCCESS")
            print("AUDIT: SKIPPED_BY_WORKFLOW")

        # Phase 2c：自动 Evaluation 闭环（best-effort，失败不影响 workflow）。
        # 开关：--langfuse-evaluation 或 LANGFUSE_EVALUATION_ENABLED=true；
        # 独立于 tracing（LANGFUSE_ENABLED），可单独关闭。
        if evaluation_enabled(args.langfuse_evaluation):
            try:
                from evaluation_backfill import run_auto_evaluation

                print("EVALUATION: auto (correlation + scores)")
                eval_result = run_auto_evaluation(run_dir=run_dir, write_scores=True)
                scores = eval_result.get("scores") or {}
                print(
                    "EVALUATION: correlation=%s scores_written=%s scores_skipped=%s"
                    % (
                        eval_result.get("correlation", {}).get("trace_status", "?"),
                        scores.get("written_count", 0),
                        scores.get("skipped_count", 0),
                    )
                )
                if scores.get("skip_reasons"):
                    print("EVALUATION: skip reasons %s" % scores["skip_reasons"])
            except Exception as exc:  # noqa: BLE001 —— best-effort，绝不阻断业务
                print(f"EVALUATION: skipped (error): {exc}")

    if not args.dry_run and not args.keep_intermediates:
        intermediate_paths = [
            step1,
            slim,
            ai_slim,
            calibrated,
            verified,
            checked,
            selected,
            output_path.parent / f"{stem}__full_template.xlsx",
            calibrated.parent / f"{calibrated.stem}_report.md",
            verified.parent / f"{verified.stem}_report.md",
            checked.parent / f"{checked.stem}_report.md",
            selected.parent / f"{selected.stem}_selection_report.md",
        ]
        if args.ai:
            intermediate_paths.append(post_sel)
            intermediate_paths.append(post_sel.parent / f"{post_sel.stem}_report.md")
        print("Cleaning intermediate files...")
        cleanup_paths(intermediate_paths)

    print(f"\nFinal output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
