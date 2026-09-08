from __future__ import annotations

import concurrent.futures
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from financial_variable_curation.classification.artifact_writer import ClassificationArtifactWriter
from financial_variable_curation.classification.cache import ClassificationCacheService
from financial_variable_curation.classification.exceptions import (
    LLMError,
    LLMInvalidRequestError,
    LLMRealCallDisabledError,
)
from financial_variable_curation.classification.factory import LLMClientFactory
from financial_variable_curation.classification.mock import MockLLMClient
from financial_variable_curation.classification.models import (
    ClassificationBatchResponse,
    ClassificationRequest,
    ClassificationRequestItem,
    ClassificationResponse,
    ClassificationRunResult,
    LLMCallResult,
    build_comparison_group_key,
    classification_request_hash,
)
from financial_variable_curation.classification.protocols import LLMClient
from financial_variable_curation.classification.prompts import (
    load_system_prompt,
    load_user_prompt,
)
from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.classification.validation import apply_issues, validate_batch
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import (
    AuditEventRepository,
    LlmCallRepository,
    ReviewItemRepository,
    VariableClassificationRepository,
    VariableQualityRepository,
    VariableRepository,
)
from financial_variable_curation.database.schemas import (
    AuditEventDTO,
    ClassificationCandidateDTO,
    LlmCallDTO,
    ReviewItemDTO,
    VariableClassificationDTO,
)
from financial_variable_curation.database.types import utcnow


class BatchClassificationService:
    def __init__(
        self,
        manager: DatabaseManager | None = None,
        *,
        settings: LLMSettings | None = None,
        client_factory: LLMClientFactory | None = None,
        cache_service: ClassificationCacheService | None = None,
    ) -> None:
        self.manager = manager or DatabaseManager()
        self.settings = settings or LLMSettings.from_env()
        self.client_factory = client_factory or LLMClientFactory(self.settings)
        self.cache_service = cache_service or ClassificationCacheService(self.manager)

    def _classify_batch_api(
        self,
        *,
        request: ClassificationRequest,
        selected_provider: str,
        effective_model: str,
        max_tokens: int,
    ) -> LLMCallResult:
        """Isolated API call for one batch. Runs safely in a thread."""
        client = self.client_factory.create(selected_provider)
        return client.generate_structured(
            task_type="variable_classification",
            system_prompt=load_system_prompt(),
            user_payload=self._user_payload(request),
            response_model=ClassificationBatchResponse,
            request_id=request.batch_id,
        )

    def classify_run(
        self,
        run_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        limit: int | None = None,
        variable_ids: list[str] | None = None,
        batch_size: int | None = None,
        force_refresh: bool = False,
        dry_run: bool = False,
        artifacts_dir: str | Path = "artifacts",
        skip_non_data: bool = False,
    ) -> ClassificationRunResult:
        selected_provider = (provider or self.settings.llm_provider).lower()
        if selected_provider == "openai":
            effective_model = model or self.settings.openai_model
        elif selected_provider == "deepseek":
            effective_model = model or self.settings.deepseek_model
        else:
            effective_model = model or "mock"
        if selected_provider in {"openai", "deepseek"} and not self.settings.real_llm_enabled:
            raise LLMRealCallDisabledError(
                "Real LLM calls are disabled. Set REAL_LLM_ENABLED=true explicitly."
            )
        if (
            selected_provider == "openai"
            and not dry_run
            and limit is None
            and not variable_ids
        ):
            raise LLMInvalidRequestError(
                "--limit or --variable-id is required for real provider calls."
            )

        candidates = self._load_candidates(
            run_id,
            limit=limit,
            variable_ids=variable_ids,
            skip_non_data=skip_non_data,
        )
        if selected_provider == "openai" and len(candidates) > self.settings.real_llm_max_variables:
            raise LLMInvalidRequestError(
                f"Real provider validation is limited to {self.settings.real_llm_max_variables} variables."
            )
        request_items = [self._build_request_item(candidate) for candidate in candidates]
        effective_batch_size = batch_size or (
            self.settings.deepseek_batch_size if selected_provider == "deepseek" else self.settings.openai_batch_size
        )
        batches = [
            request_items[index : index + effective_batch_size]
            for index in range(0, len(request_items), effective_batch_size)
        ]
        requests = [
            ClassificationRequest(
                batch_id=f"batch_{uuid4().hex[:12]}",
                provider=selected_provider,
                model=effective_model,
                prompt_version=self.settings.llm_prompt_version,
                taxonomy_version=self.settings.llm_taxonomy_version,
                schema_version=self.settings.llm_response_schema_version,
                variables=items,
            )
            for items in batches
        ]
        request_hashes = {request.batch_id: classification_request_hash(request) for request in requests}

        result = ClassificationRunResult(
            run_id=run_id,
            provider=selected_provider,
            model=effective_model,
            prompt_version=self.settings.llm_prompt_version,
            taxonomy_version=self.settings.llm_taxonomy_version,
            schema_version=self.settings.llm_response_schema_version,
            selected_variable_count=len(request_items),
            batch_count=len(requests),
            artifacts_path=str(Path(artifacts_dir) / run_id / "classification"),
            dry_run=dry_run,
        )
        if dry_run:
            self.client_factory.create(selected_provider)
            self._write_dry_run_audit(run_id, request_hashes)
            return result

        writer = ClassificationArtifactWriter(artifacts_dir, run_id)
        writer.write_audit(result)
        mock_responses: list[ClassificationResponse] = []
        openai_responses: list[ClassificationResponse] = []
        original_names = {item.variable_id: item.original_name for item in request_items}
        client = self.client_factory.create(selected_provider)

        for request in requests:
            request_hash = request_hashes[request.batch_id]
            request_path = writer.write_request(request)
            cache_hit = False
            if not force_refresh:
                cached = self.cache_service.get(
                    request,
                    provider=selected_provider,
                    model=effective_model,
                    prompt_version=self.settings.llm_prompt_version,
                    taxonomy_version=self.settings.llm_taxonomy_version,
                    schema_version=self.settings.llm_response_schema_version,
                    base_url=self.settings.deepseek_base_url if selected_provider == "deepseek" else None,
                )
                if cached is not None:
                    cache_hit = True
                    result.cache_hit_count += 1
                    self._persist_cached_batch(run_id, request, cached, request_hash, request_path)
                    self._persist_classifications(
                        run_id,
                        request,
                        cached.items,
                        llm_call_id=None,
                        cached=True,
                        result=result,
                    )
                    if selected_provider == "openai":
                        openai_responses.extend(cached.items)
                        mock_result = MockLLMClient().generate_structured(
                            task_type="variable_classification",
                            system_prompt=load_system_prompt(),
                            user_payload=self._user_payload(request),
                            response_model=ClassificationBatchResponse,
                            request_id=request.batch_id,
                        )
                        mock_response = mock_result.response
                        if isinstance(mock_response, ClassificationBatchResponse):
                            mock_responses.extend(mock_response.items)
                    continue
            try:
                call_result = client.generate_structured(
                    task_type="variable_classification",
                    system_prompt=load_system_prompt(),
                    user_payload=self._user_payload(request),
                    response_model=ClassificationBatchResponse,
                    request_id=request.batch_id,
                )
                response = self._validated_response(request, call_result)
                response_path = writer.write_response(response)
                self._persist_llm_calls(run_id, request, call_result, request_hash, request_path, response_path)
                for attempt in call_result.attempts:
                    result.input_tokens += attempt.input_tokens or 0
                    result.output_tokens += attempt.output_tokens or 0
                    result.total_tokens += attempt.total_tokens or 0
                self._persist_classifications(
                    run_id,
                    request,
                    response.items,
                    llm_call_id=f"llm_{request_hash[:16]}_a{len(call_result.attempts)}",
                    cached=False,
                    result=result,
                )
                self.cache_service.set(
                    request,
                    response,
                    provider=selected_provider,
                    model=effective_model,
                    prompt_version=self.settings.llm_prompt_version,
                    taxonomy_version=self.settings.llm_taxonomy_version,
                    schema_version=self.settings.llm_response_schema_version,
                    base_url=self.settings.deepseek_base_url if selected_provider == "deepseek" else None,
                    request_artifact_path=str(request_path),
                    response_artifact_path=str(response_path),
                )
                if selected_provider == "openai":
                    openai_responses.extend(response.items)
            except LLMError as exc:
                result.failed_count += len(request.variables)
                result.errors.append(f"{request.batch_id}: {type(exc).__name__}: {exc}")
                attempts = getattr(exc, "attempts", [])
                self._persist_llm_attempts(
                    run_id,
                    request,
                    request_hash,
                    request_path,
                    attempts=attempts,
                    response_path=None,
                )
                self._persist_failed_batch(run_id, request, request_hash, request_path, exc)
                if selected_provider == "openai":
                    continue
            if selected_provider == "openai":
                mock_result = MockLLMClient().generate_structured(
                    task_type="variable_classification",
                    system_prompt=load_system_prompt(),
                    user_payload=self._user_payload(request),
                    response_model=ClassificationBatchResponse,
                    request_id=request.batch_id,
                )
                mock_response = mock_result.response
                if isinstance(mock_response, ClassificationBatchResponse):
                    mock_responses.extend(mock_response.items)

        result.total_llm_calls = self._count_llm_calls(run_id)
        if selected_provider == "openai":
            writer.write_comparison(
                original_names=original_names,
                mock_responses=mock_responses,
                openai_responses=openai_responses,
            )
        writer.write_audit(result)
        return result

    def _load_candidates(
        self,
        run_id: str,
        *,
        limit: int | None,
        variable_ids: list[str] | None,
        skip_non_data: bool = False,
    ) -> list[ClassificationCandidateDTO]:
        with self.manager.session_scope() as session:
            variables = VariableRepository(session).list_classification_candidates(
                run_id,
                limit=limit,
                variable_ids=variable_ids,
                skip_non_data=skip_non_data,
            )
            qualities = {
                item.variable_id: item
                for item in VariableQualityRepository(session).list_by_run_id(run_id)
            }
        for candidate in variables:
            if candidate.quality is None:
                candidate.quality = qualities.get(candidate.variable.variable_id)
        return variables

    @staticmethod
    def _build_request_item(candidate: ClassificationCandidateDTO) -> ClassificationRequestItem:
        variable = candidate.variable
        quality = candidate.quality
        return ClassificationRequestItem(
            variable_id=variable.variable_id,
            file_name=candidate.file_name,
            sheet_name=candidate.sheet_name,
            original_name=variable.original_name,
            normalized_name=variable.normalized_name,
            unit_hint=variable.unit_hint,
            detected_frequency=quality.detected_frequency if quality else "unknown",
            inferred_data_type=variable.inferred_data_type or "",
            sample_values=[],
            quality_summary={
                "observation_count": quality.observation_count if quality else 0,
                "missing_rate": quality.missing_rate if quality else 1.0,
                "unique_value_count": quality.unique_value_count if quality else 0,
            },
        )

    @staticmethod
    def _user_payload(request: ClassificationRequest) -> dict[str, Any]:
        variable_batch_json = str(request.model_dump(mode="json"))
        return {
            "instruction": load_user_prompt(variable_batch_json),
            "batch_id": request.batch_id,
            "provider": request.provider,
            "model": request.model,
            "variables": [item.model_dump(mode="json") for item in request.variables],
        }

    def _validated_response(
        self,
        request: ClassificationRequest,
        call_result: LLMCallResult,
    ) -> ClassificationBatchResponse:
        response = call_result.response
        if not isinstance(response, ClassificationBatchResponse):
            from financial_variable_curation.classification.exceptions import LLMStructuredOutputError

            raise LLMStructuredOutputError("Provider returned the wrong response model.")
        issues = validate_batch(request.variables, response.items)
        for item in response.items:
            apply_issues(item, issues)
        return response

    def _persist_llm_calls(
        self,
        run_id: str,
        request: ClassificationRequest,
        call_result: LLMCallResult,
        request_hash: str,
        request_path: Path,
        response_path: Path,
    ) -> None:
        self._persist_llm_attempts(
            run_id,
            request,
            request_hash,
            request_path,
            attempts=call_result.attempts,
            response_path=response_path,
        )

    def _persist_llm_attempts(
        self,
        run_id: str,
        request: ClassificationRequest,
        request_hash: str,
        request_path: Path,
        *,
        attempts: list[Any],
        response_path: Path | None,
    ) -> None:
        with self.manager.unit_of_work() as uow:
            repository = LlmCallRepository(uow.session)
            for attempt in attempts:
                repository.add(
                    LlmCallDTO(
                        llm_call_id=f"llm_{request_hash[:16]}_a{attempt.attempt_number}",
                        run_id=run_id,
                        batch_id=request.batch_id,
                        task_type="variable_classification",
                        provider=request.provider,
                        model=request.model,
                        prompt_version=request.prompt_version,
                        taxonomy_version=request.taxonomy_version,
                        request_hash=request_hash,
                        response_status=attempt.status,
                        response_id=attempt.response_id,
                        input_tokens=attempt.input_tokens,
                        output_tokens=attempt.output_tokens,
                        total_tokens=attempt.total_tokens,
                        latency_ms=attempt.latency_ms,
                        cached=False,
                        attempt_count=attempt.attempt_number,
                        error_type=attempt.error_type,
                        error_message=attempt.error_message,
                        request_artifact_path=str(request_path),
                        response_artifact_path=str(response_path) if response_path else None,
                        created_at=attempt.started_at,
                        completed_at=attempt.completed_at,
                    )
                )

    def _persist_cached_batch(
        self,
        run_id: str,
        request: ClassificationRequest,
        response: ClassificationBatchResponse,
        request_hash: str,
        request_path: Path,
    ) -> None:
        with self.manager.unit_of_work() as uow:
            LlmCallRepository(uow.session).add(
                LlmCallDTO(
                    llm_call_id=f"llm_{request_hash[:16]}_cache",
                    run_id=run_id,
                    batch_id=request.batch_id,
                    task_type="variable_classification",
                    provider=request.provider,
                    model=request.model,
                    prompt_version=request.prompt_version,
                    taxonomy_version=request.taxonomy_version,
                    request_hash=request_hash,
                    response_status="CACHE_HIT",
                    cached=True,
                    attempt_count=1,
                    request_artifact_path=str(request_path),
                    response_artifact_path=None,
                    created_at=utcnow(),
                    completed_at=utcnow(),
                )
            )

    def _persist_classifications(
        self,
        run_id: str,
        request: ClassificationRequest,
        responses: list[ClassificationResponse],
        *,
        llm_call_id: str | None,
        cached: bool,
        result: ClassificationRunResult,
    ) -> None:
        dto_items: list[VariableClassificationDTO] = []
        review_items: list[ReviewItemDTO] = []
        with self.manager.unit_of_work() as uow:
            classification_repo = VariableClassificationRepository(uow.session)
            review_repo = ReviewItemRepository(uow.session)
            for response in responses:
                status = "NEEDS_REVIEW" if response.review_reasons else "COMPLETED"
                if status == "NEEDS_REVIEW":
                    result.needs_review_count += 1
                else:
                    result.successful_count += 1
                classification_id = self._stable_id(
                    run_id, response.variable_id, request.provider
                )
                dto_items.append(
                    VariableClassificationDTO(
                        classification_id=classification_id,
                        variable_id=response.variable_id,
                        llm_call_id=llm_call_id,
                        run_id=run_id,
                        batch_id=request.batch_id,
                        provider=request.provider,
                        model=request.model,
                        prompt_version=request.prompt_version,
                        taxonomy_version=request.taxonomy_version,
                        schema_version=request.schema_version,
                        response_id=None,
                        standard_name=response.standard_name,
                        industry=response.industry,
                        sector=response.sector,
                        commodity=response.commodity,
                        category_level_1=response.category_level_1.value,
                        category_level_2=response.category_level_2,
                        metric_name=response.metric_name,
                        data_nature=response.data_nature.value,
                        market=response.market,
                        region=response.region,
                        unit=response.unit,
                        statistical_scope=response.statistical_scope,
                        comparison_group_key=build_comparison_group_key(response),
                        comparison_group_components_json=response.comparison_group_components,
                        confidence=response.confidence,
                        reason=response.reason,
                        classification_status=status,
                        review_reasons_json=response.review_reasons,
                        is_derived=response.is_derived,
                        parent_metric=response.parent_metric,
                        created_at=utcnow(),
                    )
                )
                if status == "NEEDS_REVIEW":
                    reason_code = response.review_reasons[0] if response.review_reasons else "LOW_CONFIDENCE"
                    review_items.append(
                        ReviewItemDTO(
                            review_item_id=self._stable_id(
                                run_id, response.variable_id, "review", request.provider
                            ),
                            run_id=run_id,
                            entity_type="variable",
                            entity_id=response.variable_id,
                            review_type="CLASSIFICATION_REVIEW",
                            status="NEEDS_REVIEW",
                            reason_code=reason_code,
                            reason_text="; ".join(response.review_reasons),
                            resolution_json={
                                "provider": request.provider,
                                "batch_id": request.batch_id,
                                "cached": cached,
                            },
                            created_at=utcnow(),
                        )
                    )
            classification_repo.upsert_batch(dto_items)
            for review_item in review_items:
                review_repo.upsert(review_item)
            AuditEventRepository(uow.session).add(
                AuditEventDTO(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="CACHE_HIT" if cached else "CLASSIFICATION_BATCH_COMPLETED",
                    entity_type="classification_batch",
                    entity_id=request.batch_id,
                    event_payload_json={
                        "provider": request.provider,
                        "batch_id": request.batch_id,
                        "variable_count": len(responses),
                    },
                    created_at=utcnow(),
                )
            )

    def _persist_failed_batch(
        self,
        run_id: str,
        request: ClassificationRequest,
        request_hash: str,
        request_path: Path,
        error: LLMError,
    ) -> None:
        with self.manager.unit_of_work() as uow:
            classification_repo = VariableClassificationRepository(uow.session)
            review_repo = ReviewItemRepository(uow.session)
            audit_repo = AuditEventRepository(uow.session)
            for item in request.variables:
                classification_repo.upsert_batch(
                    [
                        VariableClassificationDTO(
                            classification_id=self._stable_id(
                                run_id, item.variable_id, request.provider
                            ),
                            variable_id=item.variable_id,
                            run_id=run_id,
                            batch_id=request.batch_id,
                            provider=request.provider,
                            model=request.model,
                            prompt_version=request.prompt_version,
                            taxonomy_version=request.taxonomy_version,
                            schema_version=request.schema_version,
                            classification_status="FAILED",
                            review_reasons_json=["LLM_FAILED"],
                            confidence=0.0,
                            created_at=utcnow(),
                        )
                    ]
                )
                review_repo.upsert(
                    ReviewItemDTO(
                        review_item_id=self._stable_id(
                            run_id, item.variable_id, "review", request.provider
                        ),
                        run_id=run_id,
                        entity_type="variable",
                        entity_id=item.variable_id,
                        review_type="CLASSIFICATION_REVIEW",
                        status="NEEDS_REVIEW",
                        reason_code="LLM_FAILED",
                        reason_text=f"{type(error).__name__}: {error}",
                        resolution_json={"batch_id": request.batch_id, "request_hash": request_hash},
                        created_at=utcnow(),
                    )
                )
            audit_repo.add(
                AuditEventDTO(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="CLASSIFICATION_BATCH_FAILED",
                    entity_type="classification_batch",
                    entity_id=request.batch_id,
                    event_payload_json={
                        "provider": request.provider,
                        "batch_id": request.batch_id,
                        "variable_count": len(request.variables),
                        "error_type": type(error).__name__,
                    },
                    created_at=utcnow(),
                )
            )

    def _write_dry_run_audit(self, run_id: str, request_hashes: dict[str, str]) -> None:
        with self.manager.unit_of_work() as uow:
            AuditEventRepository(uow.session).add(
                AuditEventDTO(
                    event_id=str(uuid4()),
                    run_id=run_id,
                    event_type="CLASSIFICATION_DRY_RUN",
                    entity_type="classification_run",
                    entity_id=run_id,
                    event_payload_json={"batch_count": len(request_hashes)},
                    created_at=utcnow(),
                )
            )

    def _count_llm_calls(self, run_id: str) -> int:
        with self.manager.session_scope() as session:
            return len(LlmCallRepository(session).list_for_run(run_id))

    @staticmethod
    def _stable_id(*parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
