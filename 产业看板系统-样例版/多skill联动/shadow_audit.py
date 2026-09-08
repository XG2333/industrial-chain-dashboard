"""Shadow execution of Result_audit after a Producer run.

The audit is best-effort only: audit failures are recorded but never block the
Producer workflow or its publish/copy steps.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RESULT_AUDIT_PYTHON = Path(
    os.getenv(
        "RESULT_AUDIT_PYTHON",
        r"C:\Users\11\Documents\ChatGPT\审查skill数据项目\Result_audit\.venv\Scripts\python.exe",
    )
)


def detect_result_audit_python() -> Path | None:
    if RESULT_AUDIT_PYTHON.exists():
        return RESULT_AUDIT_PYTHON
    return None


def run_shadow_audit(
    *,
    run_dir: str | Path,
    raw_file: str | Path,
    final_output: str | Path,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    audit_dir = run_path / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    python = detect_result_audit_python()
    started_at = datetime.now(timezone.utc).isoformat()
    execution: dict[str, Any] = {
        "mode": "shadow",
        "status": "FAILED",
        "started_at": started_at,
        "python": str(python) if python else None,
        "commands": [],
        "returncode": None,
        "error": None,
    }
    if python is None:
        execution["error"] = "AUDIT_INTERPRETER_NOT_FOUND"
        execution["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_execution(audit_dir, execution)
        return _write_failed_summary(run_path, audit_dir, execution)

    manifest_path = audit_dir / "audit_manifest.json"
    build_cmd = [
        str(python),
        "-m",
        "result_audit",
        "build-manifest",
        "--run-dir",
        str(run_path),
        "--raw-file",
        str(raw_file),
        "--final-output",
        str(final_output),
        "--output",
        str(manifest_path),
    ]
    audit_cmd = [
        str(python),
        "-m",
        "result_audit",
        "audit",
        "--manifest",
        str(manifest_path),
        "--output",
        str(audit_dir),
    ]
    execution["commands"] = [build_cmd, audit_cmd]
    try:
        for cmd in (build_cmd, audit_cmd):
            proc = subprocess.run(
                cmd,
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            execution["returncode"] = proc.returncode
            if proc.returncode != 0:
                execution["error"] = (proc.stderr or proc.stdout or "AUDIT_COMMAND_FAILED")[-2000:]
                break
        report_path = audit_dir / "audit_report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            execution["status"] = "COMPLETED"
            execution["completed_at"] = datetime.now(timezone.utc).isoformat()
            audit_summary = {
                "workflow_run_id": run_path.name,
                "audit_status": "COMPLETED",
                "confirmed_errors": summary.get("errors", 0),
                "review_required": summary.get("review_required", 0),
                "ambiguous": summary.get("ambiguous", 0),
                "expected_transformations": summary.get("pass_count", 0),
                "top_findings": [
                    {
                        "issue_type": item.get("issue_type"),
                        "verdict": item.get("verdict"),
                        "original_name": item.get("original_name"),
                    }
                    for item in report.get("findings", [])[:5]
                ],
                "audit_completed_at": datetime.now(timezone.utc).isoformat(),
                "audit_report_path": str(report_path),
            }
            (audit_dir / "audit_summary.json").write_text(
                json.dumps(audit_summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            _update_workflow_summary(run_path, audit_summary)
            _write_execution(audit_dir, execution)
            return audit_summary
        else:
            execution["status"] = "AUDIT_EXECUTION_FAILED"
            execution["error"] = execution["error"] or "audit_report.json missing"
    except Exception as exc:
        execution["status"] = "AUDIT_EXECUTION_FAILED"
        execution["error"] = f"{type(exc).__name__}: {exc}"
    execution["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write_execution(audit_dir, execution)
    return _write_failed_summary(run_path, audit_dir, execution)


def _write_execution(audit_dir: Path, execution: dict[str, Any]) -> None:
    (audit_dir / "audit_execution.json").write_text(
        json.dumps(execution, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_failed_summary(
    run_path: Path,
    audit_dir: Path,
    execution: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "workflow_run_id": run_path.name,
        "audit_status": "AUDIT_EXECUTION_FAILED",
        "confirmed_errors": 0,
        "review_required": 0,
        "ambiguous": 0,
        "expected_transformations": 0,
        "top_findings": [],
        "audit_completed_at": execution.get("completed_at") or datetime.now(timezone.utc).isoformat(),
        "audit_report_path": None,
        "error": execution.get("error"),
    }
    (audit_dir / "audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _update_workflow_summary(run_path, summary)
    return summary


def _update_workflow_summary(run_path: Path, audit_summary: dict[str, Any]) -> None:
    summary_path = run_path / "workflow_summary.json"
    if not summary_path.exists():
        return
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["audit"] = {
        "mode": "shadow",
        "status": audit_summary.get("audit_status"),
        "report": audit_summary.get("audit_report_path"),
        "confirmed_errors": audit_summary.get("confirmed_errors", 0),
        "review_required": audit_summary.get("review_required", 0),
        "ambiguous": audit_summary.get("ambiguous", 0),
    }
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
