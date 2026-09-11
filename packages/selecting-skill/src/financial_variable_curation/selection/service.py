from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import (
    AuditEventRepository,
    PipelineRunRepository,
    ReviewItemRepository,
    RuleConflictRepository,
    RuleSetRepository,
    SelectionResultRepository,
    SelectionRunRepository,
    VariableClassificationRepository,
    VariableRepository,
)
from financial_variable_curation.database.schemas import (
    AuditEventDTO,
    PipelineRunDTO,
    SelectionRunDTO,
    VariableSelectionResultDTO,
)
from financial_variable_curation.database.types import utcnow
from financial_variable_curation.rule_workflow.models import CompiledRuleSetOutput
from financial_variable_curation.selection.artifact_writer import SelectionArtifactWriter
from financial_variable_curation.selection.engine import RuleExecutionEngine
from financial_variable_curation.selection.models import (
    CandidateVariable,
    SelectionDecision,
    SelectionSummary,
)


class SelectionWorkflowError(Exception):
    pass


class VariableSelectionService:
    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.manager = manager or DatabaseManager()
        self.engine = RuleExecutionEngine()

    def select(
        self,
        run_id: str,
        *,
        rule_set_id: str | None = None,
        rule_set_name: str | None = None,
        rule_version: str | None = None,
        dry_run: bool = False,
        resume: bool = False,
        allow_validated_rules: bool = False,
        include_review_candidates: bool = False,
        artifacts_dir: str | Path = "artifacts",
    ) -> SelectionSummary:
        self._validate_inputs(run_id, rule_set_id, rule_set_name)
        rule_set, compiled = self._load_rule_set(
            rule_set_id=rule_set_id,
            rule_set_name=rule_set_name,
            rule_version=rule_version,
            allow_validated_rules=allow_validated_rules,
        )
        candidates = self._load_candidates(run_id)
        warnings = [
            "Classification is partial: variables without a classification result are marked FAILED/UNCLASSIFIED and must be reviewed."
        ] if any(candidate.classification_status == "FAILED" for candidate in candidates) else []
        if warnings and not include_review_candidates:
            warnings.append(
                "Use --include-review-candidates to explicitly acknowledge FAILED/UNCLASSIFIED variables in this selection."
            )
        self._check_taxonomy(run_id, rule_set.taxonomy_version)
        self._check_blocking_conflicts(rule_set.rule_set_id)
        result = self.engine.execute(candidates, compiled)
        selection_run_id = f"sel_{uuid4().hex[:12]}"
        summary = self._build_summary(
            selection_run_id=selection_run_id,
            source_run_id=run_id,
            rule_set=rule_set,
            compiled=compiled,
            result=result,
            dry_run=dry_run,
            warnings=warnings,
        )
        writer = SelectionArtifactWriter(artifacts_dir, selection_run_id)
        writer.write_request(
            {
                "source_run_id": run_id,
                "rule_set_id": rule_set.rule_set_id,
                "rule_set_name": rule_set.rule_set_name,
                "rule_set_version": rule_set.version,
                "compiled_hash": compiled.compiled_hash,
                "dry_run": dry_run,
            }
        )
        writer.write_candidates(candidates)
        writer.write_compiled_plan(compiled)
        writer.write_stage_summaries(result.stage_summaries)
        trace_path = writer.write_traces(result.decisions)
        writer.write_results(result.decisions)
        writer.write_summary(summary)
        writer.write_log(f"Selection run {selection_run_id} completed for source run {run_id}.")
        summary.artifacts_path = str(writer.selection_dir)
        if dry_run:
            summary.status = "DRY_RUN"
            return summary
        self._persist(
            selection_run_id=selection_run_id,
            source_run_id=run_id,
            rule_set=rule_set,
            compiled=compiled,
            result=result,
            summary=summary,
            artifacts_dir=writer.selection_dir,
            trace_path=trace_path,
        )
        return summary

    def show_selection(self, selection_run_id: str) -> SelectionSummary:
        with self.manager.session_scope() as session:
            run = SelectionRunRepository(session).get(selection_run_id)
            if run is None:
                raise SelectionWorkflowError(f"Selection run not found: {selection_run_id}")
            results = SelectionResultRepository(session).list_for_run(selection_run_id)
        counts = Counter(item.final_status for item in results)
        selected_by_category = Counter(
            result.category_level_1
            for result in self._load_candidates(run.classification_run_id or run.pipeline_run_id)
            if result.variable_id
            in {
                item.variable_id
                for item in results
                if item.final_status == "SELECTED"
            }
        )
        selected_by_frequency = Counter(
            result.detected_frequency
            for result in self._load_candidates(run.classification_run_id or run.pipeline_run_id)
            if result.variable_id
            in {
                item.variable_id
                for item in results
                if item.final_status == "SELECTED"
            }
        )
        return SelectionSummary(
            selection_run_id=run.selection_run_id,
            source_run_id=run.classification_run_id or run.pipeline_run_id,
            rule_set_id=run.rule_set_id or "",
            rule_set_name="",
            rule_set_version=run.rule_set_version or "",
            compiled_hash=run.compiled_hash or "",
            total_variables=run.total_variables,
            candidate_variables=run.candidate_variables,
            selected_count=counts.get("SELECTED", 0),
            rejected_count=counts.get("REJECTED", 0),
            duplicate_count=counts.get("DUPLICATE", 0),
            needs_review_count=counts.get("NEEDS_REVIEW", 0),
            not_selected_count=counts.get("NOT_SELECTED", 0),
            failed_count=counts.get("FAILED", 0),
            selected_by_category=dict(selected_by_category),
            selected_by_frequency=dict(selected_by_frequency),
            status=run.status,
            artifacts_path=run.artifacts_path,
        )

    def _validate_inputs(
        self,
        run_id: str,
        rule_set_id: str | None,
        rule_set_name: str | None,
    ) -> None:
        if not rule_set_id and not rule_set_name:
            raise SelectionWorkflowError("Either --rule-set-id or --rule-set is required.")
        with self.manager.session_scope() as session:
            run = PipelineRunRepository(session).get(run_id)
            if run is None:
                raise SelectionWorkflowError(f"Source run not found: {run_id}")
            variables = VariableRepository(session).list_classification_candidates(run_id)
            classifications = VariableClassificationRepository(session).list_for_run(run_id)
        if not variables:
            raise SelectionWorkflowError("Source run has no variables.")
        if not classifications:
            raise SelectionWorkflowError("Source run has no classification results.")

    def _load_rule_set(
        self,
        *,
        rule_set_id: str | None,
        rule_set_name: str | None,
        rule_version: str | None,
        allow_validated_rules: bool,
    ):
        with self.manager.session_scope() as session:
            repo = RuleSetRepository(session)
            if rule_set_id:
                rule_set = repo.get(rule_set_id)
            elif rule_set_name and rule_version:
                rule_set = repo.get_by_name_version(rule_set_name, rule_version)
            elif rule_set_name:
                rule_set = repo.get_active(rule_set_name)
            else:
                rule_set = None
            if rule_set is None:
                raise SelectionWorkflowError("Rule set was not found.")
            if rule_set.status not in {"VALIDATED", "ACTIVE"}:
                raise SelectionWorkflowError(
                    f"Rule set status {rule_set.status} is not VALIDATED or ACTIVE."
                )
            if rule_set.status == "VALIDATED" and not allow_validated_rules:
                raise SelectionWorkflowError(
                    "Rule set is VALIDATED; pass --allow-validated-rules to use it."
                )
            if not rule_set.compiled_rules_path:
                raise SelectionWorkflowError("Rule set has no compiled_rules_path.")
            path = Path(rule_set.compiled_rules_path)
            if not path.exists():
                raise SelectionWorkflowError(f"Compiled rules file missing: {path}")
            compiled = CompiledRuleSetOutput.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
            if compiled.compiled_hash != rule_set.compiled_hash:
                raise SelectionWorkflowError("compiled_hash does not match the stored rule set.")
            return rule_set, compiled

    def _load_candidates(self, run_id: str) -> list[CandidateVariable]:
        with self.manager.session_scope() as session:
            variable_candidates = VariableRepository(session).list_classification_candidates(run_id)
            classifications = {
                item.variable_id: item
                for item in VariableClassificationRepository(session).list_for_run(run_id)
            }
            review_ids = {
                item.entity_id
                for item in ReviewItemRepository(session).list_for_run(run_id)
                if item.status == "NEEDS_REVIEW"
            }
        candidates: list[CandidateVariable] = []
        for candidate in variable_candidates:
            variable = candidate.variable
            quality = candidate.quality
            classification = classifications.get(variable.variable_id)
            if classification is None:
                candidates.append(
                    self._unclassified_candidate(
                        run_id=run_id,
                        variable=variable,
                        quality=quality,
                        review_ids=review_ids,
                    )
                )
                continue
            candidates.append(
                CandidateVariable(
                    variable_id=variable.variable_id,
                    run_id=run_id,
                    original_name=variable.original_name,
                    standard_name=classification.standard_name or variable.original_name,
                    industry=classification.industry,
                    sector=classification.sector,
                    commodity=classification.commodity,
                    category_level_1=classification.category_level_1 or "UNKNOWN",
                    category_level_2=classification.category_level_2 or "UNCLASSIFIED",
                    metric_name=classification.metric_name or variable.normalized_name,
                    data_nature=classification.data_nature or "UNKNOWN",
                    market=classification.market,
                    region=classification.region,
                    country=classification.region,
                    unit_standard=classification.unit,
                    unit_dimension=classification.unit,
                    statistical_scope=classification.statistical_scope,
                    comparison_group_key=classification.comparison_group_key,
                    classification_confidence=classification.confidence,
                    classification_status=classification.classification_status,
                    detected_frequency=quality.detected_frequency if quality else "unknown",
                    missing_rate=quality.missing_rate if quality else 1.0,
                    non_null_count=quality.non_null_count if quality else 0,
                    unique_value_count=quality.unique_value_count if quality else 0,
                    coverage_days=quality.coverage_days,
                    latest_gap_days=quality.latest_gap_days,
                    quality_score=(
                        round(
                            (1.0 - quality.missing_rate) * 80.0
                            + min(quality.unique_value_count, 1000) / 1000.0 * 20.0,
                            2,
                        )
                        if quality
                        else 0.0
                    ),
                    is_constant=quality.is_constant if quality else False,
                    is_pseudo_high_frequency=quality.is_pseudo_high_frequency if quality else False,
                    has_unresolved_review=variable.variable_id in review_ids,
                    review_reasons=classification.review_reasons_json,
                )
            )
        return candidates

    @staticmethod
    def _unclassified_candidate(
        *,
        run_id: str,
        variable,
        quality,
        review_ids: set[str],
    ) -> CandidateVariable:
        return CandidateVariable(
            variable_id=variable.variable_id,
            run_id=run_id,
            original_name=variable.original_name,
            standard_name=variable.original_name,
            metric_name=variable.normalized_name,
            classification_confidence=0.0,
            classification_status="FAILED",
            detected_frequency=quality.detected_frequency if quality else "unknown",
            missing_rate=quality.missing_rate if quality else 1.0,
            non_null_count=quality.non_null_count if quality else 0,
            unique_value_count=quality.unique_value_count if quality else 0,
            coverage_days=quality.coverage_days if quality else None,
            latest_gap_days=quality.latest_gap_days if quality else None,
            quality_score=(
                round(
                    (1.0 - quality.missing_rate) * 80.0
                    + min(quality.unique_value_count, 1000) / 1000.0 * 20.0,
                    2,
                )
                if quality
                else 0.0
            ),
            is_constant=quality.is_constant if quality else False,
            is_pseudo_high_frequency=quality.is_pseudo_high_frequency if quality else False,
            has_unresolved_review=variable.variable_id in review_ids,
            review_reasons=["UNCLASSIFIED"],
        )

    def _check_taxonomy(self, run_id: str, rule_taxonomy: str | None) -> None:
        if not rule_taxonomy:
            return
        with self.manager.session_scope() as session:
            classifications = VariableClassificationRepository(session).list_for_run(run_id)
        mismatched = {
            item.taxonomy_version for item in classifications if item.taxonomy_version != rule_taxonomy
        }
        if mismatched:
            raise SelectionWorkflowError(
                f"Classification taxonomy {mismatched} is incompatible with rule taxonomy {rule_taxonomy}."
            )

    def _check_blocking_conflicts(self, rule_set_id: str) -> None:
        with self.manager.session_scope() as session:
            conflicts = RuleConflictRepository(session).list_for_set(rule_set_id)
        if any(conflict.blocks_compilation for conflict in conflicts):
            raise SelectionWorkflowError("Rule set contains blocking conflicts.")

    def _build_summary(
        self,
        *,
        selection_run_id: str,
        source_run_id: str,
        rule_set,
        compiled: CompiledRuleSetOutput,
        result,
        dry_run: bool,
        warnings: list[str],
    ) -> SelectionSummary:
        status_counts = Counter(decision.status for decision in result.decisions)
        selected = [
            decision
            for decision in result.decisions
            if decision.status == "SELECTED"
        ]
        return SelectionSummary(
            selection_run_id=selection_run_id,
            source_run_id=source_run_id,
            rule_set_id=rule_set.rule_set_id,
            rule_set_name=rule_set.rule_set_name,
            rule_set_version=rule_set.version,
            compiled_hash=compiled.compiled_hash,
            total_variables=len(result.decisions),
            candidate_variables=len(result.decisions),
            selected_count=status_counts.get("SELECTED", 0),
            rejected_count=status_counts.get("REJECTED", 0),
            duplicate_count=status_counts.get("DUPLICATE", 0),
            needs_review_count=status_counts.get("NEEDS_REVIEW", 0),
            not_selected_count=status_counts.get("NOT_SELECTED", 0),
            failed_count=status_counts.get("FAILED", 0),
            selected_by_category=dict(
                Counter(decision.candidate.category_level_1 for decision in selected)
            ),
            selected_by_frequency=dict(
                Counter(decision.candidate.detected_frequency for decision in selected)
            ),
            stage_summaries=result.stage_summaries,
            status="DRY_RUN" if dry_run else (
                "REVIEW_REQUIRED"
                if status_counts.get("NEEDS_REVIEW", 0) or status_counts.get("FAILED", 0)
                else "COMPLETED"
            ),
            dry_run=dry_run,
            warnings=[*result.warnings, *warnings],
        )

    def _persist(
        self,
        *,
        selection_run_id: str,
        source_run_id: str,
        rule_set,
        compiled: CompiledRuleSetOutput,
        result,
        summary: SelectionSummary,
        artifacts_dir: Path,
        trace_path: Path,
    ) -> None:
        try:
            with self.manager.unit_of_work() as uow:
                run_repo = SelectionRunRepository(uow.session)
                run_repo.save(
                    SelectionRunDTO(
                        selection_run_id=selection_run_id,
                        pipeline_run_id=source_run_id,
                        classification_run_id=source_run_id,
                        rule_set_id=rule_set.rule_set_id,
                        rule_set_version=rule_set.version,
                        compiled_hash=compiled.compiled_hash,
                        status=summary.status,
                        started_at=utcnow(),
                        total_variables=summary.total_variables,
                        candidate_variables=summary.candidate_variables,
                        selected_count=summary.selected_count,
                        rejected_count=summary.rejected_count,
                        duplicate_count=summary.duplicate_count,
                        needs_review_count=summary.needs_review_count,
                        not_selected_count=summary.not_selected_count,
                        artifacts_path=str(artifacts_dir),
                        created_at=utcnow(),
                        completed_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
                result_repo = SelectionResultRepository(uow.session)
                result_repo.bulk_upsert(
                    selection_run_id,
                    [
                        self._decision_dto(selection_run_id, decision, trace_path)
                        for decision in result.decisions
                    ],
                )
                AuditEventRepository(uow.session).add(
                    AuditEventDTO(
                        event_id=str(uuid4()),
                        run_id=source_run_id,
                        event_type="SELECTION_COMPLETED",
                        entity_type="selection_run",
                        entity_id=selection_run_id,
                        event_payload_json={"status": summary.status},
                        created_at=utcnow(),
                    )
                )
        except Exception as exc:
            self._mark_failed(selection_run_id, source_run_id, rule_set, compiled, exc)
            raise

    def _mark_failed(
        self,
        selection_run_id: str,
        source_run_id: str,
        rule_set,
        compiled: CompiledRuleSetOutput,
        error: Exception,
    ) -> None:
        try:
            with self.manager.unit_of_work() as uow:
                SelectionRunRepository(uow.session).save(
                    SelectionRunDTO(
                        selection_run_id=selection_run_id,
                        pipeline_run_id=source_run_id,
                        classification_run_id=source_run_id,
                        rule_set_id=rule_set.rule_set_id,
                        rule_set_version=rule_set.version,
                        compiled_hash=compiled.compiled_hash,
                        status="FAILED",
                        started_at=utcnow(),
                        failed_at=utcnow(),
                        error_type=type(error).__name__,
                        error_message=str(error),
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
        except Exception as recovery_error:
            raise SelectionWorkflowError(
                f"Selection failed and failure recovery also failed: {recovery_error}"
            ) from recovery_error

    @staticmethod
    def _decision_dto(
        selection_run_id: str,
        decision: SelectionDecision,
        trace_path: Path,
    ) -> VariableSelectionResultDTO:
        scores = decision.scores
        return VariableSelectionResultDTO(
            selection_result_id=f"selres_{selection_run_id[:8]}_{decision.variable_id[:12]}",
            selection_run_id=selection_run_id,
            variable_id=decision.variable_id,
            selection_status=decision.status,
            final_status=decision.status,
            total_score=decision.total_score,
            category_rank=decision.category_rank,
            subcategory_rank=decision.subcategory_rank,
            frequency_rank=decision.frequency_rank,
            source_rank=decision.source_rank,
            quality_rank=decision.quality_rank,
            category_score=scores.category_score,
            frequency_score=scores.frequency_score,
            quality_score=scores.quality_score,
            source_score=scores.source_score,
            recency_score=scores.recency_score,
            coverage_score=scores.coverage_score,
            user_preference_score=scores.user_preference_score,
            redundancy_penalty=scores.redundancy_penalty,
            rank=decision.overall_rank,
            overall_rank=decision.overall_rank,
            comparison_group_key=decision.comparison_group_key,
            group_rank=decision.group_rank,
            reason_code=decision.primary_reason_code,
            reason_text=decision.primary_reason_text,
            primary_reason_code=decision.primary_reason_code,
            primary_reason_text=decision.primary_reason_text,
            matched_rule_ids_json=decision.matched_rule_ids,
            replacement_variable_id=decision.replacement_variable_id,
            execution_trace_path=str(trace_path),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
