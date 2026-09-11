from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

import os
from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(frozen=True)
class LLMSettings:
    llm_provider: str = "mock"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60.0
    openai_max_retries: int = 3
    openai_batch_size: int = 20
    openai_max_concurrency: int = 2
    llm_temperature: float = 0.0
    llm_prompt_version: str = "variable_classifier_v1"
    llm_taxonomy_version: str = "taxonomy_v1"
    llm_response_schema_version: str = "classification_response_v1"
    rule_schema_version: str = "rule_schema_v1"

    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 120.0
    deepseek_max_retries: int = 3
    deepseek_batch_size: int = 20
    deepseek_max_concurrency: int = 4
    deepseek_max_tokens: int = 16000

    real_llm_enabled: bool = False
    real_llm_max_variables: int = 20
    retry_min_seconds: float = 1.0
    retry_max_seconds: float = 30.0
    retry_jitter_seconds: float = 1.0

    @classmethod
    def from_env(
        cls,
        *,
        provider: str | None = None,
        model: str | None = None,
        batch_size: int | None = None,
        max_variables: int | None = None,
    ) -> LLMSettings:
        return cls(
            llm_provider=(provider or os.getenv("LLM_PROVIDER", "mock")).lower(),
            openai_api_key=SecretStr(os.getenv("OPENAI_API_KEY", "")),
            openai_model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
            openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "3")),
            openai_batch_size=batch_size or int(os.getenv("OPENAI_BATCH_SIZE", "20")),
            openai_max_concurrency=int(os.getenv("OPENAI_MAX_CONCURRENCY", "2")),
            llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            llm_prompt_version=os.getenv("LLM_PROMPT_VERSION", "variable_classifier_v1"),
            llm_taxonomy_version=os.getenv("LLM_TAXONOMY_VERSION", "taxonomy_v1"),
            llm_response_schema_version=os.getenv(
                "LLM_RESPONSE_SCHEMA_VERSION", "classification_response_v1"
            ),
            rule_schema_version=os.getenv("RULE_SCHEMA_VERSION", "rule_schema_v1"),
            deepseek_api_key=SecretStr(os.getenv("DEEPSEEK_API_KEY", "")),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            deepseek_timeout_seconds=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "120")),
            deepseek_max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
            deepseek_batch_size=batch_size or int(os.getenv("DEEPSEEK_BATCH_SIZE", "20")),
            deepseek_max_concurrency=int(os.getenv("DEEPSEEK_MAX_CONCURRENCY", "4")),
            deepseek_max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "16000")),
            real_llm_enabled=os.getenv("REAL_LLM_ENABLED", "false").strip().lower()
            in {"1", "true", "yes"},
            real_llm_max_variables=max_variables or int(os.getenv("REAL_LLM_MAX_VARIABLES", "20")),
            retry_min_seconds=float(os.getenv("LLM_RETRY_MIN_SECONDS", "1")),
            retry_max_seconds=float(os.getenv("LLM_RETRY_MAX_SECONDS", "30")),
            retry_jitter_seconds=float(os.getenv("LLM_RETRY_JITTER_SECONDS", "1")),
        )
