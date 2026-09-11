# -*- coding: utf-8 -*-
"""二次筛选规则：在第一次筛选（是否选中）之后追加的展示性筛选。

第一次筛选由 Skill2 公共规则 + 产业专属确定性规则（apply_industry_selection.py）
完成，结果写入目录表"是否选中"列（是/否）。二次筛选不修改"是否选中"，
只在目录表最右侧新增"二次筛选是否保留"列（是/否），供后续按需取数使用。

规则（按顺序判定，命中即止）：
1. 第一次筛选未选中（是否选中=否）的行，二次筛选一律为"否"。
2. 频率不是 日度/周度（即月度、半月度、季度、年度）的行，一律为"否"。
3. 标题含"指数"的指标，一律为"否"；但含"库存周期指数"或"库存天数"的指标
   除外（如"碳酸锂库存周期指数: 分环节库存天数: 总计"——"库存周期指数"是
   SMM 对库存天数指标的命名方式，实质是库存天数，不算指数）。
3b. 标题含"情绪因子"的指标，一律为"否"（如"磷酸铁出货/成交/购货情绪因子"）。
3c. 标题含"修复"（修复型指标）的指标，一律为"否"（如"修复型磷酸铁锂"）。
4. 锂电下游板块（负极材料/隔膜/辅材/新能源汽车）的所有行，一律为"否"。
5. 板块专属保留词：
   - 磷酸铁锂：仅保留标题含"磷酸铁"、"磷酸铁锂"或"磷酸锰铁锂"（LMFP）的指标
   - 三元正极：仅保留标题含"三元前驱体"或"三元材料"的指标
   - 电解液产业链：仅保留标题含"电解液"或"六氟磷酸锂"的指标
5b. 板块专属排除词：
   - 锂矿：指标名称中不带"原矿"的都是精矿（即使指标未写"精矿"二字，
     但实际就是精矿），因此锂矿板块仅排除标题含"原矿"的指标，其余保留。
   - 磷酸铁锂：仅排除"储能型压实密度≥2.30g/cm³"与"动力型压实密度≥2.50g/cm³"
     两个规格的平均价指标（周度版本），其他压实密度规格不受影响。
6. 锂盐板块：碳酸锂/氢氧化锂板块整板块保留（月差、基差等标题无产品名的
   碳酸锂期货指标同样保留）；其他锂盐板块整板块筛除。
7. 其余未提及板块（储能/电池电芯/磷化工链/锰酸锂/钴酸锂等）仅受规则 1-3
   约束。
"""

from __future__ import annotations

# 规则 2：只保留日度、周度
SECONDARY_KEEP_FREQUENCIES = frozenset({"日度", "周度"})

# 规则 3：标题含"指数"一律不保留；但"库存周期指数/库存天数"类指标除外
#（如"碳酸锂库存周期指数: 分环节库存天数: 总计"——"库存周期指数"是 SMM 对
# 库存天数指标的命名方式，实质是库存天数，不应按指数筛除）
SECONDARY_INDEX_WORD = "指数"
SECONDARY_INDEX_EXCEPTION_WORDS = ("库存周期指数", "库存天数")

# 规则 3b：标题含"情绪因子"一律不保留
SECONDARY_EMOTION_WORD = "情绪因子"

# 规则 3c：标题含"修复"（修复型指标）一律不保留
SECONDARY_REPAIR_WORD = "修复"

# 规则 4：锂电下游板块整板块筛除
SECONDARY_EXCLUDE_SECTORS = frozenset({"负极材料", "隔膜", "辅材", "新能源汽车"})

# 规则 5：板块专属保留词（标题必须包含任一保留词才保留）
SECONDARY_SECTOR_KEEP_WORDS = {
    "磷酸铁锂": ("磷酸铁", "磷酸铁锂", "磷酸锰铁锂"),
    # 磷化工链归入磷酸铁锂板块规则：只保留磷酸铁/磷酸铁锂/磷酸锰铁锂
    #（磷矿、磷酸、热法磷酸、磷酸一铵等一律不保留）
    "磷化工链": ("磷酸铁", "磷酸铁锂", "磷酸锰铁锂"),
    "三元正极": ("三元前驱体", "三元材料"),
    "电解液产业链": ("电解液", "六氟磷酸锂"),
}

# 规则 5b：板块专属排除词（标题含任一排除词即不保留）
# 锂矿：指标名称中不带"原矿"的都是精矿（即使未写"精矿"二字），仅排除"原矿"类指标
# 磷酸铁锂：仅排除"储能型压实密度≥2.30g/cm³"与"动力型压实密度≥2.50g/cm³"
#   两个规格的平均价指标（周度版本；同板块其他压实密度规格如粉体压实密度、
#   储能型 2.40/2.50 日度等不受影响）
SECONDARY_SECTOR_EXCLUDE_WORDS = {
    "锂矿": ("原矿",),
    "磷酸铁锂": ("储能型压实密度≥2.30g/cm³", "动力型压实密度≥2.50g/cm³"),
}

# 规则 6：锂盐板块（数据中拆分为三个板块名）：
# - 碳酸锂 / 氢氧化锂 板块整板块保留（不再按标题是否含产品名判断，
#   月差、基差等标题无产品名的碳酸锂期货指标同样保留）
# - 其他锂盐 板块整板块筛除
SECONDARY_LITHIUM_SALT_KEEP_SECTORS = frozenset({"碳酸锂", "氢氧化锂"})
SECONDARY_LITHIUM_SALT_EXCLUDE_SECTORS = frozenset({"其他锂盐"})


def secondary_selection_decision(
    title: str, frequency: str, sector: str, first_selected: bool
) -> tuple[bool, str]:
    """对单行做二次筛选判定，返回 (是否保留, 原因)。"""
    title = str(title or "")
    frequency = str(frequency or "").strip()
    sector = str(sector or "").strip()

    if not first_selected:
        return False, "二次筛选：第一次筛选未选中"
    if frequency not in SECONDARY_KEEP_FREQUENCIES:
        return False, "二次筛选：只保留日度/周度数据"
    if SECONDARY_INDEX_WORD in title and not any(
        word in title for word in SECONDARY_INDEX_EXCEPTION_WORDS
    ):
        return False, "二次筛选：指数类指标不保留"
    if SECONDARY_EMOTION_WORD in title:
        return False, "二次筛选：情绪因子类指标不保留"
    if SECONDARY_REPAIR_WORD in title:
        return False, "二次筛选：修复型指标不保留"
    if sector in SECONDARY_EXCLUDE_SECTORS:
        return False, "二次筛选：锂电下游板块（负极材料/隔膜/辅材/新能源汽车）不保留"
    if sector in SECONDARY_SECTOR_KEEP_WORDS:
        words = SECONDARY_SECTOR_KEEP_WORDS[sector]
        if not any(word in title for word in words):
            return False, f"二次筛选：{sector}板块仅保留{'/'.join(words)}相关指标"
        # 板块同时配置排除词时（如磷酸铁锂的特定压实密度规格），
        # 排除词优先于保留词判定
        exclude = SECONDARY_SECTOR_EXCLUDE_WORDS.get(sector, ())
        if any(word in title for word in exclude):
            return False, f"二次筛选：{sector}板块排除{'/'.join(exclude)}类指标"
        return True, "二次筛选：保留"
    if sector in SECONDARY_SECTOR_EXCLUDE_WORDS:
        exclude = SECONDARY_SECTOR_EXCLUDE_WORDS[sector]
        if any(word in title for word in exclude):
            return False, f"二次筛选：{sector}板块排除{'/'.join(exclude)}类指标"
        return True, "二次筛选：保留"
    if sector in SECONDARY_LITHIUM_SALT_KEEP_SECTORS:
        return True, "二次筛选：保留"
    if sector in SECONDARY_LITHIUM_SALT_EXCLUDE_SECTORS:
        return False, "二次筛选：其他锂盐板块不保留"
    return True, "二次筛选：保留"


def apply_secondary_selection(rows: list[dict]) -> list[dict]:
    """对全部目录行计算二次筛选结果，写入 secondary_keep / secondary_reason。"""
    for row in rows:
        keep, reason = secondary_selection_decision(
            str(row.get("title") or ""),
            str(row.get("frequency") or ""),
            str(row.get("sector") or ""),
            bool(row.get("selected")),
        )
        row["secondary_keep"] = keep
        row["secondary_reason"] = reason
    return rows


# ── 锡/硅（通用）二次筛选规则 ──
# 锡、硅数据暂无锂电的板块保留词/排除词等专属规则，仅受通用约束：
# 未选中 -> 否；频率非日/周度 -> 否；标题含"指数"（含"库存周期指数/库存天数"
# 例外的除外）-> 否。与 secondary_selection_decision（锂电专属）并列。
def secondary_selection_decision_generic(
    title: str, frequency: str, first_selected: bool
) -> tuple[bool, str]:
    """锡/硅板块的通用二次筛选判定，返回 (是否保留, 原因)。"""
    title = str(title or "")
    frequency = str(frequency or "").strip()

    if not first_selected:
        return False, "二次筛选：第一次筛选未选中"
    if frequency not in SECONDARY_KEEP_FREQUENCIES:
        return False, "二次筛选：只保留日度/周度数据"
    if SECONDARY_INDEX_WORD in title and not any(
        word in title for word in SECONDARY_INDEX_EXCEPTION_WORDS
    ):
        return False, "二次筛选：指数类指标不保留"
    return True, "二次筛选：保留"
