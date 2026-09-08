from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from financial_variable_curation.database.base import Base
from financial_variable_curation.database.types import JSONText, UTCDateTime, utcnow


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    failed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_successful_step: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_request_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, nullable=True)
    artifacts_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_retriable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_name", name="uq_pipeline_steps_run_step"),
        Index("ix_pipeline_steps_run_status", "run_id", "status"),
    )

    step_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(String(120), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SourceFile(Base):
    __tablename__ = "source_files"

    file_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sheet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inspection_status: Mapped[str] = mapped_column(String(40), nullable=False, default="PROCESSED")
    first_seen_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SourceSheet(Base):
    __tablename__ = "source_sheets"
    __table_args__ = (
        UniqueConstraint("file_id", "sheet_index", name="uq_source_sheets_file_index"),
        Index("ix_source_sheets_file_status", "file_id", "status"),
    )

    sheet_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("source_files.file_id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_empty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detected_header_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    header_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    selected_date_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_column_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    variable_column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    review_reasons_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class Variable(Base):
    __tablename__ = "variables"
    __table_args__ = (
        UniqueConstraint("sheet_id", "column_index", name="uq_variables_sheet_column"),
        Index("ix_variables_file_id", "file_id"),
        Index("ix_variables_profile_status", "profile_status"),
    )

    variable_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("source_files.file_id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("source_sheets.sheet_id", ondelete="CASCADE"),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    column_letter: Mapped[str | None] = mapped_column(String(8), nullable=True)
    date_column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inferred_data_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unit_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_empty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_numeric_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_text_description: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profile_status: Mapped[str] = mapped_column(String(40), nullable=False)
    review_reasons_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class VariableQuality(Base):
    __tablename__ = "variable_quality"

    variable_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("variables.variable_id", ondelete="CASCADE"),
        primary_key=True,
    )
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    non_null_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unique_value_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_gap_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_date_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_constant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    numeric_parse_success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    date_aligned_observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_frequency: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    median_interval_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    dominant_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dominant_interval_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    frequency_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    frequency_reason_codes_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    is_pseudo_high_frequency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pseudo_frequency_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pseudo_frequency_reason_codes_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    calculated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)


class RunFile(Base):
    __tablename__ = "run_files"
    __table_args__ = (
        Index("ix_run_files_file_id", "file_id"),
        Index("ix_run_files_created_at", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("source_files.file_id", ondelete="CASCADE"),
        primary_key=True,
    )
    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class RunVariable(Base):
    __tablename__ = "run_variables"
    __table_args__ = (
        Index("ix_run_variables_variable_id", "variable_id"),
        Index("ix_run_variables_created_at", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    variable_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("variables.variable_id", ondelete="CASCADE"),
        primary_key=True,
    )
    profile_status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_run_event", "run_id", "event_type"),
        Index("ix_audit_events_event_type", "event_type"),
    )

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    event_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONText, nullable=False, default=dict)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_run_id", "run_id"),
        Index("ix_llm_calls_batch_id", "batch_id"),
    )

    llm_call_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=True,
    )
    batch_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    response_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class VariableClassification(Base):
    __tablename__ = "variable_classifications"
    __table_args__ = (
        Index("ix_variable_classifications_variable_id", "variable_id"),
        Index("ix_variable_classifications_run_id", "run_id"),
    )

    classification_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    variable_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("variables.variable_id", ondelete="CASCADE"),
        nullable=False,
    )
    llm_call_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=True,
    )
    batch_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    response_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    standard_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    commodity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category_level_1: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category_level_2: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_nature: Mapped[str | None] = mapped_column(String(120), nullable=True)
    market: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(120), nullable=True)
    statistical_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comparison_group_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comparison_group_components_json: Mapped[dict[str, Any]] = mapped_column(JSONText, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classification_status: Mapped[str] = mapped_column(String(40), nullable=False)
    review_reasons_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_metric: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ClassificationCache(Base):
    __tablename__ = "classification_cache"

    cache_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    classification_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONText, nullable=False, default=dict)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class RuleSet(Base):
    __tablename__ = "rule_sets"
    __table_args__ = (
        UniqueConstraint("rule_set_name", "version", name="uq_rule_sets_name_version"),
    )

    rule_set_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    rule_set_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    production_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parsed_rules_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiled_rules_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiled_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)
    activated_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    deprecated_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "rule_id", name="uq_rules_set_rule"),
        Index("ix_rules_rule_set_id", "rule_set_id"),
    )

    rule_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    rule_set_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rule_sets.rule_set_id", ondelete="CASCADE"),
        primary_key=True,
    )
    rule_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONText, nullable=False, default=dict)
    conditions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, nullable=False, default=list)
    action_json: Mapped[dict[str, Any] | None] = mapped_column(JSONText, nullable=True)
    exceptions_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_text_excerpt: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class RuleConflict(Base):
    __tablename__ = "rule_conflicts"

    conflict_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    rule_set_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("rule_sets.rule_set_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conflict_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    involved_rule_ids_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_resolution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blocks_compilation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class RuleParseRun(Base):
    __tablename__ = "rule_parse_runs"
    __table_args__ = (Index("ix_rule_parse_runs_source_hash", "source_hash"),)

    parse_run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False)
    completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class RuleParseCache(Base):
    __tablename__ = "rule_parse_cache"

    cache_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    taxonomy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parsed_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONText, nullable=False, default=dict)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    expires_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)


class SelectionRun(Base):
    __tablename__ = "selection_runs"
    __table_args__ = (Index("ix_selection_runs_pipeline_run_id", "pipeline_run_id"),)

    selection_run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    pipeline_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    classification_run_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    rule_set_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("rule_sets.rule_set_id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_set_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    compiled_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    started_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    failed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    total_variables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_variables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class VariableSelectionResult(Base):
    __tablename__ = "variable_selection_results"
    __table_args__ = (Index("ix_variable_selection_results_variable_id", "variable_id"),)

    selection_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("selection_runs.selection_run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    selection_result_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    variable_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("variables.variable_id", ondelete="CASCADE"),
        primary_key=True,
    )
    selection_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    final_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subcategory_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frequency_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    frequency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    coverage_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    user_preference_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    redundancy_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comparison_group_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    group_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    primary_reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_rule_ids_json: Mapped[list[str]] = mapped_column(JSONText, nullable=False, default=list)
    replacement_variable_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("variables.variable_id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_trace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ExportRun(Base):
    __tablename__ = "export_runs"

    export_run_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=True,
    )
    selection_run_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("selection_runs.selection_run_id", ondelete="CASCADE"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_file_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    output_file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_variable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sheet_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("ix_export_runs_selection_run_id", "selection_run_id"),
    )


class ExportedVariable(Base):
    __tablename__ = "exported_variables"
    __table_args__ = (
        Index("ix_exported_variables_export_run_id", "export_run_id"),
        Index("ix_exported_variables_variable_id", "variable_id"),
    )

    export_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("export_runs.export_run_id", ondelete="CASCADE"),
        primary_key=True,
    )
    variable_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("variables.variable_id", ondelete="CASCADE"),
        primary_key=True,
    )
    output_sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    output_column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    output_column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (Index("ix_review_items_run_status", "run_id", "status"),)

    review_item_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("pipeline_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    review_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_json: Mapped[dict[str, Any]] = mapped_column(JSONText, nullable=False, default=dict)
    created_at: Mapped[Any] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    resolved_at: Mapped[Any | None] = mapped_column(UTCDateTime, nullable=True)
