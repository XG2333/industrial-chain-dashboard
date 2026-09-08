from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FinancialCategory(str, Enum):
    PRICE = "PRICE"
    QUANTITY = "QUANTITY"
    INVENTORY = "INVENTORY"
    CAPACITY = "CAPACITY"
    COST = "COST"
    MARGIN = "MARGIN"
    FINANCIAL = "FINANCIAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    MACRO = "MACRO"
    INDEX = "INDEX"
    UNKNOWN = "UNKNOWN"


class DataNature(str, Enum):
    LEVEL = "LEVEL"
    DIFFERENCE = "DIFFERENCE"
    RATIO = "RATIO"
    PERCENT_CHANGE = "PERCENT_CHANGE"
    INDEX = "INDEX"
    STOCK = "STOCK"
    FLOW = "FLOW"
    AGGREGATE = "AGGREGATE"
    UNKNOWN = "UNKNOWN"


class ClassificationRequestItem(BaseModel):
    variable_id: str = Field(min_length=1, max_length=100)
    file_name: str = Field(default="", max_length=255)
    sheet_name: str = Field(default="", max_length=255)
    original_name: str = Field(min_length=1, max_length=512)
    normalized_name: str = Field(default="", max_length=512)
    unit_hint: str | None = Field(default=None, max_length=120)
    industry_hint: str | None = Field(default=None, max_length=120)
    commodity_hint: str | None = Field(default=None, max_length=120)
    detected_frequency: str = Field(default="unknown", max_length=40)
    inferred_data_type: str = Field(default="", max_length=40)
    sample_values: list[str] = Field(default_factory=list, max_length=10)
    quality_summary: dict[str, Any] = Field(default_factory=dict)


class ClassificationRequest(BaseModel):
    batch_id: str
    provider: str
    model: str
    prompt_version: str
    taxonomy_version: str
    schema_version: str
    variables: list[ClassificationRequestItem] = Field(min_length=1, max_length=50)


class ClassificationResponse(BaseModel):
    variable_id: str = Field(min_length=1, max_length=100)
    standard_name: str = Field(default="", max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    commodity: str | None = Field(default=None, max_length=120)
    category_level_1: FinancialCategory = FinancialCategory.UNKNOWN
    category_level_2: str = Field(default="UNCLASSIFIED", max_length=120)
    metric_name: str = Field(default="", max_length=255)
    data_nature: DataNature = DataNature.UNKNOWN
    market: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    unit: str | None = Field(default=None, max_length=120)
    statistical_scope: str | None = Field(default=None, max_length=255)
    comparison_group_components: dict[str, str | None] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    review_reasons: list[str] = Field(default_factory=list, max_length=20)
    is_derived: bool = False
    parent_metric: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=2000)
    notes: list[str] = Field(default_factory=list, max_length=20)


class ClassificationBatchResponse(BaseModel):
    batch_id: str = Field(default="", max_length=120)
    items: list[ClassificationResponse] = Field(min_length=1, max_length=50)


class LLMCallAttempt(BaseModel):
    attempt_number: int
    started_at: datetime
    completed_at: datetime
    status: str
    response_id: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None


class LLMCallResult(BaseModel):
    response: BaseModel
    attempts: list[LLMCallAttempt] = Field(default_factory=list)
    cached: bool = False


class ValidationIssue(BaseModel):
    variable_id: str
    code: str
    message: str


class ClassificationRunResult(BaseModel):
    run_id: str
    provider: str
    model: str
    prompt_version: str
    taxonomy_version: str
    schema_version: str
    selected_variable_count: int = 0
    batch_count: int = 0
    successful_count: int = 0
    needs_review_count: int = 0
    failed_count: int = 0
    cache_hit_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_llm_calls: int = 0
    artifacts_path: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    errors: list[str] = Field(default_factory=list)
    dry_run: bool = False


COMPARISON_GROUP_KEYS = (
    "standard_name",
    "industry",
    "sector",
    "commodity",
    "category_level_1",
    "category_level_2",
    "data_nature",
    "market",
    "region",
    "unit",
)


def build_comparison_group_key(response: ClassificationResponse) -> str:
    components = {
        key: response.comparison_group_components.get(key)
        if response.comparison_group_components
        else getattr(response, key, None)
        for key in COMPARISON_GROUP_KEYS
    }
    normalized = json.dumps(
        {key: (value or "").lower().strip() if value else "" for key, value in components.items()},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def classification_request_hash(request: ClassificationRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
