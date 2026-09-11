# -*- coding: utf-8 -*-
"""产业看板系统一键处理入口：原始产业数据 → 处理数据 + 个股标的 → 看板就绪。

仓库根目录下运行：
    python scripts/process_all.py [--provider mock|deepseek] [--ai]

流程（对 锂电/锡/硅 各行业）：
  1. run_industry_pipeline：Skill1-4 workflow → 校准 → 频率校验 → 分类一致性 → 筛选 → 排序
  2. 二次筛选列生成（锂电专属规则 / 锡硅通用规则）
  3. 个股标的生成（stock-target-curator，纯配置，无需 AI）
  4. 产物写入 data/processed 与 data/stock-targets，并清理运行缓存

原始文件约定（放入 data/raw/ 或 --input-dir 指定）：
  碳酸锂数据库.xlsx   → 锂电
  锡产业链数据.xlsx    → 锡
  硅产业链数据.xlsx    → 硅
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent
PROJECT_ROOT = REPO_ROOT / "pipeline"
DASHBOARD_DIR = REPO_ROOT / "apps" / "dashboard"
SELECTING_SKILL_DIR = REPO_ROOT / "packages" / "selecting-skill"
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DATA_DIR = REPO_ROOT / "data" / "processed"
STOCK_TARGETS_DIR = REPO_ROOT / "data" / "stock-targets"
WORKFLOW_RUNS_DIR = REPO_ROOT / "runtime" / "workflow-runs"
CACHE_DIR = REPO_ROOT / "runtime" / "cache"

WORKFLOW_CONFIGS = {
    "lithium": PROJECT_ROOT / "configs" / "workflow_lithium.yaml",
    "tin": PROJECT_ROOT / "configs" / "workflow_tin.yaml",
    "silicon": PROJECT_ROOT / "configs" / "workflow_silicon.yaml",
}
# 原始输入文件 → (行业, 看板数据文件名)；锡支持两种命名（锡数据库 / 锡产业链数据）
RAW_FILES = {
    "碳酸锂数据库.xlsx": ("lithium", "碳酸锂数据库_workflow_ai.xlsx"),
    "锡数据库.xlsx": ("tin", "锡产业链数据_workflow_ai.xlsx"),
    "锡产业链数据.xlsx": ("tin", "锡产业链数据_workflow_ai.xlsx"),
    "硅产业链数据.xlsx": ("silicon", "硅产业链数据_workflow_ai.xlsx"),
}
STOCK_TARGET_FILES = {
    "lithium": "个股标的_锂电.xlsx",
    "tin": "个股标的_锡.xlsx",
    "silicon": "个股标的_硅.xlsx",
}
GEN_STOCK_SCRIPT = PROJECT_ROOT / "skills" / "stock-target-curator" / "scripts" / "generate_stock_targets.py"
STOCK_CONFIG = PROJECT_ROOT / "skills" / "stock-target-curator" / "config" / "stock_targets.json"
PIPELINE_SCRIPT = PROJECT_ROOT / "scripts" / "run_industry_pipeline.py"
RECOMPUTE_LITHIUM = PROJECT_ROOT / "scripts" / "recompute_secondary_only.py"
RECOMPUTE_TIN_SILICON = PROJECT_ROOT / "scripts" / "recompute_secondary_tin_silicon.py"


def rewrite(obj, replacements: dict[str, str]):
    """递归替换字符串（处理 yaml steps 内嵌 script/command 路径）。"""
    if isinstance(obj, str):
        for old, new in replacements.items():
            obj = obj.replace(old, new)
        return obj
    if isinstance(obj, list):
        return [rewrite(x, replacements) for x in obj]
    if isinstance(obj, dict):
        return {k: rewrite(v, replacements) for k, v in obj.items()}
    return obj


def run(cmd: list[str], label: str) -> None:
    print(f"\n===== {label} =====")
    print("  " + " ".join(str(c) for c in cmd))
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # 部署场景：Selecting skill 未 pip 安装（源仓库靠 .venv），把 src 挂到 PYTHONPATH
    # （runner 以 python -m financial_variable_curation 执行，沿 subprocess 链继承）
    src_dir = SELECTING_SKILL_DIR / "src"
    if src_dir.is_dir():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src_dir) + (os.pathsep + existing if existing else "")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    if proc.returncode != 0:
        raise SystemExit(f"[{label}] failed with exit {proc.returncode}")


def build_workflow_yaml(industry: str, provider: str = "mock") -> Path:
    """读取模板 yaml，把硬编码路径替换为部署包内路径，写出临时 yaml。

    provider 同时覆盖 yaml 内 generate_stock_targets 步骤的 provider（模板
    写死 deepseek，无 key 时个股步骤会失败；随 process_all --provider 走，
    默认 mock=离线候选池输出，无需 API）。
    """
    template = WORKFLOW_CONFIGS[industry]
    raw = json.loads(json.dumps(__import__("yaml").safe_load(template.read_text(encoding="utf-8"))))
    wf = raw.get("workflow") or raw
    wf["project_root"] = str(SELECTING_SKILL_DIR)
    wf["python"] = sys.executable
    wf["rules"] = str(SELECTING_SKILL_DIR / "input" / "selection_rules.docx")
    wf["run_root"] = str(WORKFLOW_RUNS_DIR)
    wf["final_output"] = str(PROCESSED_DATA_DIR / "<input_stem>_workflow.xlsx")
    for step in wf.get("steps", []):
        if step.get("id") == "generate_stock_targets" and "params" in step:
            step["params"]["provider"] = provider
    replaced = rewrite(wf, {
        "{python}": sys.executable,
        "{pipeline_root}": str(PROJECT_ROOT),
        "{selecting_skill_root}": str(SELECTING_SKILL_DIR),
        "{workflow_runs_dir}": str(WORKFLOW_RUNS_DIR),
        "{processed_data_dir}": str(PROCESSED_DATA_DIR),
    })
    tmp = Path(tempfile.mkdtemp(prefix="wf_cfg_")) / template.name
    tmp.write_text(json.dumps({"workflow": replaced}, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp


def process_industry(industry: str, raw_path: Path, final_name: str, provider: str, use_ai: bool) -> None:
    out = PROCESSED_DATA_DIR / final_name
    out.parent.mkdir(parents=True, exist_ok=True)

    cfg_yaml = build_workflow_yaml(industry, provider)
    print(f"\n########## {industry}: {raw_path.name} -> {out.name} ##########")
    pipeline_cmd = [
        sys.executable, str(PIPELINE_SCRIPT),
        "--industry", industry,
        "--input", str(raw_path),
        "--output", str(out),
        "--provider", provider,
        "--config", str(cfg_yaml),
    ]
    if use_ai:
        pipeline_cmd.append("--ai")
    run(pipeline_cmd, f"1. {industry} 全流程管道（Skill1-4 + 校准 + 校验 + 筛选 + 排序）")

    # 二次筛选列
    if industry == "lithium":
        run([sys.executable, str(RECOMPUTE_LITHIUM), str(out), str(out)], "2. 锂电二次筛选列")
    else:
        run([
            sys.executable,
            str(RECOMPUTE_TIN_SILICON),
            "--data-dir",
            str(PROCESSED_DATA_DIR),
        ], f"2. {industry} 二次筛选列（通用规则）")

    # 个股标的
    stock_out = STOCK_TARGETS_DIR / STOCK_TARGET_FILES[industry]
    run([
        sys.executable, str(GEN_STOCK_SCRIPT),
        "--industry", industry,
        "--config", str(STOCK_CONFIG),
        "--output", str(stock_out),
    ], f"3. {industry} 个股标的生成")

    print(f"[{industry}] 完成：{out.name} + {stock_out.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="产业看板系统一键处理：原始数据 -> 看板数据")
    parser.add_argument("--input-dir", default=None, help="原始文件目录（默认 data/raw）")
    parser.add_argument("--provider", choices=["mock", "deepseek", "openai"], default="mock",
                        help="workflow LLM provider（默认 mock=确定性规则，无需 API）")
    parser.add_argument("--ai", action="store_true", help="AI 辅助整理（需 DEEPSEEK_API_KEY）")
    parser.add_argument("--only", choices=["lithium", "tin", "silicon"], default=None,
                        help="只处理指定行业（默认全部）")
    parser.add_argument("--parallel", type=int, default=1,
                        help="并行行业数（默认 1=串行；2/3 并行跑行业，总耗时≈最慢行业）")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir) if args.input_dir else RAW_DATA_DIR
    if not input_dir.exists():
        print(f"输入目录不存在: {input_dir}", file=sys.stderr)
        return 1

    if not SELECTING_SKILL_DIR.exists():
        print(f"缺少 Selecting skill 目录（Skill1 规则依赖）: {SELECTING_SKILL_DIR}", file=sys.stderr)
        return 1

    done_industries: set[str] = set()
    targets: list[tuple[str, Path, str]] = []
    for raw_name, (industry, final_name) in RAW_FILES.items():
        if args.only and args.only != industry:
            continue
        raw = input_dir / raw_name
        if not raw.exists():
            print(f"跳过（原始文件缺失）: {raw}")
            continue
        if industry in done_industries:
            continue  # 同行业多文件名（如锡两种命名）只处理一次
        done_industries.add(industry)
        targets.append((industry, raw, final_name))

    if args.parallel > 1 and len(targets) > 1:
        # 并行：每行业一个独立子进程（日志隔离到文件、失败互不影响）。
        # 行业之间完全独立（输出文件/workflow_runs/个股均独立），并行安全。
        from concurrent.futures import ThreadPoolExecutor, as_completed

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        src_dir = SELECTING_SKILL_DIR / "src"
        if src_dir.is_dir():
            existing = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(src_dir) + (os.pathsep + existing if existing else "")

        def run_one(item: tuple[str, Path, str]) -> tuple[str, int, Path]:
            industry, raw, final_name = item
            cmd = [
                sys.executable, str(Path(__file__).resolve()),
                "--only", industry,
                "--provider", args.provider,
                "--input-dir", str(input_dir),
            ]
            if args.ai:
                cmd.append("--ai")
            log = Path(tempfile.gettempdir()) / f"process_all_{industry}.log"
            with open(log, "w", encoding="utf-8") as f:
                proc = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT)
            return industry, proc.returncode, log

        print(f"并行处理 {len(targets)} 个行业（workers={args.parallel}）...")
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(run_one, t): t[0] for t in targets}
            for fut in as_completed(futures):
                industry, rc, log = fut.result()
                if rc != 0:
                    print(f"[{industry}] 失败（exit {rc}），详细日志: {log}", file=sys.stderr)
                else:
                    print(f"[{industry}] 完成（日志: {log}）")
    else:
        for industry, raw, final_name in targets:
            process_industry(industry, raw, final_name, args.provider, args.ai)

    # 清缓存（后端按 Excel mtime 重建，此处保险清理）
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*"):
            if not f.is_file():
                continue
            f.unlink()
            print(f"清理缓存: {f.name}")

    print("\n========== 全部完成 ==========")
    print(f"看板数据已就位: {PROCESSED_DATA_DIR}")
    print(f"个股标的已就位: {STOCK_TARGETS_DIR}")
    print("下一步：")
    print(f"  1. cd {DASHBOARD_DIR / 'frontend'} && npm install && npm run build")
    print(f"  2. {sys.executable} {REPO_ROOT / 'scripts' / 'configure_env.py'}")
    print(f"  3. {sys.executable} {DASHBOARD_DIR / 'server.py'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
