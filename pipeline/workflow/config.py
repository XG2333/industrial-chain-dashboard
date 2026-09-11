from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class StepConfig:
    id: str
    name: str
    runner: str
    enabled: bool = True
    in_place: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowConfig:
    name: str
    project_root: Path
    python: Path
    provider: str = "mock"
    model: str | None = None
    rules: Path | None = None
    run_root: Path = PROJECT_ROOT / "workflow_runs"
    final_output: Path | None = None
    steps: list[StepConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "WorkflowConfig":
        path = Path(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        wf = raw.get("workflow") or raw
        project_root = Path(wf.get("project_root", PROJECT_ROOT))
        if not project_root.is_absolute():
            project_root = PROJECT_ROOT / project_root
        project_root = project_root.resolve()

        python = Path(wf.get("python", project_root / ".venv" / "Scripts" / "python.exe"))
        if not python.is_absolute():
            python = project_root / python

        rules_raw = wf.get("rules")
        rules = None
        if rules_raw:
            rules = Path(rules_raw)
            if not rules.is_absolute():
                rules = project_root / rules

        run_root = Path(wf.get("run_root", "workflow_runs"))
        if not run_root.is_absolute():
            run_root = project_root / run_root

        final_output_raw = wf.get("final_output")
        final_output = None
        if final_output_raw:
            final_output = Path(final_output_raw)
            if not final_output.is_absolute():
                final_output = project_root / final_output

        steps = [
            StepConfig(
                id=str(item["id"]),
                name=str(item.get("name", item["id"])),
                runner=str(item["runner"]),
                enabled=bool(item.get("enabled", True)),
                in_place=bool(item.get("in_place", False)),
                params=dict(item.get("params", {})),
            )
            for item in wf.get("steps", [])
        ]
        return cls(
            name=str(wf.get("name", path.stem)),
            project_root=project_root,
            python=python.resolve(),
            provider=str(wf.get("provider", "mock")),
            model=wf.get("model"),
            rules=rules,
            run_root=run_root,
            final_output=final_output,
            steps=steps,
        )
