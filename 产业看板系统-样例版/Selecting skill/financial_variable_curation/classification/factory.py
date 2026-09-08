from __future__ import annotations

from financial_variable_curation.classification.exceptions import LLMInvalidRequestError
from financial_variable_curation.classification.mock import MockLLMClient
from financial_variable_curation.classification.openai_provider import OpenAILLMClient
from financial_variable_curation.classification.deepseek_provider import DeepSeekLLMClient
from financial_variable_curation.classification.settings import LLMSettings


class LLMClientFactory:
    def __init__(self, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_env()

    def create(self, provider: str | None = None):
        selected = (provider or self.settings.llm_provider).lower()
        if selected == "mock":
            return MockLLMClient()
        if selected == "openai":
            return OpenAILLMClient(self.settings)
        if selected == "deepseek":
            return DeepSeekLLMClient(self.settings)
        raise LLMInvalidRequestError(f"Unsupported LLM provider: {selected}")
