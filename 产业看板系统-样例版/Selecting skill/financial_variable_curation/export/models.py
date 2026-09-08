from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExportColumnMapping(BaseModel):
    variable_id: str
    original_sheet_name: str
    original_column_index: int
    original_column_name: str
    output_sheet_name: str
    output_column_index: int
    output_column_name: str


class ExportSummary(BaseModel):
    export_run_id: str
    selection_run_id: str
    pipeline_run_id: str
    status: str
    output_path: str | None = None
    output_file_hash: str | None = None
    output_file_size_bytes: int | None = None
    selected_variable_count: int = 0
    sheet_count: int = 0
    sheet_names: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    completed_at: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    artifacts_path: str | None = None


class PipelineSummary(BaseModel):
    pipeline_run_id: str
    status: str = "CREATED"
    stages: dict[str, str] = Field(default_factory=dict)
    selection_run_id: str | None = None
    export_run_id: str | None = None
    output_path: str | None = None
    output_file_hash: str | None = None
    dry_run: bool = False
    warnings: list[str] = Field(default_factory=list)
