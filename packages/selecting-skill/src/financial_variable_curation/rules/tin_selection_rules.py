from __future__ import annotations

import re
from collections import defaultdict


FREQ_RANK = {
    "日度": 4,
    "周度": 3,
    "月度": 2,
    "季度": 1,
    "年度": 0,
}

FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")

CONTRACT_PATTERN = re.compile(
    r"(主力合约|01合约|05合约|09合约|(?<!十)一月合约|五月合约|九月合约)"
)

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
    for suffix in FREQ_SUFFIXES:
        if title.endswith(suffix):
            return suffix
    return fallback or "日度"


def metric_base(title: str) -> str:
    for suffix in FREQ_SUFFIXES:
        if title.endswith(suffix):
            return title[: -len(suffix)].strip().rstrip(":").strip()
    return title.strip()


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
        if sub == "持仓":
            return bool(CONTRACT_PATTERN.search(title)), "持仓仅保留主力/01/05/09合约"
        if sub == "月差":
            return any(token in title for token in SPREAD_KEEP), "月差仅保留01-05/05-09/09-01"
        if sub == "基差":
            return "当月合约" in title or "现货升贴水" in title, "基差仅保留当月期现/现货升贴水"
        if sub == "现货价差":
            return True, "现货价差全部保留"
        return False, "价格规则未覆盖，默认不选中"

    if major == "成本利润":
        if sub == "利润":
            return title in PROFIT_SELECT_TITLES, "利润仅保留矿端/进出口盈亏"
        return True, "成本利润按最高频后置处理"

    if major == "库存":
        if sub == "仓单":
            if "分仓库" in title and freq == "日度":
                return True, "仓单分仓库日度"
            if "仓单日报" in title and "期货" in title and "增减" not in title:
                return True, "总仓单保留"
            return False, "仓单仅保留分仓库日度或总仓单"
        return freq in ("周度", "月度"), "库存仅保留周度/月度"

    if major == "供应":
        return freq in ("日度", "周度", "月度"), "供给仅保留日度/周度/月度"

    if major == "进出口":
        return freq == "月度" and is_total_import_export(title), "进出口仅保留总量月度"

    if major == "其他" and sub == "成交量":
        return bool(CONTRACT_PATTERN.search(title)), "成交量仅保留主力/01/05/09合约"

    if major == "平衡":
        return True, "平衡类保留"

    return False, "规则未覆盖，默认不选中"


def select_rows(rows: list[dict]) -> list[dict]:
    rows = [dict(row) for row in rows]
    cost_groups: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row["major"] == "成本利润" and row["sub"] == "成本":
            cost_groups[metric_base(row["title"])].append(idx)

    selected_by_rule: set[int] = set()
    for idx, row in enumerate(rows):
        selected, reason = evaluate_selection(
            row["major"],
            row["sub"],
            row["title"],
            row["frequency"],
        )
        if row["major"] == "成本利润" and row["sub"] != "利润":
            continue
        row["selected"] = selected
        row["reason"] = reason
        if selected:
            selected_by_rule.add(idx)

    for base, indices in cost_groups.items():
        if not indices:
            continue
        best_rank = max(FREQ_RANK.get(rows[i]["frequency"], -1) for i in indices)
        for idx in indices:
            keep = FREQ_RANK.get(rows[idx]["frequency"], -1) == best_rank
            rows[idx]["selected"] = keep
            rows[idx]["reason"] = "成本利润仅保留最高频" if keep else "成本利润仅保留最高频"
            if keep:
                selected_by_rule.add(idx)

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
        if row["major"] == "库存" and row["sub"] == "仓单":
            key = _warehouse_key(row["title"])
            if key and row["selected"]:
                warehouse_daily[key] = True
    for row in rows:
        if row["major"] == "库存" and row["sub"] != "仓单" and row["selected"]:
            key = _warehouse_key(row["title"])
            if key and warehouse_daily.get(key):
                row["selected"] = False
                row["reason"] = "仓单日度已覆盖同仓库周度库存"

    subtotal_warehouses: set[str] = set()
    for row in rows:
        if row["major"] == "库存" and row["sub"] != "仓单" and row["selected"] and "小计" in row["title"]:
            key = _scope_key(row["title"])
            if key:
                subtotal_warehouses.add(key)
    for row in rows:
        if row["major"] == "库存" and row["sub"] != "仓单" and row["selected"]:
            if "期货" in row["title"] and "小计" not in row["title"]:
                key = _scope_key(row["title"])
                if key and key in subtotal_warehouses:
                    row["selected"] = False
                    row["reason"] = "同仓库库存小计已保留，库存期货去重"
