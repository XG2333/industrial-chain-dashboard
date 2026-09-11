from __future__ import annotations

from pathlib import Path

import pandas as pd

from financial_variable_curation.models.workbook import WorkbookProfile
from financial_variable_curation.pipeline.execute import SelectionResult


def write_selection_workbook(
    input_path: str | Path,
    workbook_profile: WorkbookProfile,
    result: SelectionResult,
    output_path: str | Path,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_profile in workbook_profile.sheets:
            frame = pd.read_excel(input_path, sheet_name=sheet_profile.sheet_name)
            selected_for_sheet = [
                profile
                for profile in result.selected_variables
                if profile.sheet_name == sheet_profile.sheet_name
            ]
            column_indices = list(sheet_profile.date_column_indices)
            for profile in selected_for_sheet:
                if profile.column_index not in column_indices:
                    column_indices.append(profile.column_index)
            column_indices = [index for index in column_indices if index < len(frame.columns)]
            if column_indices:
                frame.iloc[:, column_indices].to_excel(writer, sheet_name=sheet_profile.sheet_name, index=False)

        decision_rows = [profile.model_dump(mode="json") for profile in result.all_variables]
        pd.DataFrame(decision_rows).to_excel(writer, sheet_name="DecisionLog", index=False)
        pd.DataFrame([result.audit.model_dump(mode="json")]).to_excel(
            writer, sheet_name="AuditSummary", index=False
        )
    return output.resolve()
