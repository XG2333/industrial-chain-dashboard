from __future__ import annotations

from typing import Any

from financial_variable_curation.models.enums import RuleSetStatus, RuleSource
from financial_variable_curation.models.rules import (
    Condition,
    RuleSet,
    RuleValidationResult,
)
from financial_variable_curation.utils.hashing import canonical_json, hash_model

ALLOWED_FIELDS = {
    "name",
    "missing_rate",
    "non_null_count",
    "unique_count",
    "constant",
    "all_empty",
    "numeric_rate",
    "date_parse_rate",
    "text_rate",
    "time_coverage",
    "quality_score",
    "data_type",
    "category",
    "subcategory",
    "frequency",
    "source",
    "status",
    "score",
    "rank",
    "dedupe_group",
}

ALLOWED_OPERATORS = {
    "gt",
    "gte",
    "lt",
    "lte",
    "eq",
    "ne",
    "in",
    "not_in",
    "contains",
    "not_contains",
    "is_true",
    "is_false",
}

ALLOWED_ACTIONS = {"INCLUDE", "EXCLUDE", "REJECTED", "NEEDS_REVIEW"}
ALLOWED_SORT_DIRECTIONS = {"asc", "desc"}
ALLOWED_SCORING_TRANSFORMS = {"raw", "inverse", "normalize", "rank_asc", "rank_desc"}
ALLOWED_DEDUP_METHODS = {"none", "all", "priority", "score"}
ALLOWED_DEDUP_KEEP = {"best", "all", "needs_review"}
ALLOWED_CONFLICT_ACTIONS = {"NEEDS_REVIEW", "USE_FIRST", "USE_LAST", "ABORT"}


def _condition_key(condition: Condition) -> tuple[str, str, str]:
    return condition.field, condition.operator, canonical_json(condition.value)


class RuleValidator:
    def validate(self, rule_set: RuleSet) -> RuleValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        self._validate_empty_and_status(rule_set, errors, warnings)
        self._validate_hash(rule_set, errors)
        self._validate_priorities(rule_set, errors)
        self._validate_conditions(rule_set, errors)
        self._validate_hard_filters(rule_set, errors)
        self._validate_sorting(rule_set, errors)
        self._validate_scoring(rule_set, errors)
        self._validate_deduplication(rule_set, errors)
        self._validate_exceptions(rule_set, errors)
        self._validate_conflict_rules(rule_set, errors)
        self._validate_review_rules(rule_set, errors)
        self._validate_duplicates(rule_set, errors)
        self._validate_max_count(rule_set, errors)

        return RuleValidationResult(valid=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _validate_empty_and_status(rule_set: RuleSet, errors: list[str], warnings: list[str]) -> None:
        if rule_set.is_empty():
            if rule_set.status == RuleSetStatus.ACTIVE:
                errors.append("Empty rule set cannot be ACTIVE.")
            if rule_set.production_ready:
                errors.append("Empty rule set cannot be marked production_ready=true.")
        if rule_set.source == RuleSource.DEFAULT_PLACEHOLDER and rule_set.production_ready:
            errors.append("DEFAULT_PLACEHOLDER rules must never be marked production_ready=true.")
        if rule_set.production_ready and rule_set.status not in {RuleSetStatus.VALIDATED, RuleSetStatus.ACTIVE}:
            warnings.append("production_ready=true is set before the rule set is VALIDATED or ACTIVE.")

    @staticmethod
    def _validate_hash(rule_set: RuleSet, errors: list[str]) -> None:
        if rule_set.rules_hash and rule_set.rules_hash != hash_model(rule_set):
            errors.append("rules_hash does not match the canonical rule payload.")

    @staticmethod
    def _validate_priorities(rule_set: RuleSet, errors: list[str]) -> None:
        for label, items in [
            ("category_priorities", rule_set.category_priorities),
            ("subcategory_priorities", rule_set.subcategory_priorities),
            ("frequency_priorities", rule_set.frequency_priorities),
            ("source_priorities", rule_set.source_priorities),
        ]:
            priorities_by_value: dict[str, set[int]] = {}
            for item in items:
                priorities_by_value.setdefault(item.value, set()).add(item.priority)
            conflicts = [value for value, priorities in priorities_by_value.items() if len(priorities) > 1]
            for value in conflicts:
                errors.append(f"{label} contains conflicting priorities for value '{value}'.")

    @staticmethod
    def _validate_condition(condition: Condition, errors: list[str], context: str) -> None:
        if condition.field not in ALLOWED_FIELDS:
            errors.append(f"{context}: unsupported field '{condition.field}'.")
        if condition.operator not in ALLOWED_OPERATORS:
            errors.append(f"{context}: unsupported operator '{condition.operator}'.")

    def _validate_conditions(self, rule_set: RuleSet, errors: list[str]) -> None:
        for rule in rule_set.exception_rules:
            for index, condition in enumerate(rule.when):
                self._validate_condition(condition, errors, f"exception_rules[{index}]")
        for rule in rule_set.review_rules:
            self._validate_condition(rule.condition, errors, "review_rules")

    @staticmethod
    def _validate_hard_filters(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.hard_filter_rules):
            if rule.field not in ALLOWED_FIELDS:
                errors.append(f"hard_filter_rules[{index}]: unsupported field '{rule.field}'.")
            if rule.operator not in ALLOWED_OPERATORS:
                errors.append(f"hard_filter_rules[{index}]: unsupported operator '{rule.operator}'.")
            if rule.action not in ALLOWED_ACTIONS:
                errors.append(f"hard_filter_rules[{index}]: unsupported action '{rule.action}'.")

    @staticmethod
    def _validate_sorting(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.sorting_rules):
            if rule.field not in ALLOWED_FIELDS:
                errors.append(f"sorting_rules[{index}]: unsupported field '{rule.field}'.")
            if rule.direction not in ALLOWED_SORT_DIRECTIONS:
                errors.append(f"sorting_rules[{index}]: unsupported direction '{rule.direction}'.")

    @staticmethod
    def _validate_scoring(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.scoring_rules):
            if rule.field not in ALLOWED_FIELDS:
                errors.append(f"scoring_rules[{index}]: unsupported field '{rule.field}'.")
            if rule.transform not in ALLOWED_SCORING_TRANSFORMS:
                errors.append(f"scoring_rules[{index}]: unsupported transform '{rule.transform}'.")
            if rule.weight == 0:
                errors.append(f"scoring_rules[{index}]: weight must not be zero.")

    @staticmethod
    def _validate_deduplication(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.deduplication_rules):
            if rule.method not in ALLOWED_DEDUP_METHODS:
                errors.append(f"deduplication_rules[{index}]: unsupported method '{rule.method}'.")
            if rule.keep not in ALLOWED_DEDUP_KEEP:
                errors.append(f"deduplication_rules[{index}]: unsupported keep '{rule.keep}'.")
            for field in [*rule.group_by, *rule.prefer_fields]:
                if field not in ALLOWED_FIELDS:
                    errors.append(f"deduplication_rules[{index}]: unsupported field '{field}'.")
            if not rule.group_by:
                errors.append(f"deduplication_rules[{index}]: group_by must not be empty.")
            if rule.max_per_group is not None and rule.max_per_group < 1:
                errors.append(f"deduplication_rules[{index}]: max_per_group must be >= 1.")

    @staticmethod
    def _validate_exceptions(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.exception_rules):
            if rule.action not in ALLOWED_ACTIONS:
                errors.append(f"exception_rules[{index}]: unsupported action '{rule.action}'.")
            if not rule.when:
                errors.append(f"exception_rules[{index}]: exception must define at least one condition.")
            if not rule.reason.strip():
                errors.append(f"exception_rules[{index}]: exception must include a reason.")

    @staticmethod
    def _validate_conflict_rules(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.conflict_resolution_rules):
            if rule.action not in ALLOWED_CONFLICT_ACTIONS:
                errors.append(f"conflict_resolution_rules[{index}]: unsupported action '{rule.action}'.")
            if not rule.reason.strip():
                errors.append(f"conflict_resolution_rules[{index}]: conflict resolution must include a reason.")

    @staticmethod
    def _validate_review_rules(rule_set: RuleSet, errors: list[str]) -> None:
        for index, rule in enumerate(rule_set.review_rules):
            if not rule.reason.strip():
                errors.append(f"review_rules[{index}]: review rule must include a reason.")

    @staticmethod
    def _validate_duplicates(rule_set: RuleSet, errors: list[str]) -> None:
        hard_keys = {
            (rule.field, rule.operator, canonical_json(rule.value), rule.action)
            for rule in rule_set.hard_filter_rules
        }
        if len(hard_keys) != len(rule_set.hard_filter_rules):
            errors.append("hard_filter_rules contains duplicate rules.")
        dedup_keys = {
            (
                tuple(rule.group_by),
                rule.method,
                rule.keep,
                canonical_json(rule.prefer_fields),
                rule.max_per_group,
            )
            for rule in rule_set.deduplication_rules
        }
        if len(dedup_keys) != len(rule_set.deduplication_rules):
            errors.append("deduplication_rules contains duplicate rules.")

    @staticmethod
    def _validate_max_count(rule_set: RuleSet, errors: list[str]) -> None:
        if rule_set.max_variable_count is not None and rule_set.max_variable_count < 0:
            errors.append("max_variable_count must be >= 0.")
