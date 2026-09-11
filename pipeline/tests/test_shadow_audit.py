from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from workflow import shadow_audit


def test_detect_result_audit_python() -> None:
    python = shadow_audit.detect_result_audit_python()
    assert python is None or python.exists()


def test_audit_execution_failure_does_not_raise(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "workflow_summary.json").write_text(
        json.dumps({"workflow": "tin", "status": "COMPLETED"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(shadow_audit, "RESULT_AUDIT_PYTHON", tmp_path / "missing_python.exe")
    result = shadow_audit.run_shadow_audit(
        run_dir=run_dir,
        raw_file="raw.xlsx",
        final_output="final.xlsx",
    )
    assert result["audit_status"] == "AUDIT_EXECUTION_FAILED"
    assert result["error"] == "AUDIT_INTERPRETER_NOT_FOUND"
    assert (run_dir / "audit" / "audit_summary.json").exists()
    summary = json.loads((run_dir / "workflow_summary.json").read_text(encoding="utf-8"))
    assert summary["audit"]["mode"] == "shadow"
    assert summary["audit"]["status"] == "AUDIT_EXECUTION_FAILED"


def test_audit_success_writes_artifacts_and_does_not_block(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "workflow_summary.json").write_text(
        json.dumps({"workflow": "tin", "status": "COMPLETED"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(shadow_audit, "RESULT_AUDIT_PYTHON", Path(sys.executable))

    def fake_run(cmd, **kwargs):
        audit_dir = run_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "audit_report.json").write_text(
            json.dumps(
                {
                    "summary": {
                        "errors": 2,
                        "review_required": 3,
                        "ambiguous": 4,
                        "pass_count": 5,
                    },
                    "findings": [
                        {
                            "issue_type": "X",
                            "verdict": "ERROR",
                            "original_name": "A",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(shadow_audit.subprocess, "run", fake_run)
    result = shadow_audit.run_shadow_audit(
        run_dir=run_dir,
        raw_file="raw.xlsx",
        final_output="final.xlsx",
    )
    assert result["audit_status"] == "COMPLETED"
    assert result["confirmed_errors"] == 2
    assert (run_dir / "audit" / "audit_summary.json").exists()
    assert (run_dir / "audit" / "audit_execution.json").exists()
    summary = json.loads((run_dir / "workflow_summary.json").read_text(encoding="utf-8"))
    assert summary["audit"]["confirmed_errors"] == 2
    assert summary["audit"]["review_required"] == 3
