from __future__ import annotations

from collections import Counter
from pathlib import Path
from uuid import uuid4

from financial_variable_curation.classification.exceptions import LLMRealCallDisabledError
from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import (
    LlmCallRepository,
    PipelineRunRepository,
    ReviewItemRepository,
    RuleConflictRepository,
    RuleParseCacheRepository,
    RuleParseRunRepository,
    RuleRepository,
    RuleSetRepository,
)
from financial_variable_curation.database.schemas import (
    LlmCallDTO,
    PipelineRunDTO,
    ReviewItemDTO,
    RuleConflictDTO,
    RuleDTO,
    RuleParseRunDTO,
    RuleSetDTO,
)
from financial_variable_curation.database.types import utcnow
from financial_variable_curation.rule_workflow.artifact_writer import RuleArtifactWriter
from financial_variable_curation.rule_workflow.cache import RuleParseCacheService
from financial_variable_curation.rule_workflow.compiler import RuleCompilationError, RuleCompiler
from financial_variable_curation.rule_workflow.conflicts import RuleConflictDetector
from financial_variable_curation.rule_workflow.exceptions import (
    RuleSourceError,
    RuleWorkflowError,
)
from financial_variable_curation.rule_workflow.mock_parser import MockRuleParser
from financial_variable_curation.rule_workflow.models import (
    CompiledRuleSetOutput,
    RuleParseResult,
    RuleParserProviderResult,
    RuleSetDocument,
    RuleSourceMetadata,
    RuleSummary,
    RuleWorkflowResult,
    rule_source_hash,
)
from financial_variable_curation.rule_workflow.normalizer import RuleNormalizer
from financial_variable_curation.rule_workflow.openai_parser import OpenAIRuleParser
from financial_variable_curation.rule_workflow.deepseek_parser import DeepSeekRuleParser
from financial_variable_curation.rule_workflow.validator import RuleSchemaValidator
from financial_variable_curation.rule_workflow.source_loader import load_rule_source


class RuleParserService:
    def __init__(
        self,
        manager: DatabaseManager | None = None,
        *,
        settings: LLMSettings | None = None,
        cache_service: RuleParseCacheService | None = None,
    ) -> None:
        self.manager = manager or DatabaseManager()
        self.settings = settings or LLMSettings.from_env()
        self.cache_service = cache_service or RuleParseCacheService(self.manager)
        self.normalizer = RuleNormalizer()
        self.validator = RuleSchemaValidator()
        self.conflict_detector = RuleConflictDetector()
        self.compiler = RuleCompiler()

    def validate_rules(
        self,
        rules_path: str | Path,
        *,
        provider: str | None = None,
        model: str | None = None,
        force_refresh: bool = False,
        dry_run: bool = False,
        rule_set_name: str | None = None,
        version: str = "1",
        artifacts_dir: str | Path = "artifacts",
        pipeline_run_id: str | None = None,
    ) -> RuleWorkflowResult:
        text, metadata = self._read_source(rules_path)
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
        metadata = RuleSourceMetadata(
            source_file_name=metadata["source_file_name"],
            original_path=metadata["original_path"],
            source_hash=metadata["source_hash"],
            text_length=metadata["text_length"],
            extension=metadata["extension"],
            provider=selected_provider,
            model=effective_model,
        )
        parse_run_id = f"ruleparse_{uuid4().hex[:12]}"
        document, cache_hit = self._get_document(
            text=text,
            metadata=metadata,
            provider=selected_provider,
            model=effective_model,
            parse_run_id=parse_run_id,
            force_refresh=force_refresh,
            rule_set_name=rule_set_name,
        )
        normalized = self.normalizer.normalize(document)
        validation = self.validator.validate(normalized)
        conflicts = self.conflict_detector.detect(normalized)
        compiled = None
        if validation.valid and not any(
            conflict.severity == "FATAL" for conflict in conflicts.conflicts
        ):
            compiled = self.compiler.compile(
                normalized,
                source_hash=metadata.source_hash,
                rule_set_name=rule_set_name or normalized.rule_set_name,
                version=version,
                conflicts=conflicts,
            )
        summary = self._build_summary(metadata, normalized, validation, conflicts, compiled)
        writer = RuleArtifactWriter(artifacts_dir, parse_run_id)
        writer.write_source_metadata(metadata)
        writer.write_parser_request(
            {
                "source_hash": metadata.source_hash,
                "provider": selected_provider,
                "model": effective_model,
                "rule_text": text,
            }
        )
        writer.write_parser_response(
            RuleParseResult(
                parse_run_id=parse_run_id,
                source_metadata=metadata,
                document=document,
                cache_hit=cache_hit,
            )
        )
        writer.write_document("parsed_rules.json", document)
        writer.write_document("normalized_rules.json", normalized)
        writer.write_validation(validation)
        writer.write_conflicts(conflicts)
        if compiled is not None:
            writer.write_compiled(compiled)
        writer.write_summary(summary)
        self._save_parse_run(
            parse_run_id=parse_run_id,
            pipeline_run_id=pipeline_run_id,
            metadata=metadata,
            status="COMPLETED",
        )
        self.cache_service.set(
            source_hash=metadata.source_hash,
            provider=selected_provider,
            model=effective_model,
            prompt_version=self.settings.llm_prompt_version,
            taxonomy_version=self.settings.llm_taxonomy_version,
            schema_version=self.settings.rule_schema_version,
            base_url=self.settings.deepseek_base_url if selected_provider == "deepseek" else None,
            document=document,
        )
        self._save_review_items(
            run_id=pipeline_run_id or parse_run_id,
            document=normalized,
            validation=validation,
            conflicts=conflicts,
        )
        return RuleWorkflowResult(
            parse_run_id=parse_run_id,
            source_metadata=metadata,
            document=document,
            normalized_document=normalized,
            validation=validation,
            conflicts=conflicts,
            compiled=compiled,
            summary=summary,
            artifacts_path=str(Path(artifacts_dir) / parse_run_id / "rules"),
            dry_run=dry_run,
            cache_hit=cache_hit,
        )

    def compile_rules(
        self,
        rules_path: str | Path,
        *,
        provider: str | None = None,
        model: str | None = None,
        name: str,
        version: str,
        force_refresh: bool = False,
        dry_run: bool = False,
        activate: bool = False,
        artifacts_dir: str | Path = "artifacts",
    ) -> RuleWorkflowResult:
        result = self.validate_rules(
            rules_path,
            provider=provider,
            model=model,
            force_refresh=force_refresh,
            dry_run=dry_run,
            rule_set_name=name,
            version=version,
            artifacts_dir=artifacts_dir,
            pipeline_run_id=None,
        )
        if not result.validation.valid:
            raise RuleWorkflowError("Rule validation failed; cannot compile.")
        if result.compiled is None:
            raise RuleWorkflowError("Rule compilation failed; fatal conflicts were detected.")
        if activate and any(
            conflict.severity in {"ERROR", "FATAL"} for conflict in result.conflicts.conflicts
        ):
            raise RuleWorkflowError("Activation blocked by ERROR or FATAL rule conflicts.")
        if not dry_run:
            self._persist_rule_set(result, activate=activate)
        return result

    def _get_document(
        self,
        *,
        text: str,
        metadata: RuleSourceMetadata,
        provider: str,
        model: str,
        parse_run_id: str,
        force_refresh: bool,
        rule_set_name: str | None,
    ) -> tuple[RuleSetDocument, bool]:
        if not force_refresh:
            cached = self.cache_service.get(
                source_hash=metadata.source_hash,
                provider=provider,
                model=model,
                prompt_version=self.settings.llm_prompt_version,
                taxonomy_version=self.settings.llm_taxonomy_version,
                schema_version=self.settings.rule_schema_version,
                base_url=self.settings.deepseek_base_url if provider == "deepseek" else None,
            )
            if cached is not None:
                return cached, True
        context = {
            "parse_run_id": parse_run_id,
            "rule_set_name": rule_set_name or "user_rules",
            "provider": provider,
            "model": model,
            "prompt_version": self.settings.llm_prompt_version,
            "taxonomy_version": self.settings.llm_taxonomy_version,
            "schema_version": self.settings.rule_schema_version,
        }
        if provider == "mock":
            return MockRuleParser().parse(text, context), False
        if provider == "openai":
            provider_result = OpenAIRuleParser(settings=self.settings).parse(text, context)
            self._save_llm_calls(parse_run_id, metadata, provider_result)
            return provider_result.document, False
        if provider == "deepseek":
            provider_result = DeepSeekRuleParser(settings=self.settings).parse(text, context)
            self._save_llm_calls(parse_run_id, metadata, provider_result)
            return provider_result.document, False
        raise RuleWorkflowError(f"Unsupported rule parser provider: {provider}")

    @staticmethod
    def _read_source(path: str | Path) -> tuple[str, dict[str, object]]:
        source_path = Path(path)
        if not source_path.exists():
            raise RuleSourceError(f"Rule file does not exist: {source_path}")
        if not source_path.is_file():
            raise RuleSourceError(f"Rule path is not a file: {source_path}")
        if source_path.suffix.lower() not in {".txt", ".md", ".docx"}:
            raise RuleSourceError("Rule input must be a .txt, .md, or .docx file.")
        if source_path.suffix.lower() == ".docx":
            loaded = load_rule_source(source_path)
            if not loaded.text.strip():
                raise RuleSourceError("Rule file is empty.")
            return loaded.text, {
                "source_file_name": source_path.name,
                "original_path": str(source_path.resolve()),
                "source_hash": loaded.metadata["source_file_hash"],
                "text_length": len(loaded.text),
                "extension": source_path.suffix.lower(),
                "docx_paragraph_count": loaded.metadata["paragraph_count"],
                "docx_table_count": loaded.metadata["table_count"],
                "docx_unsupported_content": loaded.metadata["unsupported_content"],
            }
        try:
            text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RuleSourceError("Rule file is not valid UTF-8.") from exc
        if not text.strip():
            raise RuleSourceError("Rule file is empty.")
        if len(text) > 200_000:
            raise RuleSourceError("Rule file exceeds the 200,000 character limit.")
        return text, {
            "source_file_name": source_path.name,
            "original_path": str(source_path.resolve()),
            "source_hash": rule_source_hash(text),
            "text_length": len(text),
            "extension": source_path.suffix.lower(),
        }

    @staticmethod
    def _build_summary(
        metadata: RuleSourceMetadata,
        document: RuleSetDocument,
        validation,
        conflicts,
        compiled: CompiledRuleSetOutput | None,
    ) -> RuleSummary:
        return RuleSummary(
            source_hash=metadata.source_hash,
            rule_count=len(document.rules),
            rule_type_counts=dict(Counter(rule.rule_type for rule in document.rules)),
            unresolved_count=len(document.unresolved_items),
            warning_count=(
                len(validation.warnings)
                + len(document.warnings)
                + sum(1 for conflict in conflicts.conflicts if conflict.severity == "WARNING")
            ),
            error_count=len(validation.errors),
            conflict_count=len(conflicts.conflicts),
            blocking_conflict_count=sum(
                1 for conflict in conflicts.conflicts if conflict.blocks_compilation
            ),
            validation_valid=validation.valid,
            compile_successful=compiled is not None,
            production_ready=False,
            provider=metadata.provider,
            model=metadata.model,
            prompt_version=document.prompt_version,
            taxonomy_version=document.taxonomy_version,
            schema_version=document.schema_version,
        )

    def _save_llm_calls(
        self,
        parse_run_id: str,
        metadata: RuleSourceMetadata,
        provider_result: RuleParserProviderResult,
    ) -> None:
        llm_result = provider_result.llm_call_result
        if llm_result is None:
            return
        with self.manager.unit_of_work() as uow:
            repository = LlmCallRepository(uow.session)
            for attempt in llm_result.attempts:
                repository.add(
                    LlmCallDTO(
                        llm_call_id=f"rulellm_{metadata.source_hash[:16]}_a{attempt.attempt_number}",
                        run_id=None,
                        batch_id=parse_run_id,
                        task_type="rule_parsing",
                        provider=metadata.provider,
                        model=metadata.model,
                        prompt_version=self.settings.llm_prompt_version,
                        taxonomy_version=self.settings.llm_taxonomy_version,
                        request_hash=metadata.source_hash,
                        response_status=attempt.status,
                        response_id=attempt.response_id,
                        input_tokens=attempt.input_tokens,
                        output_tokens=attempt.output_tokens,
                        total_tokens=attempt.total_tokens,
                        latency_ms=attempt.latency_ms,
                        attempt_count=attempt.attempt_number,
                        error_type=attempt.error_type,
                        error_message=attempt.error_message,
                        created_at=attempt.started_at,
                        completed_at=attempt.completed_at,
                    )
                )

    def _save_parse_run(
        self,
        *,
        parse_run_id: str,
        pipeline_run_id: str | None,
        metadata: RuleSourceMetadata,
        status: str,
    ) -> None:
        with self.manager.unit_of_work() as uow:
            RuleParseRunRepository(uow.session).add(
                RuleParseRunDTO(
                    parse_run_id=parse_run_id,
                    pipeline_run_id=pipeline_run_id,
                    source_hash=metadata.source_hash,
                    provider=metadata.provider,
                    model=metadata.model,
                    prompt_version=self.settings.llm_prompt_version,
                    status=status,
                    started_at=utcnow(),
                    completed_at=utcnow(),
                )
            )

    def _persist_rule_set(self, result: RuleWorkflowResult, *, activate: bool) -> None:
        compiled = result.compiled
        if compiled is None:
            raise RuleWorkflowError("Cannot persist a rule set without a compiled output.")
        with self.manager.unit_of_work() as uow:
            rule_set_repo = RuleSetRepository(uow.session)
            existing = rule_set_repo.get_by_name_version(compiled.rule_set_name, compiled.version)
            if existing is not None:
                raise RuleWorkflowError(
                    f"Rule set {compiled.rule_set_name} version {compiled.version} already exists."
                )
            status = "ACTIVE" if activate else "VALIDATED"
            rule_set_repo.save(
                RuleSetDTO(
                    rule_set_id=compiled.compiled_rule_set_id,
                    rule_set_name=compiled.rule_set_name,
                    version=compiled.version,
                    status=status,
                    source_type="USER_RULES",
                    source_file_name=result.source_metadata.source_file_name,
                    source_hash=result.source_metadata.source_hash,
                    source_language=result.document.source_language,
                    provider=result.source_metadata.provider,
                    model=result.source_metadata.model,
                    prompt_version=result.document.prompt_version,
                    taxonomy_version=result.document.taxonomy_version,
                    schema_version=result.document.schema_version,
                    production_ready=False,
                    parsed_rules_path=str(
                        Path(result.artifacts_path or "") / "normalized_rules.json"
                    ),
                    compiled_rules_path=str(
                        Path(result.artifacts_path or "") / "compiled_rules.json"
                    ),
                    compiled_hash=compiled.compiled_hash,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                    activated_at=utcnow() if status == "ACTIVE" else None,
                )
            )
            rules = [
                RuleDTO(
                    rule_id=rule.rule_id,
                    rule_set_id=compiled.compiled_rule_set_id,
                    rule_type=rule.rule_type,
                    rule_name=rule.rule_name,
                    priority=rule.priority,
                    scope_json=rule.scope.model_dump(mode="json"),
                    conditions_json=[item.model_dump(mode="json") for item in rule.conditions],
                    action_json=rule.action.model_dump(mode="json") if rule.action else None,
                    exceptions_json=rule.exceptions,
                    confidence=rule.confidence,
                    requires_review=rule.requires_review,
                    source_text_excerpt=rule.source_text_excerpt,
                    created_at=utcnow(),
                )
                for rule in result.normalized_document.rules
            ]
            RuleRepository(uow.session).bulk_save(compiled.compiled_rule_set_id, rules)
            RuleConflictRepository(uow.session).bulk_save(
                compiled.compiled_rule_set_id,
                [
                    RuleConflictDTO(
                        conflict_id=conflict.conflict_id,
                        rule_set_id=compiled.compiled_rule_set_id,
                        conflict_type=conflict.conflict_type,
                        severity=conflict.severity,
                        involved_rule_ids_json=conflict.involved_rule_ids,
                        description=conflict.description,
                        suggested_resolution=conflict.suggested_resolution,
                        blocks_compilation=conflict.blocks_compilation,
                        created_at=utcnow(),
                    )
                    for conflict in result.conflicts.conflicts
                ],
            )

    def _save_review_items(
        self,
        *,
        run_id: str,
        document: RuleSetDocument,
        validation,
        conflicts,
    ) -> None:
        if not (document.unresolved_items or any(rule.requires_review for rule in document.rules) or conflicts.conflicts):
            return
        with self.manager.unit_of_work() as uow:
            pipeline_repo = PipelineRunRepository(uow.session)
            if pipeline_repo.get(run_id) is None:
                pipeline_repo.create(
                    PipelineRunDTO(
                        run_id=run_id,
                        run_type="RULE_VALIDATION",
                        status="REVIEW_REQUIRED",
                        started_at=utcnow(),
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
            review_repo = ReviewItemRepository(uow.session)
            for index, unresolved in enumerate(document.unresolved_items):
                review_repo.upsert(
                    ReviewItemDTO(
                        review_item_id=f"review_rule_{run_id}_{index}",
                        run_id=run_id,
                        entity_type="rule_parse_run",
                        entity_id=run_id,
                        review_type="RULE_SEMANTICS_REVIEW",
                        status="NEEDS_REVIEW",
                        reason_code="UNRESOLVED_RULE",
                        reason_text=unresolved[:1000],
                        resolution_json={"source_hash": document.metadata.get("source_hash")},
                        created_at=utcnow(),
                    )
                )
            for index, conflict in enumerate(conflicts.conflicts):
                review_repo.upsert(
                    ReviewItemDTO(
                        review_item_id=f"review_conflict_{run_id}_{index}",
                        run_id=run_id,
                        entity_type="rule_conflict",
                        entity_id=conflict.conflict_id,
                        review_type="RULE_CONFLICT_REVIEW",
                        status="NEEDS_REVIEW",
                        reason_code=conflict.conflict_type,
                        reason_text=conflict.description[:1000],
                        resolution_json={"involved_rule_ids": conflict.involved_rule_ids},
                        created_at=utcnow(),
                    )
                )
