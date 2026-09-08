from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_variable_curation.rule_workflow.models import CompiledRuleSetOutput
from financial_variable_curation.selection.models import (
    CandidateVariable,
    SelectionDecision,
    SelectionExecutionResult,
    SelectionSummary,
    StageSummary,
)


class SelectionArtifactWriter:
    def __init__(self, artifacts_dir: str | Path, selection_run_id: str) -> None:
        self.selection_dir = Path(artifacts_dir) / selection_run_id / "selection"
        self.selection_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.selection_dir / name
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def write_request(self, request: dict[str, Any]) -> Path:
        return self.write_json("selection_request.json", request)

    def write_candidates(self, candidates: list[CandidateVariable]) -> Path:
        return self.write_json(
            "candidate_variables.json",
            [candidate.model_dump(mode="json") for candidate in candidates],
        )

    def write_compiled_plan(self, compiled: CompiledRuleSetOutput) -> Path:
        return self.write_json("compiled_execution_plan.json", compiled.model_dump(mode="json"))

    def write_stage_summaries(self, summaries: list[StageSummary]) -> Path:
        return self.write_json(
            "stage_summaries.json", [summary.model_dump(mode="json") for summary in summaries]
        )

    def write_traces(self, decisions: list[SelectionDecision]) -> Path:
        path = self.selection_dir / "variable_execution_traces.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for decision in decisions:
                handle.write(
                    json.dumps(
                        {
                            "variable_id": decision.variable_id,
                            "trace": [event.model_dump(mode="json") for event in decision.execution_trace],
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
        return path

    def write_results(self, decisions: list[SelectionDecision]) -> Path:
        return self.write_json(
            "selection_results.json", [decision.model_dump(mode="json") for decision in decisions]
        )

    def write_summary(self, summary: SelectionSummary) -> Path:
        return self.write_json("selection_summary.json", summary.model_dump(mode="json"))

    def write_log(self, text: str) -> Path:
        path = self.selection_dir / "selection.log"
        path.write_text(text, encoding="utf-8")
        return path
