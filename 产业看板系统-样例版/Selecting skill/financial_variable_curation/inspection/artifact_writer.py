from __future__ import annotations

from financial_variable_curation.io.artifacts import ArtifactManager
from financial_variable_curation.models.artifacts import RequestRecord
from financial_variable_curation.models.inspection import InspectionResult


class InspectionArtifactWriter:
    def write(
        self,
        manager: ArtifactManager,
        result: InspectionResult,
        run_log: str,
        request_record: RequestRecord,
    ) -> None:
        manager.write_model("request.json", request_record)
        manager.write_model("workbook_profile.json", result.workbook_profile)
        manager.write_json(
            "variable_profiles.json",
            [profile.model_dump(mode="json") for profile in result.variable_profiles],
        )
        manager.write_model("inspection_summary.json", result.inspection_summary)
        manager.write_text("run.log", run_log)
        manager.write_model("data_quality_report.json", result.data_quality_report)
        manager.write_json(
            "needs_review_variables.json",
            [profile.model_dump(mode="json") for profile in result.needs_review_variables],
        )
