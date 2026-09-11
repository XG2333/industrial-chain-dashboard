from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class DateCandidate(BaseModel):
    column_index: int
    header: str
    confidence: float = 0.0
    date_type_ratio: float = 0.0
    date_parse_rate: float = 0.0
    sorted_ratio: float = 0.0
    unique_ratio: float = 0.0
    coverage_days: int | None = None
    reason: str = ""
    reason_code: str = "DATE_CANDIDATE"


class DateDetection(BaseModel):
    status: str = "NO_DATE_COLUMN"
    selected_column: str | None = None
    selected_column_index: int | None = None
    candidates: list[DateCandidate] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class HeaderDetection(BaseModel):
    status: str = "NEEDS_REVIEW"
    header_row: int | None = None
    confidence: float = 0.0
    reason: str | None = None
    reason_code: str = "HEADER_NEEDS_REVIEW"


class SheetProfile(BaseModel):
    sheet_name: str
    sheet_index: int = 0
    row_count: int
    column_count: int
    metadata_row_count: int = 1
    empty_sheet: bool = False
    detected_header_row: int | None = None
    header_confidence: float = 0.0
    selected_date_column: str | None = None
    date_column_confidence: float = 0.0
    variable_column_count: int = 0
    status: str = "PROCESSED"
    review_reasons: list[str] = Field(default_factory=list)
    header_detection: HeaderDetection = Field(default_factory=HeaderDetection)
    date_detection: DateDetection = Field(default_factory=DateDetection)
    date_column_candidates: list[str] = Field(default_factory=list)
    date_column_indices: list[int] = Field(default_factory=list)
    variable_columns: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    header: list[str] = Field(default_factory=list)


class WorkbookProfile(BaseModel):
    workbook_path: str
    run_id: str = ""
    file_name: str = ""
    file_path: str = ""
    file_hash: str | None = None
    file_size_bytes: int = 0
    sheet_count: int = 0
    sheet_names: list[str] = Field(default_factory=list)
    empty_sheet_count: int = 0
    sheets: list[SheetProfile] = Field(default_factory=list)
    total_rows: int = 0
    total_columns: int = 0
    profile_version: str = "2.0"
    inspection_started_at: datetime | None = None
    inspection_completed_at: datetime | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "COMPLETED"
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def path(self) -> Path:
        return Path(self.workbook_path)
