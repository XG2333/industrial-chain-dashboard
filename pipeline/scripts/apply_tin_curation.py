# -*- coding: utf-8 -*-
"""Post-process the tin directory with deterministic tin rules.

All rule tables and pure functions live in tin_rules.py; this script only owns
workbook mutation and audit reporting.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook


sys.path.insert(0, str(Path(__file__).resolve().parent))

from tin_rules import (
    build_tags,
    classify_major,
    classify_nature,
    classify_sub,
    detect_indicator_freq,
    select_rows,
)
from classification_candidates import candidate_plan
from selection_utils import ensure_unique_selected_rows, ensure_volume_position_pairing


SRC = Path(r"<local-documents>\多skill联动\workflow_runs\20260805T025651Z_10d97042ae6e\02_financial_variable_curation\directory_marked.xlsx")
OUT = Path(r"<local-documents>\多skill联动\output\锡产业链数据_workflow.xlsx")
REPORT = Path(r"<local-documents>\多skill联动\output\锡产业链数据标签审计报告.md")


def is_indicator_row(values: list) -> bool:
    if not values or values[0] is None:
        return False
    raw = str(values[0]).strip()
    return bool(re.fullmatch(r"\d+", raw)) and bool(values[3]) and bool(values[4])


def main(argv: list[str] | None = None) -> int:
    global SRC, OUT, REPORT
    parser = argparse.ArgumentParser(description="Apply deterministic tin curation rules.")
    parser.add_argument("--input", default=str(SRC))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--report", default=str(REPORT))
    args = parser.parse_args(argv)
    SRC = Path(args.input).resolve()
    OUT = Path(args.output).resolve()
    REPORT = Path(args.report).resolve()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    shutil.copy2(SRC, OUT)

    wb = load_workbook(OUT)
    ws = wb.worksheets[0]

    headers = [str(c.value or "").strip() for c in ws[1]]
    tag_col = None
    for idx, header in enumerate(headers, 1):
        if header == "指标标签":
            tag_col = idx
            break
    if tag_col is None:
        tag_col = len(headers) + 1
        ws.cell(row=1, column=tag_col, value="指标标签")

    current_sheet = ""
    current_sector = ""
    records = []
    major_counter: Counter[str] = Counter()
    sub_counter: Counter[str] = Counter()
    coverage: Counter[str] = Counter()
    examples: list[tuple[str, str, str, dict[str, str]]] = []

    for row in ws.iter_rows(min_row=2):
        values = [c.value for c in row]
        col0 = str(values[0]).strip() if values[0] is not None else ""
        if col0.startswith("[统计]"):
            continue
        if not is_indicator_row(values):
            if col0 and not re.fullmatch(r"\d+", col0) and len(values) > 6 and values[6] is not None:
                current_sheet = col0
                current_sector = str(values[6]).strip()
            continue

        name = str(values[4])
        unit = str(values[5] or "")
        freq = detect_indicator_freq(name, str(values[2] or ""))
        sector = str(values[6] or "") or current_sector
        plan = candidate_plan(name, current_sheet)
        major = plan["major"]
        sub = plan["sub"]
        nature = classify_nature(major, sub, name, current_sheet)
        tags = build_tags(name, current_sheet, unit, freq, major, sub, sector)
        raw_tags = values[tag_col - 1] if tag_col and values[tag_col - 1] is not None else None
        previous_tags = {}
        if raw_tags:
            try:
                parsed = json.loads(str(raw_tags))
                if isinstance(parsed, dict):
                    previous_tags = parsed
            except (TypeError, ValueError):
                pass
        if "composite" in previous_tags:
            tags["composite"] = previous_tags["composite"]
        if plan["major_candidates"]:
            tags["候选大类"] = plan["major_candidates"]
        if plan["sub_candidates"]:
            tags["候选子类"] = plan["sub_candidates"]
        if plan["combinations"]:
            tags["候选分类组合"] = plan["combinations"]

        records.append(
            {
                "sheet": current_sheet,
                "title": name,
                "frequency": freq,
                "major": major,
                "sub": sub,
                "_nature": nature,
                "_tags": tags,
                "_row": row,
            }
        )

        major_counter[major] += 1
        sub_counter[sub] += 1
        for key in ("产品", "研究主题", "指标类型", "规格", "工艺属性", "地域", "统计口径", "状态", "频率"):
            if key in tags and tags[key] not in ("未识别", "未指定"):
                coverage[key] += 1
        if len(examples) < 50:
            examples.append((current_sheet, name, unit, tags))

    processed = select_rows(records)
    ensure_volume_position_pairing(processed)
    ensure_unique_selected_rows(processed)
    total = len(processed)

    for rec in processed:
        row = rec["_row"]
        row[7].value = rec["major"]
        row[8].value = rec["sub"]
        row[9].value = rec["_nature"]
        row[2].value = rec["frequency"]
        row[11].value = "是" if rec.get("selected") else "否"
        row[12].value = rec.get("reason") or "锡确定性规则归类"
        row[tag_col - 1].value = json.dumps(rec["_tags"], ensure_ascii=False)

    wb.save(OUT)

    selected_count = sum(1 for rec in processed if rec.get("selected"))
    report_lines = [
        "# 锡产业链数据标签审计报告",
        "",
        f"- 输入文件：`{SRC.name}`",
        f"- 输出文件：`{OUT.name}`",
        f"- 有效指标数：{total}",
        f"- 选中指标数：{selected_count}",
        "",
        "## 大类分布",
        "",
    ]
    for major, count in major_counter.most_common():
        report_lines.append(f"- {major}: {count}")
    report_lines += ["", "## 子类分布", ""]
    for sub, count in sub_counter.most_common(30):
        report_lines.append(f"- {sub}: {count}")
    report_lines += ["", "## 标签覆盖率", ""]
    for key in ("产品", "研究主题", "指标类型", "规格", "工艺属性", "地域", "统计口径", "状态", "频率"):
        report_lines.append(f"- {key}：{coverage[key]}/{total}")
    report_lines += ["", "## 样例", ""]
    for sheet, name, unit, tags in examples:
        report_lines.append(f"- {sheet} | {name} | {unit} | {json.dumps(tags, ensure_ascii=False)}")
    REPORT.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"Processed {total} indicators")
    print(f"Selected: {selected_count}")
    print(f"Major: {dict(major_counter)}")
    print(f"Coverage: {dict(coverage)}")
    print(f"Output: {OUT}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
