from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y%m%d",
    "%Y.%m.%d",
    "%Y-%m",
    "%Y/%m",
]

DATE_HEADER_TOKENS = (
    "date",
    "time",
    "period",
    "日期",
    "时间",
    "期间",
    "月份",
    "年月",
    "年",
    "月",
    "日",
)


def parse_date_value(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if 1900 <= number <= 2100 and number == int(number):
            return datetime(int(number), 1, 1)
        if 20000 <= number <= 80000:
            try:
                return datetime(1899, 12, 30) + timedelta(days=number)
            except OverflowError:
                return None
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        match = re.match(r"^(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?$", text)
        if match:
            year, month, day = match.groups()
            return datetime(int(year), int(month), int(day or 1))
    return None


def date_format_signature(value: object) -> str:
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "serial"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "empty"
        if re.match(r"^\d{4}-\d{2}-\d{2}", text):
            return "iso"
        if re.match(r"^\d{4}/\d{1,2}/\d{1,2}", text):
            return "slash"
        if re.match(r"^\d{8}$", text):
            return "compact"
        if re.search(r"年.*月", text):
            return "chinese"
        if re.match(r"^\d{1,2}/\d{1,2}/\d{4}", text):
            return "us"
        return "text"
    return "other"


def is_date_header(header: str) -> bool:
    lowered = header.lower()
    return any(token in lowered for token in DATE_HEADER_TOKENS)
