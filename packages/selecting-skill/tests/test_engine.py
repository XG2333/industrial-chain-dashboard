from financial_variable_curation.models.rules import (
    Condition,
    HardFilterRule,
    ReviewRule,
    RuleSet,
    ScoringRule,
)
from financial_variable_curation.pipeline.execute import DeterministicRuleEngine
from financial_variable_curation.pipeline.inspect import run_inspection
from financial_variable_curation.rules.compiler import RuleCompiler
from financial_variable_curation.rules.default_rules import build_default_rules


def test_default_rules_execute_conservatively(sample_workbook) -> None:
    inspection = run_inspection(sample_workbook)
    compiled = RuleCompiler().compile(build_default_rules())
    decisions = DeterministicRuleEngine().execute(inspection.variable_profiles, compiled)
    statuses = {profile.column_name: profile.status.value for profile in decisions}
    assert statuses["empty_col"] == "EXCLUDE"
    assert statuses["constant_col"] == "EXCLUDE"
    assert statuses["high_missing"] == "REJECTED"
    assert statuses["close_price"] == "NEEDS_REVIEW"
    assert statuses["close_price_2"] == "NEEDS_REVIEW"
    assert statuses["note"] == "NEEDS_REVIEW"
    assert statuses["volume"] in {"INCLUDE", "NEEDS_REVIEW"}


def test_empty_rule_set_does_not_auto_remove(sample_workbook) -> None:
    inspection = run_inspection(sample_workbook)
    compiled = RuleCompiler().compile(RuleSet(name="empty_legal"))
    decisions = DeterministicRuleEngine().execute(inspection.variable_profiles, compiled)
    assert all(profile.status.value == "INCLUDE" for profile in decisions)


def test_user_hard_filter_and_scoring_are_deterministic(sample_workbook) -> None:
    inspection = run_inspection(sample_workbook)
    rules = RuleSet(
        name="user_hard_filter",
        source="USER_RULES",
        status="VALIDATED",
        hard_filter_rules=[
            HardFilterRule(
                field="missing_rate",
                operator="gt",
                value=0.5,
                action="EXCLUDE",
                reason="user rule",
            )
        ],
        scoring_rules=[
            ScoringRule(field="quality_score", weight=1.0, transform="raw"),
        ],
        max_variable_count=3,
    )
    compiled = RuleCompiler().compile(rules)
    decisions = DeterministicRuleEngine().execute(inspection.variable_profiles, compiled)
    included = [profile for profile in decisions if profile.status.value == "INCLUDE"]
    assert len(included) == 3
    assert all(profile.score > 0 for profile in decisions if profile.status.value != "EXCLUDE")


def test_unknown_condition_does_not_crash_engine(sample_workbook) -> None:
    inspection = run_inspection(sample_workbook)
    rules = RuleSet(
        name="unknown_condition",
        source="USER_RULES",
        status="VALIDATED",
        review_rules=[
            ReviewRule(
                condition=Condition(field="missing_rate", operator="gt", value=0.1),
                reason="review test",
            )
        ],
    )
    compiled = RuleCompiler().compile(rules)
    decisions = DeterministicRuleEngine().execute(inspection.variable_profiles, compiled)
    assert any(profile.status.value == "NEEDS_REVIEW" for profile in decisions)
