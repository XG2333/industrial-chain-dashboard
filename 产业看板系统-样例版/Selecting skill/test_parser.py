from financial_variable_curation.ai.rule_parser import MockRuleParser


def test_mock_parser_accepts_json_rule_set() -> None:
    payload = """
    {
      "name": "json_rules",
      "source": "USER_RULES",
      "status": "PARSED",
      "hard_filter_rules": [
        {"field": "missing_rate", "operator": "gt", "value": 0.9, "action": "EXCLUDE", "reason": "test"}
      ]
    }
    """
    parsed = MockRuleParser().parse_rules(payload)
    assert parsed.rule_set.name == "json_rules"
    assert parsed.rule_set.hard_filter_rules[0].field == "missing_rate"


def test_mock_parser_handles_generic_phrases() -> None:
    text = """
    规则集名称: generic_rules
    删除全空列
    删除恒定列
    删除缺失率高于 90% 的变量
    优先选择日频
    最多选择 5 个变量
    同类指标无法确认经济含义时进入复核
    """
    parsed = MockRuleParser().parse_rules(text)
    rules = parsed.rule_set
    assert rules.name == "generic_rules"
    assert any(rule.field == "all_empty" for rule in rules.hard_filter_rules)
    assert any(rule.field == "missing_rate" for rule in rules.hard_filter_rules)
    assert rules.frequency_priorities[0].value == "DAILY"
    assert rules.max_variable_count == 5
    assert rules.review_rules


def test_mock_parser_records_unresolved_lines() -> None:
    parsed = MockRuleParser().parse_rules("这条规则解析器看不懂\n")
    assert parsed.rule_set.unresolved_items
    assert parsed.warnings
