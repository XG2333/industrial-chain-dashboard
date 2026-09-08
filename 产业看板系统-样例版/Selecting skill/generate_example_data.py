from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook


def generate(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "MarketData"
    sheet.append(
        [
            "date",
            "close_price",
            "close_price_2",
            "volume",
            "revenue",
            "constant_col",
            "empty_col",
            "high_missing",
            "note",
        ]
    )
    start = date(2024, 1, 1)
    for index in range(25):
        day = start + timedelta(days=index)
        sheet.append(
            [
                day,
                100 + index,
                99 + index,
                1000 + index * 10,
                (index + 1) * 1000,
                7,
                None,
                123 if index == 0 else (456 if index == 24 else None),
                f"note-{index}" if index < 3 else None,
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


if __name__ == "__main__":
    generate(Path(__file__).resolve().parents[1] / "input" / "example.xlsx")
