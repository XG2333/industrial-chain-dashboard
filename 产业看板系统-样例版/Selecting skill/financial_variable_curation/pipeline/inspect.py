from __future__ import annotations

from pathlib import Path

from financial_variable_curation.ai.classification import VariableClassifier
from financial_variable_curation.inspection.inspection_service import InspectionService
from financial_variable_curation.models.inspection import InspectionResult


def run_inspection(
    input_path: str | Path,
    classifier: VariableClassifier | None = None,
    header_row: int | None = None,
    date_column: str | None = None,
    sheet: str | None = None,
    run_id: str = "inspect",
) -> InspectionResult:
    result = InspectionService().inspect(
        input_path,
        header_row=header_row,
        date_column=date_column,
        sheet_filter=sheet,
        run_id=run_id,
    )
    if classifier is not None:
        for profile in result.variable_profiles:
            profile.classification = classifier.classify(profile)
        result.needs_review_variables = [
            profile
            for profile in result.variable_profiles
            if profile.classification.needs_review
            or profile.missing_rate > 0.5
            or profile.constant
            or profile.all_empty
        ]
    return result
