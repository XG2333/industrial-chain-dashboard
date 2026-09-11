from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from financial_variable_curation.classification.service import BatchClassificationService
from financial_variable_curation.classification.settings import LLMSettings
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import (
    PipelineRunRepository,
    PipelineStepRepository,
    RuleSetRepository,
)
from financial_variable_curation.database.schemas import (
    PipelineRunDTO,
    PipelineStepDTO,
)
from financial_variable_curation.database.services import InspectionPersistenceService
from financial_variable_curation.database.types import utcnow
from financial_variable_curation.export.models import PipelineSummary
from financial_variable_curation.export.service import SelectionExportService
from financial_variable_curation.pipeline.inspect import run_inspection
from financial_variable_curation.rule_workflow.service import RuleParserService
from financial_variable_curation.selection.service import VariableSelectionService


class PipelineWorkflowError(Exception):
    pass


class FullPipelineOrchestrator:
    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.manager = manager or DatabaseManager()

    def run(
        self,
        input_path: str | Path,
        *,
        rules_path: str | Path | None = None,
        rule_set_id: str | None = None,
        use_default_rules: bool = False,
        provider: str = "mock",
        model: str | None = None,
        output_path: str | Path,
        batch_size: int | None = None,
        limit: int | None = None,
        dry_run: bool = False,
        force_refresh: bool = False,
        overwrite: bool = False,
        artifacts_dir: str | Path = "artifacts",
    ) -> PipelineSummary:
        input_path = Path(input_path)
        output_path = Path(output_path)
        if not input_path.exists():
            raise PipelineWorkflowError(f"Input file does not exist: {input_path}")
        if output_path.resolve() == input_path.resolve():
            raise PipelineWorkflowError("Output path must not equal the input path.")
        if rules_path and rule_set_id:
            raise PipelineWorkflowError("--rules and --rule-set-id cannot be used together.")
        if use_default_rules and (rules_path or rule_set_id):
            raise PipelineWorkflowError("--use-default-rules cannot be combined with formal rules.")
        settings = LLMSettings.from_env(provider=provider, model=model, batch_size=batch_size)
        if provider in {"openai", "deepseek"} and not settings.real_llm_enabled:
            raise PipelineWorkflowError(
                "Real LLM calls are disabled. Set REAL_LLM_ENABLED=true explicitly."
            )

        pipeline_run_id = f"pipe_{uuid4().hex[:12]}"
        if dry_run:
            inspection = run_inspection(input_path, run_id=pipeline_run_id)
            return PipelineSummary(
                pipeline_run_id=pipeline_run_id,
                status="DRY_RUN",
                stages={
                    "CREATE_RUN": "COMPLETED",
                    "INSPECT_EXCEL": "COMPLETED",
                    "DRY_RUN": "COMPLETED",
                },
                dry_run=True,
                warnings=[
                    "Dry run completed without persisting inspection, classification, selection, or output."
                ],
            )

        self._save_pipeline_run(pipeline_run_id, status="CREATED")
        self._save_step(pipeline_run_id, "CREATE_RUN", "COMPLETED")
        try:
            self._save_step(pipeline_run_id, "INSPECT_EXCEL", "RUNNING")
            inspection = run_inspection(input_path, run_id=pipeline_run_id)
            self._save_step(pipeline_run_id, "INSPECT_EXCEL", "COMPLETED")

            self._save_step(pipeline_run_id, "PERSIST_INSPECTION", "RUNNING")
            InspectionPersistenceService(self.manager).persist(
                inspection,
                artifacts_dir=Path(artifacts_dir),
                run_id=pipeline_run_id,
            )
            self._save_step(pipeline_run_id, "PERSIST_INSPECTION", "COMPLETED")

            self._save_step(pipeline_run_id, "CLASSIFY_VARIABLES", "RUNNING")
            classification = BatchClassificationService(self.manager, settings=settings).classify_run(
                pipeline_run_id,
                provider=provider,
                model=model,
                limit=limit,
                batch_size=batch_size,
                force_refresh=force_refresh,
                artifacts_dir=artifacts_dir,
            )
            self._save_step(pipeline_run_id, "CLASSIFY_VARIABLES", "COMPLETED")

            if rules_path:
                self._save_step(pipeline_run_id, "PARSE_RULES", "RUNNING")
                name = f"{Path(rules_path).stem}_{pipeline_run_id[:8]}"
                rule_result = RuleParserService(self.manager, settings=settings).compile_rules(
                    rules_path,
                    provider=provider,
                    model=model,
                    name=name,
                    version="1",
                    force_refresh=force_refresh,
                    artifacts_dir=artifacts_dir,
                )
                self._save_step(pipeline_run_id, "PARSE_RULES", "COMPLETED")
                resolved_rule_set_id = (
                    rule_result.compiled.compiled_rule_set_id if rule_result.compiled else None
                )
                if not resolved_rule_set_id:
                    raise PipelineWorkflowError("Rule compilation did not produce a rule set id.")
            elif rule_set_id:
                with self.manager.session_scope() as session:
                    rule_set = RuleSetRepository(session).get(rule_set_id)
                if rule_set is None:
                    raise PipelineWorkflowError(f"Rule set not found: {rule_set_id}")
                resolved_rule_set_id = rule_set_id
            elif use_default_rules:
                raise PipelineWorkflowError(
                    "Default placeholder rules are not yet supported by the new pipeline orchestrator."
                )
            else:
                raise PipelineWorkflowError("One of --rules, --rule-set-id, or --use-default-rules is required.")
            self._save_step(pipeline_run_id, "SELECT_VARIABLES", "RUNNING")
            selection = VariableSelectionService(self.manager).select(
                pipeline_run_id,
                rule_set_id=resolved_rule_set_id,
                allow_validated_rules=True,
                include_review_candidates=True,
                artifacts_dir=artifacts_dir,
            )
            self._save_step(pipeline_run_id, "SELECT_VARIABLES", "COMPLETED")

            self._save_step(pipeline_run_id, "EXPORT_RESULTS", "RUNNING")
            export = SelectionExportService(self.manager).export(
                selection.selection_run_id,
                output_path=output_path,
                overwrite=overwrite,
                artifacts_dir=artifacts_dir,
            )
            self._save_step(pipeline_run_id, "EXPORT_RESULTS", "COMPLETED")

            status = (
                "REVIEW_REQUIRED"
                if selection.needs_review_count > 0 or selection.failed_count > 0
                else "COMPLETED"
            )
            self._save_pipeline_run(
                pipeline_run_id,
                status=status,
                completed=True,
            )
            summary = PipelineSummary(
                pipeline_run_id=pipeline_run_id,
                status=status,
                stages={
                    "CREATE_RUN": "COMPLETED",
                    "INSPECT_EXCEL": "COMPLETED",
                    "PERSIST_INSPECTION": "COMPLETED",
                    "CLASSIFY_VARIABLES": "COMPLETED",
                    "PARSE_RULES": "COMPLETED" if rules_path else "SKIPPED",
                    "SELECT_VARIABLES": "COMPLETED",
                    "EXPORT_RESULTS": "COMPLETED",
                    "FINALIZE_RUN": "COMPLETED",
                },
                selection_run_id=selection.selection_run_id,
                export_run_id=export.export_run_id,
                output_path=str(export.output_path),
                output_file_hash=export.output_file_hash,
            )
        except Exception as exc:
            self._save_pipeline_run(pipeline_run_id, status="FAILED", failed=True)
            raise PipelineWorkflowError(f"Pipeline failed: {exc}") from exc

        pipeline_dir = Path(artifacts_dir) / pipeline_run_id
        pipeline_dir.mkdir(parents=True, exist_ok=True)
        (pipeline_dir / "pipeline_summary.json").write_text(
            json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    def _save_pipeline_run(
        self,
        run_id: str,
        *,
        status: str,
        completed: bool = False,
        failed: bool = False,
    ) -> None:
        with self.manager.unit_of_work() as uow:
            repo = PipelineRunRepository(uow.session)
            existing = repo.get(run_id)
            if existing is None:
                repo.create(
                    PipelineRunDTO(
                        run_id=run_id,
                        run_type="FULL_PIPELINE",
                        status=status,
                        started_at=utcnow(),
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
            else:
                repo.update(
                    run_id,
                    status=status,
                    completed_at=utcnow() if completed else None,
                    failed_at=utcnow() if failed else None,
                )

    def _save_step(self, run_id: str, step_name: str, status: str) -> None:
        with self.manager.unit_of_work() as uow:
            PipelineStepRepository(uow.session).upsert(
                PipelineStepDTO(
                    step_id=f"step_{run_id[:8]}_{step_name}",
                    run_id=run_id,
                    step_name=step_name,
                    step_order=0,
                    status=status,
                    started_at=utcnow(),
                    completed_at=utcnow() if status == "COMPLETED" else None,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
