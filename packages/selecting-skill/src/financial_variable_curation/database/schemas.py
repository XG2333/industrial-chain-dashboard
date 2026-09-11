from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OrmDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PipelineRunDTO(OrmDTO):
    run_id: str
    run_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    current_step: str | None = None
    last_successful_step: str | None = None
    input_request_json: dict[str, Any] | None = None
    artifacts_path: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    is_retriable: bool = False
    created_at: datetime
    updated_at: datetime


class PipelineStepDTO(OrmDTO):
    step_id: str
    run_id: str
    step_name: str
    step_order: int = 0
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    attempt_count: int = 1
    input_hash: str | None = None
    output_artifact_path: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceFileDTO(OrmDTO):
    file_id: str
    file_hash: str
    file_name: str
    original_path: str | None = None
    file_size_bytes: int = 0
    extension: str | None = None
    sheet_count: int = 0
    inspection_status: str = "PROCESSED"
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class SourceSheetDTO(OrmDTO):
    sheet_id: str
    file_id: str
    sheet_name: str
    sheet_index: int
    row_count: int = 0
    column_count: int = 0
    metadata_row_count: int = 1
    is_empty: bool = False
    detected_header_row: int | None = None
    header_confidence: float = 0.0
    selected_date_column: str | None = None
    date_column_confidence: float = 0.0
    variable_column_count: int = 0
    status: str = "PROCESSED"
    review_reasons_json: list[str] = []
    created_at: datetime
    updated_at: datetime


class VariableDTO(OrmDTO):
    variable_id: str
    file_id: str
    sheet_id: str
    original_name: str
    normalized_name: str
    column_index: int
    column_letter: str | None = None
    date_column_name: str | None = None
    inferred_data_type: str | None = None
    unit_hint: str | None = None
    is_empty: bool = False
    is_numeric_candidate: bool = False
    is_text_description: bool = False
    profile_status: str = "PROCESSED"
    review_reasons_json: list[str] = []
    created_at: datetime
    updated_at: datetime


class VariableQualityDTO(OrmDTO):
    variable_id: str
    observation_count: int = 0
    non_null_count: int = 0
    missing_count: int = 0
    missing_rate: float = 0.0
    unique_value_count: int = 0
    start_date: date | None = None
    end_date: date | None = None
    coverage_days: int | None = None
    latest_observation_date: date | None = None
    latest_gap_days: int | None = None
    duplicate_date_count: int = 0
    is_constant: bool = False
    numeric_parse_success_rate: float = 0.0
    date_aligned_observation_count: int = 0
    detected_frequency: str = "unknown"
    median_interval_days: float | None = None
    dominant_interval_days: int | None = None
    dominant_interval_ratio: float | None = None
    frequency_confidence: float = 0.0
    frequency_reason_codes_json: list[str] = []
    is_pseudo_high_frequency: bool = False
    pseudo_frequency_confidence: float = 0.0
    pseudo_frequency_reason_codes_json: list[str] = []
    calculated_at: datetime


class RunFileDTO(OrmDTO):
    run_id: str
    file_id: str
    input_path: str
    artifact_path: str | None = None
    created_at: datetime


class RunVariableDTO(OrmDTO):
    run_id: str
    variable_id: str
    profile_status: str
    created_at: datetime


class AuditEventDTO(OrmDTO):
    event_id: str
    run_id: str | None = None
    event_type: str
    entity_type: str | None = None
    entity_id: str | None = None
    event_payload_json: dict[str, Any] = {}
    created_at: datetime


class LlmCallDTO(OrmDTO):
    llm_call_id: str
    run_id: str | None = None
    batch_id: str | None = None
    task_type: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    request_hash: str | None = None
    response_status: str | None = None
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    cached: bool = False
    attempt_count: int = 1
    error_type: str | None = None
    error_message: str | None = None
    request_artifact_path: str | None = None
    response_artifact_path: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class VariableClassificationDTO(OrmDTO):
    classification_id: str
    variable_id: str
    llm_call_id: str | None = None
    run_id: str | None = None
    batch_id: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    schema_version: str | None = None
    response_id: str | None = None
    standard_name: str | None = None
    industry: str | None = None
    sector: str | None = None
    commodity: str | None = None
    category_level_1: str | None = None
    category_level_2: str | None = None
    metric_name: str | None = None
    data_nature: str | None = None
    market: str | None = None
    region: str | None = None
    unit: str | None = None
    statistical_scope: str | None = None
    comparison_group_key: str | None = None
    comparison_group_components_json: dict[str, Any] | None = None
    confidence: float = 0.0
    reason: str | None = None
    classification_status: str = "PROCESSED"
    review_reasons_json: list[str] = []
    is_derived: bool = False
    parent_metric: str | None = None
    created_at: datetime


class ClassificationCacheDTO(OrmDTO):
    cache_key: str
    classification_payload_json: dict[str, Any] = {}
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    schema_version: str | None = None
    input_hash: str | None = None
    request_artifact_path: str | None = None
    response_artifact_path: str | None = None
    created_at: datetime
    expires_at: datetime | None = None


class ReviewItemDTO(OrmDTO):
    review_item_id: str
    run_id: str
    entity_type: str
    entity_id: str
    review_type: str
    status: str
    reason_code: str | None = None
    reason_text: str | None = None
    resolution_json: dict[str, Any] = {}
    created_at: datetime
    resolved_at: datetime | None = None


class ClassificationCandidateDTO(BaseModel):
    variable: VariableDTO
    file_name: str
    sheet_name: str
    quality: VariableQualityDTO | None = None


class RuleSetDTO(OrmDTO):
    rule_set_id: str
    rule_set_name: str
    version: str
    status: str
    source_type: str | None = None
    source_file_name: str | None = None
    source_hash: str | None = None
    source_language: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    schema_version: str | None = None
    production_ready: bool = False
    parsed_rules_path: str | None = None
    compiled_rules_path: str | None = None
    compiled_hash: str | None = None
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None
    deprecated_at: datetime | None = None


class RuleDTO(OrmDTO):
    rule_id: str
    rule_set_id: str
    rule_type: str
    rule_name: str
    priority: int = 100
    scope_json: dict[str, Any] = {}
    conditions_json: list[dict[str, Any]] = []
    action_json: dict[str, Any] | None = None
    exceptions_json: list[str] = []
    confidence: float = 0.0
    requires_review: bool = False
    source_text_excerpt: str = ""
    created_at: datetime


class RuleConflictDTO(OrmDTO):
    conflict_id: str
    rule_set_id: str
    conflict_type: str
    severity: str
    involved_rule_ids_json: list[str] = []
    description: str
    suggested_resolution: str = ""
    blocks_compilation: bool = False
    created_at: datetime


class RuleParseRunDTO(OrmDTO):
    parse_run_id: str
    pipeline_run_id: str | None = None
    source_hash: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None


class RuleParseCacheDTO(OrmDTO):
    cache_key: str
    source_hash: str
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    schema_version: str | None = None
    parsed_payload_json: dict[str, Any] = {}
    created_at: datetime
    expires_at: datetime | None = None


class SelectionRunDTO(OrmDTO):
    selection_run_id: str
    pipeline_run_id: str
    classification_run_id: str | None = None
    rule_set_id: str | None = None
    rule_set_version: str | None = None
    compiled_hash: str | None = None
    status: str
    started_at: datetime | None = None
    failed_at: datetime | None = None
    total_variables: int = 0
    candidate_variables: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    needs_review_count: int = 0
    not_selected_count: int = 0
    error_type: str | None = None
    error_message: str | None = None
    artifacts_path: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    updated_at: datetime


class VariableSelectionResultDTO(OrmDTO):
    selection_result_id: str
    selection_run_id: str
    variable_id: str
    selection_status: str
    final_status: str
    total_score: float = 0.0
    category_rank: int | None = None
    subcategory_rank: int | None = None
    frequency_rank: int | None = None
    source_rank: int | None = None
    quality_rank: int | None = None
    category_score: float = 0.0
    frequency_score: float = 0.0
    quality_score: float = 0.0
    source_score: float = 0.0
    recency_score: float = 0.0
    coverage_score: float = 0.0
    user_preference_score: float = 0.0
    redundancy_penalty: float = 0.0
    rank: int | None = None
    overall_rank: int | None = None
    comparison_group_key: str | None = None
    group_rank: int | None = None
    reason_code: str | None = None
    reason_text: str | None = None
    primary_reason_code: str | None = None
    primary_reason_text: str | None = None
    matched_rule_ids_json: list[str] = []
    replacement_variable_id: str | None = None
    execution_trace_path: str | None = None
    created_at: datetime
    updated_at: datetime


class ExportRunDTO(OrmDTO):
    export_run_id: str
    pipeline_run_id: str | None = None
    selection_run_id: str | None = None
    status: str
    output_path: str | None = None
    output_file_hash: str | None = None
    output_file_size_bytes: int | None = None
    selected_variable_count: int = 0
    sheet_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ExportedVariableDTO(OrmDTO):
    export_run_id: str
    variable_id: str
    output_sheet_name: str
    output_column_index: int
    output_column_name: str
    created_at: datetime


class FrequencyStatusStatDTO(BaseModel):
    detected_frequency: str
    profile_status: str
    count: int


class ReviewVariableDTO(BaseModel):
    variable_id: str
    column_name: str
    profile_status: str
    missing_rate: float
    is_constant: bool
    review_reasons: list[str]


class RunSummaryDTO(BaseModel):
    run: PipelineRunDTO
    file_count: int
    source_file_count: int
    sheet_count: int
    variable_count: int
    quality_count: int
    review_count: int
    audit_event_count: int


class PersistenceSummaryDTO(BaseModel):
    run_id: str
    status: str
    file_count: int
    source_file_count: int
    sheet_count: int
    variable_count: int
    quality_count: int
    audit_event_count: int
    run_file_count: int
    run_variable_count: int
    idempotent_skip: bool = False
