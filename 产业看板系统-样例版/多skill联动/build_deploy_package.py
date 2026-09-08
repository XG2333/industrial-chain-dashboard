# -*- coding: utf-8 -*-
"""制作"产业看板系统"部署包：整合 多skill联动 + 本地可视化dashboard，
排除数据/依赖/缓存/产物，生成可复现部署目录与部署说明。"""
import shutil
from pathlib import Path

SRC_SKILL = Path(r"C:\Users\11\Documents\多skill联动")
SRC_DASH = Path(r"C:\Users\11\Documents\本地可视化dashboard")
SRC_SELECTING = Path(r"C:\Users\11\Documents\Selecting skill")
DEST = Path(r"C:\Users\11\Documents\产业看板系统")

# 多skill联动排除项（数据/临时/缓存/运行产物；workflow/ 是 python 源码包，必须保留）
SKILL_EXCLUDE_DIRS = {
    "output", "input", "data_input", "workflow_runs", "migration",
    ".claude", ".pytest_cache", ".tmp_composite", "pytest_tmp_composite", "__pycache__",
    ".git",
}
SKILL_EXCLUDE_DIR_PREFIXES = (".pytest_tmp", "pytest_tmp_", ".pytest_tmp_")
SKILL_EXCLUDE_FILES = {
    ".gitignore", "build_deploy_package.py",
    # git bundle(仓库历史包): 历史中可能含曾提交的数据文件, 不入部署包
    "muti-scale-pipeline.bundle", "muti-skill-pipeline.bundle",
}

# Selecting skill 排除项（Skill1 规则源；排除环境/数据/产物，保留 规则docx/scripts/src/configs）
SELECTING_EXCLUDE_DIRS = {
    ".venv", "data", "artifacts", "artifacts_reuse_ok", "output",
    ".pytest_cache", ".pytest_tmp", ".codex", ".git", "__pycache__",
}
SELECTING_EXCLUDE_DIR_PREFIXES = ()
SELECTING_EXCLUDE_FILES = {
    ".env", "selectingskill.bundle",
    "reuse_test_output2__tmp.xlsx", "reuse_test_output__tmp.xlsx",
}

# dashboard 排除项（数据/依赖/产物/缓存）
DASH_EXCLUDE_DIRS = {
    "data", ".venv", "node_modules", "dist", ".git", ".pytest_tmp", "__pycache__",
    "backup_scheme1",  # 旧版前端整目录备份(源码噪音, 不入包)
}
DASH_EXCLUDE_DIR_PREFIXES = ()
DASH_EXCLUDE_FILES = {
    ".env", "server_stdout.log", "server_stderr.log", "_err.log", "_server_err.log",
    "_srv.log", "锡核心指标.json", "local-dashboard.bundle", "output_processed_final_v4.xlsx",
    "battery-real-canvas.png", "battery-shell-canvas.png", "flowbite-overview-dark.png",
    "flowbite-overview-light.png", "flowbite-overview-mobile.png", "p3-battery-light.png",
    "p3-overview-dark.png", "p3-overview-light.png", "p3-silicon-light.png",
    "p3-tin-dark.png", "p3-tin-light.png", "silicon-canvas.png", "silicon-real-canvas.png",
    "silicon-shell-canvas.png", "tin-canvas.png", "tin-full.png", "tin-real-canvas.png",
    "tin-shell-canvas.png",
}

REQUIREMENTS_EXTRA = [
    "# 产业看板系统合并依赖（dashboard + 多skill联动 + Selecting skill）",
    "pandas",
    "numpy",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
    "requests",
    "curl_cffi",  # server.py 顶层导入（新浪资金流抓取），缺失会导致 uvicorn 启动闪退
    "fastapi",
    "uvicorn",
    "PyYAML",
    "openpyxl",
    "pytest",
    "openai",
    "sqlalchemy",
    "python-docx",  # Selecting skill financial_variable_curation 依赖
    "",
]


# 点/双下划线前缀文件默认排除，但部署模板 .env.example 需要保留
KEEP_DOT_FILES = {".env.example"}


def copy_tree(src: Path, dst: Path, exclude_dirs, exclude_prefixes, exclude_files):
    """递归复制目录，顶层与所有子层级统一排除（node_modules/__pycache__ 等）。"""

    def _ignore(directory: str, names: list[str]) -> list[str]:
        dropped = []
        for n in names:
            full = Path(directory) / n
            if full.is_dir():
                if n in exclude_dirs or n.startswith(exclude_prefixes):
                    dropped.append(n)
            else:
                if n in exclude_files:
                    dropped.append(n)
                # 只排除点文件；__init__.py / __main__.py 等 python 包必需文件必须保留
                # （__pycache__ 目录已由 exclude_dirs 排除，不存在 __ 前缀文件需排除）
                elif n.startswith(".") and n not in KEEP_DOT_FILES:
                    dropped.append(n)
        return dropped

    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore)


def clean_pycache(root: Path):
    for p in root.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def main():
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)

    print("复制 多skill联动 ...")
    copy_tree(SRC_SKILL, DEST / "多skill联动", SKILL_EXCLUDE_DIRS, SKILL_EXCLUDE_DIR_PREFIXES, SKILL_EXCLUDE_FILES)
    # input/ 整体排除(源数据不入包), 但随包附赠"样例源数据"(结构一致/数值随机),
    # 便于新电脑无真实源时也能跑通 Skill1-4 全流程演示
    sample_input = SRC_SKILL / "input" / "样例"
    if sample_input.exists():
        shutil.copytree(sample_input, DEST / "多skill联动" / "input" / "样例", dirs_exist_ok=True)
        print("复制 多skill联动/input/样例(源数据样例)...")
    print("复制 本地可视化dashboard ...")
    copy_tree(SRC_DASH, DEST / "本地可视化dashboard", DASH_EXCLUDE_DIRS, DASH_EXCLUDE_DIR_PREFIXES, DASH_EXCLUDE_FILES)
    print("复制 Selecting skill（Skill1 规则源）...")
    copy_tree(SRC_SELECTING, DEST / "Selecting skill", SELECTING_EXCLUDE_DIRS, SELECTING_EXCLUDE_DIR_PREFIXES, SELECTING_EXCLUDE_FILES)

    print("清理 __pycache__ ...")
    clean_pycache(DEST)

    print("写入合并 requirements.txt ...")
    (DEST / "requirements.txt").write_text("\n".join(REQUIREMENTS_EXTRA), encoding="utf-8")

    print("复制部署说明与一键脚本 ...")
    shutil.copy2(SRC_SKILL / "docs" / "部署说明.md", DEST / "部署说明.md")
    shutil.copy2(SRC_SKILL / "scripts" / "process_all.py", DEST / "process_all.py")
    shutil.copy2(SRC_SKILL / "scripts" / "setup.bat", DEST / "setup.bat")
    shutil.copy2(SRC_SKILL / "scripts" / "run_all.bat", DEST / "run_all.bat")
    shutil.copy2(SRC_SKILL / "scripts" / "configure_env.py", DEST / "configure_env.py")

    print("创建 data 数据目录占位 ...")
    data_dir = DEST / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "数据放置说明.txt").write_text(
        "请将以下数据文件放入本目录与多skill联动/output/ 后运行：\n"
        "1. data/碳酸锂数据库_workflow_ai.xlsx（含二次筛选是否保留列，锂电）\n"
        "2. data/锡产业链数据_workflow_ai.xlsx（含二次筛选是否保留列）\n"
        "3. data/硅产业链数据_workflow_ai.xlsx（含二次筛选是否保留列）\n"
        "4. 多skill联动/output/个股标的_锂电.xlsx、个股标的_锡.xlsx、个股标的_硅.xlsx\n"
        "详见 部署说明.md。\n",
        encoding="utf-8",
    )

    print("打包完成 ->", DEST)
    total = sum(1 for _ in DEST.rglob("*"))
    print("文件/目录数:", total)


if __name__ == "__main__":
    main()
