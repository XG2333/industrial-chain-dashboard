from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RuleScope(BaseModel):
    industries: list[str] = Field(default_factory=list)
    commodities: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    comparison_group_keys: list[str] = Field(default_factory=list)
    statistical_scopes: list[str] = Field(default_factory=list)


class RuleCondition(BaseModel):
    field: str
    operator: str
    value: Any = None
    target_rule_id: str | None = None
    target_rule_type: str | None = None


class RuleAction(BaseModel):
    action_type: str
    value: Any = None
    field: str | None = None
    direction: str | None = None
    score: float | None = None
    sort_order: int = 0
    keep_n: int | None = None
    max_count: int | None = None
    max_count_scope: str | None = None
    group_by: list[str] = Field(default_factory=list)
    prefer_fields: list[str] = Field(default_factory=list)
    replace_with: str | None = None
    blocks_automatic_selection: bool = False


class Rule(BaseModel):
    rule_id: str = ""
    rule_type: str
    rule_name: str = ""
    description: str = ""
    scope: RuleScope = Field(default_factory=RuleScope)
    conditions: list[RuleCondition] = Field(default_factory=list)
    ordered_values: list[str] = Field(default_factory=list)
    priority: int = 100
    action: RuleAction | None = None
    exceptions: list[str] = Field(default_factory=list)
    source_text_excerpt: str = Field(default="", max_length=300)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_review: bool = False
    unresolved_fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleSetDocument(BaseModel):
    rule_set_name: str = "unnamed_rule_set"
    rule_set_description: str = ""
    source_language: str = "zh-CN"
    source_type: str = "USER_RULES"
    provider: str = "mock"
    model: str = "mock"
    prompt_version: str = "rule_parser_v1"
    taxonomy_version: str = "taxonomy_v1"
    schema_version: str = "rule_schema_v1"
    rules: list[Rule] = Field(default_factory=list)
    global_settings: dict[str, Any] = Field(default_factory=dict)
    unresolved_items: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuleSourceMetadata(BaseModel):
    source_file_name: str
    original_path: str
    source_hash: str
    text_length: int
    extension: str
    provider: str
    model: str


class RuleParseResult(BaseModel):
    parse_run_id: str
    source_metadata: RuleSourceMetadata
    document: RuleSetDocument
    cache_hit: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class RuleParserProviderResult(BaseModel):
    document: RuleSetDocument
    llm_call_result: Any | None = None


class RuleValidationReport(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RuleConflict(BaseModel):
    conflict_id: str
    involved_rule_ids: list[str] = Field(default_factory=list)
    conflict_type: str
    severity: str
    description: str
    suggested_resolution: str = ""
    blocks_compilation: bool = False


class RuleConflictReport(BaseModel):
    conflicts: list[RuleConflict] = Field(default_factory=list)

    @property
    def blocking_count(self) -> int:
        return sum(1 for conflict in self.conflicts if conflict.blocks_compilation)


class CompiledRule(BaseModel):
    rule: Rule
    execution_phase: str
    dependency_rule_ids: list[str] = Field(default_factory=list)


class CompiledRuleSetOutput(BaseModel):
    compiled_rule_set_id: str
    rule_set_name: str
    version: str
    status: str
    production_ready: bool
    compiled_rules: list[CompiledRule] = Field(default_factory=list)
    execution_plan: list[str] = Field(default_factory=list)
    source_hash: str
    compiled_hash: str
    warnings: list[str] = Field(default_factory=list)


class RuleSummary(BaseModel):
    source_hash: str
    rule_count: int
    rule_type_counts: dict[str, int] = Field(default_factory=dict)
    unresolved_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    conflict_count: int = 0
    blocking_conflict_count: int = 0
    validation_valid: bool = False
    compile_successful: bool = False
    production_ready: bool = False
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    taxonomy_version: str = ""
    schema_version: str = ""


class RuleWorkflowResult(BaseModel):
    parse_run_id: str
    source_metadata: RuleSourceMetadata
    document: RuleSetDocument
    normalized_document: RuleSetDocument
    validation: RuleValidationReport
    conflicts: RuleConflictReport
    compiled: CompiledRuleSetOutput | None = None
    summary: RuleSummary
    artifacts_path: str | None = None
    dry_run: bool = False
    cache_hit: bool = False


def rule_source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rule_document_hash(document: RuleSetDocument) -> str:
    payload = document.model_dump(mode="json")
    return hashlib.sha256(
        __import__("json").dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
