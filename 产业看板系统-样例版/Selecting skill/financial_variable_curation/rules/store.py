from __future__ import annotations

import json
import re
from pathlib import Path

from financial_variable_curation.models.enums import RuleSetStatus, RuleSource
from financial_variable_curation.models.rules import CompiledRuleSet, RuleSet
from financial_variable_curation.utils.hashing import hash_model


def _sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
    return cleaned or "unnamed_rule_set"


def _version_number(path: Path) -> int:
    match = re.search(r"_v(\d+)\.json$", path.name)
    return int(match.group(1)) if match else 0


class RuleStore:
    def __init__(self, base_dir: str | Path = "configs/rules") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_parsed(self, run_id: str, rule_set: RuleSet, artifacts_dir: str | Path = "artifacts") -> Path:
        directory = Path(artifacts_dir) / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "parsed_rules.json"
        path.write_text(rule_set.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_compiled(
        self, run_id: str, compiled: CompiledRuleSet, artifacts_dir: str | Path = "artifacts"
    ) -> Path:
        directory = Path(artifacts_dir) / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "compiled_rules.json"
        path.write_text(compiled.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_versioned(
        self, rule_set: RuleSet, production_ready: bool = False
    ) -> tuple[Path, RuleSet]:
        safe_name = _sanitize_name(rule_set.name)
        existing = sorted(self.base_dir.glob(f"{safe_name}_v*.json"), key=_version_number)
        version_number = _version_number(existing[-1]) + 1 if existing else 1
        version = f"v{version_number}"

        active = rule_set.model_copy(deep=True)
        active.name = safe_name
        active.version = version
        active.source = RuleSource.SAVED_RULE_SET
        active.status = RuleSetStatus.ACTIVE
        active.production_ready = production_ready
        active.rules_hash = hash_model(active)

        path = self.base_dir / f"{safe_name}_{version}.json"
        path.write_text(active.model_dump_json(indent=2), encoding="utf-8")
        return path, active

    def load_rule_set(self, rule_set_name: str) -> tuple[RuleSet, Path]:
        safe_name = _sanitize_name(rule_set_name)
        exact = self.base_dir / f"{safe_name}.json"
        if exact.exists():
            return self._load_path(exact), exact

        candidates = sorted(self.base_dir.glob(f"{safe_name}_v*.json"), key=_version_number)
        if not candidates:
            raise FileNotFoundError(
                f"No saved rule set named '{rule_set_name}' found under {self.base_dir}."
            )
        path = candidates[-1]
        return self._load_path(path), path

    def _load_path(self, path: Path) -> RuleSet:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuleSet.model_validate(payload)
