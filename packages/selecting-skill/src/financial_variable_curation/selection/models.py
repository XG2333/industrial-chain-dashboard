from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CandidateVariable(BaseModel):
    variable_id: str
    run_id: str
    original_name: str
    standard_name: str = ""
    industry: str | None = None
    sector: str | None = None
    commodity: str | None = None
    category_level_1: str = "UNKNOWN"
    category_level_2: str = "UNCLASSIFIED"
    metric_name: str = ""
    data_nature: str = "UNKNOWN"
    market: str | None = None
    region: str | None = None
    country: str | None = None
    unit_standard: str | None = None
    unit_dimension: str | None = None
    statistical_scope: str | None = None
    comparison_group_key: str | None = None
    classification_confidence: float = 0.0
    classification_status: str = "FAILED"
    detected_frequency: str = "unknown"
    missing_rate: float = 1.0
    non_null_count: int = 0
    unique_value_count: int = 0
    coverage_days: int | None = None
    latest_gap_days: int | None = None
    quality_score: float = 0.0
    is_constant: bool = False
    is_outdated: bool = False
    is_pseudo_high_frequency: bool = False
    source_type: str | None = None
    has_unresolved_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class ExecutionTraceEvent(BaseModel):
    stage: str
    rule_id: str | None = None
    matched: bool | None = None
    assigned_rank: int | None = None
    group_rank: int | None = None
    action: str | None = None
    input_value: Any = None
    output_value: Any = None
    reason: str | None = None


class ScoreComponents(BaseModel):
    category_score: float = 0.0
    frequency_score: float = 0.0
    quality_score: float = 0.0
    source_score: float = 0.0
    recency_score: float = 0.0
    coverage_score: float = 0.0
    user_preference_score: float = 0.0
    redundancy_penalty: float = 0.0

    @property
    def total_score(self) -> float:
        return round(
            self.category_score
            + self.frequency_score
            + self.quality_score
            + self.source_score
            + self.recency_score
            + self.coverage_score
            + self.user_preference_score
            + self.redundancy_penalty,
            4,
        )


class SelectionDecision(BaseModel):
    candidate: CandidateVariable
    status: str = "PROCESSED"
    category_rank: int | None = None
    subcategory_rank: int | None = None
    frequency_rank: int | None = None
    source_rank: int | None = None
    quality_rank: int | None = None
    scores: ScoreComponents = Field(default_factory=ScoreComponents)
    overall_rank: int | None = None
    comparison_group_key: str | None = None
    group_rank: int | None = None
    replacement_variable_id: str | None = None
    primary_reason_code: str | None = None
    primary_reason_text: str | None = None
    matched_rule_ids: list[str] = Field(default_factory=list)
    execution_trace: list[ExecutionTraceEvent] = Field(default_factory=list)

    @property
    def variable_id(self) -> str:
        return self.candidate.variable_id

    @property
    def total_score(self) -> float:
        return self.scores.total_score


class StageSummary(BaseModel):
    stage: str
    status: str
    reason: str | None = None
    executed_rule_count: int = 0
    matched_rule_count: int = 0


class SelectionExecutionResult(BaseModel):
    decisions: list[SelectionDecision] = Field(default_factory=list)
    stage_summaries: list[StageSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SelectionSummary(BaseModel):
    selection_run_id: str
    source_run_id: str
    rule_set_id: str
    rule_set_name: str
    rule_set_version: str
    compiled_hash: str
    total_variables: int = 0
    candidate_variables: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    needs_review_count: int = 0
    not_selected_count: int = 0
    failed_count: int = 0
    selected_by_category: dict[str, int] = Field(default_factory=dict)
    selected_by_frequency: dict[str, int] = Field(default_factory=dict)
    stage_summaries: list[StageSummary] = Field(default_factory=list)
    artifacts_path: str | None = None
    status: str = "COMPLETED"
    generated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    dry_run: bool = False
    warnings: list[str] = Field(default_factory=list)
