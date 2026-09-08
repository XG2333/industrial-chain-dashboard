# -*- coding: utf-8 -*-
"""临时：模拟 workflow step3 (calculate_net_exports) 定位 FileNotFoundError"""
import glob
import os
import sys
import traceback
from pathlib import Path

DEPLOY = Path(r"C:\Users\11\Documents\产业看板系统")
sys.path.insert(0, str(DEPLOY / "多skill联动"))
sys.path.insert(0, str(DEPLOY / "Selecting skill" / "src"))

from workflow.runners import _load_module  # noqa: E402

PROJECT = DEPLOY / "多skill联动"

# 找最近的 run_dir step2 输出
runs = sorted((PROJECT / "workflow_runs").glob("20*"), key=lambda p: p.name, reverse=True)
run_dir = runs[0]
step2 = run_dir / "02_financial_variable_curation" / "directory_marked.xlsx"
print("step2 exists:", step2.exists(), "|", step2)
print("step3 script via 多skill联动:", (PROJECT / "scripts" / "calculate_net_exports.py").exists())
print("step3 script via Selecting:", (DEPLOY / "Selecting skill" / "scripts" / "calculate_net_exports.py").exists())

try:
    print("--- load module (project_root=多skill联动) ---")
    m = _load_module("scripts/calculate_net_exports.py", "calculate_net_exports", PROJECT)
    print("loaded OK")
    print("--- run calculate_net_exports ---")
    m.calculate_net_exports(step2)
    print("calculate_net_exports OK")
except Exception:
    traceback.print_exc()
