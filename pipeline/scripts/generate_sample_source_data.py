# -*- coding: utf-8 -*-
"""生成 skill 处理前的"原始产业源数据"样例文件（保密演示用）。

与 generate_sample_industry_data.py（成品样例）对应：本脚本处理的是**多 skill 联动
流程的输入**（原始未处理产业 Excel，如 data_input/碳酸锂数据库.xlsx），而非
server 直接读取的 *_workflow_ai.xlsx 成品。

原则：
- 结构/格式原样保留：sheet 顺序与名称、表头结构行（指标名称/单位/频率行，位置
  各源不一，按 A 列首个日期行自动定位）、公式列文本、日期时间骨架；
  无日期行的 sheet（目录/空壳等）整表原样复制。
- 数值一律随机（固定 seed 可复现随机游走），不含任何真实数据。
- 输出：<多skill联动>/input/样例/{碳酸锂数据库,锡数据库,硅产业链数据}.xlsx

用法：
  python generate_sample_source_data.py
  演示：把 input/样例/*.xlsx 拷到 input/ 根目录（或 pipeline --input 直接指向样例）
  → 运行 run_industry_pipeline.py / run_all.bat → 产出 workflow_ai 成品 → dashboard 分析。
"""
import random
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.workbook import Workbook

# (源文件路径, 输出文件名) —— 输出名与 部署说明.md 第 1 步的 input 约定一致
SRC_FILES = [
    (Path(r"<local-documents>\多skill联动\data_input\碳酸锂数据库.xlsx"), "碳酸锂数据库.xlsx"),
    (Path(r"<local-documents>\market-ai-dashboard\锡数据库.xlsx"), "锡产业链数据.xlsx"),
    (Path(r"<local-documents>\多skill联动\data_input\硅产业链数据.xlsx"), "硅产业链数据.xlsx"),
]
OUT_DIR = Path(__file__).resolve().parent.parent / "input" / "样例"
SEED = 20260903


def make_walker(rng: random.Random, lo: float, hi: float):
    state = {"v": rng.uniform(lo, lo + (hi - lo) * 0.4)}

    def walk() -> float:
        v = state["v"]
        if rng.random() < 0.04:
            v *= rng.uniform(0.7, 1.45)
        else:
            v *= 1.0 + rng.uniform(-0.03, 0.03)
        v = max(lo * 0.5, min(v, hi))
        state["v"] = v
        return round(v, 6)

    return walk


def _is_date_like(v) -> bool:
    if v is None:
        return False
    year = None
    if isinstance(v, datetime):
        year = v.year
    elif isinstance(v, str):
        s = v.strip()
        if not s:
            return False
        # "2026-08-19" / "2026/8/19 00:00:00" 等日期形态
        head = s[:10]
        if len(head) == 10 and head[4] in "-/" and head[:4].isdigit() and head[5:7].isdigit() and head[8:10].isdigit():
            year = int(head[:4])
    # 2000 年之前的"日期"视为伪日期(如结构行 1900-01-01 + 列号), 不当作数据起始
    return year is not None and year >= 2000


def generate_one(src: Path, dst_name: str) -> int:
    if not src.exists():
        print("missing:", src)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst = OUT_DIR / dst_name
    wb_src = load_workbook(src, data_only=False, read_only=False)
    wb_out = Workbook(write_only=True)
    stats = {"sheets": 0, "rows": 0, "formula": 0, "random": 0, "date": 0}
    for ws in wb_src.worksheets:
        ws_out = wb_out.create_sheet(title=ws.title)
        stats["sheets"] += 1
        # 先读前 40 行 A 列找首个日期行(数据起始)；找不到(目录/空壳/纯文本 sheet)→ 整表原样
        first_rows = list(ws.iter_rows(min_row=1, max_row=40, values_only=True))
        data_start = None
        for i, row in enumerate(first_rows, start=1):
            if row and _is_date_like(row[0]):
                data_start = i
                break
        if data_start is None:
            for row in ws.iter_rows(values_only=True):
                ws_out.append(list(row))
            stats["rows"] += ws.max_row
            continue
        rng = random.Random(SEED ^ hash(ws.title) % (2 ** 31))
        walkers: dict[int, object] = {}
        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if r_idx < data_start:
                ws_out.append(list(row))  # 结构行(指标名称/单位/频率等)原样
                continue
            out_row = [None] * len(row)
            for c_idx, val in enumerate(row, start=1):
                if c_idx == 1:
                    out_row[0] = val  # 日期列原样
                    stats["date"] += 1
                    continue
                if val is None:
                    continue
                if isinstance(val, str) and val.lstrip().startswith("="):
                    # 公式列不保留公式文本：公式可能含行业参数/加权常量（如税率、系数），
                    # 视为数据特征一并随机化；样例不演示公式回填（skill/server 对普通数值列同样可读）
                    walker = walkers.get(c_idx)
                    if walker is None:
                        walker = make_walker(rng, 0.01, 500000.0)
                        walkers[c_idx] = walker
                    out_row[c_idx - 1] = walker()
                    stats["random"] += 1
                elif isinstance(val, (int, float)):
                    walker = walkers.get(c_idx)
                    if walker is None:
                        walker = make_walker(rng, 0.01, 500000.0)
                        walkers[c_idx] = walker
                    out_row[c_idx - 1] = walker()
                    stats["random"] += 1
                else:
                    out_row[c_idx - 1] = None  # 数据区文本占位置空
            ws_out.append(out_row)
            stats["rows"] += 1
    wb_src.close()
    wb_out.save(dst)
    print(f"[sample-src] {src.name}: sheets={stats['sheets']} rows={stats['rows']} "
          f"random={stats['random']} formula_kept={stats['formula']}")
    return 1


def main() -> int:
    ok = 0
    for src, dst_name in SRC_FILES:
        try:
            ok += generate_one(src, dst_name)
        except Exception as e:  # noqa: BLE001
            print(f"[sample-src] {dst_name} failed: {e}")
    print(f"\n输出目录: {OUT_DIR} ({ok}/{len(SRC_FILES)})")
    print("演示: 拷贝 input/样例/*.xlsx 到 input/ 根目录 → 运行 run_all.bat → dashboard 读产出成品")
    return 0 if ok == len(SRC_FILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
