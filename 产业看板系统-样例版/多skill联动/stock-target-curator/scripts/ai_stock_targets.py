# -*- coding: utf-8 -*-
"""Skill3 AI 个股筛选：按细分板块调用 DeepSeek 筛选代表性上市公司并附筛选原因。

- 候选池（config/stock_targets.json 的 stocks）作为提示词参考，AI 可从中筛选
  也可补充自己确定代码准确的公司；
- --provider mock：直接输出候选池（reason 取备注），用于离线验证流程；
- --provider deepseek：真实调用 DeepSeek，输出 AI 筛选原因；
- 结果按「产业|板块」缓存到 SQLite（--force-refresh 强制重筛）；
- 输出列：序号 | 产业链 | 细分板块 | 所属环节 | 股票名称 | 股票代码 | 总市值(亿) | AI筛选原因
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stock_targets import HEADERS, write_xlsx  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(r"C:\Users\11\Documents\Selecting skill\.env"))
except Exception:
    pass

DEFAULT_MAX_TOKENS = int(os.getenv("DEEPSEEK_MAX_TOKENS", "8000"))
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "120"))
DEFAULT_MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))
# DeepSeek key 等配置（与 ai_assisted_curation 同源）
try:
    from dotenv import load_dotenv

    load_dotenv(Path(r"C:\Users\11\Documents\Selecting skill\.env"))
except Exception:
    pass

# 统一 observability adapter（唯一 Langfuse 接触层，best-effort）。
# 直接加载 workflow/observability.py，避免触发 workflow/__init__（其 import cli）。
import importlib.util  # noqa: E402

_OBS_SPEC = importlib.util.spec_from_file_location(
    "workflow_observability",
    str(Path(__file__).resolve().parents[3] / "workflow" / "observability.py"),
)
observability = importlib.util.module_from_spec(_OBS_SPEC)
assert _OBS_SPEC and _OBS_SPEC.loader
_OBS_SPEC.loader.exec_module(observability)


DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
PROMPT_VERSION = "stock_targets_v1"

# 系统提示模板（供 observability 计算稳定 prompt_hash）
STOCK_TARGETS_SYSTEM_PROMPT = "你是严谨的A股产业链个股筛选助手，只输出用户要求的严格JSON。"

# 板块业务描述（AI 提示词依据；同时给出默认所属环节）
SEGMENT_DESCRIPTIONS = {
    "lithium": {
        "锂矿锂盐": ("锂辉石/锂云母/盐湖卤水等锂矿资源开采、锂精矿，以及碳酸锂、氢氧化锂等锂盐冶炼加工", "中游-锂盐"),
        "三元正极": ("三元前驱体与三元正极材料（NCM/NCA）生产", "中游-正极材料"),
        "磷酸铁锂正极": ("磷酸铁、磷酸铁锂（LFP/LMFP）正极材料生产", "中游-正极材料"),
        "负极": ("人造/天然石墨负极材料生产", "中游-负极材料"),
        "隔膜": ("湿法/干法锂电隔膜生产", "中游-隔膜"),
        "电解液": ("电解液及六氟磷酸锂、溶剂、添加剂生产", "中游-电解液"),
        "铜箔铝箔": ("锂电铜箔、铝箔及复合集流体生产", "中游-铜箔铝箔"),
        "电池&电芯": ("动力/储能/消费锂离子电池电芯与PACK生产", "下游-电池电芯"),
        "储能&集成": ("储能系统集成、PCS逆变器、储能电池", "下游-储能系统"),
        "新能源车": ("新能源汽车整车与核心零部件", "下游-整车"),
    },
    "silicon": {
        "工业硅": ("工业硅冶炼", "上游-工业硅"),
        "有机硅": ("有机硅单体及下游", "上游-有机硅"),
        "多晶硅": ("多晶硅料生产", "中游-多晶硅"),
        "硅片": ("单晶硅片拉棒切片", "中游-硅片"),
        "电池片": ("光伏电池片", "中游-电池片"),
        "组件": ("光伏组件", "下游-组件"),
        "光伏辅材": ("光伏玻璃、胶膜、背板、逆变器等辅材", "下游-光伏辅材"),
        "铝合金": ("铝加工及铝材", "下游-铝合金"),
    },
    "tin": {
        "锡矿": ("锡矿采选", "上游-锡矿"),
        "锡锭": ("锡冶炼", "中游-冶炼"),
        "锡材": ("锡材深加工", "中游-深加工"),
        "锡下游": ("锡下游制品及再生", "下游-再生及制品"),
    },
}


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def segment_candidates(config: dict, industry: str, segment: str) -> list[dict]:
    return [
        stock for stock in config.get("stocks", [])
        if stock.get("industry") == industry and stock.get("segment") == segment
    ]


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for i, stock in enumerate(candidates, 1):
        cap = str(stock.get("market_cap") or "未知")
        lines.append(
            f"{i}. {stock.get('name')}（{stock.get('code')}，总市值约{cap}亿元，"
            f"备注：{stock.get('note') or '无'}）"
        )
    return "\n".join(lines)


def build_prompt(
    industry_meta: dict,
    segment: str,
    candidates: list[dict],
    min_count: int,
    max_count: int,
) -> str:
    description, default_stage = SEGMENT_DESCRIPTIONS.get(
        industry_meta.get("key", ""), {}
    ).get(segment, ("", "中游"))
    industry_name = industry_meta["name"]
    return (
        f"你是A股产业链研究专家。请为「{industry_name}」的细分板块「{segment}」"
        f"筛选代表性上市公司。\n\n"
        f"板块业务范围：{description}。\n\n"
        f"参考候选池（可从中筛选，也可补充你确定股票代码准确的其他公司）：\n"
        f"{_format_candidates(candidates) or '（无）'}\n\n"
        f"筛选标准（覆盖全面、有理有据）：\n"
        f"1. 覆盖尽可能全面：输出该板块主要上市公司，数量尽量接近 {max_count} 只"
        f"（不少于 {min_count} 只）；除行业龙头外，还应覆盖第二梯队、细分领域特色公司"
        f"（如细分产品、区域龙头、重要新进入者），只要业务相关且有实际布局即可入选；\n"
        f"2. 相关性要求：主营业务或核心业务与该板块直接相关，有实际业务布局"
        f"（产能、资源、客户等可查证）；多元化公司只要相关业务有明确规模即可入选，"
        f"并在原因中说明该业务情况；\n"
        f"3. 每只股票的筛选原因（25~50字）必须包含至少一个具体事实依据（如：XX万吨产能、"
        f"市占率第X、XX万吨资源储量、深度绑定XX客户、XX技术路线领先等），"
        f"禁止只用\"行业领先\"\"龙头地位\"\"前景广阔\"等无具体事实支撑的表述；\n"
        f"4. 股票代码必须准确（6位数字），不确定代码的公司不要输出；\n"
        f"5. 总市值（market_cap）为亿元人民币整数近似值，可参考候选池中的市值；\n"
        f"6. 股票名称（name）必须使用交易所证券简称（如\"华友钴业\"\"宁德时代\"），\n"
        f"   禁止使用公司注册全称（如\"浙江华友钴业股份有限公司\"）；\n"
        f"7. 只输出严格JSON，不要任何多余文字：\n"
        f'{{"stocks":[{{"name":"证券简称","code":"6位代码","market_cap":123,'
        f'"reason":"筛选原因"}}]}}'
    )


def call_deepseek(prompt: str, model: str = DEFAULT_MODEL, span=None) -> dict:
    from openai import OpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")
    client = OpenAI(api_key=api_key, base_url=base_url,
                    timeout=DEFAULT_TIMEOUT_SECONDS, max_retries=0)
    messages = [
        {"role": "system", "content": STOCK_TARGETS_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    # prompt_hash：系统提示模板的稳定 SHA-256（动态 candidates 不进 hash）
    prompt_hash = observability.prompt_fingerprint(STOCK_TARGETS_SYSTEM_PROMPT)
    last_error: Exception | None = None
    for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
        try:
            response = observability.completion(
                lambda: client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=DEFAULT_MAX_TOKENS,
                ),
                model=model,
                messages=messages,
                prompt_name="stock_targets",
                prompt_version=PROMPT_VERSION,
                prompt_hash=prompt_hash,
                extra_metadata={"segment_prompt": bool(prompt)},
                span=span,
            )
            content = response.choices[0].message.content or "{}"
            payload = json.loads(content)
            if isinstance(payload.get("stocks"), list) and payload["stocks"]:
                return payload
            raise ValueError("response missing non-empty stocks list")
        except Exception as exc:
            last_error = exc
            if attempt < DEFAULT_MAX_RETRIES:
                time.sleep(min(30, 1.5 ** attempt))
    raise RuntimeError(f"DeepSeek stock selection failed: {last_error}")


def normalize_stock(item: dict, candidates: dict[str, dict]) -> dict | None:
    name = str(item.get("name") or "").strip()
    code = str(item.get("code") or "").strip()
    reason = str(item.get("reason") or "").strip()
    if not name or not re.fullmatch(r"\d{6}", code):
        return None
    # 原因过短视为敷衍/无依据，宁缺勿滥
    if len(reason) < 8:
        return None
    try:
        cap = float(str(item.get("market_cap") or 0) or 0)
        if not math.isfinite(cap):
            cap = 0.0
    except (TypeError, ValueError):
        cap = 0.0
    candidate = candidates.get(code)
    stage = str(candidate.get("stage") or "") if candidate else ""
    return {
        "name": name,
        "code": code,
        "market_cap": cap,
        "reason": reason or (str(candidate.get("note") or "") if candidate else "AI筛选"),
        "stage": stage,
    }


def mock_selection(candidates: list[dict]) -> list[dict]:
    """mock provider：输出候选池，reason 取备注。"""
    result = []
    seen = set()
    for stock in candidates:
        code = str(stock.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append({
            "name": str(stock.get("name") or "").strip(),
            "code": code,
            "market_cap": float(stock.get("market_cap") or 0),
            "reason": f"候选池参考：{stock.get('note') or ''}",
            "stage": str(stock.get("stage") or "").strip(),
        })
    return result


# ---- SQLite 缓存 ----

def init_cache(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute(
        """CREATE TABLE IF NOT EXISTS ai_stock_targets_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    con.commit()
    return con


def cache_get(con: sqlite3.Connection, key: str):
    row = con.execute(
        "SELECT payload_json FROM ai_stock_targets_cache WHERE cache_key=?",
        (key,),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def cache_set(con: sqlite3.Connection, key: str, payload: list[dict], provider: str, model: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO ai_stock_targets_cache "
        "(cache_key, payload_json, provider, model, created_at) VALUES (?,?,?,?,?)",
        (key, json.dumps(payload, ensure_ascii=False), provider, model,
         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    con.commit()


# ---- 主流程 ----

def select_for_segment(
    config: dict, industry: str, segment: str, provider: str,
    con: sqlite3.Connection, force_refresh: bool, stats: "observability.StageStats | None" = None,
    span=None,
) -> list[dict]:
    cache_key = f"{industry}|{segment}"
    if not force_refresh:
        cached = cache_get(con, cache_key)
        if cached is not None:
            if stats is not None:
                stats.hit()
            return cached

    candidates = segment_candidates(config, industry, segment)
    if provider == "mock":
        stocks = mock_selection(candidates)
    else:
        if stats is not None:
            stats.call()
        industry_meta = config["industries"][industry]
        req = config.get("requirements", {}).get(industry, {})
        prompt = build_prompt(
            {**industry_meta, "key": industry}, segment, candidates,
            int(req.get("min_per_segment", 5)),
            int(req.get("max_per_segment", 20)),
        )
        payload = call_deepseek(prompt, span=span)
        candidate_map = {str(s.get("code") or "").strip(): s for s in candidates}
        stocks = []
        seen = set()
        for item in payload.get("stocks", []):
            norm = normalize_stock(item, candidate_map)
            if norm and norm["code"] not in seen:
                seen.add(norm["code"])
                stocks.append(norm)

    cache_set(con, cache_key, stocks, provider, DEFAULT_MODEL if provider != "mock" else "mock")
    return stocks


def run(
    industry: str,
    provider: str,
    config_path: Path,
    output: Path,
    database: Path,
    force_refresh: bool,
) -> int:
    config = load_config(config_path)
    industry_meta = config["industries"].get(industry)
    if not industry_meta:
        print(f"Unsupported industry: {industry}", file=sys.stderr)
        return 2

    database.parent.mkdir(parents=True, exist_ok=True)
    con = init_cache(database)
    segments = industry_meta["segments"]
    by_segment: dict[str, list[dict]] = {}
    total = 0
    stage_stats = observability.StageStats()
    stage_stats.items_total = len(segments)
    with observability.stage_span("stock_targets") as _span:
        for segment in segments:
            stocks = select_for_segment(config, industry, segment, provider, con, force_refresh, stats=stage_stats, span=_span)
            if not stocks:
                print(f"  {segment}: 0 stocks", file=sys.stderr)
                continue
            # 板块内按市值降序（市值相同按代码升序保持稳定）
            stocks.sort(key=lambda s: (-s["market_cap"], s["code"]))
            by_segment[segment] = stocks
            total += len(stocks)
            print(f"  {segment}: {len(stocks)} 只")
        if _span is not None:
            try:
                _span.update(metadata=stage_stats.to_metadata())
            except Exception:
                pass
    con.close()

    rows = []
    for segment in segments:
        default_stage = SEGMENT_DESCRIPTIONS.get(industry, {}).get(segment, ("", ""))[1]
        for stock in by_segment.get(segment, []):
            rows.append({
                "industry": industry_meta["name"],
                "segment": segment,
                "stage": stock["stage"] or default_stage,
                "name": stock["name"],
                "code": stock["code"],
                "cap": stock["market_cap"],
                "reason": stock["reason"],
            })

    if not rows:
        print(f"No stocks selected for {industry}", file=sys.stderr)
        return 2
    write_xlsx(rows, output)
    print(f"Industry={industry} provider={provider} stocks={total} output={output}")
    observability.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI stock selection for an industry chain.")
    parser.add_argument("--industry", choices=["silicon", "tin", "lithium"], required=True)
    parser.add_argument("--provider", choices=["mock", "deepseek"], default="mock")
    parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "config" / "stock_targets.json",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--database", default=None,
                        help="AI 结果缓存 db；默认与输出同目录 stock_targets_ai_cache.db")
    parser.add_argument("--force-refresh", action="store_true",
                        help="忽略缓存强制重新筛选")
    args = parser.parse_args(argv)

    output = Path(args.output).resolve()
    database = Path(args.database).resolve() if args.database else (
        output.parent / "stock_targets_ai_cache.db"
    )
    return run(args.industry, args.provider, Path(args.config), output, database, args.force_refresh)


if __name__ == "__main__":
    raise SystemExit(main())
