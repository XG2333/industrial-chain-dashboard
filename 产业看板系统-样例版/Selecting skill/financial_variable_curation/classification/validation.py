from __future__ import annotations

from collections import Counter

from financial_variable_curation.classification.exceptions import LLMStructuredOutputError
from financial_variable_curation.classification.models import (
    ClassificationRequestItem,
    ClassificationResponse,
    FinancialCategory,
    ValidationIssue,
)


def validate_batch(
    request_items: list[ClassificationRequestItem],
    responses: list[ClassificationResponse],
) -> list[ValidationIssue]:
    requested_ids = [item.variable_id for item in request_items]
    response_ids = [item.variable_id for item in responses]
    if set(requested_ids) != set(response_ids):
        raise LLMStructuredOutputError(
            "Structured output variable set does not match the requested batch."
        )
    duplicates = [variable_id for variable_id, count in Counter(response_ids).items() if count > 1]
    if duplicates:
        raise LLMStructuredOutputError(f"Structured output contains duplicate variables: {duplicates}")

    issues: list[ValidationIssue] = []
    by_request = {item.variable_id: item for item in request_items}
    for response in responses:
        request = by_request[response.variable_id]
        issues.extend(_validate_response(request, response))
    return issues


def apply_issues(response: ClassificationResponse, issues: list[ValidationIssue]) -> None:
    for issue in issues:
        if issue.variable_id == response.variable_id and issue.code not in response.review_reasons:
            response.review_reasons.append(issue.code)
    if response.confidence < 0.6 and "LOW_CONFIDENCE" not in response.review_reasons:
        response.review_reasons.append("LOW_CONFIDENCE")


def _validate_response(
    request: ClassificationRequestItem,
    response: ClassificationResponse,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if response.category_level_1 != FinancialCategory.UNKNOWN:
        if not response.standard_name:
            issues.append(
                ValidationIssue(
                    variable_id=response.variable_id,
                    code="STANDARD_NAME_MISSING",
                    message="standard_name is required when a category is assigned.",
                )
            )
        if not response.data_nature:
            issues.append(
                ValidationIssue(
                    variable_id=response.variable_id,
                    code="DATA_NATURE_MISSING",
                    message="data_nature is required when a category is assigned.",
                )
            )
    if response.is_derived and not response.parent_metric:
        issues.append(
            ValidationIssue(
                variable_id=response.variable_id,
                code="DERIVED_MISSING_PARENT",
                message="Derived variables must identify parent_metric.",
            )
        )
    if request.unit_hint and response.unit:
        request_unit = request.unit_hint.strip().lower().replace(" ", "")
        response_unit = response.unit.strip().lower().replace(" ", "")
        if request_unit and response_unit and request_unit != response_unit:
            issues.append(
                ValidationIssue(
                    variable_id=response.variable_id,
                    code="UNIT_CONFLICT",
                    message=f"Input unit hint {request.unit_hint} conflicts with response unit {response.unit}.",
                )
            )
    if response.category_level_1 != FinancialCategory.UNKNOWN and not response.comparison_group_components:
        issues.append(
            ValidationIssue(
                variable_id=response.variable_id,
                code="COMPARISON_GROUP_MISSING",
                message="comparison_group_components are required for non-unknown classifications.",
            )
        )
    return issues
