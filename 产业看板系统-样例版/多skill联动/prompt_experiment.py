# -*- coding: utf-8 -*-
"""Phase 3：Prompt Management + Dataset Experiment（最小可复现闭环）。

链路：Prompt version（Langfuse）→ Dataset（classification/human_confirmed）
→ 离线 Experiment（v1 baseline vs v2 candidate，同模型同参数）→ 确定性
Evaluator → Comparison report。

原则：
- 不修改生产 workflow / tracing / correlation / evaluation / Skill 规则 / Skill4
- 不自动推 production：即使 v2 更优也只输出 PROMOTE_RECOMMENDED / DO_NOT_PROMOTE
- 不在代码中删除生产 Prompt（v1 从生产代码读取注册；v2 是显式候选）
- dynamic input（items/candidates）不进入 Prompt 版本定义

用法：
  python scripts/prompt_experiment.py --register          # 注册 v1/v2 到 Langfuse（幂等）
  python scripts/prompt_experiment.py --verify            # 检查 prompts 与 dataset
  python scripts/prompt_experiment.py --experiment        # 跑实验（默认 dry-run 报告）
  python scripts/prompt_experiment.py --experiment --apply  # 真实 LLM 调用
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(Path(os.getenv("SELECTING_ENV", r"C:\Users\11\Documents\Selecting skill\.env")))
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

PROMPT_NAME = "ai_disambiguation"
LABEL_V1 = "baseline"
LABEL_V2 = "candidate"
LABEL_V3 = "candidate3"
SCHEMA_VERSION = "1.0"
V2_CHANGE_REASON = "强化候选硬约束与输出 schema 明确性（最小可解释改动，验证实验系统）"
V2_CHANGE_SUMMARY = (
    "在 v1 基础上增加两句约束：候选限制是硬约束（候选为空时保持原分类）；"
    "输出必须完全符合 JSON schema，不得输出额外字段。"
)
V3_CHANGE_REASON = (
    "多候选时优先判断指标整体经济含义（核心变量性质），再以关键词辅助；"
    "针对候选选择错误（PROMPT_SELECTION_ERROR）改进（基于 v1，不继承 v2）"
)
V3_CHANGE_SUMMARY = (
    "基于 v1 增加：先判断指标整体变量性质，再使用名称关键词辅助；"
    "名称含价格/现货等词不得默认价格类；进出口盈亏/进口盈亏/出口盈亏/"
    "进口利润/出口利润/进口成本/出口成本等组合指标先判断整体性质；"
    "必须从候选分类组合中选择，候选为空保持原分类；输出 schema 完全不变。"
)

# deepseek-chat 估算单价（$ / 1M tokens；非官方计费，标记 estimated）
DEFAULT_INPUT_COST_PER_1M = float(os.getenv("DEEPSEEK_INPUT_COST_PER_1M", "0.27"))
DEFAULT_OUTPUT_COST_PER_1M = float(os.getenv("DEEPSEEK_OUTPUT_COST_PER_1M", "1.10"))


# ── Prompt 盘点（从生产代码读取，不做任何修改）────────────────

def _load_production_module():
    spec = importlib.util.spec_from_file_location(
        "ai_assisted_curation",
        str(PROJECT_ROOT / "scripts" / "ai_assisted_curation.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def production_prompt_info() -> dict:
    """当前生产 ai_disambiguation Prompt 盘点（stable template + dynamic 区分）。"""
    mod = _load_production_module()
    system_prompt = mod.AI_DISAMBIGUATION_SYSTEM_PROMPT
    return {
        "name": PROMPT_NAME,
        "system_prompt": system_prompt,
        "prompt_version": mod.PROMPT_VERSION,
        "prompt_hash": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "temperature": 0,
        "response_format": "json_object",
        "max_tokens": int(os.getenv("DEEPSEEK_MAX_TOKENS", "32000")),
        "max_retries": int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
        "dynamic_fields": ["items", "provider", "model"],  # 不进 Prompt identity
    }


def build_v2_system_prompt(v1_system_prompt: str) -> str:
    """候选 v2：最小可解释改动（候选硬约束 + schema 明确性）。"""
    return v1_system_prompt + (
        "候选限制是硬约束：即使你认为存在更合适的分类，也必须从候选范围内选择；"
        "候选为空时保持原分类不变。输出必须完全符合上述 JSON schema，"
        "不得输出任何额外字段。"
    )


def build_v3_system_prompt(v1_system_prompt: str) -> str:
    """候选 v3（基于 v1，不继承 v2）：先判断整体经济含义，再以关键词辅助。

    紧凑无长解释，避免 token / latency 上升；输出 schema 完全不变。
    """
    return v1_system_prompt + (
        "优先判断指标的整体经济含义（核心变量性质），再以名称关键词辅助判断。"
        "名称含“价格/现货”等词时不得默认价格类；对“进出口盈亏/进口盈亏/出口盈亏/"
        "进口利润/出口利润/进口成本/出口成本”等组合指标，先判断其整体变量性质"
        "（如成本利润），再从候选分类组合中选择。候选为空时保持原分类不变。"
    )


def build_chat_messages(system_prompt: str, item: dict, prompt_version: str, model: str) -> list[dict]:
    """与生产调用等价的 messages 结构（system stable + user dynamic items）。"""
    user_payload = {
        "provider": "deepseek",
        "model": model,
        "prompt_version": prompt_version,
        "items": [item],
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
    ]


def experiment_item_from_dataset(ds_item: dict) -> dict:
    """dataset item → 实验 item（映射到生产 item schema；candidates 不伪造）。

    Phase 3b 起：enriched item 的 input 携带 production candidates（候选分类组合）
    与 current_major/current_sub —— 完整复现生产 ai_disambiguation 输入结构。
    """
    inp = ds_item.get("input") or {}
    tags = dict(inp.get("current_tags") or {})
    if inp.get("candidates"):
        tags["候选分类组合"] = inp["candidates"]
    return {
        "variable_id": str(inp.get("physical_variable_id") or ""),
        "name": str(inp.get("original_name") or ""),
        "sheet": str(inp.get("sheet") or ""),
        "unit": str(inp.get("unit") or ""),
        "frequency": str(inp.get("frequency") or ""),
        "sector": str(inp.get("industry") or ""),
        "current_major": str(inp.get("current_major") or ""),
        "current_sub": str(inp.get("current_sub") or ""),
        "current_tags": tags,
    }


# ── Langfuse 访问 ──────────────────────────────────────────

def _make_client():
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        base_url=os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com"),
        environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
        debug=False,
    )


def register_prompts(client=None, dry_run: bool = False) -> dict:
    """把生产 Prompt 注册为 v1（baseline），创建候选 v2（candidate）。幂等 upsert。"""
    client = client or _make_client()
    info = production_prompt_info()
    v1_messages = build_chat_messages(info["system_prompt"], {}, info["prompt_version"], info["model"])
    v2_text = build_v2_system_prompt(info["system_prompt"])
    v2_messages = build_chat_messages(v2_text, {}, "ai_disambiguation_v2_candidate", info["model"])
    meta = {
        "source": "code_baseline",
        "original_prompt_version": info["prompt_version"],
        "original_prompt_hash": info["prompt_hash"],
        "schema_version": SCHEMA_VERSION,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    v2_meta = {
        **meta,
        "change_reason": V2_CHANGE_REASON,
        "change_summary": V2_CHANGE_SUMMARY,
    }
    if dry_run:
        return {
            "name": PROMPT_NAME, "dry_run": True,
            "v1": {"messages": v1_messages, "labels": [LABEL_V1, "v1"], "config": meta},
            "v2": {"messages": v2_messages, "labels": [LABEL_V2, "v2"], "config": v2_meta},
        }
    p1 = client.create_prompt(
        name=PROMPT_NAME, prompt=v1_messages, type="chat",
        labels=[LABEL_V1, "v1"], config=meta,
        commit_message="register production baseline v1 (code)",
    )
    p2 = client.create_prompt(
        name=PROMPT_NAME, prompt=v2_messages, type="chat",
        labels=[LABEL_V2, "v2"], config=v2_meta,
        commit_message="candidate v2: candidate hard-constraint + schema clarity",
    )
    v3_text = build_v3_system_prompt(info["system_prompt"])
    v3_messages = build_chat_messages(v3_text, {}, "ai_disambiguation_v3_candidate", info["model"])
    v3_meta = {
        **meta,
        "change_reason": V3_CHANGE_REASON,
        "change_summary": V3_CHANGE_SUMMARY,
        "based_on": "v1",
    }
    p3 = client.create_prompt(
        name=PROMPT_NAME, prompt=v3_messages, type="chat",
        labels=[LABEL_V3, "v3"], config=v3_meta,
        commit_message="candidate v3: overall-semantics-first, schema unchanged (based on v1)",
    )
    return {"name": PROMPT_NAME,
            "v1_version": getattr(p1, "version", "?"), "v2_version": getattr(p2, "version", "?"),
            "v3_version": getattr(p3, "version", "?"),
            "v1_labels": [LABEL_V1, "v1"], "v2_labels": [LABEL_V2, "v2"],
            "v3_labels": [LABEL_V3, "v3"]}


def load_prompt(client, label: str) -> dict:
    """从 Langfuse 按 label 拉 Prompt（证明 Prompt Management 链路可用）。

    compile() 返回 chat message dict 列表；get_langchain_prompt() 返回
    (role, content) 元组（Langchain 格式）——统一规范化为 {"role","content"}。
    """
    pc = client.get_prompt(PROMPT_NAME, label=label, type="chat")
    raw = pc.compile()
    msgs: list[dict] = []
    for m in raw:
        if isinstance(m, dict) and m.get("type") == "placeholder":
            continue  # 无占位符注册场景
        if isinstance(m, dict) and "content" in m:
            msgs.append({"role": str(m.get("role") or m.get("type") or "system"),
                         "content": m["content"]})
    return {
        "label": label,
        "version": getattr(pc, "version", "?"),
        "messages": msgs,
        "config": getattr(pc, "config", None),
    }


def load_dataset_items(client, dataset_name: str = "classification/human_confirmed") -> list[dict]:
    ds = client.get_dataset(dataset_name)
    out = []
    for item in ds.items:
        out.append({"id": item.id, "input": item.input or {},
                    "expected_output": item.expected_output or {},
                    "metadata": item.metadata or {}})
    return out


# ── Dataset eligibility ────────────────────────────────────

def check_eligibility(items: list[dict]) -> dict:
    """eligibility 分层（Phase 3b）：expected_output 有大类且 input 有名称才可评估。

    - production_equivalent：有真实生产 candidates/context（enriched）
    - historical_reconstructed：可较高可信重建（本数据集当前为 0，留给未来）
    - context_limited：仍缺关键上下文（无 candidates），可评估但不具生产等价性
    - ineligible：无期望/无名称
    """
    eligible, ineligible = [], []
    for it in items:
        expected = it["expected_output"]
        inp = it["input"]
        reasons = []
        if not str(expected.get("大类") or "").strip():
            reasons.append("NO_EXPECTED_MAJOR")
        if not str(inp.get("original_name") or "").strip():
            reasons.append("NO_INPUT_NAME")
        if reasons:
            ineligible.append({"id": it["id"], "physical_variable_id": inp.get("physical_variable_id"),
                               "reasons": reasons})
            continue
        md = it.get("metadata") or {}
        eligibility = md.get("eligibility") or (
            "production_equivalent" if inp.get("candidates") else "context_limited"
        )
        eligible.append({
            **it,
            "eligibility": eligibility,
            "context_limited": eligibility == "context_limited",
            "expected_sub_present": bool(str(expected.get("子类") or "").strip()),
        })
    return {"eligible": eligible, "ineligible": ineligible}


# ── Deterministic Evaluator ────────────────────────────────

class Evaluator:
    """确定性分类正确性判定：expected 大类/子类 vs model major/sub。

    normalization：strip + 折叠连续空白（全角/半角空格）。子类在 expected 缺失时
    不判错（不评估 是否选中 —— 不在模型输出 schema 内）。
    """

    @staticmethod
    def normalize(value) -> str:
        import re

        return re.sub(r"\s+", "", str(value or "")).strip()

    def evaluate(self, expected: dict, model_output: dict) -> bool:
        exp_major = self.normalize(expected.get("大类"))
        out_major = self.normalize(model_output.get("major"))
        if not exp_major or out_major != exp_major:
            return False
        exp_sub = self.normalize(expected.get("子类"))
        if exp_sub:
            return self.normalize(model_output.get("sub")) == exp_sub
        return True

    def evaluate_with_detail(self, expected: dict, model_output: dict) -> dict:
        return {
            "correct": self.evaluate(expected, model_output),
            "expected_major": self.normalize(expected.get("大类")),
            "expected_sub": self.normalize(expected.get("子类")),
            "output_major": self.normalize(model_output.get("major")),
            "output_sub": self.normalize(model_output.get("sub")),
        }


# ── 输出解析 / 变化分类 ────────────────────────────────────

def parse_classification_output(content: str) -> dict:
    """解析模型 JSON 输出 → {major, sub}；解析失败返回空（判 incorrect）。"""
    try:
        payload = json.loads(content)
    except Exception:  # noqa: BLE001
        return {}
    results = payload.get("results") if isinstance(payload, dict) else None
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return {"major": results[0].get("major"), "sub": results[0].get("sub")}
    if isinstance(payload, dict) and ("major" in payload or "sub" in payload):
        return {"major": payload.get("major"), "sub": payload.get("sub")}
    return {}


def classify_change(v1_correct: bool, v2_correct: bool) -> str:
    if v1_correct and v2_correct:
        return "UNCHANGED_CORRECT"
    if not v1_correct and v2_correct:
        return "FIXED"
    if v1_correct and not v2_correct:
        return "REGRESSED"
    return "UNCHANGED_WRONG"


# ── Experiment ─────────────────────────────────────────────

def run_experiment(
    *,
    items: list[dict],
    prompts: dict,  # {"v1": {messages...}, "v2": {...}}
    llm_fn: Callable[[list[dict], str, int], dict],
    model: str,
    max_tokens: int = 4096,
    versions: list[str] | None = None,
) -> dict:
    """同一 items 上分别跑 v1/v2（同模型同参数同 evaluator），输出对比报告。"""
    versions = versions or ["v1", "v2"]
    evaluator = Evaluator()
    rows: list[dict] = []
    lat: dict[str, list[float]] = {v: [] for v in versions}
    usage: dict[str, dict] = {v: {"input": 0, "output": 0} for v in versions}
    correct: dict[str, int] = {v: 0 for v in versions}
    failures = []

    for it in items:
        row = {
            "case_id": it["id"],
            "physical_variable_id": str(it["input"].get("physical_variable_id") or ""),
            "original_name": str(it["input"].get("original_name") or ""),
            "expected": it["expected_output"],
            "context_limited": it.get("context_limited", False),
            "eligibility": it.get("eligibility", ""),
        }
        exp_item = experiment_item_from_dataset(it)
        evals = {}
        for key in versions:
            try:
                # 每次调用注入当前 case 的 item（dynamic input 不进 prompt identity）
                system = prompts[key]["messages"][0]["content"]
                msgs = build_chat_messages(system, exp_item, key, model)
                resp = llm_fn(msgs, model, max_tokens)
                content = resp.get("content") or ""
                parsed = parse_classification_output(content)
                ev = evaluator.evaluate_with_detail(it["expected_output"], parsed)
                row[f"{key}_output"] = parsed
                row[f"{key}_correct"] = ev["correct"]
                evals[key] = ev["correct"]
                latency_ms = resp.get("latency_ms", 0)
                resp_usage = resp.get("usage") or {}
                lat[key].append(latency_ms)
                usage[key]["input"] += int(resp_usage.get("input", 0))
                usage[key]["output"] += int(resp_usage.get("output", 0))
            except Exception as exc:  # noqa: BLE001 —— 单 case 失败隔离
                failures.append({"case_id": it["id"], "version": key, "error": str(exc)[:200]})
                row[f"{key}_correct"] = False
                evals[key] = False
        for k in versions:
            correct[k] += 1 if evals.get(k) else 0
        if len(versions) == 2:
            row["change_type"] = classify_change(bool(evals.get("v1")), bool(evals.get("v2")))
        rows.append(row)

    def _lat_stats(lats):
        if not lats:
            return {"avg": None, "p50": None, "p95": None, "n": 0}
        s = sorted(lats)
        return {"avg": round(sum(s) / len(s), 1), "p50": s[len(s) // 2],
                "p95": s[int(len(s) * 0.95) - 1], "n": len(s)}

    def _cost(usage):
        return round(
            usage["input"] / 1e6 * DEFAULT_INPUT_COST_PER_1M
            + usage["output"] / 1e6 * DEFAULT_OUTPUT_COST_PER_1M, 4,
        )

    n = len(items)
    changes = {}
    for r in rows:
        if r.get("change_type"):
            changes[r["change_type"]] = changes.get(r["change_type"], 0) + 1
    metrics = {}
    for k in versions:
        metrics[k] = {
            "correct": correct[k], "incorrect": n - correct[k],
            "accuracy": round(correct[k] / n, 4) if n else None,
            "latency": _lat_stats(lat[k]), "usage": usage[k],
            "estimated_cost_usd": _cost(usage[k]),
        }
    return {
        "cases": n,
        **metrics,
        "changes": changes,
        "case_rows": rows,
        "failures": failures,
        "estimated": True,
    }


def _llm_fn_factory(timeout: float = 120.0):
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        timeout=timeout, max_retries=1,
    )

    def _call(messages, model, max_tokens):
        start = time.perf_counter()
        resp = client.chat.completions.create(
            model=model, messages=messages,
            response_format={"type": "json_object"}, temperature=0, max_tokens=max_tokens,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        usage = resp.usage
        return {
            "content": resp.choices[0].message.content or "",
            "latency_ms": latency_ms,
            "usage": {"input": int(usage.prompt_tokens or 0) if usage else 0,
                      "output": int(usage.completion_tokens or 0) if usage else 0},
        }

    return _call


def aggregate_runs(run_results: list[dict]) -> dict:
    """多次运行聚合：mean/min/max accuracy、per-case consistency、selection_stability。

    selection_stability = 同一 case 多次运行判定一致（全对或全错）的比例。
    """
    n = len(run_results)
    versions = [v for v in ("v1", "v2", "v3") if v in run_results[0]]
    per_case: dict[str, dict[str, list[bool]]] = {}
    failures = 0
    for r in run_results:
        failures += len(r.get("failures", []))
        for row in r["case_rows"]:
            entry = per_case.setdefault(row["case_id"], {})
            for v in versions:
                entry.setdefault(v, []).append(bool(row.get(f"{v}_correct")))
    agg: dict[str, dict] = {}
    for v in versions:
        accs = [r.get(v, {}).get("accuracy") for r in run_results if r.get(v)]
        accs = [a for a in accs if a is not None]
        agg[v] = {
            "accuracy_mean": round(sum(accs) / len(accs), 4) if accs else None,
            "accuracy_min": min(accs) if accs else None,
            "accuracy_max": max(accs) if accs else None,
            "correct_each_run": [r.get(v, {}).get("correct") for r in run_results if r.get(v)],
            "latency": run_results[0].get(v, {}).get("latency"),
            "usage": run_results[0].get(v, {}).get("usage"),
            "estimated_cost_usd": round(
                sum((r.get(v, {}).get("estimated_cost_usd") or 0) for r in run_results), 4),
        }
    stability = {
        v: (round(sum(1 for e in per_case.values() if len(set(e.get(v, []))) == 1) / len(per_case), 4)
            if per_case else None)
        for v in versions
    }
    return {
        "cases": len(per_case), "runs": n, "failures": failures,
        "per_version": agg, "selection_stability": stability,
        "per_case": {cid: {v: entry[v] for v in versions} for cid, entry in per_case.items()},
    }


def decompose_gains(baseline_old_v1: float, new_v1: float, new_v3: float) -> dict:
    """归因分解：candidate rule gain 与 prompt gain 分开（不得合并）。"""
    return {
        "baseline_old_candidates_v1_accuracy": baseline_old_v1,
        "new_candidates_v1_accuracy": new_v1,
        "new_candidates_v3_accuracy": new_v3,
        "candidate_rule_gain_pp": round((new_v1 - baseline_old_v1) * 100, 1),
        "prompt_gain_pp": round((new_v3 - new_v1) * 100, 1),
    }


def write_report(out_dir: Path, report: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "experiment_report.json").write_text(
        json.dumps({k: v for k, v in report.items() if k != "case_rows"},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    cols = ["case_id", "physical_variable_id", "original_name", "expected",
            "v1_output", "v2_output", "v1_correct", "v2_correct", "change_type", "context_limited"]
    with (out_dir / "case_diff.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in report["case_rows"]:
            writer.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
                             for k, v in r.items()})
    return out_dir / "experiment_report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3 prompt experiment")
    parser.add_argument("--register", action="store_true", help="注册 v1/v2 到 Langfuse")
    parser.add_argument("--verify", action="store_true", help="检查 prompts 与 dataset")
    parser.add_argument("--experiment", action="store_true", help="运行实验")
    parser.add_argument("--dry-run", action="store_true", help="不调用 LLM / 不写 Langfuse")
    parser.add_argument("--limit", type=int, default=None, help="eligible 子集上限")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--versions", default=None, help="实验版本（v1,v2,v3）")
    parser.add_argument("--items-file", default=None, help="本地 items jsonl（替代 Langfuse dataset）")
    parser.add_argument("--runs", type=int, default=1, help="每 Prompt 重复次数（≥3 以评估方差）")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--dataset-name", default="classification/human_confirmed")
    args = parser.parse_args(argv)

    if args.register:
        result = register_prompts(dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    client = None if args.dry_run else _make_client()
    info = production_prompt_info()

    if args.verify:
        ds_items = [] if args.dry_run else load_dataset_items(client, args.dataset_name)
        elig = check_eligibility(ds_items)
        print(json.dumps({
            "prompt": info,
            "dataset_items": len(ds_items),
            "eligible": len(elig["eligible"]),
            "ineligible": elig["ineligible"],
        }, ensure_ascii=False, indent=2))
        return 0

    if args.experiment:
        if args.dry_run:
            # 纯本地：用代码内 Prompt 文本 + 静态 dataset 结构做 dry-run 计划
            prompts = {
                "v1": {"messages": build_chat_messages(info["system_prompt"], {}, info["prompt_version"], info["model"])},
                "v2": {"messages": build_chat_messages(build_v2_system_prompt(info["system_prompt"]), {}, "v2", info["model"])},
            }
            ds_items = load_dataset_items(client, args.dataset_name) if client else []
            elig = check_eligibility(ds_items)
            plan = {
                "dry_run": True,
                "prompt": {k: {"label": v, "messages": prompts[k]["messages"]} for k, v in
                           (("v1", LABEL_V1), ("v2", LABEL_V2))},
                "model": args.model or info["model"],
                "max_tokens": args.max_tokens,
                "eligible": len(elig["eligible"]),
                "ineligible": elig["ineligible"],
            }
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0

        version_labels = {"v1": LABEL_V1, "v2": LABEL_V2, "v3": LABEL_V3}
        versions = [v.strip() for v in (args.versions or "v1,v2").split(",") if v.strip()]
        prompts = {k: load_prompt(client, version_labels[k]) for k in versions}
        if args.items_file:
            ds_items = [json.loads(l) for l in
                        open(args.items_file, encoding="utf-8").read().splitlines() if l.strip()]
        else:
            ds_items = load_dataset_items(client, args.dataset_name)
        elig = check_eligibility(ds_items)
        model = args.model or info["model"]
        # 子集：A=production_equivalent；B=production_equivalent+historical_reconstructed
        pe = [i for i in elig["eligible"] if i["eligibility"] == "production_equivalent"]
        rec = [i for i in elig["eligible"]
               if i["eligibility"] in ("production_equivalent", "historical_reconstructed")]
        subsets = {"production_equivalent": pe,
                   "production_equivalent+reconstructed": rec}
        out_dir = Path(args.out_dir or PROJECT_ROOT / "workflow_runs" / "experiments")
        out_dir = out_dir / f"prompt_compare_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        out_dir.mkdir(parents=True, exist_ok=True)
        llm_fn = _llm_fn_factory()
        subset_results = {}
        for name, items in subsets.items():
            if args.limit:
                items = items[: args.limit]
            if not items:
                subset_results[name] = {"cases": 0, "skipped": "no items"}
                continue
            run_results = []
            for run_i in range(args.runs):
                report = run_experiment(
                    items=items, prompts=prompts, llm_fn=llm_fn,
                    model=model, max_tokens=args.max_tokens, versions=versions,
                )
                run_results.append(report)
                write_report(out_dir / name / f"run_{run_i + 1}", report)
            subset_results[name] = aggregate_runs(run_results)
        summary = {
            "model": model, "max_tokens": args.max_tokens, "versions": versions,
            "runs": args.runs, "subsets": subset_results,
            "eligible_layers": {
                "production_equivalent": len(pe),
                "historical_reconstructed": len(rec) - len(pe),
                "context_limited": sum(1 for i in elig["eligible"] if i["eligibility"] == "context_limited"),
                "ineligible": len(elig["ineligible"]),
            },
            "out_dir": str(out_dir),
        }
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
