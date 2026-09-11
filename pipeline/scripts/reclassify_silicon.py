from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook


sys.path.insert(0, str(Path(__file__).resolve().parent))
from classification_candidates import candidate_plan


PRICE_UNIT_TOKENS = (
    "元/",
    "美元/",
    "欧元/",
)


def is_price_unit(unit: str) -> bool:
    return any(token in unit for token in PRICE_UNIT_TOKENS)


def classify_row(
    sheet: str,
    name: str,
    unit: str,
    old_major: str,
    old_sub: str,
) -> tuple[str, str]:
    n = name
    u = unit

    if "成交量" in n:
        return "价格", "成交量"
    if "成交持仓比" in n:
        return "价格", "成交持仓比"
    if "持仓" in n:
        return "价格", "持仓"
    if "月差" in n:
        return "价格", "月差"
    if "基差" in n or "期现价差" in n or "价差" in n:
        return "价格", "现货价差"
    if ("期货价格" in n or "收盘价" in n) and ("合约" in n or "主力" in n):
        return "价格", "期货价格"

    if "库存指数" in n:
        return "库存", "库存指数"
    if "库存天数" in n:
        return "库存", "库存天数"
    if "库存" in n and not any(k in n for k in ("进口量", "出口量", "净出口")):
        sub = "仓单" if "仓单" in n else "库存"
        return "库存", sub

    if "PMI" in n.upper() or ("指数" in n and "PMI" in sheet):
        return "其他", "宏观"

    cost_markers = (
        "成本",
        "LCOE",
        "lcoe",
        "折旧",
        "人工",
        "三费",
        "投资",
        "运维",
        "初始投资",
        "原料-",
        "包装-",
        "能耗-",
        "财务费用",
        "运费",
        "损耗",
        "辅料",
        "费用",
        "电耗",
        "水耗",
        "综合能耗",
        "耗量",
        "消耗",
        "余热利用率",
        "浆料",
        "银浆",
    )
    if any(marker in n for marker in cost_markers):
        return "成本利润", "成本"
    if "利润" in n or "盈亏" in n:
        return "成本利润", "利润"

    if "成本" in sheet and is_price_unit(u) and not any(k in n for k in ("价格", "利润")):
        return "成本利润", "成本"

    price_markers = (
        "价格",
        "电价",
        "平均价",
        "均价",
        "低价",
        "高价",
        "CIF",
        "FOB",
        "自提价",
        "中标均价",
    )
    if any(marker in n for marker in price_markers):
        return "价格", "现货价格"

    if "发电量" in n or "产量" in n or "排产" in n:
        return "供给", "产量"
    if "产能" in n:
        return "供给", "产能"
    if "开工率" in n or "开工" in n:
        return "供给", "开工率"
    if "供应量" in n:
        return "供给", "数量"
    if "平衡值" in n:
        return "平衡", "平衡"
    if "进口量" in n:
        return "进出口", "进出口"
    if "出口量" in n:
        return "进出口", "进出口"
    if "净出口" in n:
        return "进出口", "进出口"
    if any(marker in n for marker in ("表观消费量", "实际消费量", "终端消费量", "消费量", "需求量")):
        return "需求", "需求"
    if any(
        marker in n
        for marker in ("消费", "需求", "用电量", "装机", "消纳", "出货", "销量", "中标采购")
    ):
        sub = "销量" if ("销量" in n or "出货" in n) else "需求"
        return "需求", sub
    if "全球新增光伏装机" in sheet and any(
        unit.startswith(token) for token in ("GW", "万千瓦", "吉瓦", "MW")
    ):
        return "需求", "需求"
    if "净出口" in n:
        return "进出口", "进出口"
    if "进口" in n:
        return "进出口", "进出口"
    if "出口" in n:
        return "进出口", "进出口"
    if "平衡" in n:
        return "平衡", "平衡"

    if any(
        marker in n
        for marker in (
            "效率",
            "占比",
            "市场占有率",
            "市场份额",
            "供应率",
            "人均产出",
            "方块电阻",
            "转换效率",
            "厚度",
            "功率",
            "电压",
            "折算标准",
        )
    ) or "参数" in sheet:
        return "其他", "参数"

    if is_price_unit(u):
        return "价格", "现货价格"

    return old_major, old_sub



def _reorder_import_export(ws):
    sections = []
    current_sheet = ""
    start = None
    for row_idx in range(2, ws.max_row + 1):
        c0 = str(ws.cell(row_idx, 1).value or "").strip()
        if not c0:
            continue
        if "sht" in c0:
            continue
        if not c0.isdigit():
            if start is not None:
                sections.append((current_sheet, start, row_idx - 1))
            current_sheet = c0
            start = None
            continue
        c3 = str(ws.cell(row_idx, 4).value or "").strip()
        if not c3.isdigit():
            continue
        if start is None:
            start = row_idx
    if start is not None:
        sections.append((current_sheet, start, ws.max_row))

    def _ie_order(title):
        t = str(title or "")
        if "净出口" in t:
            return 0
        if "进口" in t and "出口" not in t:
            return 1
        if "出口" in t:
            return 2
        return 99
    for sheet_name, sec_start, sec_end in sections:
        sub = [ws.cell(r, 9).value for r in range(sec_start, sec_end + 1)]
        if not any(str(v) == "进出口" for v in sub):
            continue
        rows_data = []
        for r in range(sec_start, sec_end + 1):
            max_cols = min(ws.max_column, 14)
            row_vals = [ws.cell(r, c).value for c in range(1, max_cols + 1)]
            title = str(ws.cell(r, 5).value or "")
            order = _ie_order(title)
            rows_data.append((order, title, row_vals, r))
        rows_data.sort(key=lambda x: (x[0], x[1]))
        for i, (_, _, row_vals, src_row) in enumerate(rows_data):
            dst_row = sec_start + i
            if dst_row == src_row:
                continue
            for col_idx, val in enumerate(row_vals, 1):
                ws.cell(dst_row, col_idx).value = val

def main() -> None:
    parser = argparse.ArgumentParser(description="Reclassify silicon directory categories by name and unit.")
    parser.add_argument("--input", default="output/硅产业链数据_processed.xlsx")
    parser.add_argument("--output", default="output/硅产业链数据_processed_checked.xlsx")
    parser.add_argument("--report", default="output/硅产业链分类检查报告.md")
    args = parser.parse_args()

    source = Path(args.input).resolve()
    target = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    if not source.exists():
        raise SystemExit(f"Input file does not exist: {source}")

    if source != target:
        shutil.copy2(source, target)

    wb = load_workbook(target)
    ws = wb[wb.sheetnames[0]]

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
    total = 0
    changed = 0
    junk_rows: list[int] = []
    old_new = Counter()
    changes: list[tuple[str, str, str, str, str, str, str]] = []

    for row in ws.iter_rows(min_row=2):
        c0 = str(row[0].value).strip() if row[0].value is not None else ""
        if not c0:
            continue
        if "sht" in c0:
            continue
        if not c0.isdigit():
            current_sheet = c0
            continue

        c3 = str(row[3].value).strip() if row[3].value is not None else ""
        if not c3.isdigit():
            continue

        name = str(row[4].value).strip() if row[4].value is not None else ""
        if not name:
            continue
        unit = str(row[5].value).strip() if row[5].value is not None else ""
        total += 1
        if name == "指标名称" and unit == "单位":
            junk_rows.append(row[0].row)
            continue
        old_major = str(row[7].value).strip() if row[7].value is not None else ""
        old_sub = str(row[8].value).strip() if row[8].value is not None else ""

        plan = candidate_plan(name, current_sheet, industry="silicon")
        new_major = plan["major"]
        new_sub = plan["sub"]
        old_new[((old_major, old_sub), (new_major, new_sub))] += 1
        if new_major != old_major or new_sub != old_sub:
            changed += 1
            changes.append((current_sheet, name, unit, old_major, old_sub, new_major, new_sub))
            row[7].value = new_major
            row[8].value = new_sub

        candidate_tags = {}
        if plan["major_candidates"]:
            candidate_tags["候选大类"] = plan["major_candidates"]
        if plan["sub_candidates"]:
            candidate_tags["候选子类"] = plan["sub_candidates"]
        if plan["combinations"]:
            candidate_tags["候选分类组合"] = plan["combinations"]
        if candidate_tags:
            row[tag_col - 1].value = json.dumps(candidate_tags, ensure_ascii=False)

    if junk_rows:
        for row_idx in sorted(junk_rows, reverse=True):
            ws.delete_rows(row_idx)


    _reorder_import_export(ws)
    wb.save(target)
    wb.close()

    new_dist = Counter()
    wb2 = load_workbook(target, read_only=True, data_only=True)
    ws2 = wb2[wb2.sheetnames[0]]
    for r in ws2.iter_rows(min_row=2, values_only=True):
        c0 = str(r[0]).strip() if r[0] is not None else ""
        if not c0 or "sht" in c0 or not c0.isdigit():
            continue
        c3 = str(r[3]).strip() if r[3] is not None else ""
        if c3.isdigit():
            new_dist[(str(r[7]), str(r[8]))] += 1
    wb2.close()

    lines = [
        "# 硅产业链分类检查报告",
        "",
        f"- 输入文件：`{source.name}`",
        f"- 输出文件：`{target.name}`",
        f"- 原始目录行：{total + len(junk_rows)}",
        f"- 剔除伪指标行：{len(junk_rows)}",
        f"- 有效指标总数：{total}",
        f"- 调整数量：{changed}",
        "",
        "## 变更统计（旧分类 → 新分类）",
        "",
    ]
    for (old, new), count in old_new.most_common():
        if old == new:
            continue
        lines.append(f"- `{old[0]}/{old[1]}` → `{new[0]}/{new[1]}`：{count}")

    lines += [
        "",
        "## 复核后分类分布",
        "",
    ]
    for (major, sub), count in new_dist.most_common():
        lines.append(f"- {major}/{sub}：{count}")

    lines += [
        "",
        "## 调整示例",
        "",
    ]
    for item in changes[:40]:
        sheet, name, unit, old_major, old_sub, new_major, new_sub = item
        lines.append(
            f"- `{sheet}` | {name} | {unit} | "
            f"`{old_major}/{old_sub}` → `{new_major}/{new_sub}`"
        )

    lines += [
        "",
        "## 分类错误原因与修复思路",
        "",
        "1. Skill2 的 mock 分类器主要按指标名称关键词匹配，缺少单位与所在 Sheet 的上下文，导致电价、装机量、价格指数、PMI 子指数等被误判。",
        "2. 目录写入层的 `_infer_category_cn/_infer_subcategory_cn` 使用通用默认规则，容易出现 `平衡/产量`、`进出口/进口`、`其他/其他` 这类大类与指标实际含义不一致的结果。",
        "3. 现有 `selection_rules.docx` 是筛选规则，不是分类规则，没有定义指标级消歧；例如未区分“进口量”和“进口ADC12宁波CIF低价”，也未区分“成本模型里的价格”和“现货价格”。",
        "4. 原工作流缺少硅产业链的后置分类复核步骤。本次新增脚本按“指标名称 + 单位 + 所在 Sheet”重新判定大类/子类，并优先处理库存、成本利润、价格、平衡表成分，再处理供需进出口，最后处理参数类。",
        "5. 建议后续把这套判定规则并入 workflow，作为 Skill2 之后的强制分类复核；同时修复 Skill1 对重复“指标名称/单位”表头的识别，避免目录中出现伪指标。",
    ]

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reclassified {target}: total={total}, changed={changed}")
    print(f"Report written: {report_path}")


if __name__ == "__main__":
    main()
