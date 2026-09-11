from __future__ import annotations

import hashlib
from itertools import combinations

from financial_variable_curation.rule_workflow.models import (
    Rule,
    RuleConflict,
    RuleConflictReport,
    RuleSetDocument,
)


class RuleConflictDetector:
    def detect(self, document: RuleSetDocument) -> RuleConflictReport:
        rules = document.rules
        by_id = {rule.rule_id: rule for rule in rules}
        conflicts: list[RuleConflict] = []
        self._detect_order_conflicts(rules, conflicts)
        self._detect_filter_conflicts(rules, conflicts)
        self._detect_impossible_range_conflicts(rules, conflicts)
        self._detect_deduplication_conflicts(rules, conflicts)
        self._detect_scope_conflicts(rules, conflicts)
        return RuleConflictReport(conflicts=conflicts)

    @staticmethod
    def _detect_order_conflicts(rules: list[Rule], conflicts: list[RuleConflict]) -> None:
        priority_rules = [
            rule
            for rule in rules
            if rule.rule_type
            in {"CATEGORY_PRIORITY", "SUBCATEGORY_PRIORITY", "FREQUENCY_PRIORITY", "SOURCE_PRIORITY"}
        ]
        for left, right in combinations(priority_rules, 2):
            for first, second in combinations(left.ordered_values, 2):
                if first not in right.ordered_values or second not in right.ordered_values:
                    continue
                left_order = left.ordered_values.index(first) < left.ordered_values.index(second)
                right_order = right.ordered_values.index(first) < right.ordered_values.index(second)
                if left_order != right_order:
                    conflicts.append(
                        RuleConflict(
                            conflict_id=_conflict_id(left.rule_id, right.rule_id, "ORDER_CONFLICT"),
                            involved_rule_ids=[left.rule_id, right.rule_id],
                            conflict_type="ORDER_CONFLICT",
                            severity="ERROR",
                            description=(
                                f"Priority rules disagree on order of {first} and {second}."
                            ),
                            suggested_resolution="Make the strict ordering consistent or remove one rule.",
                            blocks_compilation=False,
                        )
                    )

    @staticmethod
    def _detect_filter_conflicts(rules: list[Rule], conflicts: list[RuleConflict]) -> None:
        filters = [rule for rule in rules if rule.rule_type == "HARD_FILTER"]
        for left, right in combinations(filters, 2):
            if not left.conditions or not right.conditions:
                continue
            left_condition = left.conditions[0]
            right_condition = right.conditions[0]
            if left_condition.field != right_condition.field:
                continue
            left_action = left.action.action_type if left.action else "NO_ACTION"
            right_action = right.action.action_type if right.action else "NO_ACTION"
            if {left_action, right_action} == {"REJECT", "KEEP"} and _thresholds_overlap(
                left_condition, right_condition
            ):
                conflicts.append(
                    RuleConflict(
                        conflict_id=_conflict_id(left.rule_id, right.rule_id, "FILTER_CONFLICT"),
                        involved_rule_ids=[left.rule_id, right.rule_id],
                        conflict_type="FILTER_CONFLICT",
                        severity="ERROR",
                        description=(
                            f"Filter rules overlap for {left_condition.field}: "
                            f"one rejects and the other keeps the same values."
                        ),
                        suggested_resolution="Tighten the KEEP scope or remove one filter.",
                        blocks_compilation=False,
                    )
                )

    @staticmethod
    def _detect_deduplication_conflicts(rules: list[Rule], conflicts: list[RuleConflict]) -> None:
        dedup_rules = [rule for rule in rules if rule.rule_type == "DEDUPLICATION"]
        for left, right in combinations(dedup_rules, 2):
            left_group = tuple(left.action.group_by if left.action else [])
            right_group = tuple(right.action.group_by if right.action else [])
            if left_group != right_group or not left_group:
                continue
            left_n = left.action.keep_n if left.action else None
            right_n = right.action.keep_n if right.action else None
            if left_n is not None and right_n is not None and left_n != right_n:
                conflicts.append(
                    RuleConflict(
                        conflict_id=_conflict_id(left.rule_id, right.rule_id, "DEDUP_CONFLICT"),
                        involved_rule_ids=[left.rule_id, right.rule_id],
                        conflict_type="DEDUP_CONFLICT",
                        severity="ERROR",
                        description=(
                            "Deduplication rules for the same group disagree on how many variables to keep."
                        ),
                        suggested_resolution="Use one explicit keep_n for the group.",
                        blocks_compilation=False,
                    )
                )

    @staticmethod
    def _detect_impossible_range_conflicts(
        rules: list[Rule], conflicts: list[RuleConflict]
    ) -> None:
        filters = [rule for rule in rules if rule.rule_type == "HARD_FILTER"]
        for left, right in combinations(filters, 2):
            if not left.conditions or not right.conditions:
                continue
            left_condition = left.conditions[0]
            right_condition = right.conditions[0]
            if left_condition.field != right_condition.field:
                continue
            try:
                left_value = float(left_condition.value)
                right_value = float(right_condition.value)
            except (TypeError, ValueError):
                continue
            if {left_condition.operator, right_condition.operator} != {"GT", "LT"}:
                continue
            gt_rule = left if left_condition.operator == "GT" else right
            lt_rule = left if left_condition.operator == "LT" else right
            gt_value = left_value if left_condition.operator == "GT" else right_value
            lt_value = right_value if left_condition.operator == "GT" else left_value
            if gt_value >= lt_value:
                conflicts.append(
                    RuleConflict(
                        conflict_id=_conflict_id(
                            left.rule_id, right.rule_id, "IMPOSSIBLE_RANGE"
                        ),
                        involved_rule_ids=[left.rule_id, right.rule_id],
                        conflict_type="IMPOSSIBLE_RANGE",
                        severity="FATAL",
                        description=(
                            f"Filters define an impossible range for {left_condition.field}."
                        ),
                        suggested_resolution="Remove or adjust one of the contradictory thresholds.",
                        blocks_compilation=True,
                    )
                )

    @staticmethod
    def _detect_scope_conflicts(rules: list[Rule], conflicts: list[RuleConflict]) -> None:
        global_rules = [rule for rule in rules if _is_global(rule)]
        scoped_rules = [rule for rule in rules if not _is_global(rule)]
        for global_rule in global_rules:
            for scoped_rule in scoped_rules:
                if global_rule.rule_type != scoped_rule.rule_type:
                    continue
                shared = set(global_rule.ordered_values) & set(scoped_rule.ordered_values)
                if shared and global_rule.ordered_values != scoped_rule.ordered_values:
                    conflicts.append(
                        RuleConflict(
                            conflict_id=_conflict_id(
                                global_rule.rule_id, scoped_rule.rule_id, "SCOPE_CONFLICT"
                            ),
                            involved_rule_ids=[global_rule.rule_id, scoped_rule.rule_id],
                            conflict_type="SCOPE_CONFLICT",
                            severity="WARNING",
                            description=(
                                "A scoped rule changes the global priority; resolution priority is implicit."
                            ),
                            suggested_resolution="Declare whether scoped rules override global rules.",
                            blocks_compilation=False,
                        )
                    )


def _is_global(rule: Rule) -> bool:
    scope = rule.scope
    return not any(
        [
            scope.industries,
            scope.commodities,
            scope.categories,
            scope.regions,
            scope.markets,
            scope.comparison_group_keys,
            scope.statistical_scopes,
        ]
    )


def _thresholds_overlap(left, right) -> bool:
    try:
        left_value = float(left.value)
        right_value = float(right.value)
    except (TypeError, ValueError):
        return False
    if left.operator == "GT" and right.operator == "GT":
        return min(left_value, right_value) >= max(left_value, right_value) or True
    if left.operator == "LT" and right.operator == "LT":
        return min(left_value, right_value) <= max(left_value, right_value) or True
    if left.operator == "GTE" and right.operator == "GT":
        return left_value <= right_value
    return False


def _conflict_id(left: str, right: str, conflict_type: str) -> str:
    raw = f"{left}|{right}|{conflict_type}".encode("utf-8")
    return f"conflict_{hashlib.sha256(raw).hexdigest()[:12]}"
