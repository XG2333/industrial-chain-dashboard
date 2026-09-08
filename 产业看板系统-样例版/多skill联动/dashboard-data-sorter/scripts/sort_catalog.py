# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import ast
import json
import re
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink


MAJOR_ORDER = [
    "价格",
    "成本利润",
    "库存",
    "供给",
    "供应",
    "需求",
    "进出口",
    "平衡",
    "其他",
]

SUB_ORDER = {
    "价格": ["价格", "现货价格", "贸易金额", "期货价格", "现货价差", "价差", "基差", "月差", "指数"],
    "成本利润": ["成本", "利润", "其他"],
    "库存": ["库存", "库存天数", "库销比", "仓单", "库存指数", "其他"],
    "供给": ["产能", "产量", "开工率", "加工费", "冶炼", "自给率", "集中度", "成交量", "持仓", "数量", "储量", "其他"],
    "供应": ["产能", "产量", "开工率", "成交量", "持仓", "数量", "储量"],
    "需求": ["需求", "销量", "装机", "招标", "中标", "保有量", "带电量", "渗透率", "充电基础设施", "政策要求", "消耗量", "出货量", "其他"],
    "进出口": ["进出口", "净出口", "进口", "出口"],
    "平衡": ["平衡", "产量"],
    "其他": ["其他"],
}

COMPOSITE_SUBS = ["成交量", "成交", "持仓", "持仓量", "成交持仓比"]
COMPOSITE_SUB_ORDER = ["成交量", "成交", "持仓", "持仓量", "成交持仓比"]

COMPOSITE_ROLE_ORDER = {
    "market_activity": ["volume", "open_interest", "oi_volume_ratio"],
    "trade": ["import", "export", "net_export"],
    "balance": ["production", "import", "export", "demand", "balance"],
}

COMPOSITE_REASON_LABELS = {
    "market_activity": "该指标属于同一成交持仓复合组，按成交量→持仓量→持仓/成交比排列。",
    "trade": "该指标属于同一进出口复合组，按进口→出口→净出口排列。",
    "balance": "该指标属于供需平衡组，按产量→进口→出口→需求→平衡排列。",
}

COMPOSITE_TYPE_ORDER = {
    "market_activity": 0,
    "trade": 1,
    "balance": 2,
}

# 规则中的半年频实际数据不存在，排序时忽略；实际频率为 日/周/月/季/年。
FREQ_ORDER = ["日度", "周度", "月度", "季度", "年度"]

INDICATOR_VARIABLE_WORDS = [
    "现货价格",
    "期货价格",
    "收盘价",
    "价格指数",
    "价格",
    "供需平衡",
    "平衡",
    "成交持仓比",
    "成交量",
    "成交额",
    "持仓量",
    "持仓",
    "库存天数",
    "库存指数",
    "库存量",
    "库存",
    "产量",
    "产能",
    "年化",
    "预测值",
    "预测",
    "开工率",
    "表观消费量",
    "消费量",
    "需求量",
    "供给量",
    "进口量",
    "出口量",
    "净出口额",
    "净出口",
    "进口额",
    "出口额",
    "进出口",
    "进口",
    "出口",
    "总计",
    "合计",
    "总额",
    "总量",
    "总",
    "金额",
    "利润",
    "成本",
    "价差",
    "基差",
    "月差",
    "同比",
    "环比",
    "值",
    "量",
    "额",
    "价",
]

EXCHANGE_PREFIXES = ["SHFE:", "GFEX:", "DCE:", "CZCE:", "INE:"]
SOURCE_PREFIXES = ["SMM:", "Mysteel:", "百川:", "Wind:", "iFind:"]
INDICATOR_SPEC_WORDS = [
    "含税",
    "不含税",
    "出厂",
    "到厂",
    "到港",
    "均价",
    "平均价",
    "平均",
    "长单",
    "散单",
    "现货",
    "期货",
    "高端款",
    "中端款",
    "低端款",
    "回收型",
    "容量型",
    "动力型",
    "储能型",
    "高容量型",
    "高倍率型",
    "工业级",
    "电池级",
    "材料级",
    "电芯级",
    "优等品",
    "一级品",
    "二级品",
    "合格品",
    "规格",
    "型号",
    "粒度",
    "纯度",
    "含量",
]

CHINESE_MONTH_NUMBERS = {
    "一月": "01",
    "二月": "02",
    "三月": "03",
    "四月": "04",
    "五月": "05",
    "六月": "06",
    "七月": "07",
    "八月": "08",
    "九月": "09",
    "十月": "10",
    "十一月": "11",
    "十二月": "12",
}

FREQ_WORDS = ["日度", "周度", "月度", "季度", "年度"]

CHINA_KEYWORDS = [
    "中国",
    "国产",
    "国内",
    "中国大陆",
    "中国台湾",
    "中国香港",
    "中国澳门",
]

CHINA_REGIONS = {
    "中国",
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "香港",
    "澳门",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "南通",
    "钦州",
    "镇江",
    "青岛",
    "大连",
    "广州",
    "深圳",
    "厦门",
    "宁波",
    "珠海",
    "湛江",
    "港口汇总",
}

FOREIGN_REGIONS = {
    "韩国",
    "美国",
    "日本",
    "英国",
    "德国",
    "智利",
    "阿根廷",
    "澳大利亚",
    "巴西",
    "意大利",
    "印尼",
    "印度尼西亚",
    "泰国",
    "比利时",
    "马来西亚",
    "菲律宾",
    "印度",
    "俄罗斯",
    "加拿大",
    "法国",
    "荷兰",
    "新加坡",
    "西班牙",
    "土耳其",
    "图尔基耶",
    "越南",
    "缅甸",
    "刚果",
    "刚果（金）",
    "刚果（布）",
    "尼日利亚",
    "玻利维亚",
    "喀麦隆",
    "哥伦比亚",
    "大韩民国",
    "墨西哥",
    "南非",
    "秘鲁",
    "津巴布韦",
    "马里",
    "卢旺达",
    "非洲",
    "奥地利",
    "波兰",
    "瑞士",
    "瑞典",
    "挪威",
    "丹麦",
    "芬兰",
    "乌克兰",
    "哈萨克斯坦",
    "蒙古",
    "阿联酋",
    "沙特阿拉伯",
    "伊朗",
    "以色列",
    "埃及",
    "摩洛哥",
    "巴基斯坦",
    "孟加拉国",
    "斯里兰卡",
    "新西兰",
    "葡萄牙",
    "爱尔兰",
    "希腊",
    "匈牙利",
    "捷克",
    "斯洛伐克",
    "罗马尼亚",
    "保加利亚",
    "塞尔维亚",
    "克罗地亚",
    "斯洛文尼亚",
    "立陶宛",
    "拉脱维亚",
    "爱沙尼亚",
    "卢森堡",
}

NODE_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "sector_node_rules.json"
NORMALIZED_NAME_HEADER = "指标名称归一化"
SORT_REASON_HEADER = "排序说明"

POLICY_ORDER = {
    "spot_price": 0,
    "futures_price": 1,
    "spread": 2,
    "output": 3,
    "capacity": 4,
    "utilization": 5,
    "inventory": 6,
    "cost": 7,
    "profit": 8,
    "demand": 9,
    "trade": 10,
    "balance": 11,
    "default": 99,
}

POLICY_LABELS = {
    "spot_price": "现货价格：产业阶段 → 平行分支 → 产品 → 规格",
    "futures_price": "期货价格：期货品种 → 合约角色/结构 → 合约期限",
    "spread": "价差/基差/月差：标的对象 → 价格关系类型 → 合约/市场结构",
    "output": "产量/产能：产业阶段 → 生产节点 → 产品",
    "capacity": "产能：产业阶段 → 生产节点 → 产品",
    "utilization": "开工率：产业阶段 → 生产/加工环节 → 产品",
    "inventory": "库存：产业阶段 → 产品节点 → 库存位置/性质",
    "cost": "成本：加工环节 → 成本对象 → 产品",
    "profit": "利润：利润产生环节 → 加工环节 → 产品",
    "demand": "需求：需求链阶段 → 消费节点 → 产品",
    "trade": "进出口：产品节点 → 进口 → 出口 → 净出口",
    "balance": "平衡：产业阶段 → 平衡对象 → 产品节点",
    "default": "默认：保持现有排序",
}

NODE_DISPLAY_NAMES = {
    "lithium_resource": "锂矿资源",
    "lithium_mining": "锂矿采选",
    "lithium_mineral": "锂矿资源矿物",
    "concentrate_trade": "锂精矿贸易",
    "ore_balance": "锂矿供需平衡",
    "production_cost": "锂盐生产成本",
    "product_price": "锂盐产品价格",
    "inventory_trade": "锂盐库存贸易",
    "balance": "锂盐供需平衡",
    "production": "产品生产环节",
    "price": "产品价格环节",
    "trade_inventory": "产品库存贸易",
    "base_lithium_salts": "锂盐基础产品",
    "battery_auxiliaries": "电池辅材锂盐",
    "precursor": "三元前驱体",
    "cathode_material": "三元正极材料",
    "lfp_raw": "磷化工原料",
    "iron_phosphate": "磷酸铁",
    "lfp_cathode": "磷酸铁锂成品",
    "lfp_trade": "磷酸铁锂贸易库存",
    "graphite_raw": "天然石墨原料",
    "graphitization": "石墨化加工",
    "anode_product": "人造石墨成品",
    "anode_supply_demand": "负极供给需求",
    "base_film": "隔膜基膜",
    "coated_film": "隔膜涂覆加工",
    "raw_additive": "电解液原料添加剂",
    "electrolyte_product": "电解液成品",
    "copper_aluminum_foil": "铜铝箔辅材",
    "pvdf": "PVDF辅材",
    "cell_cost": "电芯成本",
    "cell_price": "电芯产品价格",
    "supply_output": "电芯产能产量",
    "storage_battery_system": "储能电池系统",
    "demand_install": "储能需求装机",
    "policy_bidding": "储能政策招标",
    "vehicle_production": "整车产量",
    "sales_ownership": "汽车销量保有量",
    "ev_penetration": "电动化指标",
    "phosphate_rock": "磷矿资源",
    "phosphoric_acid_products": "磷化工中间品",
    "trade_demand": "磷化工贸易需求",
    "supply_trade": "产品供给贸易",
}

STAGE_DISPLAY_NAMES = {
    "upstream": "上游",
    "midstream": "中游",
    "downstream": "下游",
    "trade": "贸易",
    "raw": "原料",
    "process": "加工",
    "product": "产品",
    "supply_demand": "供需",
    "demand": "需求",
    "inventory": "库存",
    "cost": "成本",
    "profit": "利润",
}

PRODUCT_NAME_TOKENS = [
    "电芯",
    "Pack",
    "电解液",
    "固态电解质",
    "金属锂",
    "LPSC",
    "LATP",
    "LLZO",
    "NMP",
    "CMC",
    "SBR",
    "五硫化二磷",
    "六氟磷酸锂",
    "LiFSI",
    "FEC",
    "VC",
    "DMC",
    "EC",
    "PC",
    "DEC",
    "EMC",
    "磷酸铁锂",
    "磷酸铁",
    "磷酸一铵",
    "磷酸",
    "磷矿石",
    "热法磷酸",
    "锂精矿",
    "锂辉石",
    "锂云母",
    "磷锂铝石",
    "碳酸锂",
    "氢氧化锂",
    "天然石墨",
    "人造石墨",
    "球形石墨",
    "鳞片石墨",
    "石墨化",
    "三元前驱体",
    "三元材料",
    "氯化锂",
    "氟化锂",
    "铁粉",
]


def select_policy(major: str, sub: str) -> str:
    if major == "价格":
        if sub in ("现货价格", "价格"):
            return "spot_price"
        if sub in ("期货价格",):
            return "futures_price"
        if sub in ("基差", "现货价差", "价差", "月差"):
            return "spread"
    if major in ("供给", "供应"):
        if sub == "产量":
            return "output"
        if sub == "产能":
            return "capacity"
        if sub == "开工率":
            return "utilization"
    if major == "库存":
        return "inventory"
    if major == "成本利润":
        if sub == "成本":
            return "cost"
        if sub in ("利润", "利润"):
            return "profit"
    if major == "需求":
        return "demand"
    if major == "进出口":
        return "trade"
    if major == "平衡":
        return "balance"
    return "default"


def _load_node_rules() -> dict:
    try:
        payload = json.loads(NODE_RULES_PATH.read_text(encoding="utf-8"))
        sectors = payload.get("sectors", {})
        for spec in sectors.values():
            for node in spec.get("nodes", []):
                node.setdefault("node_id", node.get("node_name"))
                node.setdefault("stage", "")
                node.setdefault("branch", "")
                node.setdefault("branch_priority", 0)
                node.setdefault("node_priority", node.get("node_rank", 0))
                node.setdefault("relation_type", "priority")
                node.setdefault("upstream_of", None)
                node.setdefault("downstream_of", None)
        return sectors
    except (OSError, ValueError):
        return {}


NODE_RULES = _load_node_rules()


def normalize_indicator_title(title: str) -> str:
    """与前端 chartGrouping.ts 的 normalizeIndicatorTitle 保持一致。"""
    value = str(title or "")
    for word in INDICATOR_VARIABLE_WORDS:
        value = value.replace(word, "")
    if "人造石墨" in value or "石墨" in value:
        for word in ("储能", "动力", "消费"):
            value = value.replace(word, "")
    if "电芯出货" in value:
        for word in ("三元", "磷酸铁锂", "总计", "合计"):
            value = value.replace(word, "")
    if "分电池类型" in value or "库存分电池类型" in value:
        for word in (
            "储能电池",
            "动力电池",
            "消费电池",
            "三元电池",
            "磷酸铁锂电池",
            "分电池类型",
            "电池类型",
        ):
            value = value.replace(word, "")
    for word in INDICATOR_SPEC_WORDS:
        value = value.replace(word, "")
    for prefix in EXCHANGE_PREFIXES:
        value = value.replace(prefix, "")
    for prefix in SOURCE_PREFIXES:
        value = value.replace(prefix, "")
    for cn, num in CHINESE_MONTH_NUMBERS.items():
        value = value.replace(cn, num)
    value = re.sub(r"(月度|周度|季度|年度|日度)", "", value)
    value = re.sub(r"Fe/P\s*[:：]?\s*[0-9.%~\-\s]+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\d+(\.\d+)?\s*%\s*[-~]\s*\d+(\.\d+)?\s*%", "", value)
    value = re.sub(r"\d+(\.\d+)?\s*[-~]\s*\d+(\.\d+)?", "", value)
    value = re.sub(r"[（(][^）)]*[）)]", "", value)
    value = re.sub(r"[\s：:，,。.（）()\-_/元吨手%]+", "", value)
    return value


def parse_tags(raw) -> dict:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if isinstance(obj, dict):
        # Keep nested list/dict values (候选大类/候选分类组合/composite) intact;
        # only scalar values are coerced to str. Flattening them into str caused
        # double JSON serialization when tags were written back to the workbook.
        return {
            str(k): (v if isinstance(v, (list, dict)) else str(v))
            for k, v in obj.items()
            if v not in (None, "")
        }
    return {}


def _major_key(major: str) -> int:
    return MAJOR_ORDER.index(major) if major in MAJOR_ORDER else len(MAJOR_ORDER)


# 板块一级排序（与前端 industryGroups.SECTOR_ORDER 一致）：
# 锂矿 -> 锂盐(碳酸锂/氢氧化锂/其他锂盐) -> 磷酸铁锂/磷化工链 -> 三元正极 -> …
SECTOR_RANK = {
    "锂矿": 0,
    "锂盐": 1, "碳酸锂": 1, "氢氧化锂": 1, "其他锂盐": 1,
    "磷酸铁锂": 2, "磷化工链": 2,
    "三元正极": 3,
    "钴酸锂": 4,
    "锰酸锂": 5,
    "负极材料": 6,
    "隔膜": 7,
    "电解液产业链": 8,
    "辅材": 9,
    "电池电芯": 10,
    "储能": 11,
    "新能源汽车": 12,
}
# 同 rank 板块必须有次级键，否则同 rank 的段会按大类交错排列
# （如磷酸铁锂/磷化工链同为 rank 2，缺次级键时两板块的段按大类交替出现）：
# - 锂盐拆分板块：碳酸锂 < 氢氧化锂 < 其他锂盐
# - 磷酸铁锂 < 磷化工链
SECTOR_SUB_RANK = {
    "碳酸锂": 0, "氢氧化锂": 1, "其他锂盐": 2,
    "磷酸铁锂": 0, "磷化工链": 1,
}


def _sector_key(sector: str) -> tuple:
    rank = SECTOR_RANK.get(sector, 99)
    sub = SECTOR_SUB_RANK.get(sector, 99)
    return (rank, sub)


def _sub_key(major: str, sub: str) -> int:
    order = SUB_ORDER.get(major, [])
    if major == "价格" and sub in COMPOSITE_SUBS:
        return len(order) + 1
    return order.index(sub) if sub in order else len(order)


def _freq_key(freq: str) -> int:
    return FREQ_ORDER.index(freq) if freq in FREQ_ORDER else len(FREQ_ORDER)


def _composite_order(major: str, sub: str) -> int:
    if major == "价格" and sub in COMPOSITE_SUB_ORDER:
        return COMPOSITE_SUB_ORDER.index(sub)
    return -1


def _composite_meta(tags: dict) -> dict | None:
    if not isinstance(tags, dict):
        return None
    composite = tags.get("composite")
    if isinstance(composite, dict):
        return composite
    if isinstance(composite, str):
        try:
            payload = json.loads(composite)
        except (TypeError, ValueError):
            try:
                payload = ast.literal_eval(composite)
            except (SyntaxError, ValueError):
                return None
        if isinstance(payload, dict):
            return {str(k): v for k, v in payload.items()}
        return None
    return None


def _composite_sort_key(rec: dict) -> tuple:
    meta = _composite_meta(rec.get("tags") or {})
    if not meta:
        return (False, 9999, "", 9999)
    ctype = str(meta.get("composite_type") or "")
    ckey = str(meta.get("composite_key") or "")
    role = str(meta.get("composite_role") or "")
    status = str(meta.get("composite_status") or "")
    role_order = COMPOSITE_ROLE_ORDER.get(ctype, [])
    role_rank = role_order.index(role) if role in role_order else len(role_order)
    if status != "MATCHED" or not ctype or not ckey or not role_order:
        return (False, 9999, "", 9999)
    return (True, COMPOSITE_TYPE_ORDER.get(ctype, 9999), ckey, role_rank)


def _composite_group_key(rec: dict) -> tuple:
    meta = _composite_meta(rec.get("tags") or {})
    if not meta:
        return (False, 9999, "")
    ctype = str(meta.get("composite_type") or "")
    ckey = str(meta.get("composite_key") or "")
    status = str(meta.get("composite_status") or "")
    if status != "MATCHED" or not ctype or not ckey:
        return (False, 9999, "")
    return (True, COMPOSITE_TYPE_ORDER.get(ctype, 9999), ckey)


def _composite_sub_rank(major: str, sub: str, rec: dict) -> tuple:
    group = _composite_group_key(rec)
    sub_rank = _sub_key(major, sub)
    return (group, sub_rank)


def _composite_role_rank(rec: dict) -> int:
    meta = _composite_meta(rec.get("tags") or {})
    if not meta:
        return 9999
    ctype = str(meta.get("composite_type") or "")
    ckey = str(meta.get("composite_key") or "")
    status = str(meta.get("composite_status") or "")
    # 未配对（INCOMPLETE）的复合组行不进复合组，role 与普通行一致（9999），
    # 避免未配对进出口/成交持仓行以 role=0 插队到板块最前
    if status != "MATCHED" or not ctype or not ckey:
        return 9999
    role_order = COMPOSITE_ROLE_ORDER.get(ctype, [])
    role = str(meta.get("composite_role") or "")
    return role_order.index(role) if role in role_order else len(role_order)


def _composite_reason(rec: dict) -> str:
    meta = _composite_meta(rec.get("tags") or {})
    if not meta:
        return ""
    ctype = str(meta.get("composite_type") or "")
    status = str(meta.get("composite_status") or "")
    if status != "MATCHED":
        return ""
    return COMPOSITE_REASON_LABELS.get(ctype, "")


def _current_key(tags: dict[str, str], nature: str, name: str = "") -> int:
    state = tags.get("状态", "") or ""
    if "预测" in state or "预测" in nature or "预测" in name:
        return 1
    return 0


def _total_rank(name: str) -> int:
    # 总览 rows（标题以"总"开头，如 总招标功率）come first; then 组内总 rows
    # （含 总计/合计/总，如 动力电芯产量: 总、储能EPC（总）招标功率）; others last.
    text = (name or "").strip()
    if re.match(r"^SMM\s*[:：]\s*总", text) or text.startswith("总"):
        return 0
    if "总" in text or "合计" in text:
        return 1
    return 2


FOREIGN_PRODUCT_KEYWORDS = ["磷锂铝石"]


def _strip_parentheses(text: str) -> str:
    value = re.sub(r"（[^（）]*）", "", text or "")
    value = re.sub(r"\([^()]*\)", "", value)
    return value


def _is_foreign_region(region: str, name: str) -> bool:
    if region in FOREIGN_REGIONS or region in ("全球", "海外"):
        return True
    outside = _strip_parentheses(name)
    if "海关" in outside:
        return "中国" not in outside
    if any(country in outside for country in FOREIGN_REGIONS):
        if "蒙古" in outside and "内蒙古" in outside:
            return any(country in outside for country in FOREIGN_REGIONS if country != "蒙古")
        return True
    return any(keyword in outside for keyword in FOREIGN_PRODUCT_KEYWORDS)


def _is_china_region(region: str, name: str) -> bool:
    if _is_foreign_region(region, name):
        return False
    # Parenthesized 中国现货/CIF中国 must not count as a China region.
    outside = _strip_parentheses(name)
    if any(region_name in outside for region_name in CHINA_REGIONS):
        return True
    if region == "中国" or "中国" in outside:
        return True
    if any(keyword in outside for keyword in CHINA_KEYWORDS):
        return True
    return region in CHINA_REGIONS


def _region_key(tags: dict[str, str], name: str = "") -> int:
    region = tags.get("地域", "") or ""
    if _is_foreign_region(region, name):
        return 2
    if _is_china_region(region, name):
        return 1
    # 无地区（通用指标，如 磷酸-平均价）排在具体地区之前；中国/省份次之，
    # 全球/海外/外国最后。
    return 0


def _region_name_key(tags: dict[str, str], name: str = "") -> tuple:
    region = tags.get("地域", "") or ""
    if _is_foreign_region(region, name):
        return (2, region or "")
    if _is_china_region(region, name):
        return (1, region or "")
    # 无地区（通用指标）最前；同地区内再由当期/预测键决定顺序。
    return (0, "")


def _node_score(rule: dict, major: str, sub: str, name: str) -> int:
    score = 0
    include_hit = False
    for keyword in rule.get("include", []):
        if keyword in name:
            include_hit = True
            score += 2
    if not include_hit:
        return 0
    for keyword in rule.get("exclude", []):
        if keyword in name:
            score -= 5
    majors = rule.get("major")
    if majors:
        if major in majors:
            score += 3
        else:
            score -= 1
    subs = rule.get("sub")
    if subs:
        if sub in subs:
            score += 2
        else:
            score -= 1
    return score


def assign_industry_components(sector: str, major: str, sub: str, name: str) -> dict:
    rules = NODE_RULES.get(sector or "", {}).get("nodes", [])
    best_score = 0
    best_rules: list[dict] = []
    for rule in rules:
        score = _node_score(rule, major, sub, name)
        if score <= 0:
            continue
        if score > best_score:
            best_score = score
            best_rules = [rule]
        elif score == best_score:
            best_rules.append(rule)
    if not best_rules:
        policy = select_policy(major, sub)
        return {
            "matched": False,
            "fallback": True,
            "conflict": False,
            "policy": policy,
        }
    unique_ids = {rule.get("node_id") or rule.get("node_name") for rule in best_rules}
    if len(unique_ids) > 1:
        policy = select_policy(major, sub)
        return {
            "matched": True,
            "fallback": True,
            "conflict": True,
            "policy": policy,
        }
    node = best_rules[0]
    policy = select_policy(major, sub)
    return {
        "matched": True,
        "fallback": False,
        "conflict": False,
        "node_id": node.get("node_id") or node.get("node_name"),
        "node_name": node.get("node_name"),
        "display_name": node.get("display_name"),
        "stage_label": node.get("stage_label"),
        "business_role": node.get("business_role"),
        "stage": node.get("stage") or "",
        "branch": node.get("branch") or "",
        "branch_priority": int(node.get("branch_priority", 0) or 0),
        "node_priority": int(node.get("node_priority", node.get("node_rank", 0)) or 0),
        "relation_type": node.get("relation_type") or "priority",
        "upstream_of": node.get("upstream_of"),
        "downstream_of": node.get("downstream_of"),
        "policy": policy,
    }


def build_sort_reason(components: dict, major: str = "", sub: str = "") -> str:
    policy = components.get("policy", "default")
    policy_label = POLICY_LABELS.get(policy, policy)
    overall = f"总体排序：{major or '未分类'}-{sub or '未分类'}；"
    if components.get("conflict"):
        return overall + f"检测到产业关系冲突，本次未强制调整，保持稳定原顺序；当前 policy：{policy_label}。"
    if not components.get("matched"):
        return overall + f"未识别到明确产业节点，保持原 catalog_order；当前 policy：{policy_label}。"
    relation = components.get("relation_type", "priority")
    stage = components.get("stage") or "同阶段"
    branch = components.get("branch") or ""
    node = components.get("node_name") or components.get("node_id") or ""
    upstream = components.get("downstream_of") or []
    downstream = components.get("upstream_of") or []
    if relation == "strict":
        parts = []
        if upstream:
            parts.append(f"位于上游节点 {upstream} 之后")
        if downstream:
            parts.append(f"位于下游节点 {downstream} 之前")
        if parts:
            return overall + f"产业链{stage}节点{node}，{'、'.join(parts)}，按严格上下游排列；排序策略：{policy_label}。"
        return overall + f"产业链{stage}节点{node}，按严格上下游排列；排序策略：{policy_label}。"
    if relation == "parallel":
        return overall + (
            f"属于{stage}阶段{branch}路线；与平行路线按展示优先级排列，"
            f"不代表上下游关系；排序策略：{policy_label}。"
        )
    if relation == "peer":
        return overall + f"属于{stage}同级并列节点{node}，无明确上下游，保持原 catalog_order；排序策略：{policy_label}。"
    return overall + f"产业链{stage}节点{node}，按节点优先级排列；排序策略：{policy_label}。"


def _node_display(rec: dict) -> str:
    ind = rec.get("industry") or {}
    node_id = ind.get("node_id") or ind.get("node_name") or ""
    return ind.get("display_name") or NODE_DISPLAY_NAMES.get(node_id, "当前产业环节")


def _current_product_name(rec: dict) -> str:
    name = rec.get("name") or ""
    for token in PRODUCT_NAME_TOKENS:
        if token in name:
            return token
    return ""


def _product_family_key(name: str) -> str:
    value = name or ""
    # Match mixed half/full-width parentheses (e.g. "(出厂价）") so that rows
    # differing only in the parenthesized qualifier share the same family.
    value = re.sub(r"[（(][^（）()]*[）)]", "", value)
    # 词表排序先按长度降序、同长按字典序（完整 tie-break），
    # 消除 set/hash 顺序依赖（PYTHONHASHSEED 不同会导致同长词顺序不同）
    region_words = sorted(
        set(CHINA_REGIONS) | set(FOREIGN_REGIONS) | {"全球", "海外", "中国"},
        key=lambda w: (len(w), w),
        reverse=True,
    )
    for word in region_words:
        value = value.replace(word, "")
    value = re.sub(r"\d+(\.\d+)?%", "", value)
    value = re.sub(r"Li2O[:：]?\s*[\d\-.%]+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"Li₂O[:：]?\s*[\d\-.%]+", "", value)
    value = re.sub(r"\d+(\.\d+)?\s*(μm|mm|um|cm)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"g/cm³|g/cm3", "", value)
    value = re.sub(r"\d+(\.\d+)?\s*(Ah|V)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\d+系", "", value)
    value = re.sub(r"18650|21700|26550", "", value)
    for word in (
        "低端",
        "中端",
        "高端",
        "储能",
        "动力",
        "消费",
        "累计",
        "新增",
        "总计",
        "合计",
        "总",
        "现货",
        "平均价",
        "均价",
        "价格",
        "产量",
        "产能",
        "开工率",
        "库存",
        "进口",
        "出口",
        "净出口",
        "收盘价",
        "预测值",
        "预测",
    ):
        value = value.replace(word, "")
    for word in ("日度", "周度", "月度", "季度", "年度"):
        value = value.replace(word, "")
    value = value.replace("SMM", "")
    for prefix in EXCHANGE_PREFIXES:
        value = value.replace(prefix, "")
    value = re.sub(r"[\s：:，,。.（）()\-_/元吨手%]+", "", value)
    return value


def _source_detail(name: str) -> str:
    # 词表排序先按长度降序、同长按字典序（完整 tie-break），消除 set/hash 顺序依赖
    region_words = sorted(
        set(CHINA_REGIONS) | set(FOREIGN_REGIONS) | {"全球", "海外", "中国"},
        key=lambda w: (len(w), w),
        reverse=True,
    )
    for word in region_words:
        if word in (name or ""):
            return word
    return ""


def _variant_key(rec: dict) -> str:
    name = rec.get("name") or ""
    family = _product_family_key(name)
    normalized = normalize_indicator_title(name)
    if family and family in normalized:
        return normalized.replace(family, "")
    return normalized


def _display_group(name: str) -> str:
    if "港口" in name and "库存" in name:
        return "港口库存"
    return ""


def _display_product_family(rec: dict) -> str:
    sector = rec.get("sector") or ""
    if sector:
        return sector
    return _product_family_key(rec.get("name") or "")


def _group_display(group: dict | None) -> str:
    if not group or not group.get("recs"):
        return ""
    first = group["recs"][0]
    product = _current_product_name(first)
    return product or _node_display(first)


def _group_has_spec_sequence(group: dict) -> bool:
    names = [rec.get("name") or "" for rec in group["recs"]]
    return bool(names) and all(
        any(keyword in name for keyword in ("低端", "中端", "高端"))
        for name in names
    )


def _specific_product_reason(first: dict, policy_label: str) -> str:
    name = first.get("name") or ""
    product = _current_product_name(first)
    texts = {
        "鳞片石墨": "天然鳞片石墨属于天然石墨路线的原料端，经球形化加工形成球形石墨，后续进入天然石墨负极材料，因此排在天然石墨路线最前。",
        "球形石墨": "球形石墨属于天然石墨路线的加工产品，上游承接鳞片石墨，下游进入天然石墨负极材料，因此排在鳞片石墨之后、天然石墨负极之前。",
        "天然石墨": "天然石墨属于天然石墨路线成品端，上游承接球形石墨；与人造石墨路线属于平行技术路线，不存在直接上下游关系，因此排在球形石墨之后。",
        "石油焦": "石油焦属于人造石墨路线的上游原料，后续经过加工和石墨化形成人造石墨负极材料，因此排在人造石墨路线最前。",
        "针状焦": "针状焦属于人造石墨路线的上游原料，后续经过加工和石墨化形成人造石墨负极材料，因此排在人造石墨路线最前。",
        "石墨化": "石墨化属于人造石墨路线的加工环节，上游承接石油焦/针状焦等原料，下游形成人造石墨负极材料，因此排在原料之后、成品之前。",
        "人造石墨": "人造石墨属于人造石墨路线成品端，上游承接石墨化加工；与天然石墨路线属于平行技术路线，不存在直接上下游关系，因此排在石墨化之后。",
        "六氟磷酸锂": "六氟磷酸锂属于液态电解液体系中的电解质锂盐，与溶剂、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "LiFSI": "LiFSI属于液态电解液体系中的电解质锂盐，与溶剂、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "DMC": "DMC属于液态电解液溶剂，与电解质锂盐、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "EC": "EC属于液态电解液溶剂，与电解质锂盐、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "PC": "PC属于液态电解液溶剂，与电解质锂盐、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "DEC": "DEC属于液态电解液溶剂，与电解质锂盐、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "EMC": "EMC属于液态电解液溶剂，与电解质锂盐、添加剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "VC": "VC属于液态电解液添加剂，与电解质锂盐、溶剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "FEC": "FEC属于液态电解液添加剂，与电解质锂盐、溶剂属于平行投入分支，不互为上下游，最终共同进入电解液成品。",
        "电解液": "电解液属于液态电解液体系成品，由电解质锂盐、溶剂和添加剂共同组成，因此排在各类原料之后。",
        "LPSC": "LPSC属于固态电解质路线，与液态电解液体系属于平行技术路线，不作为液态电解液添加剂处理。",
        "LATP": "LATP属于固态电解质路线，与液态电解液体系属于平行技术路线，不作为液态电解液添加剂处理。",
        "LLZO": "LLZO属于固态电解质路线，与液态电解液体系属于平行技术路线，不作为液态电解液添加剂处理。",
        "硫酸亚铁": "硫酸亚铁属于磷酸铁锂路线的铁源分支，与磷源原料属于平行投入分支，最终共同进入磷酸铁。",
        "氧化铁红": "氧化铁红属于磷酸铁锂路线的铁源分支，与磷源原料属于平行投入分支，最终共同进入磷酸铁。",
        "氧化铁": "氧化铁属于磷酸铁锂路线的铁源分支，与磷源原料属于平行投入分支，最终共同进入磷酸铁。",
        "铁粉": "铁粉属于磷酸铁锂路线的铁源分支，与磷源原料属于平行投入分支，最终共同进入磷酸铁。",
        "磷矿石": "磷矿石属于磷酸铁锂路线的磷源分支，与铁源原料属于平行投入分支，最终共同进入磷酸铁。",
        "磷酸一铵": "磷酸一铵属于磷酸铁锂路线的磷源分支，与铁源原料属于平行投入分支，最终共同进入磷酸铁。",
        "磷酸": "磷酸属于磷酸铁锂路线的磷源分支，与铁源原料属于平行投入分支，最终共同进入磷酸铁。",
        "热法磷酸": "热法磷酸属于磷酸铁锂路线的磷源分支，与铁源原料属于平行投入分支，最终共同进入磷酸铁。",
        "锂精矿": "锂精矿属于锂矿采选后的加工产品，上游承接锂辉石、锂云母等原矿，下游进入锂盐生产。",
        "锂辉石": "锂辉石属于锂矿资源矿物路线，与其他锂矿矿物属于平行资源路线，经选矿形成锂精矿后进入锂盐生产。",
        "锂云母": "锂云母属于锂矿资源矿物路线，与其他锂矿矿物属于平行资源路线，经选矿形成锂精矿后进入锂盐生产。",
        "磷锂铝石": "磷锂铝石属于锂矿资源矿物路线，与其他锂矿矿物属于平行资源路线，经选矿形成锂精矿后进入锂盐生产。",
        "磷酸铁": "磷酸铁位于磷源/铁源原料与磷酸铁锂之间，上游承接磷源与铁源，下游进入磷酸铁锂生产，因此排在原料之后、磷酸铁锂之前。",
        "磷酸铁锂": "磷酸铁锂承接磷酸铁，属于正极材料成品端，因此排在磷酸铁之后。",
        "三元前驱体": "三元前驱体属于三元材料的上游前驱体，下游进入三元正极材料，因此排在前驱体之后、正极材料之前。",
        "三元材料": "三元材料承接三元前驱体，属于三元正极材料成品端，因此排在前驱体之后。",
        "电芯": "电芯属于电池材料与Pack之间的中间产品，上游承接电池材料，下游进入Pack/电池组，因此排在电池材料之后、Pack之前。",
        "Pack": "Pack/电池组属于电芯之后的下游集成环节，承接电芯，进入储能系统或整车应用。",
    }
    for token, text in texts.items():
        if token == product:
            return f"{text}排序依据：{policy_label}。"
    return ""


def _business_group_reason(group: dict, prev_group: dict | None, next_group: dict | None) -> str:
    first = group["recs"][0]
    composite_reason = _composite_reason(first)
    if composite_reason:
        return composite_reason
    ind = first.get("industry") or {}
    policy_label = POLICY_LABELS.get(ind.get("policy", "default"), "默认")
    if ind.get("conflict"):
        return "检测到产业关系存在冲突，本组保持既定展示顺序，未强制调整。"
    if not ind.get("matched"):
        return "当前未识别到明确上下游关系，本组保持既定展示顺序。"
    node_display = _current_product_name(first) or _node_display(first)
    stage_display = STAGE_DISPLAY_NAMES.get(ind.get("stage") or "", node_display or "产业链")
    relation = ind.get("relation_type") or "priority"
    if _group_has_spec_sequence(group):
        return f"均属于{node_display}，不涉及产业上下游变化，本组仅按规格顺序排列。排序依据：{policy_label}。"
    prev_display = _group_display(prev_group)
    next_display = _group_display(next_group)
    if relation == "strict" and (
        (prev_display and next_display and prev_display == next_display)
        or prev_display == node_display
        or next_display == node_display
    ):
        return (
            "该指标与相邻指标属于同一产业环节，不存在需要表达的直接上下游关系，"
            "本组按产品、规格或其他既定内部规则排列。"
        )
    specific = _specific_product_reason(first, policy_label)
    if specific:
        return specific
    if ind.get("policy") == "profit" and node_display.endswith("成本"):
        node_display = f"{node_display[:-2]}利润"
    if relation == "parallel_input":
        return (
            f"{node_display}属于{stage_display}的平行投入分支，"
            f"与同阶段其他原料/添加剂不互为上下游，最终共同进入下游成品。"
            f"排序依据：{policy_label}。"
        )
    if relation == "process":
        if prev_display and next_display:
            return (
                f"{node_display}属于{stage_display}加工转化环节，"
                f"上游承接{prev_display}，下游进入{next_display}，"
                f"因此排在{prev_display}之后、{next_display}之前。排序依据：{policy_label}。"
            )
        if prev_display:
            return f"{node_display}属于{stage_display}加工转化环节，承接{prev_display}，因此排在{prev_display}之后。排序依据：{policy_label}。"
        if next_display:
            return f"{node_display}属于{stage_display}加工转化环节，是{next_display}的前置加工，因此排在最前。排序依据：{policy_label}。"
        return f"{node_display}属于{stage_display}加工转化环节，按既定加工顺序排列。排序依据：{policy_label}。"
    if relation == "strict":
        if prev_display and next_display:
            return (
                f"{node_display}位于{prev_display}与{next_display}之间，"
                f"上游承接{prev_display}，下游进入{next_display}，"
                f"因此排在{prev_display}之后、{next_display}之前。排序依据：{policy_label}。"
            )
        if next_display:
            return (
                f"{node_display}位于产业链上游，是{next_display}的原料或前置环节，"
                f"因此排在最前。排序依据：{policy_label}。"
            )
        if prev_display:
            return (
                f"{node_display}位于产业链下游，承接{prev_display}，"
                f"因此排在{prev_display}之后。排序依据：{policy_label}。"
            )
        return f"{node_display}位于{stage_display}环节，按严格上下游顺序排列。排序依据：{policy_label}。"
    if relation == "parallel":
        other_group = prev_group or next_group
        other_display = _group_display(other_group) if other_group else ""
        if other_display:
            return (
                f"{node_display}与{other_display}属于{stage_display}阶段的平行技术路线，"
                f"不存在直接上下游关系；本组按展示顺序排列。排序依据：{policy_label}。"
            )
        return (
            f"{node_display}属于{stage_display}阶段的平行技术路线，"
            f"与同阶段其他路线不存在直接上下游关系；本组按展示顺序排列。排序依据：{policy_label}。"
        )
    if relation == "peer":
        if prev_display:
            return (
                f"{node_display}与{prev_display}同属于{stage_display}同级产品/环节，"
                f"无本组需要表达的严格上下游关系，按既定展示顺序排列。排序依据：{policy_label}。"
            )
        return (
            f"{node_display}属于{stage_display}同级产品/环节，"
            f"无明确上下游关系，按既定展示顺序排列。排序依据：{policy_label}。"
        )
    if STAGE_DISPLAY_NAMES.get(ind.get("stage") or ""):
        return f"{node_display}属于{stage_display}环节，按既定产业环节顺序排列。排序依据：{policy_label}。"
    return f"{node_display}按既定产业环节顺序排列。排序依据：{policy_label}。"


def generate_business_sort_reasons(output_records: list[dict]) -> dict:
    current_sheet = ""
    groups: list[dict] = []
    current_group: dict | None = None
    for rec in output_records:
        if rec.get("kind") == "sheet_header":
            current_sheet = rec.get("sheet") or ""
            continue
        if rec.get("kind") == "composite_section":
            current_sheet = "COMPOSITE"
            continue
        if rec.get("kind") != "data":
            continue
        node_id = (rec.get("industry") or {}).get("node_id") or ""
        product = _current_product_name(rec)
        composite_key = _composite_sort_key(rec)
        if composite_key[0]:
            current_sheet = "COMPOSITE"
        key = (current_sheet, rec.get("selected") == "是", overall_bucket_key(rec), node_id, product, composite_key)
        if current_group is not None and current_group["key"] == key:
            current_group["recs"].append(rec)
        else:
            if current_group is not None:
                groups.append(current_group)
            current_group = {"key": key, "recs": [rec]}
    if current_group is not None:
        groups.append(current_group)
    stats = {"total": 0, "fallback": 0, "conflict": 0, "self_loop": 0, "name_mismatch": 0, "empty": 0}
    wrong_labels = ["锂盐基础产品", "电池辅材锂盐", "电解液原料添加剂"]
    special_tokens = ["金属锂", "CMC", "SBR", "NMP", "LPSC", "LATP", "LLZO", "固态电解质"]
    for index, group in enumerate(groups):
        prev_group = None
        for candidate in reversed(groups[:index]):
            if candidate["key"][0] == group["key"][0]:
                prev_group = candidate
                break
        next_group = None
        for candidate in groups[index + 1:]:
            if candidate["key"][0] == group["key"][0]:
                next_group = candidate
                break
        reason = _business_group_reason(group, prev_group, next_group)
        for rec in group["recs"]:
            rec["sort_reason"] = reason
            stats["total"] += 1
            if not reason:
                stats["empty"] += 1
            if "当前未识别到明确上下游关系" in reason:
                stats["fallback"] += 1
            if "产业关系存在冲突" in reason:
                stats["conflict"] += 1
            if "位于" in reason and "之间" in reason:
                match = re.search(r"(.+?)位于(.+?)与(.+?)之间", reason)
                if match and match.group(2) == match.group(3):
                    stats["self_loop"] += 1
            name = rec.get("name") or ""
            if any(token in name for token in special_tokens) and any(label in reason for label in wrong_labels):
                stats["name_mismatch"] += 1
    return stats


def _contract_role_rank(name: str) -> int:
    if "主力" in name:
        return 0
    if "当月" in name:
        return 1
    for cn, num in CHINESE_MONTH_NUMBERS.items():
        if cn in name:
            return 1 + int(num)
    match = re.search(r"(\d{1,2})合约", name)
    if match:
        return 1 + int(match.group(1))
    return 99


def _contract_term_key(name: str) -> str:
    return normalize_indicator_title(name)


def _futures_variety_key(name: str) -> str:
    value = name or ""
    for cn in CHINESE_MONTH_NUMBERS:
        value = value.replace(f"{cn}合约", "")
    value = re.sub(r"\d{1,2}合约", "", value)
    for word in ("主力合约", "当月合约", "收盘价", "日度", "周度", "月度", "季度", "年度"):
        value = value.replace(word, "")
    for prefix in EXCHANGE_PREFIXES:
        value = value.replace(prefix, "")
    value = re.sub(r"[\s：:，,。.（）()\-_/元吨手%]+", "", value)
    return value


def _relation_rank(name: str) -> int:
    if "基差" in name or "期现" in name:
        return 0
    if "现货价差" in name or "升贴水" in name:
        return 1
    if "价差" in name or "溢价" in name:
        return 2
    if "月差" in name:
        return 3
    return 9


def _inventory_location_key(name: str) -> int:
    for index, keyword in enumerate(["港口", "社会", "样本", "显性", "仓单", "矿山", "四地"]):
        if keyword in name:
            return index
    return 99


def _cost_object_key(name: str) -> int:
    if "现金成本" in name:
        return 0
    if "理论成本" in name:
        return 1
    if "成本占比" in name:
        return 2
    if "加工" in name and "成本" in name:
        return 3
    return 9


def policy_sort_key(rec: dict) -> tuple:
    name = rec.get("name") or ""
    major = rec.get("major") or ""
    sub = rec.get("sub") or ""
    ind = rec.get("industry") or {}
    policy = ind.get("policy") or select_policy(major, sub)
    pid = POLICY_ORDER.get(policy, POLICY_ORDER["default"])
    matched = bool(ind.get("matched") and not ind.get("conflict") and not ind.get("fallback"))
    stage = int(ind.get("node_priority", 9999) or 9999) if matched else 9999
    branch = int(ind.get("branch_priority", 0) or 0) if matched else 9999
    product = normalize_indicator_title(name)
    spec = normalize_indicator_title(name)
    # 总览（总招标功率）排在同 policy 的最前；组内总（…: 总、…（总）…）次之。
    # 只放在 block 键里（不放进 data_sort_key），避免影响段间顺序与 invariant。
    total = _total_rank(name)
    if policy == "spot_price":
        return (pid, total, stage, branch, product, spec)
    if policy == "futures_price":
        return (pid, total, _futures_variety_key(name), _contract_role_rank(name), _contract_term_key(name))
    if policy == "spread":
        # Relation first (基差/期现 -> 升贴水 -> 价差/溢价 -> 月差) so that
        # spread indicators of the same product stay adjacent and can form a
        # single row on the dashboard (contiguous catalog_order).
        return (pid, total, _relation_rank(name), _contract_term_key(name))
    if policy in ("output", "capacity"):
        return (pid, total, stage, stage, product, spec)
    if policy == "utilization":
        return (pid, total, stage, product, spec)
    if policy == "inventory":
        return (pid, total, stage, product, _inventory_location_key(name), spec)
    if policy == "cost":
        return (pid, total, stage, _cost_object_key(name), product, spec)
    if policy == "profit":
        return (pid, total, stage, product, spec)
    if policy == "demand":
        return (pid, total, stage, product, spec)
    if policy == "trade":
        sub_rank = {"进口": 0, "出口": 1, "净出口": 2, "进出口": 3}.get(sub, 9)
        return (pid, total, product, sub_rank)
    if policy == "balance":
        return (pid, total, stage, product, spec)
    return (pid, total, stage, branch, product, spec)


def overall_bucket_key(rec: dict) -> tuple:
    major = rec.get("major") or ""
    sub = rec.get("sub") or ""
    tags = rec.get("tags") or {}
    name = rec.get("name") or ""
    return (
        _major_key(major),
        _sub_key(major, sub),
        _freq_key(rec.get("freq") or ""),
        _region_key(tags, name),
    )


def data_sort_key(rec: dict) -> tuple:
    name = rec.get("name") or ""
    major = rec.get("major") or ""
    sub = rec.get("sub") or ""
    tags = rec.get("tags") or {}
    block_industry_key = rec.get("_block_industry_key") or policy_sort_key(rec)
    composite_key = _composite_sort_key(rec)
    # 排序层级（与排序规则.md 一致）：板块 -> 大类 -> 复合组 -> 复合 role ->
    # 大类内子类 -> 频率 -> 业务块 -> 产品族 -> 地区 -> 当期/预测 -> 来源 -> 规格 -> 名称。
    # 大类（MAJOR_ORDER）是板块内的硬顺序：价格 -> 成本利润 -> 库存 -> 供给 -> 需求 ->
    # 进出口 -> 平衡，各大类内部的子类顺序由 _sub_key(major, sub) 提供；
    # 大类层必须存在，否则跨大类直接比较各 SUB_ORDER 的独立索引没有业务依据
    # （如"库存"子类索引 0 会排在"现货价格"索引 1 之前）。
    return (
        _sector_key(rec.get("sector") or ""),
        _major_key(major),
        _composite_group_key(rec),
        _composite_role_rank(rec),
        _sub_key(major, sub),
        _freq_key(rec.get("freq") or ""),
        block_industry_key,
        _product_family_key(name),
        _region_name_key(tags, name),
        _current_key(tags, rec.get("nature") or "", name),
        _source_detail(name),
        _variant_key(rec),
        _composite_order(major, sub),
        name,
        rec["row_idx"],
    )


def _is_pseudo(c0: str, name: str) -> bool:
    if not c0.isdigit():
        return True
    return name.startswith("'") and ("!A1" in name or "Sheet 数" in name)


def classify_rows(ws):
    max_col = ws.max_column
    header_idx = None
    for row_idx in range(1, min(ws.max_row, 20) + 1):
        if str(ws.cell(row_idx, 1).value or "").strip() == "#":
            header_idx = row_idx
            break
    if header_idx is None:
        raise ValueError("目录表未找到以 # 开头的表头行")

    header_values = [ws.cell(header_idx, col).value for col in range(1, max_col + 1)]
    colmap: dict[str, int] = {}
    for col_idx, value in enumerate(header_values):
        key = str(value or "").strip()
        if key and key not in colmap:
            colmap[key] = col_idx

    def col(name: str, default: int | None = None) -> int | None:
        return colmap.get(name, default)

    name_idx = col("Indicator Name", 4)
    col_idx = col("Col", 3)
    freq_idx = col("Freq", 2)
    major_idx = col("大类", 7)
    sub_idx = col("子类", 8)
    sector_idx = col("板块", 6)
    nature_idx = col("数据性质", 9)
    selected_idx = col("是否选中", 11 if "置信度" in colmap else 10)
    tags_idx = col("指标标签", 13 if "置信度" in colmap else 12)

    def at(values: list, idx: int | None) -> str:
        if idx is None or idx >= len(values):
            return ""
        return str(values[idx] or "").strip()

    records = []
    current_sheet = ""
    for row_idx in range(1, ws.max_row + 1):
        cells = [ws.cell(row_idx, col) for col in range(1, max_col + 1)]
        values = [cell.value for cell in cells]
        if all(v is None or str(v).strip() == "" for v in values):
            continue
        c0 = str(values[0] or "").strip()
        cname = at(values, name_idx)

        if row_idx == header_idx:
            records.append(
                {
                    "kind": "header",
                    "row_idx": row_idx,
                    "values": values,
                    "cells": cells,
                    "name_idx": name_idx,
                }
            )
            continue

        if cname == "":
            if c0.isdigit():
                records.append(
                    {
                        "kind": "pseudo",
                        "row_idx": row_idx,
                        "values": values,
                        "cells": cells,
                    }
                )
            elif c0 == "" or "sht" in c0 or c0.startswith("["):
                records.append(
                    {
                        "kind": "summary",
                        "row_idx": row_idx,
                        "values": values,
                        "cells": cells,
                    }
                )
            else:
                records.append(
                    {
                        "kind": "sheet_header",
                        "row_idx": row_idx,
                        "values": values,
                        "cells": cells,
                        "sheet": c0,
                    }
                )
                current_sheet = c0
            continue

        major = at(values, major_idx)
        sub = at(values, sub_idx)
        sector = at(values, sector_idx)
        industry = assign_industry_components(sector, major, sub, cname)
        tags = parse_tags(at(values, tags_idx))
        tags["product_family"] = _display_product_family(
            {"sector": sector, "name": cname}
        )
        display_group = _display_group(cname)
        if display_group:
            tags["display_group"] = display_group
        records.append(
            {
                "kind": "data" if c0.isdigit() and not _is_pseudo(c0, cname) else "pseudo",
                "row_idx": row_idx,
                "values": values,
                "cells": cells,
                "sheet": current_sheet,
                "name": cname,
                "col": at(values, col_idx),
                "name_idx": name_idx,
                "freq": at(values, freq_idx),
                "major": major,
                "sub": sub,
                "sector": sector,
                "industry": industry,
                "sort_reason": build_sort_reason(industry, major, sub),
                "nature": at(values, nature_idx),
                "selected": at(values, selected_idx),
                "tags": tags,
                "tags_idx": tags_idx,
            }
        )
    block_groups: dict[tuple, list[dict]] = {}
    for rec in records:
        if rec.get("kind") != "data":
            continue
        key = (
            rec.get("sheet") or "",
            rec.get("selected") == "是",
            rec.get("major") or "",
            rec.get("sub") or "",
            rec.get("freq") or "",
            _product_family_key(rec.get("name") or ""),
        )
        block_groups.setdefault(key, []).append(rec)
    for group in block_groups.values():
        block_industry_key = min(policy_sort_key(rec) for rec in group)
        for rec in group:
            rec["_block_industry_key"] = block_industry_key
    return records


def section_sort_key(header_rec, data_rows: list[dict]) -> tuple:
    """段（来源 sheet）名行排序键：段内选中指标（无选中则全部）的最小 data_sort_key。
    全局板块排序下段名行按该键参与排序，保证段名行出现在其首个板块部分数据之前。"""
    sheet = header_rec["sheet"]
    rows = [r for r in data_rows if r["sheet"] == sheet]
    selected = [r for r in rows if r["selected"] == "是"]
    pool = selected or rows
    if not pool:
        # 无数据段名行（bottom 保留的孤立段头）：排最后，不参与段顺序校验
        return (9999,)
    return min(data_sort_key(r) for r in pool)


def build_output(records) -> list[dict]:
    header = next(r for r in records if r["kind"] == "header")
    data = [r for r in records if r["kind"] == "data"]
    # Composite rows (trade/balance/market_activity groups) stay contiguous:
    # data_sort_key already keeps a composite group together via
    # _composite_group_key/_composite_role_rank.
    used_sheets = {r["sheet"] for r in data}
    sheet_headers = [r for r in records if r["kind"] == "sheet_header"]
    bottom = [
        r
        for r in records
        if r["kind"] in ("summary", "pseudo")
        or (
            r["kind"] == "sheet_header"
            and r["sheet"] not in used_sheets
        )
    ]
    bottom.sort(key=lambda r: r["row_idx"])

    # 板块一级全局排序（排序规则：板块 -> 大类 -> … -> 名称）：
    # 数据行直接按 data_sort_key 全局排序，来源 sheet 段不再作为第一层分组——
    # 跨板块的混合段（如"中国海关"段同时含锂矿与氯化锂/其他锂盐）会被板块键
    # 拆开，氯化锂等指标自动归入所属板块区，不再被夹在锂矿段之间。
    # 选中（selected=是）指标优先于未选中（原实现"段内 selected 优先"的全局化，
    # 两类内部仍按 data_sort_key 排序，相对顺序不变）。
    # 段名行按其段内数据的最小键参与排序（kind 排序保证段名行排在数据之前），
    # 只出现在其首个板块部分前；无数据的段名行（bottom）保持末尾。
    def out_key(rec) -> tuple:
        if rec["kind"] == "data":
            sel = 0 if rec.get("selected") == "是" else 1
            dk = data_sort_key(rec)
            # selected 维度放在板块键之后：同板块内 选中在前、未选中在后，
            # 板块整体只出现一轮（全局 selected 分层会让板块顺序重复两轮）
            return ((dk[0], sel) + dk[1:], 1)
        sk = section_sort_key(rec, data)
        # 段名行按段内最小键参与排序；sel=0 使其位于该段选中数据之前
        return ((sk[0], 0) + sk[1:], 0)

    seen_headers: set[str] = set()
    headers_used = []
    for h in sheet_headers:
        if h["sheet"] in used_sheets and h["sheet"] not in seen_headers:
            seen_headers.add(h["sheet"])
            headers_used.append(h)

    out = [header]
    out.extend(sorted(data + headers_used, key=out_key))
    out.extend(bottom)
    return out


def _copy_cell(src, dst) -> None:
    dst.value = src.value
    # 直接共享 src 的 Style 对象（含样式索引）：openpyxl 保存时按 style_id
    # 写入，无需逐属性 deepcopy/注册（重建 8.7 万单元格时省 ~40s）。
    # _style 是 openpyxl 内部属性但版本固定，赋值不改源对象，无副作用。
    dst._style = src._style


def _ensure_hyperlink(rec: dict, src, dst, col_idx: int) -> None:
    if src.hyperlink is not None:
        dst.hyperlink = src.hyperlink
        return
    if rec.get("kind") == "sheet_header" and col_idx == 1 and rec.get("sheet"):
        dst.hyperlink = Hyperlink(
            ref=dst.coordinate,
            location=f"'{rec['sheet']}'!A1",
            display=dst.value,
        )
        return
    if rec.get("kind") != "data":
        return
    name_idx = rec.get("name_idx")
    if name_idx is None or col_idx != name_idx + 1:
        return
    sheet = rec.get("sheet") or ""
    col_num = rec.get("col") or ""
    try:
        col_letter = get_column_letter(int(float(str(col_num))))
    except (TypeError, ValueError):
        return
    if not sheet:
        return
    dst.hyperlink = Hyperlink(
        ref=dst.coordinate,
        location=f"'{sheet}'!{col_letter}1",
        display=dst.value,
    )


def validate_sort_invariants(output_records: list[dict]) -> None:
    # 全局板块排序（板块一级）下，连续性/单调性以"板块"为桶检查：
    # 原实现按来源 sheet 段组织输出，桶含 sheet；板块一级排序后同 sheet 跨板块
    # 指标会被拆散归位，连续性应在板块内检查（段名行仅是来源标识）。
    all_data = [r for r in output_records if r.get("kind") == "data"]
    last_by_group: dict[tuple, tuple[int, int, dict]] = {}
    contig_last: dict[tuple, str] = {}
    contig_seen: dict[tuple, set[str]] = {}
    composite_last: dict[tuple, str] = {}
    composite_seen: dict[tuple, set[str]] = {}
    violations: list[str] = []
    for rec in output_records:
        if rec.get("kind") in ("sheet_header", "composite_section"):
            continue
        if rec.get("kind") != "data":
            continue
        sector_key = _sector_key(rec.get("sector") or "")
        selected_group = (sector_key, rec.get("selected") == "是")
        major = rec.get("major") or ""
        sub = rec.get("sub") or ""
        freq = rec.get("freq") or ""
        nature = rec.get("nature") or ""
        # 同变体（归一化标题）才检查连续：product_family_key 会把 储能/动力/消费
        # 电芯 归一为"电芯"，粒度过粗（原校验靠 sheet 维度隐式分隔，板块一级
        # 排序后同板块跨 sheet 指标合并检查，需用更细的 variant 维度）
        variant = normalize_indicator_title(rec.get("name") or "")
        current_state = _current_key(rec.get("tags") or {}, nature, rec.get("name") or "")
        bucket = (sector_key, selected_group, major, sub, freq, current_state, variant)
        is_composite = _composite_sort_key(rec)[0]
        if (
            not is_composite
            and bucket in contig_last
            and contig_last[bucket] != variant
            and variant in contig_seen.get(bucket, set())
        ):
            violations.append(
                f"NAME_GROUP_CONTIGUITY_VIOLATION sector={rec.get('sector')} "
                f"indicator={rec.get('name')} variant={variant} major={major} sub={sub} "
                f"freq={freq} row={rec.get('row_idx')}"
            )
        if not is_composite:
            contig_seen.setdefault(bucket, set()).add(variant)
            contig_last[bucket] = variant
        major_key = _major_key(major)
        group_key = _composite_group_key(rec)
        role_rank = _composite_role_rank(rec)
        sub_key = _sub_key(major, sub)
        composite_key = _composite_sort_key(rec)
        if composite_key[0]:
            # composite bucket 与排序层级一致（sector -> major）：同复合组的行
            # 在排序中按 major 层相邻，跨 major 的组（workflow 内部筛选前 major
            # 分类不一致，如成交量=其他/成交持仓比=价格）不强制连续
            comp_bucket = (sector_key, selected_group, major_key)
            seen_keys = composite_seen.setdefault(comp_bucket, set())
            if (
                composite_last.get(comp_bucket) != composite_key[2]
                and composite_key[2] in seen_keys
            ):
                violations.append(
                    f"COMPOSITE_CONTIGUITY_VIOLATION sector={rec.get('sector')} "
                    f"indicator={rec.get('name')} composite_key={composite_key[2]} "
                    f"role={role_rank} major={major} sub={sub} "
                    f"freq={freq} row={rec.get('row_idx')} "
                    f"violated=matched_composite_key_not_contiguous"
                )
            composite_last[comp_bucket] = composite_key[2]
            seen_keys.add(composite_key[2])
        if selected_group in last_by_group:
            prev_sector_key, prev_major_key, prev_group_key, prev_role, prev_sub_key, prev = last_by_group[selected_group]
            current_sort = (sector_key, major_key, group_key, role_rank, sub_key)
            prev_sort = (prev_sector_key, prev_major_key, prev_group_key, prev_role, prev_sub_key)
            if current_sort < prev_sort:
                violations.append(
                    f"SORT_INVARIANT_VIOLATION sector={rec.get('sector')} "
                    f"indicator={rec.get('name')} major={major} sub={sub} row={rec.get('row_idx')} "
                    f"prev_indicator={prev.get('name')} prev_major={prev.get('major')} "
                    f"prev_sub={prev.get('sub')} prev_row={prev.get('row_idx')} "
                    f"violated=sector_or_major_or_composite_or_subcategory_priority"
                )
        last_by_group[selected_group] = (sector_key, major_key, group_key, role_rank, sub_key, rec)

    # 段名行顺序：按段内最小键单调（全局板块排序下段名行按 section_sort_key 参与排序）。
    # 无数据段名行（bottom 保留的孤立段头，pool 为空返回 (9999,)）跳过——
    # 其键与 data_sort_key 元组不可比较（int vs tuple 类型错误），且不参与段顺序。
    prev_segment_key = None
    prev_segment_sheet = None
    for rec in output_records:
        if rec.get("kind") != "sheet_header":
            continue
        if not any(r.get("sheet") == rec.get("sheet") for r in all_data):
            continue
        segment_key = section_sort_key(rec, all_data)
        if prev_segment_key is not None and segment_key < prev_segment_key:
            violations.append(
                f"SORT_INVARIANT_VIOLATION segment={rec.get('sheet')} "
                f"prev_segment={prev_segment_sheet} "
                f"violated=segment_major_or_subcategory_priority"
            )
        prev_segment_key = segment_key
        prev_segment_sheet = rec.get("sheet") or ""

    if violations:
        for line in violations:
            print(line)
        raise RuntimeError("SORT_INVARIANT_VIOLATION: fixed major/subcategory priority broken.")


def sort_catalog_workbook(
    input_path: Path,
    output_path: Path,
    sheet_name: str | None = None,
    add_normalized_column: bool = False,
    add_sort_reason_column: bool = False,
) -> tuple[Path, int]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = load_workbook(input_path)
    ws = wb[sheet_name] if sheet_name else wb.worksheets[0]
    records = classify_rows(ws)
    output_records = build_output(records)
    explanation_stats = generate_business_sort_reasons(output_records)
    print(f"Explanation stats: {explanation_stats}")
    validate_sort_invariants(output_records)
    data_count = sum(1 for r in records if r["kind"] == "data")
    header = next(r for r in records if r["kind"] == "header")
    normalized_insert_at = header.get("name_idx", 4) + 1
    header_values = list(header.get("values") or [])
    header_names = {str(v or "").strip() for v in header_values}
    has_normalized = NORMALIZED_NAME_HEADER in header_names
    has_sort_reason = SORT_REASON_HEADER in header_names
    insert_normalized = (add_normalized_column or add_sort_reason_column) and not has_normalized
    insert_sort_reason = add_sort_reason_column and not has_sort_reason
    reason_insert_at = normalized_insert_at + 1
    add_normalized_column = insert_normalized or insert_sort_reason
    add_sort_reason_column = insert_sort_reason

    for merged in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(merged))

    ws.delete_rows(1, ws.max_row)
    for row_idx, rec in enumerate(output_records, start=1):
        cells = rec.get("cells") or []
        values = list(rec.get("values") or [])
        if not add_normalized_column:
            for col_idx, src in enumerate(cells, start=1):
                dst = ws.cell(row=row_idx, column=col_idx)
                _copy_cell(src, dst)
                _ensure_hyperlink(rec, src, dst, col_idx)
            tags_idx = rec.get("tags_idx")
            if rec.get("kind") == "data" and tags_idx is not None:
                ws.cell(row=row_idx, column=tags_idx + 1).value = json.dumps(
                    rec.get("tags") or {}, ensure_ascii=False
                )
            continue

        if rec.get("kind") == "header":
            normalized = NORMALIZED_NAME_HEADER
            sort_reason = SORT_REASON_HEADER
        elif rec.get("kind") == "data":
            normalized = normalize_indicator_title(rec.get("name") or "")
            normalized = normalized or rec.get("name") or ""
            sort_reason = rec.get("sort_reason") or ""
        else:
            normalized = ""
            sort_reason = ""
        if normalized_insert_at >= len(values):
            values.extend([None] * (normalized_insert_at - len(values) + 1))
        if insert_normalized:
            values.insert(normalized_insert_at, normalized)
        if insert_sort_reason:
            values.insert(reason_insert_at, sort_reason)

        for col_idx in range(1, len(values) + 1):
            dst = ws.cell(row=row_idx, column=col_idx)
            zero = col_idx - 1
            if (insert_normalized and zero == normalized_insert_at) or (
                insert_sort_reason and zero == reason_insert_at
            ):
                dst.value = values[zero]
                continue
            if has_normalized and zero == normalized_insert_at:
                dst.value = normalized
                continue
            if has_sort_reason and zero == reason_insert_at:
                dst.value = sort_reason
                continue
            inserted_before = 0
            if insert_normalized and zero > normalized_insert_at:
                inserted_before += 1
            if insert_sort_reason and zero > reason_insert_at:
                inserted_before += 1
            src_zero = zero - inserted_before
            src = cells[src_zero] if src_zero < len(cells) else None
            if src is not None:
                _copy_cell(src, dst)
                _ensure_hyperlink(rec, src, dst, col_idx)
            else:
                dst.value = values[zero] if zero < len(values) else None
        tags_idx = rec.get("tags_idx")
        if rec.get("kind") == "data" and tags_idx is not None:
            tags_col = tags_idx + 1
            if insert_normalized and tags_col > normalized_insert_at + 1:
                tags_col += 1
            if insert_sort_reason and tags_col > reason_insert_at + 1:
                tags_col += 1
            ws.cell(row=row_idx, column=tags_col).value = json.dumps(
                rec.get("tags") or {}, ensure_ascii=False
            )
    # 表头筛选索引：所有列均可下拉筛选；"是否选中"/"二次筛选是否保留"
    # 等 是/否 列的筛选下拉直接显示 是/否 与各自指标数量。
    ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
    wb.save(output_path)
    return output_path, data_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sort the catalog sheet of a processed industry workbook.")
    parser.add_argument("--input", required=True, help="Input xlsx with 指标目录 sheet.")
    parser.add_argument("--output", default=None, help="Output xlsx path; defaults to <input>_sorted.xlsx.")
    parser.add_argument("--sheet-name", default=None, help="Catalog sheet name; defaults to the first sheet.")
    parser.add_argument(
        "--add-normalized-column",
        action="store_true",
        help="在指标名称右侧新增“指标名称归一化”列，仅用于最终目录输出。",
    )
    parser.add_argument(
        "--add-sort-reason-column",
        action="store_true",
        help="在指标名称归一化列右侧新增“排序说明”列；同时自动添加归一化列。",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input).resolve()
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = input_path.with_name(f"{input_path.stem}_sorted.xlsx")

    output_path, data_count = sort_catalog_workbook(
        input_path,
        output_path,
        args.sheet_name,
        add_normalized_column=args.add_normalized_column,
        add_sort_reason_column=args.add_sort_reason_column,
    )
    print(f"Input={input_path}")
    print(f"Output={output_path}")
    print(f"Catalog rows sorted={data_count}")
    if args.add_normalized_column:
        print("Normalized name column added")
    if args.add_sort_reason_column:
        print("Sort reason column added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
