from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_variable_curation.rule_workflow.models import (
    CompiledRuleSetOutput,
    RuleConflictReport,
    RuleParseResult,
    RuleSetDocument,
    RuleSourceMetadata,
    RuleSummary,
    RuleValidationReport,
)


class RuleArtifactWriter:
    def __init__(self, artifacts_dir: str | Path, run_id: str) -> None:
        self.run_dir = Path(artifacts_dir) / run_id
        self.rules_dir = self.run_dir / "rules"
        self.rules_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.rules_dir / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_source_metadata(self, metadata: RuleSourceMetadata) -> Path:
        return self.write_json("rule_source_metadata.json", metadata.model_dump(mode="json"))

    def write_parser_request(self, request: dict[str, Any]) -> Path:
        return self.write_json("rule_parser_request.json", request)

    def write_parser_response(self, response: RuleParseResult) -> Path:
        return self.write_json("rule_parser_response.json", response.model_dump(mode="json"))

    def write_document(self, name: str, document: RuleSetDocument) -> Path:
        return self.write_json(name, document.model_dump(mode="json"))

    def write_validation(self, validation: RuleValidationReport) -> Path:
        return self.write_json("rule_validation_report.json", validation.model_dump(mode="json"))

    def write_conflicts(self, conflicts: RuleConflictReport) -> Path:
        return self.write_json("rule_conflicts.json", conflicts.model_dump(mode="json"))

    def write_compiled(self, compiled: CompiledRuleSetOutput) -> Path:
        return self.write_json("compiled_rules.json", compiled.model_dump(mode="json"))

    def write_summary(self, summary: RuleSummary) -> Path:
        return self.write_json("rule_summary.json", summary.model_dump(mode="json"))
