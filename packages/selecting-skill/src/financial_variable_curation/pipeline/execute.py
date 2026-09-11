from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from financial_variable_curation.models.artifacts import SelectionAuditReport
from financial_variable_curation.models.enums import VariableStatus
from financial_variable_curation.models.rules import CompiledRuleSet, Condition, HardFilterRule
from financial_variable_curation.models.variable import VariableProfile


class SelectionResult(BaseModel):
    all_variables: list[VariableProfile] = Field(default_factory=list)
    selected_variables: list[VariableProfile] = Field(default_factory=list)
    rejected_variables: list[VariableProfile] = Field(default_factory=list)
    review_variables: list[VariableProfile] = Field(default_factory=list)
    audit: SelectionAuditReport


def _field_value(profile: VariableProfile, field: str) -> Any:
    if field == "category":
        return profile.classification.category
    if field == "subcategory":
        return profile.classification.subcategory
    if field == "frequency":
        return profile.inferred_frequency or "UNKNOWN"
    if field == "source":
        return profile.source or "UNKNOWN"
    if field == "data_type":
        return profile.data_type.value
    if field == "status":
        return profile.status.value
    return getattr(profile, field, None)


def _condition_matches(profile: VariableProfile, condition: Condition) -> bool:
    value = _field_value(profile, condition.field)
    target = condition.value
    operator = condition.operator.lower()

    if operator == "is_true":
        return bool(value)
    if operator == "is_false":
        return not bool(value)
    if operator in {"contains", "not_contains"}:
        matched = str(target) in str(value)
        return matched if operator == "contains" else not matched
    if operator in {"in", "not_in"}:
        matched = value in (target or [])
        return matched if operator == "in" else not matched

    try:
        left = float(value)
        right = float(target)
    except (TypeError, ValueError):
        left_str = str(value).lower()
        right_str = str(target).lower()
        if operator == "eq":
            return left_str == right_str
        if operator == "ne":
            return left_str != right_str
        return False

    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    if operator == "eq":
        return left == right
    if operator == "ne":
        return left != right
    return False


def _hard_filter_matches(profile: VariableProfile, rule: HardFilterRule) -> bool:
    return _condition_matches(
        profile,
        Condition(field=rule.field, operator=rule.operator, value=rule.value),
    )


def _order_index(value: str, order_map: dict[str, int]) -> int:
    if not order_map:
        return 0
    return order_map.get(value, len(order_map) + 1000)


class DeterministicRuleEngine:
    def execute(self, profiles: list[VariableProfile], compiled: CompiledRuleSet) -> list[VariableProfile]:
        decisions = [profile.model_copy(deep=True) for profile in profiles]
        self._apply_hard_filters(decisions, compiled)
        self._apply_exceptions(decisions, compiled)
        self._apply_review_rules(decisions, compiled)
        self._apply_scoring(decisions, compiled)
        self._apply_priority_sort(decisions, compiled)
        self._apply_custom_sorting(decisions, compiled)
        self._apply_deduplication(decisions, compiled)
        self._apply_conflict_resolution(decisions, compiled)
        self._apply_max_variable_count(decisions, compiled)
        self._apply_default_include(decisions)
        self._assign_ranks(decisions)
        return decisions

    @staticmethod
    def _apply_hard_filters(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        for profile in decisions:
            if profile.status in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                continue
            for rule in compiled.hard_filter_rules:
                if not _hard_filter_matches(profile, rule):
                    continue
                profile.status = VariableStatus(rule.action)
                profile.status_reason = rule.reason or f"Hard filter matched: {rule.field} {rule.operator} {rule.value}"
                if profile.status in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                    break

    @staticmethod
    def _apply_exceptions(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        for profile in decisions:
            for rule in compiled.exception_rules:
                if all(_condition_matches(profile, condition) for condition in rule.when):
                    profile.status = VariableStatus(rule.action)
                    profile.status_reason = rule.reason or rule.description

    @staticmethod
    def _apply_review_rules(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        for profile in decisions:
            if profile.status in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                continue
            for rule in compiled.review_rules:
                if _condition_matches(profile, rule.condition):
                    profile.status = VariableStatus.NEEDS_REVIEW
                    profile.status_reason = rule.reason
                    break

    @staticmethod
    def _apply_scoring(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        if not compiled.scoring_rules:
            return
        for rule in compiled.scoring_rules:
            if rule.transform in {"rank_asc", "rank_desc"}:
                ordered = sorted(decisions, key=lambda profile: _numeric_or_zero(_field_value(profile, rule.field)))
                total = len(ordered)
                for rank, profile in enumerate(ordered):
                    normalized = rank / max(total - 1, 1)
                    profile.score += (normalized if rule.transform == "rank_asc" else 1.0 - normalized) * rule.weight
                continue
            for profile in decisions:
                raw = _numeric_or_zero(_field_value(profile, rule.field))
                if rule.transform == "inverse":
                    raw = 1.0 - min(max(raw, 0.0), 1.0)
                elif rule.transform == "normalize":
                    raw = min(max(raw / 100.0, 0.0), 1.0)
                profile.score += raw * rule.weight

    @staticmethod
    def _apply_priority_sort(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        category_order = {value: index for index, value in enumerate(compiled.effective_category_order)}
        subcategory_order = {value: index for index, value in enumerate(compiled.effective_subcategory_order)}
        frequency_order = {value: index for index, value in enumerate(compiled.effective_frequency_order)}
        source_order = {value: index for index, value in enumerate(compiled.effective_source_order)}

        decisions.sort(
            key=lambda profile: (
                _order_index(profile.classification.category, category_order),
                _order_index(profile.classification.subcategory, subcategory_order),
                _order_index(profile.inferred_frequency or "UNKNOWN", frequency_order),
                _order_index(profile.source or "UNKNOWN", source_order),
                -profile.quality_score,
                -profile.time_coverage,
                profile.missing_rate,
                profile.column_name.lower(),
            )
        )

    @staticmethod
    def _apply_custom_sorting(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        for rule in sorted(compiled.sorting_rules, key=lambda item: item.priority):
            decisions.sort(
                key=lambda profile: _sortable_value(_field_value(profile, rule.field)),
                reverse=rule.direction == "desc",
            )

    @staticmethod
    def _apply_deduplication(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        for rule in compiled.deduplication_rules:
            groups: dict[tuple[str, ...], list[VariableProfile]] = defaultdict(list)
            for profile in decisions:
                if profile.status in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                    continue
                key = tuple(str(_field_value(profile, field)) for field in rule.group_by)
                profile.dedupe_group = "|".join(key)
                groups[key].append(profile)

            for members in groups.values():
                if len(members) < 2:
                    continue
                ambiguous = any(
                    profile.classification.needs_review or profile.classification.confidence < 0.95
                    for profile in members
                )
                if rule.method in {"none", "all"} and rule.max_per_group is None:
                    if rule.needs_review_on_ambiguous and ambiguous:
                        for profile in members:
                            if profile.status not in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                                profile.status = VariableStatus.NEEDS_REVIEW
                                profile.status_reason = "Similar variables could not be confirmed as economically identical."
                    continue

                ranked = list(members)
                if rule.method in {"priority", "score"}:
                    if rule.method == "score":
                        ranked.sort(key=lambda profile: -profile.score)
                    elif rule.prefer_fields:
                        ranked.sort(key=lambda profile: tuple(_prefer_value(_field_value(profile, field), field) for field in rule.prefer_fields))
                    else:
                        ranked = list(members)
                keep_count = rule.max_per_group if rule.max_per_group is not None else 1
                for profile in ranked[keep_count:]:
                    if rule.needs_review_on_ambiguous and ambiguous:
                        profile.status = VariableStatus.NEEDS_REVIEW
                        profile.status_reason = "Duplicate-like variable retained for review because semantics are uncertain."
                    else:
                        profile.status = VariableStatus.EXCLUDE
                        profile.status_reason = "Deduplication rule excluded this variable."

    @staticmethod
    def _apply_conflict_resolution(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        if not compiled.conflict_resolution_rules:
            return
        if len(compiled.deduplication_rules) < 2:
            return
        for rule in compiled.conflict_resolution_rules:
            if rule.action == "ABORT":
                raise ValueError("Conflict resolution rule requested abort.")
            if rule.action == "NEEDS_REVIEW":
                for profile in decisions:
                    if profile.status not in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                        profile.status = VariableStatus.NEEDS_REVIEW
                        profile.status_reason = rule.reason or "Conflicting deduplication rules require review."

    @staticmethod
    def _apply_max_variable_count(decisions: list[VariableProfile], compiled: CompiledRuleSet) -> None:
        if compiled.max_variable_count is None:
            return
        candidates = [
            profile
            for profile in decisions
            if profile.status not in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}
        ]
        for profile in candidates[compiled.max_variable_count:]:
            profile.status = VariableStatus.EXCLUDE
            profile.status_reason = f"Exceeded max_variable_count={compiled.max_variable_count}."

    @staticmethod
    def _apply_default_include(decisions: list[VariableProfile]) -> None:
        for profile in decisions:
            if profile.status == VariableStatus.UNPROCESSED:
                profile.status = VariableStatus.INCLUDE
                profile.status_reason = "No rule excluded or flagged this variable for review."

    @staticmethod
    def _assign_ranks(decisions: list[VariableProfile]) -> None:
        rank = 0
        for profile in decisions:
            if profile.status in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}:
                continue
            rank += 1
            profile.rank = rank


def _numeric_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _sortable_value(value: Any) -> Any:
    if value is None:
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _prefer_value(value: Any, field: str) -> Any:
    numeric = _numeric_or_zero(value)
    if field in {"missing_rate"}:
        return numeric
    if field in {"quality_score", "time_coverage", "non_null_count", "date_parse_rate"}:
        return -numeric
    return str(value)


def build_selection_result(
    run_id: str,
    decisions: list[VariableProfile],
    compiled: CompiledRuleSet,
    output_path: str | Path | None = None,
) -> SelectionResult:
    selected = [profile for profile in decisions if profile.status == VariableStatus.INCLUDE]
    rejected = [
        profile
        for profile in decisions
        if profile.status in {VariableStatus.EXCLUDE, VariableStatus.REJECTED}
    ]
    review = [profile for profile in decisions if profile.status == VariableStatus.NEEDS_REVIEW]
    audit = SelectionAuditReport(
        run_id=run_id,
        rule_name=compiled.name,
        rule_version=compiled.version,
        rule_source=compiled.source.value,
        rule_status=compiled.status.value,
        production_ready=compiled.production_ready,
        rules_hash=compiled.rules_hash,
        prompt_version=compiled.prompt_version,
        total_variables=len(decisions),
        selected_count=len(selected),
        rejected_count=len(rejected),
        review_count=len(review),
        output_path=str(Path(output_path).resolve()) if output_path else None,
        engine_notes=_engine_notes(compiled),
    )
    return SelectionResult(
        all_variables=decisions,
        selected_variables=selected,
        rejected_variables=rejected,
        review_variables=review,
        audit=audit,
    )


def _engine_notes(compiled: CompiledRuleSet) -> list[str]:
    notes: list[str] = []
    if not compiled.category_priorities:
        notes.append("No category priorities provided; category order preserved from input.")
    if not compiled.frequency_priorities:
        notes.append("No frequency priorities provided; frequency does not affect selection.")
    if not compiled.source_priorities:
        notes.append("No source priorities provided; source does not affect selection.")
    if compiled.max_variable_count is None:
        notes.append("No max_variable_count provided; variable count is not limited.")
    return notes
