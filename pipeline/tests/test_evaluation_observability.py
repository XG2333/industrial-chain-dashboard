# -*- coding: utf-8 -*-
"""Phase 2b：workflow/observability.py record_evaluation() 测试（fake client，不触网）。"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow import observability  # noqa: E402

VID = "abcd1234abcd1234"
STAGE = "ai_disambiguation"
PROMPT_VERSION = "ai_assisted_curation_v1"
PROMPT_HASH = "h" * 64
OBS_ID = "obs1234567890abcdef"
TRACE_ID = "t" * 32
RUN_ID = "run1234567890"


class _FakeScoreClient:
    def __init__(self):
        self.scores: list[dict] = []

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def flush(self):
        pass


def _index_row(**overrides):
    row = {
        "workflow_run_id": RUN_ID, "physical_variable_id": VID, "industry": "lithium",
        "stage": STAGE, "generation_observation_id": OBS_ID, "batch_index": 0,
        "prompt_name": "ai_disambiguation", "prompt_version": PROMPT_VERSION,
        "prompt_hash": PROMPT_HASH, "model": "deepseek-v4-flash",
        "original_name": "X指标", "sheet": "价格-日", "unit": "元/吨",
        "frequency": "日度", "match_method": "EXACT_TRIPLE", "trace_id": TRACE_ID,
    }
    row.update(overrides)
    return row


@pytest.fixture
def index_env(tmp_path, monkeypatch):
    """临时 run root + 唯一关联行。"""
    eval_dir = tmp_path / "run1" / "audit" / "evaluation"
    eval_dir.mkdir(parents=True)
    (eval_dir / "correlation_index.jsonl").write_text(
        json.dumps(_index_row()) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("EVAL_RUN_ROOT", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_RUN_ID", RUN_ID)
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setattr(observability, "_client", _FakeScoreClient())
    monkeypatch.setattr(observability, "_client_failed", False)
    return observability._client


def test_evaluation_key_stable():
    k1 = observability.evaluation_key(VID, PROMPT_VERSION, PROMPT_HASH)
    k2 = observability.evaluation_key(VID, PROMPT_VERSION, PROMPT_HASH)
    assert k1 == k2 and len(k1) == 32
    assert observability.evaluation_key(VID, "v2", PROMPT_HASH) != k1
    assert observability.evaluation_key(VID, PROMPT_VERSION, "g" * 64) != k1


def test_score_id_idempotent():
    key = observability.evaluation_key(VID, PROMPT_VERSION, PROMPT_HASH)
    s1 = observability.score_id(key, "audit_1", "verifier", "verifier_status")
    s2 = observability.score_id(key, "audit_1", "verifier", "verifier_status")
    assert s1 == s2 and len(s1) == 32
    assert observability.score_id(key, "audit_2", "verifier", "verifier_status") != s1
    assert observability.score_id(key, "audit_1", "human", "human_decision") != s1


def test_unique_correlation_writes_score(index_env):
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_status", value="CONFIRMED", data_type="CATEGORICAL",
        source="verifier", audit_run_id="audit_1",
    )
    assert len(index_env.scores) == 1
    score = index_env.scores[0]
    assert score["observation_id"] == OBS_ID
    assert score["trace_id"] == TRACE_ID  # 真实 trace 关联，非推导
    assert score["name"] == "verifier_status"
    assert score["data_type"] == "CATEGORICAL"
    assert score["metadata"]["prompt_version"] == PROMPT_VERSION
    assert score["metadata"]["prompt_hash"] == PROMPT_HASH
    assert score["metadata"]["evaluation_key"] == observability.evaluation_key(VID, PROMPT_VERSION, PROMPT_HASH)
    expected_sid = observability.score_id(
        observability.evaluation_key(VID, PROMPT_VERSION, PROMPT_HASH), "audit_1", "verifier", "verifier_status"
    )
    assert score["score_id"] == expected_sid


def test_no_correlation_noop(index_env):
    observability.record_evaluation(
        physical_variable_id="0000000000000000", stage=STAGE,
        score_name="verifier_status", value="CONFIRMED", data_type="CATEGORICAL",
        source="verifier", audit_run_id="audit_1",
    )
    assert index_env.scores == []


def test_ambiguous_correlation_noop(index_env, tmp_path):
    eval_dir = tmp_path / "run1" / "audit" / "evaluation"
    with (eval_dir / "correlation_index.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(_index_row(batch_index=5, generation_observation_id="obs_other")) + "\n")
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_status", value="CONFIRMED", data_type="CATEGORICAL",
        source="verifier", audit_run_id="audit_1",
    )
    assert index_env.scores == []


def test_correctness_requires_expected_output(index_env):
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_classification_correct", value=True, data_type="BOOLEAN",
        source="verifier", audit_run_id="audit_1", expected_output=None,
    )
    assert index_env.scores == []


@pytest.mark.parametrize("status", ["PENDING_HUMAN_REVIEW", "REVIEW_REQUIRED", "ERROR", "AMBIGUOUS", "NEEDS_HUMAN_REVIEW"])
def test_verifier_forbidden_status_not_written(index_env, status):
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_classification_correct", value=True, data_type="BOOLEAN",
        source="verifier", audit_run_id="audit_1",
        expected_output={"大类": "价格"}, metadata={"verifier_status": status},
    )
    assert index_env.scores == []


def test_verifier_eligible_correctness_written(index_env):
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_classification_correct", value=True, data_type="BOOLEAN",
        source="verifier", audit_run_id="audit_1",
        expected_output={"大类": "价格"},
    )
    assert len(index_env.scores) == 1
    # SDK 4.14.1：BOOLEAN 的 value 必须是 number（1/0）
    assert index_env.scores[0]["value"] == 1


def test_human_unresolved_no_correctness(index_env):
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="human_classification_correct", value=True, data_type="BOOLEAN",
        source="human", audit_run_id="audit_1",
        expected_output={"大类": "价格"}, metadata={"human_decision": "UNRESOLVED"},
    )
    assert index_env.scores == []
    # UNRESOLVED 只允许 human_decision
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="human_decision", value="UNRESOLVED", data_type="CATEGORICAL",
        source="human", audit_run_id="audit_1",
    )
    assert len(index_env.scores) == 1
    assert index_env.scores[0]["name"] == "human_decision"


def test_source_name_prefix_validation(index_env):
    with pytest.raises(ValueError):
        observability.record_evaluation(
            physical_variable_id=VID, stage=STAGE,
            score_name="classification_correct", value=True, data_type="BOOLEAN",
            source="verifier", audit_run_id="audit_1",
        )
    with pytest.raises(ValueError):
        observability.record_evaluation(
            physical_variable_id=VID, stage=STAGE,
            score_name="verifier_status", value="x", data_type="CATEGORICAL",
            source="human",
        )
    with pytest.raises(ValueError):
        observability.record_evaluation(
            physical_variable_id="", stage=STAGE,
            score_name="verifier_status", value="x", data_type="CATEGORICAL",
            source="verifier", audit_run_id="a",
        )


def test_human_requires_idem_source(index_env):
    with pytest.raises(ValueError):
        observability.record_evaluation(
            physical_variable_id=VID, stage=STAGE,
            score_name="human_decision", value="CONFIRMED", data_type="CATEGORICAL",
            source="human", audit_run_id=None,
        )
    # metadata.source_record_id 作为幂等来源可用
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="human_decision", value="CONFIRMED", data_type="CATEGORICAL",
        source="human", metadata={"source_record_id": "review_0001"},
    )
    assert len(index_env.scores) == 1
    assert index_env.scores[0]["metadata"]["idem_source"] == "review_0001"


def test_prompt_fields_from_index_not_caller(index_env):
    # 接口签名无 prompt_version/prompt_hash 参数；值只来自 correlation index 行
    import inspect

    params = inspect.signature(observability.record_evaluation).parameters
    assert "prompt_version" not in params and "prompt_hash" not in params
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_status", value="CONFIRMED", data_type="CATEGORICAL",
        source="verifier", audit_run_id="audit_1",
    )
    assert index_env.scores[0]["metadata"]["prompt_version"] == PROMPT_VERSION
    assert index_env.scores[0]["metadata"]["prompt_hash"] == PROMPT_HASH


def test_disabled_noop_no_business_impact(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_RUN_ROOT", str(tmp_path))
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_client_failed", True)
    final = tmp_path / "final_output.xlsx"
    final.write_bytes(b"business-output")
    observability.record_evaluation(
        physical_variable_id=VID, stage=STAGE,
        score_name="verifier_status", value="CONFIRMED", data_type="CATEGORICAL",
        source="verifier", audit_run_id="audit_1",
    )
    assert final.read_bytes() == b"business-output"  # workflow 输出不受影响
