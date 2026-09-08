from __future__ import annotations

import json
import random
import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from financial_variable_curation.classification.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMEmptyResponseError,
    LLMError,
    LLMInsufficientBalanceError,
    LLMInvalidRequestError,
    LLMPermissionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRealCallDisabledError,
    LLMRefusalError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from financial_variable_curation.classification.models import (
    ClassificationBatchResponse,
    ClassificationResponse,
    DataNature,
    FinancialCategory,
    LLMCallAttempt,
    LLMCallResult,
)
from financial_variable_curation.classification.settings import LLMSettings


class DeepSeekLLMClient:
    provider = "deepseek"

    def __init__(self, settings: LLMSettings, *, sdk_client: Any | None = None) -> None:
        if not settings.real_llm_enabled:
            raise LLMRealCallDisabledError(
                "Real LLM calls are disabled. Set REAL_LLM_ENABLED=true explicitly."
            )
        api_key = settings.deepseek_api_key.get_secret_value()
        if not api_key:
            raise LLMAuthenticationError(
                "DEEPSEEK_API_KEY is not set. Configure the key in the environment before enabling DeepSeek."
            )
        self.settings = settings
        if sdk_client is not None:
            self._client = sdk_client
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMInvalidRequestError(
                    "OpenAI SDK is required for DeepSeek compatibility."
                ) from exc
            self._client = OpenAI(
                api_key=api_key,
                base_url=settings.deepseek_base_url,
                timeout=settings.deepseek_timeout_seconds,
                max_retries=0,
            )

    def generate_structured(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_payload: dict,
        response_model: type[BaseModel],
        request_id: str,
    ) -> LLMCallResult:
        if not isinstance(response_model, type) or not issubclass(response_model, BaseModel):
            raise LLMInvalidRequestError("response_model must be a Pydantic BaseModel class.")
        max_attempts = self.settings.deepseek_max_retries + 1
        attempts: list[LLMCallAttempt] = []
        messages = [
            {"role": "system", "content": system_prompt + "\nReturn valid JSON."},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
        ]
        for attempt_number in range(1, max_attempts + 1):
            started_at = datetime.now(timezone.utc)
            started_perf = time.perf_counter()
            try:
                raw_response = self._client.chat.completions.create(
                    model=self.settings.deepseek_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.deepseek_max_tokens,
                )
                parsed = self._parse_response(raw_response, response_model, user_payload)
                latency_ms = int((time.perf_counter() - started_perf) * 1000)
                usage = getattr(raw_response, "usage", None)
                attempts.append(
                    LLMCallAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc),
                        status="SUCCESS",
                        response_id=getattr(raw_response, "id", None),
                        model=getattr(raw_response, "model", self.settings.deepseek_model),
                        input_tokens=getattr(usage, "prompt_tokens", None),
                        output_tokens=getattr(usage, "completion_tokens", None),
                        total_tokens=getattr(usage, "total_tokens", None),
                        latency_ms=latency_ms,
                        finish_reason=getattr(getattr(raw_response, "choices", [None])[0], "finish_reason", None),
                    )
                )
                return LLMCallResult(response=parsed, attempts=attempts, cached=False)
            except LLMError as exc:
                attempts.append(self._failure_attempt(attempt_number, started_at, exc))
                if not self._retryable(exc) or attempt_number >= max_attempts:
                    exc.attempts = attempts
                    raise exc
                self._sleep_before_retry(attempt_number)
            except Exception as exc:
                mapped = self._map_sdk_exception(exc)
                attempts.append(self._failure_attempt(attempt_number, started_at, mapped))
                if not self._retryable(mapped) or attempt_number >= max_attempts:
                    mapped.attempts = attempts
                    raise mapped
                self._sleep_before_retry(attempt_number)
        raise LLMProviderError(f"DeepSeek request failed after {max_attempts} attempts.")

    @staticmethod
    def _parse_response(
        raw_response: Any,
        response_model: type[BaseModel],
        user_payload: dict | None = None,
    ) -> BaseModel:
        choices = getattr(raw_response, "choices", [])
        if not choices:
            raise LLMEmptyResponseError("DeepSeek returned no choices.")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise LLMEmptyResponseError("DeepSeek returned no message.")
        if getattr(message, "refusal", None):
            raise LLMRefusalError("DeepSeek refused the request.")
        content = getattr(message, "content", None)
        if not content:
            raise LLMEmptyResponseError("DeepSeek returned empty content.")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMStructuredOutputError("DeepSeek returned invalid JSON.") from exc
        try:
            if (
                response_model is ClassificationBatchResponse
                and isinstance(payload, dict)
                and "results" in payload
                and "items" not in payload
            ):
                return DeepSeekLLMClient._build_batch_from_results(payload, user_payload or {})
            return response_model.model_validate(payload)
        except Exception as exc:
            detail = str(exc)
            if len(detail) > 800:
                detail = detail[:800] + "..."
            raise LLMStructuredOutputError(
                f"DeepSeek JSON failed Pydantic validation: {detail}"
            ) from exc

    @staticmethod
    def _build_batch_from_results(
        payload: dict[str, Any],
        user_payload: dict[str, Any],
    ) -> ClassificationBatchResponse:
        variables_by_id = {
            item.get("variable_id"): item
            for item in (user_payload.get("variables") or [])
            if isinstance(item, dict)
        }
        items: list[ClassificationResponse] = []
        for result in payload.get("results") or []:
            variable_id = str(result.get("variable_id") or "")
            source = variables_by_id.get(variable_id, {})
            original_name = (
                result.get("original_name")
                or result.get("standard_name")
                or source.get("original_name")
                or source.get("normalized_name")
                or ""
            )
            category = DeepSeekLLMClient._normalize_category(
                result.get("category") or result.get("category_level_1")
            )
            data_nature = DeepSeekLLMClient._normalize_data_nature(
                result.get("data_nature")
            )
            response = ClassificationResponse(
                variable_id=variable_id,
                standard_name=str(result.get("standard_name") or original_name or "")[:255],
                industry=result.get("industry") or source.get("industry_hint"),
                sector=result.get("sector"),
                commodity=result.get("commodity") or source.get("commodity_hint"),
                category_level_1=category,
                category_level_2=str(
                    result.get("category_level_2") or category.value
                )[:120],
                metric_name=str(result.get("metric_name") or original_name or "")[:255],
                data_nature=data_nature,
                market=result.get("market"),
                region=result.get("region"),
                unit=result.get("unit") or source.get("unit_hint"),
                statistical_scope=result.get("statistical_scope"),
                confidence=float(result.get("confidence") or 0.0),
                review_reasons=list(result.get("review_reasons") or []),
                is_derived=bool(result.get("is_derived", False)),
                parent_metric=result.get("parent_metric"),
                reason=result.get("reason")
                or f"DeepSeek compact response normalized to {category.value}.",
            )
            response.comparison_group_components = {
                "standard_name": response.standard_name,
                "industry": response.industry,
                "sector": response.sector,
                "commodity": response.commodity,
                "category_level_1": response.category_level_1.value,
                "category_level_2": response.category_level_2,
                "data_nature": response.data_nature.value,
                "market": response.market,
                "region": response.region,
                "unit": response.unit,
            }
            items.append(response)
        return ClassificationBatchResponse(
            batch_id=str(payload.get("batch_id") or user_payload.get("batch_id") or ""),
            items=items,
        )

    @staticmethod
    def _normalize_category(value: Any) -> FinancialCategory:
        raw = str(value or "").strip().lower()
        aliases = {
            "commodity": FinancialCategory.PRICE,
            "price": FinancialCategory.PRICE,
            "prices": FinancialCategory.PRICE,
            "spot": FinancialCategory.PRICE,
            "futures": FinancialCategory.PRICE,
            "spread": FinancialCategory.PRICE,
            "quantity": FinancialCategory.QUANTITY,
            "volume": FinancialCategory.QUANTITY,
            "supply": FinancialCategory.QUANTITY,
            "demand": FinancialCategory.QUANTITY,
            "production": FinancialCategory.QUANTITY,
            "import": FinancialCategory.QUANTITY,
            "export": FinancialCategory.QUANTITY,
            "sales": FinancialCategory.QUANTITY,
            "inventory": FinancialCategory.INVENTORY,
            "stock": FinancialCategory.INVENTORY,
            "warehouse": FinancialCategory.INVENTORY,
            "capacity": FinancialCategory.CAPACITY,
            "utilization": FinancialCategory.CAPACITY,
            "cost": FinancialCategory.COST,
            "margin": FinancialCategory.MARGIN,
            "profit": FinancialCategory.MARGIN,
            "financial": FinancialCategory.FINANCIAL,
            "revenue": FinancialCategory.FINANCIAL,
            "fundamental": FinancialCategory.FUNDAMENTAL,
            "macro": FinancialCategory.MACRO,
            "index": FinancialCategory.INDEX,
        }
        return aliases.get(raw, FinancialCategory.UNKNOWN)

    @staticmethod
    def _normalize_data_nature(value: Any) -> DataNature:
        raw = str(value or "").strip().lower()
        aliases = {
            "price": DataNature.LEVEL,
            "level": DataNature.LEVEL,
            "spot": DataNature.LEVEL,
            "futures": DataNature.LEVEL,
            "value": DataNature.LEVEL,
            "spread": DataNature.DIFFERENCE,
            "difference": DataNature.DIFFERENCE,
            "basis": DataNature.DIFFERENCE,
            "premium": DataNature.DIFFERENCE,
            "discount": DataNature.DIFFERENCE,
            "ratio": DataNature.RATIO,
            "rate": DataNature.RATIO,
            "margin": DataNature.RATIO,
            "percent_change": DataNature.PERCENT_CHANGE,
            "percent": DataNature.PERCENT_CHANGE,
            "change": DataNature.PERCENT_CHANGE,
            "index": DataNature.INDEX,
            "stock": DataNature.STOCK,
            "inventory": DataNature.STOCK,
            "flow": DataNature.FLOW,
            "volume": DataNature.FLOW,
            "aggregate": DataNature.AGGREGATE,
        }
        return aliases.get(raw, DataNature.UNKNOWN)

    @staticmethod
    def _failure_attempt(attempt_number: int, started_at: datetime, error: BaseException) -> LLMCallAttempt:
        return LLMCallAttempt(
            attempt_number=attempt_number,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            status="FAILED" if not DeepSeekLLMClient._retryable(error) else "RETRYABLE_ERROR",
            error_type=type(error).__name__,
            error_message=str(error),
        )

    @staticmethod
    def _retryable(error: BaseException) -> bool:
        return isinstance(
            error,
            (
                LLMRateLimitError,
                LLMTimeoutError,
                LLMConnectionError,
                LLMProviderError,
                LLMStructuredOutputError,
                LLMEmptyResponseError,
            ),
        )

    def _sleep_before_retry(self, attempt_number: int) -> None:
        base = min(
            self.settings.retry_max_seconds,
            self.settings.retry_min_seconds * (2 ** (attempt_number - 1)),
        )
        delay = base + random.uniform(0, self.settings.retry_jitter_seconds)
        time.sleep(min(delay, self.settings.retry_max_seconds))

    def _map_sdk_exception(self, exc: Exception) -> LLMError:
        status = getattr(exc, "status_code", None)
        class_name = type(exc).__name__
        if status == 401 or class_name == "AuthenticationError":
            return LLMAuthenticationError("DeepSeek authentication failed. Check the API key.")
        if status == 402:
            return LLMInsufficientBalanceError("DeepSeek account balance is insufficient.")
        if status == 422 or class_name == "BadRequestError":
            return LLMInvalidRequestError("DeepSeek rejected the request.")
        if status == 429 or class_name == "RateLimitError":
            return LLMRateLimitError("DeepSeek rate limit exceeded.")
        if class_name == "APITimeoutError":
            return LLMTimeoutError("DeepSeek request timed out.")
        if class_name == "APIConnectionError":
            return LLMConnectionError("DeepSeek connection failed.")
        if status in {500, 503} or class_name in {"InternalServerError", "ServiceUnavailableError"}:
            return LLMProviderError("DeepSeek reported a transient server error.")
        return LLMProviderError("DeepSeek provider error.")
