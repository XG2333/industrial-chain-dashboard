from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from financial_variable_curation.classification.cache import build_classification_cache_key
from financial_variable_curation.classification.exceptions import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMProviderError,
    LLMRealCallDisabledError,
    LLMRefusalError,
    LLMStructuredOutputError,
)
from financial_variable_curation.classification.factory import LLMClientFactory
from financial_variable_curation.classification.deepseek_provider import DeepSeekLLMClient
from financial_variable_curation.classification.mock import MockLLMClient
from financial_variable_curation.classification.models import (
    ClassificationBatchResponse,
    ClassificationRequest,
    ClassificationRequestItem,
    ClassificationResponse,
    DataNature,
    FinancialCategory,
)
from financial_variable_curation.classification.openai_provider import OpenAILLMClient
from financial_variable_curation.classification.service import BatchClassificationService
from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import (
    LlmCallRepository,
    ReviewItemRepository,
    VariableClassificationRepository,
)
from financial_variable_curation.database.services import InspectionPersistenceService
from financial_variable_curation.models.artifacts import RequestRecord
from financial_variable_curation.pipeline.inspect import run_inspection


def _persist_sample(db_manager: DatabaseManager, sample_workbook: Path, run_id: str) -> None:
    result = run_inspection(sample_workbook, run_id=run_id)
    request = RequestRecord(
        run_id=run_id,
        input_path=str(sample_workbook),
        file_hash=result.workbook_profile.file_hash,
        cli_args={"test": True},
    )
    InspectionPersistenceService(db_manager).persist(
        result,
        request_record=request,
        artifacts_dir=Path("artifacts"),
        run_id=run_id,
    )


def _request_item(variable_id: str = "var_1", name: str = "沪锡主力收盘价") -> ClassificationRequestItem:
    return ClassificationRequestItem(
        variable_id=variable_id,
        file_name="sample.xlsx",
        sheet_name="MarketData",
        original_name=name,
        normalized_name=name,
        detected_frequency="daily",
        inferred_data_type="NUMERIC",
    )


def _classification(
    variable_id: str = "var_1",
    category: FinancialCategory = FinancialCategory.PRICE,
) -> ClassificationResponse:
    response = ClassificationResponse(
        variable_id=variable_id,
        standard_name="standard",
        category_level_1=category,
        category_level_2="Price",
        metric_name="close",
        data_nature=DataNature.LEVEL,
        confidence=0.8,
        reason="test",
    )
    response.comparison_group_components = {
        "standard_name": "standard",
        "category_level_1": category.value,
        "data_nature": DataNature.LEVEL.value,
    }
    return response


class FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15


class FakeMessage:
    def __init__(self, parsed=None, refusal=None):
        self.parsed = parsed
        self.refusal = refusal


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, parsed=None, refusal=None, response_id="resp_123", model="gpt-test"):
        self.choices = [FakeChoice(FakeMessage(parsed=parsed, refusal=refusal))]
        self.id = response_id
        self.model = model
        self.usage = FakeUsage()


class FakeCompletions:
    def __init__(self, events):
        self.events = list(events)
        self.index = 0

    def parse(self, **kwargs):
        event = self.events[self.index]
        self.index += 1
        if isinstance(event, Exception):
            raise event
        return event


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, events):
        self.chat = FakeChat(FakeCompletions(events))


class _FakeError(Exception):
    pass


class _AuthenticationError(_FakeError):
    pass


class _RateLimitError(_FakeError):
    pass


class _TimeoutError(_FakeError):
    pass


class _ServerError(_FakeError):
    pass


_AuthenticationError.__name__ = "AuthenticationError"
_RateLimitError.__name__ = "RateLimitError"
_TimeoutError.__name__ = "APITimeoutError"
_ServerError.__name__ = "InternalServerError"


def _openai_settings(**overrides) -> LLMSettings:
    defaults = {
        "llm_provider": "openai",
        "openai_api_key": SecretStr("test-key"),
        "real_llm_enabled": True,
        "openai_model": "gpt-test",
        "openai_max_retries": 0,
        "retry_min_seconds": 0.001,
        "retry_max_seconds": 0.01,
        "retry_jitter_seconds": 0.0,
    }
    defaults.update(overrides)
    return LLMSettings(**defaults)


def _batch_response(*items: ClassificationResponse) -> ClassificationBatchResponse:
    return ClassificationBatchResponse(batch_id="batch_test", items=list(items))


def test_factory_creates_mock_without_openai_key() -> None:
    settings = LLMSettings(llm_provider="mock", openai_api_key=SecretStr("should-not-matter"))
    client = LLMClientFactory(settings).create("mock")
    assert isinstance(client, MockLLMClient)


def test_factory_openai_missing_key_fails() -> None:
    settings = LLMSettings(llm_provider="openai", openai_api_key=SecretStr(""), real_llm_enabled=True)
    with pytest.raises(LLMAuthenticationError):
        LLMClientFactory(settings).create("openai")


def test_factory_openai_real_calls_disabled_fails() -> None:
    settings = LLMSettings(llm_provider="openai", openai_api_key=SecretStr("x"), real_llm_enabled=False)
    with pytest.raises(LLMRealCallDisabledError):
        LLMClientFactory(settings).create("openai")


def test_factory_creates_openai_adapter() -> None:
    settings = _openai_settings()
    client = LLMClientFactory(settings).create("openai")
    assert isinstance(client, OpenAILLMClient)


def test_openai_success_maps_metadata() -> None:
    response = _batch_response(_classification())
    client = OpenAILLMClient(_openai_settings(), sdk_client=FakeClient([FakeResponse(parsed=response)]))
    result = client.generate_structured(
        task_type="variable_classification",
        system_prompt="system",
        user_payload={"variables": []},
        response_model=ClassificationBatchResponse,
        request_id="batch_test",
    )
    assert isinstance(result.response, ClassificationBatchResponse)
    attempt = result.attempts[0]
    assert attempt.response_id == "resp_123"
    assert attempt.input_tokens == 10
    assert attempt.output_tokens == 5
    assert attempt.total_tokens == 15
    assert attempt.latency_ms >= 0


def test_openai_invalid_structured_output_raises_project_error() -> None:
    client = OpenAILLMClient(
        _openai_settings(),
        sdk_client=FakeClient([FakeResponse(parsed={"bad": "payload"})]),
    )
    with pytest.raises(LLMStructuredOutputError):
        client.generate_structured(
            task_type="variable_classification",
            system_prompt="system",
            user_payload={},
            response_model=ClassificationBatchResponse,
            request_id="batch_test",
        )


def test_deepseek_compact_results_are_normalized_to_batch_response() -> None:
    raw = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(
                        '{"batch_id":"batch_test","results":['
                        '{"variable_id":"var_1","category":"Price","data_nature":"Level","confidence":0.8},'
                        '{"variable_id":"var_2","category":"Inventory","data_nature":"Stock","confidence":0.6}'
                        "]}"
                    )
                )
            )
        ]
    )
    user_payload = {
        "batch_id": "batch_test",
        "variables": [
            {
                "variable_id": "var_1",
                "original_name": "日__col_3",
                "normalized_name": "日__col_3",
            },
            {
                "variable_id": "var_2",
                "original_name": "日__col_10",
                "normalized_name": "日__col_10",
            },
        ],
    }
    result = DeepSeekLLMClient._parse_response(
        raw,
        ClassificationBatchResponse,
        user_payload,
    )
    assert isinstance(result, ClassificationBatchResponse)
    assert result.batch_id == "batch_test"
    assert result.items[0].category_level_1 == FinancialCategory.PRICE
    assert result.items[0].data_nature == DataNature.LEVEL
    assert result.items[1].category_level_1 == FinancialCategory.INVENTORY
    assert result.items[1].data_nature == DataNature.STOCK


def test_openai_empty_response_raises() -> None:
    client = OpenAILLMClient(_openai_settings(), sdk_client=FakeClient([FakeResponse(parsed=None)]))
    with pytest.raises(LLMEmptyResponseError):
        client.generate_structured(
            task_type="variable_classification",
            system_prompt="system",
            user_payload={},
            response_model=ClassificationBatchResponse,
            request_id="batch_test",
        )


def test_openai_refusal_raises() -> None:
    client = OpenAILLMClient(
        _openai_settings(),
        sdk_client=FakeClient([FakeResponse(refusal="I cannot do that.")]),
    )
    with pytest.raises(LLMRefusalError):
        client.generate_structured(
            task_type="variable_classification",
            system_prompt="system",
            user_payload={},
            response_model=ClassificationBatchResponse,
            request_id="batch_test",
        )


def test_openai_authentication_error_is_not_retried() -> None:
    client = OpenAILLMClient(
        _openai_settings(openai_max_retries=3),
        sdk_client=FakeClient([_AuthenticationError("bad")]),
    )
    with pytest.raises(LLMAuthenticationError):
        client.generate_structured(
            task_type="variable_classification",
            system_prompt="system",
            user_payload={},
            response_model=ClassificationBatchResponse,
            request_id="batch_test",
        )


def test_openai_rate_limit_is_retried_limited_times() -> None:
    events = [_RateLimitError("slow"), _RateLimitError("slower"), FakeResponse(parsed=_batch_response(_classification()))]
    client = OpenAILLMClient(_openai_settings(openai_max_retries=3), sdk_client=FakeClient(events))
    result = client.generate_structured(
        task_type="variable_classification",
        system_prompt="system",
        user_payload={},
        response_model=ClassificationBatchResponse,
        request_id="batch_test",
    )
    assert len(result.attempts) == 3
    assert result.attempts[-1].status == "SUCCESS"


def test_openai_timeout_and_server_error_are_retried() -> None:
    events = [
        _TimeoutError("timeout"),
        _ServerError("server"),
        FakeResponse(parsed=_batch_response(_classification())),
    ]
    client = OpenAILLMClient(_openai_settings(openai_max_retries=3), sdk_client=FakeClient(events))
    result = client.generate_structured(
        task_type="variable_classification",
        system_prompt="system",
        user_payload={},
        response_model=ClassificationBatchResponse,
        request_id="batch_test",
    )
    assert len(result.attempts) == 3


class CountingClient:
    def __init__(self):
        self.delegate = MockLLMClient()
        self.calls = 0

    def generate_structured(self, **kwargs):
        self.calls += 1
        return self.delegate.generate_structured(**kwargs)


class CountingFactory:
    def __init__(self):
        self.client = CountingClient()

    def create(self, provider):
        return self.client


def test_classification_service_mock_persists_and_reviews(
    db_manager: DatabaseManager,
    sample_workbook: Path,
) -> None:
    _persist_sample(db_manager, sample_workbook, "run-class-mock")
    settings = LLMSettings(llm_provider="mock")
    result = BatchClassificationService(db_manager, settings=settings).classify_run(
        "run-class-mock",
        provider="mock",
        limit=5,
        artifacts_dir="artifacts",
    )
    assert result.selected_variable_count == 5
    assert result.successful_count + result.needs_review_count == 5
    with db_manager.session_scope() as session:
        assert VariableClassificationRepository(session).count_for_run("run-class-mock") == 5


def test_classification_cache_hit_and_force_refresh(
    db_manager: DatabaseManager,
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    _persist_sample(db_manager, sample_workbook, "run-cache")
    factory = CountingFactory()
    settings = _openai_settings(openai_max_retries=0)
    service = BatchClassificationService(db_manager, settings=settings, client_factory=factory)
    first = service.classify_run(
        "run-cache",
        provider="openai",
        limit=2,
        artifacts_dir=tmp_path / "artifacts",
    )
    assert first.cache_hit_count == 0
    assert factory.client.calls == 1
    second = service.classify_run(
        "run-cache",
        provider="openai",
        limit=2,
        artifacts_dir=tmp_path / "artifacts",
    )
    assert second.cache_hit_count == 1
    assert factory.client.calls == 1
    third = service.classify_run(
        "run-cache",
        provider="openai",
        limit=2,
        force_refresh=True,
        artifacts_dir=tmp_path / "artifacts",
    )
    assert third.cache_hit_count == 0
    assert factory.client.calls == 2


def test_cache_key_isolation_provider_model_and_versions() -> None:
    request = ClassificationRequest(
        batch_id="b1",
        provider="openai",
        model="gpt-test",
        prompt_version="v1",
        taxonomy_version="tax_v1",
        schema_version="schema_v1",
        variables=[_request_item()],
    )
    key = build_classification_cache_key(
        request,
        provider="openai",
        model="gpt-test",
        prompt_version="v1",
        taxonomy_version="tax_v1",
        schema_version="schema_v1",
    )
    mock_key = build_classification_cache_key(
        request,
        provider="mock",
        model="mock",
        prompt_version="v1",
        taxonomy_version="tax_v1",
        schema_version="schema_v1",
    )
    prompt_key = build_classification_cache_key(
        request,
        provider="openai",
        model="gpt-test",
        prompt_version="v2",
        taxonomy_version="tax_v1",
        schema_version="schema_v1",
    )
    schema_key = build_classification_cache_key(
        request,
        provider="openai",
        model="gpt-test",
        prompt_version="v1",
        taxonomy_version="tax_v1",
        schema_version="schema_v2",
    )
    assert len({key, mock_key, prompt_key, schema_key}) == 4


def test_prompt_version_change_invalidates_cache(
    db_manager: DatabaseManager,
    sample_workbook: Path,
) -> None:
    _persist_sample(db_manager, sample_workbook, "run-prompt-cache")
    first_settings = LLMSettings(llm_provider="mock", llm_prompt_version="v1")
    first = BatchClassificationService(db_manager, settings=first_settings).classify_run(
        "run-prompt-cache",
        provider="mock",
        limit=2,
        artifacts_dir="artifacts",
    )
    assert first.cache_hit_count == 0
    second_settings = LLMSettings(llm_provider="mock", llm_prompt_version="v2")
    second = BatchClassificationService(db_manager, settings=second_settings).classify_run(
        "run-prompt-cache",
        provider="mock",
        limit=2,
        artifacts_dir="artifacts",
    )
    assert second.cache_hit_count == 0


def test_schema_version_change_invalidates_cache(
    db_manager: DatabaseManager,
    sample_workbook: Path,
) -> None:
    _persist_sample(db_manager, sample_workbook, "run-schema-cache")
    first_settings = LLMSettings(
        llm_provider="mock",
        llm_response_schema_version="schema_v1",
    )
    first = BatchClassificationService(db_manager, settings=first_settings).classify_run(
        "run-schema-cache",
        provider="mock",
        limit=2,
        artifacts_dir="artifacts",
    )
    assert first.cache_hit_count == 0
    second_settings = LLMSettings(
        llm_provider="mock",
        llm_response_schema_version="schema_v2",
    )
    second = BatchClassificationService(db_manager, settings=second_settings).classify_run(
        "run-schema-cache",
        provider="mock",
        limit=2,
        artifacts_dir="artifacts",
    )
    assert second.cache_hit_count == 0


def test_service_failed_batch_is_persisted_as_failed_and_review(
    db_manager: DatabaseManager,
    sample_workbook: Path,
) -> None:
    _persist_sample(db_manager, sample_workbook, "run-failed-batch")
    settings = LLMSettings(
        llm_provider="openai",
        openai_api_key=SecretStr("x"),
        real_llm_enabled=True,
        openai_model="gpt-test",
    )

    class FailingClient:
        def generate_structured(self, **kwargs):
            raise LLMProviderError("temporary provider failure")

    class FailingFactory:
        def create(self, provider):
            return FailingClient()

    result = BatchClassificationService(
        db_manager,
        settings=settings,
        client_factory=FailingFactory(),
    ).classify_run(
        "run-failed-batch",
        provider="openai",
        limit=1,
        artifacts_dir="artifacts",
    )
    assert result.failed_count == 1
    with db_manager.session_scope() as session:
        assert VariableClassificationRepository(session).count_for_run(
            "run-failed-batch", status="FAILED"
        ) == 1
        assert ReviewItemRepository(session).count_for_run(
            "run-failed-batch", status="NEEDS_REVIEW"
        ) == 1


def test_openai_api_key_not_in_repr_artifacts_or_database(
    db_manager: DatabaseManager,
    sample_workbook: Path,
    tmp_path: Path,
) -> None:
    _persist_sample(db_manager, sample_workbook, "run-key-safe")
    secret = "super-secret-openai-key"
    settings = LLMSettings(
        llm_provider="openai",
        openai_api_key=SecretStr(secret),
        real_llm_enabled=True,
        openai_model="gpt-test",
        openai_max_retries=0,
    )
    assert secret not in repr(settings)
    response = _batch_response(_classification())
    factory = CountingFactory()
    fake_client = FakeClient([FakeResponse(parsed=response)])

    class _FakeFactory:
        def create(self, provider):
            return _FakeClientWrapper(fake_client)

    class _FakeClientWrapper:
        def __init__(self, client):
            self._client = client

        def generate_structured(self, **kwargs):
            return MockLLMClient().generate_structured(**kwargs)

    # Use a real counting fake client while preserving the openai key context.
    service = BatchClassificationService(
        db_manager,
        settings=settings,
        client_factory=_FakeFactory(),
    )
    result = service.classify_run(
        "run-key-safe",
        provider="openai",
        limit=1,
        artifacts_dir=tmp_path / "artifacts",
    )
    assert result.successful_count == 1
    artifact_text = "".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "artifacts" / "run-key-safe" / "classification").glob("*.json")
    )
    assert secret not in artifact_text
    with db_manager.session_scope() as session:
        call_payload = "".join(
            item.model_dump(mode="json").__repr__() for item in LlmCallRepository(session).list_for_run("run-key-safe")
        )
        classification_payload = "".join(
            item.model_dump(mode="json").__repr__()
            for item in VariableClassificationRepository(session).list_for_run("run-key-safe")
        )
    assert secret not in call_payload
    assert secret not in classification_payload
