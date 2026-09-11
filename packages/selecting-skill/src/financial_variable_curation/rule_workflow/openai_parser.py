from __future__ import annotations

from financial_variable_curation.classification.exceptions import (
    LLMRealCallDisabledError,
    LLMStructuredOutputError,
)
from financial_variable_curation.classification.factory import LLMClientFactory
from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.rule_workflow.models import (
    RuleParserProviderResult,
    RuleSetDocument,
)
from financial_variable_curation.rule_workflow.prompts import (
    load_rule_system_prompt,
    load_rule_user_prompt,
)


class OpenAIRuleParser:
    provider = "openai"

    def __init__(
        self,
        *,
        settings: LLMSettings | None = None,
        client_factory: LLMClientFactory | None = None,
    ) -> None:
        self.settings = settings or LLMSettings.from_env(provider="openai")
        self.client_factory = client_factory or LLMClientFactory(self.settings)

    def parse(self, text: str, context: dict | None = None) -> RuleParserProviderResult:
        if not self.settings.real_llm_enabled:
            raise LLMRealCallDisabledError(
                "Real LLM calls are disabled. Set REAL_LLM_ENABLED=true explicitly."
            )
        context = context or {}
        client = self.client_factory.create("openai")
        user_payload = {
            "instruction": load_rule_user_prompt(text),
            "rule_text": text,
            "rule_set_name": context.get("rule_set_name", "user_rules"),
            "schema_version": context.get("schema_version", "rule_schema_v1"),
        }
        result = client.generate_structured(
            task_type="rule_parsing",
            system_prompt=load_rule_system_prompt(),
            user_payload=user_payload,
            response_model=RuleSetDocument,
            request_id=context.get("parse_run_id", "rule_parse"),
        )
        document = result.response
        if not isinstance(document, RuleSetDocument):
            raise LLMStructuredOutputError("Rule parser returned the wrong structured model.")
        return RuleParserProviderResult(document=document, llm_call_result=result)
