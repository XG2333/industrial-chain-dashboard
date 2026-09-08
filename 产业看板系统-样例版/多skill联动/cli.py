from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from workflow.config import StepConfig, WorkflowConfig
from workflow.runners import WorkflowContext, WorkflowStepError, run_step
from workflow.snapshots import save_immutable_final, save_stage_snapshot, write_latest_run_pointer


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _format_plan(config: WorkflowConfig, input_path: Path, run_dir: Path) -> list[dict]:
    plan = []
    current_input = input_path
    for index, step in enumerate(config.steps):
        if not step.enabled:
            continue
        step_dir = run_dir / f"{index + 1:02d}_{step.id}"
        output_name = step.params.get("output_name", f"{step.id}.xlsx")
        output = current_input if step.in_place else step_dir / output_name
        plan.append(
            {
                "id": step.id,
                "name": step.name,
                "runner": step.runner,
                "input": str(current_input),
                "output": str(output),
            }
        )
        current_input = output
    return plan


def run_workflow(
    config: WorkflowConfig,
    input_path: Path,
    *,
    provider: str | None = None,
    rules: Path | None = None,
    model: str | None = None,
    output: Path | None = None,
    run_root: Path | None = None,
    dry_run: bool = False,
) -> dict:
    input_path = input_path.resolve()
    if not input_path.exists():
        raise WorkflowStepError(f"Input file does not exist: {input_path}")
    if provider:
        config.provider = provider
    if rules:
        config.rules = rules.resolve()
    if model:
        config.model = model
    if run_root:
        config.run_root = run_root.resolve()

    enabled_steps = [step for step in config.steps if step.enabled]
    if not enabled_steps:
        raise WorkflowStepError("Workflow config has no enabled steps.")

    run_id = uuid4().hex[:12]
    run_dir = config.run_root / f"{_utc_now()}_{run_id}"
    # 当前 run_id 注入：步骤子进程（command runner 等）继承 env，
    # 供 observability 作为业务 correlation ID（workflow_run_id）。
    # 同时写入 current_run_id.txt（创建时立即写，供 pipeline 外围步骤读取，
    # 不使用 latest.json —— 它可能指向历史 run）。
    os.environ["WORKFLOW_RUN_ID"] = run_id
    try:
        (config.run_root / "current_run_id.txt").write_text(run_id, encoding="utf-8")
    except OSError:
        pass
    plan = _format_plan(config, input_path, run_dir)
    if dry_run:
        return {
            "workflow": config.name,
            "run_id": run_id,
            "status": "DRY_RUN",
            "input": str(input_path),
            "run_dir": str(run_dir),
            "steps": plan,
        }

    run_dir.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []

    def log(line: str) -> None:
        log_lines.append(line)
        print(line)

    ctx = WorkflowContext(
        project_root=config.project_root,
        python=config.python,
        provider=config.provider,
        rules=config.rules,
        model=config.model,
    )
    step_records: list[dict] = []
    current_input = input_path
    last_stage: str | None = None
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        for index, step in enumerate(enabled_steps, 1):
            plan_item = plan[index - 1]
            output_path = Path(plan_item["output"])
            step_started = datetime.now(timezone.utc)
            log(f"[{index}/{len(enabled_steps)}] {step.name} ({step.id})")
            result = run_step(
                step,
                input_path=current_input,
                output_path=output_path,
                run_dir=run_dir,
                ctx=ctx,
            )
            stage = _stage_for_step(step.id)
            if stage:
                save_stage_snapshot(
                    run_dir,
                    stage=stage,
                    source_path=result.output,
                    operation=step.id,
                    input_stage=last_stage,
                    script_or_operation=step.runner,
                )
                last_stage = stage
            elapsed = (datetime.now(timezone.utc) - step_started).total_seconds()
            step_records.append(
                {
                    "id": step.id,
                    "name": step.name,
                    "runner": step.runner,
                    "status": "COMPLETED",
                    "input": str(current_input),
                    "output": str(result.output),
                    "duration_seconds": round(elapsed, 3),
                    "metadata": result.metadata,
                }
            )
            log(f"    -> {result.output}")
            current_input = result.output

        final_artifact = current_input
        if output:
            resolved_output = output.resolve()
        elif config.final_output:
            raw = str(config.final_output)
            raw = raw.replace("<input_stem>", input_path.stem).replace("<run_id>", run_id)
            resolved_output = Path(raw).resolve()
        else:
            resolved_output = run_dir / "final.xlsx"

        if final_artifact.resolve() != resolved_output:
            resolved_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_artifact, resolved_output)
            log(f"[final] copied to {resolved_output}")
        save_immutable_final(
            run_dir,
            resolved_output,
            artifact_name="workflow_final.xlsx",
            workflow_run_id=run_id,
        )
        write_latest_run_pointer(config.run_root, run_dir)

        summary = {
            "workflow": config.name,
            "run_id": run_id,
            "status": "COMPLETED",
            "input_file": str(input_path),
            "final_output": str(resolved_output),
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "provider": config.provider,
            "rules": str(config.rules) if config.rules else None,
            "steps": step_records,
        }
        (run_dir / "workflow_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "workflow.log").write_text("\n".join(log_lines), encoding="utf-8")
        return summary
    except Exception as exc:
        failed = {
            "workflow": config.name,
            "run_id": run_id,
            "status": "FAILED",
            "input_file": str(input_path),
            "started_at": started_at,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "steps": step_records,
        }
        (run_dir / "workflow_summary.json").write_text(
            json.dumps(failed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "workflow.log").write_text("\n".join(log_lines), encoding="utf-8")
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the configured multi-skill Excel workflow.")
    parser.add_argument("--config", default="configs/workflow.yaml")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--provider", choices=["mock", "openai", "deepseek"], default=None)
    parser.add_argument("--rules", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--run-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _stage_for_step(step_id: str) -> str | None:
    mapping = {
        "excel_catalog_curator": "CATALOG",
        "financial_variable_curation": "DIRECTORY_MARK",
        "calculate_net_exports": "INDUSTRY_CURATION",
        "reclassify_silicon": "CLASSIFICATION_CHECK",
        "apply_silicon_selection_rules": "INDUSTRY_SELECTION",
        "check_silicon_output": "CLASSIFICATION_CHECK",
        "generate_stock_targets": "STOCK_TARGETS",
        "dashboard_data_sorter": "DASHBOARD_SORT",
        "composite_metric_stage": "COMPOSITE_METRIC",
    }
    return mapping.get(step_id)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = WorkflowConfig.from_yaml(args.config)
        output = Path(args.output) if args.output else None
        rules = Path(args.rules) if args.rules else None
        run_root = Path(args.run_root) if args.run_root else None
        summary = run_workflow(
            config,
            Path(args.input),
            provider=args.provider,
            rules=rules,
            model=args.model,
            output=output,
            run_root=run_root,
            dry_run=args.dry_run,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (WorkflowStepError, FileNotFoundError, ValueError) as exc:
        import traceback
        traceback.print_exc()
        print(f"Workflow failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
