# -*- coding: utf-8 -*-
"""按原始产业数据结构生成"样例产业数据"文件（保密演示用）。

原则：
- 只参考 指标结构/格式：指标目录（#/Sheet Name/Freq/Col/Indicator Name/单位/板块…）、
  数据 sheet 布局（指标名称行/单位行/频率行 + 日期列）、公式结构、日期骨架全部原样保留
  —— 生成文件可被 server.py 原样加载、dashboard 完整分析（目录、频率、单位、公式回填同真实流程）。
- 禁止使用真实数据：数据区（日期列之后的指标数值）一律随机生成 —— 每个指标列独立
  随机游走（固定 seed 可复现，数值尺度按单位分档仅保证图表观感，与真实世界无关）；
  公式列保留公式文本（引用结构与真实结构一致、无缓存值，不含任何真实数值）。
- 输出：<dashboard>/data/sample/ 三个同名文件；原始数据文件不做任何改动。

用法：
  python generate_sample_industry_data.py
  演示切换：备份 data/ 下原始 xlsx → 用 data/sample/ 同名文件覆盖 → 删除 data/cache/*.pkl
  → 重启 server → 打开看板即为样例数据（全随机）；演示完恢复原始文件 + 删缓存 + 重启。
"""
import random
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.workbook import Workbook

DATA_DIR = Path(__file__).resolve().parents[2] / "本地可视化dashboard" / "data"
SAMPLE_DIR = DATA_DIR / "sample"
FILES = [
    "碳酸锂数据库_workflow_ai.xlsx",
    "锡产业链数据_workflow_ai.xlsx",
    "硅产业链数据_workflow_ai.xlsx",
]
SEED = 20260903


def _scale_for_unit(unit: str):
    u = unit or ""
    if "%" in u:
        return 1.0, 100.0
    if "美元" in u:
        return 1.0, 20000.0
    if "元/吨" in u or "元/千克" in u or "元/公斤" in u:
        return 1000.0, 300000.0
    if "元/平方米" in u or "元/㎡" in u or "元/瓦" in u or "元/块" in u:
        return 0.05, 300.0
    if u:  # 吨 / 手 / 万台 等数量类
        return 1.0, 1000000.0
    return 0.1, 800.0  # 无量纲（指数/比值）


def make_walker(rng: random.Random, lo: float, hi: float):
    state = {"v": rng.uniform(lo, lo + (hi - lo) * 0.4)}

    def walk() -> float:
        v = state["v"]
        if rng.random() < 0.04:
            v *= rng.uniform(0.7, 1.45)  # 偶发跳变
        else:
            v *= 1.0 + rng.uniform(-0.035, 0.035)
        v = max(lo * 0.5, min(v, hi))
        state["v"] = v
        return round(v, 6)

    return walk


def generate_one(fname: str) -> int:
    src = DATA_DIR / fname
    if not src.exists():
        print("missing:", src)
        return 0
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    dst = SAMPLE_DIR / fname

    wb_src = load_workbook(src, data_only=False, read_only=False)
    wb_out = Workbook(write_only=True)
    stats = {"sheets": 0, "rows": 0, "formula": 0, "random": 0, "date": 0}
    for ws_idx, ws in enumerate(wb_src.worksheets):
        ws_out = wb_out.create_sheet(title=ws.title)
        stats["sheets"] += 1
        # 第一个 sheet 是指标目录（server 以 sheet_names[0] 为目录）：目录只有
        # 结构文本（#/Sheet Name/Freq/Col/Indicator Name/…），无数据列，整表原样复制
        if ws_idx == 0:
            for row in ws.iter_rows(values_only=True):
                ws_out.append(list(row))
            stats["rows"] += ws.max_row
            continue
        rng = random.Random(SEED ^ hash(ws.title) % (2 ** 31))
        # 单位行（第 2 行）：决定数据列随机尺度；先取前三行（结构行）
        head = list(ws.iter_rows(min_row=1, max_row=3, values_only=True))
        unit_row = head[1] if len(head) > 1 else ()
        units = {c_idx: str(v).strip() for c_idx, v in enumerate(unit_row, start=1) if v is not None}
        walkers: dict[int, object] = {}

        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if r_idx <= 3:
                ws_out.append(list(row))  # 指标名称/单位/频率 结构行原样
                continue
            out_row = [None] * len(row)
            for c_idx, val in enumerate(row, start=1):
                if c_idx == 1:
                    out_row[0] = val  # 日期列原样（时间骨架）
                    stats["date"] += 1
                    continue
                if val is None:
                    continue
                if isinstance(val, str) and val.lstrip().startswith("="):
                    # 公式列不保留公式文本：公式可能含行业参数/加权常量（如税率、系数），
                    # 视为数据特征一并随机化；样例不演示公式回填（server 对普通数值列同样可读）
                    walker = walkers.get(c_idx)
                    if walker is None:
                        lo, hi = _scale_for_unit(units.get(c_idx, ""))
                        walker = make_walker(rng, lo, hi)
                        walkers[c_idx] = walker
                    out_row[c_idx - 1] = walker()
                    stats["random"] += 1
                elif isinstance(val, (int, float)):
                    walker = walkers.get(c_idx)
                    if walker is None:
                        lo, hi = _scale_for_unit(units.get(c_idx, ""))
                        walker = make_walker(rng, lo, hi)
                        walkers[c_idx] = walker
                    out_row[c_idx - 1] = walker()
                    stats["random"] += 1
                else:
                    # 数据区其它文本（"停牌/—"等占位）：样例置空，避免夹带原始文本
                    out_row[c_idx - 1] = None
            ws_out.append(out_row)
            stats["rows"] += 1
    wb_src.close()
    wb_out.save(dst)
    print(f"[sample] {fname}: sheets={stats['sheets']} rows={stats['rows']} "
          f"random={stats['random']} formula_kept={stats['formula']} date={stats['date']}")
    return 1


def main() -> int:
    ok = 0
    for f in FILES:
        try:
            ok += generate_one(f)
        except Exception as e:  # noqa: BLE001
            print(f"[sample] {f} failed: {e}")
    print(f"\n输出目录: {SAMPLE_DIR}（{ok}/3 个文件）")
    print("演示切换: 备份 data/ 原始 xlsx → 用 sample 同名覆盖 → 删除 data/cache/*.pkl → 重启 server")
    return 0 if ok == len(FILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
