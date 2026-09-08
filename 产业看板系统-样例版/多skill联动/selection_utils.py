# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict

from catalog_utils import resolve_annualized_frequency


CONTRACT_PATTERN = re.compile(
    r"(主力合约|当月合约|01合约|05合约|09合约|(?<!十)一月合约|五月合约|九月合约)"
)

VOLUME_SUBS = {"成交量"}
POSITION_SUBS = {"持仓", "持仓量"}
FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")
FREQ_RANK = {
    "日度": 4,
    "周度": 3,
    "月度": 2,
    "季度": 1,
    "年度": 0,
}
SPREAD_KEEP = ("01-05", "05-09", "09-01")

_MONTH_ALIASES = (
    ("十二月", "12"),
    ("十一月", "11"),
    ("十月", "10"),
    ("九月", "09"),
    ("八月", "08"),
    ("七月", "07"),
    ("六月", "06"),
    ("五月", "05"),
    ("四月", "04"),
    ("三月", "03"),
    ("二月", "02"),
    ("一月", "01"),
)

CONTRACT_NAMES = (
    "主力合约",
    "十二月合约",
    "十一月合约",
    "十月合约",
    "九月合约",
    "八月合约",
    "七月合约",
    "六月合约",
    "五月合约",
    "四月合约",
    "三月合约",
    "二月合约",
    "一月合约",
    "01合约",
    "02合约",
    "03合约",
    "04合约",
    "05合约",
    "06合约",
    "07合约",
    "08合约",
    "09合约",
    "10合约",
    "11合约",
    "12合约",
)

CONTRACT_CANONICAL = {
    "主力合约": "主力合约",
    "一月合约": "01合约",
    "二月合约": "02合约",
    "三月合约": "03合约",
    "四月合约": "04合约",
    "五月合约": "05合约",
    "六月合约": "06合约",
    "七月合约": "07合约",
    "八月合约": "08合约",
    "九月合约": "09合约",
    "十月合约": "10合约",
    "十一月合约": "11合约",
    "十二月合约": "12合约",
    "01合约": "01合约",
    "02合约": "02合约",
    "03合约": "03合约",
    "04合约": "04合约",
    "05合约": "05合约",
    "06合约": "06合约",
    "07合约": "07合约",
    "08合约": "08合约",
    "09合约": "09合约",
    "10合约": "10合约",
    "11合约": "11合约",
    "12合约": "12合约",
}


def is_target_contract(title: str) -> bool:
    return bool(CONTRACT_PATTERN.search(str(title or "")))


def volume_position_key(title: str, frequency: str = "") -> str:
    text = str(title or "")
    text = re.sub(r"成交量（手）|成交量|持仓量|持仓", "", text)
    text = re.sub(r"[：:]\s*(日度|周度|月度|季度|年度)$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" :_")
    return f"{text}|{str(frequency or '').strip()}"


def _extract_product_contract(title: str) -> tuple[str, str]:
    text = str(title or "")
    text = re.sub(r"成交量（手）|成交量|持仓量|持仓|成交持仓比", "", text)
    text = re.sub(r"[：:]\s*(日度|周度|月度|季度|年度)$", "", text)
    for contract in CONTRACT_NAMES:
        if contract in text:
            product = text.replace(contract, "")
            product = re.sub(r"^(GFEX|SHFE|LME|JFX|ICDX)[：:\s]+", "", product)
            product = re.sub(r"[：:\s_]+", "", product)
            return product, CONTRACT_CANONICAL.get(contract, contract)
    return "", ""


def volume_position_ratio_key(title: str, frequency: str = "") -> str:
    product, contract = _extract_product_contract(title)
    return f"{product}|{contract}|{str(frequency or '').strip()}"


def normalize_metric_title(title: str) -> str:
    text = str(title or "")
    if text.endswith("半月度"):
        text = text[: -len("半月度")].strip().rstrip(":").strip()
    else:
        for suffix in FREQ_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip().rstrip(":").strip()
                break
    text = re.sub(r"^(SMM|SHFE|GFEX|DCE|CZCE|INE)\s*[：:]", "", text)
    for chinese_month, numeric_month in _MONTH_ALIASES:
        text = text.replace(chinese_month, numeric_month)
    text = re.sub(r"[：:－—–-]", "", text)
    text = re.sub(r"\s+", "", text)
    normalized = re.sub(r"[^\w\u4e00-\u9fff.]+", "", text)
    return normalized or str(title or "").strip()


SOURCE_PREFIX_PATTERN = re.compile(
    r"^\s*(SMM|Mysteel|百川|Wind|iFind)\s*[：:]\s*",
    re.IGNORECASE,
)
DASH_VARIANTS = "－—–―~〜"


def normalize_comparison_text(value) -> str:
    """Normalize text for internal frequency/identity comparison only."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    for char in DASH_VARIANTS:
        text = text.replace(char, "-")
    text = re.sub(r"[\s：:，,。．（）()\-_/]+", "", text)
    return text.strip()


def _parse_comparison_tags(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _strip_source_prefix(title: str) -> str:
    return SOURCE_PREFIX_PATTERN.sub("", str(title or ""), count=1)


def _normalize_chemical_formula_text(text: str) -> str:
    """锂矿品位化学式归一化：删除 "Li2O:" / "Li₂O:"（含 ASCII 2 与下标 ₂
    两种写法）品位标注。

    "锂辉石（中国现货 Li2O: 3%-4%）" 与 "锂辉石（中国现货 3%-4%）" 是同一
    指标（化学式仅为品位标注，日度版多写、周度/月度版省略），删除后同组去重
    只保留最高频。精确匹配化学式字样，不影响 NMP/DMC/FEC 等含其他英文字母
    的指标。
    """
    text = re.sub(r"Li₂O\s*[:：]?\s*", "", text)
    text = re.sub(r"Li2O\s*[:：]?\s*", "", text)
    return text


def _normalize_spec_value(value) -> str:
    """规格标签归一化：按 ";" 拆分后逐段删除化学式标注并去重。

    日度版规格常同时写入 "Li2O: 3%-4%; 3%-4%"（化学式+区间两种写法），
    周度/月度版只写 "3%-4%"；删化学式并去重后两者一致，保证同指标
    多频率归入同一组、只保留最高频。
    """
    parts = []
    for part in str(value or "").split(";"):
        cleaned = _normalize_chemical_formula_text(part.strip())
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return ";".join(parts)


def _normalize_cobalt_price_text(text: str) -> str:
    """钴酸锂价格标题归一化（仅含"钴酸锂"的标题启用）。

    - "4.45V钴酸锂(国产)" 与 "钴酸锂 4.45V" 视为同一产品：周度版标题省略
      "国产"标注，按用户规则均视为国产钴酸锂，删除"国产"并统一电压词序；
    - 电压尾零归一化：4.40V/4.50V 与 4.4V/4.5V 视为同一产品。
    """
    if "钴酸锂" not in text:
        return text
    text = text.replace("钴酸锂(国产)", "钴酸锂").replace("钴酸锂（国产）", "钴酸锂")
    text = re.sub(r"(\d+(?:\.\d+)?)V\s*钴酸锂", r"钴酸锂\1V", text)
    text = re.sub(r"(\d+\.\d*[1-9])0+(?=V)", r"\1", text)
    return text


def _strip_frequency_suffix(title: str) -> str:
    text = str(title or "").strip()
    # 半月度 is treated as 月度 (half-month frequency is monthly-frequency
    # data); strip it as a whole first so it groups with the 月度 rows instead
    # of leaving a stray "半" behind after the generic suffix match.
    if text.endswith("半月度"):
        return text[: -len("半月度")].strip()
    for suffix in FREQ_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def frequency_comparison_key(row: dict) -> tuple:
    """Build a frequency-group identity key that preserves business dimensions."""
    title = str(row.get("title") or "")
    source = str(row.get("source") or "").strip()
    if not source:
        match = SOURCE_PREFIX_PATTERN.match(title)
        source = match.group(1) if match else ""

    body = _normalize_chemical_formula_text(
        _normalize_cobalt_price_text(
            _strip_source_prefix(_strip_frequency_suffix(title))
        )
    )
    tags = _parse_comparison_tags(row.get("tags"))

    fields = [
        normalize_comparison_text(source),
        normalize_comparison_text(row.get("sector") or row.get("sheet") or ""),
        normalize_comparison_text(row.get("major") or ""),
        normalize_comparison_text(row.get("sub") or ""),
        normalize_comparison_text(row.get("nature") or ""),
        normalize_comparison_text(row.get("unit") or ""),
        normalize_comparison_text(body),
    ]
    for key in ("规格", "工艺属性", "地域", "统计口径", "状态"):
        value = tags.get(key) or ""
        if key == "规格":
            value = _normalize_spec_value(value)
        fields.append(normalize_comparison_text(value))
    return tuple(fields)


def _effective_frequency(title: str, fallback: str = "") -> str:
    annualized = resolve_annualized_frequency(title or "")
    if annualized:
        return annualized
    text = str(title or "")
    for suffix in FREQ_SUFFIXES:
        if text.endswith(suffix):
            return suffix
    return str(fallback or "").strip()


def _evaluate_common_price(sub: str, title: str, frequency: str) -> tuple[bool, str]:
    if sub == "成交持仓比":
        return True, "公共价格规则：成交持仓比全部保留"
    # 合约过滤仅限合约类子类：期现价差（现货-期货）、交割库容等标题含"期货"
    # 字样但非合约行的指标不受影响（走后续基差/价差规则或保留）
    if sub in ("期货价格", "成交量", "持仓"):
        return bool(CONTRACT_PATTERN.search(title)), "公共价格规则：仅保留主力/01/05/09合约"
    if sub == "月差" or "月差" in title:
        return any(token in title for token in SPREAD_KEEP), "公共价格规则：月差仅保留01-05/05-09/09-01"
    if sub == "基差" or "基差" in title or "期现" in title:
        if "现货-期货" in title or "当月合约" in title or "现货升贴水" in title:
            return True, "公共价格规则：基差/期现价差保留"
        return False, "公共价格规则：基差仅保留当月期现/现货升贴水"
    if sub in ("价差", "现货价差") or "价差" in title:
        return True, "公共价格规则：价差全部保留"
    return True, "公共价格规则：仅保留最高频"


def apply_common_price_rules(rows: list[dict]) -> list[dict]:
    for row in rows:
        if row.get("major") != "价格":
            continue
        sub = str(row.get("sub") or "")
        title = str(row.get("title") or "")
        frequency = _effective_frequency(title, str(row.get("frequency") or ""))
        row["selected"], row["reason"] = _evaluate_common_price(sub, title, frequency)

    groups: dict[tuple, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if row.get("major") == "价格" and row.get("selected"):
            groups[frequency_comparison_key(row)].append(idx)

    for indices in groups.values():
        ranks = [
            FREQ_RANK.get(
                _effective_frequency(
                    str(rows[i].get("title") or ""), str(rows[i].get("frequency") or "")
                ),
                -1,
            )
            for i in indices
        ]
        best_rank = max(ranks)
        kept = False
        for idx in indices:
            rank = FREQ_RANK.get(
                _effective_frequency(
                    str(rows[idx].get("title") or ""), str(rows[idx].get("frequency") or "")
                ),
                -1,
            )
            if rank == best_rank:
                rows[idx]["selected"] = True
                rows[idx]["reason"] = "公共价格规则：仅保留最高频"
                if kept:
                    rows[idx]["selected"] = False
                    rows[idx]["reason"] = "公共价格规则：同指标重复，只保留一条"
                kept = True
            else:
                rows[idx]["selected"] = False
                rows[idx]["reason"] = "公共价格规则：仅保留最高频"
    return rows


EXCLUDE_RATIO_WORDS = ("同比", "环比", "占比")
EXCLUDE_IMPORT_EXPORT_AVERAGE_WORDS = ("进出口均价", "进口均价", "出口均价", "净出口均价")
EXCLUDE_IMPORT_EXPORT_AMOUNT_WORDS = (
    "进口额",
    "出口额",
    "净出口额",
    "进口金额",
    "出口金额",
    "净出口金额",
    "进口总额",
    "出口总额",
    "净出口总额",
    "总额",
    "总值",
    "金额",
)


def exclude_yoy_mom_share_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        title = str(row.get("title") or "")
        if any(word in title for word in EXCLUDE_RATIO_WORDS):
            row["selected"] = False
            if row.get("major") == "供给" and any(
                word in title for word in ("同比", "环比")
            ):
                row["reason"] = "供给大类同环比指标不保留"
            else:
                row["reason"] = "同比/环比/占比指标不保留"
    return rows


def exclude_import_export_average_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        title = str(row.get("title") or "")
        if any(word in title for word in EXCLUDE_IMPORT_EXPORT_AVERAGE_WORDS):
            row["selected"] = False
            row["reason"] = "进出口均价指标不保留"
    return rows


def exclude_import_export_amount_rows(rows: list[dict]) -> list[dict]:
    for row in rows:
        title = str(row.get("title") or "")
        if "进口" not in title and "出口" not in title:
            continue
        if any(word in title for word in EXCLUDE_IMPORT_EXPORT_AMOUNT_WORDS):
            row["selected"] = False
            row["reason"] = "进出口金额指标不保留"
    return rows


def ensure_unique_selected_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if not row.get("selected"):
            continue
        title = str(row.get("title") or "")
        frequency = str(row.get("frequency") or "")
        for suffix in FREQ_SUFFIXES:
            if title.endswith(suffix):
                frequency = suffix
                break
        key = (
            str(row.get("major") or ""),
            str(row.get("sub") or ""),
            normalize_metric_title(title),
            frequency,
        )
        if key in seen:
            row["selected"] = False
            row["reason"] = "同指标重复，只保留一条"
        else:
            seen.add(key)
    return rows


def _ie_product_key(title: str) -> str:
    text = normalize_metric_title(title or "")
    # 地区词归一化：补算净出口标题可能缺"中国"（如"中国海关 金属锂净出口"
    # vs "中国海关: 中国金属锂进口量"），删除地区词使配对键一致。
    for word in ("中国", "日本", "美国", "韩国", "英国", "德国", "澳大利亚", "智利", "阿根廷", "巴西"):
        text = text.replace(word, "")
    for word in ("净出口", "净进口", "进出口", "进口量", "出口量", "进口", "出口", "总计", "合计", "总量", "累计", "量"):
        text = text.replace(word, "")
    # 残留分隔符：进口/出口标题"进口量_总计"（下划线格式）去词后残留下划线
    #（如"海关精炼锡_"），与净出口标题（无"量_总计"结构）的配对键不一致，
    # 导致配对失败被滤除（进出口三子类数量失衡）
    text = text.replace("_", "")
    return text


def enforce_composite_pairing(rows: list[dict]) -> None:
    """成交持仓与进出口复合组必须配对齐全才保留（用户规则）。

    - 价格/成交持仓组：同一 产品+合约+频率 下必须同时存在 成交量 与 持仓/持仓量，
      否则该组所有行（含成交持仓比）都不保留。
    - 进出口组：同一产品下必须同时存在 进口 与 出口，否则该组所有行
      （含净出口）都不保留。
    """
    ma_groups: dict[str, set] = {}
    ie_groups: dict[str, set] = {}
    for row in rows:
        if not row.get("selected"):
            continue
        major = row.get("major")
        sub = str(row.get("sub") or "")
        title = str(row.get("title") or "")
        if major == "价格" and sub in ("成交量", "持仓", "持仓量", "成交持仓比"):
            key = volume_position_ratio_key(title, str(row.get("frequency") or ""))
            ma_groups.setdefault(key, set()).add(sub)
        elif major == "进出口" and sub in ("进口", "出口", "净出口"):
            key = _ie_product_key(title)
            ie_groups.setdefault(key, set()).add(sub)

    for row in rows:
        if not row.get("selected"):
            continue
        major = row.get("major")
        sub = str(row.get("sub") or "")
        title = str(row.get("title") or "")
        if major == "价格" and sub in ("成交量", "持仓", "持仓量", "成交持仓比"):
            key = volume_position_ratio_key(title, str(row.get("frequency") or ""))
            roles = ma_groups.get(key, set())
            if not (roles & {"成交量"}) or not (roles & {"持仓", "持仓量"}):
                row["selected"] = False
                row["reason"] = "成交持仓组缺少配对成交量或持仓量，不保留"
        elif major == "进出口" and sub in ("进口", "出口", "净出口"):
            roles = ie_groups.get(_ie_product_key(title), set())
            if "进口" not in roles or "出口" not in roles:
                row["selected"] = False
                row["reason"] = "进出口组缺少配对进口或出口，不保留"


def remove_confidence_column(workbook) -> bool:
    removed = False
    for ws in workbook.worksheets:
        headers = [str(cell.value or "").strip() for cell in ws[1]]
        if "置信度" not in headers:
            continue
        col = headers.index("置信度") + 1
        ws.delete_cols(col)
        removed = True
    return removed


def ensure_volume_position_pairing(rows: list[dict]) -> list[dict]:
    selected = [row for row in rows if row.get("selected")]
    volume_keys = {
        volume_position_key(
            row.get("title", ""), row.get("frequency", "")
        )
        for row in selected
        if row.get("sub") in VOLUME_SUBS
    }
    position_keys = {
        volume_position_key(
            row.get("title", ""), row.get("frequency", "")
        )
        for row in selected
        if row.get("sub") in POSITION_SUBS
    }

    for row in rows:
        sub = row.get("sub")
        if not row.get("selected") or sub not in VOLUME_SUBS | POSITION_SUBS:
            continue
        key = volume_position_key(
            row.get("title", ""), row.get("frequency", "")
        )
        has_counterpart = (
            key in position_keys if sub in VOLUME_SUBS else key in volume_keys
        )
        if not has_counterpart:
            row["selected"] = False
            row["reason"] = "成交量/持仓量无对应持仓/成交量，不选中"
    return rows
