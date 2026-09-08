from __future__ import annotations

from pathlib import Path

import pytest

from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import RuleSetRepository
from financial_variable_curation.rule_workflow.compiler import RuleCompilationError, RuleCompiler
from financial_variable_curation.rule_workflow.conflicts import RuleConflictDetector
from financial_variable_curation.rule_workflow.exceptions import RuleSourceError, RuleWorkflowError
from financial_variable_curation.rule_workflow.mock_parser import MockRuleParser
from financial_variable_curation.rule_workflow.models import (
    Rule,
    RuleAction,
    RuleCondition,
    RuleScope,
    RuleSetDocument,
)
from financial_variable_curation.rule_workflow.normalizer import RuleNormalizer
from financial_variable_curation.rule_workflow.service import RuleParserService
from financial_variable_curation.rule_workflow.validator import RuleSchemaValidator


RULES_TEXT = """价格 > 价差 > 库存 > 产量 > 进口 > 出口
日频 > 周频 > 月频
缺失率超过40%的变量删除
同一指标只保留一个
分类置信度低于0.8的变量进入人工复核
最终最多保留30个变量
"""


def _write_rules(tmp_path: Path, text: str = RULES_TEXT) -> Path:
    path = tmp_path / "rules.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _settings(**overrides) -> LLMSettings:
    values = {
        "llm_provider": "mock",
        "llm_prompt_version": "rule_v1",
        "llm_taxonomy_version": "tax_v1",
        "rule_schema_version": "schema_v1",
    }
    values.update(overrides)
    return LLMSettings(**values)


def _rule(
    rule_id: str,
    rule_type: str,
    *,
    ordered_values: list[str] | None = None,
    conditions: list[RuleCondition] | None = None,
    action: RuleAction | None = None,
    scope: RuleScope | None = None,
    priority: int = 100,
) -> Rule:
    return Rule(
        rule_id=rule_id,
        rule_type=rule_type,
        rule_name=rule_id,
        ordered_values=ordered_values or [],
        conditions=conditions or [],
        action=action,
        scope=scope or RuleScope(),
        confidence=0.8,
        priority=priority,
    )


def test_empty_rule_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(RuleSourceError):
        RuleParserService().validate_rules(path, provider="mock")


def test_nonexistent_rule_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RuleSourceError):
        RuleParserService().validate_rules(tmp_path / "missing.txt", provider="mock")


def test_non_utf8_rule_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(RuleSourceError):
        RuleParserService().validate_rules(path, provider="mock")


def test_md_rule_file_is_accepted(db_manager: DatabaseManager, tmp_path: Path) -> None:
    path = tmp_path / "rules.md"
    path.write_text("# Rules\n价格优先于数量", encoding="utf-8")
    result = RuleParserService(db_manager, settings=_settings()).validate_rules(path, provider="mock")
    assert result.summary.rule_count == 1


def test_source_hash_is_stable(db_manager: DatabaseManager, tmp_path: Path) -> None:
    path = _write_rules(tmp_path)
    service = RuleParserService(db_manager, settings=_settings())
    first = service.validate_rules(path, provider="mock")
    second = service.validate_rules(path, provider="mock")
    assert first.summary.source_hash == second.summary.source_hash


def test_mock_parser_recognizes_required_examples() -> None:
    document = MockRuleParser().parse(RULES_TEXT, {"rule_set_name": "rules"})
    types = {rule.rule_type for rule in document.rules}
    assert "CATEGORY_PRIORITY" in types
    assert "FREQUENCY_PRIORITY" in types
    assert "HARD_FILTER" in types
    assert "DEDUPLICATION" in types
    assert "REVIEW" in types
    assert "MAX_COUNT" in types
    hard_filter = next(rule for rule in document.rules if rule.rule_type == "HARD_FILTER")
    assert hard_filter.conditions[0].value == 0.4


def test_unknown_field_is_rejected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule(
                "r1",
                "HARD_FILTER",
                conditions=[RuleCondition(field="not_allowed", operator="GT", value=0.5)],
            )
        ]
    )
    report = RuleSchemaValidator().validate(document)
    assert not report.valid
    assert any("not_allowed" in error for error in report.errors)


def test_unknown_operator_is_rejected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule(
                "r1",
                "HARD_FILTER",
                conditions=[RuleCondition(field="missing_rate", operator="LIKE", value=0.5)],
            )
        ]
    )
    report = RuleSchemaValidator().validate(document)
    assert any("LIKE" in error for error in report.errors)


def test_unknown_action_is_rejected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule(
                "r1",
                "HARD_FILTER",
                conditions=[RuleCondition(field="missing_rate", operator="GT", value=0.5)],
                action=RuleAction(action_type="DROP_IT"),
            )
        ]
    )
    report = RuleSchemaValidator().validate(document)
    assert any("DROP_IT" in error for error in report.errors)


def test_normalizer_dedupes_ordered_values_and_sorts_rules() -> None:
    document = RuleSetDocument(
        rules=[
            _rule("r2", "CATEGORY_PRIORITY", ordered_values=["price", "价格", "inventory", "price"], priority=20),
            _rule("r1", "CATEGORY_PRIORITY", ordered_values=["export", "import"], priority=10),
        ]
    )
    normalized = RuleNormalizer().normalize(document)
    assert normalized.rules[0].ordered_values == ["EXPORT", "IMPORT"]
    assert normalized.rules[1].ordered_values == ["PRICE", "INVENTORY"]


def test_rule_id_and_compiled_hash_are_stable() -> None:
    document = MockRuleParser().parse(RULES_TEXT, {"rule_set_name": "rules"})
    first = RuleNormalizer().normalize(document)
    second = RuleNormalizer().normalize(document)
    assert [rule.rule_id for rule in first.rules] == [rule.rule_id for rule in second.rules]
    conflicts = RuleConflictDetector().detect(first)
    compiled_one = RuleCompiler().compile(first, source_hash="hash", rule_set_name="r", version="1", conflicts=conflicts)
    compiled_two = RuleCompiler().compile(second, source_hash="hash", rule_set_name="r", version="1", conflicts=conflicts)
    assert compiled_one.compiled_hash == compiled_two.compiled_hash


def test_sort_conflict_is_detected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule("a", "CATEGORY_PRIORITY", ordered_values=["PRICE", "INVENTORY"]),
            _rule("b", "CATEGORY_PRIORITY", ordered_values=["INVENTORY", "PRICE"]),
        ]
    )
    conflicts = RuleConflictDetector().detect(document)
    assert any(item.conflict_type == "ORDER_CONFLICT" for item in conflicts.conflicts)


def test_frequency_conflict_is_detected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule("a", "FREQUENCY_PRIORITY", ordered_values=["DAILY", "MONTHLY"]),
            _rule("b", "FREQUENCY_PRIORITY", ordered_values=["MONTHLY", "DAILY"]),
        ]
    )
    conflicts = RuleConflictDetector().detect(document)
    assert any(item.conflict_type == "ORDER_CONFLICT" for item in conflicts.conflicts)


def test_filter_conflict_is_detected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule(
                "a",
                "HARD_FILTER",
                conditions=[RuleCondition(field="missing_rate", operator="GT", value=0.4)],
                action=RuleAction(action_type="REJECT"),
            ),
            _rule(
                "b",
                "HARD_FILTER",
                conditions=[RuleCondition(field="missing_rate", operator="GT", value=0.3)],
                action=RuleAction(action_type="KEEP"),
            ),
        ]
    )
    conflicts = RuleConflictDetector().detect(document)
    assert any(item.conflict_type == "FILTER_CONFLICT" for item in conflicts.conflicts)


def test_deduplication_conflict_is_detected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule(
                "a",
                "DEDUPLICATION",
                action=RuleAction(action_type="KEEP_TOP_N", keep_n=1, group_by=["comparison_group_key"]),
            ),
            _rule(
                "b",
                "DEDUPLICATION",
                action=RuleAction(action_type="KEEP_TOP_N", keep_n=2, group_by=["comparison_group_key"]),
            ),
        ]
    )
    conflicts = RuleConflictDetector().detect(document)
    assert any(item.conflict_type == "DEDUP_CONFLICT" for item in conflicts.conflicts)


def test_scope_conflict_is_detected() -> None:
    document = RuleSetDocument(
        rules=[
            _rule("a", "CATEGORY_PRIORITY", ordered_values=["PRICE", "INVENTORY"]),
            _rule(
                "b",
                "CATEGORY_PRIORITY",
                ordered_values=["INVENTORY", "PRICE"],
                scope=RuleScope(commodities=["TIN"]),
            ),
        ]
    )
    conflicts = RuleConflictDetector().detect(document)
    assert any(item.conflict_type == "SCOPE_CONFLICT" for item in conflicts.conflicts)


def test_impossible_range_conflict_is_fatal_and_blocks_compile() -> None:
    document = RuleSetDocument(
        rules=[
            _rule(
                "a",
                "HARD_FILTER",
                conditions=[RuleCondition(field="missing_rate", operator="GT", value=0.9)],
                action=RuleAction(action_type="REJECT"),
            ),
            _rule(
                "b",
                "HARD_FILTER",
                conditions=[RuleCondition(field="missing_rate", operator="LT", value=0.1)],
                action=RuleAction(action_type="KEEP"),
            ),
        ]
    )
    normalized = RuleNormalizer().normalize(document)
    conflicts = RuleConflictDetector().detect(normalized)
    assert any(item.severity == "FATAL" for item in conflicts.conflicts)
    with pytest.raises(RuleCompilationError):
        RuleCompiler().compile(normalized, source_hash="hash", rule_set_name="r", version="1", conflicts=conflicts)


def test_service_cache_hit_and_force_refresh(
    db_manager: DatabaseManager,
    tmp_path: Path,
) -> None:
    path = _write_rules(tmp_path)
    service = RuleParserService(db_manager, settings=_settings())
    first = service.validate_rules(path, provider="mock", rule_set_name="cache", artifacts_dir=tmp_path / "a")
    assert first.cache_hit is False
    second = service.validate_rules(path, provider="mock", rule_set_name="cache", artifacts_dir=tmp_path / "b")
    assert second.cache_hit is True
    third = service.validate_rules(
        path,
        provider="mock",
        rule_set_name="cache",
        force_refresh=True,
        artifacts_dir=tmp_path / "c",
    )
    assert third.cache_hit is False


def test_prompt_and_schema_version_change_invalidate_cache(
    db_manager: DatabaseManager,
    tmp_path: Path,
) -> None:
    path = _write_rules(tmp_path)
    first = RuleParserService(db_manager, settings=_settings()).validate_rules(
        path, provider="mock", rule_set_name="versions", artifacts_dir=tmp_path
    )
    assert first.cache_hit is False
    second = RuleParserService(
        db_manager, settings=_settings(llm_prompt_version="rule_v2")
    ).validate_rules(path, provider="mock", rule_set_name="versions", artifacts_dir=tmp_path)
    assert second.cache_hit is False
    third = RuleParserService(
        db_manager, settings=_settings(rule_schema_version="schema_v2")
    ).validate_rules(path, provider="mock", rule_set_name="versions", artifacts_dir=tmp_path)
    assert third.cache_hit is False


def test_dry_run_does_not_persist_rule_set(
    db_manager: DatabaseManager,
    tmp_path: Path,
) -> None:
    path = _write_rules(tmp_path)
    result = RuleParserService(db_manager, settings=_settings()).compile_rules(
        path,
        provider="mock",
        name="dry_run_rules",
        version="1",
        dry_run=True,
        artifacts_dir=tmp_path,
    )
    assert result.dry_run is True
    with db_manager.session_scope() as session:
        assert RuleSetRepository(session).get_by_name_version("dry_run_rules", "1") is None


def test_compile_version_management(
    db_manager: DatabaseManager,
    tmp_path: Path,
) -> None:
    path = _write_rules(tmp_path)
    service = RuleParserService(db_manager, settings=_settings())
    first = service.compile_rules(
        path,
        provider="mock",
        name="versioned_rules",
        version="1",
        artifacts_dir=tmp_path,
    )
    assert first.compiled is not None
    with db_manager.session_scope() as session:
        assert RuleSetRepository(session).get_by_name_version("versioned_rules", "1").status == "VALIDATED"
    with pytest.raises(RuleWorkflowError):
        service.compile_rules(
            path,
            provider="mock",
            name="versioned_rules",
            version="1",
            artifacts_dir=tmp_path,
        )
    second = service.compile_rules(
        path,
        provider="mock",
        name="versioned_rules",
        version="2",
        artifacts_dir=tmp_path,
    )
    assert second.compiled is not None


def test_activate_blocks_on_error_conflict(
    db_manager: DatabaseManager,
    tmp_path: Path,
) -> None:
    path = tmp_path / "conflict.txt"
    path.write_text(
        "价格 > 库存\n库存 > 价格\n",
        encoding="utf-8",
    )
    service = RuleParserService(db_manager, settings=_settings())
    with pytest.raises(RuleWorkflowError):
        service.compile_rules(
            path,
            provider="mock",
            name="conflict_rules",
            version="1",
            activate=True,
            artifacts_dir=tmp_path,
        )
