from __future__ import annotations

from pathlib import Path

from financial_variable_curation.inspection.inspection_service import InspectionService
from financial_variable_curation.models.variable import VariableProfile
from financial_variable_curation.models.workbook import WorkbookProfile


class ExcelWorkbookReader:
    """Compatibility wrapper around the deterministic inspection service."""

    def read(
        self,
        path: str | Path,
        header_row: int | None = None,
        date_column: str | None = None,
    ) -> tuple[WorkbookProfile, list[VariableProfile]]:
        result = InspectionService().inspect(
            path,
            header_row=header_row,
            date_column=date_column,
        )
        return result.workbook_profile, result.variable_profiles
