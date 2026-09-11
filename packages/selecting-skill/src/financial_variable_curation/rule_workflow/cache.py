from __future__ import annotations

import hashlib
import json

from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import RuleParseCacheRepository
from financial_variable_curation.database.schemas import RuleParseCacheDTO
from financial_variable_curation.database.types import utcnow
from financial_variable_curation.rule_workflow.models import RuleSetDocument


def rule_parse_cache_key(
    *,
    source_hash: str,
    provider: str,
    model: str,
    prompt_version: str,
    taxonomy_version: str,
    schema_version: str,
    base_url: str | None = None,
) -> str:
    payload = {
        "source_hash": source_hash,
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "taxonomy_version": taxonomy_version,
        "schema_version": schema_version,
        "base_url": base_url or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class RuleParseCacheService:
    def __init__(self, manager: DatabaseManager) -> None:
        self.manager = manager

    def get(
        self,
        *,
        source_hash: str,
        provider: str,
        model: str,
        prompt_version: str,
        taxonomy_version: str,
        schema_version: str,
        base_url: str | None = None,
    ) -> RuleSetDocument | None:
        key = rule_parse_cache_key(
            source_hash=source_hash,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            taxonomy_version=taxonomy_version,
            schema_version=schema_version,
            base_url=base_url,
        )
        with self.manager.session_scope() as session:
            item = RuleParseCacheRepository(session).get(key)
        if item is None:
            return None
        return RuleSetDocument.model_validate(item.parsed_payload_json)

    def set(
        self,
        *,
        source_hash: str,
        provider: str,
        model: str,
        prompt_version: str,
        taxonomy_version: str,
        schema_version: str,
        base_url: str | None = None,
        document: RuleSetDocument,
    ) -> str:
        key = rule_parse_cache_key(
            source_hash=source_hash,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            taxonomy_version=taxonomy_version,
            schema_version=schema_version,
            base_url=base_url,
        )
        with self.manager.session_scope() as session:
            RuleParseCacheRepository(session).set(
                RuleParseCacheDTO(
                    cache_key=key,
                    source_hash=source_hash,
                    provider=provider,
                    model=model,
                    prompt_version=prompt_version,
                    taxonomy_version=taxonomy_version,
                    schema_version=schema_version,
                    parsed_payload_json=document.model_dump(mode="json"),
                    created_at=utcnow(),
                )
            )
        return key
