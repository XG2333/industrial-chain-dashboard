# -*- coding: utf-8 -*-
"""Deterministic candidate detection for major/sub classification.

The rules do not use an early-return priority chain. They collect every
matching candidate from the indicator name first, then fall back to the sheet
name. Ambiguous rows can be sent to AI for disambiguation.
"""

from __future__ import annotations

import re


AMOUNT_MARKERS = (
    "进口额",
    "出口额",
    "净出口额",
    "进口总额",
    "出口总额",
    "净出口总额",
    "进口金额",
    "出口金额",
    "净出口金额",
    "总额",
    "总值",
    "金额",
)

_PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")
_ANNOTATION_RATIO_TOKENS = ("市占率", "覆盖率", "市场覆盖", "样本代表性")
_RATIO_MEASURE_TOKENS = ("CR5", "占比", "市占率", "集中度", "覆盖率")
_RATIO_SUB_LABELS = ("市占率", "集中度", "渗透率", "库销比", "成交持仓比")
_RATIO_UNITS = ("%", "％", "百分比", "比例", "ratio")


MAJOR_KEYWORD_GROUPS = {
    "平衡": ("平衡",),
    "成本利润": ("成本", "利润", "毛利率", "盈亏"),
    "进出口": ("进出口", "进口", "出口", "出港", "到港", "贸易流向", "净出口", "发货量", "航运"),
    "库存": ("库存", "仓单", "库容", "库销比", "库存天数", "库存周期"),
    "供给": (
        "产量", "产能", "开工", "排产", "自给率", "储量",
        "市占率", "供应", "冶炼", "CR5", "集中度", "出货情绪", "加工费",
    ),
    "需求": (
        "需求", "消费", "销量", "装机", "招标", "中标", "上险",
        "保有量", "带电量", "渗透率", "装车", "充电桩", "换电站",
        "批发", "零售", "消耗量", "配储", "要求", "建成规模", "出货量",
        "工商业储能", "购货情绪", "成交情绪",
    ),
    "价格": (
        "价格", "平均价", "均价", "售价", "基差", "价差", "月差",
        "收盘价", "结算价", "指数", "现货", "期货",
        "CIF", "FOB", "升贴水", "溢价", "成交量", "成交持仓比", "持仓",
        *AMOUNT_MARKERS,
    ),
}


SUB_KEYWORD_GROUPS = {
    "价格": {
        "成交量": ("成交量",),
        "成交持仓比": ("成交持仓比",),
        "持仓": ("持仓",),
        "月差": ("月差",),
        "期货价格": ("期货价格", "期货", "收盘价", "结算价"),
        "价差": ("价差", "升贴水", "溢价", "基差", "期现"),
        "指数": ("指数",),
        "现货价格": ("现货", "平均价", "均价", "价格"),
        "贸易金额": AMOUNT_MARKERS,
    },
    "成本利润": {
        "利润": ("利润", "毛利率", "盈亏"),
        "成本": ("成本",),
    },
    "库存": {
        "仓单": ("仓单",),
        "库容": ("库容",),
        "库存天数": ("库存天数", "天数"),
        "库销比": ("库销比",),
        "库存指数": ("库存指数", "指数"),
        "库存周期": ("库存周期",),
        "库存": ("库存",),
    },
    "进出口": {
        "净出口": ("净出口",),
        "进出口": ("进出口",),
        "进口": ("进口", "到港", "进口量", "进口额", "进口数量"),
        "出口": ("出口", "出港", "出口量", "出口额", "出口数量"),
        "贸易流向": ("贸易流向",),
    },
    "需求": {
        "销量": ("销量", "上险量", "批发零售"),
        "出货量": ("出货量",),
        "装机": ("装机",),
        "招标": ("招标",),
        "中标": ("中标",),
        "保有量": ("保有量",),
        "渗透率": ("渗透率",),
        "带电量": ("带电量",),
        "充电基础设施": ("充电桩", "换电站"),
        "政策要求": ("配储", "要求"),
        "消耗量": ("消耗量",),
        "需求": ("需求",),
    },
    "供给": {
        "产量": ("产量", "排产"),
        "产能": ("产能",),
        "开工率": ("开工",),
        "自给率": ("自给率",),
        "储量": ("储量",),
        "市占率": ("市占率",),
        "集中度": ("CR5", "集中度"),
        "数量": ("供应量", "数量"),
        "冶炼": ("冶炼",),
        "建成规模": ("建成规模",),
        "供给": ("供给",),
        "加工费": ("加工费",),
    },
    "平衡": {
        "平衡": ("平衡",),
    },
}


SILICON_MAJOR_KEYWORD_GROUPS = {
    "平衡": ("平衡", "平衡值"),
    "成本利润": (
        "成本", "利润", "毛利率", "盈亏", "LCOE", "lcoe", "折旧", "人工",
        "三费", "投资", "运维", "初始投资", "电耗", "水耗", "综合能耗",
        "耗量", "消耗", "浆料", "银浆", "费用", "运费", "损耗", "辅料",
    ),
    "进出口": ("进出口", "进口", "出口", "净出口", "出港", "到港", "贸易流向"),
    "库存": ("库存", "仓单", "库容", "库销比", "库存天数", "库存周期"),
    "供给": (
        "产量", "产能", "开工", "排产", "自给率", "储量",
        "市占率", "供应", "冶炼", "发电量", "供应量", "加工费",
    ),
    "需求": (
        "需求", "消费", "销量", "装机", "招标", "中标", "上险",
        "保有量", "带电量", "渗透率", "装车", "充电桩", "换电站",
        "批发", "零售", "消耗量", "配储", "要求", "建成规模", "出货量",
        "工商业储能", "购货情绪", "成交情绪", "用电量", "消纳", "出货",
    ),
    "价格": (
        "价格", "平均价", "均价", "售价", "基差", "价差", "月差",
        "收盘价", "结算价", "指数", "现货", "期货",
        "CIF", "FOB", "升贴水", "溢价", "电价", "低价", "高价",
        "自提价", "中标均价", "成交量", "成交持仓比", "持仓",
        *AMOUNT_MARKERS,
    ),
}


SILICON_SUB_KEYWORD_GROUPS = {
    "价格": {
        "成交量": ("成交量",),
        "成交持仓比": ("成交持仓比",),
        "持仓": ("持仓",),
        "月差": ("月差",),
        "现货价差": ("价差", "升贴水", "溢价", "基差", "期现", "期现价差"),
        "期货价格": ("期货价格", "期货", "收盘价", "结算价"),
        "现货价格": (
            "现货", "平均价", "均价", "价格", "电价", "低价", "高价",
            "CIF", "FOB", "自提价", "中标均价",
        ),
        "贸易金额": AMOUNT_MARKERS,
    },
    "成本利润": {
        "利润": ("利润", "毛利率", "盈亏"),
        "成本": ("成本",),
    },
    "库存": {
        "仓单": ("仓单",),
        "库存指数": ("库存指数",),
        "库存天数": ("库存天数",),
        "库存": ("库存",),
    },
    "进出口": {
        "净出口": ("净出口",),
        "进出口": ("进出口",),
        "进口": ("进口", "到港", "进口量", "进口额", "进口数量"),
        "出口": ("出口", "出港", "出口量", "出口额", "出口数量"),
    },
    "供给": {
        "产量": ("产量", "发电量", "排产"),
        "产能": ("产能",),
        "开工率": ("开工",),
        "数量": ("供应量", "数量"),
        "供给": ("供应", "自给率", "市占率", "储量", "冶炼"),
        "加工费": ("加工费",),
    },
    "平衡": {
        "平衡": ("平衡",),
    },
    "需求": {
        "销量": ("销量", "出货"),
        "出货量": ("出货量",),
        "装机": ("装机",),
        "需求": ("需求", "消费", "消纳", "用电量"),
    },
}


def _groups_for_industry(industry: str):
    if industry == "silicon":
        return SILICON_MAJOR_KEYWORD_GROUPS, SILICON_SUB_KEYWORD_GROUPS
    return MAJOR_KEYWORD_GROUPS, SUB_KEYWORD_GROUPS


def _unique_hits(groups: dict[str, tuple[str, ...]], text: str) -> list[str]:
    hits: list[str] = []
    for label, keywords in groups.items():
        if any(k in text for k in keywords):
            hits.append(label)
    return hits


def _strip_parentheses(text: str) -> str:
    return _PAREN_RE.sub("", text or "")


def _parenthetical_text(text: str) -> str:
    return " ".join(_PAREN_RE.findall(text or ""))


def major_candidates(name: str, sheet: str, industry: str = "lithium_tin") -> list[str]:
    major_groups, _ = _groups_for_industry(industry)
    hits = _unique_hits(major_groups, name or "")
    if hits:
        main_text = _strip_parentheses(name or "")
        main_hits = _unique_hits(major_groups, main_text)
        if main_hits:
            paren_text = _parenthetical_text(name or "")
            if paren_text and any(token in paren_text for token in _ANNOTATION_RATIO_TOKENS):
                annotation_hits = _unique_hits(major_groups, paren_text)
                hits = [h for h in hits if not (h in annotation_hits and h not in main_hits)]
        return hits
    return _unique_hits(major_groups, sheet or "")


def sub_candidates(
    major: str,
    name: str,
    sheet: str,
    industry: str = "lithium_tin",
    unit: str = "",
) -> list[str]:
    _, sub_groups = _groups_for_industry(industry)
    groups = sub_groups.get(major)
    if not groups:
        return []
    hits = _unique_hits(groups, name or "")
    if hits:
        if major == "进出口" and any(token in (name or "") for token in ("净出口", "净进口")):
            return ["净出口"]
        main_text = _strip_parentheses(name or "")
        main_hits = _unique_hits(groups, main_text)
        if main_hits:
            paren_text = _parenthetical_text(name or "")
            if paren_text and any(token in paren_text for token in _ANNOTATION_RATIO_TOKENS):
                annotation_hits = _unique_hits(groups, paren_text)
                hits = [h for h in hits if not (h in annotation_hits and h not in main_hits)]
            if any(token in main_text for token in _RATIO_MEASURE_TOKENS) and (
                not unit or any(token in unit for token in _RATIO_UNITS)
            ):
                ratio_hits = [h for h in hits if h in _RATIO_SUB_LABELS]
                if ratio_hits:
                    return ratio_hits
        return hits
    return _unique_hits(groups, sheet or "")


# Deterministic subcategory priority for non-price majors, aligned with the
# sorter's SUB_ORDER. When a name hits multiple subcategory keywords of the
# same major (e.g. 氢氧化锂冶炼端产能 hits both 产能 and 冶炼), the first
# match wins instead of falling back to 其他.
SUB_PRIORITY = {
    "供给": ("产能", "集中度", "产量", "开工率", "加工费", "冶炼", "自给率", "数量", "储量", "供给"),
    "库存": ("仓单", "库容", "库存天数", "库销比", "库存指数", "库存周期", "库存"),
    "需求": ("需求", "销量", "装机", "招标", "中标", "保有量", "带电量", "渗透率", "充电基础设施", "政策要求", "消耗量", "出货量"),
    "成本利润": ("成本", "利润"),
    "进出口": ("进出口", "净出口", "进口", "出口"),
    "平衡": ("平衡",),
}


PRICE_SUB_PRIORITY = {
    "silicon": (
        "成交持仓比",
        "成交量",
        "持仓",
        "月差",
        "贸易金额",
        "现货价差",
        "期货价格",
        "现货价格",
    ),
    "generic": (
        "成交持仓比",
        "成交量",
        "持仓",
        "月差",
        "贸易金额",
        "价差",
        "指数",
        "现货价格",
        "期货价格",
    ),
}


def deterministic_price_sub(name: str, sheet: str, industry: str = "lithium_tin") -> str | None:
    """Pick one price subclass deterministically when multiple keywords hit."""
    subs = sub_candidates("价格", name or "", sheet or "", industry)
    if not subs:
        return None
    priority = PRICE_SUB_PRIORITY.get(industry, PRICE_SUB_PRIORITY["generic"])
    for label in priority:
        if label in subs:
            return label
    return subs[0]


def candidate_plan(
    name: str,
    sheet: str,
    industry: str = "lithium_tin",
    unit: str = "",
) -> dict:
    """Return deterministic choices plus all candidate combinations for AI fallback."""
    major_cands = major_candidates(name or "", sheet or "", industry)
    if "平衡" in major_cands:
        major_cands = ["平衡"]
    if "成本利润" in major_cands and any(
        token in (name or "") for token in ("利润", "毛利率", "盈亏")
    ):
        major_cands = ["成本利润"]
    if "供给" in major_cands and "价格" in major_cands and "加工费" in (name or sheet or ""):
        major_cands = ["供给"]
    # Trade keywords such as 进口/出口 often co-occur with 均价/价格. In that
    # case the indicator is a price observation, not a trade-flow volume.
    if "进出口" in major_cands and "价格" in major_cands:
        major_cands = ["价格"]
    # "消费" in product-grade names such as 消费人造石墨/消费电池 is a product
    # attribute, not a demand flow. Prefer price when the name is a price
    # observation and the unit is price-like or unknown.
    if "需求" in major_cands and "价格" in major_cands:
        name_text = name or ""
        if "消费" in name_text and not any(
            token in name_text
            for token in ("消费量", "消费需求", "消耗量", "表观消费", "消费总量")
        ):
            if any(
                token in name_text
                for token in ("平均价", "均价", "价格", "收盘价", "结算价", "CIF", "FOB", "低价", "高价")
            ):
                if not unit or any(token in unit for token in ("元/", "美元/", "欧元/")):
                    major_cands = ["价格"]
    # Cost rows that also hit price keywords (e.g. 生产成本（FOB）) are cost
    # observations, not price quotes.
    if "成本利润" in major_cands and "价格" in major_cands and "成本" in (name or ""):
        major_cands = ["成本利润"]
    # 库存指数/库存周期/库容/库存天数/库存预警 are inventory observations;
    # the co-occurring "指数/期货" keyword is not a price flow.
    if "库存" in major_cands and "价格" in major_cands and any(
        token in (name or "")
        for token in ("库存指数", "库存周期", "库容", "库存天数", "库存预警")
    ):
        major_cands = ["库存"]
    # 冶炼厂/冶炼法 as a location/process qualifier must not turn an
    # inventory or cost row into a supply row.
    if "库存" in major_cands and "供给" in major_cands and "冶炼" in (name or ""):
        major_cands = ["库存"]
    if "成本利润" in major_cands and "供给" in major_cands and "冶炼" in (name or ""):
        major_cands = ["成本利润"]
    # Cost rows that mention 进口/出口 (e.g. 进口原料, 进口成本) are cost
    # observations, not trade flows.
    if "成本利润" in major_cands and "进出口" in major_cands:
        major_cands = ["成本利润"]
    # "消费" in product-grade names (消费电芯/消费型/加工费) co-occurring with
    # supply or cost keywords is a product attribute, not a demand flow.
    if "需求" in major_cands and "供给" in major_cands and "消费" in (name or ""):
        major_cands = ["供给"]
    if "需求" in major_cands and "成本利润" in major_cands and "消费" in (name or ""):
        major_cands = ["成本利润"]
    # 中标均价/工商业储能/储能系统 are price observations whose demand-side
    # keywords (中标/储能) are auction or product attributes.
    if "需求" in major_cands and "价格" in major_cands and any(
        token in (name or "") for token in ("中标", "工商业储能", "储能系统", "储能EPC")
    ):
        major_cands = ["价格"]
    # 消耗量-based indices are demand observations.
    if "需求" in major_cands and "价格" in major_cands and "消耗量" in (name or ""):
        major_cands = ["需求"]
    # 销量 with a channel qualifier (销量: 出口) is a demand observation.
    if "需求" in major_cands and "进出口" in major_cands and "销量" in (name or ""):
        major_cands = ["需求"]
    if not major_cands:
        return {
            "major": "其他",
            "sub": "其他",
            "major_candidates": [],
            "sub_candidates": [],
            "combinations": [],
        }

    combinations: list[dict[str, str]] = []
    sub_union: list[str] = []
    for major in major_cands:
        subs = sub_candidates(major, name or "", sheet or "", industry, unit)
        if subs:
            for sub in subs:
                combinations.append({"大类": major, "子类": sub})
                if sub not in sub_union:
                    sub_union.append(sub)
        else:
            combinations.append({"大类": major, "子类": "其他"})

    if len(major_cands) == 1:
        major = major_cands[0]
        if major == "价格":
            deterministic_sub = deterministic_price_sub(name or "", sheet or "", industry)
            if deterministic_sub:
                return {
                    "major": major,
                    "sub": deterministic_sub,
                    "major_candidates": major_cands,
                    "sub_candidates": sub_union,
                    "combinations": combinations,
                }
        sub_priority = SUB_PRIORITY.get(major)
        if sub_priority:
            for label in sub_priority:
                if label in sub_union:
                    return {
                        "major": major,
                        "sub": label,
                        "major_candidates": major_cands,
                        "sub_candidates": sub_union,
                        "combinations": combinations,
                    }
        if len(combinations) == 1 and combinations[0]["子类"] != "其他":
            return {
                "major": major,
                "sub": combinations[0]["子类"],
                "major_candidates": major_cands,
                "sub_candidates": sub_union,
                "combinations": combinations,
            }
        return {
            "major": major,
            "sub": "其他",
            "major_candidates": major_cands,
            "sub_candidates": sub_union,
            "combinations": combinations,
        }

    return {
        "major": "其他",
        "sub": "其他",
        "major_candidates": major_cands,
        "sub_candidates": sub_union,
        "combinations": combinations,
    }
