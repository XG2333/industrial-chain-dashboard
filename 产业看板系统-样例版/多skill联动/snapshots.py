"""Minimal immutable snapshot and provenance helpers for workflow runs.

This module only copies artifacts and writes neutral JSON provenance. It never
executes or imports business classification/selection logic.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGE_INDEX = {
    "RAW": 0,
    "CATALOG": 1,
    "DIRECTORY_MARK": 2,
    "INDUSTRY_CURATION": 3,
    "FREQUENCY_VERIFY": 4,
    "CLASSIFICATION_CHECK": 5,
    "INDUSTRY_SELECTION": 6,
    "AI_CURATION": 7,
    "FINAL_SELECTION": 8,
    "FINAL_OUTPUT": 9,
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_stage_snapshot(
    run_dir: str | Path,
    *,
    stage: str,
    source_path: str | Path,
    operation: str,
    input_stage: str | None = None,
    script_or_operation: str | None = None,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    snap_dir = run_path / "stage_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Cannot snapshot missing artifact: {source}")
    index = STAGE_INDEX.get(stage, 99)
    safe_operation = operation.strip().replace(" ", "_").replace("/", "_")
    dest = snap_dir / f"{index:02d}_{stage.lower()}__{safe_operation}.xlsx"
    if dest.exists():
        raise FileExistsError(f"Snapshot already exists and must not be overwritten: {dest}")
    shutil.copy2(source, dest)
    record = {
        "stage": stage,
        "artifact": str(dest),
        "sha256": sha256_file(dest),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_stage": input_stage,
        "script_or_operation": script_or_operation or operation,
        "status": "COMPLETED",
    }
    _append_stage_manifest(run_path, record)
    return record


def save_immutable_final(
    run_dir: str | Path,
    source_path: str | Path,
    *,
    artifact_name: str = "final_output.xlsx",
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    final_dir = run_path / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Cannot save immutable final artifact: {source}")
    dest = final_dir / artifact_name
    if dest.exists():
        raise FileExistsError(f"Immutable final artifact already exists: {dest}")
    shutil.copy2(source, dest)
    record = {
        "artifact": str(dest),
        "sha256": sha256_file(dest),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workflow_run_id": workflow_run_id or run_path.name,
        "source_global_output": str(source),
    }
    (final_dir / "final_artifact.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def write_latest_run_pointer(run_root: str | Path, run_dir: str | Path) -> None:
    root = Path(run_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "latest.json"
    payload = {
        "workflow_run_id": Path(run_dir).name,
        "run_dir": str(Path(run_dir)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_stage_manifest(run_path: Path, record: dict[str, Any]) -> None:
    manifest_path = run_path / "stage_manifest.json"
    payload: dict[str, Any] = {"workflow_run_id": run_path.name, "stages": []}
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"workflow_run_id": run_path.name, "stages": []}
    payload.setdefault("stages", [])
    payload["stages"].append(record)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
