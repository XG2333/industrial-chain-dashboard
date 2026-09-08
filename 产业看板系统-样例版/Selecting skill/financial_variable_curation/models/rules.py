from typing import Any

from pydantic import BaseModel, Field

from financial_variable_curation.models.enums import RuleSetStatus, RuleSource


class Condition(BaseModel):
    field: str
    operator: str
    value: Any = None


class PrioritySpec(BaseModel):
    value: str
    priority: int = 100
    reason: str | None = None


class HardFilterRule(BaseModel):
    field: str
    operator: str
    value: Any
    action: str
    reason: str = ""


class SortingRule(BaseModel):
    field: str
    direction: str = "asc"
    priority: int = 0


class ScoringRule(BaseModel):
    field: str
    weight: float = 1.0
    transform: str = "raw"


class DeduplicationRule(BaseModel):
    group_by: list[str] = Field(default_factory=lambda: ["category", "subcategory"])
    method: str = "none"
    keep: str = "all"
    prefer_fields: list[str] = Field(default_factory=list)
    max_per_group: int | None = None
    needs_review_on_ambiguous: bool = True


class ExceptionRule(BaseModel):
    description: str = ""
    when: list[Condition] = Field(default_factory=list)
    action: str
    reason: str = ""


class ConflictResolutionRule(BaseModel):
    trigger: str = "priority_conflict"
    action: str = "NEEDS_REVIEW"
    reason: str = ""


class ReviewRule(BaseModel):
    condition: Condition
    reason: str


class RuleSet(BaseModel):
    name: str = "unnamed_rule_set"
    version: str = "v1"
    source: RuleSource = RuleSource.USER_RULES
    status: RuleSetStatus = RuleSetStatus.DRAFT
    production_ready: bool = False
    prompt_version: str | None = None
    rules_hash: str | None = None
    category_priorities: list[PrioritySpec] = Field(default_factory=list)
    subcategory_priorities: list[PrioritySpec] = Field(default_factory=list)
    frequency_priorities: list[PrioritySpec] = Field(default_factory=list)
    source_priorities: list[PrioritySpec] = Field(default_factory=list)
    hard_filter_rules: list[HardFilterRule] = Field(default_factory=list)
    sorting_rules: list[SortingRule] = Field(default_factory=list)
    scoring_rules: list[ScoringRule] = Field(default_factory=list)
    deduplication_rules: list[DeduplicationRule] = Field(default_factory=list)
    exception_rules: list[ExceptionRule] = Field(default_factory=list)
    conflict_resolution_rules: list[ConflictResolutionRule] = Field(default_factory=list)
    review_rules: list[ReviewRule] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    max_variable_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (
            self.category_priorities
            or self.subcategory_priorities
            or self.frequency_priorities
            or self.source_priorities
            or self.hard_filter_rules
            or self.sorting_rules
            or self.scoring_rules
            or self.deduplication_rules
            or self.exception_rules
            or self.conflict_resolution_rules
            or self.review_rules
            or self.unresolved_items
            or self.max_variable_count is not None
        )


class RuleValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CompiledRuleSet(RuleSet):
    effective_category_order: list[str] = Field(default_factory=list)
    effective_subcategory_order: list[str] = Field(default_factory=list)
    effective_frequency_order: list[str] = Field(default_factory=list)
    effective_source_order: list[str] = Field(default_factory=list)
    compile_warnings: list[str] = Field(default_factory=list)
