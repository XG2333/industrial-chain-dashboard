from financial_variable_curation.models.enums import RuleSource
from financial_variable_curation.models.rules import HardFilterRule, RuleSet
from financial_variable_curation.rules.store import RuleStore


def test_saved_rule_set_is_not_auto_production(tmp_path) -> None:
    store = RuleStore(tmp_path)
    rule_set = RuleSet(
        name="test_rule_set",
        source="USER_RULES",
        status="VALIDATED",
        hard_filter_rules=[
            HardFilterRule(field="all_empty", operator="eq", value=True, action="EXCLUDE", reason="test")
        ],
    )
    _, saved = store.save_versioned(rule_set)
    assert saved.source == RuleSource.SAVED_RULE_SET
    assert saved.status.value == "ACTIVE"
    assert saved.production_ready is False


def test_saved_rule_set_can_be_explicitly_production(tmp_path) -> None:
    store = RuleStore(tmp_path)
    rule_set = RuleSet(
        name="test_rule_set_2",
        source="USER_RULES",
        status="VALIDATED",
        hard_filter_rules=[
            HardFilterRule(field="all_empty", operator="eq", value=True, action="EXCLUDE", reason="test")
        ],
    )
    _, saved = store.save_versioned(rule_set, production_ready=True)
    assert saved.production_ready is True
