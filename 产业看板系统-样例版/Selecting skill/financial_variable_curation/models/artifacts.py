from datetime import datetime, timezone

from pydantic import BaseModel, Field


class DataQualityReport(BaseModel):
    run_id: str
    total_variables: int = 0
    empty_columns: int = 0
    constant_columns: int = 0
    high_missing_columns: int = 0
    needs_review_columns: int = 0
    quality_score_mean: float = 0.0
    notes: list[str] = Field(default_factory=list)


class SelectionAuditReport(BaseModel):
    run_id: str
    rule_name: str
    rule_version: str
    rule_source: str
    rule_status: str
    production_ready: bool
    rules_hash: str | None = None
    prompt_version: str | None = None
    total_variables: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    review_count: int = 0
    output_path: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    engine_notes: list[str] = Field(default_factory=list)


class InspectionSummary(BaseModel):
    run_id: str
    input_file: str
    file_hash: str | None = None
    status: str = "COMPLETED"
    sheets_processed: int = 0
    sheets_successful: int = 0
    sheets_needs_review: int = 0
    sheets_unsupported: int = 0
    raw_column_count: int = 0
    total_variables: int = 0
    valid_variables: int = 0
    empty_columns: int = 0
    constant_columns: int = 0
    comment_columns: int = 0
    text_description_columns: int = 0
    daily_count: int = 0
    weekly_count: int = 0
    monthly_count: int = 0
    quarterly_count: int = 0
    annual_count: int = 0
    irregular_count: int = 0
    unknown_count: int = 0
    other_frequency_count: int = 0
    pseudo_high_frequency_count: int = 0
    review_variable_count: int = 0
    detected_frequencies: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FileValidationResult(BaseModel):
    valid: bool
    file_name: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    file_hash: str | None = None
    errors: list[str] = Field(default_factory=list)


class RequestRecord(BaseModel):
    run_id: str
    input_path: str
    file_hash: str | None = None
    cli_args: dict[str, object] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    software_version: str = ""
