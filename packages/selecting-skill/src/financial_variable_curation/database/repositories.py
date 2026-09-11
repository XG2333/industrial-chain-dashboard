from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from financial_variable_curation.database.exceptions import EntityNotFoundError, RepositoryError
from financial_variable_curation.database.models import (
    AuditEvent,
    ClassificationCache,
    ExportRun,
    ExportedVariable,
    LlmCall,
    PipelineRun,
    PipelineStep,
    ReviewItem,
    Rule,
    RuleConflict,
    RuleParseCache,
    RuleParseRun,
    RuleSet,
    SelectionRun,
    RunFile,
    RunVariable,
    SourceFile,
    SourceSheet,
    Variable,
    VariableClassification,
    VariableQuality,
    VariableSelectionResult,
)
from financial_variable_curation.database.schemas import (
    AuditEventDTO,
    ClassificationCacheDTO,
    ClassificationCandidateDTO,
    ExportedVariableDTO,
    ExportRunDTO,
    FrequencyStatusStatDTO,
    LlmCallDTO,
    PipelineRunDTO,
    PipelineStepDTO,
    ReviewItemDTO,
    RuleConflictDTO,
    RuleDTO,
    RuleParseCacheDTO,
    RuleParseRunDTO,
    RuleSetDTO,
    SelectionRunDTO,
    ReviewVariableDTO,
    RunFileDTO,
    RunVariableDTO,
    SourceFileDTO,
    SourceSheetDTO,
    VariableDTO,
    VariableClassificationDTO,
    VariableQualityDTO,
    VariableSelectionResultDTO,
)


class PipelineRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: str) -> PipelineRunDTO | None:
        run = self.session.get(PipelineRun, run_id)
        return PipelineRunDTO.model_validate(run) if run else None

    def create(self, run: PipelineRunDTO) -> PipelineRunDTO:
        existing = self.get(run.run_id)
        if existing is not None:
            return existing
        try:
            self.session.add(PipelineRun(**run.model_dump(mode="python")))
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot create pipeline run {run.run_id}: {exc}") from exc
        return self.get(run.run_id)  # type: ignore[return-value]

    def update(self, run_id: str, **fields: object) -> PipelineRunDTO:
        run = self.session.get(PipelineRun, run_id)
        if run is None:
            raise EntityNotFoundError(f"Pipeline run not found: {run_id}")
        try:
            for key, value in fields.items():
                setattr(run, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot update pipeline run {run_id}: {exc}") from exc
        return PipelineRunDTO.model_validate(run)

    def mark_completed(
        self,
        run_id: str,
        completed_at: object,
        current_step: str | None = None,
        last_successful_step: str | None = None,
    ) -> PipelineRunDTO:
        return self.update(
            run_id,
            status="COMPLETED",
            completed_at=completed_at,
            current_step=current_step,
            last_successful_step=last_successful_step,
            error_type=None,
            error_message=None,
            failed_at=None,
        )

    def mark_failed(
        self,
        run_id: str,
        failed_at: object,
        error_type: str,
        error_message: str,
        current_step: str | None = None,
        last_successful_step: str | None = None,
        is_retriable: bool = True,
    ) -> PipelineRunDTO:
        return self.update(
            run_id,
            status="FAILED",
            failed_at=failed_at,
            error_type=error_type,
            error_message=error_message,
            current_step=current_step,
            last_successful_step=last_successful_step,
            is_retriable=is_retriable,
            completed_at=None,
        )

    def get_last_successful_step(self, run_id: str) -> str | None:
        run = self.get(run_id)
        return run.last_successful_step if run else None

    def is_retriable(self, run_id: str) -> bool:
        run = self.get(run_id)
        return bool(run and run.is_retriable)

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(PipelineRun.run_id))) or 0)


class PipelineStepRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, step: PipelineStepDTO) -> PipelineStepDTO:
        existing = self.session.scalar(
            select(PipelineStep).where(
                PipelineStep.run_id == step.run_id,
                PipelineStep.step_name == step.step_name,
            )
        )
        try:
            if existing is None:
                self.session.add(PipelineStep(**step.model_dump(mode="python")))
            else:
                for key, value in step.model_dump(mode="python").items():
                    if key not in {"step_id", "run_id", "step_name", "created_at"}:
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot upsert pipeline step {step.step_name}: {exc}") from exc
        persisted = self.session.scalar(
            select(PipelineStep).where(
                PipelineStep.run_id == step.run_id,
                PipelineStep.step_name == step.step_name,
            )
        )
        return PipelineStepDTO.model_validate(persisted)

    def list_for_run(self, run_id: str) -> list[PipelineStepDTO]:
        steps = self.session.scalars(
            select(PipelineStep).where(PipelineStep.run_id == run_id).order_by(PipelineStep.step_order)
        ).all()
        return [PipelineStepDTO.model_validate(step) for step in steps]


class SourceFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_hash(self, file_hash: str) -> SourceFileDTO | None:
        source = self.session.scalar(select(SourceFile).where(SourceFile.file_hash == file_hash))
        return SourceFileDTO.model_validate(source) if source else None

    def upsert_by_hash(self, source: SourceFileDTO) -> SourceFileDTO:
        existing = self.session.scalar(
            select(SourceFile).where(SourceFile.file_hash == source.file_hash)
        )
        try:
            if existing is None:
                self.session.add(SourceFile(**source.model_dump(mode="python")))
            else:
                existing.file_name = source.file_name
                existing.original_path = source.original_path
                existing.file_size_bytes = source.file_size_bytes
                existing.extension = source.extension
                existing.sheet_count = source.sheet_count
                existing.inspection_status = source.inspection_status
                existing.last_seen_at = source.last_seen_at
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot upsert source file {source.file_hash}: {exc}") from exc
        persisted = self.session.scalar(
            select(SourceFile).where(SourceFile.file_hash == source.file_hash)
        )
        return SourceFileDTO.model_validate(persisted)

    def record_run_file(
        self,
        run_id: str,
        file_id: str,
        input_path: str,
        artifact_path: str | None = None,
        created_at: object | None = None,
    ) -> RunFileDTO:
        existing = self.session.get(RunFile, (run_id, file_id))
        try:
            if existing is None:
                from financial_variable_curation.database.types import utcnow

                self.session.add(
                    RunFile(
                        run_id=run_id,
                        file_id=file_id,
                        input_path=input_path,
                        artifact_path=artifact_path,
                        created_at=created_at or utcnow(),
                    )
                )
            else:
                existing.input_path = input_path
                existing.artifact_path = artifact_path
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot record run file {run_id}/{file_id}: {exc}") from exc
        return RunFileDTO.model_validate(self.session.get(RunFile, (run_id, file_id)))

    def list_for_run(self, run_id: str) -> list[SourceFileDTO]:
        sources = self.session.scalars(
            select(SourceFile)
            .join(RunFile, RunFile.file_id == SourceFile.file_id)
            .where(RunFile.run_id == run_id)
            .order_by(SourceFile.file_hash)
        ).all()
        return [SourceFileDTO.model_validate(source) for source in sources]

    def count_run_files(self, run_id: str) -> int:
        return int(self.session.scalar(select(func.count(RunFile.run_id)).where(RunFile.run_id == run_id)) or 0)

    def count_for_run(self, run_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(func.distinct(SourceFile.file_id)))
                .select_from(RunFile)
                .join(SourceFile, SourceFile.file_id == RunFile.file_id)
                .where(RunFile.run_id == run_id)
            )
            or 0
        )

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(SourceFile.file_id))) or 0)


class SourceSheetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_upsert(self, file_id: str, sheets: list[SourceSheetDTO]) -> list[SourceSheetDTO]:
        existing = {
            sheet.sheet_index: sheet
            for sheet in self.session.scalars(
                select(SourceSheet).where(SourceSheet.file_id == file_id)
            ).all()
        }
        try:
            for dto in sheets:
                if dto.file_id != file_id:
                    raise ValueError(f"Sheet {dto.sheet_id} belongs to a different file.")
                current = existing.get(dto.sheet_index)
                if current is None:
                    self.session.add(SourceSheet(**dto.model_dump(mode="python")))
                else:
                    for key, value in dto.model_dump(mode="python").items():
                        if key not in {"sheet_id", "file_id", "created_at"}:
                            setattr(current, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot upsert sheets for file {file_id}: {exc}") from exc
        return self.list_by_file_id(file_id)

    def list_by_file_id(self, file_id: str) -> list[SourceSheetDTO]:
        sheets = self.session.scalars(
            select(SourceSheet).where(SourceSheet.file_id == file_id).order_by(SourceSheet.sheet_index)
        ).all()
        return [SourceSheetDTO.model_validate(sheet) for sheet in sheets]

    def get_by_file_and_index(self, file_id: str, sheet_index: int) -> SourceSheetDTO | None:
        sheet = self.session.scalar(
            select(SourceSheet).where(
                SourceSheet.file_id == file_id,
                SourceSheet.sheet_index == sheet_index,
            )
        )
        return SourceSheetDTO.model_validate(sheet) if sheet else None

    def count_for_run(self, run_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(func.distinct(SourceSheet.sheet_id)))
                .select_from(RunFile)
                .join(SourceFile, SourceFile.file_id == RunFile.file_id)
                .join(SourceSheet, SourceSheet.file_id == SourceFile.file_id)
                .where(RunFile.run_id == run_id)
            )
            or 0
        )

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(SourceSheet.sheet_id))) or 0)


class VariableRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_upsert(self, variables: list[VariableDTO]) -> list[VariableDTO]:
        if not variables:
            return []
        existing = {
            variable.variable_id: variable
            for variable in self.session.scalars(
                select(Variable).where(
                    Variable.variable_id.in_([item.variable_id for item in variables])
                )
            ).all()
        }
        try:
            for dto in variables:
                current = existing.get(dto.variable_id)
                if current is None:
                    self.session.add(Variable(**dto.model_dump(mode="python")))
                else:
                    for key, value in dto.model_dump(mode="python").items():
                        if key != "created_at":
                            setattr(current, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError("Cannot upsert variables: {exc}".format(exc=exc)) from exc
        return self.list_by_ids([item.variable_id for item in variables])

    def list_by_ids(self, variable_ids: list[str]) -> list[VariableDTO]:
        variables = self.session.scalars(
            select(Variable).where(Variable.variable_id.in_(variable_ids))
        ).all()
        return [VariableDTO.model_validate(variable) for variable in variables]

    def get_by_id(self, variable_id: str) -> VariableDTO | None:
        variable = self.session.get(Variable, variable_id)
        return VariableDTO.model_validate(variable) if variable else None

    def list_by_run_id(self, run_id: str) -> list[VariableDTO]:
        variables = self.session.scalars(
            select(Variable)
            .join(RunVariable, RunVariable.variable_id == Variable.variable_id)
            .where(RunVariable.run_id == run_id)
            .order_by(Variable.sheet_id, Variable.column_index)
        ).all()
        return [VariableDTO.model_validate(variable) for variable in variables]

    def list_classification_candidates(
        self,
        run_id: str,
        *,
        limit: int | None = None,
        variable_ids: list[str] | None = None,
        skip_non_data: bool = False,
    ) -> list[ClassificationCandidateDTO]:
        statement = (
            select(Variable, SourceFile.file_name, SourceSheet.sheet_name, VariableQuality)
            .join(SourceSheet, SourceSheet.sheet_id == Variable.sheet_id)
            .join(SourceFile, SourceFile.file_id == Variable.file_id)
            .outerjoin(VariableQuality, VariableQuality.variable_id == Variable.variable_id)
            .join(RunVariable, RunVariable.variable_id == Variable.variable_id)
        .where(RunVariable.run_id == run_id)
        .order_by(SourceSheet.sheet_index, Variable.column_index, Variable.variable_id)
    )
        if skip_non_data:
            statement = statement.where(
                VariableQuality.is_constant == False,
                VariableQuality.is_pseudo_high_frequency == False,
            )
        if variable_ids:
            statement = statement.where(Variable.variable_id.in_(variable_ids))
        if limit is not None:
            statement = statement.limit(limit)
        rows = self.session.execute(statement).all()
        return [
            ClassificationCandidateDTO(
                variable=VariableDTO.model_validate(variable),
                file_name=file_name,
                sheet_name=sheet_name,
                quality=VariableQualityDTO.model_validate(quality) if quality else None,
            )
            for variable, file_name, sheet_name, quality in rows
        ]

    def list_by_file_id(self, file_id: str) -> list[VariableDTO]:
        variables = self.session.scalars(
            select(Variable).where(Variable.file_id == file_id).order_by(Variable.column_index)
        ).all()
        return [VariableDTO.model_validate(variable) for variable in variables]

    def list_by_sheet_id(self, sheet_id: str) -> list[VariableDTO]:
        variables = self.session.scalars(
            select(Variable).where(Variable.sheet_id == sheet_id).order_by(Variable.column_index)
        ).all()
        return [VariableDTO.model_validate(variable) for variable in variables]

    def save_run_variables(self, run_id: str, items: list[RunVariableDTO]) -> None:
        existing = {
            item.variable_id: item
            for item in self.session.scalars(
                select(RunVariable).where(
                    RunVariable.run_id == run_id,
                    RunVariable.variable_id.in_([item.variable_id for item in items]),
                )
            ).all()
        }
        try:
            for item in items:
                current = existing.get(item.variable_id)
                if current is None:
                    self.session.add(RunVariable(**item.model_dump(mode="python")))
                else:
                    current.profile_status = item.profile_status
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save run variables for {run_id}: {exc}") from exc

    def count_for_run(self, run_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(func.distinct(RunVariable.variable_id))).where(
                    RunVariable.run_id == run_id
                )
            )
            or 0
        )

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(Variable.variable_id))) or 0)


class VariableQualityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_upsert(self, qualities: list[VariableQualityDTO]) -> list[VariableQualityDTO]:
        if not qualities:
            return []
        existing = {
            item.variable_id: item
            for item in self.session.scalars(
                select(VariableQuality).where(
                    VariableQuality.variable_id.in_([item.variable_id for item in qualities])
                )
            ).all()
        }
        try:
            for dto in qualities:
                current = existing.get(dto.variable_id)
                if current is None:
                    self.session.add(VariableQuality(**dto.model_dump(mode="python")))
                else:
                    for key, value in dto.model_dump(mode="python").items():
                        if key != "variable_id":
                            setattr(current, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError("Cannot upsert variable quality profiles: {exc}".format(exc=exc)) from exc
        return self.list_by_ids([item.variable_id for item in qualities])

    def list_by_ids(self, variable_ids: list[str]) -> list[VariableQualityDTO]:
        qualities = self.session.scalars(
            select(VariableQuality).where(VariableQuality.variable_id.in_(variable_ids))
        ).all()
        return [VariableQualityDTO.model_validate(quality) for quality in qualities]

    def get_by_variable_id(self, variable_id: str) -> VariableQualityDTO | None:
        quality = self.session.get(VariableQuality, variable_id)
        return VariableQualityDTO.model_validate(quality) if quality else None

    def list_by_run_id(self, run_id: str) -> list[VariableQualityDTO]:
        qualities = self.session.scalars(
            select(VariableQuality)
            .join(RunVariable, RunVariable.variable_id == VariableQuality.variable_id)
            .where(RunVariable.run_id == run_id)
            .order_by(VariableQuality.variable_id)
        ).all()
        return [VariableQualityDTO.model_validate(quality) for quality in qualities]

    def list_needs_review(self, run_id: str | None = None) -> list[ReviewVariableDTO]:
        statement = (
            select(Variable, VariableQuality.missing_rate)
            .join(VariableQuality, VariableQuality.variable_id == Variable.variable_id)
            .where(
                or_(
                    Variable.profile_status == "NEEDS_REVIEW",
                    VariableQuality.missing_rate > 0.5,
                    VariableQuality.is_constant.is_(True),
                )
            )
            .order_by(Variable.sheet_id, Variable.column_index)
        )
        if run_id is not None:
            statement = statement.join(RunVariable, RunVariable.variable_id == Variable.variable_id).where(
                RunVariable.run_id == run_id
            )
        rows = self.session.execute(statement).all()
        return [
            ReviewVariableDTO(
                variable_id=variable.variable_id,
                column_name=variable.original_name,
                profile_status=variable.profile_status,
                missing_rate=missing_rate,
                is_constant=variable.review_reasons_json is not None
                and "CONSTANT_COLUMN" in variable.review_reasons_json,
                review_reasons=variable.review_reasons_json,
            )
            for variable, missing_rate in rows
        ]

    def count_by_frequency_and_status(self) -> list[FrequencyStatusStatDTO]:
        rows = self.session.execute(
            select(
                VariableQuality.detected_frequency,
                Variable.profile_status,
                func.count(Variable.variable_id),
            )
            .join(Variable, Variable.variable_id == VariableQuality.variable_id)
            .group_by(VariableQuality.detected_frequency, Variable.profile_status)
            .order_by(VariableQuality.detected_frequency, Variable.profile_status)
        ).all()
        return [
            FrequencyStatusStatDTO(
                detected_frequency=detected_frequency,
                profile_status=profile_status,
                count=int(count),
            )
            for detected_frequency, profile_status, count in rows
        ]

    def count_for_run(self, run_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(VariableQuality.variable_id))
                .join(RunVariable, RunVariable.variable_id == VariableQuality.variable_id)
                .where(RunVariable.run_id == run_id)
            )
            or 0
        )

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(VariableQuality.variable_id))) or 0)


class AuditEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: AuditEventDTO) -> AuditEventDTO:
        try:
            self.session.add(AuditEvent(**event.model_dump(mode="python")))
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot write audit event {event.event_type}: {exc}") from exc
        return event

    def list_by_run(self, run_id: str, event_type: str | None = None) -> list[AuditEventDTO]:
        statement = select(AuditEvent).where(AuditEvent.run_id == run_id)
        if event_type is not None:
            statement = statement.where(AuditEvent.event_type == event_type)
        events = self.session.scalars(statement.order_by(AuditEvent.created_at, AuditEvent.event_id)).all()
        return [AuditEventDTO.model_validate(event) for event in events]

    def count_for_run(self, run_id: str, event_type: str | None = None) -> int:
        statement = select(func.count(AuditEvent.event_id)).where(AuditEvent.run_id == run_id)
        if event_type is not None:
            statement = statement.where(AuditEvent.event_type == event_type)
        return int(self.session.scalar(statement) or 0)

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(AuditEvent.event_id))) or 0)


class LlmCallRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, call: LlmCallDTO) -> LlmCallDTO:
        try:
            self.session.add(LlmCall(**call.model_dump(mode="python")))
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot write LLM call {call.llm_call_id}: {exc}") from exc
        return call

    def list_for_run(self, run_id: str) -> list[LlmCallDTO]:
        calls = self.session.scalars(
            select(LlmCall).where(LlmCall.run_id == run_id).order_by(LlmCall.created_at)
        ).all()
        return [LlmCallDTO.model_validate(call) for call in calls]

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(LlmCall.llm_call_id))) or 0)


class VariableClassificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_batch(self, items: list[VariableClassificationDTO]) -> list[VariableClassificationDTO]:
        if not items:
            return []
        existing = {
            item.classification_id: item
            for item in self.session.scalars(
                select(VariableClassification).where(
                    VariableClassification.classification_id.in_(
                        [item.classification_id for item in items]
                    )
                )
            ).all()
        }
        try:
            for item in items:
                current = existing.get(item.classification_id)
                if current is None:
                    self.session.add(VariableClassification(**item.model_dump(mode="python")))
                else:
                    for key, value in item.model_dump(mode="python").items():
                        if key != "created_at":
                            setattr(current, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError("Cannot upsert variable classifications: {exc}".format(exc=exc)) from exc
        return [
            VariableClassificationDTO.model_validate(self.session.get(VariableClassification, item.classification_id))
            for item in items
        ]

    def list_for_run(self, run_id: str) -> list[VariableClassificationDTO]:
        items = self.session.scalars(
            select(VariableClassification)
            .where(VariableClassification.run_id == run_id)
            .order_by(VariableClassification.variable_id)
        ).all()
        return [VariableClassificationDTO.model_validate(item) for item in items]

    def count_for_run(self, run_id: str, status: str | None = None) -> int:
        statement = select(func.count(VariableClassification.classification_id)).where(
            VariableClassification.run_id == run_id
        )
        if status is not None:
            statement = statement.where(VariableClassification.classification_status == status)
        return int(self.session.scalar(statement) or 0)


class ClassificationCacheRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, cache_key: str) -> ClassificationCacheDTO | None:
        item = self.session.get(ClassificationCache, cache_key)
        return ClassificationCacheDTO.model_validate(item) if item else None

    def set(self, item: ClassificationCacheDTO) -> ClassificationCacheDTO:
        existing = self.session.get(ClassificationCache, item.cache_key)
        try:
            if existing is None:
                self.session.add(ClassificationCache(**item.model_dump(mode="python")))
            else:
                for key, value in item.model_dump(mode="python").items():
                    if key != "cache_key":
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot write classification cache {item.cache_key}: {exc}") from exc
        return ClassificationCacheDTO.model_validate(
            self.session.get(ClassificationCache, item.cache_key)
        )

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(ClassificationCache.cache_key))) or 0)


class ReviewItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, item: ReviewItemDTO) -> ReviewItemDTO:
        existing = self.session.get(ReviewItem, item.review_item_id)
        try:
            if existing is None:
                self.session.add(ReviewItem(**item.model_dump(mode="python")))
            else:
                for key, value in item.model_dump(mode="python").items():
                    if key not in {"review_item_id", "created_at"}:
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot write review item {item.review_item_id}: {exc}") from exc
        return ReviewItemDTO.model_validate(self.session.get(ReviewItem, item.review_item_id))

    def list_for_run(self, run_id: str) -> list[ReviewItemDTO]:
        items = self.session.scalars(
            select(ReviewItem).where(ReviewItem.run_id == run_id).order_by(ReviewItem.created_at)
        ).all()
        return [ReviewItemDTO.model_validate(item) for item in items]

    def count_for_run(self, run_id: str, status: str | None = None) -> int:
        statement = select(func.count(ReviewItem.review_item_id)).where(ReviewItem.run_id == run_id)
        if status is not None:
            statement = statement.where(ReviewItem.status == status)
        return int(self.session.scalar(statement) or 0)


class RuleSetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, rule_set_id: str) -> RuleSetDTO | None:
        item = self.session.get(RuleSet, rule_set_id)
        return RuleSetDTO.model_validate(item) if item else None

    def get_by_name_version(self, name: str, version: str) -> RuleSetDTO | None:
        item = self.session.scalar(
            select(RuleSet).where(
                RuleSet.rule_set_name == name,
                RuleSet.version == version,
            )
        )
        return RuleSetDTO.model_validate(item) if item else None

    def get_active(self, name: str) -> RuleSetDTO | None:
        item = self.session.scalar(
            select(RuleSet).where(
                RuleSet.rule_set_name == name,
                RuleSet.status == "ACTIVE",
            )
        )
        return RuleSetDTO.model_validate(item) if item else None

    def save(self, item: RuleSetDTO) -> RuleSetDTO:
        existing = self.get(item.rule_set_id)
        try:
            if existing is None:
                self.session.add(RuleSet(**item.model_dump(mode="python")))
            else:
                for key, value in item.model_dump(mode="python").items():
                    if key != "created_at":
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save rule set {item.rule_set_id}: {exc}") from exc
        return RuleSetDTO.model_validate(self.session.get(RuleSet, item.rule_set_id))

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(RuleSet.rule_set_id))) or 0)


class RuleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_save(self, rule_set_id: str, rules: list[RuleDTO]) -> None:
        existing = {
            item.rule_id: item
            for item in self.session.scalars(
                select(Rule).where(
                    Rule.rule_set_id == rule_set_id,
                    Rule.rule_id.in_([item.rule_id for item in rules]),
                )
            ).all()
        }
        try:
            for item in rules:
                current = existing.get(item.rule_id)
                if current is None:
                    self.session.add(Rule(**item.model_dump(mode="python")))
                else:
                    for key, value in item.model_dump(mode="python").items():
                        if key not in {"rule_id", "rule_set_id", "created_at"}:
                            setattr(current, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save rules for {rule_set_id}: {exc}") from exc

    def list_for_set(self, rule_set_id: str) -> list[RuleDTO]:
        items = self.session.scalars(
            select(Rule).where(Rule.rule_set_id == rule_set_id).order_by(Rule.priority, Rule.rule_id)
        ).all()
        return [RuleDTO.model_validate(item) for item in items]

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(Rule.rule_id))) or 0)


class RuleConflictRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_save(self, rule_set_id: str, conflicts: list[RuleConflictDTO]) -> None:
        try:
            for item in conflicts:
                existing = self.session.get(RuleConflict, item.conflict_id)
                if existing is None:
                    self.session.add(RuleConflict(**item.model_dump(mode="python")))
                else:
                    for key, value in item.model_dump(mode="python").items():
                        if key not in {"conflict_id", "created_at"}:
                            setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save rule conflicts for {rule_set_id}: {exc}") from exc

    def list_for_set(self, rule_set_id: str) -> list[RuleConflictDTO]:
        items = self.session.scalars(
            select(RuleConflict).where(RuleConflict.rule_set_id == rule_set_id)
        ).all()
        return [RuleConflictDTO.model_validate(item) for item in items]


class RuleParseRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: RuleParseRunDTO) -> RuleParseRunDTO:
        try:
            self.session.add(RuleParseRun(**item.model_dump(mode="python")))
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save rule parse run {item.parse_run_id}: {exc}") from exc
        return item

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(RuleParseRun.parse_run_id))) or 0)


class RuleParseCacheRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, cache_key: str) -> RuleParseCacheDTO | None:
        item = self.session.get(RuleParseCache, cache_key)
        return RuleParseCacheDTO.model_validate(item) if item else None

    def set(self, item: RuleParseCacheDTO) -> RuleParseCacheDTO:
        existing = self.session.get(RuleParseCache, item.cache_key)
        try:
            if existing is None:
                self.session.add(RuleParseCache(**item.model_dump(mode="python")))
            else:
                for key, value in item.model_dump(mode="python").items():
                    if key != "cache_key":
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save rule parse cache {item.cache_key}: {exc}") from exc
        return RuleParseCacheDTO.model_validate(self.session.get(RuleParseCache, item.cache_key))


class SelectionRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, selection_run_id: str) -> SelectionRunDTO | None:
        item = self.session.get(SelectionRun, selection_run_id)
        return SelectionRunDTO.model_validate(item) if item else None

    def save(self, item: SelectionRunDTO) -> SelectionRunDTO:
        existing = self.get(item.selection_run_id)
        try:
            if existing is None:
                self.session.add(SelectionRun(**item.model_dump(mode="python")))
            else:
                for key, value in item.model_dump(mode="python").items():
                    if key not in {"selection_run_id", "created_at"}:
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save selection run {item.selection_run_id}: {exc}") from exc
        return SelectionRunDTO.model_validate(self.session.get(SelectionRun, item.selection_run_id))

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(SelectionRun.selection_run_id))) or 0)


class SelectionResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_upsert(self, selection_run_id: str, items: list[VariableSelectionResultDTO]) -> None:
        if not items:
            return
        existing = {
            item.variable_id: item
            for item in self.session.scalars(
                select(VariableSelectionResult).where(
                    VariableSelectionResult.selection_run_id == selection_run_id,
                    VariableSelectionResult.variable_id.in_(
                        [item.variable_id for item in items]
                    ),
                )
            ).all()
        }
        try:
            for item in items:
                current = existing.get(item.variable_id)
                if current is None:
                    self.session.add(VariableSelectionResult(**item.model_dump(mode="python")))
                else:
                    for key, value in item.model_dump(mode="python").items():
                        if key not in {"selection_run_id", "variable_id", "created_at"}:
                            setattr(current, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save selection results for {selection_run_id}: {exc}") from exc

    def list_for_run(self, selection_run_id: str) -> list[VariableSelectionResultDTO]:
        items = self.session.scalars(
            select(VariableSelectionResult)
            .where(VariableSelectionResult.selection_run_id == selection_run_id)
            .order_by(VariableSelectionResult.overall_rank, VariableSelectionResult.variable_id)
        ).all()
        return [VariableSelectionResultDTO.model_validate(item) for item in items]

    def count_by_status(self, selection_run_id: str, status: str) -> int:
        return int(
            self.session.scalar(
                select(func.count(VariableSelectionResult.variable_id)).where(
                    VariableSelectionResult.selection_run_id == selection_run_id,
                    VariableSelectionResult.final_status == status,
                )
            )
            or 0
        )

    def list_by_status(self, selection_run_id: str, status: str) -> list[VariableSelectionResultDTO]:
        items = self.session.scalars(
            select(VariableSelectionResult)
            .where(
                VariableSelectionResult.selection_run_id == selection_run_id,
                VariableSelectionResult.final_status == status,
            )
            .order_by(VariableSelectionResult.overall_rank, VariableSelectionResult.variable_id)
        ).all()
        return [VariableSelectionResultDTO.model_validate(item) for item in items]

    def count(self) -> int:
        return int(
            self.session.scalar(select(func.count(VariableSelectionResult.variable_id))) or 0
        )


class ExportRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, export_run_id: str) -> ExportRunDTO | None:
        item = self.session.get(ExportRun, export_run_id)
        return ExportRunDTO.model_validate(item) if item else None

    def save(self, item: ExportRunDTO) -> ExportRunDTO:
        existing = self.get(item.export_run_id)
        try:
            if existing is None:
                self.session.add(ExportRun(**item.model_dump(mode="python")))
            else:
                for key, value in item.model_dump(mode="python").items():
                    if key != "created_at":
                        setattr(existing, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save export run {item.export_run_id}: {exc}") from exc
        return ExportRunDTO.model_validate(self.session.get(ExportRun, item.export_run_id))

    def count(self) -> int:
        return int(self.session.scalar(select(func.count(ExportRun.export_run_id))) or 0)


class ExportedVariableRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bulk_save(self, export_run_id: str, items: list[ExportedVariableDTO]) -> None:
        try:
            for item in items:
                self.session.add(ExportedVariable(**item.model_dump(mode="python")))
            self.session.flush()
        except SQLAlchemyError as exc:
            raise RepositoryError(f"Cannot save exported variables for {export_run_id}: {exc}") from exc

    def list_for_export(self, export_run_id: str) -> list[ExportedVariableDTO]:
        items = self.session.scalars(
            select(ExportedVariable)
            .where(ExportedVariable.export_run_id == export_run_id)
            .order_by(ExportedVariable.output_column_index)
        ).all()
        return [ExportedVariableDTO.model_validate(item) for item in items]
