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
    return normalize_metric_title(title)


def is_total_import_export(title: str, sheet: str = "") -> bool:
    if any(token in title for token in ("总计", "合计", "总量", "净出口")):
        return True
    if "分国别" in sheet or "分国家" in sheet:
        return False
    base = title.strip()
    for suffix in FREQ_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip().rstrip(":").strip()
    if base.count(":") > 1:
        return False
    if "_其他" in title or base.endswith(": 其他") or base.endswith("其他"):
        return False
    return "进口" in base or "出口" in base


def evaluate_selection(
    major: str,
    sub: str,
    title: str,
    frequency: str,
    sheet: str = "",
) -> tuple[bool, str]:
    freq = actual_frequency(title, frequency)

    if major == "价格":
        if sub == "期货价格":
            return bool(CONTRACT_PATTERN.search(title)), "价格仅保留主力/01/05/09合约"
        if sub == "成交持仓比":
            return True, "成交持仓比全部保留"
        if sub == "持仓":
            if "成交持仓比" in title and not CONTRACT_PATTERN.search(title):
                return True, "持仓/成交持仓比（总量）全部保留"
            return bool(CONTRACT_PATTERN.search(title)), "持仓仅保留主力/01/05/09合约"
        if sub == "月差":
            return any(token in title for token in SPREAD_KEEP), "月差仅保留01-05/05-09/09-01"
        if sub == "基差" or "基差" in title or "期现" in title:
            return "当月合约" in title or "现货升贴水" in title, "基差仅保留当月期现或现货升贴水"
        if sub == "现货价差" or "价差" in title or "升贴水" in title:
            return True, "现货价差全部保留"
        if sub == "成交量":
            return bool(CONTRACT_PATTERN.search(title)), "成交量仅保留主力/01/05/09合约"
        if sub == "现货价格":
            return True, "现货价格按最高频后置处理"
        return False, "价格规则未覆盖，默认不选中"

    if major == "成本利润":
        return True, "成本利润按最高频后置处理"

    if major == "库存":
        if sub == "仓单":
            if "分仓库" in title and freq == "日度":
                return True, "仓单分仓库日度"
            if "仓单日报" in title and "今日仓单量" in title and "增减" not in title:
                return True, "总仓单保留"
            return False, "仓单仅保留分仓库日度或总仓单"
        return freq in ("周度", "月度"), "库存仅保留周度/月度"

    if major == "供给":
        return freq in ("日度", "周度", "月度"), "供给仅保留日度/周度/月度"

    if major == "需求":
        return freq in ("日度", "周度", "月度"), "需求仅保留日度/周度/月度"

    if major == "进出口":
        return freq == "月度" and is_total_import_export(title, sheet), "进出口仅保留总量月度"


    if major == "平衡":
        return freq in ("日度", "周度", "月度"), "平衡仅保留日度/周度/月度"

    return False, "规则未覆盖，默认不选中"


def select_rows(rows: list[dict]) -> list[dict]:
    rows = [dict(row) for row in rows]
    for idx, row in enumerate(rows):
        selected, reason = evaluate_selection(
            row.get("major", ""),
            row.get("sub", ""),
            row.get("title", ""),
            row.get("frequency", ""),
            row.get("sheet", ""),
        )
        row["selected"] = selected
        row["reason"] = reason

    cost_groups: dict[tuple, list[int]] = defaultdict(list)
    spot_groups: dict[tuple, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row.get("major") == "成本利润" and row.get("selected"):
            cost_groups[frequency_comparison_key(row)].append(idx)
        if (
            row.get("major") == "价格"
            and row.get("sub") in ("现货价格", "成交量")
            and row.get("selected")
        ):
            spot_groups[frequency_comparison_key(row)].append(idx)

    for indices in cost_groups.values():
        if not indices:
            continue
        ranks = [
            (
                FREQ_RANK.get(
                    actual_frequency(
                        rows[i].get("title", ""), rows[i].get("frequency", "")
                    ),
                    -1,
                ),
                i,
            )
            for i in indices
        ]
        best_rank = max(rank for rank, _ in ranks)
        kept = False
        for idx in indices:
            rank = FREQ_RANK.get(
                actual_frequency(
                    rows[idx].get("title", ""), rows[idx].get("frequency", "")
                ),
                -1,
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
            (
                FREQ_RANK.get(
                    actual_frequency(
                        rows[i].get("title", ""), rows[i].get("frequency", "")
                    ),
                    -1,
                ),
                i,
            )
            for i in indices
        ]
        best_rank = max(rank for rank, _ in ranks)
        kept = False
        for idx in indices:
            rank = FREQ_RANK.get(
                actual_frequency(
                    rows[idx].get("title", ""), rows[idx].get("frequency", "")
                ),
                -1,
            )
            sub = rows[idx].get("sub", "")
            if rank == best_rank:
                rows[idx]["selected"] = True
                rows[idx]["reason"] = (
                    "成交量仅保留主力/01/05/09合约"
                    if sub == "成交量"
                    else "价格/现价/成交量仅保留最高频"
                )
                if kept:
                    rows[idx]["selected"] = False
                    rows[idx]["reason"] = (
                        "成交量同频重复，只保留一条"
                        if sub == "成交量"
                        else "价格/现价/成交量同频重复，只保留一条"
                    )
                kept = True
            else:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = (
                    "成交量仅保留主力/01/05/09合约"
                    if sub == "成交量"
                    else "价格/现价/成交量仅保留最高频"
                )

    _dedup_import_export(rows)
    _dedup_warehouse(rows)
    return rows


def _scope_key(title: str) -> str:
    for marker in ("分仓库:", "分地区:"):
        idx = title.find(marker)
        if idx >= 0:
            tail = title[idx + len(marker):]
            return tail.split(":")[0].strip()
    return "TOTAL"


def _warehouse_key(title: str) -> str | None:
    marker = "分仓库:"
    idx = title.find(marker)
    if idx < 0:
        return None
    tail = title[idx + len(marker):]
    return tail.split(":")[0].strip()


def _ie_normalize(title: str) -> str:
    t = title
    for prefix in ("中国海关: ", "美国海关: ", "SMM: ", "NBS: ", "CPIA: ", "英国石油: ", "公开数据: "):
        t = t.replace(prefix, "")
    for suffix in ("进口量", "出口量", "进口额", "出口额", "净出口", "进口", "出口"):
        t = t.replace(suffix, "")
    for suffix in ("-月", "-日", "-周", "-年", "-季", "月度", "日度", "周度", "年度", "季度", "月", "日", "周", "年", "季"):
        if t.endswith(suffix):
            t = t[:-len(suffix)]
    t = t.strip(" :_")
    for token in ("合计", "总计", "总量", "总"):
        t = t.replace(token, "")
    t = t.strip(" :_")
    t = t.replace("工业硅", "金属硅")
    t = t.replace("光伏电池", "电池片")
    return t

def _dedup_import_export(rows: list[dict]) -> None:
    groups: dict[tuple[str, str], dict] = {}
    for idx, row in enumerate(rows):
        if row.get("major") != "进出口":
            continue
        if not row.get("selected"):
            continue
        title = row.get("title") or ""
        sheet = row.get("sheet") or ""
        key = _ie_normalize(title)
        if not key:
            continue
        gk = (sheet, key)
        groups.setdefault(gk, []).append(idx)

    for (sheet, key), indices in groups.items():
        imps = [i for i in indices if ("进口" in (rows[i].get("title") or "")
                 and "净" not in (rows[i].get("title") or "")
                 and "出口" not in (rows[i].get("title") or ""))]
        exps = [i for i in indices if ("出口" in (rows[i].get("title") or "")
                 and "净" not in (rows[i].get("title") or "")
                 and "进口" not in (rows[i].get("title") or ""))]

        if len(imps) == 0 or len(exps) == 0:
            for i in imps + exps:
                rows[i]["selected"] = False
                rows[i]["reason"] = "进出口无配对（只有进口或只有出口），不选中"
            continue

        if len(imps) > 1:
            imps.sort(key=lambda i: len(rows[i].get("title") or ""), reverse=True)
            for i in imps[1:]:
                rows[i]["selected"] = False
                rows[i]["reason"] = "进出口重复（同一指标多条进口），只保留一条"

        if len(exps) > 1:
            exps.sort(key=lambda i: len(rows[i].get("title") or ""), reverse=True)
            for i in exps[1:]:
                rows[i]["selected"] = False
                rows[i]["reason"] = "进出口重复（同一指标多条出口），只保留一条"



def _dedup_warehouse(rows: list[dict]) -> None:
    warehouse_daily: dict[str, bool] = {}
    for row in rows:
        if row.get("major") == "库存" and row.get("sub") == "仓单":
            key = _warehouse_key(row.get("title") or "")
            if key and row.get("selected"):
                warehouse_daily[key] = True
    for row in rows:
        if row.get("major") == "库存" and row.get("sub") != "仓单" and row.get("selected"):
            key = _warehouse_key(row.get("title") or "")
            if key and warehouse_daily.get(key):
                row["selected"] = False
                row["reason"] = "仓单日度已覆盖同仓库周度库存"

    subtotal_warehouses: set[str] = set()
    for row in rows:
        if row.get("major") == "库存" and row.get("sub") != "仓单" and row.get("selected") and "小计" in (row.get("title") or ""):
            key = _scope_key(row.get("title") or "")
            if key:
                subtotal_warehouses.add(key)
    for row in rows:
        if row.get("major") == "库存" and row.get("sub") != "仓单" and row.get("selected"):
            title = row.get("title") or ""
            if "期货" in title and "小计" not in title:
                key = _scope_key(title)
                if key and key in subtotal_warehouses:
                    row["selected"] = False
                    row["reason"] = "同仓库库存小计已保留，库存期货去重"
