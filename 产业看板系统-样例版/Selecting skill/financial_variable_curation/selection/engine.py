from __future__ import annotations

from collections import defaultdict
from typing import Any

from financial_variable_curation.rule_workflow.constants import EXECUTION_PHASES
from financial_variable_curation.rule_workflow.models import (
    CompiledRule,
    CompiledRuleSetOutput,
    Rule,
)
from financial_variable_curation.selection.models import (
    CandidateVariable,
    ExecutionTraceEvent,
    ScoreComponents,
    SelectionDecision,
    SelectionExecutionResult,
    StageSummary,
)


STATUS_PRIORITY = {
    "FAILED": 0,
    "NEEDS_REVIEW": 1,
    "REJECTED": 2,
    "DUPLICATE": 3,
    "NOT_SELECTED": 4,
    "SELECTED": 5,
}

SCORE_COMPONENT_FIELDS = {
    "category_score",
    "frequency_score",
    "quality_score",
    "source_score",
    "recency_score",
    "coverage_score",
    "user_preference_score",
    "redundancy_penalty",
}


class RuleExecutionEngine:
    def execute(
        self,
        candidates: list[CandidateVariable],
        compiled: CompiledRuleSetOutput,
    ) -> SelectionExecutionResult:
        decisions = [
            SelectionDecision(candidate=candidate, status="PROCESSED")
            for candidate in candidates
        ]
        by_phase: dict[str, list[CompiledRule]] = defaultdict(list)
        for compiled_rule in compiled.compiled_rules:
            by_phase[compiled_rule.execution_phase].append(compiled_rule)

        stage_summaries: list[StageSummary] = []
        for stage in [*EXECUTION_PHASES, "FINAL_STATUS"]:
            rules = by_phase.get(stage, [])
            if stage == "FINAL_STATUS":
                self._final_status(decisions)
                stage_summaries.append(
                    StageSummary(stage=stage, status="COMPLETED", executed_rule_count=len(rules))
                )
                continue
            if stage == "HARD_FILTER":
                matched = self._hard_filter(decisions, rules)
            elif stage == "REVIEW_GATE":
                matched = self._review_gate(decisions, rules)
            elif stage in {"CATEGORY_PRIORITY", "SUBCATEGORY_PRIORITY", "FREQUENCY_PRIORITY", "SOURCE_PRIORITY"}:
                matched = self._priority(decisions, rules, stage)
            elif stage == "QUALITY_SORT":
                matched = self._quality_sort(decisions, rules)
            elif stage == "SCORING":
                matched = self._scoring(decisions, rules)
            elif stage == "DEDUPLICATION":
                matched = self._deduplication(decisions, rules)
            elif stage == "TOP_N_LIMIT":
                matched = self._top_n(decisions, rules)
            elif stage == "VALIDATION":
                matched = self._validation(decisions, rules)
            else:
                matched = 0
            if rules:
                stage_summaries.append(
                    StageSummary(
                        stage=stage,
                        status="COMPLETED",
                        executed_rule_count=len(rules),
                        matched_rule_count=matched,
                    )
                )
            else:
                stage_summaries.append(
                    StageSummary(
                        stage=stage,
                        status="SKIPPED",
                        reason="NO_APPLICABLE_RULES",
                        executed_rule_count=0,
                    )
                )
        self._sort_decisions(decisions)
        self._assign_ranks(decisions)
        return SelectionExecutionResult(
            decisions=decisions,
            stage_summaries=stage_summaries,
        )

    @staticmethod
    def _validation(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        for decision in decisions:
            for compiled_rule in rules:
                matched = bool(compiled_rule.dependency_rule_ids)
                decision.execution_trace.append(
                    ExecutionTraceEvent(
                        stage="VALIDATION",
                        rule_id=compiled_rule.rule.rule_id,
                        matched=matched,
                    )
                )
        return 0

    @staticmethod
    def _hard_filter(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        matched_count = 0
        for decision in decisions:
            for compiled_rule in rules:
                rule = compiled_rule.rule
                if not rule.conditions:
                    continue
                all_matched = True
                for condition in rule.conditions:
                    value = _field_value(decision.candidate, condition.field)
                    if value is None:
                        all_matched = False
                        decision.execution_trace.append(
                            ExecutionTraceEvent(
                                stage="HARD_FILTER",
                                rule_id=rule.rule_id,
                                matched=False,
                                input_value=None,
                                reason="NULL_FIELD_MARKED_REVIEW",
                            )
                        )
                        if decision.status not in {"FAILED", "REJECTED"}:
                            decision.status = "NEEDS_REVIEW"
                            decision.primary_reason_code = "NULL_FIELD"
                            decision.primary_reason_text = (
                                f"Field {condition.field} is null and no null_policy was provided."
                            )
                        break
                    if not _condition_matches(value, condition):
                        all_matched = False
                        decision.execution_trace.append(
                            ExecutionTraceEvent(
                                stage="HARD_FILTER",
                                rule_id=rule.rule_id,
                                matched=False,
                                input_value=value,
                            )
                        )
                        break
                if all_matched:
                    matched_count += 1
                    action = rule.action.action_type if rule.action else "REJECT"
                    decision.status = "REJECTED" if action == "REJECT" else decision.status
                    decision.primary_reason_code = _reason_code(rule)
                    decision.primary_reason_text = rule.description or rule.rule_name
                    decision.matched_rule_ids.append(rule.rule_id)
                    decision.execution_trace.append(
                        ExecutionTraceEvent(
                            stage="HARD_FILTER",
                            rule_id=rule.rule_id,
                            matched=True,
                            action=action,
                            reason=decision.primary_reason_text,
                        )
                    )
        return matched_count

    @staticmethod
    def _review_gate(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        matched_count = 0
        for decision in decisions:
            candidate = decision.candidate
            reasons: list[str] = []
            if candidate.classification_status == "FAILED":
                decision.status = "FAILED"
                reasons.append("CLASSIFICATION_FAILED")
            if candidate.classification_status == "NEEDS_REVIEW":
                decision.status = "NEEDS_REVIEW"
                reasons.append("CLASSIFICATION_NEEDS_REVIEW")
            if candidate.category_level_1 == "UNKNOWN":
                decision.status = "NEEDS_REVIEW"
                reasons.append("UNKNOWN_CATEGORY")
            if not candidate.comparison_group_key:
                decision.status = "NEEDS_REVIEW"
                reasons.append("COMPARISON_GROUP_MISSING")
            if candidate.has_unresolved_review:
                decision.status = "NEEDS_REVIEW"
                reasons.append("UNRESOLVED_REVIEW")
            for compiled_rule in rules:
                rule = compiled_rule.rule
                if _rule_matches(decision.candidate, rule):
                    matched_count += 1
                    decision.status = "NEEDS_REVIEW"
                    decision.matched_rule_ids.append(rule.rule_id)
                    reasons.append(rule.rule_id)
                    decision.execution_trace.append(
                        ExecutionTraceEvent(
                            stage="REVIEW_GATE",
                            rule_id=rule.rule_id,
                            matched=True,
                            reason=rule.description or rule.rule_name,
                        )
                    )
            if reasons and decision.primary_reason_code is None:
                decision.primary_reason_code = reasons[0]
                decision.primary_reason_text = "; ".join(reasons)
        return matched_count

    @staticmethod
    def _priority(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
        stage: str,
    ) -> int:
        field_map = {
            "CATEGORY_PRIORITY": "category_level_1",
            "SUBCATEGORY_PRIORITY": "category_level_2",
            "FREQUENCY_PRIORITY": "detected_frequency",
            "SOURCE_PRIORITY": "source_type",
        }
        field = field_map[stage]
        order: list[str] = []
        for compiled_rule in rules:
            for value in compiled_rule.rule.ordered_values:
                if value not in order:
                    order.append(value)
        rank_map = {value: index + 1 for index, value in enumerate(order)}
        for decision in decisions:
            value = str(getattr(decision.candidate, field) or "UNKNOWN").upper()
            rank = rank_map.get(value, len(order) + 1000)
            if stage == "CATEGORY_PRIORITY":
                decision.category_rank = rank
            elif stage == "SUBCATEGORY_PRIORITY":
                decision.subcategory_rank = rank
            elif stage == "FREQUENCY_PRIORITY":
                decision.frequency_rank = rank
            elif stage == "SOURCE_PRIORITY":
                decision.source_rank = rank
            decision.execution_trace.append(
                ExecutionTraceEvent(
                    stage=stage,
                    rule_id=rules[0].rule.rule_id if rules else None,
                    matched=True,
                    assigned_rank=rank,
                    input_value=value,
                )
            )
        return len(rules)

    @staticmethod
    def _quality_sort(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        for compiled_rule in rules:
            rule = compiled_rule.rule
            field = rule.action.field if rule.action and rule.action.field else "quality_score"
            direction = rule.action.direction if rule.action and rule.action.direction else "desc"
            decisions.sort(
                key=lambda decision: _sort_value(_field_value(decision.candidate, field), direction),
                reverse=direction == "desc",
            )
            for decision in decisions:
                decision.execution_trace.append(
                    ExecutionTraceEvent(
                        stage="QUALITY_SORT",
                        rule_id=rule.rule_id,
                        matched=True,
                        input_value=_field_value(decision.candidate, field),
                    )
                )
        return len(rules)

    @staticmethod
    def _scoring(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        matched_count = 0
        for decision in decisions:
            for compiled_rule in rules:
                rule = compiled_rule.rule
                if not _rule_matches(decision.candidate, rule):
                    continue
                matched_count += 1
                action = rule.action
                if action is None or action.action_type not in {"ADD_SCORE", "SUBTRACT_SCORE"}:
                    continue
                component = action.field if action.field in SCORE_COMPONENT_FIELDS else "user_preference_score"
                delta = float(action.score or 0)
                if action.action_type == "SUBTRACT_SCORE":
                    delta = -delta
                setattr(decision.scores, component, getattr(decision.scores, component) + delta)
                decision.matched_rule_ids.append(rule.rule_id)
                decision.execution_trace.append(
                    ExecutionTraceEvent(
                        stage="SCORING",
                        rule_id=rule.rule_id,
                        matched=True,
                        action=action.action_type,
                        input_value=delta,
                    )
                )
        return matched_count

    @staticmethod
    def _deduplication(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        matched_count = 0
        for compiled_rule in rules:
            rule = compiled_rule.rule
            action = rule.action
            if action is None:
                continue
            group_fields = action.group_by or ["comparison_group_key"]
            groups: dict[tuple[str, ...], list[SelectionDecision]] = defaultdict(list)
            for decision in decisions:
                if decision.status in {"REJECTED", "FAILED", "NOT_SELECTED"}:
                    continue
                key = tuple(
                    str(_field_value(decision.candidate, field) or "")
                    for field in group_fields
                )
                if any(not item for item in key):
                    continue
                groups[key].append(decision)
            for members in groups.values():
                keep_n = action.keep_n or action.max_count or 1
                ranked = sorted(
                    members,
                    key=lambda decision: (
                        -decision.total_score,
                        decision.category_rank or 9999,
                        decision.frequency_rank or 9999,
                        decision.candidate.missing_rate,
                        decision.variable_id,
                    ),
                )
                for index, decision in enumerate(ranked):
                    decision.group_rank = index + 1
                    decision.comparison_group_key = "|".join(
                        str(_field_value(decision.candidate, field) or "") for field in group_fields
                    )
                    decision.execution_trace.append(
                        ExecutionTraceEvent(
                            stage="DEDUPLICATION",
                            rule_id=rule.rule_id,
                            matched=True,
                            group_rank=index + 1,
                            action="KEEP" if index < keep_n else "DUPLICATE",
                        )
                    )
                    if index >= keep_n:
                        matched_count += 1
                        decision.status = "DUPLICATE"
                        decision.replacement_variable_id = ranked[0].variable_id
                        decision.scores.redundancy_penalty = -10.0
                        decision.primary_reason_code = "DUPLICATE_VARIABLE"
                        decision.primary_reason_text = (
                            f"Duplicate in comparison group; replacement is {ranked[0].variable_id}."
                        )
                        decision.matched_rule_ids.append(rule.rule_id)
        return matched_count

    @staticmethod
    def _top_n(
        decisions: list[SelectionDecision],
        rules: list[CompiledRule],
    ) -> int:
        matched_count = 0
        for compiled_rule in rules:
            rule = compiled_rule.rule
            action = rule.action
            if action is None or not action.max_count:
                continue
            scope = (action.max_count_scope or "GLOBAL").upper()
            eligible = [
                decision
                for decision in decisions
                if decision.status not in {"REJECTED", "FAILED", "NOT_SELECTED", "DUPLICATE"}
            ]
            if scope == "GLOBAL":
                groups = {"__global__": eligible}
            elif scope == "CATEGORY":
                groups = _group_by(eligible, lambda item: item.candidate.category_level_1)
            elif scope == "COMMODITY":
                groups = _group_by(eligible, lambda item: item.candidate.commodity or "UNKNOWN")
            elif scope == "COMPARISON_GROUP":
                groups = _group_by(eligible, lambda item: item.candidate.comparison_group_key or "UNKNOWN")
            elif scope == "INDUSTRY":
                groups = _group_by(eligible, lambda item: item.candidate.industry or "UNKNOWN")
            else:
                groups = {"__global__": eligible}
            for members in groups.values():
                ranked = sorted(
                    members,
                    key=lambda decision: (
                        -decision.total_score,
                        decision.category_rank or 9999,
                        decision.frequency_rank or 9999,
                        decision.candidate.missing_rate,
                        decision.variable_id,
                    ),
                )
                for decision in ranked[action.max_count :]:
                    matched_count += 1
                    decision.status = "NOT_SELECTED"
                    decision.primary_reason_code = "TOP_N_LIMIT"
                    decision.primary_reason_text = (
                        f"Exceeded {scope} TOP_N limit {action.max_count}."
                    )
                    decision.matched_rule_ids.append(rule.rule_id)
        return matched_count

    @staticmethod
    def _final_status(decisions: list[SelectionDecision]) -> None:
        for decision in decisions:
            candidate = decision.candidate
            if candidate.classification_status == "FAILED":
                decision.status = "FAILED"
            elif decision.status in {"PROCESSED", "UNPROCESSED"}:
                decision.status = "SELECTED"
                decision.primary_reason_code = decision.primary_reason_code or "NO_BLOCKING_RULE"
                decision.primary_reason_text = decision.primary_reason_text or "Selected by deterministic rules."

    @staticmethod
    def _sort_decisions(decisions: list[SelectionDecision]) -> None:
        decisions.sort(
            key=lambda decision: (
                STATUS_PRIORITY.get(decision.status, 99),
                -decision.total_score,
                decision.category_rank or 9999,
                decision.frequency_rank or 9999,
                decision.variable_id,
            )
        )

    @staticmethod
    def _assign_ranks(decisions: list[SelectionDecision]) -> None:
        for index, decision in enumerate(decisions, start=1):
            decision.overall_rank = index


def _field_value(candidate: CandidateVariable, field: str) -> Any:
    if field in {"country", "unit_standard", "unit_dimension", "is_outdated", "source_type"}:
        return getattr(candidate, field, None)
    if field in {"quality_score"}:
        return candidate.quality_score
    if field in {"classification_confidence"}:
        return candidate.classification_confidence
    return getattr(candidate, field, None)


def _condition_matches(value: Any, condition) -> bool:
    operator = condition.operator.upper()
    target = condition.value
    if operator == "IS_NULL":
        return value is None
    if operator == "IS_NOT_NULL":
        return value is not None
    if value is None:
        return False
    if operator in {"IN", "NOT_IN"}:
        items = [str(item).lower() for item in (target or [])]
        matched = str(value).lower() in items
        return matched if operator == "IN" else not matched
    if operator in {"CONTAINS", "NOT_CONTAINS"}:
        matched = str(target) in str(value)
        return matched if operator == "CONTAINS" else not matched
    try:
        left = float(value)
        right = float(target)
    except (TypeError, ValueError):
        left_str = str(value).lower()
        right_str = str(target).lower()
        if operator == "EQ":
            return left_str == right_str
        if operator == "NE":
            return left_str != right_str
        return False
    if operator == "EQ":
        return left == right
    if operator == "NE":
        return left != right
    if operator == "GT":
        return left > right
    if operator == "GTE":
        return left >= right
    if operator == "LT":
        return left < right
    if operator == "LTE":
        return left <= right
    return False


def _rule_matches(candidate: CandidateVariable, rule: Rule) -> bool:
    if not rule.conditions:
        return True
    return all(_condition_matches(_field_value(candidate, condition.field), condition) for condition in rule.conditions)


def _reason_code(rule: Rule) -> str:
    if rule.conditions:
        return f"{rule.conditions[0].field}_{rule.conditions[0].operator}"
    return rule.rule_type


def _sort_value(value: Any, direction: str) -> Any:
    if value is None:
        return -999999 if direction == "desc" else 999999
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _group_by(items: list[SelectionDecision], key):
    groups: dict[str, list[SelectionDecision]] = defaultdict(list)
    for item in items:
        groups[str(key(item))].append(item)
    return groups
