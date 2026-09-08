from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from financial_variable_curation.classification.models import LLMCallResult


@runtime_checkable
class LLMClient(Protocol):
    provider: str

    def generate_structured(
        self,
        *,
        task_type: str,
        system_prompt: str,
        user_payload: dict,
        response_model: type[BaseModel],
        request_id: str,
    ) -> LLMCallResult:
        """Generate a structured response through a provider adapter."""
