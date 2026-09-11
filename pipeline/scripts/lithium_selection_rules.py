# -*- coding: utf-8 -*-
"""Lithium-specific deterministic selection rules.

Used after Skill2's common selection rules to override 是否选中 for the
lithium industry chain.
"""

from __future__ import annotations

import re
from collections import defaultdict

from catalog_utils import resolve_annualized_frequency
from selection_utils import CONTRACT_PATTERN, frequency_comparison_key, normalize_metric_title


FREQ_RANK = {
    "日度": 4,
    "周度": 3,
    "月度": 2,
    "季度": 1,
    "年度": 0,
}

FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")

_MONTH_ALIASES = (
    ("十二月", "12"),
    ("十一月", "11"),
    ("十月", "10"),
    ("九月", "09"),
    ("八月", "08"),
    ("七月", "07"),
    ("六月", "06"),
    ("五月", "05"),
    ("四月", "04"),
    ("三月", "03"),
    ("二月", "02"),
    ("一月", "01"),
)

SPREAD_KEEP = ("01-05", "05-09", "09-01")


def actual_frequency(title: str, fallback: str = "") -> str:
    annualized = resolve_annualized_frequency(title or "")
    if annualized:
        return annualized
    for suffix in FREQ_SUFFIXES:
        if title.endswith(suffix):
            return suffix
    return fallback or "日度"


def metric_base(title: str) -> str:
    for suffix in FREQ_SUFFIXES:
        if title.endswith(suffix):
            base = title[: -len(suffix)].strip().rstrip(":").strip()
            return _normalize_metric_base(base)
    return _normalize_metric_base(title.strip())


def _normalize_metric_base(base: str) -> str:
    return normalize_metric_title(base)


def is_total_import_export(title: str) -> bool:
    if any(token in title for token in ("总计", "合计", "总量", "净出口")):
        return True
    base = title.strip()
    for suffix in FREQ_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip().rstrip(":").strip()
    if base.count(":") > 1:
        return False
    if "其他" in title:
        return False
    return "进口" in base or "出口" in base


def _storage_ratio_key(title: str) -> str | None:
    text = str(title or "").strip()
    if "储能电芯库销比" not in text:
        return None
    return metric_base(text.replace("总计", "").replace("合计", ""))


def evaluate_selection(
    major: str,
    sub: str,
    title: str,
    frequency: str,
) -> tuple[bool, str]:
    freq = actual_frequency(title, frequency)

    if major == "价格":
        if sub == "基差" or "基差" in title or "期现" in title:
            if "现货-期货" in title:
                return True, "期现价差（现货-期货）保留"
            if "当月合约" in title or "现货升贴水" in title:
                return True, "基差仅保留当月期现/现货升贴水"
            return False, "基差仅保留当月期现/现货升贴水"
        if sub in ("期货价格", "成交量", "持仓") or "期货" in title:
            return bool(CONTRACT_PATTERN.search(title)), "价格仅保留主力/01/05/09/当月合约"
        if sub == "月差" or "月差" in title:
            return any(token in title for token in SPREAD_KEEP), "月差仅保留01-05/05-09/09-01"
        if sub == "成交持仓比":
            return True, "成交持仓比全部保留"
        if sub == "现货价格":
            return True, "现货价格按最高频后置处理"
        return freq in ("日度", "周度", "月度"), "价格仅保留日度/周度/月度"

    if major == "成本利润":
        return True, "成本利润按最高频后置处理"

    if major in ("库存", "供需-库存"):
        if sub == "仓单" or "仓单" in title:
            return True, "仓单全部保留"
        return freq in ("周度", "月度"), "库存仅保留周度/月度"

    if major in ("供给", "供需-供给"):
        return freq in ("日度", "周度", "月度"), "供给仅保留日度/周度/月度"

    if major in ("需求", "供需-需求"):
        return freq in ("日度", "周度", "月度"), "需求仅保留日度/周度/月度"

    if major in ("进出口", "供需-进出口"):
        return freq == "月度" and is_total_import_export(title), "进出口仅保留总量月度"

    if major in ("平衡", "供需-平衡"):
        return True, "平衡类保留"

    if major == "其他" and sub in ("成交量", "持仓量"):
        return bool(CONTRACT_PATTERN.search(title)), "量价仅保留主力/01/05/09合约"

    return False, "规则未覆盖，默认不选中"


def select_rows(rows: list[dict]) -> list[dict]:
    rows = [dict(row) for row in rows]
    selected_by_rule: set[int] = set()
    for idx, row in enumerate(rows):
        selected, reason = evaluate_selection(
            row["major"],
            row["sub"],
            row["title"],
            row["frequency"],
        )
        row["selected"] = selected
        row["reason"] = reason
        if "电解铜" in row["title"] or "电解铜" in str(row.get("sheet") or ""):
            row["selected"] = False
            row["reason"] = "锂电专属规则：电解铜指标不保留"
        if selected:
            selected_by_rule.add(idx)

    cost_groups: dict[tuple, list[int]] = defaultdict(list)
    spot_groups: dict[tuple, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row["major"] == "成本利润" and row.get("selected"):
            cost_groups[frequency_comparison_key(row)].append(idx)
        if row["major"] == "价格" and row["sub"] == "现货价格" and row.get("selected"):
            spot_groups[frequency_comparison_key(row)].append(idx)

    for indices in cost_groups.values():
        if not indices:
            continue
        ranks = [
            (FREQ_RANK.get(actual_frequency(rows[i]["title"], rows[i]["frequency"]), -1), i)
            for i in indices
        ]
        best_rank = max(rank for rank, _ in ranks)
        kept = False
        for idx in indices:
            rank = FREQ_RANK.get(
                actual_frequency(rows[idx]["title"], rows[idx]["frequency"]), -1
            )
            if rank == best_rank:
                rows[idx]["selected"] = True
                rows[idx]["reason"] = "成本利润仅保留最高频"
                if kept:
                    rows[idx]["selected"] = False
                    rows[idx]["reason"] = "成本利润同频重复，只保留一条"
                kept = True
            else:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = "成本利润仅保留最高频"

    for indices in spot_groups.values():
        if not indices:
            continue
        ranks = [
            (FREQ_RANK.get(actual_frequency(rows[i]["title"], rows[i]["frequency"]), -1), i)
            for i in indices
        ]
        best_rank = max(rank for rank, _ in ranks)
        kept = False
        for idx in indices:
            rank = FREQ_RANK.get(
                actual_frequency(rows[idx]["title"], rows[idx]["frequency"]), -1
            )
            if rank == best_rank:
                rows[idx]["selected"] = True
                rows[idx]["reason"] = "现货价格仅保留最高频"
                if kept:
                    rows[idx]["selected"] = False
                    rows[idx]["reason"] = "现货价格同频重复，只保留一条"
                kept = True
            else:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = "现货价格仅保留最高频"

    storage_ratio_groups: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        key = _storage_ratio_key(row.get("title") or "")
        if key and row.get("selected"):
            storage_ratio_groups[key].append(idx)

    for indices in storage_ratio_groups.values():
        kept = False
        for idx in indices:
            if kept:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = "锂电专属规则：储能电芯库销比重复，只保留一条"
            else:
                kept = True

    return rows
