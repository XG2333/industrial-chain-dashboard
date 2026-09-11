from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any


FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")


def metric_key(title: str) -> str:
    t = title
    for token in ("进口量", "出口量", "净出口", "进口", "出口"):
        t = t.replace(token, "")
    for token in ("_总计", ": 总计", "总计", "合计", "总量"):
        t = t.replace(token, "")
    for suffix in ("-月", "-日", "-周", "-年", "-季", "月", "日", "周", "年", "季"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
    return t.strip(" :_-")


def net_title(import_title: str, export_title: str, freq: str = "月度") -> str:
    key = metric_key(export_title) or metric_key(import_title)
    return f"{key}净出口: {freq}"


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_net_series(
    workbook,
    sheet_name: str,
    import_col: int,
    export_col: int,
) -> list[dict]:
    ws = workbook[sheet_name]
    rows: list[dict] = []
    for row in ws.iter_rows(min_row=4):
        date_cell = row[0].value
        if date_cell is None or str(date_cell).strip() == "":
            continue
        imp = _to_number(row[import_col].value) if import_col < len(row) else None
        exp = _to_number(row[export_col].value) if export_col < len(row) else None
        if imp is None or exp is None:
            continue
        rows.append({"date": _date_string(date_cell), "value": round(exp - imp, 4)})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def _date_string(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()[:10]


def find_missing_net_export_pairs(directory_rows: list[dict]) -> list[dict]:
    by_sheet_key: dict[tuple[str, str], dict] = defaultdict(dict)
    sheets_with_net: set[str] = set()

    for row in directory_rows:
        if str(row.get("selected") or "") != "是":
            continue
        sheet = str(row.get("sheet") or "")
        title = str(row.get("title") or "")
        sub = str(row.get("sub") or "")
        if "净出口" in title:
            sheets_with_net.add(sheet)
            continue
        if str(row.get("major") or "") != "进出口":
            continue
        if "总计" not in title:
            continue
        key = metric_key(title)
        if not key:
            continue
        slot = by_sheet_key[(sheet, key)]
        if sub == "进口" or "进口" in title:
            slot["import"] = row
        if sub == "出口" or ("出口" in title and "进口" not in title):
            slot["export"] = row

    missing: list[dict] = []
    for (sheet, key), pair in by_sheet_key.items():
        if sheet in sheets_with_net:
            continue
        if "import" not in pair or "export" not in pair:
            continue
        if "净出口" in str(pair["import"].get("title") or ""):
            continue
        missing.append(
            {
                "sheet": sheet,
                "key": key,
                "import_row": pair["import"],
                "export_row": pair["export"],
            }
        )
    return missing
