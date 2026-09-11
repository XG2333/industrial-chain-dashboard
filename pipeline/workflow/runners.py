from __future__ import annotations

import hashlib
import importlib.util
import inspect
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from workflow.config import StepConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]

STOCK_TARGET_LABELS = {
    "lithium": "锂电",
    "tin": "锡",
    "silicon": "硅",
}


class WorkflowStepError(Exception):
    pass


@dataclass
class WorkflowContext:
    project_root: Path
    python: Path
    provider: str
    rules: Path | None
    model: str | None = None


@dataclass
class StepResult:
    output: Path
    metadata: dict[str, Any] = field(default_factory=dict)


def _resolve(value: str | Path, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _dir_fingerprint(root: Path) -> str:
    """目录下所有 .py 文件的 (相对路径, mtime, size) 指纹，用于外部代码版本检测。"""
    h = hashlib.md5()
    files = sorted(root.rglob("*.py"))
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        h.update(f"{f.relative_to(root)}|{st.st_mtime_ns}|{st.st_size}|".encode("utf-8"))
    return h.hexdigest()


def _workbook_semantic_fingerprint(path: Path) -> str:
    """Excel 内容语义指纹：sheet 名列表 + 目录表全部单元格 + 文件 mtime/size。

    Skill1 每次重新生成的 cataloged 字节不同（openpyxl zip 元数据），但
    语义内容完全一致——缓存键必须用语义指纹，否则缓存永不命中。

    补充：目录结构相同的不同数据文件（如"真实源"与"结构一致的样例源"）
    若只取目录会指纹碰撞 → 缓存误用对方结果（样例演示会复用真实数据缓存，
    真实流程也会复用样例缓存）。文件 mtime_ns + size 使不同文件/更新后的
    文件天然区分，缓存各自独立。
    """
    from openpyxl import load_workbook

    h = hashlib.md5()
    try:
        st = path.stat()
        h.update(f"{st.st_mtime_ns}:{st.st_size}|".encode("utf-8"))
        wb = load_workbook(path, read_only=True, data_only=False)
        h.update("|".join(wb.sheetnames).encode("utf-8"))
        ws = wb.worksheets[0]
        for row in ws.iter_rows():
            for cell in row:
                h.update(str(cell.value or "").encode("utf-8", errors="replace"))
                h.update(b"|")
        wb.close()
    except Exception:
        return ""
    return h.hexdigest()


def _skill2_cache_key(input_path: Path, rules: Path) -> str:
    """Skill2 结果缓存键：输入文件语义指纹 + 规则文件内容 + 外部 Skill2 代码指纹。"""
    h = hashlib.md5()
    h.update(_workbook_semantic_fingerprint(input_path).encode("utf-8"))
    if rules.exists():
        h.update(b"|rules|")
        h.update(rules.read_bytes())
    # 外部 financial_variable_curation 包代码指纹（从 rules 路径推导外部项目根）
    ext_pkg = rules.resolve().parents[1] / "src" / "financial_variable_curation"
    if ext_pkg.exists():
        h.update(b"|ext|" + _dir_fingerprint(ext_pkg).encode("utf-8"))
    return h.hexdigest()


def _load_module(relative_path: str, module_name: str, project_root: Path):
    path = project_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise WorkflowStepError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_indicator_tags(
    ctx: WorkflowContext,
    output_path: Path,
    run_dir: Path,
) -> dict:
    tag_script = Path(__file__).resolve().parents[1] / "scripts" / "apply_indicator_tags.py"
    if not tag_script.exists():
        raise WorkflowStepError(f"Indicator tags script not found: {tag_script}")
    cmd = [
        str(ctx.python),
        str(tag_script),
        str(output_path),
        "--report",
        str(run_dir / "indicator_tag_report.md"),
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        env=env,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        raise WorkflowStepError(
            f"Indicator tags step failed with exit {proc.returncode}\n{detail[-4000:]}"
        )
    return {
        "indicator_tags": "applied",
        "stdout_tail": (proc.stdout or "")[-2000:],
    }


def _excel_catalog_curator(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    script = _resolve(step.params.get("script", ""), ctx.project_root)
    if not script.exists():
        raise WorkflowStepError(f"Skill1 script not found: {script}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        os.chmod(output_path, stat.S_IWRITE)
        output_path.unlink()
    shutil.copy2(input_path, output_path)
    os.chmod(output_path, stat.S_IWRITE)

    spec = importlib.util.spec_from_file_location("excel_catalog_curator_script", script)
    if spec is None or spec.loader is None:
        raise WorkflowStepError(f"Cannot load Skill1 script: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    catalog_result = module.build_catalog(output_path)
    sheets, indicators = catalog_result[0], catalog_result[1]
    catalog = catalog_result[2] if len(catalog_result) > 2 else None
    pickle_name = str(step.params.get("pickle_name", "dataset.pkl"))
    pickle_path = output_path.parent / pickle_name
    # 兼容旧签名（无 catalog 参数的外部脚本）与新的复用签名
    if catalog is not None and "catalog" in inspect.signature(module.build_tin_pickle).parameters:
        pickle_records = module.build_tin_pickle(output_path, pickle_path, catalog=catalog)
    else:
        pickle_records = module.build_tin_pickle(output_path, pickle_path)
    return StepResult(
        output=output_path,
        metadata={
            "sheets": sheets,
            "indicators": indicators,
            "pickle_records": pickle_records,
            "pickle": str(pickle_path),
        },
    )


def _financial_variable_directory_mark(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rules = ctx.rules or _resolve(step.params.get("rules", ""), ctx.project_root)
    if not rules.exists():
        raise WorkflowStepError(f"Selection rules file not found: {rules}")

    # Skill2 整体结果缓存：输入（cataloged）与规则文件内容相同、外部代码未变时
    # 复用上次输出（Skill2 已验证确定性：同输入两次运行 0 差异），
    # 跳过整个筛选子进程（省 ~90s）。force_refresh 时绕过缓存。
    database = _resolve(step.params.get("database_name", "curation.db"), run_dir)
    artifacts_dir = _resolve(step.params.get("artifacts_dir", "skill2_artifacts"), run_dir)
    cache_dir = run_dir.parent / "_skill2_cache"
    use_cache = not step.params.get("force_refresh")
    cache_key = None
    if use_cache:
        cache_key = _skill2_cache_key(input_path, rules)
        cached = cache_dir / f"{cache_key}.xlsx"
        if cached.exists():
            shutil.copy2(cached, output_path)
            # 恢复 curation.db 与 skill2_artifacts：影子审计（Result_audit）
            # 需要它们发现 source_run_id / selection_run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            cached_db = cache_dir / f"{cache_key}.db"
            if cached_db.exists():
                shutil.copy2(cached_db, database)
            cached_artifacts = cache_dir / f"{cache_key}_artifacts"
            if cached_artifacts.exists() and not artifacts_dir.exists():
                shutil.copytree(cached_artifacts, artifacts_dir)
            return StepResult(
                output=output_path,
                metadata={
                    "cache_hit": True,
                    "cache_key": cache_key,
                    "source": str(cached),
                    "indicator_tags": "deferred_to_merged_stage",
                },
            )
    artifacts_dir = _resolve(step.params.get("artifacts_dir", "skill2_artifacts"), run_dir)
    cmd = [
        str(ctx.python),
        "-m",
        "financial_variable_curation",
        "directory-mark",
        "--input",
        str(input_path),
        "--rules",
        str(rules),
        "--provider",
        ctx.provider,
        "--database",
        str(database),
        "--artifacts-dir",
        str(artifacts_dir),
        "--output",
        str(output_path),
        "--overwrite",
    ]
    if ctx.model:
        cmd += ["--model", ctx.model]
    if step.params.get("force_refresh"):
        cmd.append("--force-refresh")
    if step.params.get("limit") is not None:
        cmd += ["--limit", str(step.params["limit"])]

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    timeout_ms = int(step.params.get("timeout_ms", 1_800_000))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ctx.project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_ms / 1000,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkflowStepError(f"Step {step.id} timed out after {timeout_ms}ms") from exc
    if proc.returncode != 0:
        detail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        raise WorkflowStepError(f"Step {step.id} failed with exit {proc.returncode}\n{detail[-4000:]}")
    # 指标标签不再在此独立重跑：合并链步骤（workflow_merged_stage.py）内的
    # apply_indicator_tags_on_workbook 会无条件重算全部行（含净出口追加行），
    # 输出与此前的独立 tags 子进程一致，省一次完整文件 load/save。
    if use_cache and cache_key:
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, cache_dir / f"{cache_key}.xlsx")
        # 同步缓存 curation.db 与 skill2_artifacts（影子审计依赖）
        if database.exists():
            shutil.copy2(database, cache_dir / f"{cache_key}.db")
        cached_artifacts = cache_dir / f"{cache_key}_artifacts"
        if artifacts_dir.exists() and not cached_artifacts.exists():
            shutil.copytree(artifacts_dir, cached_artifacts)
    return StepResult(
        output=output_path,
        metadata={
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
            "database": str(database),
            "indicator_tags": "deferred_to_merged_stage",
            "cache_written": bool(cache_key),
        },
    )


def _net_export_calculator(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    module = _load_module("scripts/calculate_net_exports.py", "calculate_net_exports", ctx.project_root)
    module.calculate_net_exports(input_path)
    tag_metadata = _apply_indicator_tags(ctx, input_path, run_dir)
    return StepResult(
        output=input_path,
        metadata={"in_place": True, **tag_metadata},
    )


def _tin_selection_rules(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    module = _load_module("scripts/apply_selection_rules.py", "apply_selection_rules", ctx.project_root)
    module.apply_selection(input_path)
    return StepResult(output=input_path, metadata={"in_place": True})


def _reclassify_directory(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    module = _load_module(
        "scripts/reclassify_output_processed_final.py",
        "reclassify_output_processed_final",
        ctx.project_root,
    )
    database = _resolve(step.params.get("database", "curation.db"), run_dir)
    module.reclassify(input_path, db_path=database)
    return StepResult(output=input_path, metadata={"in_place": True})


def _copy_file(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    target = _resolve(step.params.get("target", output_path), ctx.project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, target)
    return StepResult(output=target, metadata={"target": str(target)})


def _command_runner(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    raw_command = step.params.get("command", [])
    replacements = {
        "{input}": str(input_path),
        "{output}": str(output_path),
        "{run_dir}": str(run_dir),
        "{project_root}": str(ctx.project_root),
    }
    cmd = []
    for item in raw_command:
        text = str(item)
        for key, value in replacements.items():
            text = text.replace(key, value)
        cmd.append(text)
    if not cmd:
        raise WorkflowStepError(f"Step {step.id} has no command to run.")
    timeout_ms = int(step.params.get("timeout_ms", 600_000))
    proc = subprocess.run(
        cmd,
        cwd=str(ctx.project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_ms / 1000,
    )
    if proc.returncode != 0:
        raise WorkflowStepError(f"Step {step.id} failed with exit {proc.returncode}\n{(proc.stderr or '')[-2000:]}")
    return StepResult(output=output_path, metadata={"returncode": proc.returncode})


def _stock_target_curator(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    industry = str(step.params.get("industry") or "").strip()
    if industry not in STOCK_TARGET_LABELS:
        raise WorkflowStepError(f"Step {step.id} requires a valid industry, got {industry!r}")
    # provider=deepseek 时走 AI 筛选（附 AI 筛选原因）；否则输出候选池
    provider = str(step.params.get("provider") or "mock").strip()
    script_name = "ai_stock_targets.py" if provider == "deepseek" else "generate_stock_targets.py"
    script = PROJECT_ROOT / "skills" / "stock-target-curator" / "scripts" / script_name
    if not script.exists():
        raise WorkflowStepError(f"Skill3 script not found: {script}")
    default_target = PROJECT_ROOT / "output" / f"个股标的_{STOCK_TARGET_LABELS[industry]}.xlsx"
    target = _resolve(step.params.get("output_path", default_target), PROJECT_ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(ctx.python),
        str(script),
        "--industry",
        industry,
        "--output",
        str(target),
    ]
    if provider == "deepseek":
        cmd += ["--provider", "deepseek"]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["STAGE"] = "stock_targets"
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env=env,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        raise WorkflowStepError(
            f"Step {step.id} failed with exit {proc.returncode}\n{detail[-4000:]}"
        )
    return StepResult(
        output=input_path,
        metadata={
            "in_place": True,
            "stock_targets": str(target),
            "returncode": proc.returncode,
        },
    )


def _dashboard_data_sorter(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    script = PROJECT_ROOT / "skills" / "dashboard-data-sorter" / "scripts" / "sort_catalog.py"
    if not script.exists():
        raise WorkflowStepError(f"Skill4 script not found: {script}")
    cmd = [
        str(ctx.python),
        str(script),
        "--input",
        str(input_path),
        "--output",
        str(input_path),
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    timeout_ms = int(step.params.get("timeout_ms", 1_800_000))
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_ms / 1000,
        env=env,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        raise WorkflowStepError(
            f"Step {step.id} failed with exit {proc.returncode}\n{detail[-4000:]}"
        )
    return StepResult(
        output=input_path,
        metadata={
            "in_place": True,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
        },
    )


def _composite_metric_stage(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    script = PROJECT_ROOT / "scripts" / "composite_metric_stage.py"
    if not script.exists():
        raise WorkflowStepError(f"Composite Metric Stage script not found: {script}")
    report = run_dir / "composite_metric_report.json"
    cmd = [
        str(ctx.python),
        str(script),
        "--input",
        str(input_path),
        "--output",
        str(input_path),
        "--report",
        str(report),
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    timeout_ms = int(step.params.get("timeout_ms", 1_800_000))
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_ms / 1000,
        env=env,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or "") + "\n" + (proc.stderr or "")
        raise WorkflowStepError(
            f"Step {step.id} failed with exit {proc.returncode}\n{detail[-4000:]}"
        )
    return StepResult(
        output=input_path,
        metadata={
            "in_place": True,
            "report": str(report),
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-4000:],
        },
    )


RUNNERS: dict[str, Callable[..., StepResult]] = {
    "excel_catalog_curator": _excel_catalog_curator,
    "financial_variable_directory_mark": _financial_variable_directory_mark,
    "net_export_calculator": _net_export_calculator,
    "tin_selection_rules": _tin_selection_rules,
    "reclassify_directory": _reclassify_directory,
    "copy_file": _copy_file,
    "command": _command_runner,
    "stock_target_curator": _stock_target_curator,
    "dashboard_data_sorter": _dashboard_data_sorter,
    "composite_metric_stage": _composite_metric_stage,
}


def run_step(
    step: StepConfig,
    input_path: Path,
    output_path: Path,
    run_dir: Path,
    ctx: WorkflowContext,
) -> StepResult:
    runner = RUNNERS.get(step.runner)
    if runner is None:
        raise WorkflowStepError(
            f"Unknown runner '{step.runner}' for step '{step.id}'. "
            f"Available runners: {', '.join(sorted(RUNNERS))}"
        )
    return runner(step, input_path, output_path, run_dir, ctx)
