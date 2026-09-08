from __future__ import annotations

from pathlib import Path

from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.classification.service import BatchClassificationService
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.services import InspectionPersistenceService
from financial_variable_curation.models.artifacts import RequestRecord
from financial_variable_curation.pipeline.inspect import run_inspection
from financial_variable_curation.rule_workflow.service import RuleParserService
from financial_variable_curation.selection.engine import RuleExecutionEngine
from financial_variable_curation.selection.models import CandidateVariable
from financial_variable_curation.selection.service import VariableSelectionService
from financial_variable_curation.rule_workflow.models import (
    CompiledRule,
    CompiledRuleSetOutput,
    Rule,
    RuleAction,
    RuleCondition,
)


def _candidate(
    variable_id: str,
    *,
    category: str = "PRICE",
    frequency: str = "daily",
    missing_rate: float = 0.0,
    comparison_group_key: str = "tin|price|cn",
    classification_status: str = "COMPLETED",
) -> CandidateVariable:
    return CandidateVariable(
        variable_id=variable_id,
        run_id="run",
        original_name=variable_id,
        standard_name=variable_id,
        commodity="TIN",
        category_level_1=category,
        category_level_2="FUTURES_PRICE",
        metric_name="close_price",
        data_nature="LEVEL",
        market="SHFE",
        region="CN",
        unit_standard="CNY_PER_TON",
        comparison_group_key=comparison_group_key,
        classification_confidence=0.9,
        classification_status=classification_status,
        detected_frequency=frequency,
        missing_rate=missing_rate,
        non_null_count=100,
        unique_value_count=90,
        coverage_days=100,
        quality_score=80.0,
    )


def _compiled(*compiled_rules: CompiledRule) -> CompiledRuleSetOutput:
    return CompiledRuleSetOutput(
        compiled_rule_set_id="ruleset",
        rule_set_name="test_rules",
        version="1",
        status="VALIDATED",
        production_ready=False,
        compiled_rules=list(compiled_rules),
        execution_plan=list({rule.execution_phase for rule in compiled_rules}),
        source_hash="source",
        compiled_hash="hash",
    )


def _rule(
    rule_id: str,
    rule_type: str,
    phase: str,
    *,
    conditions: list[RuleCondition] | None = None,
    action: RuleAction | None = None,
    ordered_values: list[str] | None = None,
) -> CompiledRule:
    return CompiledRule(
        rule=Rule(
            rule_id=rule_id,
            rule_type=rule_type,
            rule_name=rule_id,
            conditions=conditions or [],
            action=action,
            ordered_values=ordered_values or [],
            confidence=0.9,
        ),
        execution_phase=phase,
    )


def test_hard_filter_rejects_and_records_trace() -> None:
    engine = RuleExecutionEngine()
    rule = _rule(
        "filter_missing",
        "HARD_FILTER",
        "HARD_FILTER",
        conditions=[RuleCondition(field="missing_rate", operator="GT", value=0.4)],
        action=RuleAction(action_type="REJECT", value=0.4),
    )
    result = engine.execute([_candidate("v1", missing_rate=0.5)], _compiled(rule))
    decision = result.decisions[0]
    assert decision.status == "REJECTED"
    assert "filter_missing" in decision.matched_rule_ids
    assert any(event.stage == "HARD_FILTER" and event.matched for event in decision.execution_trace)


def test_hard_filter_null_marks_review() -> None:
    engine = RuleExecutionEngine()
    candidate = _candidate("v1")
    candidate.missing_rate = None
    rule = _rule(
        "filter_missing",
        "HARD_FILTER",
        "HARD_FILTER",
        conditions=[RuleCondition(field="missing_rate", operator="GT", value=0.4)],
        action=RuleAction(action_type="REJECT"),
    )
    result = engine.execute([candidate], _compiled(rule))
    assert result.decisions[0].status == "NEEDS_REVIEW"


def test_review_gate_blocks_classification_review() -> None:
    engine = RuleExecutionEngine()
    candidate = _candidate("v1", classification_status="NEEDS_REVIEW")
    result = engine.execute([candidate], _compiled())
    assert result.decisions[0].status == "NEEDS_REVIEW"


def test_category_and_frequency_ranks_are_assigned() -> None:
    engine = RuleExecutionEngine()
    category_rule = _rule(
        "category",
        "CATEGORY_PRIORITY",
        "CATEGORY_PRIORITY",
        ordered_values=["PRICE", "INVENTORY"],
        action=RuleAction(action_type="PRIORITIZE"),
    )
    frequency_rule = _rule(
        "frequency",
        "FREQUENCY_PRIORITY",
        "FREQUENCY_PRIORITY",
        ordered_values=["DAILY", "MONTHLY"],
        action=RuleAction(action_type="PRIORITIZE"),
    )
    result = engine.execute(
        [
            _candidate("price", category="PRICE", frequency="daily"),
            _candidate("inventory", category="INVENTORY", frequency="monthly"),
        ],
        _compiled(category_rule, frequency_rule),
    )
    by_id = {item.variable_id: item for item in result.decisions}
    assert by_id["price"].category_rank == 1
    assert by_id["inventory"].category_rank == 2
    assert by_id["price"].frequency_rank == 1
    assert by_id["inventory"].frequency_rank == 2


def test_scoring_components_total_score() -> None:
    engine = RuleExecutionEngine()
    rule = _rule(
        "score",
        "SCORING",
        "SCORING",
        action=RuleAction(action_type="ADD_SCORE", score=10.0, field="user_preference_score"),
    )
    result = engine.execute([_candidate("v1")], _compiled(rule))
    assert result.decisions[0].total_score == 10.0


def test_deduplication_marks_duplicate_with_replacement() -> None:
    engine = RuleExecutionEngine()
    rule = _rule(
        "dedup",
        "DEDUPLICATION",
        "DEDUPLICATION",
        action=RuleAction(action_type="KEEP_TOP_N", keep_n=1, group_by=["comparison_group_key"]),
    )
    result = engine.execute(
        [_candidate("v1"), _candidate("v2")],
        _compiled(rule),
    )
    by_id = {item.variable_id: item for item in result.decisions}
    assert by_id["v1"].status == "SELECTED"
    assert by_id["v2"].status == "DUPLICATE"
    assert by_id["v2"].replacement_variable_id == "v1"


def test_top_n_marks_not_selected() -> None:
    engine = RuleExecutionEngine()
    rule = _rule(
        "top_n",
        "MAX_COUNT",
        "TOP_N_LIMIT",
        action=RuleAction(action_type="KEEP_TOP_N", max_count=2, max_count_scope="GLOBAL"),
    )
    result = engine.execute(
        [_candidate("v1"), _candidate("v2"), _candidate("v3")],
        _compiled(rule),
    )
    statuses = [item.status for item in result.decisions]
    assert statuses.count("SELECTED") == 2
    assert statuses.count("NOT_SELECTED") == 1


def test_execution_is_deterministic() -> None:
    candidates = [
        _candidate("v3", category="PRICE"),
        _candidate("v1", category="INVENTORY"),
        _candidate("v2", category="PRICE"),
    ]
    rule = _rule(
        "category",
        "CATEGORY_PRIORITY",
        "CATEGORY_PRIORITY",
        ordered_values=["PRICE", "INVENTORY"],
        action=RuleAction(action_type="PRIORITIZE"),
    )
    first = RuleExecutionEngine().execute(candidates, _compiled(rule))
    second = RuleExecutionEngine().execute(candidates, _compiled(rule))
    assert [item.variable_id for item in first.decisions] == [
        item.variable_id for item in second.decisions
    ]


def _persist_source_run(db_manager: DatabaseManager, sample_workbook: Path, run_id: str) -> None:
    result = run_inspection(sample_workbook, run_id=run_id)
    InspectionPersistenceService(db_manager).persist(
        result,
        request_record=RequestRecord(
            run_id=run_id,
            input_path=str(sample_workbook),
            file_hash=result.workbook_profile.file_hash,
            cli_args={},
        ),
        artifacts_dir=Path("artifacts"),
        run_id=run_id,
    )


def test_selection_service_end_to_end_mock(
    db_manager: DatabaseManager,
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    run_id = "run-select-e2e"
    _persist_source_run(db_manager, sample_workbook, run_id)
    taxonomy = "taxonomy_v1"
    class_settings = LLMSettings(llm_provider="mock", llm_taxonomy_version=taxonomy)
    BatchClassificationService(db_manager, settings=class_settings).classify_run(
        run_id,
        provider="mock",
        limit=10,
        artifacts_dir=tmp_path / "class_artifacts",
    )
    rules_text = """价格 > 价差 > 库存 > 产量 > 进口 > 出口
缺失率超过40%的变量删除
同一指标只保留一个
最终最多保留5个变量
"""
    rules_path = tmp_path / "rules.txt"
    rules_path.write_text(rules_text, encoding="utf-8")
    rule_settings = LLMSettings(llm_provider="mock", llm_taxonomy_version=taxonomy)
    RuleParserService(db_manager, settings=rule_settings).compile_rules(
        rules_path,
        provider="mock",
        name="e2e_rules",
        version="1",
        artifacts_dir=tmp_path / "rule_artifacts",
    )
    summary = VariableSelectionService(db_manager).select(
        run_id,
        rule_set_name="e2e_rules",
        rule_version="1",
        allow_validated_rules=True,
        artifacts_dir=tmp_path / "selection_artifacts",
    )
    assert summary.total_variables > 0
    assert summary.selected_count + summary.rejected_count + summary.needs_review_count + summary.not_selected_count + summary.duplicate_count == summary.total_variables
    assert (tmp_path / "selection_artifacts" / summary.selection_run_id / "selection" / "selection_summary.json").exists()


def test_selection_accepts_partial_classification(
    db_manager: DatabaseManager,
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    run_id = "run-select-partial"
    _persist_source_run(db_manager, sample_workbook, run_id)
    taxonomy = "taxonomy_v1"
    BatchClassificationService(
        db_manager,
        settings=LLMSettings(llm_provider="mock", llm_taxonomy_version=taxonomy),
    ).classify_run(
        run_id,
        provider="mock",
        limit=1,
        artifacts_dir=tmp_path / "class_artifacts",
    )
    rules_path = tmp_path / "rules.txt"
    rules_path.write_text("浠锋牸 > 搴撳瓨 > 浜ч噺\n", encoding="utf-8")
    RuleParserService(
        db_manager,
        settings=LLMSettings(llm_provider="mock", llm_taxonomy_version=taxonomy),
    ).compile_rules(
        rules_path,
        provider="mock",
        name="partial_rules",
        version="1",
        artifacts_dir=tmp_path / "rule_artifacts",
    )
    summary = VariableSelectionService(db_manager).select(
        run_id,
        rule_set_name="partial_rules",
        rule_version="1",
        allow_validated_rules=True,
        artifacts_dir=tmp_path / "selection_artifacts",
    )
    assert summary.total_variables > 1
    assert summary.failed_count + summary.needs_review_count > 0
    assert summary.status == "REVIEW_REQUIRED"
    assert any("UNCLASSIFIED" in reason for reason in summary.warnings)
