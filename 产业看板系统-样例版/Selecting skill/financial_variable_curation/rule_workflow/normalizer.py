from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from financial_variable_curation.rule_workflow.constants import (
    CATEGORY_ALIASES,
    FREQUENCY_ALIASES,
)
from financial_variable_curation.rule_workflow.models import (
    Rule,
    RuleCondition,
    RuleSetDocument,
)


def _normalize_value(value):
    if isinstance(value, str):
        stripped = value.strip()
        return None if stripped == "" else stripped
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _normalize_enum_value(value: str | None, aliases: dict[str, str]) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return aliases.get(normalized, value.strip().upper())


def _stable_rule_id(rule: Rule) -> str:
    payload = {
        "rule_type": rule.rule_type,
        "rule_name": rule.rule_name,
        "description": rule.description,
        "scope": rule.scope.model_dump(mode="json"),
        "conditions": [condition.model_dump(mode="json") for condition in rule.conditions],
        "ordered_values": rule.ordered_values,
        "action": rule.action.model_dump(mode="json") if rule.action else None,
        "priority": rule.priority,
        "source_text_excerpt": rule.source_text_excerpt,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"rule_{hashlib.sha256(raw).hexdigest()[:12]}"


class RuleNormalizer:
    def normalize(self, document: RuleSetDocument) -> RuleSetDocument:
        normalized = document.model_copy(deep=True)
        normalized.rule_set_name = normalized.rule_set_name.strip() or "unnamed_rule_set"
        normalized.source_type = normalized.source_type.strip().upper() or "USER_RULES"
        normalized.provider = normalized.provider.lower()
        normalized.metadata = dict(normalized.metadata)
        if normalized.provider == "mock":
            normalized.metadata["mock_only"] = True
            normalized.metadata["production_ready"] = False
        normalized.rules = [
            self._normalize_rule(rule, document.provider) for rule in normalized.rules
        ]
        normalized.rules.sort(key=lambda rule: (rule.priority, rule.rule_id))
        return normalized

    @staticmethod
    def _normalize_rule(rule: Rule, provider: str) -> Rule:
        normalized = rule.model_copy(deep=True)
        raw_type = normalized.rule_type.strip().lower()
        normalized.rule_type = {
            "filter": "HARD_FILTER",
            "hard_filter": "HARD_FILTER",
            "computation": "SCORING",
            "compute": "SCORING",
        }.get(raw_type, normalized.rule_type.strip().upper())
        normalized.rule_name = normalized.rule_name.strip()
        normalized.description = normalized.description.strip()
        normalized.source_text_excerpt = normalized.source_text_excerpt.strip()[:300]
        normalized.priority = int(normalized.priority or 100)
        normalized.scope = rule.scope.model_copy(deep=True)
        normalized.scope.categories = [
            value
            for value in dict.fromkeys(
                _normalize_enum_value(value, CATEGORY_ALIASES) or value
                for value in normalized.scope.categories
            )
        ]
        normalized.conditions = [RuleNormalizer._normalize_condition(item) for item in normalized.conditions]
        normalized.ordered_values = list(
            dict.fromkeys(
                _normalize_enum_value(value, CATEGORY_ALIASES)
                if normalized.rule_type in {"CATEGORY_PRIORITY", "SUBCATEGORY_PRIORITY"}
                else _normalize_enum_value(value, FREQUENCY_ALIASES)
                if normalized.rule_type == "FREQUENCY_PRIORITY"
                else value
                for value in normalized.ordered_values
                if value
            )
        )
        normalized.unresolved_fields = list(
            dict.fromkeys(_normalize_value(value) or "" for value in normalized.unresolved_fields if value)
        )
        if normalized.action is not None:
            normalized.action.action_type = normalized.action.action_type.strip().upper()
        if provider == "mock":
            normalized.metadata["mock_only"] = True
            normalized.metadata["production_ready"] = False
        normalized.rule_id = _stable_rule_id(normalized)
        return normalized

    @staticmethod
    def _normalize_condition(condition: RuleCondition) -> RuleCondition:
        normalized = condition.model_copy(deep=True)
        normalized.field = condition.field.strip()
        normalized.operator = condition.operator.strip().upper()
        normalized.value = _normalize_value(condition.value)
        return normalized
