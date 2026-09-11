from __future__ import annotations

import re

from financial_variable_curation.rule_workflow.constants import (
    CATEGORY_ALIASES,
    FREQUENCY_ALIASES,
)
from financial_variable_curation.rule_workflow.models import (
    Rule,
    RuleAction,
    RuleCondition,
    RuleScope,
    RuleSetDocument,
)


class MockRuleParser:
    provider = "mock"

    def parse(self, text: str, context: dict | None = None) -> RuleSetDocument:
        context = context or {}
        rules: list[Rule] = []
        unresolved: list[str] = []
        warnings: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parsed = self._parse_line(line)
            if parsed is None:
                unresolved.append(line)
                warnings.append(f"Unresolved rule line: {line[:80]}")
            else:
                rules.append(parsed)
        return RuleSetDocument(
            rule_set_name=context.get("rule_set_name", "user_rules"),
            provider="mock",
            model="mock",
            prompt_version=context.get("prompt_version", "rule_parser_v1"),
            taxonomy_version=context.get("taxonomy_version", "taxonomy_v1"),
            schema_version=context.get("schema_version", "rule_schema_v1"),
            rules=rules,
            global_settings={
                "max_selected_variables": None,
                "default_uncertain_action": "MARK_REVIEW",
                "allow_automatic_deletion": False,
            },
            unresolved_items=unresolved,
            warnings=warnings,
            metadata={"mock_only": True, "production_ready": False},
        )

    def _parse_line(self, line: str) -> Rule | None:
        if re.search(r"价格.*优先.*数量|数量.*优先.*价格", line):
            ordered = ["价格", "数量"]
            return self._priority_rule(
                line,
                "CATEGORY_PRIORITY",
                [CATEGORY_ALIASES.get(value, value) for value in ordered],
            )
        category_order = re.search(r"^(价格|价差|库存|产量|进口|出口)(\s*>\s*(价格|价差|库存|产量|进口|出口))+$", line)
        if category_order:
            values = [item.strip() for item in re.split(r"\s*>\s*", line)]
            return self._priority_rule(
                line,
                "CATEGORY_PRIORITY",
                [CATEGORY_ALIASES.get(value, value) for value in values],
            )
        frequency_order = re.search(r"^(日频|周频|月频|季频|年频)(\s*>\s*(日频|周频|月频|季频|年频))+$", line)
        if frequency_order:
            values = [item.strip() for item in re.split(r"\s*>\s*", line)]
            return self._priority_rule(
                line,
                "FREQUENCY_PRIORITY",
                [FREQUENCY_ALIASES.get(value, value) for value in values],
                metadata={"same_comparison_group_only": True},
            )
        missing_match = re.search(r"缺失率超过\s*(\d+(?:\.\d+)?)\s*%", line)
        if missing_match:
            value = float(missing_match.group(1)) / 100.0
            return Rule(
                rule_type="HARD_FILTER",
                rule_name="missing_rate_hard_filter",
                description="Hard filter on missing_rate.",
                conditions=[RuleCondition(field="missing_rate", operator="GT", value=value)],
                action=RuleAction(action_type="REJECT", value=value),
                source_text_excerpt=line[:200],
                confidence=0.9,
            )
        if "同一指标" in line and "只保留" in line:
            return Rule(
                rule_type="DEDUPLICATION",
                rule_name="deduplicate_same_indicator",
                description="Keep one variable per comparison group.",
                action=RuleAction(
                    action_type="KEEP_TOP_N",
                    keep_n=1,
                    group_by=["comparison_group_key"],
                ),
                source_text_excerpt=line[:200],
                confidence=0.8,
            )
        if "分类置信度" in line and "低于" in line and ("人工复核" in line or "复核" in line):
            confidence_match = re.search(r"低于\s*0?\.?(\d+)", line)
            value = float(confidence_match.group(1)) / 10.0 if confidence_match else 0.8
            return Rule(
                rule_type="REVIEW",
                rule_name="low_classification_confidence_review",
                description="Low classification confidence enters review.",
                conditions=[
                    RuleCondition(
                        field="classification_confidence",
                        operator="LT",
                        value=value,
                    )
                ],
                action=RuleAction(action_type="MARK_REVIEW"),
                source_text_excerpt=line[:200],
                confidence=0.8,
            )
        max_match = re.search(r"最多保留\s*(\d+)\s*个变量", line)
        if max_match:
            return Rule(
                rule_type="MAX_COUNT",
                rule_name="global_max_variable_count",
                description="Global maximum variable count.",
                action=RuleAction(
                    action_type="KEEP_TOP_N",
                    max_count=int(max_match.group(1)),
                    max_count_scope="GLOBAL",
                ),
                source_text_excerpt=line[:200],
                confidence=0.9,
            )
        return None

    @staticmethod
    def _priority_rule(
        line: str,
        rule_type: str,
        ordered_values: list[str],
        metadata: dict | None = None,
    ) -> Rule:
        return Rule(
            rule_type=rule_type,
            rule_name=f"{rule_type.lower()}_priority",
            description=f"Priority rule parsed from: {line[:80]}",
            ordered_values=ordered_values,
            action=RuleAction(action_type="PRIORITIZE", sort_order=0),
            source_text_excerpt=line[:200],
            confidence=0.85,
            metadata=metadata or {},
        )
