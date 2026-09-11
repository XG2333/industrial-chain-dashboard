# -*- coding: utf-8 -*-
"""Deterministic Composite Metric Stage.

This stage runs after Skill2 and before Skill4. It only identifies composite
groups, writes structured composite metadata, and computes derived metrics for
complete market_activity / trade groups. It does not classify, sort, or touch
Dashboard row packing.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from import_export_rules import compute_net_series, metric_key
from selection_utils import CONTRACT_CANONICAL, CONTRACT_NAMES


COMPOSITE_SHEET_NAME = "复合指标计算"
FREQ_SUFFIXES = ("日度", "周度", "月度", "季度", "年度")
EXCHANGE_PREFIXES = ("SHFE:", "GFEX:", "DCE:", "CZCE:", "INE:", "LME:", "JFX:", "ICDX:")
SOURCE_PREFIX_RE = re.compile(r"^\s*(SMM|Mysteel|百川|Wind|iFind|中国海关|韩国海关|日本海关|美国海关)\s*[：:]", re.IGNORECASE)


def _normalize(value) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _compact(value) -> str:
    text = _normalize(value)
    return re.sub(r"[\s：:，,。.（）()\-_/]+", "", text)


def _parse_tags(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _freq(title: str, fallback: str = "") -> str:
    text = str(title or "").strip()
    for suffix in FREQ_SUFFIXES:
        if text.endswith(suffix):
            return suffix
    return str(fallback or "").strip() or "日度"


def _source(title: str) -> str:
    match = SOURCE_PREFIX_RE.match(str(title or ""))
    return match.group(1) if match else ""


def _exchange(title: str) -> str:
    text = _normalize(title)
    for prefix in EXCHANGE_PREFIXES:
        if text.upper().startswith(prefix):
            return prefix.rstrip(":")
    return ""


def _contract(title: str) -> str:
    text = str(title or "")
    for name in CONTRACT_NAMES:
        if name in text:
            return CONTRACT_CANONICAL.get(name, name)
    return ""


def _product_contract(title: str) -> tuple[str, str]:
    text = str(title or "")
    text = re.sub(r"成交量（手）|成交量|持仓量|持仓|成交持仓比", "", text)
    # Strip the contract using its original spelling (e.g. 一月合约) so the
    # product part is identical across 成交量/持仓量/成交持仓比 rows regardless
    # of whether the title spells the contract in Chinese or digits.
    contract_name = ""
    for name in CONTRACT_NAMES:
        if name in text:
            contract_name = name
            break
    contract = CONTRACT_CANONICAL.get(contract_name, contract_name)
    product = text.replace(contract_name, "") if contract_name else text
    product = re.sub(r"^(SHFE|GFEX|DCE|CZCE|INE|LME|JFX|ICDX)\s*[：:\s]+", "", product)
    product = re.sub(r"^(SMM|Mysteel|百川|Wind|iFind)\s*[：:\s]+", "", product)
    product = re.sub(r"[：:]\s*(日度|周度|月度|季度|年度)$", "", product)
    return _compact(product), contract


def _date_string(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()[:10]


def _to_number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _series(workbook, sheet_name: str, col: int) -> dict[str, float]:
    ws = workbook[sheet_name]
    values: dict[str, float] = {}
    for row in ws.iter_rows(min_row=4):
        date_cell = row[0].value
        if date_cell is None or str(date_cell).strip() == "":
            continue
        value = _to_number(row[col].value) if col < len(row) else None
        if value is not None:
            values[_date_string(date_cell)] = value
    return values


def load_records(ws) -> list[dict]:
    headers = [str(c.value or "").strip() for c in ws[1]]
    colmap = {header: idx for idx, header in enumerate(headers) if header}

    def col(name: str, default: int | None = None) -> int | None:
        return colmap.get(name, default)

    name_idx = col("Indicator Name", 4)
    col_idx = col("Col", 3)
    freq_idx = col("Freq", 2)
    unit_idx = col("Unit")
    if unit_idx is None:
        unit_idx = name_idx + 2 if any(k in colmap for k in ("指标名称归一化", "排序说明")) else name_idx + 1
    sector_idx = col("板块", 6)
    major_idx = col("大类", 7)
    sub_idx = col("子类", 8)
    nature_idx = col("数据性质", 9)
    selected_idx = col("是否选中", 11 if "置信度" in colmap else 10)
    tags_idx = col("指标标签", 13 if "置信度" in colmap else 12)

    records = []
    current_sheet = ""
    for row_idx in range(2, ws.max_row + 1):
        values = [c.value for c in ws[row_idx]]
        c0 = str(values[0] or "").strip()
        cname = str(values[name_idx] or "").strip() if name_idx is not None and name_idx < len(values) else ""
        if not c0.isdigit() or not cname:
            if c0 and not c0.isdigit():
                current_sheet = c0
            continue
        tags = _parse_tags(values[tags_idx] if tags_idx is not None and tags_idx < len(values) else None)
        records.append(
            {
                "sheet": current_sheet,
                "title": cname,
                "col": int(str(values[col_idx] or 0)) if col_idx is not None and values[col_idx] is not None else 0,
                "frequency": str(values[freq_idx] or "").strip() if freq_idx is not None else "",
                "unit": str(values[unit_idx] or "").strip() if unit_idx is not None else "",
                "sector": str(values[sector_idx] or "").strip() if sector_idx is not None else "",
                "major": str(values[major_idx] or "").strip() if major_idx is not None else "",
                "sub": str(values[sub_idx] or "").strip() if sub_idx is not None else "",
                "nature": str(values[nature_idx] or "").strip() if nature_idx is not None else "",
                "selected": str(values[selected_idx] or "").strip() if selected_idx is not None else "是",
                "tags": tags,
                "_row_idx": row_idx,
            }
        )
    return records


def _market_role(rec: dict) -> str | None:
    sub = rec.get("sub") or ""
    title = rec.get("title") or ""
    # At this stage (right after Skill2) the subcategory of 成交持仓比 rows is
    # still the Skill2 value (e.g. 价格), so role detection must fall back to
    # the title text. Note "成交持仓比" contains the substring "持仓", so the
    # open_interest branch must exclude titles that contain 成交持仓比 first.
    if sub == "成交持仓比" or ("成交持仓比" in title and "持仓量" not in title):
        return "oi_volume_ratio"
    if sub == "成交量" or (sub == "价格" and "成交量" in title and "持仓" not in title):
        return "volume"
    if sub in ("持仓", "持仓量") or ("持仓" in title and "成交持仓比" not in title):
        return "open_interest"
    return None


def _trade_role(rec: dict) -> str | None:
    sub = rec.get("sub") or ""
    title = rec.get("title") or ""
    # At this stage (right after Skill2) the subcategory of trade rows is often
    # still 其他, so role detection relies on the title text.
    if ("进口量" in title and "净" not in title) or (sub == "进口" and "进口量" in title):
        return "import"
    if ("出口量" in title and "净" not in title) or (sub == "出口" and "出口量" in title):
        return "export"
    if "净出口" in title or "净进口" in title or sub == "净出口":
        return "net_export"
    return None


def _balance_role(rec: dict) -> str | None:
    title = rec.get("title") or ""
    text = f"{rec.get('sheet') or ''} {title}"
    if "平衡" not in text:
        return None
    if "产量" in title:
        return "production"
    if "进口" in title:
        return "import"
    if "出口" in title:
        return "export"
    if any(k in title for k in ("需求量", "需求", "消费量", "消费")):
        return "demand"
    if "平衡" in title:
        return "balance"
    return None


def _market_key(rec: dict) -> str:
    product, contract = _product_contract(rec.get("title") or "")
    tags = rec.get("tags") or {}
    product = product or _compact(tags.get("产品") or "")
    contract = contract or _compact(tags.get("合约") or "")
    role = _market_role(rec)
    unit = _compact(rec.get("unit") or "")
    if role == "oi_volume_ratio" and not unit:
        # 成交持仓比 rows carry no unit in the catalog; futures market-activity
        # volumes are quoted in 手, so align the unit so the ratio row joins
        # the same contract group as its 成交量/持仓量 siblings.
        unit = "手"
    # Exchange/统计口径 are dropped so that 成交量/持仓量/成交持仓比 of the same
    # contract land in one composite group (otherwise 4 same-role rows become
    # AMBIGUOUS and the ratio row never joins). Unit stays to keep different
    # units (手 vs 万吨) apart.
    fields = [
        product,
        contract,
        _freq(rec.get("title") or "", rec.get("frequency") or ""),
        unit,
        _compact(tags.get("状态") or rec.get("nature") or ""),
    ]
    return "|".join(fields)


def _trade_key(rec: dict) -> str:
    tags = rec.get("tags") or {}
    scope = _compact(tags.get("统计口径") or "")
    for token in ("进口量", "出口量", "净出口量", "净进口量", "进口", "出口", "净出口", "净进口", "量", "额"):
        scope = scope.replace(token, "")
    fields = [
        _source(rec.get("title") or ""),
        _compact(metric_key(rec.get("title") or "")),
        _compact(tags.get("地域") or ""),
        scope,
        _freq(rec.get("title") or "", rec.get("frequency") or ""),
        _compact(rec.get("unit") or ""),
        _compact(tags.get("状态") or rec.get("nature") or ""),
    ]
    return "|".join(fields)


def _balance_base(rec: dict) -> str:
    text = rec.get("title") or rec.get("sheet") or ""
    text = re.sub(r"(产量|进口量|出口量|需求量|需求|消费量|消费|平衡|日度|周度|月度|季度|年度)", "", text)
    return _compact(text)


def _balance_key(rec: dict) -> str:
    tags = rec.get("tags") or {}
    return "|".join(
        [
            _balance_base(rec),
            _freq(rec.get("title") or "", rec.get("frequency") or ""),
            _compact(tags.get("状态") or rec.get("nature") or ""),
        ]
    )


def _build_market_groups(records: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = defaultdict(lambda: {"volume": [], "open_interest": [], "oi_volume_ratio": []})
    for rec in records:
        role = _market_role(rec)
        if not role:
            continue
        if rec.get("selected") != "是":
            continue
        key = _market_key(rec)
        groups[key][role].append(rec)
    return dict(groups)


def _build_trade_groups(records: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = defaultdict(lambda: {"import": [], "export": [], "net_export": []})
    for rec in records:
        role = _trade_role(rec)
        if not role:
            continue
        if _balance_role(rec):
            continue
        # Mark rows even when Skill2 has not selected them yet: the industry
        # selection stage later selects total monthly import/export rows, and
        # the frontend needs the composite metadata to group them into one row.
        key = _trade_key(rec)
        groups[key][role].append(rec)
    return dict(groups)


def _build_balance_groups(records: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        role = _balance_role(rec)
        if not role:
            continue
        key = _balance_key(rec)
        groups[key][role].append(rec)
    return dict(groups)


def _ratio_series(workbook, volume_rec: dict, position_rec: dict) -> tuple[list[dict], list[str]]:
    volumes = _series(workbook, volume_rec["sheet"], volume_rec["col"])
    positions = _series(workbook, position_rec["sheet"], position_rec["col"])
    rows: list[dict] = []
    reasons: list[str] = []
    for date_key, volume in volumes.items():
        position = positions.get(date_key)
        if position is None:
            continue
        if volume == 0:
            reasons.append(f"volume_zero:{date_key}")
            continue
        rows.append({"date": date_key, "value": round(position / volume, 4)})
    rows.sort(key=lambda item: item["date"], reverse=True)
    return rows, reasons


def _reconcile_net(computed: list[dict], source: list[dict]) -> str:
    computed_map = {item["date"]: item["value"] for item in computed}
    source_map = {item["date"]: item["value"] for item in source}
    diffs = []
    for date_key in sorted(set(computed_map) & set(source_map)):
        left = computed_map[date_key]
        right = source_map[date_key]
        tolerance = max(1.0, abs(right) * 0.01)
        if abs(left - right) > tolerance:
            diffs.append(date_key)
    if diffs:
        return "NET_EXPORT_RECONCILIATION_WARNING"
    return "OK"


def _write_composite_sheet(workbook, rows: list[dict]) -> None:
    if COMPOSITE_SHEET_NAME in workbook.sheetnames:
        del workbook[COMPOSITE_SHEET_NAME]
    ws = workbook.create_sheet(COMPOSITE_SHEET_NAME)
    ws.append(
        [
            "composite_type",
            "composite_key",
            "composite_status",
            "roles",
            "derived_metric",
            "value_count",
            "reason",
            "publish_eligible",
        ]
    )
    for row in rows:
        ws.append(
            [
                row["composite_type"],
                row["composite_key"],
                row["composite_status"],
                ",".join(row.get("roles", [])),
                row.get("derived_metric") or "",
                row.get("value_count") or "",
                row.get("reason") or "",
                "是" if row.get("publish_eligible") else "否",
            ]
        )


def _write_tags(ws, records: list[dict], tag_meta: dict[int, dict]) -> None:
    headers = [str(c.value or "").strip() for c in ws[1]]
    tags_idx = None
    for idx, header in enumerate(headers):
        if header == "指标标签":
            tags_idx = idx
            break
    if tags_idx is None:
        return
    for rec in records:
        meta = tag_meta.get(id(rec))
        if not meta:
            continue
        tags = rec.get("tags") or {}
        tags["composite"] = meta
        ws.cell(row=rec["_row_idx"], column=tags_idx + 1).value = json.dumps(tags, ensure_ascii=False)


def run_composite_on_workbook(
    wb, report_path: Path | None = None, input_label: str = "", output_label: str = ""
) -> dict:
    """在已加载的 wb 上执行复合指标计算（共享 wb，不 load/save）。

    供合并链（workflow_merged_stage.py）复用；run_composite_stage 包装
    load/save。返回 report dict（stats + groups）。
    """
    ws = wb.worksheets[0]
    records = load_records(ws)

    market_groups = _build_market_groups(records)
    trade_groups = _build_trade_groups(records)
    balance_groups = _build_balance_groups(records)

    tag_meta: dict[int, dict] = {}
    derived_rows: list[dict] = []
    stats = {
        "market_activity_candidate_groups": len(market_groups),
        "market_activity_complete": 0,
        "market_activity_incomplete": 0,
        "market_activity_ambiguous": 0,
        "trade_candidate_groups": len(trade_groups),
        "trade_complete": 0,
        "trade_incomplete": 0,
        "trade_ambiguous": 0,
        "balance_groups": len(balance_groups),
        "balance_complete": 0,
        "balance_incomplete": 0,
    }

    for key, group in market_groups.items():
        vols = group["volume"]
        ois = group["open_interest"]
        roles = ["volume"] * len(vols) + ["open_interest"] * len(ois)
        if len(vols) > 1 or len(ois) > 1:
            status = "AMBIGUOUS"
            reason = "same market_activity key matched multiple volume/open_interest rows"
            ratio = []
            reasons = []
        elif not vols or not ois:
            status = "INCOMPLETE"
            reason = "missing volume or open_interest"
            stats["market_activity_incomplete"] += 1
            ratio = []
            reasons = []
        else:
            ratio, reasons = _ratio_series(wb, vols[0], ois[0])
            status = "MATCHED"
            reason = "volume/open_interest matched; oi_volume_ratio=" + ("computed" if ratio else "missing")
            stats["market_activity_complete"] += 1
        if status == "AMBIGUOUS":
            stats["market_activity_ambiguous"] += 1
        derived_rows.append(
            {
                "composite_type": "market_activity",
                "composite_key": key,
                "composite_status": status,
                "roles": ["volume", "open_interest", "oi_volume_ratio"],
                "derived_metric": "oi_volume_ratio" if status == "MATCHED" else "",
                "value_count": len(ratio) if status == "MATCHED" else 0,
                "reason": ";".join(reasons[:5]) or reason,
                "publish_eligible": status == "MATCHED" and bool(ratio) and not reasons,
            }
        )
        meta = {
            "composite_type": "market_activity",
            "composite_key": key,
            "composite_role": roles[0] if len(roles) == 1 else "mixed",
            "composite_status": status,
            "composite_reason": reason,
        }
        ratios = group["oi_volume_ratio"]
        for rec in vols + ois + ratios:
            rec_meta = dict(meta)
            if rec in vols:
                rec_meta["composite_role"] = "volume"
            elif rec in ois:
                rec_meta["composite_role"] = "open_interest"
            else:
                rec_meta["composite_role"] = "oi_volume_ratio"
            tag_meta[id(rec)] = rec_meta

    for key, group in trade_groups.items():
        imports = group["import"]
        exports = group["export"]
        nets = group["net_export"]
        roles = ["import"] * len(imports) + ["export"] * len(exports) + ["net_export"] * len(nets)
        if len(imports) > 1 or len(exports) > 1:
            status = "AMBIGUOUS"
            reason = "same trade key matched multiple import/export rows"
            computed = []
            reconciliation = "OK"
            stats["trade_ambiguous"] += 1
        elif not imports or not exports:
            status = "INCOMPLETE"
            reason = "missing import or export"
            computed = []
            reconciliation = "OK"
            stats["trade_incomplete"] += 1
        else:
            computed = compute_net_series(
                wb,
                imports[0]["sheet"],
                imports[0]["col"],
                exports[0]["sheet"],
                exports[0]["col"],
            )
            source = (
                _series(wb, nets[0]["sheet"], nets[0]["col"]) if nets else {}
            )
            source_items = [{"date": k, "value": v} for k, v in source.items()]
            reconciliation = _reconcile_net(computed, source_items)
            status = "MATCHED"
            reason = f"import/export matched; net_export={reconciliation}"
            stats["trade_complete"] += 1
        derived_rows.append(
            {
                "composite_type": "trade",
                "composite_key": key,
                "composite_status": status,
                "roles": ["import", "export", "net_export"],
                "derived_metric": "net_export" if status == "MATCHED" else "",
                "value_count": len(computed) if status == "MATCHED" else 0,
                "reason": reason,
                "publish_eligible": status == "MATCHED",
            }
        )
        meta = {
            "composite_type": "trade",
            "composite_key": key,
            "composite_role": roles[0] if len(roles) == 1 else "mixed",
            "composite_status": status,
            "composite_reason": reason,
        }
        for rec in imports + exports + nets:
            rec_meta = dict(meta)
            rec_meta["composite_role"] = (
                "import" if rec in imports else "export" if rec in exports else "net_export"
            )
            tag_meta[id(rec)] = rec_meta

    for key, roles_dict in balance_groups.items():
        roles = list(roles_dict)
        expected = {"production", "import", "export", "demand", "balance"}
        if len(roles) != len(set(roles)) or any(len(v) > 1 for v in roles_dict.values()):
            status = "AMBIGUOUS"
            reason = "duplicate balance role"
        elif expected.issubset(roles):
            status = "MATCHED"
            reason = "balance roles identified"
            stats["balance_complete"] += 1
        else:
            status = "INCOMPLETE"
            reason = f"missing balance roles: {sorted(expected - set(roles))}"
            stats["balance_incomplete"] += 1
        derived_rows.append(
            {
                "composite_type": "balance",
                "composite_key": key,
                "composite_status": status,
                "roles": roles,
                "derived_metric": "",
                "value_count": 0,
                "reason": reason,
                "publish_eligible": status == "MATCHED",
            }
        )
        meta = {
            "composite_type": "balance",
            "composite_key": key,
            "composite_role": "mixed",
            "composite_status": status,
            "composite_reason": reason,
        }
        for role, recs in roles_dict.items():
            for rec in recs:
                rec_meta = dict(meta)
                rec_meta["composite_role"] = role
                tag_meta[id(rec)] = rec_meta

    _write_composite_sheet(wb, derived_rows)
    _write_tags(ws, records, tag_meta)

    report = {
        "stage": "composite_metric_stage",
        "input": input_label,
        "output": output_label,
        "stats": stats,
        "groups": derived_rows,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def run_composite_stage(input_path: Path, output_path: Path, report_path: Path | None = None) -> dict:
    input_path = Path(input_path)
    output_path = Path(output_path)
    same_path = input_path.resolve() == output_path.resolve()
    working = output_path
    if same_path:
        working = output_path.with_name(f"{output_path.stem}__composite_tmp.xlsx")
    shutil.copy2(input_path, working)

    wb = load_workbook(working)
    try:
        report = run_composite_on_workbook(
            wb,
            report_path=report_path,
            input_label=str(input_path),
            output_label=str(output_path),
        )
    finally:
        wb.save(working)
        wb.close()
    if same_path:
        working.replace(output_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Composite Metric Stage.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else input_path
    report_path = Path(args.report).resolve() if args.report else None
    run_composite_stage(input_path, output_path, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
