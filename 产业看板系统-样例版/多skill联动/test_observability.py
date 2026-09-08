# -*- coding: utf-8 -*-
"""workflow/observability.py 单元测试（best-effort 行为 + SDK v4 调用形态）。"""

import hashlib
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow import observability  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_observability(monkeypatch):
    """每个测试重置模块级缓存与 env。"""
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_client_failed", False)
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("WORKFLOW_RUN_ID", raising=False)
    monkeypatch.delenv("INDUSTRY", raising=False)
    monkeypatch.delenv("STAGE", raising=False)


def test_prompt_fingerprint_is_stable_sha256():
    text = "你是行业指标分类助手。"
    fp1 = observability.prompt_fingerprint(text)
    fp2 = observability.prompt_fingerprint(text)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex
    assert fp1 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    # 不同文本不同指纹
    assert fp1 != observability.prompt_fingerprint(text + "x")


def test_disabled_without_keys(monkeypatch):
    # 未配置 LANGFUSE key：client 不初始化（enabled=False），不抛异常
    assert observability._load_client() is None
    assert observability.enabled() is False


def test_disabled_when_env_off(monkeypatch):
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    assert observability._load_client() is None


def test_disabled_completion_calls_through(monkeypatch):
    # disabled 时 completion 原样调用 create_fn（只调用一次，返回值透传）
    calls = []

    def fake_create():
        calls.append(1)
        return {"ok": True}

    result = observability.completion(
        fake_create,
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        prompt_name="test",
        prompt_version="v1",
        prompt_hash="h" * 64,
    )
    assert result == {"ok": True}
    assert len(calls) == 1


def test_disabled_stage_span_yields_none():
    with observability.stage_span("test") as span:
        assert span is None


def test_stage_stats_metadata():
    stats = observability.StageStats()
    stats.items_total = 10
    stats.hit()
    stats.hit()
    stats.hit()
    stats.call()
    md = stats.to_metadata()
    assert md["items_total"] == 10
    assert md["cache_hits"] == 3
    assert md["actual_llm_calls"] == 1
    assert md["cache_hit_rate"] == 0.3

    empty = observability.StageStats()
    assert empty.to_metadata()["cache_hit_rate"] == 0.0


def test_context_from_env(monkeypatch):
    monkeypatch.setenv("WORKFLOW_RUN_ID", "abc123")
    monkeypatch.setenv("INDUSTRY", "lithium")
    monkeypatch.setenv("STAGE", "ai_disambiguation")
    ctx = observability.get_context()
    assert ctx["workflow_run_id"] == "abc123"
    assert ctx["industry"] == "lithium"
    assert ctx["stage"] == "ai_disambiguation"


def test_flush_safe_when_disabled():
    # disabled 时 flush 无副作用、不抛
    observability.flush()


def test_fake_keys_unreachable_fallback_to_direct_call(monkeypatch):
    # 配置了 key 但服务不可达：观测失败必须静默，completion 原样调用一次
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-fake")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-fake")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:1")  # 不可达
    calls = []

    def fake_create():
        calls.append(1)
        return {"ok": True}

    result = observability.completion(
        fake_create,
        model="m",
        messages=[{"role": "user", "content": "x"}],
        prompt_name="t",
        prompt_version="v1",
        prompt_hash="h" * 64,
    )
    assert result == {"ok": True}
    assert len(calls) == 1


def test_extract_usage_from_response():
    class Usage:
        prompt_tokens = 100
        completion_tokens = 50
        total_tokens = 150

    class Resp:
        usage = Usage()

    assert observability._extract_usage(Resp()) == {"input": 100, "output": 50, "total": 150}

    class NoUsage:
        usage = None

    assert observability._extract_usage(NoUsage()) is None


def test_record_evaluation_interface_defined():
    # Phase 2b 已实施：接口存在且校验必填项（disabled 时 best-effort no-op）
    import inspect

    params = inspect.signature(observability.record_evaluation).parameters
    assert "physical_variable_id" in params
    assert "score_name" in params and "source" in params
    assert "observation_id" in params and "workflow_run_id" in params


# ── enabled 路径（fake client，验证 SDK v4 调用形态，不触网）──────────

class _FakeSpan:
    def __init__(self, name: str):
        self.name = name
        self.id = "0123456789abcdef"
        self.ended = False
        self.attrs: dict = {}

    def end(self) -> None:
        self.ended = True

    def update(self, **kwargs) -> None:
        self.attrs.update(kwargs)


class _FakeClient:
    """最小 Langfuse client 替身：记录调用，返回 fake span。"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.last_span: _FakeSpan | None = None

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.calls.append(("current", dict(kwargs)))
        span = _FakeSpan(kwargs["name"])
        yield span
        span.ended = True

    def start_observation(self, **kwargs):
        self.calls.append(("obs", dict(kwargs)))
        span = _FakeSpan(kwargs["name"])
        self.last_span = span
        return span


def _enable_fake(monkeypatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(observability, "_client", fake)
    monkeypatch.setattr(observability, "_client_failed", False)
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("WORKFLOW_RUN_ID", "run12345678")


def test_stage_span_enabled_uses_current_workflow_root(monkeypatch):
    fake = _FakeClient()
    _enable_fake(monkeypatch, fake)
    with observability.stage_span("ai_disambiguation") as span:
        assert span is not None

    current_kw = [c[1] for c in fake.calls if c[0] == "current"]
    obs_kw = [c[1] for c in fake.calls if c[0] == "obs"]
    assert len(current_kw) == 1 and len(obs_kw) == 1
    # 根观测：span workflow.<industry>，trace_context 强制 trace id = md5(run_id)
    assert current_kw[0]["as_type"] == "span"
    assert current_kw[0]["name"] == "workflow."
    expected_tid = hashlib.md5(b"run12345678").hexdigest()
    assert current_kw[0]["trace_context"] == {"trace_id": expected_tid}
    # 子观测（stage span）：不再传 trace_context（避免 AS_ROOT 覆盖 trace 名）
    assert obs_kw[0]["name"] == "ai_disambiguation"
    assert "trace_context" not in obs_kw[0]
    # 退出 with 块后根/子 span 都已 end
    assert fake.last_span.ended is True


def test_completion_enabled_records_usage_details(monkeypatch):
    fake = _FakeClient()
    _enable_fake(monkeypatch, fake)

    class Usage:
        prompt_tokens = 100
        completion_tokens = 50
        total_tokens = 150

    class Resp:
        usage = Usage()
        choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]

    result = observability.completion(
        lambda: Resp(),
        model="m",
        messages=[{"role": "user", "content": "x"}],
        prompt_name="t",
        prompt_version="v1",
        prompt_hash="h" * 64,
    )
    assert result is not None
    obs_kw = fake.calls[0][1]
    assert obs_kw["as_type"] == "generation"
    assert obs_kw["name"] == "llm.t"
    assert obs_kw["metadata"]["prompt_name"] == "t"
    # v4 SDK 参数名是 usage_details，usage 旧参数会被静默丢弃
    assert fake.last_span.attrs["usage_details"] == {"input": 100, "output": 50, "total": 150}
    assert fake.last_span.ended is True


def test_completion_enabled_records_error_level(monkeypatch):
    fake = _FakeClient()
    _enable_fake(monkeypatch, fake)

    def boom():
        raise RuntimeError("llm down")

    with pytest.raises(RuntimeError):
        observability.completion(
            boom,
            model="m",
            messages=[{"role": "user", "content": "x"}],
            prompt_name="t",
            prompt_version="v1",
            prompt_hash="h" * 64,
        )
    assert fake.last_span.attrs.get("level") == "ERROR"
    assert "llm down" in fake.last_span.attrs.get("status_message", "")
    assert fake.last_span.ended is True
