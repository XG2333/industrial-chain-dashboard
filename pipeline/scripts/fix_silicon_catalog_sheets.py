# -*- coding: utf-8 -*-
"""修复硅工作簿「指标目录」的 Sheet Name 列（显式补全真实数据 sheet）。

背景（2026-09-03 诊断）：
  数据 sheet 本身与列标签完全正常（如「工业硅现货价格-日」名称行里
  553#硅(华南)=9150 元/吨）；但目录行曾被重排工具打乱分组——指标行被放
  到错误的 sheet 头行组之下（553#/521#/551# 硅价进了「光伏胶膜价格-日」组、
  不通氧553# 进了「焊带价格-日」组、D4/DMC 进了「国内组件价格-日」组…）。
  服务器按目录行序 + Sheet Name 列继承解析 → 取错数据列（553#硅(华南)
  读成了光伏EPE胶膜价格 8.7）。

修复方式：
  用 silicon_catalog.discover（数据 sheet 名称行，权威读取）反向匹配每个目录行
  （Indicator Name + Col + Freq + Unit），把 Sheet Name 列写为真实 sheet 名。
  此后服务器逐行直读 Sheet Name，不再依赖分组行 → 数据张冠李戴消除；
  展示行序、公式、数据列一律不动。已正确分组的行也会写入同名（幂等）。

用法：
  python fix_silicon_catalog_sheets.py [--report <path>]
  默认报告写到脚本同目录 silicon_sheetfix_report.txt（可用 --report 改路径或 "" 关闭）。
"""
import argparse
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silicon_catalog import discover

DATA_DIR = Path(__file__).resolve().parents[2] / "本地可视化dashboard" / "data"
FILE = DATA_DIR / "硅产业链数据_workflow_ai.xlsx"
CAT_SHEET = "指标目录"

FULLW = {"（": "(", "）": ")", "：": ":", "，": ",", "､": ","}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", nargs="?", const=True, default="")
    args = parser.parse_args()

    if not FILE.exists():
        print("missing:", FILE)
        return 1

    backup = DATA_DIR / (FILE.stem + f"_backup_{Path(__file__).stem}.xlsx")
    shutil.copy2(FILE, backup)
    print(f"backup -> {backup.name}")

    # ── 1) 权威索引：数据 sheet 名称行（discover 同款读取） ──
    discovered = discover(FILE)
    # name -> [(sn, col0, unit, freq)]
    by_name: dict[str, list] = {}
    sheet_names = set()
    for s in discovered:
        sn = s["sn"]
        sheet_names.add(sn)
        for ind in s["inds"]:
            nm = str(ind["name"]).strip()
            by_name.setdefault(nm, []).append(
                (sn, ind["col"], str(ind["unit"] or "").strip(), str(ind["freq"] or "").strip())
            )
    print(f"data sheets={len(discovered)} indicator labels={sum(len(v) for v in by_name.values())}")

    wb = load_workbook(FILE, data_only=False)  # data_only=False: 保留公式
    if CAT_SHEET not in wb.sheetnames:
        print("catalog sheet not found:", CAT_SHEET)
        return 1
    ws = wb[CAT_SHEET]
    header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    for want in ("Sheet Name", "Freq", "Col", "Indicator Name", "Unit"):
        if want not in header:
            print("catalog header missing:", want)
            return 1
    hi = {name: i for i, name in enumerate(header)}
    c_sheet, c_freq, c_col, c_name, c_unit = (
        hi["Sheet Name"], hi["Freq"], hi["Col"], hi["Indicator Name"], hi["Unit"]
    )

    # 当前行序下的"继承分组"（服务器同款推断，用于统计错位清单）
    cur_group = None
    changes: list[tuple[int, str, str, str]] = []  # (row, old_group, real_sheet, name)
    filled = multi_manual = not_found = skipped_ref = 0

    # ── 2) 逐行匹配并写 Sheet Name ──
    for r_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        vals = ["" if c.value is None else str(c.value).strip() for c in row]
        name = vals[c_name] if len(vals) > c_name else ""
        if not name:
            continue
        col = vals[c_col] if len(vals) > c_col else ""
        if not col.isdigit():
            # sheet 头行 / 分区行：更新继承分组
            c0 = vals[0] if vals else ""
            if c0 and not c0.isdigit() and "(" not in c0 and "[" not in c0 and "统计" not in c0:
                cur_group = c0
            continue
        freq = vals[c_freq] if len(vals) > c_freq else ""
        unit = vals[c_unit] if len(vals) > c_unit else ""
        col0 = int(col)

        # 引用占位行（'sheet'!A1 形式，server 忽略）跳过
        if name.startswith("'"):
            skipped_ref += 1
            continue

        cands = by_name.get(name)
        if not cands:
            not_found += 1
            continue
        # 消歧 1: Col(0基) 与候选 col 一致
        by_col = [c for c in cands if c[1] == col0]
        if len(by_col) == 1:
            cands = by_col
        else:
            # 消歧 2: freq / unit
            filt = [c for c in cands if (not freq or c[3] == freq) and (not unit or c[2] == unit)]
            cands = filt if len(filt) == 1 else (by_col or cands)
        if len(cands) != 1:
            multi_manual += 1
            continue
        real_sheet, real_col, _, _ = cands[0]
        if real_sheet not in sheet_names:
            not_found += 1
            continue

        old = vals[c_sheet] if len(vals) > c_sheet else ""
        if old != real_sheet:
            ws.cell(row=r_idx, column=c_sheet + 1, value=real_sheet)
            filled += 1
            if old:
                changes.append((r_idx, old, real_sheet, name))
            elif cur_group and cur_group != real_sheet and cur_group not in (
                "日度", "周度", "月度", "季度", "年度"
            ):
                # 无显式旧值：对比继承分组，分组不一致 = 本次修复的错位行
                changes.append((r_idx, f"<组:{cur_group}>", real_sheet, name))
    wb.save(FILE)
    print(f"filled={filled} multi_manual={multi_manual} not_found={not_found} ref_skipped={skipped_ref}")

    # ── 3) 自检：全部指标行 (sheet,col) 与数据 sheet 名称行标签一致 ──
    verify_err = 0
    for r_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        vals = ["" if c.value is None else str(c.value).strip() for c in row]
        name = vals[c_name] if len(vals) > c_name else ""
        col = vals[c_col] if len(vals) > c_col else ""
        sh = vals[c_sheet] if len(vals) > c_sheet else ""
        if not name or not col.isdigit():
            continue
        if name.startswith("'"):
            continue
        if not sh:
            verify_err += 1
            continue
        col0 = int(col)
        ok = any(c[0] == sh and c[1] == col0 for c in by_name.get(name, []))
        if not ok:
            verify_err += 1
            print(f"  VERIFY FAIL r{r_idx}: sheet={sh} col={col0} name={name}")

    # ── 4) 报告 ──
    lines = [
        f"硅指标目录 Sheet Name 修复报告 {FILE.name}",
        f"备份: {backup.name}",
        f"指标行填表: {filled} | 多候选需人工: {multi_manual} | 未找到: {not_found} | 引用行跳过: {skipped_ref}",
        f"自检(全部指标行 sheet+col 与数据名称行一致): {'PASS' if verify_err == 0 else f'FAIL x{verify_err}'}",
        f"错位/变更行数(对比修复前分组): {len(changes)}",
        "",
        "=== 错位行清单 (row | 原分组 -> 真实sheet | 指标) ===",
    ]
    for r_idx, old, real, name in changes:
        lines.append(f"r{r_idx} | {old} -> {real} | {name[:80]}")
    if multi_manual:
        lines.append(f"\n=== 需人工处理 (多候选未消歧, {multi_manual} 行) ===")
        for r_idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
            vals = ["" if c.value is None else str(c.value).strip() for c in row]
            name = vals[c_name] if len(vals) > c_name else ""
            if name and not name.startswith("'") and vals[c_col].isdigit() and not (vals[c_sheet] if len(vals) > c_sheet else ""):
                pass  # 已填者跳过；未填且可再查的在此列示
    out = "\n".join(lines)
    if args.report is not False:
        rep_path = (
            Path(args.report)
            if isinstance(args.report, str) and args.report
            else Path(__file__).resolve().parent / "silicon_sheetfix_report.txt"
        )
        rep_path.write_text(out, encoding="utf-8")
        print("report ->", rep_path)
    else:
        print(out)
    print("DONE verify_err=", verify_err)
    return 0 if verify_err == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
