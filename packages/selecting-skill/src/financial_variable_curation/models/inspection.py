from pydantic import BaseModel, Field

from financial_variable_curation.models.artifacts import DataQualityReport, InspectionSummary
from financial_variable_curation.models.variable import VariableProfile
from financial_variable_curation.models.workbook import WorkbookProfile


class InspectionResult(BaseModel):
    workbook_profile: WorkbookProfile
    variable_profiles: list[VariableProfile] = Field(default_factory=list)
    data_quality_report: DataQualityReport
    needs_review_variables: list[VariableProfile] = Field(default_factory=list)
    inspection_summary: InspectionSummary
