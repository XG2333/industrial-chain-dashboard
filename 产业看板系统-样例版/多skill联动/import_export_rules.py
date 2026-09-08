# -*- coding: utf-8 -*-
"""Generic import/export pairing and net-export rules shared by all chains."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable


FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")
IE_MAJORS = ("进出口", "供需-进出口")


TOTAL_MARKERS = ("总计", "合计", "总量", "累计", "总额", "总")
IE_TOKENS = (
    "净出口",
    "净进口",
    "进口均价",
    "出口均价",
    "进口额",
    "出口额",
    "进口量",
    "出口量",
    "进口",
    "出口",
    "额",
)


NON_TOTAL_IE_MARKERS = (
    "均价",
    "平均价",
    "价格",
    "盈亏",
    "利润",
    "价差",
    "基差",
    "溢价",
    "费用",
    "汇率",
    "调期费",
    "海运费",
    "premium",
    "进口额",
    "出口额",
    "净出口额",
    "进口金额",
    "出口金额",
    "净出口金额",
    "进口总额",
    "出口总额",
    "净出口总额",
    "总额",
    "总值",
    "金额",
)

AMOUNT_MARKERS = (
    "进口额",
    "出口额",
    "净出口额",
    "进口金额",
    "出口金额",
    "净出口金额",
    "进口总额",
    "出口总额",
    "净出口总额",
    "总额",
    "总值",
    "金额",
)


COUNTRY_REGION_MARKERS = (
    "澳大利亚", "日本", "韩国", "美国", "马来西亚", "印度尼西亚", "印尼",
    "印度", "泰国", "越南", "巴西", "秘鲁", "玻利维亚", "缅甸", "老挝",
    "俄罗斯", "尼日利亚", "坦桑尼亚", "卢旺达", "菲律宾", "新加坡", "比利时",
    "荷兰", "德国", "法国", "意大利", "西班牙", "英国", "加拿大", "墨西哥",
    "阿联酋", "沙特", "土耳其", "图尔基耶", "中国台湾", "中国香港",
    "哈萨克斯坦", "哥伦比亚", "加纳", "刚果", "吉尔吉斯斯坦", "委内瑞拉", "其他",
)

FOREIGN_SOURCE_MARKERS = (
    "韩国海关", "韩国", "日本海关", "美国海关", "印尼统计局", "印尼海关",
    "澳大利亚海关", "马来西亚海关", "马拉西亚", "印尼", "海外", "LME", "JFX", "ICDX",
)


def _remove_suffix(value: str, suffixes: Iterable[str]) -> str:
    text = value
    for suffix in suffixes:
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text


def effective_frequency(title: str, fallback: str = "") -> str:
    for suffix in FREQ_SUFFIXES:
        if title.endswith(suffix):
            return suffix
    return fallback


def metric_key(title: str) -> str:
    """Return a normalized product/flow key after removing flow direction and totals."""
    text = str(title or "")
    for token in IE_TOKENS:
        text = text.replace(token, "")
    for suffix in ("-月", "-日", "-周", "-年", "-季", "月度", "日度", "周度", "年度", "季度"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    for token in TOTAL_MARKERS:
        text = text.replace(token, "")
    text = text.replace("中国金属锂", "金属锂")
    text = text.replace(":", " ").replace("  ", " ").strip(" :_-")
    return text


def flow_dimension(title: str) -> str:
    """Keep quantity and value flows separate so 进口量 pairs with 出口量 only."""
    if any(token in title for token in ("进口额", "出口额")):
        return "金额"
    if any(token in title for token in ("进口均价", "出口均价", "均价", "平均价", "价格")):
        return "均价"
    return "数量"


def is_total_import_export(title: str, sheet: str = "") -> bool:
    """Return True only for monthly total import/export rows eligible for pairing."""
    text = str(title or "")
    if any(marker in text for marker in NON_TOTAL_IE_MARKERS):
        return False
    if any(f"_{marker}" in text for marker in COUNTRY_REGION_MARKERS if marker != "其他"):
        return False
    if "_其他" in text or text.strip().endswith(": 其他"):
        return False
    if any(marker in text for marker in FOREIGN_SOURCE_MARKERS) and "中国" in text:
        return False
    if "海外" in sheet or "海外" in text:
        return False
    if any(token in text for token in ("净出口", "净进口", "总计", "合计", "总量", "累计")):
        return any(token in text for token in ("进口", "出口", "净出口", "净进口"))
    if "分国别" in sheet or "分国家" in sheet or "分省份" in sheet:
        return False
    base = text.strip()
    if ": " in base:
        base = base.split(": ", 1)[1]
    base = _remove_suffix(base, FREQ_SUFFIXES)
    if base.count(":") > 1:
        return False
    return "进口" in base or "出口" in base


def net_title(base_key: str, dimension: str, freq: str = "月度") -> str:
    suffix = "额" if dimension == "金额" else ""
    return f"{base_key}净出口{suffix}: {freq}"


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_string(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()[:10]


def compute_net_series(
    workbook,
    import_sheet: str,
    import_col: int,
    export_sheet: str,
    export_col: int,
) -> list[dict]:
    """Align import/export dates and return net export = export - import."""
    import_ws = workbook[import_sheet]
    export_ws = workbook[export_sheet]
    export_values: dict[str, float] = {}
    for row in export_ws.iter_rows(min_row=4):
        date_cell = row[0].value
        if date_cell is None or str(date_cell).strip() == "":
            continue
        exp = _to_number(row[export_col].value) if export_col < len(row) else None
        if exp is None:
            continue
        export_values[_date_string(date_cell)] = exp

    rows = []
    for row in import_ws.iter_rows(min_row=4):
        date_cell = row[0].value
        if date_cell is None or str(date_cell).strip() == "":
            continue
        imp = _to_number(row[import_col].value) if import_col < len(row) else None
        exp = export_values.get(_date_string(date_cell))
        if imp is None or exp is None:
            continue
        rows.append({"date": _date_string(date_cell), "value": round(exp - imp, 4)})
    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows


def find_missing_net_export_pairs(directory_rows: list[dict]) -> list[dict]:
    """Pair same-sheet monthly totals and return pairs that lack a net-export row."""
    by_key: dict[tuple[str, str], dict] = defaultdict(dict)
    net_keys: set[tuple[str, str]] = set()

    for row in directory_rows:
        sheet = str(row.get("sheet") or "")
        title = str(row.get("title") or "")
        major = str(row.get("major") or "")
        freq = str(row.get("frequency") or "")
        if major not in IE_MAJORS or effective_frequency(title, freq) != "月度":
            continue
        if not is_total_import_export(title, sheet):
            continue
        dimension = flow_dimension(title)
        if dimension in ("均价", "金额"):
            continue
        base = metric_key(title)
        if not base:
            continue
        key = (base, dimension)
        if "净出口" in title or "净进口" in title:
            net_keys.add(key)
            continue
        if "进口" in title and "出口" not in title:
            by_key[key].setdefault("import", row)
        if "出口" in title and "进口" not in title:
            by_key[key].setdefault("export", row)

    missing = []
    for key, pair in by_key.items():
        if key in net_keys:
            continue
        if "import" not in pair or "export" not in pair:
            continue
        missing.append(
            {
                "sheet": pair["import"]["sheet"],
                "import_sheet": pair["import"]["sheet"],
                "export_sheet": pair["export"]["sheet"],
                "key": key[0],
                "dimension": key[1],
                "import_row": pair["import"],
                "export_row": pair["export"],
            }
        )
    return missing


def _preferred_duplicate(indices: list[int], rows: list[dict]) -> list[int]:
    indices = sorted(
        indices,
        key=lambda idx: (
            0 if rows[idx].get("sub") not in ("进口", "出口") else 1,
            0 if any(token in (rows[idx].get("title") or "") for token in TOTAL_MARKERS) else 1,
            len(rows[idx].get("title") or ""),
        ),
        reverse=True,
    )
    return indices


def _strip_source_key(key: str) -> str:
    for prefix in ("中国海关", "韩国海关", "日本海关", "美国海关", "SMM", "NBS", "CPIA", "英国石油", "公开数据"):
        key = key.replace(prefix, "")
    return key.strip(" :_-")


def deduplicate_import_export_selection(rows: list[dict]) -> None:
    """Keep only paired monthly import/export totals and select their net exports."""
    for row in rows:
        if row.get("major") not in IE_MAJORS:
            continue
        if not row.get("selected"):
            continue
        title = row.get("title") or ""
        if not any(token in title for token in ("进口", "出口", "净出口", "净进口")):
            row["selected"] = False
            row["reason"] = "非进出口总量（出港/到港/贸易流向等）不选中"
            continue
        if flow_dimension(title) == "均价":
            row["selected"] = False
            row["reason"] = "进出口均价指标不保留"
        if flow_dimension(title) == "金额" or any(
            marker in title for marker in AMOUNT_MARKERS
        ):
            row["selected"] = False
            row["reason"] = "进出口金额指标不保留"

    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    net_rows_by_stripped_key: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row.get("major") not in IE_MAJORS:
            continue
        title = row.get("title") or ""
        sheet = row.get("sheet") or ""
        frequency = row.get("frequency") or ""
        if effective_frequency(title, frequency) != "月度":
            continue
        if not is_total_import_export(title, sheet):
            continue
        dimension = flow_dimension(title)
        if dimension in ("均价", "金额"):
            continue
        key = metric_key(title)
        if not key:
            continue
        groups[(key, dimension)].append(idx)
        if "净出口" in title or "净进口" in title:
            net_rows_by_stripped_key[_strip_source_key(key)].append(idx)

    kept_indices: set[int] = set()
    assigned_net_indices: set[int] = set()
    for (_key, _dim), indices in groups.items():
        if len(indices) == 1 and indices[0] in assigned_net_indices:
            continue
        imps = [
            idx
            for idx in indices
            if "进口" in (rows[idx].get("title") or "")
            and "净" not in (rows[idx].get("title") or "")
            and "出口" not in (rows[idx].get("title") or "")
        ]
        exps = [
            idx
            for idx in indices
            if "出口" in (rows[idx].get("title") or "")
            and "净" not in (rows[idx].get("title") or "")
            and "进口" not in (rows[idx].get("title") or "")
        ]
        nets = [
            idx
            for idx in indices
            if ("净出口" in (rows[idx].get("title") or "") or "净进口" in (rows[idx].get("title") or ""))
            and idx not in assigned_net_indices
        ]
        aggregate = [
            idx
            for idx in indices
            if idx not in imps and idx not in exps and idx not in nets
        ]
        if not imps or not exps:
            for idx in imps + exps + nets + aggregate:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = "进出口无配对（只有进口或只有出口），不选中"
            continue

        if not nets:
            stripped_import_key = _strip_source_key(metric_key(rows[imps[0]].get("title") or ""))
            candidates = [
                idx
                for idx in net_rows_by_stripped_key.get(stripped_import_key, [])
                if idx not in assigned_net_indices
            ]
            if candidates:
                nets = _preferred_duplicate(candidates, rows)[:1]
                assigned_net_indices.update(nets)
            else:
                # 无净出口配对的组（如 SMM 锡锭贸易流进出口、无净出口计算的
                # 累计变体组）：进出口无净出口配对则整体不选中，
                # 保证进出口三子类数量均衡（与旧数据 10/10/10 一致）
                for idx in imps + exps + aggregate:
                    rows[idx]["selected"] = False
                    rows[idx]["reason"] = "进出口无净出口配对，不选中"
                continue

        imps = _preferred_duplicate(imps, rows)
        exps = _preferred_duplicate(exps, rows)
        nets = _preferred_duplicate(nets, rows)
        kept_indices.update([imps[0], exps[0]])
        rows[imps[0]]["selected"] = True
        rows[imps[0]]["reason"] = "进出口仅保留总量月度"
        rows[exps[0]]["selected"] = True
        rows[exps[0]]["reason"] = "进出口仅保留总量月度"
        if nets:
            kept_indices.add(nets[0])
            rows[nets[0]]["selected"] = True
            rows[nets[0]]["reason"] = "进出口仅保留总量月度"
        for idx in imps[1:]:
            rows[idx]["selected"] = False
            rows[idx]["reason"] = "进出口重复（同一指标多条进口），只保留一条"
        for idx in exps[1:]:
            rows[idx]["selected"] = False
            rows[idx]["reason"] = "进出口重复（同一指标多条出口），只保留一条"
        for idx in nets[1:]:
            rows[idx]["selected"] = False
            rows[idx]["reason"] = "净出口重复（同一口径多条净出口），只保留一条"
        for idx in aggregate:
            rows[idx]["selected"] = False
            rows[idx]["reason"] = "进出口聚合行不选中，优先保留进口/出口/净出口"

    for idx, row in enumerate(rows):
        if row.get("major") not in IE_MAJORS:
            continue
        if row.get("selected") and idx not in kept_indices:
            row["selected"] = False
            row["reason"] = "进出口仅保留总量月度成对指标"
