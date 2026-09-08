# -*- coding: utf-8 -*-
from pathlib import Path


NEW_BLOCK = '''def _major_from_text(text: str) -> str:
    if "平衡" in text:
        return "平衡"
    if any(k in text for k in ("成本", "利润", "毛利率", "盈亏")):
        return "成本利润"
    if any(k in text for k in ("进出口", "进口", "出口", "出港", "到港", "贸易流向", "净出口", "发货量", "航运")):
        if not any(k in text for k in ("价格", "平均价", "均价", "基差", "价差", "月差", "加工费", "收盘价", "结算价", "CIF", "FOB", "升贴水", "溢价")):
            return "进出口"
    if any(k in text for k in ("库存", "仓单", "库容", "库销比", "库存天数", "库存周期")):
        return "库存"
    if any(k in text for k in (
        "产量", "产能", "开工", "排产", "出货量", "自给率", "储量",
        "市占率", "供应", "冶炼", "CR5", "集中度", "出货情绪",
    )):
        return "供给"
    if any(k in text for k in (
        "需求", "消费", "销量", "装机", "招标", "中标", "上险",
        "保有量", "带电量", "渗透率", "装车", "充电桩", "换电站",
        "批发", "零售", "消耗量", "配储", "要求", "建成规模",
        "工商业储能", "购货情绪", "成交情绪",
    )):
        return "需求"
    if any(k in text for k in (
        "价格", "平均价", "均价", "售价", "基差", "价差", "月差",
        "加工费", "收盘价", "结算价", "指数", "现货", "期货",
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
        if any(k in text for k in ("期货", "合约", "收盘价", "结算价")):
            return "期货价格"
        if any(k in text for k in ("价差", "升贴水", "溢价", "基差", "期现")):
            return "价差"
        if "加工费" in text:
            return "加工费"
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
        if any(k in text for k in ("销量", "上险量", "批发零售")):
            return "销量"
        if "装机" in text:
            return "装机"
        if any(k in text for k in ("招标", "中标")):
            return "招标中标"
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
        if any(k in text for k in ("产量", "排产", "出货量")):
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
        if "冶炼" in text:
            return "冶炼"
        if "建成规模" in text:
            return "建成规模"
        return "其他"
    if major == "平衡":
        return "供需平衡"
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
    "平衡": "供需平衡",
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
'''


for name in ["lithium_rules.py", "tin_rules.py"]:
    path = Path(r"C:\Users\11\Documents\多skill联动\scripts") / name
    text = path.read_text(encoding="utf-8")
    i = text.find("def classify_major(")
    j = text.find("def classify_nature(", i)
    if i < 0 or j < 0:
        print("marker not found", name)
        continue
    path.write_text(text[:i] + NEW_BLOCK + "\n\n\n" + text[j:], encoding="utf-8")
    print("updated", name)
