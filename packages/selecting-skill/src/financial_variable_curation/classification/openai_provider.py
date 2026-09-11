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
    LLMInvalidRequestError,
    LLMPermissionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRealCallDisabledError,
    LLMRefusalError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)
from financial_variable_curation.classification.models import LLMCallAttempt, LLMCallResult
from financial_variable_curation.classification.settings import LLMSettings


class OpenAILLMClient:
    provider = "openai"

    def __init__(
        self,
        settings: LLMSettings,
        *,
        sdk_client: Any | None = None,
    ) -> None:
        if not settings.real_llm_enabled:
            raise LLMRealCallDisabledError(
                "Real LLM calls are disabled. Set REAL_LLM_ENABLED=true explicitly."
            )
        api_key = settings.openai_api_key.get_secret_value()
        if not api_key:
            raise LLMAuthenticationError(
                "OPENAI_API_KEY is not set. Configure the key in the environment before enabling OpenAI."
            )
        self.settings = settings
        if sdk_client is not None:
            self._client = sdk_client
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMInvalidRequestError(
                    "OpenAI SDK is not installed. Install the 'ai' optional dependency."
                ) from exc
            self._client = OpenAI(
                api_key=api_key,
                timeout=settings.openai_timeout_seconds,
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
        max_attempts = self.settings.openai_max_retries + 1
        attempts: list[LLMCallAttempt] = []
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False, default=str),
            },
        ]
        for attempt_number in range(1, max_attempts + 1):
            started_at = datetime.now(timezone.utc)
            started_perf = time.perf_counter()
            try:
                raw_response = self._client.chat.completions.parse(
                    model=self.settings.openai_model,
                    messages=messages,
                    response_format=response_model,
                    temperature=self.settings.llm_temperature,
                )
                parsed = self._extract_parsed(raw_response, response_model)
                latency_ms = int((time.perf_counter() - started_perf) * 1000)
                usage = getattr(raw_response, "usage", None)
                attempts.append(
                    LLMCallAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc),
                        status="SUCCESS",
                        response_id=getattr(raw_response, "id", None),
                        model=getattr(raw_response, "model", self.settings.openai_model),
                        input_tokens=getattr(usage, "prompt_tokens", None),
                        output_tokens=getattr(usage, "completion_tokens", None),
                        total_tokens=getattr(usage, "total_tokens", None),
                        latency_ms=latency_ms,
                    )
                )
                return LLMCallResult(response=parsed, attempts=attempts, cached=False)
            except LLMError as exc:
                attempts.append(
                    LLMCallAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc),
                        status="FAILED" if not self._retryable(exc) else "RETRYABLE_ERROR",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
                if not self._retryable(exc) or attempt_number >= max_attempts:
                    exc.attempts = attempts
                    raise exc
                self._sleep_before_retry(attempt_number)
            except Exception as exc:
                if type(exc).__name__ == "ValidationError":
                    mapped = LLMStructuredOutputError(
                        "OpenAI structured output failed Pydantic validation."
                    )
                    mapped.attempts = attempts
                    attempts.append(
                        LLMCallAttempt(
                            attempt_number=attempt_number,
                            started_at=started_at,
                            completed_at=datetime.now(timezone.utc),
                            status="RETRYABLE_ERROR",
                            error_type=type(mapped).__name__,
                            error_message=str(mapped),
                        )
                    )
                    if attempt_number >= max_attempts:
                        raise mapped
                    self._sleep_before_retry(attempt_number)
                    continue
                mapped = self._map_sdk_exception(exc)
                attempts.append(
                    LLMCallAttempt(
                        attempt_number=attempt_number,
                        started_at=started_at,
                        completed_at=datetime.now(timezone.utc),
                        status="FAILED" if not self._retryable(mapped) else "RETRYABLE_ERROR",
                        error_type=type(mapped).__name__,
                        error_message=str(mapped),
                    )
                )
                if not self._retryable(mapped) or attempt_number >= max_attempts:
                    mapped.attempts = attempts
                    raise mapped
                self._sleep_before_retry(attempt_number)
        raise LLMProviderError(f"OpenAI request failed after {max_attempts} attempts.")

    def _extract_parsed(self, raw_response: Any, response_model: type[BaseModel]) -> BaseModel:
        choices = getattr(raw_response, "choices", [])
        if not choices:
            raise LLMEmptyResponseError("OpenAI returned no choices.")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise LLMEmptyResponseError("OpenAI returned no message.")
        refusal = getattr(message, "refusal", None)
        if refusal:
            raise LLMRefusalError("OpenAI refused the classification request.")
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise LLMEmptyResponseError("OpenAI returned an empty structured response.")
        if not isinstance(parsed, response_model):
            raise LLMStructuredOutputError(
                "OpenAI structured output did not match the requested Pydantic model."
            )
        return parsed

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

    def _map_sdk_exception(self, exc: Exception) -> LLMProviderError:
        class_name = type(exc).__name__
        if class_name == "AuthenticationError":
            return LLMAuthenticationError("OpenAI authentication failed. Check the API key.")
        if class_name == "PermissionDeniedError":
            return LLMPermissionError("OpenAI permission denied.")
        if class_name == "RateLimitError":
            return LLMRateLimitError("OpenAI rate limit exceeded.")
        if class_name == "APITimeoutError":
            return LLMTimeoutError("OpenAI request timed out.")
        if class_name == "APIConnectionError":
            return LLMConnectionError("OpenAI connection failed.")
        if class_name == "BadRequestError":
            return LLMInvalidRequestError("OpenAI rejected the request.")
        if class_name in {"InternalServerError", "ServiceUnavailableError"}:
            return LLMProviderError("OpenAI reported a transient server error.")
        return LLMProviderError("OpenAI provider error.")
