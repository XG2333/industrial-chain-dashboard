# -*- coding: utf-8 -*-
"""Post-check price subclass consistency from indicator names (scheme E)."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from openpyxl import load_workbook


sys.path.insert(0, str(Path(__file__).resolve().parent))
from classification_candidates import deterministic_price_sub


PRICE_SUB_RULES = (
    ("成交持仓比", ("成交持仓比",)),
    ("成交量", ("成交量",)),
    ("持仓", ("持仓",)),
    ("期货价格", ("期货", "合约", "收盘价", "结算价")),
    ("月差", ("月差",)),
    ("价差", ("价差", "升贴水", "溢价", "基差", "期现")),
    ("指数", ("指数",)),
    ("现货价格", ("现货", "平均价", "均价", "价格")),
)


def expected_price_sub(name: str, sheet: str, industry: str) -> str | None:
    """Return the deterministic price subclass selected by priority rules."""
    return deterministic_price_sub(name, sheet, industry)


def is_indicator_row(values: list) -> bool:
    if not values or values[0] is None:
        return False
    raw = str(values[0]).strip()
    return bool(re.fullmatch(r"\d+", raw)) and bool(values[3]) and bool(values[4])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check and correct price subclass consistency.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--industry", choices=["lithium", "tin", "silicon"], default=None)
    args = parser.parse_args(argv)

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve() if args.report else output_path.with_suffix(".md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, output_path)

    wb = load_workbook(output_path)
    ws = wb.worksheets[0]

    headers = [str(c.value or "").strip() for c in ws[1]]
    tag_col = None
    for idx, header in enumerate(headers, 1):
        if header == "指标标签":
            tag_col = idx
            break

    corrected = 0
    unchanged = 0
    skipped = 0
    examples: list[str] = []

    for row in ws.iter_rows(min_row=2):
        values = [c.value for c in row]
        col0 = str(values[0]).strip() if values[0] is not None else ""
        if col0.startswith("[统计]"):
            continue
        if not is_indicator_row(values):
            continue

        major = str(values[7] or "").strip()
        if major != "价格":
            skipped += 1
            continue
        name = str(values[4])
        sheet = str(values[1] or "").strip()
        current_sub = str(values[8] or "").strip()
        expected = expected_price_sub(name, sheet, args.industry or "lithium_tin")
        if expected is None:
            skipped += 1
            continue
        if expected == current_sub:
            unchanged += 1
            continue

        row[8].value = expected
        corrected += 1
        if tag_col and values[tag_col - 1] is not None:
            raw = str(values[tag_col - 1]).strip()
            if raw:
                try:
                    tags = json.loads(raw)
                    tags["指标类型"] = expected
                    row[tag_col - 1].value = json.dumps(tags, ensure_ascii=False)
                except Exception:
                    pass
        if len(examples) < 50:
            examples.append(f"- {name} | {current_sub} -> {expected}")

    wb.save(output_path)

    report_lines = [
        "# 分类一致性检查报告",
        "",
        f"- 输入：`{input_path.name}`",
        f"- 输出：`{output_path.name}`",
        f"- 价格类修正条数：{corrected}",
        f"- 价格类一致条数：{unchanged}",
        f"- 非价格类跳过条数：{skipped}",
        "",
        "## 修正示例",
        "",
    ]
    report_lines.extend(examples or ["- 无"])
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"Classification consistency: corrected={corrected} unchanged={unchanged} skipped={skipped}")
    print(f"Output: {output_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
