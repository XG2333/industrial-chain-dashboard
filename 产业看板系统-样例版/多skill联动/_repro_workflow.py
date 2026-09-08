# -*- coding: utf-8 -*-
"""临时：复现 workflow 步骤 3 失败，完整捕获输出"""
import glob
import os
import subprocess
import sys
from pathlib import Path

VENV = Path(r"C:\Users\11\Documents\产业看板系统\.venv\Scripts\python.exe")
PROJECT = Path(r"C:\Users\11\Documents\产业看板系统\多skill联动")
SELECTING = Path(r"C:\Users\11\Documents\产业看板系统\Selecting skill")
cfg_dirs = sorted(glob.glob(os.path.join(os.environ["TEMP"], "wf_cfg_*")), key=os.path.getmtime)
cfg = Path(cfg_dirs[-1]) / "workflow_lithium.yaml"

env = os.environ.copy()
env["PYTHONPATH"] = str(PROJECT) + os.pathsep + str(SELECTING / "src")
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

cmd = [
    str(VENV), "-m", "workflow",
    "--config", str(cfg),
    "--input", str(PROJECT / "input" / "碳酸锂数据库.xlsx"),
    "--output", r"C:\Users\11\AppData\Local\Temp\wf_repro2.xlsx",
    "--provider", "mock",
]
log = Path(os.environ["TEMP"]) / "wf_repro2.log"
print("running:", " ".join(cmd))
proc = subprocess.run(cmd, cwd=str(PROJECT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
log.write_text("STDOUT:\n" + proc.stdout + "\nSTDERR:\n" + proc.stderr, encoding="utf-8")
print("exit:", proc.returncode, "| log:", log)
print("--- STDERR tail ---")
print(proc.stderr[-4000:])
