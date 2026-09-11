from datetime import date

from pydantic import BaseModel, Field

from financial_variable_curation.models.enums import ClassificationMethod, DataType, VariableStatus


class FrequencyProfile(BaseModel):
    detected_frequency: str = "unknown"
    median_interval_days: float | None = None
    major_interval_days: int | None = None
    major_interval_ratio: float | None = None
    confidence: float = 0.0
    reason_code: str = "NO_DATA"
    frequency_reason_codes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VariableClassification(BaseModel):
    category: str = "UNCLASSIFIED"
    subcategory: str = "UNCLASSIFIED"
    semantic_description: str = ""
    confidence: float = 0.0
    method: ClassificationMethod = ClassificationMethod.UNCLASSIFIED
    needs_review: bool = True
    notes: list[str] = Field(default_factory=list)


class VariableProfile(BaseModel):
    variable_id: str = ""
    file_name: str = ""
    file_hash: str | None = None
    sheet_name: str
    sheet_index: int = 0
    column_index: int
    column_position: int = 0
    column_name: str
    original_header: str
    original_name: str = ""
    normalized_header: str = ""
    normalized_name: str = ""
    column_letter: str = ""
    date_column_name: str | None = None
    inferred_data_type: str = ""
    unit_hint: str | None = None
    is_date_column: bool = False
    is_empty_column: bool = False
    is_empty: bool = False
    is_comment_column: bool = False
    is_text_description: bool = False
    is_numeric_candidate: bool = False
    is_valid_variable: bool = True
    profile_status: str = "PROCESSED"
    review_reasons: list[str] = Field(default_factory=list)
    data_type: DataType = DataType.MIXED
    observation_count: int = 0
    row_count: int = 0
    non_null_count: int = 0
    missing_count: int = 0
    missing_rate: float = 1.0
    unique_value_count: int = 0
    unique_count: int = 0
    constant: bool = False
    is_constant: bool = False
    all_empty: bool = False
    numeric_rate: float = 0.0
    date_parse_rate: float = 0.0
    text_rate: float = 0.0
    time_coverage: float = 0.0
    quality_score: float = 0.0
    start_date: date | None = None
    end_date: date | None = None
    coverage_days: int | None = None
    duplicate_date_count: int = 0
    date_aligned_observation_count: int = 0
    numeric_parse_success_rate: float = 0.0
    latest_observation_date: date | None = None
    latest_gap_days: int | None = None
    frequency: FrequencyProfile = Field(default_factory=FrequencyProfile)
    declared_frequency: str | None = None
    inferred_frequency: str | None = None
    is_pseudo_high_frequency: bool = False
    pseudo_frequency_confidence: float = 0.0
    pseudo_frequency_reason: str | None = None
    pseudo_frequency_reason_codes: list[str] = Field(default_factory=list)
    source: str | None = None
    classification: VariableClassification = Field(default_factory=VariableClassification)
    status: VariableStatus = VariableStatus.UNPROCESSED
    status_reason: str | None = None
    score: float = 0.0
    rank: int | None = None
    dedupe_group: str | None = None
