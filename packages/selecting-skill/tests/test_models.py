from financial_variable_curation.models.enums import RuleSetStatus
from financial_variable_curation.models.rules import (
    Condition,
    ExceptionRule,
    HardFilterRule,
    PrioritySpec,
    ReviewRule,
    RuleSet,
)
from financial_variable_curation.rules.validator import RuleValidator


def test_empty_rule_set_is_legal_but_not_production() -> None:
    rule_set = RuleSet()
    result = RuleValidator().validate(rule_set)
    assert result.valid is True
    assert rule_set.is_empty() is True


def test_empty_active_rule_set_is_invalid() -> None:
    rule_set = RuleSet(status=RuleSetStatus.ACTIVE, production_ready=True)
    result = RuleValidator().validate(rule_set)
    assert result.valid is False
    assert any("ACTIVE" in error or "production_ready" in error for error in result.errors)


def test_priority_conflict_is_invalid() -> None:
    rule_set = RuleSet(
        category_priorities=[
            PrioritySpec(value="price", priority=1),
            PrioritySpec(value="price", priority=2),
        ]
    )
    result = RuleValidator().validate(rule_set)
    assert result.valid is False
    assert any("conflicting priorities" in error for error in result.errors)


def test_duplicate_hard_filter_is_invalid() -> None:
    rule = HardFilterRule(field="all_empty", operator="eq", value=True, action="EXCLUDE", reason="x")
    rule_set = RuleSet(hard_filter_rules=[rule, rule.model_copy(deep=True)])
    result = RuleValidator().validate(rule_set)
    assert result.valid is False
    assert any("duplicate rules" in error for error in result.errors)


def test_exception_requires_complete_condition() -> None:
    rule_set = RuleSet(
        exception_rules=[
            ExceptionRule(action="INCLUDE", when=[], reason="missing condition"),
        ]
    )
    result = RuleValidator().validate(rule_set)
    assert result.valid is False
    assert any("at least one condition" in error for error in result.errors)


def test_invalid_condition_field_is_rejected() -> None:
    rule_set = RuleSet(
        review_rules=[
            ReviewRule(
                condition=Condition(field="not_a_field", operator="eq", value=1),
                reason="bad field",
            )
        ]
    )
    result = RuleValidator().validate(rule_set)
    assert result.valid is False
