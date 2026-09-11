# -*- coding: utf-8 -*-
"""Workflow 内 in_place 链合并步骤：净出口计算 → 指标标签 → 复合指标。

原 workflow 中 calculate_net_exports / composite_metric_stage 各自对同一个
300+ sheets 的完整文件做 openpyxl 全量 load + save（每次 20-40 秒）。本脚本
把三步合并为单进程：一次 load → 三次内存操作（共享 wb 对象）→ 一次 save，
省去中间 2 次全量序列化，输出与逐步执行完全一致。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_indicator_tags import _write_report, apply_indicator_tags_on_workbook
from calculate_net_exports import run_net_exports_on_workbook
from composite_metric_stage import run_composite_on_workbook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merged net-export + tags + composite stage.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--tags-report", default=None)
    args = parser.parse_args(argv)

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    same_path = input_path == output_path
    working = output_path
    if same_path:
        working = output_path.with_name(f"{output_path.stem}__merged_tmp.xlsx")
    working.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, working)

    wb = load_workbook(working, data_only=False)
    try:
        pairs = run_net_exports_on_workbook(wb)
        # 无条件重算指标标签（覆盖全部行含净出口追加行），
        # 替代原 financial 步骤后的独立 tags 子进程
        total, coverage, examples = apply_indicator_tags_on_workbook(wb)
        if args.tags_report:
            _write_report(Path(args.tags_report), input_path, total, coverage, examples)
        report = run_composite_on_workbook(
            wb,
            report_path=Path(args.report).resolve() if args.report else None,
            input_label=str(input_path),
            output_label=str(output_path),
        )
    finally:
        wb.save(working)
        wb.close()
    if same_path:
        working.replace(output_path)

    print(f"Merged stage: net_export_pairs={pairs} tagged={total} composite_groups={len(report['groups'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
