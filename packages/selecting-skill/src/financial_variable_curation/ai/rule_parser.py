from __future__ import annotations

import json
import os
import re
from typing import Protocol

from pydantic import BaseModel, Field

from financial_variable_curation.models.rules import (
    Condition,
    DeduplicationRule,
    HardFilterRule,
    PrioritySpec,
    ReviewRule,
    RuleSet,
)


class RuleParseResult(BaseModel):
    rule_set: RuleSet
    warnings: list[str] = Field(default_factory=list)


class RuleParser(Protocol):
    name: str

    def parse_rules(self, text: str, rule_set_name: str | None = None) -> RuleParseResult:
        """Parse natural language or JSON rule text into a structured RuleSet."""


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def _find_percent(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not match:
        return None
    return float(match.group(1)) / 100.0


class MockRuleParser:
    """Offline parser for JSON and common generic rule phrases.

    This is a placeholder for the AI rule parser so the workflow is testable
    without a model call. It understands only generic rule language, not
    industry-specific business priorities.
    """

    name = "mock"

    def parse_rules(self, text: str, rule_set_name: str | None = None) -> RuleParseResult:
        cleaned = _strip_code_fence(text)
        if cleaned.startswith("{"):
            return self._parse_json(cleaned, rule_set_name)
        return self._parse_phrases(cleaned, rule_set_name)

    def _parse_json(self, text: str, rule_set_name: str | None) -> RuleParseResult:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            rule_set = RuleSet(name=rule_set_name or "invalid_json_rules", unresolved_items=[text])
            return RuleParseResult(rule_set=rule_set, warnings=[f"Invalid JSON: {exc}"])
        if rule_set_name and isinstance(payload, dict):
            payload.setdefault("name", rule_set_name)
        return RuleParseResult(rule_set=RuleSet.model_validate(payload))

    def _parse_phrases(self, text: str, rule_set_name: str | None) -> RuleParseResult:
        name = rule_set_name or "user_rules"
        warnings: list[str] = []
        category_priorities: list[PrioritySpec] = []
        subcategory_priorities: list[PrioritySpec] = []
        frequency_priorities: list[PrioritySpec] = []
        source_priorities: list[PrioritySpec] = []
        hard_filters: list[HardFilterRule] = []
        dedup_rules: list[DeduplicationRule] = []
        review_rules: list[ReviewRule] = []
        unresolved: list[str] = []
        max_variable_count: int | None = None

        frequency_map = {
            "日频": "DAILY",
            "周频": "WEEKLY",
            "月频": "MONTHLY",
            "季频": "QUARTERLY",
            "年频": "ANNUAL",
        }

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()

            if re.match(r"^(规则集名称|规则名称|名称|name)\s*[:：]", line):
                name = re.split(r"[:：]", line, maxsplit=1)[1].strip()
                continue

            if "全空" in line and ("删除" in line or "剔除" in line or "排除" in line):
                hard_filters.append(
                    HardFilterRule(field="all_empty", operator="eq", value=True, action="EXCLUDE", reason=line)
                )
                continue
            if ("恒定" in line or "常数" in line or "常量" in line) and ("删除" in line or "剔除" in line or "排除" in line):
                hard_filters.append(
                    HardFilterRule(field="constant", operator="eq", value=True, action="EXCLUDE", reason=line)
                )
                continue

            percent = _find_percent(line)
            if "缺失率" in line and percent is not None:
                action = "NEEDS_REVIEW" if ("复核" in line or "审查" in line or "review" in lowered) else "EXCLUDE"
                operator = "gt"
                if any(token in line for token in ("低于", "小于", "不超过", "<")):
                    operator = "lt"
                hard_filters.append(
                    HardFilterRule(field="missing_rate", operator=operator, value=percent, action=action, reason=line)
                )
                continue

            if "日期无法解析" in line or ("日期" in line and "解析率" in line):
                hard_filters.append(
                    HardFilterRule(field="date_parse_rate", operator="lt", value=0.1, action="NEEDS_REVIEW", reason=line)
                )
                continue

            if "频率优先级" in line or "优先选择" in line and any(token in line for token in frequency_map):
                for label, value in frequency_map.items():
                    if label in line:
                        frequency_priorities.append(PrioritySpec(value=value, priority=1, reason=line))
                continue

            if "类别优先级" in line or "优先选择类别" in line:
                values = re.split(r"[:：,，、/]", line, maxsplit=1)
                if len(values) == 2:
                    for raw_value in re.split(r"[,，、/]", values[1]):
                        value = raw_value.strip()
                        if value:
                            category_priorities.append(PrioritySpec(value=value, priority=1, reason=line))
                continue

            if "子类别优先级" in line:
                values = re.split(r"[:：,，、/]", line, maxsplit=1)
                if len(values) == 2:
                    for raw_value in re.split(r"[,，、/]", values[1]):
                        value = raw_value.strip()
                        if value:
                            subcategory_priorities.append(PrioritySpec(value=value, priority=1, reason=line))
                continue

            if "来源优先级" in line:
                values = re.split(r"[:：,，、/]", line, maxsplit=1)
                if len(values) == 2:
                    for raw_value in re.split(r"[,，、/]", values[1]):
                        value = raw_value.strip()
                        if value:
                            source_priorities.append(PrioritySpec(value=value, priority=1, reason=line))
                continue

            max_match = re.search(r"最多(?:选择|保留|输出)\s*(\d+)\s*个", line)
            if max_match:
                max_variable_count = int(max_match.group(1))
                continue

            if "同类" in line and ("保留" in line or "去重" in line):
                dedup_rule = DeduplicationRule(
                    group_by=["category", "subcategory"],
                    method="all",
                    keep="all",
                    needs_review_on_ambiguous=True,
                )
                per_group = re.search(r"每类(?:最多|保留)\s*(\d+)\s*个", line)
                if per_group:
                    dedup_rule.max_per_group = int(per_group.group(1))
                dedup_rules.append(dedup_rule)
                continue

            if "无法确认" in line or "需要人工复核" in line or "进入复核" in line:
                review_rules.append(
                    ReviewRule(
                        condition=Condition(field="category", operator="eq", value="UNCLASSIFIED"),
                        reason=line,
                    )
                )
                continue

            unresolved.append(line)

        rule_set = RuleSet(
            name=name,
            version="v1",
            source="USER_RULES",
            status="PARSED",
            category_priorities=category_priorities,
            subcategory_priorities=subcategory_priorities,
            frequency_priorities=frequency_priorities,
            source_priorities=source_priorities,
            hard_filter_rules=hard_filters,
            deduplication_rules=dedup_rules,
            review_rules=review_rules,
            unresolved_items=unresolved,
            max_variable_count=max_variable_count,
        )
        if unresolved:
            warnings.append(f"{len(unresolved)} line(s) were not parsed by the mock parser.")
        return RuleParseResult(rule_set=rule_set, warnings=warnings)


class OpenAIRuleParser:
    """Optional OpenAI-based rule parser used only when explicitly requested."""

    name = "openai"
    prompt_version = "financial-variable-rules-v1"

    def parse_rules(self, text: str, rule_set_name: str | None = None) -> RuleParseResult:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI rule parser requires the optional 'ai' dependency: pip install -e '.[ai]'") from exc

        client = OpenAI()
        system_prompt = (
            "Convert the user's financial variable selection rules into the exact JSON schema "
            "used by RuleSet. Never emit SQL. Never name variables to delete directly. "
            "Only emit structured rule suggestions."
        )
        response = client.chat.completions.create(
            model=os.getenv("FVC_OPENAI_MODEL", "gpt-4o-mini"),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(_strip_code_fence(content))
        if rule_set_name and isinstance(payload, dict):
            payload.setdefault("name", rule_set_name)
        payload.setdefault("prompt_version", self.prompt_version)
        return RuleParseResult(rule_set=RuleSet.model_validate(payload))


def get_rule_parser() -> RuleParser:
    if os.getenv("FVC_RULE_PARSER", "").lower() == "openai":
        return OpenAIRuleParser()
    return MockRuleParser()
