# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import date, datetime

from secondary_selection import secondary_selection_decision
from selection_utils import (
    POSITION_SUBS,
    VOLUME_SUBS,
    volume_position_ratio_key,
)


RATIO_SHEET_NAME = "成交持仓比计算"


def _to_number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date_string(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()[:10]


def _column_series(workbook, sheet_name: str, col: int) -> dict[str, float]:
    ws = workbook[sheet_name]
    values: dict[str, float] = {}
    for row in ws.iter_rows(min_row=4):
        date_cell = row[0].value
        if date_cell is None or str(date_cell).strip() == "":
            continue
        value = _to_number(row[col].value) if col < len(row) else None
        if value is not None:
            values[_date_string(date_cell)] = value
    return values


def compute_ratio_series(
    workbook,
    volume_sheet: str,
    volume_col: int,
    position_sheet: str,
    position_col: int,
    data_workbook=None,
) -> list[dict]:
    # data_workbook: 数据源 workbook（read_only 完整文件）；None 时用主 workbook
    source = data_workbook if data_workbook is not None else workbook
    volumes = _column_series(source, volume_sheet, volume_col)
    positions = _column_series(source, position_sheet, position_col)
    rows: list[dict] = []
    for date_key, volume in volumes.items():
        position = positions.get(date_key)
        if position is None or position <= 0:
            continue
        rows.append({"date": date_key, "value": round(volume / position, 4)})
    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows


def find_missing_volume_position_ratio_pairs(records: list[dict]) -> list[dict]:
    volume_by_key: dict[str, dict] = {}
    position_by_key: dict[str, dict] = {}
    existing_ratio_keys: set[str] = set()

    for rec in records:
        sub = rec.get("sub")
        title = str(rec.get("title") or "")
        frequency = str(rec.get("frequency") or "")
        key = volume_position_ratio_key(title, frequency)
        if sub in VOLUME_SUBS and rec.get("selected"):
            volume_by_key[key] = rec
        elif sub in POSITION_SUBS and rec.get("selected"):
            position_by_key[key] = rec
        elif sub == "成交持仓比":
            existing_ratio_keys.add(key)

    missing = []
    for key in sorted(set(volume_by_key) & set(position_by_key)):
        if key in existing_ratio_keys:
            continue
        product, contract, frequency = key.split("|", 2)
        volume_rec = volume_by_key[key]
        position_rec = position_by_key[key]
        missing.append(
            {
                "product": product,
                "contract": contract,
                "frequency": frequency,
                "volume_sheet": volume_rec.get("sheet") or "",
                "volume_col": int(str(volume_rec["_row"][3].value)),
                "position_sheet": position_rec.get("sheet") or "",
                "position_col": int(str(position_rec["_row"][3].value)),
                "sector": str(volume_rec["_row"][6].value or ""),
                "volume": volume_rec,
                "position": position_rec,
            }
        )
    return missing


def append_missing_volume_position_ratios(
    workbook,
    records: list[dict],
    secondary_col: int | None = None,
    data_workbook=None,
) -> int:
    missing = find_missing_volume_position_ratio_pairs(records)
    if not missing:
        return 0

    ws = workbook[workbook.sheetnames[0]]
    if secondary_col is None:
        headers = [str(c.value or "").strip() for c in ws[1]]
        if "二次筛选是否保留" in headers:
            secondary_col = headers.index("二次筛选是否保留") + 1
        else:
            secondary_col = ws.max_column + 1
            ws.cell(1, secondary_col, "二次筛选是否保留")
    if RATIO_SHEET_NAME not in workbook.sheetnames:
        calc_ws = workbook.create_sheet(RATIO_SHEET_NAME)
        calc_ws.cell(1, 1, "日期")
    else:
        calc_ws = workbook[RATIO_SHEET_NAME]

    existing_cols = calc_ws.max_column
    seq_max = 0
    for row in ws.iter_rows(min_row=2, max_col=1):
        if row[0].value is not None and str(row[0].value).isdigit():
            seq_max = max(seq_max, int(row[0].value))

    directory_start = ws.max_row + 1
    row_idx = directory_start
    first_frequency = missing[0]["frequency"]
    first_sector = missing[0]["sector"]
    ws.cell(row_idx, 1, RATIO_SHEET_NAME)
    ws.cell(row_idx, 2, "")
    ws.cell(row_idx, 3, first_frequency)
    ws.cell(row_idx, 7, first_sector)
    row_idx += 1

    added = 0
    for pair in missing:
        series = compute_ratio_series(
            workbook,
            pair["volume_sheet"],
            pair["volume_col"],
            pair["position_sheet"],
            pair["position_col"],
            data_workbook=data_workbook,
        )
        if not series:
            continue

        col = existing_cols + 1
        existing_cols += 1
        title = f"{pair['product']}{pair['contract']}成交持仓比"
        calc_ws.cell(1, col + 1, title)
        calc_ws.cell(2, col + 1, "比率")
        calc_ws.cell(3, col + 1, pair["frequency"])
        for i, point in enumerate(series):
            calc_ws.cell(4 + i, 1, point["date"])
            calc_ws.cell(4 + i, col + 1, point["value"])

        seq_max += 1
        ws.cell(row_idx, 1, seq_max)
        ws.cell(row_idx, 2, "")
        ws.cell(row_idx, 3, pair["frequency"])
        ws.cell(row_idx, 4, col)
        ws.cell(row_idx, 5, title)
        ws.cell(row_idx, 6, "比率")
        ws.cell(row_idx, 7, pair["sector"])
        ws.cell(row_idx, 8, "价格")
        ws.cell(row_idx, 9, "成交持仓比")
        ws.cell(row_idx, 10, "比率")
        ws.cell(row_idx, 11, 0.95)
        ws.cell(row_idx, 12, "是")
        ws.cell(row_idx, 13, "确定性成交持仓比计算")
        keep, _reason = secondary_selection_decision(
            title, pair["frequency"], pair["sector"], True
        )
        ws.cell(row_idx, secondary_col, "是" if keep else "否")
        row_idx += 1
        added += 1
    return added
