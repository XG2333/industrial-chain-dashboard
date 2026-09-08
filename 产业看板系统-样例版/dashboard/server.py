"""Market dashboard API server."""
from __future__ import annotations

import ast
import asyncio
import gzip
import json
import pickle
import logging
import os
import re
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from curl_cffi import requests as crequests
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(str(PROJECT_ROOT / ".env"))
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_VERSION = 6
TIN_WORKBOOK_PATH = PROJECT_ROOT / "data" / "锡产业链数据_workflow_ai.xlsx"
SILICON_WORKBOOK_PATH = PROJECT_ROOT / "data" / "硅产业链数据_workflow_ai.xlsx"
LITHIUM_WORKBOOK_PATH = PROJECT_ROOT / "data" / "碳酸锂数据库_workflow_ai.xlsx"
STOCK_TARGETS_DIR = Path(os.getenv("STOCK_TARGETS_DIR") or (PROJECT_ROOT / "data" / "stock_targets"))
STOCK_TARGET_FILES = {
    "silicon": "个股标的_硅.xlsx",
    "tin": "个股标的_锡.xlsx",
    "lithium": "个股标的_锂电.xlsx",
}
# 锂电个股"人工清单"模式：该文件存在时锂电个股不再读 Excel(个股标的_锂电.xlsx)，
# 改用 manual_lithium.json(人工维护, 与 Excel 同字段)。锡/硅保持读 Excel。
MANUAL_STOCK_FILE_LITHIUM = STOCK_TARGETS_DIR / "manual_lithium.json"


def _read_published_source_paths() -> dict[str, str]:
    """Read source workbook paths from Workflow's current.json, if configured."""
    configured = os.getenv("WORKFLOW_CURRENT_PATH", "").strip()
    if not configured:
        return {}
    try:
        payload = json.loads(Path(configured).read_text(encoding="utf-8"))
    except Exception:
        logger.warning("published current.json could not be read: %s", configured)
        return {}

    source_files = payload.get("source_files")
    if isinstance(source_files, dict):
        return {
            str(source): str(path)
            for source, path in source_files.items()
            if source and path
        }
    dashboard_path = payload.get("dashboard_data_path")
    industry = payload.get("industry")
    if dashboard_path and industry:
        return {str(industry): str(dashboard_path)}
    return {}


def _detect_industry(tab: str, referer: str = "") -> str:
    text = f"{referer} {tab}"
    if "/silicon" in referer or any(
        keyword in text
        for keyword in ("工业硅", "有机硅", "多晶硅", "硅片", "电池片", "组件", "光伏辅材", "铝合金")
    ):
        return "silicon"
    if "/tin" in referer or any(
        keyword in text
        for keyword in ("锡矿", "锡锭", "锡材", "锡下游", "锡其他")
    ):
        return "tin"
    if "/battery" in referer or any(
        keyword in text
        for keyword in ("锂", "三元", "磷酸铁锂", "负极", "电解液", "隔膜", "铜箔", "储能", "新能源车")
    ):
        return "lithium"
    return "lithium"


class StockBrief(BaseModel):
    code: str = ""
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0


class BatteryAnalyzeRequest(BaseModel):
    tab: str = Field(..., description="")
    stocks: list[StockBrief] = Field(default_factory=list)
    industry: str | None = None


class SectorQuickAnalysisRequest(BaseModel):
    """速评：输入对象名与紧凑数据摘要行（前端已取样并控制数量），
    基于指标/仓单数据（最新值/日周环比/近期走势）生成简洁点评。
    kind = metrics（板块指标速评，默认） | warehouse（仓单日报速评）"""
    industry: str | None = None
    sector: str = Field(..., description="分析对象名，如：锂矿 / 锡矿 / 工业硅 / 仓单日报")
    metrics_text: str = Field(..., description="数据摘要行文本（每行一个对象）")
    kind: str = "metrics"


class ReportRequest(BaseModel):
    tab: str = Field(..., description="")
    stocks: list[str] = Field(default_factory=list)


class ExcelRequest(BaseModel):
    tab: str = Field(..., description="")
    sector: str | None = None
    confidence: float | None = None
    dataset: str | None = None
    # 只返回目录"是否选中"列为"是"的指标（总览页数据源过滤）
    selected_only: bool = False


class ChartBatchRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)


class MarketDataRequest(BaseModel):
    stocks: list[str] = Field(default_factory=list)


class FinancialsRequest(BaseModel):
    stocks: list[str] = Field(default_factory=list)


class WatchlistRequest(BaseModel):
    stocks: list[str] = Field(default_factory=list)
    sparkline: bool = Field(default=True)


app = FastAPI(title="market dashboard API", version="0.1.0")
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=1000)

_excel_cache = {}
_DATA_LOAD_EVENT = threading.Event()


def _classify_category(title):
    if any(kw in title for kw in ("基差", "月差", "期现")):
        return "一、价格"
    if any(kw in title for kw in ("成交量", "持仓量", "成交金额", "成交额", "换手")):
        return "五、量价"
    if any(kw in title for kw in ("仓单", "库存", "显性", "仓库", "注册仓单", "注销仓单")):
        return "三、供需-库存"
    if any(kw in title for kw in ("进口", "出口", "进出口")):
        return "三、供需-进出口"
    if any(kw in title for kw in ("产量", "开工", "产能", "供应")):
        return "二、供需-供应"
    if any(kw in title for kw in ("消费量", "需求", "表观")):
        return "二、供需-需求"
    if any(kw in title for kw in ("成本", "利润", "盈亏")):
        return "四、成本利润"
    return "其他"


# ── 仓单只画总量/小计：分仓库、分地区等明细行不在看板显示 ──
# 广期所/上期所仓单日报按仓库拆分的明细行（"仓单日报分仓库: 中储无锡: 今日仓单量"
# 等）与总量行（"仓单日报:今日仓单量"、碳酸锂"碳酸锂小计"）一起进入目录表时，
# 看板只保留总量/小计行。非仓单类指标不受影响。
_WR_TOTAL_WORDS = ("小计", "合计", "总计")
_WR_DETAIL_WORDS = ("分仓库", "分地区")


def _keep_warehouse_receipt_total(title: str) -> bool:
    """仓单类指标是否保留：仅保留总量/小计行，过滤分仓库明细行。"""
    t = str(title or "")
    if "仓单" not in t:
        return True
    if any(w in t for w in _WR_TOTAL_WORDS):
        return True
    # 广期所仓单日报总量行（"GFEX: 工业硅: 仓单日报:今日仓单量: 日度"）
    if (
        "仓单日报" in t
        and "今日仓单量" in t
        and not any(w in t for w in _WR_DETAIL_WORDS)
    ):
        return True
    return False


# ── 分仓库仓单表格（看板行业数据开头以表格展示分仓库仓单，折线图仍只画总量） ──
# 表格每行一个仓库：仓库地区 | 品种 | 近 7 个交易日数据 | 日/周/月环比 | 日/周/月环比率
_WAREHOUSE_RECENT_DAYS = 7
_WAREHOUSE_WEEK_OFFSET = 5   # 周环比 = 最新 vs 5 个交易日前
_WAREHOUSE_MONTH_OFFSET = 21  # 月环比 = 最新 vs 21 个交易日前（约一个月）

# 仓库地区词表 → 省份（从仓库名匹配第一个地名，再映射到省份；括号内容优先）
_WAREHOUSE_REGION_MAP = {
    "上海": "上海", "临港": "上海", "宝山": "上海", "吴淞": "上海", "大场": "上海",
    "无锡": "江苏", "镇江": "江苏", "常州": "江苏", "苏州": "江苏", "南京": "江苏",
    "南昌": "江西", "宜春": "江西", "九江": "江西", "宜丰": "江西",
    "遂宁": "四川", "成都": "四川", "龙泉驿": "四川", "新都": "四川", "青白江": "四川",
    "包头": "内蒙古", "天津": "天津", "泰达": "天津", "东丽": "天津", "西青": "天津",
    "滨海": "天津", "新港": "天津", "广州": "广东", "佛山": "广东", "青岛": "山东",
    "昆明": "云南", "石河子": "新疆", "乌鲁木齐": "新疆", "昌吉": "新疆", "新疆": "新疆",
    "盐湖": "青海", "郑州": "河南", "杭州": "浙江", "宁波": "浙江", "东莞": "广东",
    "三工镇": "新疆", "天齐": "四川",
    # 广期所交割仓库公司名（已核实所在省份）：
    # 四川天华时代锂能(眉山)、遂宁天诚高新物流、融捷投资控股集团(成都邛崃)、江西永兴特钢新能源(宜春宜丰)
    "天华": "四川", "天诚": "四川", "融捷": "四川", "永兴": "江西",
    "深圳": "广东", "长沙": "湖南", "武汉": "湖北", "宜昌": "湖北", "曹安": "上海",
    "张华浜": "上海", "江苏": "江苏", "广东": "广东", "江西": "江西", "四川": "四川",
    "青海": "青海", "山东": "山东", "云南": "云南", "河南": "河南", "浙江": "浙江",
    "内蒙古": "内蒙古", "新疆": "新疆", "湖北": "湖北", "湖南": "湖南", "安徽": "安徽",
    "中国香港": "中国香港", "新加坡": "新加坡", "柔佛": "马来西亚", "釜山": "韩国",
    "光阳": "韩国", "鹿特丹": "荷兰", "热那亚": "意大利", "安特卫普": "比利时",
    "巴尔的摩": "美国", "圣路易斯": "美国", "长滩": "美国", "洛杉矶": "美国",
    "底特律": "美国", "赫尔辛堡": "瑞典", "新奥尔良": "美国",
}
_WAREHOUSE_TITLES = {
    "lithium": "碳酸锂仓单日报",
    "silicon": "硅仓单日报",
    "tin": "锡仓单日报",
}

_WAREHOUSE_PRODUCTS = ("碳酸锂", "氢氧化锂", "工业硅", "多晶硅", "锡")


def _extract_region(warehouse: str) -> str:
    """从仓库名提取省份地区：括号内内容优先，再全文匹配最靠后的地名并映射到省份。

    仓库名常以地区结尾（如"国贸泰达昆明"→昆明而非泰达），取最后命中的地名更准确。
    """
    text = str(warehouse or "")
    m = re.search(r"[（(]([^）)]+)[）)]", text)
    parts = [m.group(1), text] if m else [text]
    for part in parts:
        best: tuple[int, str] | None = None
        for word, province in _WAREHOUSE_REGION_MAP.items():
            idx = part.find(word)
            if idx >= 0 and (best is None or idx > best[0]):
                best = (idx, province)
        if best is not None:
            return best[1]
    return ""


def _trim_warehouse_tail(text: str) -> str:
    """去掉仓库名尾部的指标后缀（": 今日仓单量: 日度"、": 期货: 日" 等）。"""
    s = re.sub(r"\s*[:：]\s*今日仓单量(?:\s*[:：]\s*日(?:度)?)?\s*$", "", text)
    s = re.sub(r"\s*[:：]\s*期货(?:\s*[:：]\s*日(?:度)?)?\s*$", "", s)
    s = re.sub(r"\s*[:：]\s*日(?:度)?\s*$", "", s)
    return s.strip(" :：_")


def _extract_warehouse_name(title: str) -> str:
    """从仓单列标题提取仓库名（含多晶硅"仓库: 厂商"两级结构）。

    兼容两种指标后缀：广期所"…: 今日仓单量: 日度"与上期所"…: 期货: 日"。
    """
    t = str(title or "")
    m = re.search(r"分仓库[_:：]?\s*(.+?)\s*$", t)
    if m:
        return _trim_warehouse_tail(m.group(1))
    m = re.search(r"广期日库存[:：]?\s*[^:：]+[:：]\s*(.+?)\s*$", t)
    if m:
        return _trim_warehouse_tail(m.group(1))
    m = re.search(r"显性库存[_:]\s*([^_丨:：]+?)\s*[丨]\s*(注册|注销)仓单", t)
    if m:
        return f"{m.group(1).strip(' :：_')}（LME {m.group(2)}）"
    m = re.search(r"显性库存[:：]\s*([^:：]+)[:：]\s*(?:注册|注销)仓单", t)
    if m:
        return m.group(1).strip(" :：_") + "（LME）"
    return t.strip(" :：_")


def _warehouse_product(title: str) -> str:
    for p in _WAREHOUSE_PRODUCTS:
        if p in title:
            return p
    return ""


_WAREHOUSE_TON_PER_LOT = {"lithium": 1, "silicon": 5, "tin": 1}
# 分仓库仓单折线图数据点数（表格内每 4 行仓库下方插入对应指标图）
_WAREHOUSE_CHART_POINTS = 90
# 地区汇总行顺序（图片顺序；其余地区按出现顺序追加）
_WAREHOUSE_REGION_ORDER = [
    "上海", "江苏", "江西", "四川", "青海", "广东", "山东", "云南", "天津",
    "新疆", "内蒙古", "浙江", "河南", "湖北", "湖南", "安徽",
]
_SUMMARY_SERIES_LEN = _WAREHOUSE_MONTH_OFFSET + 2  # 汇总/量价行原始序列取前 N 位（覆盖月环比基准）


def _series_changes(values: list) -> tuple:
    """从降序原始序列计算 日/周/月环比与环比率（values 元素可为 None）。"""
    latest = next((v for v in values if v is not None), None)
    d_chg = d_rate = w_chg = w_rate = m_chg = m_rate = None
    if latest is not None:
        d_base = values[1] if len(values) > 1 else None
        w_base = values[_WAREHOUSE_WEEK_OFFSET] if len(values) > _WAREHOUSE_WEEK_OFFSET else None
        m_base = values[_WAREHOUSE_MONTH_OFFSET] if len(values) > _WAREHOUSE_MONTH_OFFSET else None
        for base, chg_box, rate_box in (
            (d_base, "d", "d"), (w_base, "w", "w"), (m_base, "m", "m"),
        ):
            if base is None:
                continue
            chg = round(latest - base, 2)
            rate = round(chg / base * 100, 2) if base else None
            if chg_box == "d":
                d_chg, d_rate = chg, rate
            elif chg_box == "w":
                w_chg, w_rate = chg, rate
            else:
                m_chg, m_rate = chg, rate
    return d_chg, d_rate, w_chg, w_rate, m_chg, m_rate


def _row_payload(kind: str, warehouse: str, region: str, product: str, series_dates: list, series: list, table_dates: list) -> dict:
    """把原始序列转成表格行：近 2 日值 + 环比/环比率（series 按日期对齐）。"""
    val_by_date = {d: v for d, v in zip(series_dates, series) if v is not None}
    recent = [val_by_date.get(dt) for dt in table_dates]
    d_chg, d_rate, w_chg, w_rate, m_chg, m_rate = _series_changes(series)
    row = {
        "kind": kind,
        "warehouse": warehouse,
        "region": region,
        "product": product,
        "values": recent,
        "daily_change": d_chg,
        "weekly_change": w_chg,
        "monthly_change": m_chg,
        "daily_rate": d_rate,
        "weekly_rate": w_rate,
        "monthly_rate": m_rate,
    }
    # 所有行（仓库明细/地区汇总/全国/量价）都附带近 N 个数据点，
    # 供表格右侧走势图渲染（地区汇总/全国为 22 点汇总窗口，量价行为原始序列）
    row["series"] = [
        {"date": d, "value": v}
        for d, v in zip(series_dates[:_WAREHOUSE_CHART_POINTS], series[:_WAREHOUSE_CHART_POINTS])
        if v is not None
    ]
    return row


def _load_warehouse_table(source: str) -> dict:
    """加载某行业的分仓库仓单表格数据。

    DEMO 模式: 返回内存演示仓单(不打码仓库名 A-H, 不读真实 Excel)。
    """
    if DEMO_MODE:
        return _demo_warehouse_table(source)
    """加载某行业的分仓库仓单表格数据。

    行结构（与参考样式一致）：
    - 仓库明细行（kind=warehouse）
    - 地区汇总行（kind=region，如"上海仓单量"）
    - 全国仓单量/折吨（kind=total）
    - 成交量/持仓量/成交持仓比（kind=metric，主力合约）
    """
    published = _read_published_source_paths()
    fallbacks = {"tin": TIN_WORKBOOK_PATH, "silicon": SILICON_WORKBOOK_PATH, "lithium": LITHIUM_WORKBOOK_PATH}
    filepath = _source_workbook_path(published, source, fallbacks[source])
    if not filepath.exists():
        return {"dates": [], "rows": [], "title": ""}
    import pandas as pd

    wh_candidates: list[tuple[str, int, str, int]] = []
    metric_candidates: list[tuple[str, int, str, int]] = []
    all_date_set: set[str] = set()
    seen_lme: set[tuple[str, str]] = set()
    xl = pd.ExcelFile(filepath, engine="openpyxl")
    try:
        for sn in xl.sheet_names:
            if sn in ("指标目录", "目录"):
                continue
            d = pd.read_excel(xl, sheet_name=sn, header=None)
            if d.shape[0] < 4 or d.shape[1] < 2:
                continue
            # 指标名称行：前几行中列 0 为"指标名称"的行
            #（碳酸锂在 iloc[1]，硅/锡在 iloc[0]，结构不同）；数据行 = 名称行 + 3
            name_row = None
            for r in range(min(4, d.shape[0])):
                if str(d.iloc[r, 0]).strip() == "指标名称":
                    name_row = r
                    break
            if name_row is None:
                name_row = 1
            data_start = name_row + 3
            header = [str(v) if v is not None else "" for v in d.iloc[name_row]]
            sheet_dates: list[str] = []
            for col, h in enumerate(header):
                if "仓单" in h and "增减" not in h:
                    if not _keep_warehouse_receipt_total(h) and any(
                        k in h for k in ("分仓库", "显性库存", "广期日库存")
                    ):
                        # LME 显性库存存在"冒号/下划线"两套同数据列，按(地区, 类型)去重
                        m_lme = re.search(
                            r"显性库存[_:]\s*([^_丨:：]+?)\s*[丨]\s*(注册|注销)仓单", h
                        ) or re.search(
                            r"显性库存[:：]\s*([^:：]+)[:：]\s*(注册|注销)仓单", h
                        )
                        if m_lme:
                            lme_key = (m_lme.group(1).strip(" :：_"), m_lme.group(2))
                            if lme_key in seen_lme:
                                continue
                            seen_lme.add(lme_key)
                        # 分仓库/分地区明细行（总量/小计折线图已画，表格只收明细）
                        wh_candidates.append((sn, col, h, data_start))
                    if not sheet_dates:
                        raw_dates = pd.to_datetime(d.iloc[data_start:, 0], errors="coerce").tolist()
                        sheet_dates = [str(x.date()) for x in raw_dates if x is not None and pd.notna(x)]
                        all_date_set.update(sheet_dates)
                if "主力合约" in h and any(k in h for k in ("成交量", "持仓量", "成交持仓比")):
                    metric_candidates.append((sn, col, h, data_start))
        if not wh_candidates or not all_date_set:
            return {"dates": [], "rows": [], "title": _WAREHOUSE_TITLES.get(source, "")}
        # 表格列 = 全局最近 7 个数据点（各 sheet 数据日期可能不同步）
        table_dates = sorted(all_date_set, reverse=True)[: _WAREHOUSE_RECENT_DAYS]

        def _read_series(sn: str, col: int, data_start: int) -> tuple[list, list]:
            """读取一列数据，返回 (日期字符串列表, 值列表)，按行过滤无效日期。"""
            d = pd.read_excel(xl, sheet_name=sn, header=None)
            raw_dates = pd.to_datetime(d.iloc[data_start:, 0], errors="coerce").tolist()
            raw_vals = pd.to_numeric(d.iloc[data_start:, col], errors="coerce").tolist()
            out_dates, out_vals = [], []
            for dt, v in zip(raw_dates, raw_vals):
                if dt is not None and pd.notna(dt):
                    out_dates.append(str(dt.date()))
                    out_vals.append(None if pd.isna(v) else float(v))
            return out_dates, out_vals

        rows = []
        # 汇总窗口 = 全局最近 22 个交易日（覆盖月环比基准），按日期累加
        # 初始为 None 区分"数据缺失"与"真 0"；累加时 None 视为 0
        window_dates = sorted(all_date_set, reverse=True)[: _SUMMARY_SERIES_LEN]
        total_by_date = {d: None for d in window_dates}
        region_by_date: dict[str, dict] = {}
        for sn, col, h, data_start in wh_candidates:
            s_dates, series = _read_series(sn, col, data_start)
            name = _extract_warehouse_name(h)
            region = _extract_region(name)
            rows.append(_row_payload("warehouse", name, region, _warehouse_product(h), s_dates, series, table_dates))
            for d, v in zip(s_dates, series):
                if v is None or d not in total_by_date:
                    continue
                total_by_date[d] = (total_by_date[d] or 0.0) + v
                if region:
                    acc = region_by_date.setdefault(region, {dd: None for dd in window_dates})
                    if d in acc:
                        acc[d] = (acc[d] or 0.0) + v

        # 仓库行按地区排序：图片顺序（上海/江苏/江西/四川/青海）优先，
        # 其余地区按出现顺序，未识别地区排在最后（保持目录顺序）
        _region_rank = {r: i for i, r in enumerate(_WAREHOUSE_REGION_ORDER)}
        warehouse_rows = [r for r in rows if r["kind"] == "warehouse"]
        warehouse_rows.sort(key=lambda r: (
            _region_rank.get(r["region"], 1000 + len(_region_rank)),
            0 if r["region"] else 1,
            r["warehouse"],
        ))
        rows = warehouse_rows + [r for r in rows if r["kind"] != "warehouse"]

        # 地区汇总行（图片顺序；其余地区按出现顺序）
        region_order = [r for r in _WAREHOUSE_REGION_ORDER if r in region_by_date]
        region_order += [r for r in region_by_date if r not in region_order]
        for r in region_order:
            series = [region_by_date[r][d] for d in window_dates]
            rows.append(_row_payload("region", f"{r}仓单量", "", "", window_dates, series, table_dates))

        # 全国仓单量 + 折吨（手 → 吨）
        total_series = [total_by_date[d] for d in window_dates]
        rows.append(_row_payload("total", "全国仓单量", "", "", window_dates, total_series, table_dates))
        tons = _WAREHOUSE_TON_PER_LOT.get(source, 1)
        if tons != 1:
            rows.append(_row_payload(
                "total", "全国仓单折吨", "", "", window_dates,
                [v * tons if v is not None else None for v in total_series], table_dates,
            ))

        # 成交量 / 持仓量 / 成交持仓比（主力合约，按日期对齐）
        vol_dates = oi_dates = vol_series = oi_series = None
        for sn, col, h, data_start in metric_candidates:
            if "成交量" in h and "持仓量" not in h and vol_series is None:
                vol_dates, vol_series = _read_series(sn, col, data_start)
            elif "持仓量" in h and "成交量" not in h and oi_series is None:
                oi_dates, oi_series = _read_series(sn, col, data_start)
        if vol_series is not None:
            rows.append(_row_payload("metric", "成交量", "", "", vol_dates, vol_series, table_dates))
        if oi_series is not None:
            rows.append(_row_payload("metric", "持仓量", "", "", oi_dates, oi_series, table_dates))
        if vol_series is not None and oi_series is not None:
            vol_by_date = dict(zip(vol_dates, vol_series))
            oi_by_date = dict(zip(oi_dates, oi_series))
            ratio_series = [
                round(vol_by_date[d] / oi_by_date[d], 2) if vol_by_date.get(d) is not None and oi_by_date.get(d) else None
                for d in window_dates
            ]
            rows.append(_row_payload("metric", "成交持仓比", "", "", window_dates, ratio_series, table_dates))

        return {
            "dates": table_dates,
            "rows": rows,
            "title": _WAREHOUSE_TITLES.get(source, ""),
        }
    finally:
        xl.close()


@app.get("/api/warehouse-table")
async def warehouse_table(dataset: str = ""):
    """分仓库仓单表格：每行一个仓库（近 5 交易日数据 + 日/周/月环比与环比率）。"""
    await _wait_excel_ready()
    if dataset not in ("lithium", "tin", "silicon"):
        return JSONResponse(content={"dates": [], "rows": []})
    return JSONResponse(content=_load_warehouse_table(dataset))


# ── 仓单日报 · 公开 API 数据源(交易所/东财; 前端可切换, 默认仍为本地 Excel)──
# 锂/硅 = 广期所官网仓单日报(仓库级); 锡 = 东财仓单(仅全国总量, 无仓库级免费源)。
_WR_GFEX_URL = "http://www.gfex.com.cn/u/interfacesWebTdWbillWeeklyQuotes/loadList"
_WR_GFEX_VARIETIES = {"lithium": {"碳酸锂"}, "silicon": {"多晶硅", "工业硅"}, "tin": set()}
# 公开 API 仓单地区识别: 交易所仓库名多为"主体+地名", 按关键词归属到省(与本地 Excel 地区列口径一致)。
_WR_REGION_RULES = [
    ("上海", ["上海", "临港", "吴淞", "洋山", "外高桥", "闵行", "宝山", "漕泾"]),
    ("天津", ["天津", "滨海", "东丽", "西青", "新港", "北辰", "陆通"]),
    ("江苏", ["镇江", "常州", "无锡", "南通", "苏州", "奔牛", "连云港", "靖江", "江阴", "张家港", "淮安"]),
    ("江西", ["南昌", "宜春", "奉新", "宜丰", "赣州", "九江", "上饶", "永兴材料"]),
    ("四川", ["成都", "龙泉驿", "双流", "青白江", "绵阳", "眉山", "雅化", "天华", "融捷", "新津", "遂宁", "宜宾"]),
    ("浙江", ["杭州", "宁波", "嘉兴", "温州", "舟山", "金华", "湖州", "永兴特钢"]),
    ("新疆", ["新疆", "石河子", "乌鲁木齐", "昌吉", "准东", "奎屯", "阿拉尔", "三工"]),
    ("内蒙古", ["内蒙古", "内蒙", "包头", "呼和浩特", "赤峰", "鄂尔多斯"]),
    ("浙江", ["杭州", "宁波", "嘉兴", "温州", "舟山", "金华", "湖州"]),
    ("山东", ["青岛", "烟台", "济南", "日照", "潍坊", "临沂"]),
    ("广东", ["广东", "广州", "佛山", "深圳", "东莞", "珠海"]),
    ("湖北", ["武汉", "宜昌", "荆门", "黄石", "襄阳"]),
    ("云南", ["昆明", "大理", "曲靖", "云铝"]),
    ("河南", ["郑州", "洛阳", "焦作", "许昌", "三门峡"]),
    ("湖南", ["长沙", "株洲", "湘潭"]),
    ("安徽", ["合肥", "芜湖", "铜陵", "蚌埠"]),
    ("甘肃", ["兰州", "嘉峪关"]),
    ("福建", ["厦门", "福州", "泉州"]),
    ("陕西", ["西安", "榆林"]),
    ("青海", ["西宁", "盐湖", "格尔木"]),
    ("贵州", ["贵阳"]),
]


def _warehouse_region(name: str) -> str:
    """仓库名 → 省份(识别不到返回空, 前端显示 —)。"""
    for region, keys in _WR_REGION_RULES:
        for k in keys:
            if k in name:
                return region
    return ""

_WR_LIVE_TTL = 1800.0
_WR_LIVE_CACHE: dict[str, tuple[float, dict]] = {}


def _numv(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _prev_trade_day8(base: str, back: int) -> str:
    """base(YYYY-MM-DD) 向前 back 天后跳过周末 → YYYYMMDD。"""
    from datetime import date, timedelta
    d = date.fromisoformat(base) - timedelta(days=back)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def _load_warehouse_live(dataset: str) -> dict:
    """公开 API 仓单(当日, 无历史/走势): dates=[日期], rows 结构兼容前端仓单表。"""
    now_t = time.time()
    cached = _WR_LIVE_CACHE.get(dataset)
    if cached and now_t - cached[0] < _WR_LIVE_TTL:
        return cached[1]
    result: dict = {"dates": [], "rows": []}
    try:
        if dataset in ("lithium", "silicon"):
            result = _gfex_warehouse_live(dataset)
        elif dataset == "tin":
            result = _em_tin_warehouse_live()
    except Exception as e:  # noqa: BLE001
        logger.warning("warehouse live fail (%s): %s", dataset, e)
    _WR_LIVE_CACHE[dataset] = (now_t, result)
    return result


def _gfex_fetch_day(date8: str):
    """拉取某交易日 gfex 仓单原始行; 失败/空返回 None。"""
    import urllib.parse
    try:
        payload = urllib.parse.urlencode({"gen_date": date8}).encode()
        req = urllib.request.Request(
            _WR_GFEX_URL, data=payload,
            headers={"User-Agent": "Mozilla/5.0",
                     "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode("utf-8", errors="replace"))
        rows = j.get("data") or []
        return rows if len(rows) >= 2 else None
    except Exception:  # noqa: BLE001
        return None


def _parse_gfex_day(rows: list, want: set):
    """单日行解析: 同仓库多行(商标)合并 → (仓库合并, 品种小计, 全国总计, 仓库顺序)。"""
    merged: dict[str, dict] = {}
    order: list[str] = []
    subtotal: dict[str, dict] = {}
    total: dict | None = None
    for r in rows:
        variety = str(r.get("variety") or "")
        wh = str(r.get("whAbbr") or "").strip()
        now_v = _numv(r.get("wbillQty"))
        diff = _numv(r.get("diff"))
        if variety == "总计" and not wh:
            total = {"now": now_v, "diff": diff}
            continue
        if not wh:  # 品种小计行(只保留本 dataset 需要的品种)
            base_var = variety[:-2] if variety.endswith("小计") else variety
            if base_var in want:
                subtotal[base_var] = {"now": now_v, "diff": diff}
            continue
        if variety not in want:
            continue
        if wh in merged:
            m = merged[wh]
            if now_v is not None:
                m["now"] = (m["now"] or 0) + now_v
            if diff is not None:
                m["diff"] = (m["diff"] or 0) + diff
        else:
            order.append(wh)
            merged[wh] = {"now": now_v, "diff": diff, "product": variety}
    return merged, subtotal, total, order


_WR_HIST_DAYS = 30       # 逐日补抓的交易日数(覆盖月环比 21 交易日基准 + 走势)
_WR_WEEK_OFF = 5         # 周环比基准偏移(与 Excel 口径一致: 最新 vs 前5交易日)
_WR_MONTH_OFF = 21       # 月环比基准偏移
_WR_SERIES_POINTS = 60   # 走势输出点数上限


def _wr_hist_path(dataset: str) -> Path:
    return CACHE_DIR / f"wr_live_hist_{dataset}.json"


def _load_wr_hist(dataset: str) -> dict | None:
    try:
        p = _wr_hist_path(dataset)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return None


def _save_wr_hist(dataset: str, hist: dict):
    try:
        _wr_hist_path(dataset).write_text(
            json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _ensure_gfex_history(dataset: str) -> dict | None:
    """逐日补抓近 _WR_HIST_DAYS 个交易日(gfex 单日快照→本地历史), 返回 hist 或 None。

    hist = {"dates": [d1..dn](降序, 最新在前), "wh": {仓库: {"product", "vals": [...]}},
            "sub": {品种: {"vals": [...]}}, "tot": [...]}; vals 与 dates 尾部对齐。
    """
    want = _WR_GFEX_VARIETIES[dataset]
    hist = _load_wr_hist(dataset) or {"dates": [], "wh": {}, "sub": {}, "tot": []}
    have = set(hist["dates"])
    base = time.strftime("%Y-%m-%d")
    lt = time.localtime()
    released_today = not (lt.tm_hour < 15 or (lt.tm_hour == 15 and lt.tm_min < 30))
    # 候选(近→远), 只补缺失
    need = []
    idx = 0
    while len(need) + len(have) < _WR_HIST_DAYS and idx < 60:
        d8 = _prev_trade_day8(base, (0 if released_today else 1) + idx)
        if d8 not in have:
            need.append(d8)
        idx += 1
    # 远→近抓取, 每次在头部插入(保持 dates 最新在前)
    for d8 in reversed(need):
        rows = _gfex_fetch_day(d8)
        if not rows:
            continue  # 非交易日/失败: 当日不占位, 下次再补
        m, sub, tot, _ = _parse_gfex_day(rows, want)
        hist["dates"].insert(0, d8)
        for name, info in m.items():
            rec = hist["wh"].setdefault(name, {"product": info["product"], "vals": []})
            rec["vals"].insert(0, info["now"])
        for var, s in sub.items():
            rec = hist["sub"].setdefault(var, {"vals": []})
            rec["vals"].insert(0, s["now"])
        if tot is not None:
            hist["tot"].insert(0, tot["now"])
    # 修剪到窗口
    if len(hist["dates"]) > _WR_HIST_DAYS:
        keep = _WR_HIST_DAYS
        hist["dates"] = hist["dates"][:keep]
        for rec in list(hist["wh"].values()) + list(hist["sub"].values()):
            rec["vals"] = rec["vals"][:keep]
        hist["tot"] = hist["tot"][:keep]
    if hist["dates"]:
        _save_wr_hist(dataset, hist)
    return hist if hist["dates"] else None


def _compose_live_row(dates: list, vals: list, kind: str, warehouse: str, region: str, product: str, daily_change):
    """由历史序列生成仓单行(含 日/周/月环比 + series 走势, 与 Excel 行字段同构)。"""
    n = len(vals)
    aligned = dates[len(dates) - n:] if n < len(dates) else dates
    v0 = vals[0] if n else None
    vw = vals[_WR_WEEK_OFF] if n > _WR_WEEK_OFF else None
    vm = vals[_WR_MONTH_OFF] if n > _WR_MONTH_OFF else None
    chg = lambda a, b: (round(a - b, 2) if a is not None and b is not None else None)  # noqa: E731
    rate = lambda a, b: (round((a - b) / b * 100, 2) if a is not None and b else None)  # noqa: E731
    series = [
        {"date": aligned[i], "value": vals[i]}
        for i in range(min(n, _WR_SERIES_POINTS))
        if vals[i] is not None
    ]
    return {
        "kind": kind, "warehouse": warehouse, "region": region, "product": product,
        "values": [v0, vals[1] if n > 1 else None],
        "daily_change": daily_change if daily_change is not None else chg(v0, vals[1] if n > 1 else None),
        "daily_rate": rate(v0, vals[1] if n > 1 else None),
        "weekly_change": chg(v0, vw), "weekly_rate": rate(v0, vw),
        "monthly_change": chg(v0, vm), "monthly_rate": rate(v0, vm),
        "series": series,
    }


def _gfex_warehouse_live(dataset: str) -> dict:
    """广期所仓单(仓库级): 近30交易日历史 → 日/周/月环比与走势齐全。"""
    hist = _ensure_gfex_history(dataset)
    if not hist:
        return {"dates": [], "rows": []}
    dates = hist["dates"]
    fmt = lambda d8: f"{d8[:4]}-{d8[4:6]}-{d8[6:]}"  # noqa: E731
    out_dates = [fmt(d) for d in dates[:2]]
    rows_out: list[dict] = []
    for name, rec in hist["wh"].items():
        rows_out.append(_compose_live_row(
            dates, rec["vals"], "warehouse", name, _warehouse_region(name), rec.get("product", ""), None))
    for var, rec in hist["sub"].items():
        rows_out.append(_compose_live_row(
            dates, rec["vals"], "total", f"{var}合计", "", var, None))
    if hist.get("tot"):
        rows_out.append(_compose_live_row(
            dates, hist["tot"], "total", "全国仓单量", "", "", None))
    return {"dates": out_dates, "rows": rows_out}


def _em_tin_warehouse_live() -> dict:
    """东财锡仓单(全国总量): 历史序列(约70交易日) → 全国行含 环比与走势。"""
    global ak  # noqa: PLW0603
    try:
        import akshare as _ak
        ak = _ak
    except Exception as e:  # noqa: BLE001
        logger.warning("em tin warehouse: akshare unavailable: %s", e)
        return {"dates": [], "rows": []}
    try:
        df = ak.futures_inventory_em(symbol="锡")
        if len(df) == 0:
            return {"dates": [], "rows": []}
        dates = [str(d) for d in reversed(df["日期"].tolist())]  # 最新在前
        vals = [_numv(v) for v in reversed(df["库存"].tolist())]
        if len(vals) > _WR_HIST_DAYS:
            dates, vals = dates[:_WR_HIST_DAYS], vals[:_WR_HIST_DAYS]
        diff = _numv(df["增减"].iloc[-1]) if "增减" in df.columns else None
        row = _compose_live_row(dates, vals, "total", "全国仓单量", "", "锡", diff)
        return {"dates": dates[:2], "rows": [row]}
    except Exception as e:  # noqa: BLE001
        logger.warning("em tin warehouse fail: %s", e)
        return {"dates": [], "rows": []}


@app.get("/api/warehouse-table-live")
async def warehouse_table_live(dataset: str = ""):
    """仓单日报(公开 API): 交易所/东财当日仓单, 供前端切换数据源。"""
    if dataset not in ("lithium", "tin", "silicon"):
        return JSONResponse(content={"dates": [], "rows": []})
    return JSONResponse(content=_load_warehouse_live(dataset))


_FREQ_MAP = {
    "日度": "daily",
    "周度": "weekly",
    "月度": "monthly",
    "季度": "quarterly",
    "年度": "yearly",
}


class CatalogSchemaError(Exception):
    """Raised when an Excel catalog does not match a supported schema."""


CATALOG_FIELD_ALIASES = {
    "sheet": ["Sheet Name", "#"],
    "freq": ["Freq", "频率"],
    "col": ["Col", "列号"],
    "name": ["Indicator Name", "指标名称"],
    "unit": ["Unit", "单位"],
    "sector": ["板块"],
    "major": ["大类"],
    "sub": ["子类"],
    "confidence": ["置信度", "confidence", "Confidence"],
    "selected": ["是否选中"],
    "final_selected": ["二次筛选是否保留"],
    "reason": ["状态说明"],
    "tags": ["指标标签"],
}


REQUIRED_CATALOG_FIELDS = ["sheet", "freq", "col", "name"]


def _parse_tags(raw: str) -> list[dict[str, str]]:
    if not raw or raw == "nan":
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return [
                {
                    "category": str(key),
                    "value": json.dumps(item, ensure_ascii=False)
                    if isinstance(item, (dict, list))
                    else str(item),
                }
                for key, item in value.items()
                if item not in (None, "")
            ]
        if isinstance(value, list):
            return [
                {"category": "标签", "value": str(item)}
                for item in value
                if item not in (None, "")
            ]
    except Exception:
        return []
    return []


def _evaluate_ast_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        left = _evaluate_ast_node(node.left)
        right = _evaluate_ast_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
        raise ValueError("unsupported operator")
    if isinstance(node, ast.UnaryOp):
        value = _evaluate_ast_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return value
        if isinstance(node.op, ast.USub):
            return -value
        raise ValueError("unsupported unary operator")
    raise ValueError("unsupported expression")


def _formula_cell_value(
    row: int,
    col: int,
    formula_grid: list[list],
    value_grid: list[list],
    memo: dict[tuple[int, int], float | None],
) -> float | None:
    key = (row, col)
    if key in memo:
        return memo[key]

    raw = None
    if row - 1 < len(value_grid) and col - 1 < len(value_grid[row - 1]):
        raw = value_grid[row - 1][col - 1]
    if raw is not None:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = None
        memo[key] = value
        return value

    formula = None
    if row - 1 < len(formula_grid) and col - 1 < len(formula_grid[row - 1]):
        formula = formula_grid[row - 1][col - 1]
    if not isinstance(formula, str) or not formula.startswith("="):
        memo[key] = None
        return None

    memo[key] = None

    def replace_ref(match: re.Match) -> str:
        ref = match.group(0).replace("$", "")
        ref_match = re.fullmatch(r"([A-Z]{1,3})(\d+)", ref)
        if not ref_match:
            raise ValueError("invalid cell reference")
        ref_col = column_index_from_string(ref_match.group(1))
        ref_row = int(ref_match.group(2))
        ref_value = _formula_cell_value(
            ref_row, ref_col, formula_grid, value_grid, memo
        )
        if ref_value is None:
            raise ValueError("missing cell value")
        return repr(float(ref_value))

    try:
        expression = formula[1:]
        expression = re.sub(r"\$?[A-Z]{1,3}\$?\d+", replace_ref, expression)
        if re.search(r"[A-Za-z]", expression):
            return None
        result = _evaluate_ast_node(ast.parse(expression, mode="eval").body)
        memo[key] = float(result)
        return memo[key]
    except Exception:
        return None


def _fill_formula_values(df, sheet_name: str, formula_book, value_book):
    if sheet_name not in formula_book.sheetnames or sheet_name not in value_book.sheetnames:
        return df

    formula_ws = formula_book[sheet_name]
    value_ws = value_book[sheet_name]
    formula_grid = [[cell.value for cell in row] for row in formula_ws.iter_rows(values_only=False)]
    value_grid = [[cell.value for cell in row] for row in value_ws.iter_rows(values_only=False)]
    memo: dict[tuple[int, int], float | None] = {}

    for row_idx in range(df.shape[0]):
        for col_idx in range(df.shape[1]):
            value = df.iat[row_idx, col_idx]
            if value is not None and not (isinstance(value, float) and value != value):
                continue
            computed = _formula_cell_value(
                row_idx + 1,
                col_idx + 1,
                formula_grid,
                value_grid,
                memo,
            )
            if computed is not None:
                df.iat[row_idx, col_idx] = computed
    return df


def _workbook_cache_path(prefix: str) -> Path:
    # pickle 缓存（比旧 gzip json 快 3-5 倍，启动/首开网页等待显著缩短）
    return CACHE_DIR / f"{prefix}_charts.pkl"


def _write_workbook_cache(
    filepath: Path, prefix: str, charts: list[dict], sectors: set[str]
) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        target = _workbook_cache_path(prefix)
        tmp_path = CACHE_DIR / f".{prefix}_charts.pkl.tmp"
        with open(tmp_path, "wb") as fh:
            pickle.dump(
                {
                    "version": CACHE_VERSION,
                    "source": filepath.name,
                    "charts": charts,
                    "sectors": sorted(sectors or set()),
                },
                fh,
                protocol=4,
            )
        os.replace(tmp_path, target)
    except Exception as e:
        logger.warning("workbook cache write failed (%s): %s", prefix, e)


# ══ DEMO 模式(mock 数据, 运行时内存生成, 不产生/读取任何真实样例文件)══
# 启动: DEMO=1 python server.py  (或 start_demo.bat)
# 脱敏口径(中档): 保留公开产业框架词(板块链: 锂矿/碳酸锂/锡矿/工业硅…与价格/库存等通用维度词),
# 去掉全部真实细节: 无 SMM/Mysteel/GFEX 等来源、无公司/矿区/原料成分规格、无 AI 原因文本;
# 数值为随机游走序列; 个股清单返回空(不读取本地个股 Excel); 现货 KPI 返回演示随机值(期货主力仍为新浪公开实时)。
DEMO_MODE = os.getenv("DEMO", "") == "1"
_DEMO_SECTORS = {
    "lithium": ["锂矿", "锂盐", "碳酸锂", "氢氧化锂", "其他锂盐", "三元正极", "钴酸锂", "锰酸锂",
                "磷酸铁锂", "磷化工链", "负极材料", "隔膜", "电解液产业链", "辅材", "电池电芯", "储能", "新能源汽车"],
    "tin": ["锡矿", "锡锭", "锡材", "铅蓄电池", "镀锡板", "锡其他"],
    "silicon": ["工业硅", "有机硅", "多晶硅", "硅片", "电池片", "组件", "光伏辅材", "铝合金",
                "硅石石英砂", "下游需求"],
}
_DEMO_DIM_UNITS = {
    "价格": "元/吨", "均价": "元/吨", "价差": "元/吨", "基差": "元/吨",
    "加工费": "元/吨", "成本": "元/吨", "库存": "吨", "仓单量": "手",
    "产量": "吨", "开工率": "%", "毛利": "元/吨", "表观消费": "吨",
}
_DEMO_DIMS = list(_DEMO_DIM_UNITS)
_DEMO_GRADES = ["一级品", "二级品", "优等品", "通用级", "国产", "进口", "北方", "南方"]


def _demo_trade_dates(n: int):
    """从今天往回生成 n 个工作日(演示日期, 周末跳过), 返回降序 YYYY-MM-DD。"""
    out = []
    d = datetime.now().date()
    from datetime import timedelta
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out


def _demo_walk(rng, start: float, n: int, daily_std: float = 0.008):
    v = start
    vals = []
    for _ in range(n):
        v = max(v * (1 + rng.gauss(0, daily_std)), 1.0)
        vals.append(round(v, 2))
    return vals


def _demo_charts(source: str) -> list[dict]:
    import random as _r
    rng = _r.Random()
    dates = {f: _demo_trade_dates(n) for f, n in
             (("daily", 480), ("weekly", 240), ("monthly", 120))}
    charts = []
    idx = 0
    sector_words = _DEMO_SECTORS.get(source, ["通用板块"])
    for si, sector in enumerate(sector_words):
        n_sub = 3 if si % 3 == 0 else 4
        for sub_i in range(n_sub):
            dim = _DEMO_DIMS[(si * 3 + sub_i) % len(_DEMO_DIMS)]
            grade = _DEMO_GRADES[(si + sub_i) % len(_DEMO_GRADES)]
            unit = _DEMO_DIM_UNITS[dim]
            base = {
                "价格": 15000, "均价": 14000, "价差": 800, "基差": 300, "加工费": 4000,
                "成本": 11000, "库存": 30000, "仓单量": 5000, "产量": 20000,
                "开工率": 60, "毛利": 2500, "表观消费": 25000,
            }[dim]
            freq, points = (("daily", 480) if (si + sub_i) % 3 else ("weekly", 240))
            if (si * 5 + sub_i) % 7 == 0:
                freq, points = "monthly", 120
            series = _demo_walk(rng, base, points, 0.01 if dim in ("开工率",) else 0.008)
            ds = dates[freq][:len(series)]
            data = [{"date": ds[i], "value": series[i]} for i in range(len(series))]
            charts.append({
                "id": f"{source}_demo_{idx}", "title": f"{dim}-{grade}-演示", "unit": unit,
                "sector": sector, "major": sector, "sub": f"{dim}({grade})",
                "freq": freq, "data": data,
                "selected": True, "final_selected": True, "finalSelected": True,
                "catalogOrder": idx,
            })
            idx += 1
    return charts


def _demo_warehouse_table(source: str) -> dict:
    """演示仓单行(仓库名打码 A-H, 无真实地理/仓库信息), 结构与 live 行同构。"""
    import random as _r
    rng = _r.Random()
    dates = _demo_trade_dates(30)
    vals = _demo_walk(rng, 8000, 30, 0.006)
    rows = []
    for i in range(8):
        rv = _demo_walk(rng, 300 + i * 120, 30, 0.012)
        rows.append({
            "kind": "warehouse", "warehouse": f"演示仓库{chr(65 + i)}", "region": "", "product": "",
            "values": [rv[0], rv[1]], "daily_change": round(rv[0] - rv[1], 2),
            "daily_rate": round((rv[0] - rv[1]) / rv[1] * 100, 2) if rv[1] else None,
            "weekly_change": round(rv[0] - rv[5], 2), "weekly_rate": round((rv[0] - rv[5]) / rv[5] * 100, 2) if rv[5] else None,
            "monthly_change": round(rv[0] - rv[21], 2), "monthly_rate": round((rv[0] - rv[21]) / rv[21] * 100, 2) if rv[21] else None,
            "series": [{"date": dates[i2], "value": rv[i2]} for i2 in range(30)],
        })
    rows.append({
        "kind": "total", "warehouse": "全国仓单量", "region": "", "product": "",
        "values": [vals[0], vals[1]], "daily_change": round(vals[0] - vals[1], 2),
        "daily_rate": None, "weekly_change": round(vals[0] - vals[5], 2),
        "weekly_rate": None, "monthly_change": round(vals[0] - vals[21], 2), "monthly_rate": None,
        "series": [{"date": dates[i2], "value": vals[i2]} for i2 in range(30)],
    })
    return {"dates": dates[:2], "rows": rows}


def _load_persisted_workbook(filepath: Path, prefix: str):
    """Load a workbook from pickle cache, rebuilding when stale or missing."""
    cache_path = _workbook_cache_path(prefix)
    try:
        if cache_path.exists() and cache_path.stat().st_mtime >= filepath.stat().st_mtime:
            with open(cache_path, "rb") as fh:
                payload = pickle.load(fh)
            if (
                payload.get("version") == CACHE_VERSION
                and payload.get("source") == filepath.name
            ):
                charts = payload.get("charts", [])
                sectors = set(payload.get("sectors", []))
                if charts:
                    return charts, sectors
    except Exception as e:
        logger.warning("workbook cache load failed (%s): %s", prefix, e)

    charts, sectors = _load_excel_workbook(filepath, prefix)
    if charts is not None:
        _write_workbook_cache(filepath, prefix, charts, sectors or set())
    return charts, sectors


def _source_workbook_path(
    published_paths: dict[str, str],
    source: str,
    fallback: Path,
) -> Path:
    """Use the latest published path when present and valid."""
    raw = published_paths.get(source)
    if not raw:
        return fallback
    candidate = Path(raw)
    if not candidate.exists():
        logger.warning("published workbook missing for %s: %s", source, candidate)
        return fallback
    return candidate


def _load_excel_workbook(filepath: Path, prefix: str):
    """Load a single processed Excel workbook and return charts with the given prefix."""
    import pandas as pd

    if not filepath.exists():
        logger.warning("workbook not found: %s", filepath)
        return None, None
    xl = None
    formula_book = None
    value_book = None
    try:
        xl = pd.ExcelFile(filepath, engine="openpyxl")
        try:
            formula_book = load_workbook(filepath, read_only=True, data_only=False)
            value_book = load_workbook(filepath, read_only=True, data_only=True)
        except Exception as e:
            logger.warning("formula workbook load skipped (%s): %s", filepath, e)
        catalog_sheet = xl.sheet_names[0]
        df_cat = pd.read_excel(
            xl, sheet_name=catalog_sheet, header=None, dtype=str
        )
        header_index = {}
        for idx, raw in enumerate(df_cat.iloc[0]):
            name = str(raw).strip() if pd.notna(raw) else ""
            if name:
                header_index[name] = idx

        def resolve_column(aliases):
            for alias in aliases:
                if alias in header_index:
                    return header_index[alias]
            return None

        def require_column(aliases):
            idx = resolve_column(aliases)
            if idx is None:
                raise CatalogSchemaError(
                    f"missing required catalog column, expected one of: {aliases}"
                )
            return idx

        def cell_value(row, idx):
            if idx is None or idx >= len(row):
                return ""
            value = row[idx]
            return str(value).strip() if pd.notna(value) else ""

        sheet_indexes = [
            header_index[name] for name in ("Sheet Name", "#") if name in header_index
        ]
        if not sheet_indexes:
            raise CatalogSchemaError(
                "missing required catalog column for sheet, expected 'Sheet Name' or '#'"
            )
        column_zero_is_sheet = 0 in sheet_indexes
        freq_idx = require_column(["Freq", "频率"])
        col_idx = require_column(["Col", "列号"])
        name_idx = require_column(["Indicator Name", "指标名称"])
        unit_idx = resolve_column(["Unit", "单位"])
        sector_idx = resolve_column(["板块"])
        major_idx = resolve_column(["大类"])
        sub_idx = resolve_column(["子类"])
        confidence_idx = resolve_column(["置信度", "confidence", "Confidence"])
        selected_idx = resolve_column(["是否选中"])
        final_selected_idx = resolve_column(["二次筛选是否保留"])
        reason_idx = resolve_column(["状态说明"])
        tags_idx = resolve_column(["指标标签"])

        entries = []
        current_sheet = None
        current_sector = None
        current_freq = None
        for _, row in df_cat.iloc[1:].iterrows():
            c0 = cell_value(row, 0)
            sheet_candidate = ""
            for idx in sheet_indexes:
                sheet_candidate = cell_value(row, idx)
                if sheet_candidate:
                    break
            freq = cell_value(row, freq_idx)
            col = cell_value(row, col_idx)
            name = cell_value(row, name_idx)
            unit = cell_value(row, unit_idx)
            sector = cell_value(row, sector_idx)
            major = cell_value(row, major_idx)
            sub = cell_value(row, sub_idx)
            selected_raw = cell_value(row, selected_idx) if selected_idx is not None else ""
            final_selected_raw = (
                cell_value(row, final_selected_idx)
                if final_selected_idx is not None
                else ""
            )
            reason = cell_value(row, reason_idx) if reason_idx is not None else ""
            tags_raw = cell_value(row, tags_idx) if tags_idx is not None else ""

            if not c0 and not sheet_candidate and not col and not name:
                continue
            if "sht" in c0.lower() or "sht" in sheet_candidate.lower():
                continue
            if sheet_candidate and not sheet_candidate.isdigit():
                current_sheet = sheet_candidate
            elif column_zero_is_sheet and c0 and not c0.isdigit():
                current_sheet = c0

            if current_sheet and col.isdigit() and name:
                catalog_order = len(entries)
                confidence = None
                if confidence_idx is not None:
                    raw_conf = cell_value(row, confidence_idx)
                    if raw_conf:
                        try:
                            confidence = float(raw_conf)
                        except ValueError:
                            raise CatalogSchemaError(
                                f"confidence column contains non-numeric value: {raw_conf!r}"
                            )
                entries.append((
                    current_sheet,
                    int(col),
                    name,
                    unit,
                    # 行内 Freq 优先（目录行被重排后继承链会断/被引用行污染，
                    # 行内值才是该指标真实频率；空值才回退 sheet 继承）
                    freq or current_freq,
                    sector or current_sector or "",
                    confidence,
                    major,
                    sub,
                    selected_raw,
                    final_selected_raw,
                    reason,
                    _parse_tags(tags_raw),
                    catalog_order,
                ))
                continue
            if sector:
                current_sector = sector
            # 频率继承只吸收 sheet 头行；目录中 "'sheet'!A1" 式跳转行的 Freq 列
            # 只是源位置标记，若进入继承会把后续指标频率带偏（如月度误标年度）
            if freq and not name.startswith("'"):
                current_freq = freq
        from collections import defaultdict
        sheet_cols = defaultdict(list)
        sector_set = set()
        for sn, col, name, unit, freq, sector, confidence, major, sub, selected, final_selected, reason, tags, catalog_order in entries:
            sheet_cols[sn].append((col, name, unit, freq, sector, confidence, major, sub, selected, final_selected, reason, tags, catalog_order))
            if sector:
                sector_set.add(sector)
        charts = []
        for sn, cols in sheet_cols.items():
            if sn not in xl.sheet_names:
                continue
            df_data = pd.read_excel(xl, sheet_name=sn, header=None)
            if formula_book is not None and value_book is not None:
                df_data = _fill_formula_values(df_data, sn, formula_book, value_book)
            dates_raw = df_data.iloc[3:, 0]
            dates = pd.to_datetime(dates_raw, errors="coerce").tolist()
            for col, name, unit, freq, sector, confidence, major, sub, selected, final_selected, reason, tags, catalog_order in cols:
                if col >= df_data.shape[1]:
                    continue
                if not _keep_warehouse_receipt_total(name):
                    # 仓单只画总量/小计，分仓库明细行不在看板显示
                    continue
                values = pd.to_numeric(
                    df_data.iloc[3:, col], errors="coerce"
                ).tolist()
                data_points = [
                    {"date": str(d.date()),
                     "value": float(v) if pd.notna(v) else 0.0}
                    for d, v in zip(dates, values)
                    if pd.notna(d) and pd.notna(v)
                ]
                data_points.sort(key=lambda x: x["date"], reverse=True)
                eff_sector = sector
                if "其他价格" in sn:
                    # "其他价格" sheet 无板块列信息，按数据源映射到对应"其他"板块
                    #（锡 -> 锡其他；历史实现 f"{prefix}其他" 会产出 "tin其他" 错误板块名）
                    eff_sector = {
                        "tin": "锡其他",
                        "silicon": "硅其他",
                        "lithium": "锂其他",
                    }.get(prefix, f"{prefix}其他")
                charts.append((confidence, {
                    "id": f"{prefix}_{sn}_c{col}",
                    "title": name,
                    "unit": unit,
                    "category": _classify_category(name),
                    "section": sn,
                    "source": "SMM/海关/行业",
                    "freq": _FREQ_MAP.get(freq, freq),
                    "data": data_points,
                    "sector": eff_sector,
                    "confidence": confidence,
                    "major": major or "",
                    "sub": sub or "",
                    "selected": selected == "是",
                    "final_selected": final_selected == "是",
                    "selection_reason": reason or "",
                    "tags": tags,
                    "catalog_order": catalog_order,
                    "catalogOrder": catalog_order,
                }))
        sorted_charts = [c for _, c in charts]
        # 目录表可能存在多行指向同一数据列（Sheet Name 继承错位 / 行复制导致），
        # 同一 id（同一 sheet+列）只保留目录序第一行，其余丢弃并告警，
        # 防止看板出现重复指标（表格重复行 / React key 冲突 / 数据张冠李戴）。
        seen_ids: set[str] = set()
        final_charts = []
        for c in sorted_charts:
            cid = c["id"]
            if cid in seen_ids:
                logger.warning(
                    "duplicate chart id %s ('%s') dropped (already loaded once)",
                    cid,
                    c["title"],
                )
                continue
            seen_ids.add(cid)
            final_charts.append(c)
        return final_charts, sector_set
    except CatalogSchemaError as e:
        logger.error("catalog schema error (%s): %s", filepath, e)
        return None, None
    except Exception as e:
        logger.warning("workbook load error (%s): %s", filepath, e)
        return None, None
    finally:
        # 显式关闭句柄：openpyxl read_only workbook 与 zipfile 存在循环引用，
        # 仅靠引用计数/GC 无法及时释放，会一直独占锁定 Excel 文件，
        # 导致用户无法在 Python/Excel 中删除或修改该文件。
        for _wb in (formula_book, value_book, xl):
            if _wb is not None:
                try:
                    _wb.close()
                except Exception:
                    pass


def _load_all_workbooks():
    """Load all industry workbooks and signal readiness."""
    global _TIN_SECTORS, _SILICON_SECTORS, _LITHIUM_SECTORS
    global _SOURCE_SECTORS, _SOURCE_CHARTS, _CHART_INDEX
    if DEMO_MODE:
        _SOURCE_CHARTS.clear()
        _CHART_INDEX.clear()
        _SOURCE_SECTORS.clear()
        _excel_cache.clear()
        all_charts = []
        for source in ("tin", "silicon", "lithium"):
            charts = _demo_charts(source)
            sectors = {c["sector"] for c in charts}
            _SOURCE_SECTORS[source] = sectors
            _SOURCE_CHARTS[source] = charts
            _CHART_INDEX.update({c["id"]: c for c in charts})
            all_charts.extend(charts)
            print(f"[demo] {source}: {len(charts)} charts(内存随机生成)")
        _excel_cache["__all__"] = {"tab": "__all__", "charts": all_charts}
        _DATA_LOAD_EVENT.set()
        return

    try:
        try:
            for old in CACHE_DIR.glob("*_charts.json.gz"):
                old.unlink()
        except Exception:
            pass
        all_charts = []
        published_paths = _read_published_source_paths()
        paths = {
            "tin": _source_workbook_path(published_paths, "tin", TIN_WORKBOOK_PATH),
            "silicon": _source_workbook_path(published_paths, "silicon", SILICON_WORKBOOK_PATH),
            "lithium": _source_workbook_path(published_paths, "lithium", LITHIUM_WORKBOOK_PATH),
        }

        # Phase 1（并行）：只读 pickle 缓存，不占用 Excel 解析内存
        def _try_cache(source: str, filepath: Path):
            cache_path = _workbook_cache_path(source)
            try:
                if cache_path.exists() and cache_path.stat().st_mtime >= filepath.stat().st_mtime:
                    with open(cache_path, "rb") as fh:
                        payload = pickle.load(fh)
                    if (
                        payload.get("version") == CACHE_VERSION
                        and payload.get("source") == filepath.name
                    ):
                        charts = payload.get("charts", [])
                        if charts:
                            return charts, set(payload.get("sectors", []))
            except Exception as e:
                logger.warning("workbook cache load failed (%s): %s", source, e)
            return None

        with ThreadPoolExecutor(max_workers=3) as pool:
            cached = dict(zip(paths, pool.map(lambda kv: _try_cache(kv[0], kv[1]), paths.items())))

        # Phase 2：缓存未命中者串行解析（内部会写回 pickle 缓存）
        results: dict[str, tuple[list | None, set | None]] = {}
        for source, path in paths.items():
            res = cached.get(source)
            if res is None:
                res = _load_persisted_workbook(path, source)
            results[source] = res

        for source in ("tin", "silicon", "lithium"):
            charts, sectors = results[source]
            if charts is None:
                continue
            if source == "tin":
                _TIN_SECTORS = sectors or set()
                _SOURCE_SECTORS["tin"] = _TIN_SECTORS
            elif source == "silicon":
                _SILICON_SECTORS = sectors or set()
                _SOURCE_SECTORS["silicon"] = _SILICON_SECTORS
            else:
                _LITHIUM_SECTORS = sectors or set()
                _SOURCE_SECTORS["lithium"] = _LITHIUM_SECTORS
            _SOURCE_CHARTS[source] = charts
            _CHART_INDEX.update({c["id"]: c for c in charts})
            all_charts.extend(charts)
            print(f"[excel] {source}: loaded {len(charts)} charts, sectors: {len(sectors or set())}")
        _excel_cache["__all__"] = {"tab": "__all__", "charts": all_charts}
        print(f"[excel] total loaded: {len(all_charts)} charts")
    finally:
        _DATA_LOAD_EVENT.set()


@app.on_event("startup")
async def _startup():
    """Load Excel data in background thread on startup."""
    threading.Thread(target=_load_all_workbooks, daemon=True).start()


_TIN_SECTORS: set[str] = set()
_SILICON_SECTORS: set[str] = set()
_LITHIUM_SECTORS: set[str] = set()
_SOURCE_SECTORS: dict[str, set[str]] = {}
_SOURCE_CHARTS: dict[str, list] = {}
_CHART_INDEX: dict[str, dict] = {}
_PUBLISHED_SNAPSHOT: dict[str, str] = {}


def _filter_core(charts):
    try:
        import json as _j
        core_ids = set()
        with open(PROJECT_ROOT / "锡核心指标.json", encoding="utf-8") as f:
            for c in _j.load(f):
                core_ids.add(c.get("id", ""))
        return [c for c in charts if c.get("id", "") in core_ids]
    except Exception as e:
        logger.warning("core filter failed: %s", e)
        return charts


def _filter_by_sector(charts, sector):
    return [c for c in charts if c.get("sector", "?") == sector]


def _wait_for_excel_data() -> None:
    if not _DATA_LOAD_EVENT.is_set():
        _DATA_LOAD_EVENT.wait(timeout=90)
    if not _SOURCE_CHARTS:
        _load_all_workbooks()
    _reload_published_workbooks_if_changed()


async def _wait_excel_ready() -> None:
    """等待 Excel 数据就绪（异步轮询，不阻塞事件循环）。

    旧版在 async 路由内同步 Event.wait(90s)：Excel 尚未就绪时（启动解析中），
    等待本身会把整个事件循环卡住——指数行情/新闻等所有请求都排队，页面表现为
    一打开就长时间"正在读取 Excel 数据"。改为 asyncio.sleep 轮询后，
    其它接口可先行返回，页面顶部/自选/新闻等区块先渲染，行业数据区就绪后即现。
    """
    while not _DATA_LOAD_EVENT.is_set():
        await asyncio.sleep(0.15)
    await asyncio.to_thread(_reload_published_workbooks_if_changed)


def _reload_published_workbooks_if_changed() -> None:
    global _PUBLISHED_SNAPSHOT
    published_paths = _read_published_source_paths()
    if published_paths == _PUBLISHED_SNAPSHOT:
        return
    _PUBLISHED_SNAPSHOT = published_paths
    _SOURCE_CHARTS.clear()
    _SOURCE_SECTORS.clear()
    _CHART_INDEX.clear()
    _excel_cache.clear()
    _load_all_workbooks()


def _resolve_payload_source(payload: ExcelRequest) -> str | None:
    source = payload.dataset
    if not source:
        source = _resolve_source(payload.tab, payload.sector)
    return source


LITHIUM_SECTOR_ALIASES = {
    "\u78f7\u9178\u94c1\u9502": {"\u78f7\u9178\u94c1\u9502", "\u78f7\u5316\u5de5\u94fe"},
}
# \u9521\u677f\u5757\u522b\u540d\uff1a\u6570\u636e\u4fa7\u65e0"\u9521\u4e0b\u6e38"\u677f\u5757\uff08\u94c5\u84c4\u7535\u6c60/\u9540\u9521\u677f\u5373\u9521\u4e0b\u6e38\u5e94\u7528\uff09\uff0c
# \u8bf7\u6c42 sector=\u9521\u4e0b\u6e38 \u65f6\u4e00\u5e76\u8fd4\u56de\u94c5\u84c4\u7535\u6c60/\u9540\u9521\u677f\u6307\u6807
TIN_SECTOR_ALIASES = {
    "\u9521\u4e0b\u6e38": {"\u9521\u4e0b\u6e38", "\u94c5\u84c4\u7535\u6c60", "\u9540\u9521\u677f"},
}
_SECTOR_ALIASES = {**LITHIUM_SECTOR_ALIASES, **TIN_SECTOR_ALIASES}

def _filter_by_sector_aliases(charts: list[dict], sector: str) -> list[dict]:
    allowed = _SECTOR_ALIASES.get(sector, {sector})
    return [c for c in charts if c.get("sector", "") in allowed]

def _get_charts_for_request(source: str | None, sector: str | None) -> list[dict]:
    if source and source in _SOURCE_CHARTS:
        charts = list(_SOURCE_CHARTS[source])
        if sector:
            charts = _filter_by_sector_aliases(charts, sector)
        return charts
    if "__all__" in _excel_cache:
        charts = _excel_cache["__all__"]["charts"]
        if sector:
            charts = _filter_by_sector_aliases(charts, sector)
        return charts
    return []


def _chart_metadata(chart: dict) -> dict:
    meta = {key: value for key, value in chart.items() if key != "data"}
    if "catalogOrder" not in meta and "catalog_order" in meta:
        meta["catalogOrder"] = meta["catalog_order"]
    if "finalSelected" not in meta and "final_selected" in meta:
        meta["finalSelected"] = meta["final_selected"]
    return meta


STOCK_TARGET_TAB_MAP = {
    "silicon": {
        "工业硅": ["工业硅"],
        "有机硅": ["有机硅"],
        "多晶硅": ["多晶硅"],
        "硅片": ["硅片"],
        "电池片": ["电池片"],
        "组件": ["组件"],
        "光伏辅材": ["光伏辅材"],
        "铝合金": ["铝合金"],
    },
    "tin": {
        "锡矿": ["锡矿"],
        "锡锭": ["锡锭"],
        "锡材": ["锡材"],
        "锡下游": ["锡下游"],
        "锡其他": ["锡其他"],
    },
    "lithium": {
        "锂矿锂盐": ["锂矿", "锂盐", "碳酸锂", "氢氧化锂", "其他锂盐"],
        "三元正极": ["三元正极", "钴酸锂", "锰酸锂"],
        "磷酸铁锂正极": ["磷酸铁锂", "磷化工链"],
        "负极": ["负极材料"],
        "隔膜": ["隔膜"],
        "电解液": ["电解液产业链"],
        "铜箔铝箔": ["辅材"],
        "储能&集成": ["储能"],
        "电池&电芯": ["电池电芯"],
        "新能源汽车": ["新能源汽车"],
        # 股票池细分板块实际值为"新能源车"（与 tab 名"新能源汽车"不一致），
        # 补齐映射，否则该板块股票不进入任何 tab、总览缺失
        "新能源车": ["新能源汽车"],
    },
}


# 个股排序：一级按产业链上下游环节（上游 -> 中游 -> 下游，无环节最后），
# 二级按环节内板块（细分板块）产业链顺序，三级同板块内按市值降序
# （Excel"总市值(亿)"列，缺失按 0）。
SEGMENT_RANK_PREFIXES = ["上游", "中游", "下游"]
# 细分板块产业链顺序（环节内板块排序用；与图表板块 SECTOR_ORDER 不同名，单独维护）。
# 按数据源区分：锂电 / 锡 / 硅 各自维护（与 个股标的_*.xlsx 的"细分板块"列一致）。
STOCK_SUB_ORDER_LITHIUM = [
    "锂矿", "锂盐", "三元正极", "磷酸铁锂正极", "负极",
    "隔膜", "电解液", "铜箔铝箔", "电池&电芯", "储能&集成", "新能源车",
]
STOCK_SUB_ORDER_TIN = ["锡矿", "锡锭", "锡材", "锡下游"]
STOCK_SUB_ORDER_SILICON = [
    "工业硅", "有机硅", "多晶硅", "硅片", "电池片", "组件", "光伏辅材", "铝合金",
]
STOCK_SUB_ORDERS = {
    "lithium": STOCK_SUB_ORDER_LITHIUM,
    "tin": STOCK_SUB_ORDER_TIN,
    "silicon": STOCK_SUB_ORDER_SILICON,
}


def _segment_rank(segment: str) -> int:
    for i, prefix in enumerate(SEGMENT_RANK_PREFIXES):
        if segment.startswith(prefix):
            return i
    return len(SEGMENT_RANK_PREFIXES)


def _sub_rank(sub: str, sub_order: list[str]) -> int:
    try:
        return sub_order.index(sub)
    except ValueError:
        return len(sub_order)


def _stock_sort_key(code: str, segment: str, subs, market_cap: float, sub_order: list[str]):
    sub_rank = min((_sub_rank(s, sub_order) for s in subs), default=len(sub_order))
    return (_segment_rank(segment), sub_rank, -market_cap, code)


def _iter_stock_source_rows(source: str, filename: str):
    """个股标的源行迭代：锂电存在 manual_lithium.json 时使用人工清单，否则读 Excel。

    yield dict: code/name/sub/segment/cap（Excel 行列与 manual json 字段同名）。
    """
    if source == "lithium" and MANUAL_STOCK_FILE_LITHIUM.exists():
        try:
            payload = json.loads(MANUAL_STOCK_FILE_LITHIUM.read_text(encoding="utf-8"))
            for it in payload.get("stocks", []):
                yield {
                    "code": str(it.get("code", "")).strip(),
                    "name": str(it.get("name", "")).strip(),
                    "sub": str(it.get("sub", "")).strip(),
                    "segment": str(it.get("segment", "")).strip(),
                    "cap": float(it.get("cap") or 0.0),
                }
            return
        except Exception as e:
            logger.warning("manual stock list load failed (%s): %s", source, e)
            # 人工清单读取失败时回退 Excel
    filepath = STOCK_TARGETS_DIR / filename
    if not filepath.exists():
        logger.warning("stock target file not found: %s", filepath)
        return
    wb = None
    try:
        wb = load_workbook(filepath, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        headers = [
            str(cell.value).strip() if cell.value is not None else ""
            for cell in next(ws.iter_rows(min_row=1, max_row=1))
        ]
        sub_idx = headers.index("细分板块")
        code_idx = headers.index("股票代码")
        name_idx = headers.index("股票名称")
        segment_idx = headers.index("所属环节")
        cap_idx = headers.index("总市值(亿)") if "总市值(亿)" in headers else None
        for row in ws.iter_rows(min_row=2, values_only=True):
            cap = 0.0
            if cap_idx is not None and row[cap_idx] is not None:
                try:
                    cap = float(row[cap_idx])
                except (TypeError, ValueError):
                    cap = 0.0
            yield {
                "code": str(row[code_idx]).strip() if row[code_idx] is not None else "",
                "name": str(row[name_idx]).strip() if row[name_idx] is not None else "",
                "sub": str(row[sub_idx]).strip() if row[sub_idx] is not None else "",
                "segment": str(row[segment_idx]).strip() if row[segment_idx] is not None else "",
                "cap": cap,
            }
    except Exception as e:
        logger.warning("stock targets load failed (%s): %s", filepath, e)
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


def _load_stock_targets():
    # DEMO 模式: 不读取本地个股清单(返回空, 个股区显示"暂无标的")
    if DEMO_MODE:
        return {
            "groups": {source: {"总览": []} for source in STOCK_TARGET_FILES},
            "stocks": {source: {} for source in STOCK_TARGET_FILES},
        }
    groups = {source: {"总览": []} for source in STOCK_TARGET_FILES}
    stock_meta = {source: {} for source in STOCK_TARGET_FILES}
    for source, filename in STOCK_TARGET_FILES.items():
        for row in _iter_stock_source_rows(source, filename):
            sub = row["sub"]
            code = row["code"]
            if not sub or not code.isdigit() or len(code) != 6:
                continue
            name = row["name"]
            segment = row["segment"]
            cap = row["cap"]
            if code not in stock_meta[source]:
                stock_meta[source][code] = {"name": name, "segments": set(), "subs": set(), "market_cap": cap}
            else:
                stock_meta[source][code]["market_cap"] = max(
                    stock_meta[source][code]["market_cap"], cap
                )
            if segment:
                stock_meta[source][code]["segments"].add(segment)
            if sub:
                stock_meta[source][code]["subs"].add(sub)
            for tab in STOCK_TARGET_TAB_MAP.get(source, {}).get(sub, []):
                groups[source].setdefault(tab, []).append(code)

    for source, tabs in groups.items():
        sub_order = STOCK_SUB_ORDERS.get(source, STOCK_SUB_ORDER_LITHIUM)
        all_codes = []
        for tab, codes in tabs.items():
            if tab == "总览":
                continue
            all_codes.extend(codes)
        groups[source]["总览"] = sorted(set(all_codes), key=lambda c: _stock_sort_key(
            c, _segments_of(stock_meta[source], c), _subs_of(stock_meta[source], c), _cap_of(stock_meta[source], c), sub_order))
        for tab in list(groups[source]):
            groups[source][tab] = sorted(set(groups[source][tab]), key=lambda c: _stock_sort_key(
                c, _segments_of(stock_meta[source], c), _subs_of(stock_meta[source], c), _cap_of(stock_meta[source], c), sub_order))

    for source, codes in stock_meta.items():
        for item in codes.values():
            item["segment"] = " / ".join(sorted(item.pop("segments")))
            item["subs"] = sorted(item.pop("subs"))
    return {"groups": groups, "stocks": stock_meta}


def _segments_of(meta: dict, code: str) -> str:
    item = meta.get(code) or {}
    return item.get("segment") or (item.get("segments") and " / ".join(sorted(item["segments"]))) or ""


def _subs_of(meta: dict, code: str):
    item = meta.get(code) or {}
    return set(item.get("subs") or [])


def _cap_of(meta: dict, code: str) -> float:
    item = meta.get(code) or {}
    return float(item.get("market_cap") or 0.0)


@app.get("/api/stock-targets")
async def get_stock_targets():
    return _load_stock_targets()


@app.post("/api/battery/excel")
async def battery_excel(payload: ExcelRequest):
    await _wait_excel_ready()
    tab = payload.tab
    source = _resolve_payload_source(payload)
    cache_key = (source + "|" if source else "") + tab + ("|" + payload.sector if payload.sector else "")
    if cache_key in _excel_cache:
        return JSONResponse(content=_excel_cache[cache_key], headers={"Cache-Control": "no-cache"})
    charts = _get_charts_for_request(source, payload.sector)
    if charts:
        result = {"tab": tab, "sector": payload.sector, "charts": charts}
        _excel_cache[cache_key] = result
        return JSONResponse(content=result, headers={"Cache-Control": "no-cache"})
    return JSONResponse(content={"tab": tab, "charts": []})


@app.post("/api/battery/excel/meta")
async def battery_excel_meta(payload: ExcelRequest):
    await _wait_excel_ready()
    source = _resolve_payload_source(payload)
    charts = _get_charts_for_request(source, payload.sector)
    if payload.selected_only:
        charts = [c for c in charts if c.get("final_selected")]
    result = {
        "tab": payload.tab,
        "sector": payload.sector,
        "meta_only": True,
        "charts": [_chart_metadata(c) for c in charts],
    }
    return JSONResponse(content=result, headers={"Cache-Control": "no-cache"})


@app.post("/api/battery/excel/charts")
async def battery_excel_charts(payload: ChartBatchRequest):
    await _wait_excel_ready()
    found = []
    seen = set()
    for chart_id in payload.ids[:200]:
        if chart_id in seen:
            continue
        chart = _CHART_INDEX.get(chart_id)
        if chart:
            found.append({**chart, "catalogOrder": chart.get("catalog_order")})
            seen.add(chart_id)
    return {"charts": found}


# ── 顶部核心商品 KPI（IndustryKpiBand 数据源）──
# 每个产业链取 现货 + 期货主力 两条价格；match = (标题前缀, 频率, 排除词)
INDUSTRY_KPI_SPECS = {
    "lithium": {
        "label": "锂",
        "items": [
            {"key": "spot", "label": "碳酸锂现货",
             "match": ("SMM: 电池级碳酸锂 - 平均价", "daily", None)},
            {"key": "future", "label": "碳酸锂主力",
             "match": ("GFEX: 碳酸锂: 主力合约: 收盘价", "daily", None)},
        ],
    },
    "tin": {
        "label": "锡",
        "items": [
            {"key": "spot", "label": "1#锡现货",
             "match": ("SMM: 1#锡-平均价", "daily", None)},
            {"key": "future", "label": "沪锡主力",
             "match": ("SHFE: 锡: 主力合约: 收盘价", "daily", None)},
        ],
    },
    "silicon": {
        "label": "硅",
        "items": [
            # 注：8/19 旧文件目录行错位曾使 553#硅(华南) 读到胶膜价，
            # 已由 fix_silicon_catalog_sheets.py（多skill联动）补全 Sheet Name 修复。
            {"key": "spot", "label": "553#硅现货(华南)",
             "match": ("SMM: 553#硅(华南)", "daily", "美元")},
            {"key": "future", "label": "工业硅主力",
             "match": ("GFEX: 工业硅: 主力合约: 收盘价", "daily", None)},
        ],
    },
}


# 期货主力实时行情映射（KPI 端点覆盖用）：新浪主力连续代码
FUTURE_SINA_CODES = {"lithium": "nf_LC0", "tin": "nf_SN0", "silicon": "nf_SI0"}
_FUT_QUOTE_CACHE: dict[str, tuple[float, dict]] = {}
_FUT_QUOTE_TTL = 5.0


def _fetch_sina_future_quotes(codes: list[str]) -> dict[str, dict]:
    """新浪期货主力连续行情（盘面实时）：最新价/昨结涨跌/行情日期/时间。

    字段（新浪 44 段）：[0]名称 [1]时间HHMMSS [2]开 [3]高 [4]低 [6]买 [7]卖
    [8]最新价 [10]昨结 [13]成交量 [17]行情日期。
    5 秒内存缓存防频控；失败返回空（调用方回退 Excel 读数）。
    """
    now = time.time()
    out: dict[str, dict] = {}
    missing: list[str] = []
    for code in codes:
        cached = _FUT_QUOTE_CACHE.get(code)
        if cached and now - cached[0] < _FUT_QUOTE_TTL:
            out[code] = cached[1]
        else:
            missing.append(code)
    if missing:
        try:
            url = "https://hq.sinajs.cn/list=" + ",".join(missing)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("gbk", errors="replace")
            for line in raw.strip().splitlines():
                if "=" not in line or '"' not in line:
                    continue
                key = line.split("=")[0].replace("var hq_str_", "").strip()
                vals = line.split('"')[1].split(",")
                if key not in missing or len(vals) < 18:
                    continue
                try:
                    price = float(vals[8])
                    prev = float(vals[10])
                except (TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                quote = {
                    "code": key,
                    "price": price,
                    "change_pct": round((price / prev - 1) * 100, 2) if prev > 0 else None,
                    "date": vals[17],
                    "time": vals[1],
                }
                out[key] = quote
                _FUT_QUOTE_CACHE[key] = (now, quote)
        except Exception as e:
            logger.warning("sina futures fail: %s", e)
    return out


@app.get("/api/industry/kpi")
async def industry_kpi():
    """跨产业链核心商品价格 KPI（顶部一行 6 卡）。

    每个 dataset 从已加载的 Excel 目录中按标题前缀匹配 现货/期货主力，
    取最新数据点与前一数据点算日环比；数据与指标图同源（含公式回填）。
    """
    # DEMO 模式: 现货=演示随机值(不读本地 Excel), 期货主力=新浪公开实时
    if DEMO_MODE:
        import random as _r
        rng = _r.Random()
        base0 = {"lithium": 78000, "tin": 210000, "silicon": 10500}
        today = _demo_trade_dates(1)[0]
        dgroups = []
        for ds, spec in INDUSTRY_KPI_SPECS.items():
            b = base0.get(ds, 50000)
            items = [{
                "key": "spot", "label": spec["items"][0]["label"] + "(演示)",
                "title": "演示现货(内存随机, 非本地数据)", "unit": "元/吨",
                "value": round(b * (1 + rng.gauss(0, 0.01)), 2),
                "date": today, "change_pct": round(rng.gauss(0.2, 1.2), 2),
            }]
            code = FUTURE_SINA_CODES.get(ds, "")
            if code:
                try:
                    q = _fetch_sina_future_quotes([code]).get(code)
                    if q:
                        items.append({
                            "key": "future", "label": spec["items"][1]["label"],
                            "title": "主力实时(新浪公开行情)", "unit": "元/吨",
                            "value": q["price"], "date": q.get("date") or today,
                            "change_pct": q.get("change_pct"),
                            "live": True, "live_time": q.get("time", ""),
                        })
                except Exception:  # noqa: BLE001
                    pass
            dgroups.append({"dataset": ds, "label": spec["label"], "items": items})
        return {"groups": dgroups}

    await _wait_excel_ready()
    # 期货主力卡：Excel 日频值作底，盘面实时行情（新浪主力连续）可用时覆盖，
    # 覆盖后带 live 标记（涨跌口径 = 实时 vs 昨结）；失败静默回退 Excel 值
    quotes = _fetch_sina_future_quotes(list(FUTURE_SINA_CODES.values()))
    groups = []
    for ds, spec in INDUSTRY_KPI_SPECS.items():
        charts = _SOURCE_CHARTS.get(ds) or []
        items = []
        for it in spec["items"]:
            prefix, freq, exclude = it["match"]
            hit = next(
                (
                    c
                    for c in charts
                    if c.get("title", "").startswith(prefix)
                    and c.get("freq") == freq
                    and (exclude is None or exclude not in c.get("title", ""))
                ),
                None,
            )
            if hit is None:
                continue
            data = hit.get("data") or []
            if len(data) < 2:
                continue
            latest, prev = data[0], data[1]
            value = latest.get("value")
            if value is None:
                continue
            change_pct = None
            try:
                change_pct = round(
                    (float(value) / float(prev["value"]) - 1) * 100, 2
                )
            except (TypeError, ValueError, ZeroDivisionError):
                change_pct = None
            item = {
                "key": it["key"],
                "label": it["label"],
                "title": hit["title"],
                "unit": hit.get("unit") or "",
                "value": float(value),
                "date": latest.get("date") or "",
                "change_pct": change_pct,
            }
            # 期货主力：实时覆盖（新浪代码在 FUTURE_SINA_CODES 中映射）
            if it["key"] == "future":
                sina_code = FUTURE_SINA_CODES.get(ds)
                quote = quotes.get(sina_code) if sina_code else None
                if quote:
                    item["value"] = quote["price"]
                    item["change_pct"] = quote["change_pct"]
                    item["date"] = quote["date"]
                    item["live"] = True
                    item["live_time"] = quote["time"]
            items.append(item)
        if items:
            groups.append({"dataset": ds, "label": spec["label"], "items": items})
    return {"groups": groups}


# ── 期货主力 分时/日K 图数据（新浪期货接口, 15s 缓存）──
_FUT_MARKET_CACHE: dict[str, tuple[float, dict]] = {}
_FUT_MARKET_TTL = 15.0


def _fetch_sina_future_market(dataset: str) -> dict | None:
    """主力期货 当日5分钟分时 + 近120根日K（新浪 getFewMinLine/getDailyKLine）。

    返回 None 表示失败（前端图卡显示占位）。prev_close 由实时行情涨跌反推，
    与 KPI 主力卡的涨跌口径一致（涨红跌绿同源）。
    """
    symbol = FUTURE_SINA_CODES.get(dataset, "").replace("nf_", "")
    if not symbol:
        return None
    now = time.time()
    cached = _FUT_MARKET_CACHE.get(dataset)
    if cached and now - cached[0] < _FUT_MARKET_TTL:
        return cached[1]
    result = None
    try:
        # 实时行情(取昨结反推) — 与 _fetch_sina_future_quotes 同源
        quote = _fetch_sina_future_quotes([FUTURE_SINA_CODES[dataset]]).get(FUTURE_SINA_CODES[dataset])
        prev_close = None
        if quote and quote.get("change_pct") is not None:
            try:
                prev_close = round(quote["price"] / (1 + quote["change_pct"] / 100.0), 2)
            except ZeroDivisionError:
                prev_close = None
        # 分时线:优先 1 分钟(getMinLine, 仅当日, 行=[时间,现价,均价,量,持仓...]),
        # 失败/为空时回退 5 分钟(getFewMinLine, 多日 dict 结构, 取最后一日连续段)
        base = "https://stock2.finance.sina.com.cn/futures/api/jsonp.php"
        minute: list[dict] = []
        interval = "5"
        date_str = ""
        def _jsonp(url: str) -> list | None:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("gbk", errors="replace")
            m = re.search(r"\((\[.*\])\)", body, re.S)
            return json.loads(m.group(1)) if m else None
        rows = _jsonp(f"{base}/var%20data=/InnerFuturesNewService.getMinLine?symbol={symbol}&type=1")
        if isinstance(rows, list) and rows and isinstance(rows[0], list) and len(rows[0]) >= 2:
            # 1 分钟行: [HH:MM, 现价, 均价, 成交量, 持仓量, ...]
            minute = [{"t": str(r[0]), "v": float(r[1])} for r in rows if str(r[0]).count(":") == 1]
            interval = "1"
        else:
            rows = _jsonp(f"{base}/var%20data=/InnerFuturesNewService.getFewMinLine?symbol={symbol}&type=5")
            if isinstance(rows, list) and rows:
                last_day = str(rows[-1].get("d", ""))[:10]
                minute = [
                    {"t": str(r.get("d", ""))[11:16], "v": float(r["c"])}
                    for r in rows if str(r.get("d", "")).startswith(last_day)
                ]
        # 日 K(升序) → 近 120 根
        daily: list[dict] = []
        rows2 = _jsonp(f"{base}/var%20data=/InnerFuturesNewService.getDailyKLine?symbol={symbol}")
        if isinstance(rows2, list) and rows2:
            daily = [
                {"d": r["d"], "o": float(r["o"]), "h": float(r["h"]),
                 "l": float(r["l"]), "c": float(r["c"]), "v": int(float(r["v"]))}
                for r in rows2[-120:]
            ]
        if minute or daily:
            # 分时日期: 分时只有当日序列, 日期取实时行情日期(盘后/非交易时兜底今天)
            day = ""
            if quote and quote.get("date"):
                day = str(quote["date"])
            if len(day) < 8:
                day = time.strftime("%Y-%m-%d")
            result = {
                "code": symbol,
                "prev_close": prev_close,
                "date": day,
                "interval": interval,
                "minute": minute,
                "daily": daily,
            }
    except Exception as e:
        logger.warning("sina future market fail (%s): %s", dataset, e)
    if result is not None:
        _FUT_MARKET_CACHE[dataset] = (now, result)
    return result


@app.get("/api/industry/future-market")
async def industry_future_market(dataset: str = "lithium"):
    """KPI 主力卡行情图数据：当日分时(5分钟) + 近120根日K + 昨结。"""
    await _wait_excel_ready()
    data = _fetch_sina_future_market(dataset)
    if data is None:
        return {"ok": False, "code": FUTURE_SINA_CODES.get(dataset, "").replace("nf_", "")}
    return {"ok": True, **data}


# ── 各合约成交持仓（仓单日报下方的 Excel 成交持仓汇总表）──
# 中文月份词(不含"月", 与标题"一月合约"拼接时再加"月合约"; 长词在前防前缀截断)。
# 注意: 词表为降序(十二→一), 映射必须按 12-index, 否则 五月/八月 等全部镜像错位。
_CONTRACT_MONTH_WORDS = ["十二", "十一", "十", "九", "八", "七", "六", "五", "四", "三", "二", "一"]
_CONTRACT_MONTH_NUM = {w: f"{len(_CONTRACT_MONTH_WORDS) - i:02d}" for i, w in enumerate(_CONTRACT_MONTH_WORDS)}
_CONTRACT_RE = "主力合约|" + "|".join(w + "月合约" for w in _CONTRACT_MONTH_WORDS)
# 合约乘数(吨/手): 成交额(元) = 当日成交量(手)×最新价×乘数 的近似估算(严格口径应取当日加权均价)。
# 碳酸锂(广期所)=1、锡(上期所)=1、多晶硅(广期所)=3、工业硅(广期所)=5。
_PRODUCT_MULTIPLIER = {"碳酸锂": 1, "锡": 1, "多晶硅": 3, "工业硅": 5}


def _build_positions(dataset: str) -> dict | None:
    """从目录聚合 各合约成交持仓：每品种(族)一行一合约, 含 收盘价/成交量/持仓量/成交持仓比。

    标题形态: "GFEX: 碳酸锂: 主力合约: 收盘价: 日度" / "碳酸锂主力合约成交持仓比"。
    排除期现价差/基差/月差等衍生指标；合约集 = 存在 成交量或持仓量 的合约(主力 + 活跃月份)。
    """
    charts = _SOURCE_CHARTS.get(dataset) or []
    by_key: dict[tuple[str, str, str], dict] = {}  # (product, contract, type) -> chart
    types = [("成交持仓比", "ratio"), ("持仓量", "oi"), ("成交量", "vol"), ("收盘价", "price")]
    products: dict[str, dict] = {}
    for c in charts:
        t = c.get("title", "")
        # 排除期现价差/基差/月差/连X 等衍生指标（成交持仓比标题不含这些词）
        if any(k in t for k in ("期现", "价差", "基差", "月差", "连")):
            continue
        m = re.search(r"^(?:GFEX|SHFE|DCE|CZCE)\s*[:：]\s*([^:：]+?)\s*[:：]\s*(" + _CONTRACT_RE + r")\s*[:：]", t)
        contract_raw = None
        product = None
        if m:
            product = m.group(1).strip()
            contract_raw = m.group(2)
        else:
            m2 = re.search(r"^([^:：\s]+?)(" + _CONTRACT_RE + r")成交持仓比", t)
            if m2:
                product = m2.group(1).strip()
                contract_raw = m2.group(2)
            else:
                continue
        type_key = None
        for kw, key in types:
            if kw in t:
                type_key = key
                break
        if type_key is None:
            continue
        contract = "主力" if "主力" in contract_raw else _CONTRACT_MONTH_NUM.get(contract_raw.replace("月合约", ""), contract_raw)
        if not product or not contract:
            continue
        by_key[(product, contract, type_key)] = c
        products.setdefault(product, {"date": ""})
    # 组装
    groups = []
    for product in products:
        contracts: dict[str, dict] = {}
        for (p, contract, type_key), c in by_key.items():
            if p != product:
                continue
            if type_key in ("vol", "oi"):
                contracts.setdefault(contract, {"contract": contract, "date": None, "price": None, "vol": None, "oi": None, "ratio": None, "d_vol": None, "d_oi": None, "turnover": None})
        for (p, contract, type_key), c in by_key.items():
            if p != product or contract not in contracts:
                continue
            data = c.get("data") or []
            if len(data) < 2:
                continue
            v0 = data[0].get("value")
            v1 = data[1].get("value")
            row = contracts[contract]
            try:
                if type_key == "price":
                    row["price"] = float(v0)
                    row["date"] = row["date"] or data[0].get("date", "")
                elif type_key == "vol":
                    row["vol"] = float(v0)
                    row["d_vol"] = float(v0) - float(v1) if v1 is not None else None
                elif type_key == "oi":
                    row["oi"] = float(v0)
                    row["d_oi"] = float(v0) - float(v1) if v1 is not None else None
                    row["date"] = row["date"] or data[0].get("date", "")
                elif type_key == "ratio":
                    row["ratio"] = float(v0)
            except (TypeError, ValueError):
                continue
        rows = [r for r in contracts.values() if r["vol"] is not None or r["oi"] is not None]
        # 成交持仓比：Excel 缺该指标行时按 当日成交量/持仓量 兜底计算，保证每个合约都有统一口径的比值；
        # 成交额(资金, 元) = 成交量(手)×最新价×合约乘数(吨/手)，为最新价近似口径
        mult = _PRODUCT_MULTIPLIER.get(product, 1)
        for r in rows:
            if r["ratio"] is None and r["vol"] is not None and r["oi"]:
                r["ratio"] = round(r["vol"] / r["oi"], 4)
            if r["turnover"] is None and r["vol"] is not None and r["price"] is not None:
                r["turnover"] = round(r["vol"] * r["price"] * mult, 0)
        rows.sort(key=lambda r: (r["contract"] != "主力", r["contract"]))
        if rows:
            groups.append({"product": product, "date": products[product].get("date", ""), "rows": rows})
    return {"ok": bool(groups), "groups": groups}


@app.get("/api/industry/positions")
async def industry_positions(dataset: str = "lithium"):
    """各合约成交持仓汇总（Excel 目录聚合）：收盘价/成交量/持仓量/成交持仓比。"""
    await _wait_excel_ready()
    data = _build_positions(dataset)
    if not data or not data["ok"]:
        return {"ok": False, "groups": []}
    return data


# ── 各合约成交持仓 · 实时模式（新浪公开行情, 具体上市月合约）──
# 代码规则: nf_<品种字母><YYMM>（如 nf_LC2701 = 碳酸锂2027年1月）;
# 新浪 44 段字段: [0]名称 [8]最新价 [10]昨结 [13]当日成交量 [14]持仓量 [17]行情日期。
FUTURE_CONTRACT_LETTERS = {
    "lithium": [("碳酸锂", "LC")],
    "tin": [("锡", "SN")],
    "silicon": [("多晶硅", "PS"), ("工业硅", "SI")],
}
_LIVE_POS_TTL = 15.0  # 秒级内存缓存(前端 30s 轮询, 防频控)
_LIVE_POS_CACHE: dict[str, tuple[float, dict | None]] = {}
_POS_SNAPSHOT_FILE = CACHE_DIR / "positions_live_snapshot.json"


def _roll_yyyymm(base: str, n: int = 13) -> list[str]:
    """base 'YYYY-MM' → 该月起连续 n 个月的 YYMM（如 2026-09 → 2609,2610,…,2709）。"""
    y, m = int(base[:4]), int(base[5:7])
    return [f"{(y + (m + i - 1) // 12) % 100:02d}{(m + i - 1) % 12 + 1:02d}" for i in range(n)]


def _sina_contract_quotes(codes: list[str]) -> dict[str, dict]:
    """批量拉具体月合约行情（新浪 hq）。返回 code -> {price, vol, oi, date, time}。"""
    out: dict[str, dict] = {}
    for i in range(0, len(codes), 40):
        chunk = codes[i:i + 40]
        try:
            url = "https://hq.sinajs.cn/list=" + ",".join(chunk)
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("gbk", errors="replace")
        except Exception as e:
            logger.warning("sina contract quotes fail: %s", e)
            continue
        for line in raw.strip().splitlines():
            if "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].replace("var hq_str_", "").strip()
            vals = line.split('"')[1].split(",")
            if len(vals) < 18 or key not in chunk:
                continue
            try:
                price, prev = float(vals[8]), float(vals[10])
                vol, oi = float(vals[13]), float(vals[14])
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out[key] = {"price": price, "vol": vol, "oi": oi, "date": vals[17], "time": vals[1]}
    return out


def _load_pos_snapshot() -> dict:
    try:
        if _POS_SNAPSHOT_FILE.exists():
            return json.loads(_POS_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _maybe_save_pos_snapshot(groups: list[dict], date: str):
    """本地时间 ≥15:30 时把当日 量/仓 存档（供次日计算日增减），同日只存一次。"""
    try:
        lt = time.localtime()
        if lt.tm_hour < 15 or (lt.tm_hour == 15 and lt.tm_min < 30):
            return
        snap = _load_pos_snapshot()
        if snap.get("date") == date:
            return
        rows: dict[str, dict] = {}
        for g in groups:
            for r in g["rows"]:
                if r.get("vol") is not None and r.get("oi") is not None:
                    rows[f"{g['product']}:{r['contract']}"] = {"vol": r["vol"], "oi": r["oi"]}
        _POS_SNAPSHOT_FILE.write_text(
            json.dumps({"date": date, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("positions snapshot save fail: %s", e)


def _fetch_positions_live(dataset: str) -> dict | None:
    """实时成交持仓: 各上市月合约 最新价/当日量/持仓(新浪)。主力 = 当前持仓最大合约。"""
    now_t = time.time()
    cached = _LIVE_POS_CACHE.get(dataset)
    if cached and now_t - cached[0] < _LIVE_POS_TTL:
        return cached[1]
    products = FUTURE_CONTRACT_LETTERS.get(dataset)
    if not products:
        return None
    # 基准月: 从主力连续行情日期取(新浪行情日期=最新交易日)
    base = time.strftime("%Y-%m-%d")
    try:
        mc = FUTURE_SINA_CODES.get(dataset, "")
        if mc:
            q0 = _fetch_sina_future_quotes([mc]).get(mc)
            if q0 and q0.get("date"):
                base = str(q0["date"])
    except Exception:
        pass
    yymms = _roll_yyyymm(base[:7])
    snap = _load_pos_snapshot()
    snap_rows = snap.get("rows", {})
    groups: list[dict] = []
    quote_time = ""
    for pname, letter in products:
        codes = [f"nf_{letter}{yy}" for yy in yymms]
        quotes = _sina_contract_quotes(codes)
        if not quotes:
            continue
        rows: list[dict] = []
        for yy in yymms:
            qq = quotes.get(f"nf_{letter}{yy}")
            if not qq:
                continue
            vol, oi = qq["vol"], qq["oi"]
            if not quote_time:
                quote_time = qq.get("time", "")
            prev = snap_rows.get(f"{pname}:{yy}")
            d_vol = round(vol - prev["vol"], 0) if prev and vol is not None else None
            d_oi = round(oi - prev["oi"], 0) if prev and oi is not None else None
            ratio = round(vol / oi, 4) if vol is not None and oi and oi > 0 else None
            mult = _PRODUCT_MULTIPLIER.get(pname, 1)
            turnover = round(vol * qq["price"] * mult, 0) if vol is not None else None
            rows.append({
                "contract": yy, "price": qq["price"],
                "vol": vol if vol else 0.0, "oi": oi if oi else 0.0,
                "ratio": ratio, "turnover": turnover,
                "d_vol": d_vol, "d_oi": d_oi,
            })
        if rows:
            groups.append({"product": pname, "date": base, "rows": rows})
    if not groups:
        return None
    result = {"ok": True, "groups": groups, "interval": "live", "time": quote_time, "date": base}
    _maybe_save_pos_snapshot(groups, base)
    _LIVE_POS_CACHE[dataset] = (now_t, result)
    return result


@app.get("/api/industry/positions-live")
async def industry_positions_live(dataset: str = "lithium"):
    """各合约成交持仓（实时）：最新价/当日成交量/持仓量 来自新浪公开行情, 主力=持仓最大合约。
    日增减来自本地每日收盘快照（收盘后自动存档, 接入当日增减为 null 显示 —）。"""
    data = _fetch_positions_live(dataset)
    if data is None:
        return {"ok": False, "groups": []}
    return data


# ── 各机构成交持仓（交易所会员持仓排名, 收盘后日度; akshare 封装交易所官网）──
# 数据形态与交易所/东财一致: 成交量 / 多头持仓 / 空头持仓 三栏各自独立排名(每行会员不同)。
# 仅收盘后公布: 盘中请求自动回退到上一交易日(节假日未处理, 连续失败再向前回退)。
_INSTITUTION_TTL = 1800.0
_INSTITUTION_CACHE: dict[str, tuple[float, dict | None]] = {}
_INSTITUTION_PRODUCTS = {
    "lithium": [("碳酸锂", "LC")],
    "tin": [("锡", "SN")],
    "silicon": [("多晶硅", "PS"), ("工业硅", "SI")],
}
_ak_imported = False
_ak_error: str | None = None


def _prev_trading_date8(base: str, steps: int) -> str:
    """从 base(YYYY-MM-DD) 向前回退 steps 天并跳过周末, 返回 YYYYMMDD。"""
    from datetime import date, timedelta
    d = date.fromisoformat(base) - timedelta(days=steps)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def _fetch_institution_positions(dataset: str) -> dict | None:
    """机构(会员)成交持仓排名: 广期所(锂/硅)/上期所(锡) → 各品种主力合约三栏式排名。"""
    global _ak_imported, _ak_error
    now_t = time.time()
    cached = _INSTITUTION_CACHE.get(dataset)
    if cached and now_t - cached[0] < _INSTITUTION_TTL:
        return cached[1]
    if not _ak_imported:
        try:
            import akshare  # noqa: PLC0415 — lazy import: 避免拖慢启动
            global ak  # noqa: PLW0603
            ak = akshare
            _ak_imported = True
        except Exception as e:  # noqa: BLE001
            _ak_error = f"akshare import failed: {e}"
    if not _ak_imported:
        logger.warning("institution positions unavailable: %s", _ak_error)
        return None
    products = _INSTITUTION_PRODUCTS.get(dataset)
    if not products:
        return None
    # 基准日: 实时行情日期(交易日); 若为今天且未收盘(15:30 前)排名用上一交易日
    base = time.strftime("%Y-%m-%d")
    try:
        mc = FUTURE_SINA_CODES.get(dataset, "")
        if mc:
            q0 = _fetch_sina_future_quotes([mc]).get(mc)
            if q0 and q0.get("date"):
                base = str(q0["date"])
    except Exception:
        pass
    lt = time.localtime()
    today = time.strftime("%Y-%m-%d")
    # 若今天尚未收盘(15:30 前), 当日排名还没公布 → 基准日先减一天
    if base == today and (lt.tm_hour < 15 or (lt.tm_hour == 15 and lt.tm_min < 30)):
        from datetime import date, timedelta
        base = (date.fromisoformat(base) - timedelta(days=1)).isoformat()
    result: dict | None = None
    last_err: str | None = None
    for attempt in range(6):
        date8 = _prev_trading_date8(base, attempt)
        try:
            if dataset == "tin":
                raw = ak.get_shfe_rank_table(date=date8, vars_list=["SN"])
            else:
                raw = ak.futures_gfex_position_rank(date=date8, vars_list=[p[1] for p in products])
            if isinstance(raw, dict) and raw:
                groups = _parse_institution_raw(raw, date8)
                if groups:
                    result = {"ok": True, "groups": groups, "date": date8, "source": "交易所会员持仓排名"}
                    break
            last_err = f"empty at {date8}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{date8}: {type(e).__name__}"
            continue
    if result is None:
        logger.warning("institution positions fail (%s): %s", dataset, last_err)
    _INSTITUTION_CACHE[dataset] = (now_t, result)
    return result


def _parse_institution_raw(raw: dict, date8: str) -> list[dict]:
    """dict(合约小写→df) → 按产品分组, 只保留组内持仓最大(主力)合约, 取前 12 名。"""
    letter_to_name = {letter: cname for lst in _INSTITUTION_PRODUCTS.values() for cname, letter in lst}
    dfs_by_variety: dict[str, list] = {}
    for key, df in raw.items():
        if not hasattr(df, "columns") or df.empty:
            continue
        variety = str(df["variety"].iloc[0]).upper()
        dfs_by_variety.setdefault(variety, []).append(df)
    groups: list[dict] = []
    for variety, dfs in dfs_by_variety.items():
        # 主力合约 = 多空持仓之和最大(交易所 df 无持仓总量列, 以 多+空 近似)
        def total_oi(d):
            return float(d["long_open_interest"].sum()) + float(d["short_open_interest"].sum())
        main_df = max(dfs, key=total_oi)
        sym = str(main_df["symbol"].iloc[0]).upper()
        name = letter_to_name.get(variety, variety)
        rows = []
        for _, r in main_df.head(12).iterrows():
            rows.append({
                "rank": int(r["rank"]),
                "vol_member": str(r["vol_party_name"]),
                "vol": float(r["vol"]),
                "vol_chg": _num(r, "vol_chg"),
                "long_member": str(r["long_party_name"]),
                "long_oi": float(r["long_open_interest"]),
                "long_chg": _num(r, "long_open_interest_chg"),
                "short_member": str(r["short_party_name"]),
                "short_oi": float(r["short_open_interest"]),
                "short_chg": _num(r, "short_open_interest_chg"),
            })
        if rows:
            groups.append({"product": name, "contract": sym, "date": date8, "rows": rows})
    return groups


def _num(r, col):
    try:
        v = r.get(col)
        return float(v) if v is not None and str(v) not in ("", "nan", "None") else None
    except (TypeError, ValueError):
        return None


@app.get("/api/industry/institution-positions")
async def industry_institution_positions(dataset: str = "lithium"):
    """各机构成交持仓(交易所会员排名, 收盘后数据): 主力合约的 成交量/多单/空单 三栏 Top12。"""
    data = _fetch_institution_positions(dataset)
    if data is None:
        return {"ok": False, "groups": []}
    return data


def _resolve_source(tab: str, sector: str | None) -> str | None:
    """Determine which data source a request is targeting."""
    TAB_TO_SOURCE = {"锡": "tin", "硅": "silicon", "锂": "lithium"}
    TIN_SECTORS = {"锡矿", "锡锭", "锡材", "锡下游"}
    SI_SECTORS = {"工业硅", "有机硅", "多晶硅", "硅片", "电池片", "组件", "光伏辅材", "铝合金"}
    LITHIUM_SECTORS = {
        "锂矿", "锂盐", "碳酸锂", "氢氧化锂", "其他锂盐", "三元正极", "钴酸锂", "锰酸锂",
        "磷酸铁锂", "磷化工链", "负极材料", "隔膜", "电解液产业链", "辅材", "电池电芯",
        "储能", "新能源汽车", "其他",
    }
    if sector:
        if sector in TIN_SECTORS:
            return "tin"
        if sector in SI_SECTORS:
            return "silicon"
        if sector in LITHIUM_SECTORS:
            return "lithium"
    if tab:
        if tab in TIN_SECTORS:
            return "tin"
        if tab in SI_SECTORS:
            return "silicon"
        if tab in LITHIUM_SECTORS:
            return "lithium"
        if tab in TAB_TO_SOURCE:
            return TAB_TO_SOURCE[tab]
    return None


@app.get("/api/debug/sources")
async def debug_sources():
    """Debug endpoint to check loaded data sources."""
    return {
        "tin_sectors": sorted(list(_TIN_SECTORS)),
        "silicon_sectors": sorted(list(_SILICON_SECTORS)),
        "lithium_sectors": sorted(list(_LITHIUM_SECTORS)),
        "source_sectors": {k: sorted(list(v)) for k, v in _SOURCE_SECTORS.items()},
        "source_chart_counts": {k: len(v) for k, v in _SOURCE_CHARTS.items()},
        "all_charts": len(_excel_cache.get("__all__", {}).get("charts", [])),
    }


@app.get("/api/index-quotes")
async def get_index_quotes():
    IO = ["sh000001", "sz399001", "sh000300", "sz399006", "sh000688", "bj899050"]
    IM = {"sh000001": "上证指数", "sz399001": "深证成指", "sh000300": "沪深300",
          "sz399006": "创业板指", "sh000688": "科创50", "bj899050": "北证50"}
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://qt.gtimg.cn/q=" + ",".join(IO),
                headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as resp:
            raw = resp.read().decode("gbk")
        bc = {}
        for line in raw.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            bc[key] = {"code": key, "name": IM.get(key, vals[1]),
                       "price": float(vals[3]) if vals[3] else 0,
                       "change_pct": float(vals[32]) if vals[32] else 0,
                       "amount_yi": round(float(vals[37]) / 10000, 2) if vals[37] else 0}
        return {"indices": [bc[c] for c in IO if c in bc], "updated_at": datetime.now().isoformat()}
    except Exception as e:
        logger.warning("idx fail: %s", e)
        return {"indices": [], "updated_at": datetime.now().isoformat()}


# 腾讯历史 K 线接口：ifzq.gtimg.cn / web.ifzq.gtimg.cn 均会间歇性返回 501（风控），
# 使用 proxy.finance.qq.com 正式代理接口（newfqkline），返回 qfqday 格式兼容。
KLINE_API = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"


def _stock_pfx(code: str) -> str:
    # 北交所: 8 开头(原精选层 83/87/88…)与 920 段(2024 新代码); 9 开头其他(如 B 股)仍为 sh
    if code.startswith("8") or code.startswith("92"):
        return "bj"
    return "sh" if code.startswith(("6", "9")) else "sz"


def _fetch_klines(code: str, params: str) -> list:
    """拉取腾讯 K 线，返回 [[date, close], ...]；失败返回 []。params 如 'day,,,20,qfq' 或 'day,2022-01-01,,1500,qfq'。"""
    try:
        pfx = _stock_pfx(code)
        url = f"{KLINE_API}?param={pfx}{code},{params}"
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}), timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("data", {}).get(f"{pfx}{code}", {})
        klines = data.get("qfqday") or data.get("day") or []
        return [[k[0], float(k[2])] for k in klines if len(k) >= 3]
    except Exception as e:
        logger.warning("kline fail %s: %s", code, e)
        return []


def _fetch_sparkline(item):
    # 只返回 sparkline 数组，不要返回 item 自身（否则 zip 赋值时形成自引用环）
    return [row[1] for row in _fetch_klines(item["code"], "day,,,20,qfq")[-20:]]


def _fetch_fund_flows(codes: list[str]) -> dict[str, float | None]:
    """东财 ulist 批量资金流：当日主力净流入（元 -> 亿，保留 2 位）。

    东财 push2/push2his 对 urllib/requests 的 OpenSSL TLS 指纹风控（连接被断开），
    新浪资金流并发拉取触发 456 限流；用 curl_cffi 模拟浏览器 TLS 指纹直连东财，
    一次批量请求查最多 100 只（177 只 = 2 个请求，约 0.7s）。
    """
    flows: dict[str, float | None] = {}
    secids = [("1." if c.startswith(("6", "9")) else "0.") + c for c in codes]
    # 经典 TLS 指纹可用（最新 "chrome" 指纹会被东财识别风控），失败时轮换指纹重试
    impersonates = ["chrome110", "edge101", "safari15_5"]
    for i in range(0, len(secids), 100):
        chunk = ",".join(secids[i:i + 100])
        url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?secids={chunk}&fields=f12,f14,f62&fltt=2"
        for attempt in range(3):
            try:
                r = crequests.get(
                    url,
                    impersonate=impersonates[attempt % len(impersonates)],
                    headers={"Referer": "https://data.eastmoney.com/"},
                    timeout=10,
                )
                d = r.json()
                for item in (d.get("data") or {}).get("diff") or []:
                    code = item.get("f12")
                    f62 = item.get("f62")
                    if code and f62 not in (None, "-"):
                        try:
                            flows[code] = round(float(f62) / 1e8, 2)
                        except (TypeError, ValueError):
                            flows[code] = None
                break
            except Exception as e:
                if attempt == 2:
                    logger.warning("flow fail chunk: %s", e)
                time.sleep(0.3)
    return flows


# 资金流内存缓存：同一股票池 60 秒内直接返回，避免频繁刷新触发东财风控
_flow_cache: dict[str, tuple[float, dict]] = {}
_FLOW_CACHE_TTL = 60


@app.post("/api/stocks/flow")
async def stocks_flow(payload: WatchlistRequest):
    """个股当日主力净流入（亿），POST {stocks: [...]} -> {"flows": {code: 亿 or null}}

    带 60 秒缓存：多次刷新不会重复请求东财，降低风控触发概率。
    """
    key = ",".join(sorted(set(payload.stocks or [])))
    now = time.time()
    cached = _flow_cache.get(key)
    if cached and now - cached[0] < _FLOW_CACHE_TTL:
        return {"flows": cached[1], "cached": True}
    flows = _fetch_fund_flows(payload.stocks or [])
    _flow_cache[key] = (now, flows)
    return {"flows": flows, "cached": False}


@app.post("/api/watchlist")
async def get_watchlist(payload: WatchlistRequest):
    result = {"stocks": []}
    if not payload.stocks:
        return result
    pf = [_stock_pfx(c) + c for c in [s.strip() for s in payload.stocks]]
    try:
        with urllib.request.urlopen(urllib.request.Request(
                "https://qt.gtimg.cn/q=" + ",".join(pf),
                headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as resp:
            raw = resp.read().decode("gbk")
        for line in raw.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = line.split("=")[0].split("_")[-1][2:]
            result["stocks"].append({
                "code": code, "name": vals[1],
                "price": float(vals[3]) if vals[3] else 0,
                "last_close": float(vals[4]) if vals[4] else 0,
                "open": float(vals[5]) if vals[5] else 0,
                "high": float(vals[33]) if vals[33] else 0,
                "low": float(vals[34]) if vals[34] else 0,
                "change_pct": float(vals[32]) if vals[32] else 0,
                "turnover_pct": float(vals[38]) if vals[38] else 0,
                # 成交量（手），腾讯 qt 字段 index 6
                "volume": int(float(vals[6])) if vals[6] else 0,
                "amount_yi": round(float(vals[37]) / 10000, 2) if vals[37] else 0,
                "pe_ttm": float(vals[39]) if vals[39] else 0,
                "pb": float(vals[46]) if vals[46] else 0,
                "float_mcap_yi": float(vals[44]) if vals[44] else 0,
                "mcap_yi": float(vals[45]) if vals[45] else 0,
                "limit_up": float(vals[47]) if vals[47] else 0,
                "limit_down": float(vals[48]) if vals[48] else 0,
                "sparkline": [],
            })
    except Exception as e:
        logger.warning("wl fail: %s", e)
        return result
    if payload.sparkline:
        with ThreadPoolExecutor(max_workers=10) as pool:
            for item, spark in zip(result["stocks"], pool.map(_fetch_sparkline, result["stocks"])):
                item["sparkline"] = spark
    return result


@app.post("/api/battery/market-data")
async def battery_market_data(payload: MarketDataRequest):
    result = {"stocks": []}
    # 覆盖全部股票池（与核心标的池一致），上限保护 200 只
    codes = [c.strip() for c in payload.stocks[:200]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for code, rows in zip(codes, pool.map(lambda c: _fetch_klines(c, "day,2022-01-01,,1500,qfq"), codes)):
            result["stocks"].append({
                "code": code, "name": "",
                "klines": [{"date": r[0], "value": r[1]} for r in rows],
            })
    return result


def _fetch_financials(code: str):
    """拉取单只股票财务（东方财富业绩报表 RPT_LICO_FN_CPD，营收/净利润近 24 期），失败返回 []。

    新浪财务接口（quotes.sina.cn CompanyFinanceService）并发拉取会触发 456 限流，
    改用东财 datacenter 业绩报表：TOTAL_OPERATE_INCOME 营业总收入(元)、PARENT_NETPROFIT
    归母净利润(元)、YSTZ/SJLTZ 同比(百分比数值，除以 100 转小数)。
    """
    try:
        c = code.strip()
        filter_ = f'(SECURITY_CODE="{c}")'
        url = ("https://datacenter.eastmoney.com/securities/api/data/v1/get"
               f"?reportName=RPT_LICO_FN_CPD&columns=ALL&filter={quote(filter_)}"
               "&pageNumber=1&pageSize=30&source=WEB&client=WEB")
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}), timeout=15) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        rows = (d.get("result") or {}).get("data") or []
        periods = []
        for obj in rows[:24]:
            rd = (obj.get("REPORTDATE") or "")[:10]
            if not rd:
                continue
            rec = {"period": rd}
            rev = obj.get("TOTAL_OPERATE_INCOME")
            profit = obj.get("PARENT_NETPROFIT")
            if rev not in (None, ""):
                try:
                    rec["营业总收入"] = float(rev) / 1e8
                except (TypeError, ValueError):
                    pass
                yoy = obj.get("YSTZ")
                if yoy not in (None, ""):
                    try:
                        rec["营业总收入_yoy"] = float(yoy) / 100.0
                    except (TypeError, ValueError):
                        pass
            if profit not in (None, ""):
                try:
                    rec["净利润"] = float(profit) / 1e8
                except (TypeError, ValueError):
                    pass
                yoy = obj.get("SJLTZ")
                if yoy not in (None, ""):
                    try:
                        rec["净利润_yoy"] = float(yoy) / 100.0
                    except (TypeError, ValueError):
                        pass
            if "营业总收入" in rec:
                periods.append(rec)
        return periods
    except Exception as e:
        logger.warning("fin fail %s: %s", code, e)
        return []


@app.post("/api/battery/financials")
async def battery_financials(payload: FinancialsRequest):
    result = {"stocks": []}
    # 覆盖全部股票池（与核心标的池一致），上限保护 200 只，并发拉取
    codes = [c.strip() for c in payload.stocks[:200]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for code, periods in zip(codes, pool.map(_fetch_financials, codes)):
            result["stocks"].append({"code": code, "periods": periods})
    return result


# 产业新闻按行业关键词过滤（快讯标题或摘要命中任一关键词即保留）。
# 各行业独立词表：锡/硅 抓各自相关新闻，锂电保持历史混合词表（含光伏硅词）。
NEWS_KEYWORDS = {
    "lithium": ["锂电", "锂", "锂电池", "储能", "新能源车", "新能源汽车", "电动车",
                "动力电池", "电池", "碳酸锂", "正极", "负极", "隔膜", "电解液",
                "铜箔", "固态电池", "钠电池", "宁德", "比亚迪", "光伏", "风电", "充电桩", "工业硅", "有机硅", "多晶硅", "硅片", "隆基", "通威", "合盛硅业", "晶澳"],
    "tin": ["沪锡", "焊料", "镀锡板", "马口铁", "锡锭", "锡矿", "锡精矿", "锡材", "锡价", "锡业", "铅蓄电池", "铅酸电池"],
    "silicon": ["多晶硅", "单晶硅", "硅片", "硅料", "有机硅", "工业硅", "光伏", "电池片", "组件", "硅价", "硅业", "硅烷", "隆基", "通威", "合盛硅业", "晶澳"],
}


@app.get("/api/overview/news")
async def overview_news(industry: str | None = None):
    kw = NEWS_KEYWORDS.get(industry or "lithium", NEWS_KEYWORDS["lithium"])
    try:
        # 东财快讯接口强制要求 req_trace 参数（缺失返回 data=null），任意值即可；
        # 快讯为滚动流（约 4 小时窗口），用 sortEnd 游标翻页取近 7 天
        begin = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        items = []
        sort_end = ""
        for _ in range(30):
            req_trace = str(time.time())
            url = (f"https://np-weblist.eastmoney.com/comm/web/getFastNewsList?client=web&biz=web_724"
                   f"&fastColumn=102&sortEnd={sort_end}&pageSize=500&req_trace={req_trace}")
            with urllib.request.urlopen(urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://kuaixun.eastmoney.com/"}), timeout=15) as resp:
                data = json.loads(resp.read()).get("data") or {}
            batch = data.get("fastNewsList") or []
            if not batch:
                break
            items.extend(batch)
            sort_end = data.get("sortEnd") or ""
            oldest = (batch[-1].get("showTime") or "")[:10]
            if not sort_end or oldest < begin:
                break
    except Exception:
        return {"news": []}
    # 标题或摘要命中关键词均保留（部分产业新闻标题不含关键词但摘要相关，如"中标锂电项目"）
    matched = []
    for it in items:
        title = it.get("title", "")
        summary = it.get("summary", "")
        if any(k in title for k in kw) or any(k in summary for k in kw):
            # 快讯无 url 字段，详情页为 https://finance.eastmoney.com/a/{code}.html
            # （kuaixun.eastmoney.com 格式返回 404）
            matched.append({"title": title or summary[:80],
                            "date": (it.get("showTime") or "")[:10],
                            "source": "东方财富",
                            "url": f"https://finance.eastmoney.com/a/{it.get('code', '')}.html"})
    # 按天分组、每天最多 2 条：快讯按时间倒序，若直接取前 15 条会全被当天的新闻占满，
    # 近一周内更早的产业新闻永远显示不到
    by_date: dict[str, list] = {}
    for m in matched:
        by_date.setdefault(m["date"], []).append(m)
    result = []
    for date in sorted(by_date, reverse=True):
        result.extend(by_date[date][:2])
    return {"news": result[:20]}


@app.get("/api/overview/reports")
async def overview_reports():
    begin = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    all_reports = []
    for page in range(1, 6):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    f"https://reportapi.eastmoney.com/report/list?industryCode=*&pageSize=100&industry=*&rating=*&ratingChange=*&beginTime={begin}&endTime=2030-01-01&pageNo={page}&fields=&qType=1",
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}), timeout=30) as resp:
                rows = json.loads(resp.read()).get("data") or []
            if not rows:
                break
            all_reports.extend(rows)
        except Exception:
            break
    kw = ["锂电", "锂电池", "储能", "新能源车", "动力电池", "碳酸锂",
          "正极", "负极", "隔膜", "电解液", "铜箔", "固态电池", "钠电池", "工业硅", "有机硅", "多晶硅", "硅片", "组件"]
    matched = [{"title": r.get("title", ""), "date": (r.get("publishDate") or "")[:10],
                "org": r.get("orgSName", ""),
                "url": f"https://pdf.dfcfw.com/pdf/H3_{r.get('infoCode', '')}_1.pdf"}
               for r in all_reports if any(k in r.get("title", "") for k in kw)]
    matched.sort(key=lambda x: x["date"], reverse=True)
    return {"reports": matched[:15]}


def _fetch_reports_for_code(code: str, begin: str):
    """拉取单只股票近 begin 起的研报（东方财富），返回 [raw_row, ...]；失败返回 []。"""
    rows_out = []
    try:
        for page in range(1, 4):
            params = f"industryCode=*&pageSize=50&industry=*&rating=*&ratingChange=*&beginTime={begin}&endTime=2030-01-01&pageNo={page}&fields=&qType=0&code={code}"
            with urllib.request.urlopen(urllib.request.Request(
                    f"https://reportapi.eastmoney.com/report/list?{params}",
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}), timeout=30) as resp:
                d = json.loads(resp.read())
            rows = d.get("data") or []
            if not rows:
                break
            rows_out.extend(rows)
    except Exception:
        pass
    return rows_out


@app.post("/api/battery/reports")
async def battery_reports(payload: ReportRequest):
    if not payload.stocks:
        return {"reports": [], "tab": payload.tab}
    # 按细分板块分组：每个板块取市值前 10 只（payload.stocks 已按 环节+板块+市值 排序），
    # 多板块股票（如盐湖股份=锂矿+锂盐）同时占用各板块名额；去重后并发拉取。
    begin = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    targets = _load_stock_targets()
    meta = {}
    # 按交集大小选择 source：不同产业链股票池可能有重叠（如兴发集团同时属硅/锂电），
    # 取与请求股票交集最大的 source，避免误匹配到其他产业链的板块映射
    best_overlap = 0
    for src_meta in targets.get("stocks", {}).values():
        overlap = sum(1 for c in payload.stocks if c in src_meta)
        if overlap > best_overlap:
            best_overlap = overlap
            meta = src_meta
    per_sector_count: dict = {}
    codes_to_query = []
    seen_codes = set()
    for code in payload.stocks:
        subs = (meta.get(code) or {}).get("subs") or []
        if not subs:
            subs = ["其他"]
        if any(per_sector_count.get(s, 0) < 10 for s in subs):
            for s in subs:
                per_sector_count[s] = per_sector_count.get(s, 0) + 1
            if code not in seen_codes:
                seen_codes.add(code)
                codes_to_query.append(code)
    codes_to_query = codes_to_query[:120]  # 上限保护
    logger.info("reports query %d stocks (per-sector top 10), sectors=%s",
                len(codes_to_query), dict(per_sector_count))

    all_reports = []
    seen = set()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for code, rows in zip(codes_to_query, pool.map(
                lambda c: _fetch_reports_for_code(c, begin), codes_to_query)):
            for r in rows:
                ic = r.get("infoCode", "")
                if ic and ic not in seen:
                    seen.add(ic)
                    all_reports.append({"date": (r.get("publishDate") or "")[:10],
                                        "org": r.get("orgSName", ""),
                                        "title": r.get("title", ""),
                                        "infoCode": ic,
                                        "stockName": r.get("stockName", code)})
    all_reports.sort(key=lambda x: x["date"], reverse=True)
    return {"reports": all_reports[:50], "tab": payload.tab}


@app.post("/api/battery/analyze")
async def battery_analyze(payload: BatteryAnalyzeRequest, request: Request):
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="LLM API key not configured")
    industry = payload.industry or _detect_industry(payload.tab, request.headers.get("referer", ""))
    industry_names = {
        "lithium": "锂电池产业链",
        "tin": "锡产业链",
        "silicon": "硅产业链",
    }
    industry_name = industry_names.get(industry, "锂电池产业链")
    stock_lines = [f"{s.code} {s.name} {s.price} {'+' if s.change_pct > 0 else ''}{s.change_pct:.2f}%"
                   for s in payload.stocks[:15]]
    stock_text = "\n".join(stock_lines) if stock_lines else "暂无标的"
    prompt = f"""你是{industry_name}研究专家。请分析「{payload.tab}」板块当前状态。
板块标的实时行情：
{stock_text}
请从以下5个维度评分（1-10分），每个维度给一句话理由：
1. 供需格局 - 供过于求(1)到供不应求(10)
2. 价格趋势 - 价格下行(1)到上行(10)
3. 库存周期 - 累库(1)到去库(10)
4. 资金关注 - 资金流出(1)到流入(10)
5. 政策催化 - 利空(1)到利好(10)
然后生成结构化板块点评（基于板块标的实时行情，具体到个股/涨跌幅）：
- verdict：一句话判断板块状态与主导逻辑（25-40字）
- key_points：2-3 条关键逻辑，每条 title（≤8字，如"龙头放量"）+ text（≤45字，含个股与数据）
- outlook：一句话前瞻判断（≤35字）
- conclusion：将上述整合成连贯完整的段落（100-200字，供全文展示）
严格按JSON格式返回：
{{"scores":[{{"dimension":"维度名","score":8,"reason":"一句话理由"}},...],
  "conclusion":"完整结论段落",
  "summary":{{"verdict":"...","key_points":[{{"title":"...","text":"..."}}],"outlook":"..."}}}}"""
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps({"model": "deepseek-chat",
                             "messages": [{"role": "user", "content": prompt}],
                             "temperature": 0.3, "max_tokens": 2000}).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        raw = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw[raw.index("\n") + 1:raw.rindex("```")].strip()
        data = json.loads(raw)
        summary_raw = data.get("summary")
        summary = None
        if isinstance(summary_raw, dict):
            points = []
            for p in summary_raw.get("key_points") or []:
                if isinstance(p, dict):
                    points.append(
                        {"title": str(p.get("title", "")), "text": str(p.get("text", ""))}
                    )
            summary = {
                "verdict": str(summary_raw.get("verdict", "")),
                "key_points": points[:4],
                "outlook": str(summary_raw.get("outlook", "")),
            }
        return {
            "tab": payload.tab,
            "scores": data.get("scores", []),
            "conclusion": data.get("conclusion", ""),
            "summary": summary,
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="AI returned invalid JSON")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/sector/quick-analysis")
async def sector_quick_analysis(payload: SectorQuickAnalysisRequest):
    """板块速评：参考板块简评（/api/battery/analyze）的 DeepSeek 调用方式，
    输入为板块指标速览摘要（前端压缩后的文本行），输出 100-200 字简洁点评。
    token 控制：输入文本有长度上限（截断防御），输出 max_tokens=400。"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="LLM API key not configured")
    industry_names = {
        "lithium": "锂电池产业链",
        "tin": "锡产业链",
        "silicon": "硅产业链",
    }
    industry_name = industry_names.get(payload.industry or "", "")
    text = (payload.metrics_text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="指标摘要为空")
    if len(text) > 12000:
        text = text[:12000] + "\n(数据已截断)"
    if payload.kind == "warehouse":
        # 仓单日报速评（kind=warehouse）：分层全量数据（全国总量→量价→地区汇总→仓库明细）
        prompt = f"""你是{industry_name}研究专家，请系统性点评「{payload.sector}」当前状况。

仓单数据为分层结构（单位：手；环比 = 最新 vs 前1/5/21个交易日，数字即百分比，如 "日+0.6 周+3.2 月-15.1"）。**一律以输入数据为准：输入出现哪些行才分析哪些，未出现的指标（如成交量/持仓量/成交持仓比/量价行——公开 API 快照通常只含仓单量）绝不提及或臆测。**
数据形态可能为以下两种之一：
- 本地Excel：首行为日期与单位说明；全国总量行后可能有 成交量/持仓量/成交持仓比 量价行；【地区】汇总 行（如"【上海】汇总 6796 | …"）后跟该地区全部仓库明细行（0 手仓库也列出，零仓单同样有意义）；
- 公开API：仅当日仓单快照 + 近30交易日历史（各地区按仓库行附带省名），可能不含【地区】汇总行与量价行。

{text}

要求：
1. 先判断整体累库/去库状态与节奏（全国总量与各行的日/周/月环比；公开 API 口径= 5/21 个交易日前）；
2. 再分析地区分化：哪个地区主导累库/去库，落到具体仓库（点名 2-4 个变化最大的仓库，用数字支撑；零仓单仓库如值得说明也提）；
3. 若数据包含 成交量/持仓量/成交持仓比 量价行：结合其变化给出供需与价格含义的前瞻；若未包含（如仅仓单量快照），跳过该维度，绝不虚构成交持仓分析；
4. 有条理、层次分明，全文 150-250 字，不客套。

严格输出 JSON（不要 markdown 代码块、不要任何额外文字）：
{{"verdict": "一句话判断仓单整体状态与主导逻辑（25-40字）",
  "points": [{{"metric": "仓库/地区/量价名", "change": "最新值与环比数据（如：10627手，周环比+17.6%）", "comment": "一句话点评（≤30字）"}}],
  "outlook": "一句话前瞻判断（≤35字）"}}"""
    elif payload.kind == "positions":
        # 各合约+机构成交持仓速评（kind=positions）：合约级量仓 + 交易所会员排名
        prompt = f"""你是{industry_name}研究专家，请系统性点评「各合约成交持仓」当前状况。

第一部分·合约级数据（成交量/持仓量单位：手；成交额=成交量×最新价×合约乘数(吨/手)的近似值；增减=最新 vs 前一日；成交持仓比=当日成交量/持仓量，按百分数显示）：
【品种】为该品种小节，其后行为合约行，字段：合约 最新价 | 量(手, 日增减) 仓(手, 日增减) 比% 额。
合约以到期月代码表示（如 2701），持仓量最大者为主力，标注为 主力(2701)。

第二部分·各机构成交持仓（若提供；交易所会员持仓排名, 数据截至标题日期）：
每行三栏独立排名（同行机构可能不同），字段：名次 | 量:成交量第N名会员 量(较前日) | 多:多头持仓第N名会员 多单量(较前日) | 空:空头持仓第N名会员 空单量(较前日)。

{text}

要求：
1. 先点评整体参与度：主力合约的量/仓/成交持仓比及日增减，判断资金进场还是离场；
2. 再点评月份结构：持仓向哪些月份集中、近远月活跃差异，点名 2-4 个变化最大的合约并用数字支撑；
3. 结合量仓同向/背离（量增仓增=新资金进场、量增仓减=短线离场、量缩仓增=锁仓观望等）给出价格含义前瞻；
4. 若提供机构排名：点评多头/空头头部会员是谁、多空力量对比与集中度（头部席位增减方向、净多/净空倾向），1-2 条即可，不逐条罗列；
5. 有条理、层次分明，全文 200-300 字，不客套。

严格输出 JSON（不要 markdown 代码块、不要任何额外文字）：
{{"verdict": "一句话判断市场参与度与资金行为的主导逻辑（25-40字）",
  "points": [{{"metric": "合约/量仓/机构", "change": "最新值与日增减（如：175248手 +9421；中信期货多30191 +53）", "comment": "一句话点评（≤30字）"}}],
  "outlook": "一句话前瞻判断（≤35字）"}}"""
    elif payload.kind == "market_overview":
        # 主力期货总体分析(kind=market_overview): 盘面实时 + 分时 + 日K窗口 + 主力持仓
        prompt = f"""你是{industry_name}研究专家，请对「{payload.sector}」做一份总体分析(盘面+技术+资金)。

输入分四节(数字即口径, 不要自行虚构本节没有的维度):
- 实时行情: 现价/涨跌%/昨结/今开/当日高/低;
- 当日分时要点: 现价位于当日区间的百分位、早盘/午盘极值时间等(若给出);
- 日K窗口: 近5/10/20日涨跌幅、近60日区间高低与现价回撤幅度、近10日收盘序列;
- 主力持仓: 主力合约量/仓/成交比(当日)与增减(若有)。

{text}

要求：
1. 先给一句话定性: 当前位置(区间高低/近期趋势)与短期动能;
2. 分时层面 1 条(当日强弱、与昨结/日高的距离);
3. 趋势与技术 1-2 条(用近5/10/20日涨跌与回撤支撑, 不给未提供的指标下结论);
4. 资金/持仓 1 条(量仓增减与成交比含义);
5. 前瞻 1 句; 全文 180-280 字, 不客套、不重复。

严格输出 JSON（不要 markdown 代码块、不要任何额外文字）：
{{"verdict": "一句话定性当前位置与主导逻辑（25-40字）",
  "points": [{{"metric": "维度/项目", "change": "数值（如：现价141400 -0.46%；近20日+3.2%）", "comment": "一句话点评（≤30字）"}}],
  "outlook": "一句话前瞻判断（≤35字）"}}"""
    else:
        prompt = f"""你是{industry_name}研究专家，请点评「{payload.sector}」板块当前状况。

板块指标速览数据，两种行格式：
- 单指标行：指标名（单位）: 最新值(日期) | 日/周环比 | 月环比 | 近5期走势（↑涨 ↓跌 →平）
- 族对比行：同一指标族的多条路线用 " | " 横向并列（如产量分盐湖/锂云母/锂辉石/回收，成本分不同外购原料），括号内为日/周环比
{text}

要求：
1. 综合各指标走势与环比，判断板块所处状态（强势/回暖/走弱/分化等）与主导逻辑；
2. 覆盖主要维度：价格、成本利润、库存、供给/需求，每维度点评 1-2 条，共 4-6 个要点；
3. 族对比行：族内路线分化明显时（有的涨有的跌、或部分亏损）务必横向对比指出谁强谁弱，不要只挑一条路线；
4. 用具体数据支撑，不逐条罗列；结尾给一句前瞻判断；
5. 简洁高效，不要客套语。

严格输出 JSON（不要 markdown 代码块、不要任何额外文字）：
{{"verdict": "一句话判断板块状态并说明主导逻辑（25-40字）",
  "points": [{{"metric": "指标名", "change": "最新值与变化数据（如：7650元/吨，月环比+8.4%）", "comment": "一句话点评（≤30字）"}}],
  "outlook": "一句话前瞻判断（≤30字）"}}"""
    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500,
            }).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        raw = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw[raw.index("\n") + 1:raw.rindex("```")].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # AI 未按 JSON 返回：降级为纯文本（前端原样渲染）
            return {"sector": payload.sector, "verdict": "", "points": [], "outlook": "", "raw": raw}
        points = []
        for p in data.get("points") or []:
            if isinstance(p, dict):
                points.append({
                    "metric": str(p.get("metric", "")),
                    "change": str(p.get("change", "")),
                    "comment": str(p.get("comment", "")),
                })
        return {
            "sector": payload.sector,
            "verdict": str(data.get("verdict", "")),
            "points": points[:6],
            "outlook": str(data.get("outlook", "")),
            "raw": "",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except Exception:
            full_path, stat_result = self.lookup_path("index.html")
            if full_path:
                return FileResponse(full_path, stat_result=stat_result)
            raise HTTPException(status_code=404, detail="index not found")


if FRONTEND_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
    print(f"[frontend] SPA loaded from {FRONTEND_DIST}")
else:
    print(f"[warn] Frontend dist not found at {FRONTEND_DIST}")


def main():
    print("market dashboard API Server")
    print("http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
