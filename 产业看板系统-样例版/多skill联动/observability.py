# -*- coding: utf-8 -*-
"""统一 observability adapter —— 全项目唯一 Langfuse SDK 接触层。

业务脚本（AI 消歧 / 个股 AI 筛选等）不得直接 import langfuse，统一通过本
模块接入。设计原则：

- best-effort：Langfuse 不可用（未配置 key / host 不可达 / SDK 异常）时，
  全部接口退化为 no-op，业务行为零变化、不抛异常。
- 不改变 LLM 请求内容：观测层只包住 create 调用，请求/响应原样透传。
- workflow_run_id 作为核心业务 correlation ID（由 workflow 层注入 env
  WORKFLOW_RUN_ID），记录在 span/generation metadata 中，并经 md5 映射为
  Langfuse trace id（32 hex）—— 同一 run 的跨进程/跨调用观测归并到同一 trace。
- prompt 以 prompt_name / prompt_version / prompt_hash（SHA-256）标识，
  为后续 Prompt Management 迁移建立稳定映射。
- cache hit 不创建虚假 generation；stage 层记录 items_total / cache_hits /
  actual_llm_calls / cache_hit_rate。

Langfuse SDK v4（OTEL 架构）适配要点：

- start_observation 的 as_type 不含 "trace"；trace 由"根观测"隐式创建。
  根观测必须是带 trace_context={"trace_id": ...} 的 span，trace 名取自根
  观测名（workflow.<industry>）。子观测若再传 trace_context 会打 AS_ROOT
  标记，导致 trace 名被覆盖为子观测名 —— 故只有根观测用 trace_context。
- 层级通过 OTEL 上下文建立：stage_span 用 start_as_current_observation
  把根观测设为 current，stage span 直接 start_observation 自动挂到根下；
  跨线程（ThreadPoolExecutor）时 OTEL contextvar 不传播，completion 对
  显式传入的 span 用 opentelemetry.trace.use_span 挂接父级。
- usage 参数名是 usage_details（不是旧版 usage，传入会被静默丢弃）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("observability")

# 统一加载项目根 .env（LANGFUSE_* 配置位置；系统环境变量优先，不覆盖）
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # noqa: BLE001 —— dotenv 不可用不影响
    pass

# 环境变量（官方命名）
ENV_ENABLED = "LANGFUSE_ENABLED"
ENV_PUBLIC_KEY = "LANGFUSE_PUBLIC_KEY"
ENV_SECRET_KEY = "LANGFUSE_SECRET_KEY"
ENV_BASE_URL = "LANGFUSE_BASE_URL"
ENV_TRACING_ENVIRONMENT = "LANGFUSE_TRACING_ENVIRONMENT"
ENV_RUN_ID = "WORKFLOW_RUN_ID"
ENV_INDUSTRY = "INDUSTRY"
ENV_STAGE = "STAGE"

_client = None
_client_failed = False


def _is_enabled() -> bool:
    return os.getenv(ENV_ENABLED, "true").strip().lower() in ("1", "true", "yes", "on")


def _load_client():
    """懒加载 Langfuse client；任何失败/未配置 → disabled 模式（None）。

    未配置 public/secret key 时直接禁用（不初始化 SDK，保持零依赖运行路径）。
    """
    global _client, _client_failed
    if _client is not None or _client_failed or not _is_enabled():
        return _client
    if not (os.getenv(ENV_PUBLIC_KEY) and os.getenv(ENV_SECRET_KEY)):
        _client_failed = True
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=os.getenv(ENV_PUBLIC_KEY, ""),
            secret_key=os.getenv(ENV_SECRET_KEY, ""),
            base_url=os.getenv(ENV_BASE_URL, "https://cloud.langfuse.com"),
            environment=os.getenv(ENV_TRACING_ENVIRONMENT, "development"),
            debug=False,
        )
    except Exception as exc:  # noqa: BLE001 —— best-effort，观测故障不抛
        _client_failed = True
        _client = None
        logger.warning("observability disabled: %s", exc)
    return _client


def enabled() -> bool:
    return _load_client() is not None


def get_context() -> dict[str, str]:
    """从注入层 env 读取业务上下文（workflow_run_id / industry / stage）。"""
    return {
        "workflow_run_id": os.getenv(ENV_RUN_ID, ""),
        "industry": os.getenv(ENV_INDUSTRY, ""),
        "stage": os.getenv(ENV_STAGE, ""),
    }


def prompt_fingerprint(text: str) -> str:
    """prompt 文本的稳定 SHA-256 指纹（prompt_hash）。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _trace_id() -> str:
    """Langfuse trace id（必须 32 位小写 hex）。

    workflow_run_id（12 位 hex）经 md5 映射为稳定 32 hex —— 同一 run 的
    跨进程/跨调用观测归并到同一 trace；原始 workflow_run_id 保留在 metadata。
    无 run_id 时由 SDK 生成标准 trace id。
    """
    run_id = os.getenv(ENV_RUN_ID) or ""
    if run_id:
        return hashlib.md5(run_id.encode("utf-8")).hexdigest()
    client = _load_client()
    if client is not None:
        try:
            return client.create_trace_id()
        except Exception:  # noqa: BLE001
            pass
    return hashlib.md5(b"no-run-id").hexdigest()


@contextmanager
def stage_span(name: str, metadata: dict | None = None):
    """stage 级 span（best-effort）。disabled 时 yield None。

    根观测为 span workflow.<industry>（trace_context 强制 trace id = md5
    workflow_run_id，trace 名即根观测名）；stage span 作为其子观测。yield
    的 span 对象可传给 completion 或子线程（completion 内部用其 OTEL span
    挂接父子关系）。
    """
    client = _load_client()
    if client is None:
        yield None
        return
    try:
        with client.start_as_current_observation(
            as_type="span",
            name=f"workflow.{os.getenv(ENV_INDUSTRY, '')}",
            metadata=dict(get_context()),
            trace_context={"trace_id": _trace_id()},
        ):
            span = client.start_observation(
                as_type="span",
                name=name,
                metadata=metadata or {},
            )
            try:
                yield span
            finally:
                try:
                    span.end()
                except Exception:  # noqa: BLE001
                    pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("stage_span start failed: %s", exc)
        yield None
        return


class StageStats:
    """stage 级缓存统计：cache hit 不创建 generation，只记统计。"""

    def __init__(self) -> None:
        self.items_total = 0
        self.cache_hits = 0
        self.actual_llm_calls = 0

    def hit(self) -> None:
        self.cache_hits += 1

    def call(self) -> None:
        self.actual_llm_calls += 1

    def to_metadata(self) -> dict[str, Any]:
        total = self.items_total
        rate = round(self.cache_hits / total, 4) if total else 0.0
        return {
            "items_total": self.items_total,
            "cache_hits": self.cache_hits,
            "actual_llm_calls": self.actual_llm_calls,
            "cache_hit_rate": rate,
        }


def completion(
    create_fn: Callable[[], Any],
    *,
    model: str,
    messages: list[dict],
    prompt_name: str,
    prompt_version: str,
    prompt_hash: str,
    extra_metadata: dict | None = None,
    span=None,
) -> Any:
    """执行一次 LLM completion，观测为 generation（best-effort）。

    - disabled 时：直接调用 create_fn（零开销、行为不变）。
    - 观测创建失败：直接调用 create_fn。
    - span：所属 stage span；线程池等非当前上下文场景显式传入。generation
      用其 OTEL span 挂到 span 下（OTEL contextvar 不跨线程，不能依赖
      上下文隐式挂接）。
    - 业务异常（create_fn 抛错）：记录 error 后原样抛出（业务重试逻辑在外层）。
    - 观测记录失败（update/end）：静默，不影响响应。
    """
    client = _load_client()
    metadata = {
        **get_context(),
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    if client is None:
        return create_fn()

    gen = None
    try:
        otel_span = getattr(span, "_otel_span", None)
        if otel_span is not None:
            try:
                from opentelemetry import trace as otel_trace

                with otel_trace.use_span(otel_span):
                    gen = client.start_observation(
                        as_type="generation",
                        name=f"llm.{prompt_name}",
                        model=model,
                        input=messages,
                        metadata=metadata,
                    )
            except Exception:  # noqa: BLE001 —— 挂接失败退化为无父级观测
                gen = None
        if gen is None:
            gen = client.start_observation(
                as_type="generation",
                name=f"llm.{prompt_name}",
                model=model,
                input=messages,
                metadata=metadata,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("generation start failed: %s", exc)
        return create_fn()

    try:
        response = create_fn()
    except Exception as exc:  # noqa: BLE001 —— 业务异常照常传播
        try:
            gen.update(level="ERROR", status_message=str(exc)[:2000])
            gen.end()
        except Exception:  # noqa: BLE001
            pass
        raise
    try:
        content = None
        try:
            content = response.choices[0].message.content
        except Exception:  # noqa: BLE001 —— 响应结构异常不影响观测
            pass
        # v4 SDK 参数名是 usage_details（旧版 usage 会被静默丢弃）
        gen.update(output=content, usage_details=_extract_usage(response))
        gen.end()
    except Exception:  # noqa: BLE001
        pass
    return response


def _extract_usage(response) -> dict | None:
    """从 OpenAI 兼容响应提取 token usage（DeepSeek 等返回 Usage 对象）。"""
    try:
        raw_usage = response.usage
        if raw_usage is None:
            return None
        return {
            "input": int(getattr(raw_usage, "prompt_tokens", 0) or 0),
            "output": int(getattr(raw_usage, "completion_tokens", 0) or 0),
            "total": int(getattr(raw_usage, "total_tokens", 0) or 0),
        }
    except Exception:  # noqa: BLE001
        return None


def flush() -> None:
    """进程退出前调用：异步批量发送缓冲中的观测（best-effort）。"""
    client = _load_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("observability flush failed: %s", exc)


# ── Evaluation（Phase 2b：verifier / human scores 写入）──────────

ENV_EVAL_RUN_ROOT = "EVAL_RUN_ROOT"

SCORE_DATA_TYPES = ("NUMERIC", "CATEGORICAL", "BOOLEAN", "TEXT", "CORRECTION")

# 这些 verifier 状态禁止推导 correctness（影子审计是风险发现器，不是裁判）
FORBIDDEN_CORRECTNESS_STATUSES = frozenset(
    {"PENDING_HUMAN_REVIEW", "REVIEW_REQUIRED", "ERROR", "AMBIGUOUS", "NEEDS_HUMAN_REVIEW"}
)
_CORRECTNESS_SCORES = frozenset({"verifier_classification_correct", "human_classification_correct"})


def evaluation_key(physical_variable_id: str, prompt_version: str, prompt_hash: str) -> str:
    """跨 run 聚合键：同一变量 + 同一 prompt → 同一 key（与 evaluation_correlation 一致）。"""
    payload = f"{physical_variable_id}|{prompt_version}|{prompt_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def score_id(evaluation_key: str, idem_source: str, source: str, score_name: str) -> str:
    """幂等 score 键：idem_source = audit_run_id（verifier）或 source_record_id（human）。"""
    payload = f"{evaluation_key}|{idem_source}|{source}|{score_name}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _correlation_index_rows() -> list[dict]:
    """扫描 run root 下全部 correlation_index.jsonl（EVAL_RUN_ROOT 可覆盖）。"""
    run_root = Path(os.getenv(ENV_EVAL_RUN_ROOT, str(Path(__file__).resolve().parents[1] / "workflow_runs")))
    rows: list[dict] = []
    if not run_root.is_dir():
        return rows
    for index_file in sorted(run_root.glob("*/audit/evaluation/correlation_index.jsonl")):
        try:
            for line in index_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        except Exception:  # noqa: BLE001 —— 单文件损坏不影响
            pass
    return rows


def _resolve_correlation(
    index_rows: list[dict],
    *,
    workflow_run_id: str,
    physical_variable_id: str,
    stage: str,
    observation_id: str | None,
) -> dict | None:
    """从 correlation index 精确解析 (workflow_run_id, physical_variable_id, stage)
    或显式 observation_id；必须唯一命中，AMBIGUOUS/UNMATCHED → None（不评分）。
    不用 indicator_name 查找，不跨 run 匹配。
    """
    if observation_id:
        cands = [
            r for r in index_rows
            if r.get("generation_observation_id") == observation_id
            and r.get("physical_variable_id") == physical_variable_id
        ]
    else:
        cands = [
            r for r in index_rows
            if r.get("workflow_run_id") == workflow_run_id
            and r.get("physical_variable_id") == physical_variable_id
            and r.get("stage") == stage
        ]
    if len(cands) != 1:
        logger.warning(
            "record_evaluation: correlation 非唯一命中（n=%d）run=%s vid=%s stage=%s obs=%s —— 不写 score",
            len(cands), workflow_run_id, physical_variable_id, stage, observation_id,
        )
        return None
    return cands[0]


def record_evaluation(
    *,
    physical_variable_id: str,
    stage: str,
    workflow_run_id: str | None = None,
    observation_id: str | None = None,
    score_name: str,
    value: float | str | bool,
    data_type: str,
    source: "str",
    audit_run_id: str | None = None,
    expected_output: dict | None = None,
    error_type: str | None = None,
    comment: str | None = None,
    metadata: dict | None = None,
) -> None:
    """把 verifier / human evaluation 写入 Langfuse score（best-effort）。

    - 只对“已存在真实 generation”的 case 生效：observation 经 correlation index
      唯一解析（workflow_run_id + physical_variable_id + stage 或显式
      observation_id）；AMBIGUOUS / UNMATCHED → no-op，不影响 workflow。
    - 不构造 trace_id（禁止 md5(workflow_run_id) / zfill）；trace_id 与
      observation_id 均来自 correlation index 的真实关联（observation 级挂载）。
    - prompt_version / prompt_hash 从 correlation index 行读取（不接收调用方传入）。
    - score_name 前缀强制：verifier_ / human_（与 source 一致），来源不明禁止。
    - correctness 类 score（*_classification_correct）仅在存在明确 expected_output
      且 verifier 状态可裁定 / human 非 UNRESOLVED 时写入（见 metadata 门控）。
    - 幂等：evaluation_key = sha256(vid|prompt_version|prompt_hash)；
      score_id = sha256(evaluation_key|idem_source|source|score_name)，
      idem_source = audit_run_id（verifier 必填）或 metadata['source_record_id']
      （human 且无 audit_run_id 时必填）；时间戳不参与幂等。
    """
    client = _load_client()
    if client is None:
        logger.warning("record_evaluation skipped: observability disabled")
        return
    if not physical_variable_id:
        raise ValueError("record_evaluation: physical_variable_id 必填")
    if source not in ("verifier", "human"):
        raise ValueError(f"record_evaluation: source 必须为 verifier|human，收到 {source!r}")
    if not score_name.startswith(f"{source}_"):
        raise ValueError(
            f"record_evaluation: source={source} 的 score_name 必须以 {source}_ 前缀，收到 {score_name!r}"
        )
    if data_type not in SCORE_DATA_TYPES:
        raise ValueError(f"record_evaluation: 非法 data_type {data_type!r}，允许 {SCORE_DATA_TYPES}")
    # SDK 4.14.1 Scores API：BOOLEAN 的 value 必须是 number（1/0），字符串会被 400 拒绝
    if data_type == "BOOLEAN":
        if isinstance(value, bool):
            value = 1 if value else 0
        elif isinstance(value, str) and value.lower() in ("true", "false"):
            value = 1 if value.lower() == "true" else 0
    md = dict(metadata or {})

    run_id = workflow_run_id or os.getenv(ENV_RUN_ID, "")
    if not run_id:
        logger.warning("record_evaluation: 无 workflow_run_id（env 也未注入）—— 不写 score")
        return

    row = _resolve_correlation(
        _correlation_index_rows(),
        workflow_run_id=run_id,
        physical_variable_id=physical_variable_id,
        stage=stage,
        observation_id=observation_id,
    )
    if row is None:
        return  # AMBIGUOUS / UNMATCHED：best-effort，不写 score

    prompt_version = row.get("prompt_version", "")
    prompt_hash = row.get("prompt_hash", "")
    obs_id = row.get("generation_observation_id", "") or observation_id
    real_trace_id = row.get("trace_id") or ""

    # correctness 门控
    if score_name in _CORRECTNESS_SCORES:
        if not expected_output:
            logger.warning(
                "record_evaluation: %s 缺少明确 expected_output —— 不写 correctness", score_name
            )
            return
        if score_name.startswith("verifier_") and md.get("verifier_status") in FORBIDDEN_CORRECTNESS_STATUSES:
            logger.warning(
                "record_evaluation: verifier 状态 %r 禁止推导 correctness —— 不写",
                md.get("verifier_status"),
            )
            return
        if score_name == "human_classification_correct" and md.get("human_decision") == "UNRESOLVED":
            logger.warning("record_evaluation: human UNRESOLVED 禁止写 correctness —— 不写")
            return

    # 幂等来源
    if source == "verifier":
        idem_source = audit_run_id
        if not idem_source:
            raise ValueError("record_evaluation: verifier score 必须提供 audit_run_id（幂等来源）")
    else:
        idem_source = audit_run_id or (md.get("source_record_id") or "")
        if not idem_source:
            raise ValueError("record_evaluation: human score 必须提供 audit_run_id 或 metadata['source_record_id']")

    key = evaluation_key(physical_variable_id, prompt_version, prompt_hash)
    sid = score_id(key, idem_source, source, score_name)

    score_metadata = {
        **md,
        "physical_variable_id": physical_variable_id,
        "stage": stage,
        "workflow_run_id": run_id,
        "evaluation_key": key,
        "score_source": source,
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash,
        "idem_source": idem_source,
    }
    if expected_output is not None:
        score_metadata["expected_output"] = expected_output
    if error_type:
        score_metadata["error_type"] = error_type

    try:
        client.create_score(
            name=score_name,
            value=value,
            observation_id=obs_id,
            trace_id=real_trace_id or None,
            score_id=sid,
            data_type=data_type,
            comment=comment,
            metadata=score_metadata,
            environment=os.getenv(ENV_TRACING_ENVIRONMENT, "development"),
        )
    except Exception as exc:  # noqa: BLE001 —— best-effort，观测故障不抛
        logger.warning("record_evaluation failed: %s", exc)
