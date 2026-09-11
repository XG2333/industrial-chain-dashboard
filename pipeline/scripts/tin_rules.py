# -*- coding: utf-8 -*-
"""Central deterministic rules for the tin industry workflow.

Rule tables and pure functions live here so catalog generation, directory
curation, selection, tagging, and rule documentation share one source of truth.
"""

from __future__ import annotations

import re
from collections import defaultdict

from catalog_utils import resolve_annualized_frequency
from selection_utils import CONTRACT_PATTERN, frequency_comparison_key, normalize_metric_title


AMOUNT_MARKERS = (
    "进口额",
    "出口额",
    "净出口额",
    "进口总额",
    "出口总额",
    "净出口总额",
    "进口金额",
    "出口金额",
    "净出口金额",
    "总额",
    "总值",
    "金额",
)


FREQ_CN = {
    "日": "日度",
    "周": "周度",
    "月": "月度",
    "季": "季度",
    "年": "年度",
}

FREQ_EN = {
    "日": "daily",
    "周": "weekly",
    "月": "monthly",
    "季": "quarterly",
    "年": "yearly",
}


def detect_freq(sn: str) -> str:
    for k, v in FREQ_CN.items():
        if k in sn:
            return v
    return "年度"


_FREQ_SUFFIX_PATTERN = re.compile(r"(日度|周度|月度|季度|年度)")


def detect_indicator_freq(name: str, fallback: str = "") -> str:
    annualized = resolve_annualized_frequency(name or "")
    if annualized:
        return annualized
    match = _FREQ_SUFFIX_PATTERN.search(name or "")
    if match:
        return match.group(1)
    return fallback or detect_freq("")


SECTOR_RULES = [
    ("锡矿", ["锡矿", "锡精矿", "矿砂", "精矿", "矿山", "锡矿砂", "马来西亚进口"]),
    ("锡锭", [
        "锡锭", "锡碇", "精炼锡", "精锡", "未锻轧", "1#锡", "1号锡",
        "沪锡", "LME", "LME锡", "锡库存", "锡仓单", "锡产量", "成交", "持仓",
    ]),
    ("锡材", ["焊料", "焊锡", "锡条", "锡丝", "锡粉", "锡合金", "巴氏合金", "锡材", "锡制品"]),
    ("镀锡板", ["镀锡板", "马口铁"]),
    ("铅蓄电池", ["铅蓄电池", "电蓄", "汽蓄", "摩托", "蓄电池"]),
    ("锡化工", ["二氧化锡", "锡酸钠", "氯化亚锡", "硫酸亚锡", "锡化工", "氧化锡"]),
    ("锡期货", ["期货", "合约", "仓单", "JFX", "ICDX"]),
    ("锡下游", ["光伏焊带", "MBB", "焊带", "消费", "需求"]),
    ("锡其他", ["其他价格", "其他"]),
]

SECTORS = [
    "锡矿",
    "锡锭",
    "锡材",
    "镀锡板",
    "铅蓄电池",
    "锡化工",
    "锡期货",
    "锡下游",
    "锡其他",
    "其他",
]


def classify_sector(sn: str) -> str:
    for sector, keywords in SECTOR_RULES:
        if any(k in sn for k in keywords):
            return sector
    return "其他"


def classify_category(sn: str) -> str:
    if "成本" in sn or "利润" in sn or "盈亏" in sn:
        return "四、成本利润"
    if any(k in sn for k in ["进出口", "进口", "出口"]):
        return "三、供需-进出口"
    if any(k in sn for k in ["库存", "仓单"]):
        return "三、供需-库存"
    if any(k in sn for k in ["需求", "消费", "销量"]):
        return "二、供需-需求"
    if "平衡" in sn:
        return "三、供需-平衡"
    if any(k in sn for k in ["产量", "产能", "储量", "开工", "加工费"]):
        return "二、供需-供给"
    if any(k in sn for k in ["成交", "持仓", "交易"]):
        return "五、量价"
    if any(k in sn for k in ["价格", "价差", "基差", "月差"]):
        return "一、价格"
    return "其他"


def _combined(name: str, sheet: str) -> str:
    return f"{name} {sheet}"


def _major_from_text(text: str) -> str:
    if 平衡 in text:
        return 平衡
    if any(k in text for k in (成本, 利润, 毛利率, 盈亏)):
        return 成本利润
    if any(k in text for k in (进出口, 进口, 出口, 出港, 到港, 贸易流向, 净出口, 发货量, 航运)):
        if not any(k in text for k in (价格, 平均价, 均价, 基差, 价差, 月差, 收盘价, 结算价, CIF, FOB, 升贴水, 溢价)):
            return 进出口
    if any(k in text for k in (库存, 仓单, 库容, 库销比, 库存天数, 库存周期)):
        return 库存
    if any(k in text for k in (
        产量, 产能, 开工, 排产, 自给率, 储量,
        市占率, 供应, 冶炼, CR5, 集中度, 出货情绪, 加工费,
    )):
        return 供给
    if any(k in text for k in (
        需求, 消费, 销量, 装机, 招标, 中标, 上险,
        保有量, 带电量, 渗透率, 装车, 充电桩, 换电站,
        批发, 零售, 消耗量, 配储, 要求, 建成规模, 出货量,
        工商业储能, 购货情绪, 成交情绪,
    )):
        return 需求
    if any(k in text for k in (
        价格, 平均价, 均价, 售价, 基差, 价差, 月差,
        收盘价, 结算价, 指数, 现货, 期货,
        CIF, FOB, 升贴水, 溢价,
    )):
        return 价格
    return 其他


def _major_from_text(text: str) -> str:
    if "平衡" in text:
        return "平衡"
    if any(k in text for k in ("成本", "利润", "毛利率", "盈亏")):
        return "成本利润"
    if any(k in text for k in AMOUNT_MARKERS) and any(
        k in text for k in ("进口", "出口")
    ):
        return "价格"
    if any(k in text for k in ("进出口", "进口", "出口", "出港", "到港", "贸易流向", "净出口", "发货量", "航运")):
        if not any(k in text for k in ("价格", "平均价", "均价", "基差", "价差", "月差", "收盘价", "结算价", "CIF", "FOB", "升贴水", "溢价")):
            return "进出口"
    if any(k in text for k in ("库存", "仓单", "库容", "库销比", "库存天数", "库存周期")):
        return "库存"
    if any(k in text for k in (
        "产量", "产能", "开工", "排产", "自给率", "储量",
        "市占率", "供应", "冶炼", "CR5", "集中度", "出货情绪", "加工费",
    )):
        return "供给"
    if any(k in text for k in (
        "需求", "消费", "销量", "装机", "招标", "中标", "上险",
        "保有量", "带电量", "渗透率", "装车", "充电桩", "换电站",
        "批发", "零售", "消耗量", "配储", "要求", "建成规模", "出货量",
        "工商业储能", "购货情绪", "成交情绪",
    )):
        return "需求"
    if any(k in text for k in (
        "价格", "平均价", "均价", "售价", "基差", "价差", "月差",
        "收盘价", "结算价", "指数", "现货", "期货",
        "CIF", "FOB", "升贴水", "溢价",
    )):
        return "价格"
    return "其他"


def classify_major(name: str, sheet: str) -> str:
    major = _major_from_text(name or "")
    if major != "其他":
        return major
    return _major_from_text(sheet or "")


def _sub_from_text(major: str, text: str) -> str:
    if major == "价格":
        if "月差" in text:
            return "月差"
        if any(k in text for k in AMOUNT_MARKERS):
            return "贸易金额"
        if any(k in text for k in ("期货", "合约", "收盘价", "结算价")):
            return "期货价格"
        if any(k in text for k in ("价差", "升贴水", "溢价", "基差", "期现")):
            return "价差"
        if "指数" in text:
            return "指数"
        if any(k in text for k in ("现货", "平均价", "均价", "价格")):
            return "现货价格"
        return "其他"
    if major == "成本利润":
        if any(k in text for k in ("利润", "毛利率", "盈亏")):
            return "利润"
        if "成本" in text:
            return "成本"
        return "其他"
    if major == "库存":
        if "仓单" in text:
            return "仓单"
        if "库容" in text:
            return "库容"
        if "库存天数" in text or "天数" in text:
            return "库存天数"
        if "库销比" in text:
            return "库销比"
        if "库存指数" in text or "指数" in text:
            return "库存指数"
        if "库存周期" in text:
            return "库存周期"
        return "其他"
    if major == "进出口":
        if "净出口" in text:
            return "净出口"
        if "进出口" in text and not any(k in text for k in (
            "进口量", "出口量", "进口额", "出口额", "进口均价", "出口均价", "进口数量", "出口数量",
        )):
            return "进出口"
        if any(k in text for k in ("进口", "到港", "进口量", "进口额", "进口数量")):
            return "进口"
        if any(k in text for k in ("出口", "出港", "出口量", "出口额", "出口数量")):
            return "出口"
        if "贸易流向" in text:
            return "贸易流向"
        return "其他"
    if major == "需求":
        if "出货量" in text:
            return "出货量"
        if any(k in text for k in ("销量", "上险量", "批发零售")):
            return "销量"
        if "装机" in text:
            return "装机"
        if "招标" in text:
            return "招标"
        if "中标" in text:
            return "中标"
        if "保有量" in text:
            return "保有量"
        if "渗透率" in text:
            return "渗透率"
        if "带电量" in text:
            return "带电量"
        if any(k in text for k in ("充电桩", "换电站")):
            return "充电基础设施"
        if "配储" in text or "要求" in text:
            return "政策要求"
        if "消耗量" in text:
            return "消耗量"
        return "其他"
    if major == "供给":
        if any(k in text for k in ("产量", "排产")):
            return "产量"
        if "产能" in text:
            return "产能"
        if "开工" in text:
            return "开工率"
        if "自给率" in text:
            return "自给率"
        if "储量" in text:
            return "储量"
        if "市占率" in text:
            return "市占率"
        if "CR5" in text or "集中度" in text:
            return "集中度"
        if "供应" in text:
            return "供给"
        if "加工费" in text:
            return "加工费"
        if "冶炼" in text:
            return "冶炼"
        if "建成规模" in text:
            return "建成规模"
        return "其他"
    if major == "平衡":
        return "平衡"
    if "成交持仓比" in text:
        return "成交持仓比"
    if "成交量" in text:
        return "成交量"
    if "持仓量" in text:
        return "持仓量"
    if "交易者数量" in text:
        return "交易者数量"
    return "其他"


_DEFAULT_SUB = {
    "价格": "价格",
    "成本利润": "成本利润",
    "库存": "库存",
    "进出口": "进出口",
    "需求": "需求",
    "供给": "供给",
    "平衡": "平衡",
    "其他": "其他",
}


def classify_sub(major: str, name: str, sheet: str) -> str:
    sub = _sub_from_text(major, name or "")
    if sub != "其他":
        return sub
    sub = _sub_from_text(major, sheet or "")
    if sub != "其他":
        return sub
    return _DEFAULT_SUB.get(major, "其他")



def classify_nature(major: str, sub: str, name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    if sub in ("价差", "月差"):
        return "差值"
    if sub == "成交持仓比" or any(k in text for k in ("开工率", "自给率", "渗透率", "库销比", "市占率", "利用率", "占比", "比例")):
        return "比率"
    if major == "库存":
        return "存量"
    if major in ("供给", "需求", "进出口"):
        return "流量"
    return "水平值"


# ---------------------------------------------------------------------------
# Tin selection rules
# ---------------------------------------------------------------------------

FREQ_RANK = {
    "日度": 4,
    "周度": 3,
    "月度": 2,
    "季度": 1,
    "年度": 0,
}

FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")

SPREAD_KEEP = ("01-05", "05-09", "09-01")

PROFIT_SELECT_TITLES = {
    "SMM: 锡矿进口盈亏水平: 日度",
    "SMM: 精炼锡进出口盈亏: 进口盈亏: 日度",
    "SMM: 精炼锡进出口盈亏: 出口盈亏: 日度",
}

COUNTRY_BREAKDOWN = (
    "澳大利亚", "日本", "韩国", "美国", "马来西亚", "印度尼西亚",
    "印尼", "印度", "泰国", "越南", "巴西", "秘鲁", "玻利维亚", "多民族玻利维亚国",
    "缅甸", "老挝", "俄罗斯", "俄罗斯联邦", "尼日利亚", "坦桑尼亚", "卢旺达",
    "菲律宾", "新加坡", "比利时", "荷兰", "德国", "德国联邦", "法国", "意大利",
    "西班牙", "英国", "加拿大", "墨西哥", "阿联酋", "阿拉伯联合酋长国",
    "沙特阿拉伯", "沙特", "土耳其", "图尔基耶", "中国台湾", "中国香港",
    "大韩民国", "阿根廷", "波兰", "捷克", "瑞典", "斯洛伐克", "葡萄牙",
    "哈萨克斯坦", "哥伦比亚", "加纳", "喀麦隆", "伊拉克", "伊朗",
    "伊朗伊斯兰共和国", "以色列", "埃及", "南非", "丹麦", "奥地利", "挪威",
    "芬兰", "瑞士", "爱尔兰", "希腊", "匈牙利", "罗马尼亚", "保加利亚",
    "乌克兰", "立陶宛", "拉脱维亚", "爱沙尼亚", "塞浦路斯", "马耳他",
    "刚果(金)", "刚果（金）", "刚果(布)", "刚果（布）", "刚果",
    "吉尔吉斯斯坦", "委内瑞拉", "其他",
    "JAMBI", "MUNTOK", "PANGKAL BALAM", "TANJUNG BALAI KARIMUN",
    "KOREA REPUBLIC OF", "JAPAN", "CHINA", "INDIA", "ITALY", "NETHERLANDS",
    "SINGAPORE", "SPAIN", "TAIWAN", "TURKEY", "UNITED STATES", "BELGIUM",
    "MALAYSIA", "PHILIPPINES", "VIET NAM", "HONG KONG", "MEXICO",
    "SOUTH AFRICA", "UNITED KINGDOM", "GERMANY", "AUSTRALIA", "THAILAND",
    "GERMANY FED. REP. OF", "KOREA REPUBLIC OF",
)

FOREIGN_SOURCE = (
    "韩国海关", "韩国", "印尼统计局", "印尼海关", "澳大利亚海关",
    "马来西亚海关", "马拉西亚", "印尼", "海外", "LME", "JFX", "ICDX",
)


def actual_frequency(title: str, fallback: str = "") -> str:
    annualized = resolve_annualized_frequency(title or "")
    if annualized:
        return annualized
    for suffix in FREQ_SUFFIXES:
        if title.endswith(suffix):
            return suffix
    return fallback or "日度"


def metric_base(title: str) -> str:
    return normalize_metric_title(title)


def is_total_import_export(title: str) -> bool:
    if any(token in title for token in ("总计", "合计", "总量", "净出口")):
        return True
    base = title.strip()
    for suffix in FREQ_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)].strip().rstrip(":").strip()
    if base.count(":") > 1:
        return False
    if "_其他" in title or base.endswith(": 其他"):
        return False
    if any(country in title for country in COUNTRY_BREAKDOWN if country != "其他"):
        return False
    if any(source in title for source in FOREIGN_SOURCE) and "中国" in title:
        return False
    return "进口" in base or "出口" in base


def evaluate_selection(
    major: str,
    sub: str,
    title: str,
    frequency: str,
) -> tuple[bool, str]:
    freq = actual_frequency(title, frequency)

    if "印尼交易所" in title and any(k in title for k in ("成交", "持仓", "成交量", "持仓量")):
        return False, "印尼交易所成交持仓不选中"

    if major == "价格":
        if sub == "期货价格":
            return bool(CONTRACT_PATTERN.search(title)), "价格仅保留主力/01/05/09合约"
        if sub == "成交持仓比":
            return True, "成交持仓比全部保留"
        if sub in ("持仓", "成交量"):
            return bool(CONTRACT_PATTERN.search(title)), "持仓/成交量仅保留主力/01/05/09合约"
        if sub == "月差":
            return any(token in title for token in SPREAD_KEEP), "月差仅保留01-05/05-09/09-01"
        if sub == "基差" or "基差" in title or "期现" in title:
            return "当月合约" in title or "现货升贴水" in title, "基差仅保留当月期现/现货升贴水"
        if sub in ("价差", "现货价差") or "价差" in title:
            return True, "价差全部保留"
        return False, "价格规则未覆盖，默认不选中"

    if major == "成本利润":
        if sub == "利润":
            return title in PROFIT_SELECT_TITLES, "利润仅保留矿端/进出口盈亏"
        return True, "成本利润按最高频后置处理"

    if major in ("库存", "供需-库存"):
        if sub == "仓单":
            if "分仓库_" in title and freq == "日度":
                return True, "仓单分仓库日度"
            if "仓单日报" in title and "期货" in title and "增减" not in title:
                return True, "总仓单保留"
            return False, "仓单仅保留分仓库日度或总仓单"
        return freq in ("周度", "月度"), "库存仅保留周度/月度"

    if major in ("供给", "供需-供给"):
        return freq in ("日度", "周度", "月度"), "供给仅保留日度/周度/月度"

    if major in ("进出口", "供需-进出口"):
        return freq == "月度" and is_total_import_export(title), "进出口仅保留总量月度"

    if major == "其他" and sub in ("成交量", "持仓量"):
        return bool(CONTRACT_PATTERN.search(title)), "成交量/持仓量仅保留主力/01/05/09合约"

    if major in ("平衡", "供需-平衡"):
        return True, "平衡类保留"

    return False, "规则未覆盖，默认不选中"


def select_rows(rows: list[dict]) -> list[dict]:
    rows = [dict(row) for row in rows]
    selected_by_rule: set[int] = set()
    for idx, row in enumerate(rows):
        selected, reason = evaluate_selection(
            row["major"],
            row["sub"],
            row["title"],
            row["frequency"],
        )
        row["selected"] = selected
        row["reason"] = reason
        if selected:
            selected_by_rule.add(idx)

    cost_groups: dict[tuple, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row["major"] == "成本利润" and row.get("selected"):
            cost_groups[frequency_comparison_key(row)].append(idx)

    for indices in cost_groups.values():
        if not indices:
            continue
        ranks = [
            (FREQ_RANK.get(actual_frequency(rows[i]["title"], rows[i]["frequency"]), -1), i)
            for i in indices
        ]
        best_rank = max(rank for rank, _ in ranks)
        kept = False
        for idx in indices:
            rank = FREQ_RANK.get(
                actual_frequency(rows[idx]["title"], rows[idx]["frequency"]), -1
            )
            if rank == best_rank:
                rows[idx]["selected"] = True
                rows[idx]["reason"] = "成本利润仅保留最高频"
                if kept:
                    rows[idx]["selected"] = False
                    rows[idx]["reason"] = "成本利润同频重复，只保留一条"
                kept = True
            else:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = "成本利润仅保留最高频"

    _dedup_warehouse(rows)

    return rows


def _scope_key(title: str) -> str:
    for marker in ("分仓库_", "分地区_"):
        idx = title.find(marker)
        if idx >= 0:
            tail = title[idx + len(marker):]
            return tail.split(":")[0].strip()
    return "TOTAL"


def _warehouse_key(title: str) -> str | None:
    marker = "分仓库_"
    idx = title.find(marker)
    if idx < 0:
        return None
    tail = title[idx + len(marker):]
    return tail.split(":")[0].strip()


def _dedup_warehouse(rows: list[dict]) -> None:
    warehouse_daily: dict[str, bool] = {}
    for row in rows:
        if row["major"] in ("库存", "供需-库存") and row["sub"] == "仓单":
            key = _warehouse_key(row["title"])
            if key and row["selected"]:
                warehouse_daily[key] = True
    for row in rows:
        if row["major"] in ("库存", "供需-库存") and row["sub"] != "仓单" and row["selected"]:
            key = _warehouse_key(row["title"])
            if key and warehouse_daily.get(key):
                row["selected"] = False
                row["reason"] = "仓单日度已覆盖同仓库周度库存"

    subtotal_warehouses: set[str] = set()
    for row in rows:
        if row["major"] in ("库存", "供需-库存") and row["sub"] != "仓单" and row["selected"] and "小计" in row["title"]:
            key = _scope_key(row["title"])
            if key:
                subtotal_warehouses.add(key)
    for row in rows:
        if row["major"] in ("库存", "供需-库存") and row["sub"] != "仓单" and row["selected"]:
            if "期货" in row["title"] and "小计" not in row["title"]:
                key = _scope_key(row["title"])
                if key and key in subtotal_warehouses:
                    row["selected"] = False
                    row["reason"] = "同仓库库存小计已保留，库存期货去重"


# ---------------------------------------------------------------------------
# Tin indicator tag rules
# ---------------------------------------------------------------------------

PRODUCT_RULES = [
    ("锡矿", ["锡矿", "锡精矿", "矿砂", "精矿"]),
    ("锡锭", ["锡锭", "锡碇", "精炼锡", "精锡", "未锻轧", "1#锡", "1号锡", "沪锡", "LME锡", "锡库存", "锡仓单"]),
    ("锡材", ["焊料", "焊锡", "锡条", "锡丝", "锡粉", "锡合金", "巴氏合金", "锡材", "锡制品"]),
    ("镀锡板", ["镀锡板", "马口铁"]),
    ("铅蓄电池", ["铅蓄电池", "电蓄", "汽蓄", "摩托", "蓄电池"]),
    ("锡化工", ["二氧化锡", "锡酸钠", "氯化亚锡", "硫酸亚锡", "锡化工", "氧化锡"]),
    ("光伏焊带", ["光伏焊带", "MBB", "焊带"]),
    ("锡期货", ["期货", "合约", "仓单", "JFX", "ICDX"]),
]


def extract_product(name: str, sheet: str, sector: str) -> str:
    text = _combined(name, sheet)
    for product, keywords in PRODUCT_RULES:
        if any(k in text for k in keywords):
            return product
    return sector if sector and sector != "其他" else "锡产业链"


RESEARCH_MAP = {
    "价格": "价格",
    "成本利润": "成本利润",
    "供给": "供给",
    "需求": "需求",
    "库存": "库存",
    "进出口": "进出口",
    "平衡": "平衡",
    "其他": "其他",
    "供需-供给": "供给",
    "供需-需求": "需求",
    "供需-库存": "库存",
    "供需-进出口": "进出口",
    "供需-平衡": "平衡",
}


def extract_indicator_type(major: str, sub: str, name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    if "成交持仓比" in text:
        return "成交持仓比"
    if "成交量" in text:
        return "成交量"
    if "持仓量" in text:
        return "持仓量"
    if any(k in text for k in ("基差", "期现", "升贴水")):
        return "基差"
    if any(k in text for k in ("价差", "溢价")):
        return "价差"
    if sub and sub != "其他":
        return sub
    return major if major != "其他" else "其他"


SPEC_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?V/\d+AH"),
    re.compile(r"\d+(?:\.\d+)?AH"),
    re.compile(r"\d+(?:\.\d+)?%"),
    re.compile(r"\d+#"),
    re.compile(r"\d+(?:\.\d+)?A"),
    re.compile(r"\d+(?:\.\d+)?mm"),
    re.compile(r"TLEAD\d+|TPURE\d+"),
    re.compile(r"SAC"),
]

SPEC_WORDS = [
    "驰名",
    "大型",
    "中型",
    "小型",
    "电动",
    "起动",
    "牵引",
    "固定",
    "无铅",
    "有铅",
    "精矿",
    "粗锡",
]


def extract_spec(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    found: list[str] = []
    for pattern in SPEC_PATTERNS:
        m = pattern.search(text)
        if m:
            found.append(m.group(0))
    for word in SPEC_WORDS:
        if word in text:
            found.append(word)
    return "; ".join(dict.fromkeys(found)) if found else "通用"


PROCESS_WORDS = [
    "精炼",
    "粗炼",
    "再生",
    "原生",
    "冶炼",
    "火法",
    "湿法",
    "电解",
    "采选",
    "进口矿",
    "国产矿",
    "自产矿",
    "外采矿",
]


def extract_process(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    found = [word for word in PROCESS_WORDS if word in text]
    return "; ".join(dict.fromkeys(found)) if found else "通用"


REGION_WORDS = (
    "云南", "广西", "湖南", "江西", "上海", "广东", "江苏", "苏州",
    "河北", "湖北", "浙江", "山东", "河南", "辽宁", "四川", "重庆",
    "天津", "安徽", "福建", "陕西", "甘肃", "内蒙古", "新疆", "西藏",
    "海南", "贵州", "青海", "宁夏", "山西", "吉林", "黑龙江", "北京",
    "毕尔巴鄂", "巴生港", "柔佛", "高雄", "釜山", "新加坡",
    "全球", "海外", "亚洲", "欧洲", "北美", "大洋洲", "中国",
)


def extract_region(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    for region in REGION_WORDS:
        if region in text:
            return region
    for region in COUNTRY_BREAKDOWN:
        if region in text:
            return region
    return "未指定"


CALIBER_WORDS = (
    "平均价", "最低价", "最高价", "收盘价", "结算价", "开盘价",
    "成交量", "持仓量", "成交持仓比", "库存量", "库存变化", "显性库存",
    "注册仓单", "注销仓单", "仓单日报", "分仓库", "分地区", "分国别",
    "分洲别", "分企业", "分类型", "总计", "合计", "总量", "累计",
    "净出口", "净进口", "小计", "预测", "计划", "累计值",
    "当月合约", "主力合约",
)


def extract_caliber(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    for caliber in CALIBER_WORDS:
        if caliber in text:
            return caliber
    return "未指定"


STATUS_WORDS = ("预测", "计划", "目标", "预算", "估算", "下月预计")


def extract_status(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    for status in STATUS_WORDS:
        if status in text:
            return status
    return "实际"


def build_tags(
    name: str,
    sheet: str,
    unit: str,
    freq: str,
    major: str,
    sub: str,
    sector: str,
) -> dict[str, str]:
    return {
        "产品": extract_product(name, sheet, sector),
        "研究主题": RESEARCH_MAP.get(major, major or "其他"),
        "指标类型": extract_indicator_type(major, sub, name, sheet),
        "规格": extract_spec(name, sheet),
        "工艺属性": extract_process(name, sheet),
        "地域": extract_region(name, sheet),
        "统计口径": extract_caliber(name, sheet),
        "状态": extract_status(name, sheet),
        "频率": freq or "未识别",
        "单位": unit or "未指定",
    }
