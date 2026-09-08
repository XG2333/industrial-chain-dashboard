from __future__ import annotations

from typing import Any

from financial_variable_curation.rule_workflow.constants import (
    ALLOWED_ACTIONS,
    ALLOWED_FIELDS,
    ALLOWED_OPERATORS,
    ALLOWED_RULE_TYPES,
    INTEGER_FIELDS,
    PROPORTIONAL_FIELDS,
)
from financial_variable_curation.rule_workflow.models import (
    Rule,
    RuleCondition,
    RuleSetDocument,
    RuleValidationReport,
)


class RuleSchemaValidator:
    def validate(self, document: RuleSetDocument) -> RuleValidationReport:
        errors: list[str] = []
        warnings: list[str] = []
        self._validate_global(document, errors, warnings)
        rule_ids = {rule.rule_id for rule in document.rules if rule.rule_id}
        for index, rule in enumerate(document.rules):
            self._validate_rule(rule, index, rule_ids, errors, warnings)
        return RuleValidationReport(valid=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _validate_global(
        document: RuleSetDocument,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        if not document.rule_set_name.strip():
            errors.append("rule_set_name must not be empty.")
        max_selected = document.global_settings.get("max_selected_variables")
        if max_selected is not None and (not isinstance(max_selected, int) or max_selected < 1):
            errors.append("global_settings.max_selected_variables must be a positive integer.")

    @staticmethod
    def _validate_rule(
        rule: Rule,
        index: int,
        rule_ids: set[str],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        context = f"rules[{index}]"
        if rule.rule_type not in ALLOWED_RULE_TYPES:
            errors.append(f"{context}: unsupported rule_type '{rule.rule_type}'.")
        if len(set(rule.ordered_values)) != len(rule.ordered_values):
            errors.append(f"{context}: ordered_values must not contain duplicates.")
        for condition in rule.conditions:
            RuleSchemaValidator._validate_condition(condition, context, errors)
        if rule.action is not None:
            RuleSchemaValidator._validate_action(rule, errors)
        if rule.rule_type == "DEDUPLICATION" and not rule.action:
            errors.append(f"{context}: deduplication rule requires an action.")
        if rule.rule_type == "DEDUPLICATION" and rule.action and not rule.action.group_by:
            errors.append(f"{context}: deduplication rule requires group_by fields.")
        if rule.rule_type == "FREQUENCY_PRIORITY":
            same_group = rule.metadata.get("same_comparison_group_only")
            if same_group is not True:
                warnings.append(f"{context}: frequency priority should define same_comparison_group_only.")
        if rule.rule_type == "EXCEPTION":
            target = next(
                (
                    condition.target_rule_id
                    for condition in rule.conditions
                    if condition.target_rule_id
                ),
                None,
            )
            if target and target not in rule_ids:
                errors.append(f"{context}: exception references unknown rule_id '{target}'.")
            if not rule.conditions:
                errors.append(f"{context}: exception rule must define at least one condition.")
        if rule.requires_review and rule.confidence >= 0.95:
            warnings.append(f"{context}: requires_review=true with high confidence.")
        for field in rule.unresolved_fields:
            if field and field not in ALLOWED_FIELDS:
                warnings.append(f"{context}: unresolved field '{field}'.")

    @staticmethod
    def _validate_condition(condition: RuleCondition, context: str, errors: list[str]) -> None:
        if condition.field not in ALLOWED_FIELDS:
            errors.append(f"{context}: unsupported field '{condition.field}'.")
        if condition.operator not in ALLOWED_OPERATORS:
            errors.append(f"{context}: unsupported operator '{condition.operator}'.")
        if condition.field in PROPORTIONAL_FIELDS and isinstance(condition.value, (int, float)):
            if not 0 <= float(condition.value) <= 1:
                errors.append(f"{context}: {condition.field} must be between 0 and 1.")
        if condition.field in INTEGER_FIELDS and isinstance(condition.value, (int, float)):
            if float(condition.value) < 0:
                errors.append(f"{context}: {condition.field} must be non-negative.")

    @staticmethod
    def _validate_action(rule: Rule, errors: list[str]) -> None:
        action = rule.action
        if action is None:
            return
        context = f"rules[{rule.rule_id or rule.rule_name}]"
        if action.action_type not in ALLOWED_ACTIONS:
            errors.append(f"{context}: unsupported action '{action.action_type}'.")
        if action.action_type == "KEEP_TOP_N" and not action.keep_n and not action.max_count:
            errors.append(f"{context}: KEEP_TOP_N requires keep_n or max_count.")
        if action.keep_n is not None and action.keep_n < 1:
            errors.append(f"{context}: KEEP_TOP_N requires keep_n >= 1.")
        if action.action_type in {"ADD_SCORE", "SUBTRACT_SCORE"} and action.score is None:
            errors.append(f"{context}: scoring action requires a score.")
        if action.field and action.field not in ALLOWED_FIELDS:
            errors.append(f"{context}: action references unsupported field '{action.field}'.")
        for field in [*action.group_by, *action.prefer_fields]:
            if field not in ALLOWED_FIELDS:
                errors.append(f"{context}: action references unsupported field '{field}'.")
