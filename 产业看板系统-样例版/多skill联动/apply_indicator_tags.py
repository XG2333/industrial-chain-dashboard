from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook


TAG_COLUMN = "指标标签"
FREQS = ("日度", "周度", "月度", "季度", "年度")

_PRODUCT_RULES = [
    ("光伏玻璃", ["光伏玻璃", "光伏EVA", "EVA胶膜", "POE胶膜"]),
    ("光伏胶膜", ["光伏胶膜", "EVA胶膜"]),
    ("光伏背板", ["光伏背板", "背板"]),
    ("光伏边框", ["光伏边框", "边框"]),
    ("光伏支架", ["光伏支架", "支架"]),
    ("光伏网板", ["光伏网板", "网板"]),
    ("焊带", ["焊带"]),
    ("逆变器", ["逆变器"]),
    ("光伏硅胶", ["光伏硅胶", "硅胶"]),
    ("硅片", ["硅片", "182mm", "210mm", "166mm", "M10", "M12", "G12"]),
    ("电池片", ["电池片", "PERC", "TOPCon", "HJT", "BC电池"]),
    ("组件", ["组件", "T型", "双玻", "单玻"]),
    ("多晶硅", ["多晶硅", "硅料", "致密料", "菜花料", "复投料", "颗粒硅"]),
    (
        "工业硅",
        [
            "工业硅",
            "金属硅",
            "553",
            "441",
            "421",
            "3303",
            "2202",
            "2205",
            "1101",
            "521",
            "551",
            "411",
            "97硅",
            "99硅",
            "通氧",
            "不通氧",
        ],
    ),
    ("有机硅", ["有机硅", "DMC", "硅油", "生胶", "107胶", "110胶", "白炭黑"]),
    ("三氯氢硅", ["三氯氢硅"]),
    ("硅粉", ["硅粉"]),
    ("石英砂", ["石英砂"]),
    ("硅石", ["硅石"]),
    ("铝合金", ["铝合金"]),
    ("光伏需求", ["装机", "发电", "用电", "消纳", "消费", "需求"]),
]

_RESEARCH_RULES = [
    (
        "价格",
        [
            "价格",
            "电价",
            "均价",
            "平均价",
            "收盘价",
            "结算价",
            "基差",
            "月差",
            "价差",
            "持仓",
            "成交量",
            "成交持仓比",
        ],
    ),
    (
        "成本利润",
        [
            "成本",
            "利润",
            "LCOE",
            "折旧",
            "人工",
            "电耗",
            "水耗",
            "能耗",
            "耗量",
            "消耗",
            "浆料",
            "银浆",
            "盈亏",
        ],
    ),
    ("库存", ["库存", "仓单"]),
    ("供给", ["产量", "产能", "开工率", "供应量", "排产", "发电量"]),
    ("需求", ["需求", "消费", "装机", "用电", "消纳", "出货", "销量"]),
    ("进出口", ["进口", "出口", "净出口"]),
    ("平衡", ["平衡"]),
    ("其他", ["PMI", "指数", "效率", "占比", "功率", "电压", "厚度"]),
]

_INDICATOR_TYPE_RULES = [
    ("成交持仓比", ["成交持仓比"]),
    ("成交量", ["成交量"]),
    ("持仓", ["持仓"]),
    ("月差", ["月差"]),
    ("基差", ["基差", "期现", "期现价差", "升贴水"]),
    ("现货价差", ["现货价差", "价差"]),
    ("期货价格", ["期货价格", "收盘价", "结算价", "主力合约", "合约"]),
    (
        "现货价格",
        [
            "平均价",
            "均价",
            "低价",
            "高价",
            "价格",
            "现货价格",
            "现货价",
            "最低价",
            "最高价",
            "电价",
            "出厂价",
            "到港价",
            "港口价",
            "CIF",
            "FOB",
            "自提价",
            "中标均价",
        ],
    ),
    (
        "成本",
        ["成本", "LCOE", "折旧", "人工", "投资", "电耗", "水耗", "能耗", "耗量", "浆料", "银浆"],
    ),
    ("利润", ["利润", "盈亏"]),
    ("库存指数", ["库存指数"]),
    ("库存天数", ["库存天数"]),
    ("仓单", ["仓单"]),
    ("库存", ["库存"]),
    ("产量", ["产量", "发电量", "排产"]),
    ("产能", ["产能"]),
    ("开工率", ["开工率", "开工"]),
    ("净出口", ["净出口"]),
    ("出口", ["出口"]),
    ("进口", ["进口"]),
    ("销量", ["销量", "出货"]),
    ("需求", ["需求", "消费", "装机", "用电", "消纳"]),
    ("平衡", ["平衡"]),
    ("宏观", ["PMI", "宏观"]),
    ("参数", ["效率", "占比", "功率", "电压", "厚度", "参数"]),
]

_SPEC_PATTERNS = [
    re.compile(r"(?<!\d)\d{3,4}#"),
    re.compile(r"(?<!\d)\d{2}(?:硅|#)"),
    re.compile(r"(?:N|P|T)型"),
    re.compile(r"\d+(?:\.\d+)?(?:mm|MM|cm|μm|um)"),
    re.compile(r"M(?:10|12|6|4)"),
    re.compile(r"G12(?:R)?"),
    re.compile(r"\d{2,3}(?:片|串|瓦)"),
]

_PROCESS_KEYWORDS = [
    "不通氧",
    "通氧",
    "化学级",
    "冶金级",
    "高纯",
    "致密料",
    "菜花料",
    "复投料",
    "颗粒硅",
    "粉料",
    "块状",
    "粒状",
    "原生",
    "再生",
    "免洗",
    "湿法",
    "干法",
    "流化床",
    "改良西门子",
    "单晶",
    "多晶",
    "单玻",
    "双玻",
]

_REGION_KEYWORDS = [
    "内蒙古",
    "东北",
    "华东",
    "华南",
    "华北",
    "华中",
    "西南",
    "西北",
    "黄埔港",
    "天津港",
    "连云港",
    "钦州港",
    "防城港",
    "青岛港",
    "上海港",
    "广州港",
    "宁波港",
    "昆明",
    "新疆",
    "云南",
    "四川",
    "内蒙",
    "广西",
    "青海",
    "甘肃",
    "陕西",
    "宁夏",
    "辽宁",
    "上海",
    "广东",
    "江苏",
    "浙江",
    "山东",
    "天津",
    "重庆",
    "福建",
    "江西",
    "湖南",
    "湖北",
    "河北",
    "河南",
    "安徽",
    "北京",
    "海南",
    "贵州",
    "山西",
    "黑龙江",
    "吉林",
    "西藏",
    "香港",
    "台湾",
    "中国",
    "美国",
    "日本",
    "韩国",
    "德国",
    "挪威",
    "马来西亚",
    "泰国",
    "越南",
    "印度",
    "欧洲",
    "欧盟",
    "东南亚",
    "澳大利亚",
    "巴西",
    "俄罗斯",
    "中东",
    "全球",
    "海外",
]

_CALIBER_KEYWORDS = [
    "加权平均价",
    "平均价",
    "均价",
    "最低价",
    "最高价",
    "收盘价",
    "结算价",
    "开盘价",
    "现货价",
    "出厂价",
    "到港价",
    "港口价",
    "含税",
    "不含税",
    "基差",
    "月差",
    "价差",
    "升贴水",
    "现货价格",
    "期货价格",
    "库存指数",
    "库存天数",
    "分仓库",
    "分地区",
    "分国别",
    "总计",
    "合计",
    "总量",
    "进口量",
    "出口量",
    "净出口",
    "需求量",
    "消费量",
    "开工率",
    "平衡值",
    "PMI",
    "指数",
    "功率",
    "效率",
    "厚度",
    "电压",
    "成交量",
    "持仓",
    "主力合约",
    "当月合约",
    "连一合约",
]

_CONTRACT_PATTERN = re.compile(
    r"(主力合约|当月合约|0\d合约|连[一二三四五六七八九十]+合约|"
    r"[一二三四五六七八九十]{1,2}月合约)"
)


def _find_first_rule(text: str, rules: list[tuple[str, list[str]]]) -> str:
    for tag, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return tag
    return ""


def _find_all_keywords(text: str, keywords: list[str]) -> list[str]:
    found: list[str] = []
    for keyword in keywords:
        if keyword in text and not any(keyword in existing for existing in found):
            found.append(keyword)
    return found


def _find_first_keyword(text: str, keywords: list[str]) -> str:
    for keyword in keywords:
        if keyword in text:
            return keyword
    return ""


def _first_region(text: str) -> str:
    matches = [(text.find(keyword), keyword) for keyword in _REGION_KEYWORDS if keyword in text]
    if not matches:
        return ""
    return min(matches, key=lambda item: (item[0], -len(item[1])))[1]


def _extract_specs(text: str) -> str:
    found: list[str] = []
    for pattern in _SPEC_PATTERNS:
        for match in pattern.findall(text):
            if match not in found:
                found.append(match)
    return ",".join(found)


def _extract_frequency(frequency: str, name: str) -> str:
    freq = str(frequency or "").strip()
    if freq in FREQS:
        return freq
    for suffix in FREQS:
        if suffix in (name or ""):
            return suffix
    suffix = re.search(r"([日周月季年])(?:度)?$", name or "")
    if suffix:
        return {"日": "日度", "周": "周度", "月": "月度", "季": "季度", "年": "年度"}[
            suffix.group(1)
        ]
    return "未识别"


def _extract_status(text: str) -> str:
    for status in ("预测", "计划", "目标", "预算", "估算"):
        if status in text:
            return status
    return "实际"


def _extract_research(name: str, sheet: str, major: str) -> str:
    combined = f"{name} {sheet}"
    if "PMI" in combined.upper():
        return "其他"
    if "平衡值" in name:
        return "平衡"
    if any(
        marker in name
        for marker in (
            "成本指数",
            "成本模型",
            "成本(",
            "初始投资",
            "成本",
            "LCOE",
            "折旧",
            "人工",
            "投资",
            "电耗",
            "水耗",
            "能耗",
            "耗量",
            "浆料",
            "银浆",
            "利润",
            "盈亏",
        )
    ):
        return "成本利润"
    if any(
        marker in name
        for marker in (
            "价格",
            "电价",
            "均价",
            "平均价",
            "收盘价",
            "结算价",
            "基差",
            "月差",
            "价差",
            "持仓",
            "成交量",
            "成交持仓比",
            "低价",
            "高价",
            "CIF",
            "FOB",
            "自提价",
            "港口价",
            "出厂价",
            "到港价",
            "含税",
            "不含税",
        )
    ):
        return "价格"
    if any(marker in name for marker in ("净出口", "进口量", "出口量", "进口", "出口")):
        return "进出口"
    if any(marker in name for marker in ("库存", "仓单")):
        return "库存"
    if any(marker in name for marker in ("产量", "产能", "开工率", "供应量", "排产", "发电量")):
        return "供给"
    if any(marker in name for marker in ("需求", "消费", "装机", "用电", "消纳", "出货", "销量")):
        return "需求"
    return major if major and major != "未识别" else "其他"


def _extract_indicator_type(name: str, sheet: str, sub: str, major: str) -> str:
    if "PMI" in f"{name} {sheet}".upper():
        return "宏观"
    if "平衡值" in name:
        return "平衡"
    if "供应量" in name:
        return "数量"
    if "成本指数" in name:
        return "成本"
    rule_type = _find_first_rule(name, _INDICATOR_TYPE_RULES)
    if rule_type:
        return rule_type
    return (
        sub
        if sub and sub not in ("其他", "未识别")
        else (major if major and major != "未识别" else "未识别")
    )


def extract_indicator_tags(
    sheet: str,
    name: str,
    unit: str,
    frequency: str,
    major: str,
    sub: str,
) -> dict[str, str]:
    name = str(name or "")
    sheet = str(sheet or "")
    combined = f"{name} {sheet}"

    product = _find_first_rule(name, _PRODUCT_RULES)
    if not product:
        product = _find_first_rule(sheet, _PRODUCT_RULES)

    research = _extract_research(name, sheet, major)
    indicator_type = _extract_indicator_type(name, sheet, sub, major)

    tags = {
        "产品": product or "未识别",
        "研究主题": research or "未识别",
        "指标类型": indicator_type or "未识别",
        "规格": _extract_specs(name) or "未识别",
        "工艺属性": ",".join(_find_all_keywords(name, _PROCESS_KEYWORDS)) or "未识别",
        "地域": _first_region(combined) or "未识别",
        "统计口径": _find_first_keyword(name, _CALIBER_KEYWORDS) or "未识别",
        "状态": _extract_status(name),
        "频率": _extract_frequency(frequency, name),
    }

    contract = _CONTRACT_PATTERN.search(name)
    if contract:
        tags["合约"] = contract.group(1)
    return tags


def _write_report(
    report_path: Path,
    path: Path,
    total: int,
    coverage: Counter,
    examples: list[tuple[str, str, str, dict[str, str]]],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 硅产业链指标标签报告",
        "",
        f"- 输入文件：`{path.name}`",
        f"- 有效指标数：{total}",
        "",
        "## 标签覆盖率",
        "",
    ]
    for key in (
        "产品",
        "研究主题",
        "指标类型",
        "规格",
        "工艺属性",
        "地域",
        "统计口径",
        "状态",
        "频率",
    ):
        lines.append(f"- {key}：{coverage[key]}/{total}")
    lines += ["", "## 未识别示例", ""]
    for sheet, name, unit, tags in examples[:40]:
        lines.append(
            f"- {sheet} | {name} | {unit} | {json.dumps(tags, ensure_ascii=False)}"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")


def apply_indicator_tags_on_workbook(wb) -> tuple[int, Counter, list[tuple[str, str, str, dict[str, str]]]]:
    """在已加载的 wb 上执行指标标签（共享 wb，不 load/save）。

    供合并链（workflow_merged_stage.py）复用；apply_indicator_tags 包装
    load/save。返回 (total, coverage, examples)。
    """
    ws = wb[wb.sheetnames[0]]
    headers = [str(cell.value).strip() if cell.value is not None else "" for cell in ws[1]]
    if TAG_COLUMN in headers:
        tag_col = headers.index(TAG_COLUMN) + 1
    else:
        tag_col = len(headers) + 1
        ws.cell(1, tag_col, TAG_COLUMN)

    current_sheet = ""
    total = 0
    coverage: Counter = Counter()
    examples: list[tuple[str, str, str, dict[str, str]]] = []

    for row in ws.iter_rows(min_row=2):
        c0 = str(row[0].value).strip() if row[0].value is not None else ""
        if not c0 or "sht" in c0:
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
        frequency = str(row[2].value).strip() if row[2].value is not None else ""
        major = str(row[7].value).strip() if row[7].value is not None else ""
        sub = str(row[8].value).strip() if row[8].value is not None else ""

        tags = extract_indicator_tags(
            current_sheet,
            name,
            unit,
            frequency,
            major,
            sub,
        )

        # Preserve classification candidate metadata that earlier deterministic
        # calibration wrote into the same tag column. AI-assisted curation uses
        # these fields to constrain its choices, so they must survive this pass.
        raw_existing = row[tag_col - 1].value
        if raw_existing:
            try:
                existing = json.loads(str(raw_existing))
                for field in ("候选大类", "候选子类", "候选分类组合"):
                    if field in existing:
                        tags[field] = existing[field]
            except Exception:
                pass

        row[tag_col - 1].value = json.dumps(tags, ensure_ascii=False)
        total += 1
        for key in (
            "产品",
            "研究主题",
            "指标类型",
            "规格",
            "工艺属性",
            "地域",
            "统计口径",
            "状态",
            "频率",
        ):
            if tags.get(key) not in (None, "", "未识别"):
                coverage[key] += 1
        if not examples and (
            tags.get("产品") == "未识别"
            or tags.get("地域") == "未识别"
            or tags.get("统计口径") == "未识别"
        ):
            examples.append((current_sheet, name, unit, tags))

    return total, coverage, examples


def apply_indicator_tags(path: Path, report_path: Path | None = None) -> Path:
    path = Path(path).resolve()
    tmp = path.with_name(f"{path.stem}__tmp_tags.xlsx")
    shutil.copy2(path, tmp)

    wb = load_workbook(tmp)
    total, coverage, examples = apply_indicator_tags_on_workbook(wb)
    wb.save(tmp)
    wb.close()
    try:
        tmp.replace(path)
    except PermissionError:
        print(f"Permission error writing {path}; temp file kept at {tmp}")
        raise

    if report_path:
        _write_report(Path(report_path), path, total, coverage, examples)
    print(f"Applied indicator tags to {path}: total={total}")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add indicator tags column to silicon directory.")
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    report_path = Path(args.report) if args.report else None
    for raw_path in args.inputs:
        apply_indicator_tags(Path(raw_path), report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
