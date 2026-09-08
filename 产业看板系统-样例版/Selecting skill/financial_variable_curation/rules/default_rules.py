from __future__ import annotations

from financial_variable_curation.models.enums import RuleSetStatus, RuleSource
from financial_variable_curation.models.rules import (
    Condition,
    DeduplicationRule,
    HardFilterRule,
    ReviewRule,
    RuleSet,
)


def build_default_rules() -> RuleSet:
    """Conservative placeholder rules for end-to-end testing only."""

    return RuleSet(
        name="default_placeholder_conservative",
        version="v1",
        source=RuleSource.DEFAULT_PLACEHOLDER,
        status=RuleSetStatus.VALIDATED,
        production_ready=False,
        prompt_version="default-placeholder-v1",
        hard_filter_rules=[
            HardFilterRule(
                field="all_empty",
                operator="eq",
                value=True,
                action="EXCLUDE",
                reason="Default placeholder: delete fully empty columns.",
            ),
            HardFilterRule(
                field="constant",
                operator="eq",
                value=True,
                action="EXCLUDE",
                reason="Default placeholder: delete clearly constant columns.",
            ),
            HardFilterRule(
                field="missing_rate",
                operator="gt",
                value=0.9,
                action="REJECTED",
                reason="Default placeholder: very high missing rate.",
            ),
            HardFilterRule(
                field="missing_rate",
                operator="gt",
                value=0.5,
                action="NEEDS_REVIEW",
                reason="Default placeholder: high missing rate requires review.",
            ),
        ],
        deduplication_rules=[
            DeduplicationRule(
                group_by=["category", "subcategory"],
                method="none",
                keep="all",
                needs_review_on_ambiguous=True,
            )
        ],
        review_rules=[
            ReviewRule(
                condition=Condition(field="category", operator="eq", value="UNCLASSIFIED"),
                reason="Default placeholder: unclassified variables require review.",
            )
        ],
        unresolved_items=[
            "DEFAULT_PLACEHOLDER rules only validate the workflow; they are not formal business rules."
        ],
        metadata={"production_note": "This rule set is not production-ready."},
    )
