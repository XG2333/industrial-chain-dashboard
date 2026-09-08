# -*- coding: utf-8 -*-
"""中档脱敏样例数据生成(旧式部署形态: 样例 Excel 放入 data/ 后真实模式读取)。

以真实工作簿为“模板”(sheet 结构/目录行/日期骨架), 输出副本:
  - 文本脱敏(确定性变换, 保证目录 Sheet Name 列与数据 sheet 名一致):
      去 SMM/Mysteel/GFEX/交易所等来源前缀; 括号内成分配比(如 (Li2O: 3%-4%))
      替换为固定「品级」; AI 筛选原因/状态说明等策略文本清空;
      板块/产品/单位/频率等公开框架词保留;
  - 数值全随机: 数据区(第4行起)数值/公式 → 随机游走值; 目录表引用类数值
    (Sheet Name/Col 列号/序号/选中标记)与日期列原样保留, 不破坏解析;
  - 输出到 ./build_sample_data/, 不触碰真实 data/。
"""
import random
import re
from pathlib import Path

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data"
OUT = ROOT / "build_sample_data"
WORKBOOKS = [
    "碳酸锂数据库_workflow_ai.xlsx",
    "锡产业链数据_workflow_ai.xlsx",
    "硅产业链数据_workflow_ai.xlsx",
]
_SRC_PREFIX = re.compile(
    r"^\s*(?:SMM|Mysteel|百川盈孚|百川|上海有色|GFEX|SHFE|DCE|CZCE|INE|CFFEX|LME|"
    r"安泰科|Wind|iFind|同花顺|生意社|亚洲金属网|铁合金在线|中汽协|EVTank)[：:\s]+", re.I)
_SPEC_RE = re.compile(r"[（(][^（）()]{0,16}?[0-9][^（）()]{0,12}?%[^（）()]*[）)]")
_STRATEGY_COLS = ("AI筛选原因", "AI 筛选原因", "状态说明", "筛选逻辑", "AI逻辑", "备注", "来源")


def anonymize(t):
    if not isinstance(t, str):
        return t
    s = _SRC_PREFIX.sub("", t)
    if "（品级）" not in s:
        s = _SPEC_RE.sub("（品级）", s)
    return s.strip()


def _is_date_str(v) -> bool:
    if not isinstance(v, str):
        return False
    s = v.strip()
    m = re.match(r"^(\d{4})[-/年]", s)
    return bool(m) and int(m.group(1)) >= 2000


def gen_workbook(name: str):
    src = SRC / name
    wb_src = load_workbook(src, read_only=False, data_only=False)
    wb_out = Workbook()
    wb_out.remove(wb_out.active)
    cat_name = wb_src.sheetnames[0]
    for ws in wb_src.worksheets:
        is_catalog = ws.title == cat_name
        ws_out = wb_out.create_sheet(title=anonymize(ws.title) if not is_catalog else ws.title)
        rng = random.Random(20260908 ^ hash(name) ^ hash(ws.title) % (2 ** 31))
        header_keys: list[str] = []
        for ri, row in enumerate(ws.iter_rows()):
            if is_catalog:
                if ri == 0:
                    header_keys = [str(c.value).strip() if c.value is not None else "" for c in row]
                vals = []
                for ci, cell in enumerate(row):
                    v = cell.value
                    if v is None:
                        vals.append(None)
                    elif isinstance(v, str):
                        head = header_keys[ci] if ci < len(header_keys) else ""
                        if ri > 0 and any(k in head for k in _STRATEGY_COLS):
                            vals.append("")
                        elif ri == 0:
                            vals.append(v)
                        else:
                            vals.append(anonymize(v))
                    else:
                        vals.append(v)  # 目录数值(Sheet Name/Col/序号/选中/置信度)原样保留
                ws_out.append(vals)
                continue
            # 数据 sheet: 前3行为 指标名/单位/频率(标题行也做同名脱敏)
            vals = []
            for ci, cell in enumerate(row):
                v = cell.value
                if v is None:
                    vals.append(None)
                elif isinstance(v, str):
                    if _is_date_str(v):
                        vals.append(v)
                    elif ri < 3:
                        vals.append(anonymize(v))
                    elif v.startswith("="):
                        vals.append(round(max(1.0, rng.random() * 2e4), 2))  # 公式→随机
                    else:
                        vals.append(anonymize(v))
                elif isinstance(v, (int, float)) and ci > 0 and ri >= 3:
                    base = 15000.0 if abs(v) < 300000 else 300000.0
                    vals.append(round(max(1.0, base * (0.3 + 1.4 * rng.random())), 2))
                else:
                    vals.append(v)
            ws_out.append(vals)
    dst = OUT / name
    wb_out.save(dst)
    print(f"[样例] {name}: sheets={len(wb_src.worksheets)}")


def gen_stock_file(name: str, subs: list[str], per_sub: int = 6):
    dst = OUT / "stock_targets" / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "产业链", "细分板块", "所属环节", "股票名称", "股票代码", "总市值(亿)", "AI筛选原因"])
    i = 0
    for si, sub in enumerate(subs):
        segment = "上游" if si % 3 == 0 else ("中游" if si % 3 == 1 else "下游")
        for k in range(per_sub):
            i += 1
            ws.append([i, "示例产业链", sub, f"{segment}-示例环节",
                       f"示例{sub[:2]}企业{chr(65 + k)}", f"999{i:03d}", "", ""])
    wb.save(dst)
    print(f"[样例] {name}: {i} 行(演示企业, 代码 999xxx 不存在)")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true",
                    help="generate and copy results into ./data (for the sample package machine)")
    args = ap.parse_args()
    if not SRC.exists() and not args.deploy:
        raise SystemExit("缺少真实 data/ 目录作为模板(仅用于结构)")
    OUT.mkdir(parents=True, exist_ok=True)
    for name in WORKBOOKS:
        if (SRC / name).exists():
            gen_workbook(name)
    gen_stock_file("个股标的_锂电.xlsx",
                   ["锂矿锂盐", "三元正极", "磷酸铁锂正极", "电解液", "负极", "隔膜",
                    "铜箔铝箔", "电池&电芯", "储能&集成", "新能源车"])
    gen_stock_file("个股标的_锡.xlsx", ["锡矿", "锡锭", "锡材", "锡下游"])
    gen_stock_file("个股标的_硅.xlsx",
                   ["工业硅", "有机硅", "多晶硅", "硅片", "电池片", "组件", "光伏辅材", "铝合金"])
    print("样例数据生成完成:", OUT)
    if args.deploy:
        import shutil
        data = ROOT / "data"
        data.mkdir(exist_ok=True)
        for name in WORKBOOKS:
            shutil.copy(str(OUT / name), str(data / name))
        st = data / "stock_targets"
        st.mkdir(exist_ok=True)
        for name in ("个股标的_锂电.xlsx", "个股标的_锡.xlsx", "个股标的_硅.xlsx"):
            shutil.copy(str(OUT / "stock_targets" / name), str(st / name))
        print("已部署到 data/(覆盖样例文件; 请重启看板)")


if __name__ == "__main__":
    main()
