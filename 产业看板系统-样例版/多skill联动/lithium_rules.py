# -*- coding: utf-8 -*-
"""Central deterministic rules for the lithium battery industry workflow.

All rule tables and pure classification/tagging functions live here so catalog
generation, directory curation, and rule documentation share one source of truth.
"""

from __future__ import annotations

import re

from catalog_utils import resolve_annualized_frequency


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
    ("锂矿", ["锂矿", "锂辉石", "锂云母", "矿山", "出港", "到港"]),
    ("碳酸锂", ["碳酸锂"]),
    ("氢氧化锂", ["氢氧化锂"]),
    ("其他锂盐", ["金属锂", "氯化锂", "硫化锂", "硫酸锂", "其他锂盐", "其他材料"]),
    ("三元正极", ["三元前驱体", "三元材料", "三元前", "韩国三元"]),
    ("磷酸铁锂", ["磷酸铁锂", "磷酸铁流通"]),
    ("钴酸锂", ["钴酸锂"]),
    ("锰酸锂", ["锰酸锂"]),
    (
        "磷化工链",
        [
            "磷矿",
            "磷酸一铵",
            "磷酸产能",
            "磷酸产量",
            "磷酸开工",
            "磷酸铁产能",
            "磷酸铁产量",
            "磷酸进出口",
            "磷矿石",
            "磷酸成本",
        ],
    ),
    ("负极材料", ["负极", "电解铜"]),
    ("隔膜", ["隔膜"]),
    ("电解液产业链", ["六氟磷酸锂", "氟化锂", "电解液"]),
    ("辅材", ["铝箔", "铜箔加工", "PVDF"]),
    ("电池电芯", ["Pack", "电芯", "铁锂电池", "锂电池", "锂原电池", "锂离子电池", "电池出口"]),
    (
        "新能源汽车",
        [
            "装机量",
            "汽车库存",
            "乘用车",
            "新能源车",
            "汽车产量",
            "汽车销量",
            "燃油车",
            "换电站",
            "充电桩",
            "上险量",
            "带电量",
            "保有量",
        ],
    ),
    ("储能", ["PCS", "储能", "峰谷价差", "逆变器"]),
    ("期现市场", ["期现价差", "基差", "期货价格", "月差"]),
    ("供需平衡", ["平衡", "平衡预测"]),
]

SECTORS = [
    "锂矿",
    "碳酸锂",
    "氢氧化锂",
    "其他锂盐",
    "三元正极",
    "磷酸铁锂",
    "钴酸锂",
    "锰酸锂",
    "磷化工链",
    "负极材料",
    "隔膜",
    "电解液产业链",
    "辅材",
    "电池电芯",
    "新能源汽车",
    "储能",
    "期现市场",
    "供需平衡",
    "其他",
]


def classify_sector(sn: str) -> str:
    for sector, keywords in SECTOR_RULES:
        if any(k in sn for k in keywords):
            return sector
    return "其他"


def classify_indicator_sector(sheet: str, name: str) -> str:
    if "氯化锂" in (name or ""):
        return "其他锂盐"
    return classify_sector(sheet or "")


def classify_category(sn: str) -> str:
    if "成本" in sn or "利润" in sn:
        return "四、成本利润"
    if any(k in sn for k in ["进出口", "进口", "出口", "盈亏"]):
        return "三、供需-进出口"
    if any(k in sn for k in ["库存", "仓单"]):
        return "三、供需-库存"
    if any(k in sn for k in ["需求", "消费", "装车", "装机", "用电", "发电", "装机量", "销量", "出货", "招标", "中标", "带电量", "上险量", "保有量"]):
        return "二、供需-需求"
    if "平衡" in sn:
        return "三、供需-平衡"
    if any(k in sn for k in ["产量", "产能", "储层", "开工", "平衡", "排产", "预测", "供应", "储量"]):
        return "二、供需-供给"
    if any(k in sn for k in ["成交", "持仓", "交易"]):
        return "五、量价"
    if any(k in sn for k in ["价格", "加工费", "价差", "基差", "月差", "价差"]):
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


PRODUCT_RULES = [
    ("三元前驱体", ["三元前驱体"]),
    ("三元材料", ["三元材料"]),
    ("磷酸铁锂", ["磷酸铁锂"]),
    ("磷酸铁", ["磷酸铁"]),
    ("六氟磷酸锂", ["六氟磷酸锂"]),
    ("氟化锂", ["氟化锂"]),
    ("磷酸一铵", ["磷酸一铵"]),
    ("磷矿石", ["磷矿石"]),
    ("磷矿", ["磷矿"]),
    ("磷酸", ["磷酸"]),
    ("氢氧化锂", ["氢氧化锂"]),
    ("碳酸锂", ["碳酸锂"]),
    ("金属锂", ["金属锂"]),
    ("氯化锂", ["氯化锂"]),
    ("硫化锂", ["硫化锂"]),
    ("硫酸锂", ["硫酸锂"]),
    ("氧化锂", ["氧化锂"]),
    ("电解液", ["电解液"]),
    ("钴酸锂", ["钴酸锂"]),
    ("锰酸锂", ["锰酸锂"]),
    ("负极材料", ["负极", "人造石墨"]),
    ("隔膜", ["隔膜"]),
    ("铝箔", ["铝箔"]),
    ("铜箔", ["铜箔"]),
    ("电解铜", ["电解铜"]),
    ("PVDF", ["PVDF"]),
    ("锂离子电池", ["锂离子电池"]),
    ("锂原电池", ["锂原电池"]),
    ("锂电池", ["锂电池"]),
    ("电芯", ["电芯"]),
    ("Pack", ["Pack"]),
    ("储能系统", ["储能系统"]),
    ("储能电池", ["储能电池"]),
    ("PCS", ["PCS"]),
    ("逆变器", ["逆变器"]),
    ("新能源汽车", ["新能源车"]),
    ("乘用车", ["乘用车"]),
    ("汽车", ["汽车"]),
    ("充电桩", ["充电桩"]),
    ("换电站", ["换电站"]),
    ("锂矿", ["锂矿", "锂辉石", "锂云母", "磷锂铝石", "锂精矿"]),
]


def extract_product(name: str, sheet: str, sector: str) -> str:
    text = _combined(name, sheet)
    for product, keywords in PRODUCT_RULES:
        if any(k in text for k in keywords):
            return product
    return sector if sector and sector != "其他" else "锂电产业链"


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
    if "持仓" in text:
        return "持仓"
    if any(k in text for k in ("基差", "期现", "升贴水")):
        return "基差"
    if any(k in text for k in ("价差", "溢价")):
        return "价差"
    if sub and sub != "其他":
        return sub
    return major if major != "其他" else "其他"


SPEC_PATTERNS = [
    re.compile(r"Li[₂2]O[：:]\s*[0-9.%-]+(?:[0-9.%-]*)"),
    re.compile(r"\d+(?:\.\d+)?%-\d+(?:\.\d+)?%"),
    re.compile(r"\d系"),
    re.compile(r"\d+(?:\.\d+)?(?:mm|mm2|μm|um)"),
]

SPEC_WORDS = [
    "电池级",
    "工业级",
    "准电池级",
    "粗颗粒",
    "细颗粒",
    "单晶",
    "多晶",
    "动力型",
    "消费型",
    "储能型",
    "高端",
    "中端",
    "低端",
    "小颗粒",
    "大颗粒",
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
    "锂辉石",
    "锂云母",
    "盐湖",
    "回收料",
    "矿石",
    "单晶",
    "多晶",
    "湿法",
    "干法",
    "电池级",
    "工业级",
    "高纯",
    "粉料",
    "颗粒",
    "动力型",
    "消费型",
]


def extract_process(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    found = [word for word in PROCESS_WORDS if word in text]
    return "; ".join(dict.fromkeys(found)) if found else "通用"


REGION_WORDS = [
    "澳大利亚",
    "澳洲",
    "巴西",
    "智利",
    "阿根廷",
    "美国",
    "韩国",
    "日本",
    "英国",
    "德国",
    "意大利",
    "中国",
    "全球",
    "海外",
    "北美",
    "欧洲",
    "俄罗斯",
    "秘鲁",
    "黎巴嫩",
    "马来西亚",
    "印尼",
    "印度尼西亚",
    "泰国",
    "越南",
    "印度",
    "加拿大",
    "墨西哥",
    "北卡罗来纳",
    "新加坡",
    "荷兰",
    "法国",
    "西班牙",
    "黑德兰港",
    "班伯利港",
    "埃斯珀伦斯",
    "镇江",
    "钦州",
    "青岛",
    "南通",
    "港口汇总",
    "主要港口",
    "北京",
    "上海",
    "广东",
    "江苏",
    "浙江",
    "山东",
    "福建",
    "湖南",
    "湖北",
    "河南",
    "河北",
    "四川",
    "重庆",
    "天津",
    "辽宁",
    "吉林",
    "黑龙江",
    "安徽",
    "江西",
    "广西",
    "海南",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "内蒙古",
    "新疆",
    "西藏",
    "山西",
    "青海省",
    "山东省",
    "江苏省",
    "广东省",
    "浙江省",
    "福建省",
    "湖北省",
    "湖南省",
    "河南省",
    "河北省",
    "四川省",
    "陕西省",
    "甘肃省",
    "辽宁省",
    "安徽省",
    "江西省",
    "广西壮族自治区",
    "宁夏回族自治区",
    "内蒙古自治区",
]


def extract_region(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    for region in REGION_WORDS:
        if region in text:
            return region
    return "未指定"


CALIBER_WORDS = [
    "加权平均价",
    "平均价",
    "均价",
    "最低价",
    "最高价",
    "收盘价",
    "结算价",
    "分国别",
    "分省份",
    "分级别",
    "分场景",
    "分电池类型",
    "分用户",
    "分类型",
    "港口汇总",
    "主要港口",
    "总计",
    "合计",
    "总量",
    "样本",
    "TOP5",
    "CR5",
]


def extract_caliber(name: str, sheet: str) -> str:
    text = _combined(name, sheet)
    for caliber in CALIBER_WORDS:
        if caliber in text:
            return caliber
    return "未指定"


STATUS_WORDS = ("预测", "计划", "目标", "预算", "估算")


def extract_status(name: str, sheet: str) -> str:
    # Status is judged from the indicator name only. Sheet names often contain
    # "预测" as a data-segment label (e.g. 产量+预测-月) which would mark every
    # row of the segment as 预测 and break the 当期-在前/预测-在后 ordering.
    text = str(name or "")
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
