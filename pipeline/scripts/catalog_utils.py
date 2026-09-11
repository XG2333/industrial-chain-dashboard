# -*- coding: utf-8 -*-
"""Shared Excel catalog discovery helpers used by all industry catalog scripts."""

from __future__ import annotations

import re

import pandas as pd


FREQ_ALIASES = {
    "日": "日度",
    "周": "周度",
    "月": "月度",
    "季": "季度",
    "年": "年度",
    "半月": "月度",
    "半": "月度",
}

def resolve_annualized_frequency(name: str) -> str | None:
    """Return 年度 when a name mixes 年化 with another frequency marker."""
    text = str(name or "")
    if "年化" in text and re.search(r"(日|周|月|季)", text):
        return "年度"
    return None


def find_header_rows(df) -> tuple[int, int]:
    header_row = 0
    unit_row = 1
    for ri in range(min(6, df.shape[0])):
        cell = str(df.iloc[ri, 0]).strip() if pd.notna(df.iloc[ri, 0]) else ""
        if "指标名称" in cell:
            header_row = ri
            unit_row = ri + 1
            if ri + 1 < df.shape[0]:
                nv = str(df.iloc[ri + 1, 0]).strip() if pd.notna(df.iloc[ri + 1, 0]) else ""
                if "指标Id" in nv:
                    unit_row = ri + 2
            break
        if "钢联数据" in cell:
            header_row = ri + 1
            unit_row = ri + 2
            break
    return header_row, unit_row


def find_freq_row(df) -> int | None:
    for ri in range(min(6, df.shape[0])):
        cell = str(df.iloc[ri, 0]).strip() if pd.notna(df.iloc[ri, 0]) else ""
        if cell == "频率":
            return ri
    return None


def value_columns(df, header_row: int, unit_row: int) -> list[int]:
    labels = []
    for ci in range(df.shape[1]):
        cell = str(df.iloc[header_row, ci]).strip() if pd.notna(df.iloc[header_row, ci]) else ""
        if cell == "指标名称":
            labels.append(ci)
    if len(labels) >= 2:
        cols = []
        for ci in labels:
            vc = ci + 1
            if vc < df.shape[1]:
                unit_cell = (
                    str(df.iloc[unit_row, vc]).strip()
                    if unit_row < df.shape[0] and pd.notna(df.iloc[unit_row, vc])
                    else ""
                )
                if unit_cell and unit_cell != "单位":
                    cols.append(vc)
        return cols
    return list(range(1, df.shape[1]))


def column_freq(df, freq_row: int | None, vc: int, name: str, sheet_freq: str) -> str:
    annualized = resolve_annualized_frequency(name)
    if annualized:
        return annualized
    if freq_row is not None and freq_row < df.shape[0] and vc < df.shape[1]:
        cell = (
            str(df.iloc[freq_row, vc]).strip()
            if pd.notna(df.iloc[freq_row, vc])
            else ""
        )
        for key, value in FREQ_ALIASES.items():
            if key in cell:
                return value
    match = re.search(r"(日度|周度|月度|季度|年度)", name or "")
    if match:
        return match.group(1)
    return sheet_freq
