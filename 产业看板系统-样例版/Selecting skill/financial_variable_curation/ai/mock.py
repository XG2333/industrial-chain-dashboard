from __future__ import annotations

import re

from financial_variable_curation.ai.classification import VariableClassifier
from financial_variable_curation.models.enums import ClassificationMethod
from financial_variable_curation.models.variable import VariableClassification, VariableProfile

_CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("price", ("price", "close", "收盘", "价格", "均价", "市价", "单价", "开盘", "最高价", "最低价")),
    ("quantity", ("volume", "quantity", "产量", "销量", "销售量", "成交量", "吨", "桶", "台")),
    ("inventory", ("inventory", "库存", "仓单")),
    ("financial", ("revenue", "profit", "收入", "利润", "净利润", "毛利率", "营收", "费用", "现金流")),
    ("fundamental", ("pe", "pb", "eps", "市值", "市盈率", "市净率", "每股")),
    ("capacity", ("capacity", "产能")),
    ("cost", ("cost", "成本")),
]


class MockVariableClassifier(VariableClassifier):
    """Deterministic mock classifier used until a real semantic classifier is configured."""

    name = "mock"

    def __init__(self) -> None:
        self._patterns = [
            (category, re.compile(r"|".join(re.escape(token) for token in tokens), re.IGNORECASE))
            for category, tokens in _CATEGORY_PATTERNS
        ]

    def classify(self, profile: VariableProfile) -> VariableClassification:
        header = profile.original_header.lower().replace("_", " ").replace("-", " ").strip()
        for category, pattern in self._patterns:
            if pattern.search(header):
                return VariableClassification(
                    category=category,
                    subcategory=category,
                    semantic_description=f"Mock classified header as {category}.",
                    confidence=0.75,
                    method=ClassificationMethod.MOCK,
                    needs_review=True,
                    notes=["Mock classifier is not a production semantic source."],
                )
        return VariableClassification(
            category="UNCLASSIFIED",
            subcategory="UNCLASSIFIED",
            semantic_description="",
            confidence=0.0,
            method=ClassificationMethod.UNCLASSIFIED,
            needs_review=True,
            notes=["No mock semantic category matched; requires human review."],
        )
