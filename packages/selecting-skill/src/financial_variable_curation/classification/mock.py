from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from financial_variable_curation.classification.models import (
    ClassificationBatchResponse,
    ClassificationRequestItem,
    ClassificationResponse,
    DataNature,
    FinancialCategory,
    LLMCallAttempt,
    LLMCallResult,
    build_comparison_group_key,
)


class MockLLMClient:
    provider = "mock"

    def generate_structured(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_payload: dict,
        response_model: type[BaseModel],
        request_id: str,
    ) -> LLMCallResult:
        payload_items = user_payload.get("variables") or []
        request_items = [ClassificationRequestItem.model_validate(item) for item in payload_items]
        items = [self._classify(item) for item in request_items]
        response = ClassificationBatchResponse(
            batch_id=user_payload.get("batch_id", request_id),
            items=items,
        )
        now = datetime.now(timezone.utc)
        attempt = LLMCallAttempt(
            attempt_number=1,
            started_at=now,
            completed_at=now,
            status="SUCCESS",
            model="mock",
            latency_ms=1,
        )
        return LLMCallResult(response=response, attempts=[attempt], cached=False)

    def _classify(self, item: ClassificationRequestItem) -> ClassificationResponse:
        name = " ".join([item.original_name, item.normalized_name]).lower()
        name = name.replace("_", " ").replace("-", " ").strip()
        commodity = self._commodity(name)
        category, data_nature = self._semantics(name)
        # Use unit to avoid misclassifying price-like trade metrics as quantity.
        if (
            self._is_price_unit(item.unit_hint)
            and re.search(r"盈亏|价差|基差|升贴水|premium|discount|spread", name)
        ):
            category = FinancialCategory.PRICE
            data_nature = DataNature.DIFFERENCE
        subcat = self._subcategory(name, category)
        confidence = self._confidence(name, item.detected_frequency, category, data_nature)
        response = ClassificationResponse(
            variable_id=item.variable_id,
            standard_name=item.original_name,
            industry="METALS" if commodity else None,
            sector=None,
            commodity=commodity,
            category_level_1=category,
            category_level_2=subcat,
            metric_name=item.original_name,
            data_nature=data_nature,
            market="CN" if re.search(r"中国|china|上期所|shfe|沪", name) else None,
            region="CN" if re.search(r"中国|china|上期所|shfe|沪", name) else None,
            unit=item.unit_hint,
            statistical_scope=None,
            confidence=confidence,
            review_reasons=(
                [] if category != FinancialCategory.UNKNOWN else ["UNKNOWN_SEMANTICS"]
            ),
            is_derived=False,
            parent_metric=None,
            reason=f"Mock provider classified as {category.value}.",
        )
        response.comparison_group_components = {
            "standard_name": response.standard_name,
            "industry": response.industry,
            "sector": response.sector,
            "commodity": response.commodity,
            "category_level_1": response.category_level_1.value,
            "category_level_2": response.category_level_2,
            "data_nature": response.data_nature.value,
            "market": response.market,
            "region": response.region,
            "unit": response.unit,
        }
        return response

    @staticmethod
    def _is_price_unit(unit: str | None) -> bool:
        if not unit:
            return False
        u = str(unit).strip().lower()
        return any(token in u for token in ("元/吨", "美元/吨", "元/公斤", "元/千克", "元/磅", "美元/磅", "元/手", "元/吨含税", "元/吨税后"))

    @staticmethod
    def _semantics(name: str) -> tuple[FinancialCategory, DataNature]:
        if re.search(r"pmi|美元指数|usd index|制造业|manufacturing|宏观|GDP|CPI|经济|货币|利率", name):
            return FinancialCategory.MACRO, DataNature.INDEX
        if re.search(r"库存指数|仓单指数|inventory index", name):
            return FinancialCategory.INVENTORY, DataNature.INDEX
        if re.search(r"指数|index", name):
            return FinancialCategory.INDEX, DataNature.INDEX
        if re.search(r"开工率|产能|产能利用率|capacity|operating", name):
            return FinancialCategory.CAPACITY, DataNature.RATIO
        if re.search(r"库存|inventory|仓单|warehouse|显性库存", name):
            return FinancialCategory.INVENTORY, DataNature.STOCK
        if re.search(r"升贴水|premium|discount|spread|价差|基差|月差", name):
            return FinancialCategory.PRICE, DataNature.DIFFERENCE
        if re.search(r"价格|price|收盘|close|现货|spot|均价|LME|SHFE|结算价|报价", name):
            return FinancialCategory.PRICE, DataNature.LEVEL
        if re.search(r"产量|production|output|进口|import|出口|export|销量|volume|需求|demand|消费|consumption|平衡|balance|成交|持仓|position|装机|出货|发运", name):
            return FinancialCategory.QUANTITY, DataNature.FLOW
        if re.search(r"利润|profit|成本|cost|加工费|margin|亏损|盈亏", name):
            return FinancialCategory.COST, DataNature.RATIO
        if re.search(r"收入|revenue|营收|净利", name):
            return FinancialCategory.FINANCIAL, DataNature.LEVEL
        if re.search(r"pe|pb|eps|市盈率|市净率", name):
            return FinancialCategory.FUNDAMENTAL, DataNature.RATIO
        if re.search(r"储量|reserve|resource", name):
            return FinancialCategory.FUNDAMENTAL, DataNature.STOCK
        if re.search(r"天数|days", name):
            return FinancialCategory.INVENTORY, DataNature.RATIO
        if re.search(r"预测|forecast|预估", name):
            return FinancialCategory.QUANTITY, DataNature.LEVEL
        if re.search(r"总计|合计|小计", name):
            return FinancialCategory.QUANTITY, DataNature.AGGREGATE
        return FinancialCategory.UNKNOWN, DataNature.UNKNOWN

    @staticmethod
    def _commodity(name: str) -> str | None:
        pairs = (
            ("TIN", re.compile(r"锡|tin")),
            ("CRUDE_OIL", re.compile(r"原油|crude|oil")),
            ("NATURAL_GAS", re.compile(r"天然气|natural gas")),
            ("STEEL", re.compile(r"钢|steel")),
            ("LITHIUM", re.compile(r"锂|lithium")),
            ("CEMENT", re.compile(r"水泥|cement")),
        )
        for commodity, pattern in pairs:
            if pattern.search(name):
                return commodity
        return None

    @staticmethod
    def _subcategory(name: str, category: FinancialCategory) -> str:
        if category == FinancialCategory.PRICE:
            if re.search(r"期现价差|期现", name):
                return "BASIS"
            if re.search(r"盈亏|价差|基差|月差|spread|basis", name):
                return "Spread"
            if re.search(r"升贴水|premium|discount", name):
                return "Spread"
            if re.search(r"主力合约|一月|二月|三月|四月|五月|六月|七月|八月|九月|十月|十一月|十二月|01合约|05合约|09合约", name):
                return "FUTURES_PRICE"
            return "Price"
        if category == FinancialCategory.QUANTITY:
            if re.search(r"交易者数量", name):
                return "POSITION"
            if re.search(r"销量|sales", name):
                return "DEMAND"
            if re.search(r"产量|production|output", name):
                return "SUPPLY"
            if re.search(r"进口|import", name):
                return "IMPORT"
            if re.search(r"出口|export", name):
                return "EXPORT"
            if re.search(r"成交|volume|交易量", name):
                return "VOLUME"
            if re.search(r"持仓|position", name):
                return "POSITION"
            if re.search(r"需求|demand|消费|消费量", name):
                return "DEMAND"
            if re.search(r"平衡|balance", name):
                return "BALANCE"
            return "Quantity"
        if category == FinancialCategory.INVENTORY:
            if re.search(r"仓单|warehouse", name):
                return "WAREHOUSE_RECEIPT"
            if re.search(r"库存天数|天数|days", name):
                return "INVENTORY_DAYS"
            if re.search(r"库存指数|inventory index", name):
                return "INVENTORY_INDEX"
            return "Inventory"
        if category == FinancialCategory.CAPACITY:
            if re.search(r"开工|operating", name):
                return "OPERATING_RATE"
            return "Capacity"
        if category == FinancialCategory.COST:
            return "COST_PROFIT"
        if category == FinancialCategory.MARGIN:
            return "COST_PROFIT"
        return category.value.title()

    @staticmethod
    def _confidence(
        name: str,
        detected_frequency: str,
        category: FinancialCategory,
        data_nature: DataNature,
    ) -> float:
        if category == FinancialCategory.UNKNOWN:
            return 0.2
        # Base confidence by category priority per Word rules (Rule 1: price > quantity etc.)
        priority_base = {
            FinancialCategory.PRICE: 0.92,
            FinancialCategory.QUANTITY: 0.85,
            FinancialCategory.INVENTORY: 0.80,
            FinancialCategory.CAPACITY: 0.75,
            FinancialCategory.COST: 0.72,
            FinancialCategory.MARGIN: 0.72,
            FinancialCategory.FINANCIAL: 0.65,
            FinancialCategory.FUNDAMENTAL: 0.60,
            FinancialCategory.MACRO: 0.55,
            FinancialCategory.INDEX: 0.50,
        }
        base = priority_base.get(category, 0.55)
        # Adjust by frequency match (Rule 2)
        freq = str(detected_frequency or "").lower()
        if freq == "daily":
            base += 0.03
        elif freq == "weekly":
            base += 0.01
        elif freq == "monthly":
            base -= 0.02
        elif freq in ("quarterly", "annual"):
            base -= 0.05
        # Adjust by contract keywords (Rule 3)
        if category == FinancialCategory.PRICE:
            if re.search(r"主力合约|主连", name):
                base += 0.03
            if re.search(r"01合约|02合约|03合约|04合约|05合约|06合约|07合约|08合约|09合约|10合约|11合约|12合约", name):
                base += 0.02
            if re.search(r"一月合约|二月合约|三月合约|四月合约|五月合约|六月合约|七月合约|八月合约|九月合约|十月合约|十一月合约|十二月合约", name):
                base += 0.02
            if re.search(r"现货|spot", name):
                base += 0.01
        # Clamp
        return round(min(base, 0.95), 2)
