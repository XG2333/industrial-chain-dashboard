from __future__ import annotations

ALLOWED_FIELDS = {
    "category_level_1",
    "category_level_2",
    "metric_name",
    "data_nature",
    "industry",
    "sector",
    "commodity",
    "market",
    "region",
    "country",
    "unit_standard",
    "unit_dimension",
    "statistical_scope",
    "detected_frequency",
    "classification_confidence",
    "missing_rate",
    "non_null_count",
    "unique_value_count",
    "coverage_days",
    "latest_gap_days",
    "quality_score",
    "is_constant",
    "is_outdated",
    "is_pseudo_high_frequency",
    "source_type",
    "comparison_group_key",
    "standard_name",
    "parent_metric",
    "is_derived",
}

ALLOWED_OPERATORS = {
    "EQ",
    "NE",
    "GT",
    "GTE",
    "LT",
    "LTE",
    "IN",
    "NOT_IN",
    "IS_NULL",
    "IS_NOT_NULL",
    "CONTAINS",
    "NOT_CONTAINS",
}

ALLOWED_ACTIONS = {
    "REJECT",
    "KEEP",
    "PRIORITIZE",
    "DEPRIORITIZE",
    "ADD_SCORE",
    "SUBTRACT_SCORE",
    "KEEP_TOP_N",
    "MARK_REVIEW",
    "NO_ACTION",
}

ALLOWED_RULE_TYPES = {
    "CATEGORY_PRIORITY",
    "SUBCATEGORY_PRIORITY",
    "FREQUENCY_PRIORITY",
    "SOURCE_PRIORITY",
    "HARD_FILTER",
    "SORT",
    "SCORING",
    "DEDUPLICATION",
    "EXCEPTION",
    "REVIEW",
    "MAX_COUNT",
}

EXECUTION_PHASES = [
    "VALIDATION",
    "HARD_FILTER",
    "REVIEW_GATE",
    "CATEGORY_PRIORITY",
    "SUBCATEGORY_PRIORITY",
    "FREQUENCY_PRIORITY",
    "SOURCE_PRIORITY",
    "QUALITY_SORT",
    "SCORING",
    "DEDUPLICATION",
    "TOP_N_LIMIT",
    "FINAL_REVIEW",
]

RULE_TYPE_TO_PHASE = {
    "HARD_FILTER": "HARD_FILTER",
    "REVIEW": "REVIEW_GATE",
    "CATEGORY_PRIORITY": "CATEGORY_PRIORITY",
    "SUBCATEGORY_PRIORITY": "SUBCATEGORY_PRIORITY",
    "FREQUENCY_PRIORITY": "FREQUENCY_PRIORITY",
    "SOURCE_PRIORITY": "SOURCE_PRIORITY",
    "SORT": "QUALITY_SORT",
    "SCORING": "SCORING",
    "DEDUPLICATION": "DEDUPLICATION",
    "MAX_COUNT": "TOP_N_LIMIT",
    "EXCEPTION": "VALIDATION",
}

PROPORTIONAL_FIELDS = {"missing_rate", "classification_confidence"}
INTEGER_FIELDS = {
    "non_null_count",
    "unique_value_count",
    "coverage_days",
    "latest_gap_days",
}

CATEGORY_ALIASES = {
    "price": "PRICE",
    "价格": "PRICE",
    "spread": "SPREAD",
    "价差": "SPREAD",
    "inventory": "INVENTORY",
    "库存": "INVENTORY",
    "production": "PRODUCTION",
    "产量": "PRODUCTION",
    "import": "IMPORT",
    "进口": "IMPORT",
    "export": "EXPORT",
    "出口": "EXPORT",
    "quantity": "QUANTITY",
    "capacity": "CAPACITY",
    "成本": "COST",
    "利润": "MARGIN",
    "金融": "FINANCIAL",
    "宏观": "MACRO",
    "指数": "INDEX",
}

FREQUENCY_ALIASES = {
    "daily": "DAILY",
    "日频": "DAILY",
    "weekly": "WEEKLY",
    "周频": "WEEKLY",
    "monthly": "MONTHLY",
    "月频": "MONTHLY",
    "quarterly": "QUARTERLY",
    "季频": "QUARTERLY",
    "annual": "ANNUAL",
    "年频": "ANNUAL",
}
