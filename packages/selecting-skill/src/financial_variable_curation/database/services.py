from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from financial_variable_curation.database.exceptions import EntityNotFoundError, PersistenceError
from financial_variable_curation.database.manager import DatabaseManager
from financial_variable_curation.database.repositories import (
    AuditEventRepository,
    PipelineRunRepository,
    PipelineStepRepository,
    SourceFileRepository,
    SourceSheetRepository,
    VariableQualityRepository,
    VariableRepository,
)
from financial_variable_curation.database.schemas import (
    AuditEventDTO,
    PersistenceSummaryDTO,
    PipelineRunDTO,
    PipelineStepDTO,
    RunSummaryDTO,
    RunVariableDTO,
    SourceFileDTO,
    SourceSheetDTO,
    VariableDTO,
    VariableQualityDTO,
)
from financial_variable_curation.database.types import utcnow
from financial_variable_curation.models.artifacts import RequestRecord
from financial_variable_curation.models.inspection import InspectionResult


SENSITIVE_KEY_TOKENS = ("api_key", "apikey", "token", "secret", "password", "authorization")


def redact_sensitive_values(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: ("***" if any(token in key.lower() for token in SENSITIVE_KEY_TOKENS) else redact_sensitive_values(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_sensitive_values(item) for item in payload]
    return payload


def _stable_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class InspectionPersistenceService:
    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.manager = manager or DatabaseManager()

    def persist(
        self,
        result: InspectionResult,
        request_record: RequestRecord | None = None,
        artifacts_dir: str | Path | None = None,
        run_id: str | None = None,
    ) -> PersistenceSummaryDTO:
        resolved_run_id = run_id or result.workbook_profile.run_id or (
            request_record.run_id if request_record else None
        )
        if not resolved_run_id:
            raise PersistenceError("Cannot persist inspection without a run_id.")

        try:
            with self.manager.session_scope() as session:
                existing_run = PipelineRunRepository(session).get(resolved_run_id)
                if existing_run and existing_run.status == "COMPLETED":
                    return self._summary(existing_run)
        except Exception as exc:
            raise PersistenceError(f"Could not read existing run {resolved_run_id}: {exc}") from exc

        started_at = (
            result.workbook_profile.inspection_started_at
            or (request_record.started_at if request_record else None)
            or utcnow()
        )
        completed_at = (
            result.workbook_profile.inspection_completed_at
            or (request_record.completed_at if request_record else None)
            or utcnow()
        )
        file_hash = result.workbook_profile.file_hash
        if not file_hash:
            error = PersistenceError("Workbook profile has no file_hash; cannot persist source file.")
            self._mark_failed(
                resolved_run_id,
                started_at,
                completed_at,
                request_record,
                artifacts_dir,
                error,
            )
            raise error

        try:
            with self.manager.unit_of_work() as uow:
                run_repo = PipelineRunRepository(uow.session)
                step_repo = PipelineStepRepository(uow.session)
                source_repo = SourceFileRepository(uow.session)
                sheet_repo = SourceSheetRepository(uow.session)
                variable_repo = VariableRepository(uow.session)
                quality_repo = VariableQualityRepository(uow.session)
                audit_repo = AuditEventRepository(uow.session)

                request_payload = redact_sensitive_values(
                    request_record.model_dump(mode="json") if request_record else {"run_id": resolved_run_id}
                )
                input_path = str(Path(result.workbook_profile.workbook_path).resolve())
                artifacts_path = str(Path(artifacts_dir).resolve()) if artifacts_dir else None
                run_dto = PipelineRunDTO(
                    run_id=resolved_run_id,
                    run_type="INSPECTION",
                    status="RUNNING",
                    started_at=started_at,
                    completed_at=None,
                    failed_at=None,
                    current_step="INSPECTION_PERSISTENCE",
                    last_successful_step=None,
                    input_request_json=request_payload,
                    artifacts_path=artifacts_path,
                    error_type=None,
                    error_message=None,
                    is_retriable=True,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                run_repo.create(run_dto)
                run_repo.update(
                    resolved_run_id,
                    status="RUNNING",
                    current_step="INSPECTION_PERSISTENCE",
                    last_successful_step=None,
                    error_type=None,
                    error_message=None,
                    failed_at=None,
                )
                existing_steps = step_repo.list_for_run(resolved_run_id)
                persistence_attempt = next(
                    (
                        step.attempt_count + 1
                        for step in existing_steps
                        if step.step_name == "INSPECTION_PERSISTENCE"
                    ),
                    1,
                )

                file_id = f"file_{file_hash[:16]}"
                source_file = SourceFileDTO(
                    file_id=file_id,
                    file_hash=file_hash,
                    file_name=result.workbook_profile.file_name,
                    original_path=input_path,
                    file_size_bytes=result.workbook_profile.file_size_bytes,
                    extension=Path(input_path).suffix.lower() or ".xlsx",
                    sheet_count=len(result.workbook_profile.sheets),
                    inspection_status=result.workbook_profile.status,
                    first_seen_at=started_at,
                    last_seen_at=completed_at,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                source_repo.upsert_by_hash(source_file)
                source_repo.record_run_file(
                    resolved_run_id,
                    file_id,
                    input_path=input_path,
                    artifact_path=artifacts_path,
                    created_at=started_at,
                )

                sheet_ids = {
                    sheet.sheet_index: f"sheet_{file_hash[:16]}_{sheet.sheet_index}"
                    for sheet in result.workbook_profile.sheets
                }
                sheet_dtos = [
                    SourceSheetDTO(
                        sheet_id=sheet_ids[sheet.sheet_index],
                        file_id=file_id,
                        sheet_name=sheet.sheet_name,
                        sheet_index=sheet.sheet_index,
                        row_count=sheet.row_count,
                        column_count=sheet.column_count,
                        metadata_row_count=sheet.metadata_row_count,
                        is_empty=sheet.empty_sheet,
                        detected_header_row=sheet.detected_header_row,
                        header_confidence=sheet.header_confidence,
                        selected_date_column=sheet.selected_date_column,
                        date_column_confidence=sheet.date_column_confidence,
                        variable_column_count=sheet.variable_column_count,
                        status=sheet.status,
                        review_reasons_json=sheet.review_reasons,
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                    for sheet in result.workbook_profile.sheets
                ]
                sheet_repo.bulk_upsert(file_id, sheet_dtos)

                variable_dtos = [
                    VariableDTO(
                        variable_id=profile.variable_id,
                        file_id=file_id,
                        sheet_id=sheet_ids[profile.sheet_index],
                        original_name=profile.original_name or profile.column_name,
                        normalized_name=profile.normalized_name or profile.normalized_header,
                        column_index=profile.column_index,
                        column_letter=profile.column_letter,
                        date_column_name=profile.date_column_name,
                        inferred_data_type=profile.inferred_data_type or profile.data_type.value,
                        unit_hint=profile.unit_hint,
                        is_empty=profile.is_empty or profile.all_empty,
                        is_numeric_candidate=profile.is_numeric_candidate,
                        is_text_description=profile.is_text_description,
                        profile_status=profile.profile_status,
                        review_reasons_json=profile.review_reasons,
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                    for profile in result.variable_profiles
                ]
                variable_repo.bulk_upsert(variable_dtos)

                quality_dtos = [
                    VariableQualityDTO(
                        variable_id=profile.variable_id,
                        observation_count=profile.observation_count,
                        non_null_count=profile.non_null_count,
                        missing_count=profile.missing_count,
                        missing_rate=profile.missing_rate,
                        unique_value_count=profile.unique_value_count,
                        start_date=profile.start_date,
                        end_date=profile.end_date,
                        coverage_days=profile.coverage_days,
                        latest_observation_date=profile.latest_observation_date,
                        latest_gap_days=profile.latest_gap_days,
                        duplicate_date_count=profile.duplicate_date_count,
                        is_constant=profile.constant or profile.is_constant,
                        numeric_parse_success_rate=profile.numeric_parse_success_rate,
                        date_aligned_observation_count=profile.date_aligned_observation_count,
                        detected_frequency=profile.frequency.detected_frequency,
                        median_interval_days=profile.frequency.median_interval_days,
                        dominant_interval_days=profile.frequency.major_interval_days,
                        dominant_interval_ratio=profile.frequency.major_interval_ratio,
                        frequency_confidence=profile.frequency.confidence,
                        frequency_reason_codes_json=profile.frequency.frequency_reason_codes,
                        is_pseudo_high_frequency=profile.is_pseudo_high_frequency,
                        pseudo_frequency_confidence=profile.pseudo_frequency_confidence,
                        pseudo_frequency_reason_codes_json=profile.pseudo_frequency_reason_codes,
                        calculated_at=completed_at,
                    )
                    for profile in result.variable_profiles
                ]
                quality_repo.bulk_upsert(quality_dtos)
                variable_repo.save_run_variables(
                    resolved_run_id,
                    [
                        RunVariableDTO(
                            run_id=resolved_run_id,
                            variable_id=profile.variable_id,
                            profile_status=profile.profile_status,
                            created_at=utcnow(),
                        )
                        for profile in result.variable_profiles
                    ],
                )

                audit_repo.add(
                    AuditEventDTO(
                        event_id=str(uuid4()),
                        run_id=resolved_run_id,
                        event_type="FILE_PROCESSING_STARTED",
                        entity_type="source_file",
                        entity_id=file_id,
                        event_payload_json=redact_sensitive_values(
                            {
                                "file_hash": file_hash,
                                "file_path": input_path,
                                "file_size_bytes": result.workbook_profile.file_size_bytes,
                            }
                        ),
                        created_at=utcnow(),
                    )
                )
                for sheet in result.workbook_profile.sheets:
                    audit_repo.add(
                        AuditEventDTO(
                            event_id=str(uuid4()),
                            run_id=resolved_run_id,
                            event_type="SHEET_REVIEWED",
                            entity_type="source_sheet",
                            entity_id=sheet_ids[sheet.sheet_index],
                            event_payload_json={"sheet_index": sheet.sheet_index, "status": sheet.status},
                            created_at=utcnow(),
                        )
                    )
                audit_repo.add(
                    AuditEventDTO(
                        event_id=str(uuid4()),
                        run_id=resolved_run_id,
                        event_type="VARIABLE_PROFILE_CREATED",
                        entity_type="variables",
                        entity_id=resolved_run_id,
                        event_payload_json={"variable_count": len(result.variable_profiles)},
                        created_at=utcnow(),
                    )
                )

                step_repo.upsert(
                    PipelineStepDTO(
                        step_id=_stable_hash(resolved_run_id, "INSPECTION_PERSISTENCE"),
                        run_id=resolved_run_id,
                        step_name="INSPECTION_PERSISTENCE",
                        step_order=1,
                        status="RUNNING",
                        started_at=started_at,
                        completed_at=None,
                        attempt_count=persistence_attempt,
                        input_hash=file_hash,
                        output_artifact_path=artifacts_path,
                        error_type=None,
                        error_message=None,
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )

                run_repo.mark_completed(
                    resolved_run_id,
                    completed_at=completed_at,
                    current_step="INSPECTION_PERSISTENCE",
                    last_successful_step="INSPECTION_PERSISTENCE",
                )
                step_repo.upsert(
                    PipelineStepDTO(
                        step_id=_stable_hash(resolved_run_id, "INSPECTION_PERSISTENCE"),
                        run_id=resolved_run_id,
                        step_name="INSPECTION_PERSISTENCE",
                        step_order=1,
                        status="COMPLETED",
                        started_at=started_at,
                        completed_at=completed_at,
                        attempt_count=persistence_attempt,
                        input_hash=file_hash,
                        output_artifact_path=artifacts_path,
                        error_type=None,
                        error_message=None,
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
                audit_repo.add(
                    AuditEventDTO(
                        event_id=str(uuid4()),
                        run_id=resolved_run_id,
                        event_type="DATABASE_WRITE_COMPLETED",
                        entity_type="pipeline_run",
                        entity_id=resolved_run_id,
                        event_payload_json={
                            "sheet_count": len(sheet_dtos),
                            "variable_count": len(variable_dtos),
                        },
                        created_at=completed_at,
                    )
                )
        except Exception as exc:
            self._mark_failed(
                resolved_run_id,
                started_at,
                completed_at,
                request_record,
                artifacts_dir,
                exc,
            )
            raise PersistenceError(f"Persistence failed for run {resolved_run_id}: {exc}") from exc

        with self.manager.session_scope() as session:
            run = PipelineRunRepository(session).get(resolved_run_id)
            if run is None:
                raise PersistenceError(f"Run {resolved_run_id} was not persisted.")
            return self._summary(run)

    def _summary(self, run: PipelineRunDTO) -> PersistenceSummaryDTO:
        with self.manager.session_scope() as session:
            file_repo = SourceFileRepository(session)
            sheet_repo = SourceSheetRepository(session)
            variable_repo = VariableRepository(session)
            quality_repo = VariableQualityRepository(session)
            audit_repo = AuditEventRepository(session)
            return PersistenceSummaryDTO(
                run_id=run.run_id,
                status=run.status,
                file_count=file_repo.count_run_files(run.run_id),
                source_file_count=file_repo.count_for_run(run.run_id),
                sheet_count=sheet_repo.count_for_run(run.run_id),
                variable_count=variable_repo.count_for_run(run.run_id),
                quality_count=quality_repo.count_for_run(run.run_id),
                audit_event_count=audit_repo.count_for_run(run.run_id),
                run_file_count=file_repo.count_run_files(run.run_id),
                run_variable_count=variable_repo.count_for_run(run.run_id),
                idempotent_skip=run.status == "COMPLETED",
            )

    def _mark_failed(
        self,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        request_record: RequestRecord | None,
        artifacts_dir: str | Path | None,
        error: Exception,
    ) -> None:
        artifacts_path = str(Path(artifacts_dir).resolve()) if artifacts_dir else None
        try:
            with self.manager.unit_of_work() as uow:
                run_repo = PipelineRunRepository(uow.session)
                step_repo = PipelineStepRepository(uow.session)
                audit_repo = AuditEventRepository(uow.session)
                existing = run_repo.get(run_id)
                if existing is None:
                    run_repo.create(
                        PipelineRunDTO(
                            run_id=run_id,
                            run_type="INSPECTION",
                            status="FAILED",
                            started_at=started_at,
                            completed_at=None,
                            failed_at=completed_at,
                            current_step="INSPECTION_PERSISTENCE",
                            last_successful_step=None,
                            input_request_json=redact_sensitive_values(
                                request_record.model_dump(mode="json") if request_record else {"run_id": run_id}
                            ),
                            artifacts_path=artifacts_path,
                            error_type=type(error).__name__,
                            error_message=str(error),
                            is_retriable=True,
                            created_at=utcnow(),
                            updated_at=utcnow(),
                        )
                    )
                run_repo.mark_failed(
                    run_id,
                    failed_at=completed_at,
                    error_type=type(error).__name__,
                    error_message=str(error),
                    current_step="INSPECTION_PERSISTENCE",
                    last_successful_step=None,
                    is_retriable=True,
                )
                step_repo.upsert(
                    PipelineStepDTO(
                        step_id=_stable_hash(run_id, "INSPECTION_PERSISTENCE"),
                        run_id=run_id,
                        step_name="INSPECTION_PERSISTENCE",
                        step_order=1,
                        status="FAILED",
                        started_at=started_at,
                        completed_at=completed_at,
                        attempt_count=1,
                        input_hash=None,
                        output_artifact_path=artifacts_path,
                        error_type=type(error).__name__,
                        error_message=str(error),
                        created_at=utcnow(),
                        updated_at=utcnow(),
                    )
                )
                audit_repo.add(
                    AuditEventDTO(
                        event_id=str(uuid4()),
                        run_id=run_id,
                        event_type="PIPELINE_STEP_FAILED",
                        entity_type="pipeline_step",
                        entity_id="INSPECTION_PERSISTENCE",
                        event_payload_json={"step_name": "INSPECTION_PERSISTENCE"},
                        created_at=completed_at,
                    )
                )
                audit_repo.add(
                    AuditEventDTO(
                        event_id=str(uuid4()),
                        run_id=run_id,
                        event_type="WORKFLOW_RECOVERY",
                        entity_type="pipeline_run",
                        entity_id=run_id,
                        event_payload_json={"status": "FAILED", "is_retriable": True},
                        created_at=completed_at,
                    )
                )
        except Exception as recovery_error:
            raise PersistenceError(
                f"Persistence failed and failed-run recovery also failed for {run_id}: {recovery_error}"
            ) from recovery_error


class RunQueryService:
    def __init__(self, manager: DatabaseManager | None = None) -> None:
        self.manager = manager or DatabaseManager()

    def get_run_summary(self, run_id: str) -> RunSummaryDTO:
        with self.manager.session_scope() as session:
            run = PipelineRunRepository(session).get(run_id)
            if run is None:
                raise EntityNotFoundError(f"Pipeline run not found: {run_id}")
            file_repo = SourceFileRepository(session)
            sheet_repo = SourceSheetRepository(session)
            variable_repo = VariableRepository(session)
            quality_repo = VariableQualityRepository(session)
            audit_repo = AuditEventRepository(session)
            return RunSummaryDTO(
                run=run,
                file_count=file_repo.count_run_files(run_id),
                source_file_count=file_repo.count_for_run(run_id),
                sheet_count=sheet_repo.count_for_run(run_id),
                variable_count=variable_repo.count_for_run(run_id),
                quality_count=quality_repo.count_for_run(run_id),
                review_count=len(quality_repo.list_needs_review(run_id=run_id)),
                audit_event_count=audit_repo.count_for_run(run_id),
            )
