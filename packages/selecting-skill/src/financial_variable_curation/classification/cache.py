from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from financial_variable_curation.classification.models import (
    ClassificationBatchResponse,
    ClassificationRequest,
)
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import ClassificationCacheRepository
from financial_variable_curation.database.schemas import ClassificationCacheDTO
from financial_variable_curation.database.types import utcnow


def build_classification_cache_key(
    request: ClassificationRequest,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    taxonomy_version: str,
    schema_version: str,
    base_url: str | None = None,
) -> str:
    normalized = json.dumps(
        [item.model_dump(mode="json") for item in request.variables],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "taxonomy_version": taxonomy_version,
        "schema_version": schema_version,
        "base_url": base_url or "",
        "variables": normalized,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class ClassificationCacheService:
    def __init__(self, manager: DatabaseManager) -> None:
        self.manager = manager

    def get(
        self,
        request: ClassificationRequest,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        taxonomy_version: str,
        schema_version: str,
        base_url: str | None = None,
    ) -> ClassificationBatchResponse | None:
        cache_key = build_classification_cache_key(
            request,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            taxonomy_version=taxonomy_version,
            schema_version=schema_version,
            base_url=base_url,
        )
        with self.manager.session_scope() as session:
            item = ClassificationCacheRepository(session).get(cache_key)
        if item is None:
            return None
        if item.expires_at is not None and item.expires_at < datetime.now(timezone.utc):
            return None
        return ClassificationBatchResponse.model_validate(item.classification_payload_json)

    def set(
        self,
        request: ClassificationRequest,
        response: ClassificationBatchResponse,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        taxonomy_version: str,
        schema_version: str,
        base_url: str | None = None,
        request_artifact_path: str | None = None,
        response_artifact_path: str | None = None,
        expires_at: datetime | None = None,
    ) -> str:
        cache_key = build_classification_cache_key(
            request,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            taxonomy_version=taxonomy_version,
            schema_version=schema_version,
            base_url=base_url,
        )
        with self.manager.session_scope() as session:
            ClassificationCacheRepository(session).set(
                ClassificationCacheDTO(
                    cache_key=cache_key,
                    classification_payload_json=response.model_dump(mode="json"),
                    provider=provider,
                    model=model,
                    prompt_version=prompt_version,
                    taxonomy_version=taxonomy_version,
                    schema_version=schema_version,
                    input_hash=hashlib.sha256(
                        json.dumps(
                            [item.model_dump(mode="json") for item in request.variables],
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        ).encode("utf-8")
                    ).hexdigest(),
                    request_artifact_path=request_artifact_path,
                    response_artifact_path=response_artifact_path,
                    created_at=utcnow(),
                    expires_at=expires_at,
                )
            )
        return cache_key
