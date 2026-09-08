from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from financial_variable_curation.inspection.date_detector import DateDetector
from financial_variable_curation.inspection.exceptions import InspectionError
from financial_variable_curation.inspection.file_validator import FileValidator
from financial_variable_curation.inspection.header_detector import HeaderDetector
from financial_variable_curation.inspection.variable_extractor import VariableExtractor, make_unique_headers
from financial_variable_curation.inspection.workbook_profiler import ColumnData, WorkbookProfiler
from financial_variable_curation.models.artifacts import DataQualityReport, InspectionSummary
from financial_variable_curation.models.inspection import InspectionResult
from financial_variable_curation.models.variable import VariableProfile
from financial_variable_curation.models.workbook import HeaderDetection, SheetProfile, WorkbookProfile


class InspectionService:
    def __init__(self) -> None:
        self.file_validator = FileValidator()
        self.workbook_profiler = WorkbookProfiler()
        self.header_detector = HeaderDetector()
        self.date_detector = DateDetector()
        self.variable_extractor = VariableExtractor()

    def inspect(
        self,
        input_path: str | Path,
        header_row: int | None = None,
        date_column: str | None = None,
        run_id: str = "inspect",
        sheet_filter: str | None = None,
    ) -> InspectionResult:
        started_at = datetime.now(timezone.utc)
        validation = self.file_validator.validate(input_path)
        if not validation.valid:
            raise InspectionError("; ".join(validation.errors))

        raw = self.workbook_profiler.profile(input_path, validation.file_hash)
        if sheet_filter is not None and sheet_filter not in [sheet.sheet_name for sheet in raw.sheets]:
            raise InspectionError(f"Sheet '{sheet_filter}' was not found in the workbook.")

        sheet_profiles: list[SheetProfile] = []
        all_profiles: list[VariableProfile] = []

        for sheet_index, raw_sheet in enumerate(raw.sheets):
            if sheet_filter is not None and raw_sheet.sheet_name != sheet_filter:
                continue
            sheet_profile, profiles = self._inspect_sheet(
                raw_sheet,
                header_row,
                date_column,
                raw,
                sheet_index=sheet_index,
            )
            sheet_profiles.append(sheet_profile)
            all_profiles.extend(profiles)

        completed_at = datetime.now(timezone.utc)
        workbook_profile = WorkbookProfile(
            workbook_path=str(Path(input_path).resolve()),
            run_id=run_id,
            file_name=raw.file_name,
            file_path=raw.file_path,
            file_hash=raw.file_hash,
            file_size_bytes=raw.file_size_bytes,
            sheet_count=len(sheet_profiles),
            sheet_names=[sheet.sheet_name for sheet in sheet_profiles],
            empty_sheet_count=sum(1 for sheet in sheet_profiles if sheet.empty_sheet),
            sheets=sheet_profiles,
            total_rows=sum(sheet.row_count for sheet in sheet_profiles),
            total_columns=sum(sheet.column_count for sheet in sheet_profiles),
            inspection_started_at=started_at,
            inspection_completed_at=completed_at,
            generated_at=completed_at,
            status="COMPLETED",
            notes=["Inspection is deterministic and does not call an LLM."],
        )

        frequency_counts = Counter(profile.frequency.detected_frequency for profile in all_profiles)
        needs_review = [
            profile
            for profile in all_profiles
            if profile.review_reasons
            or not profile.is_valid_variable
            or profile.missing_rate > 0.5
            or profile.constant
            or profile.all_empty
            or profile.is_pseudo_high_frequency
        ]
        summary = InspectionSummary(
            run_id=run_id,
            input_file=str(Path(input_path).resolve()),
            file_hash=raw.file_hash,
            status="COMPLETED",
            sheets_processed=len(sheet_profiles),
            sheets_successful=sum(1 for sheet in sheet_profiles if sheet.status == "PROCESSED"),
            sheets_needs_review=sum(1 for sheet in sheet_profiles if sheet.status == "NEEDS_REVIEW"),
            sheets_unsupported=sum(1 for sheet in sheet_profiles if sheet.status == "UNSUPPORTED"),
            raw_column_count=sum(sheet.column_count for sheet in sheet_profiles),
            total_variables=len(all_profiles),
            valid_variables=sum(1 for profile in all_profiles if profile.is_valid_variable),
            empty_columns=sum(1 for profile in all_profiles if profile.all_empty),
            constant_columns=sum(1 for profile in all_profiles if profile.constant),
            comment_columns=sum(1 for profile in all_profiles if profile.is_comment_column),
            text_description_columns=sum(1 for profile in all_profiles if profile.is_text_description),
            daily_count=frequency_counts.get("daily", 0),
            weekly_count=frequency_counts.get("weekly", 0),
            monthly_count=frequency_counts.get("monthly", 0),
            quarterly_count=frequency_counts.get("quarterly", 0),
            annual_count=frequency_counts.get("annual", 0),
            irregular_count=frequency_counts.get("irregular", 0),
            unknown_count=frequency_counts.get("unknown", 0),
            other_frequency_count=max(
                len(all_profiles)
                - sum(frequency_counts.get(frequency, 0) for frequency in ("daily", "weekly", "monthly", "quarterly", "annual", "irregular", "unknown")),
                0,
            ),
            pseudo_high_frequency_count=sum(1 for profile in all_profiles if profile.is_pseudo_high_frequency),
            review_variable_count=len(needs_review),
            detected_frequencies=dict(frequency_counts),
            notes=[
                "No LLM, rule parsing, or final variable selection was executed.",
                "Frequency detection uses declared frequency rows when present, otherwise actual date intervals.",
            ],
        )

        quality_report = DataQualityReport(
            run_id=run_id,
            total_variables=len(all_profiles),
            empty_columns=summary.empty_columns,
            constant_columns=summary.constant_columns,
            high_missing_columns=sum(1 for profile in all_profiles if profile.missing_rate > 0.5),
            needs_review_columns=len(needs_review),
            quality_score_mean=round(
                sum(profile.quality_score for profile in all_profiles) / len(all_profiles), 2
            )
            if all_profiles
            else 0.0,
            notes=[
                "Quality metrics are deterministic and independent of business rules.",
                "Inspect mode does not perform semantic classification.",
            ],
        )

        return InspectionResult(
            workbook_profile=workbook_profile,
            variable_profiles=all_profiles,
            data_quality_report=quality_report,
            needs_review_variables=needs_review,
            inspection_summary=summary,
        )

    def _inspect_sheet(
        self,
        raw_sheet,
        header_row: int | None,
        date_column: str | None,
        raw_workbook,
        sheet_index: int = 0,
    ) -> tuple[SheetProfile, list[VariableProfile]]:
        triple_header = self.header_detector.detect_three_row_metadata(raw_sheet.rows)
        if triple_header.detected:
            return self._inspect_three_row_sheet(
                raw_sheet,
                date_column,
                raw_workbook,
                triple_header,
                sheet_index,
            )
        header_detection = self.header_detector.detect(raw_sheet.rows, header_row)
        issues: list[str] = []
        review_reasons: list[str] = []
        if header_detection.status != "DETECTED":
            issues.append(header_detection.reason or "header detection failed.")
            review_reasons.append(header_detection.reason_code or "HEADER_NEEDS_REVIEW")
            status = "UNSUPPORTED" if header_detection.status == "UNSUPPORTED" else "NEEDS_REVIEW"
            sheet_profile = SheetProfile(
                sheet_name=raw_sheet.sheet_name,
                sheet_index=sheet_index,
                row_count=0,
                column_count=raw_sheet.column_count,
                metadata_row_count=1,
                empty_sheet=raw_sheet.empty_sheet,
                detected_header_row=None,
                header_confidence=header_detection.confidence,
                variable_column_count=0,
                status=status,
                review_reasons=review_reasons,
                header_detection=header_detection,
                issues=issues,
            )
            return sheet_profile, []

        header_index = header_detection.header_row - 1
        headers = make_unique_headers(raw_sheet.rows[header_index])
        data_rows = raw_sheet.rows[header_index + 1 :]
        row_count = len(data_rows)
        columns = [
            ColumnData(
                index=index,
                header=headers[index] if index < len(headers) else f"Column{index + 1}",
                values=[row[index] if index < len(row) else None for row in data_rows],
            )
            for index in range(max(len(headers), raw_sheet.column_count))
        ]
        date_detection = self.date_detector.detect(columns, date_column)
        if date_detection.status in {"NEEDS_REVIEW", "UNSUPPORTED"}:
            issues.append(date_detection.reason or "date column detection failed.")
            review_reasons.extend(date_detection.reason_codes or ["DATE_NEEDS_REVIEW"])

        selected_date_index = date_detection.selected_column_index
        date_values = columns[selected_date_index].values if selected_date_index is not None else []
        profiles = self.variable_extractor.extract(
            sheet_name=raw_sheet.sheet_name,
            columns=columns,
            date_detection=date_detection,
            file_name=raw_workbook.file_name,
            file_hash=raw_workbook.file_hash,
            date_values=date_values,
            row_count=row_count,
            sheet_index=sheet_index,
        )
        if not profiles and not issues:
            issues.append("No variable columns were extracted.")
        if review_reasons:
            status = "UNSUPPORTED" if date_detection.status == "UNSUPPORTED" else "NEEDS_REVIEW"
        else:
            status = "PROCESSED"

        sheet_profile = SheetProfile(
            sheet_name=raw_sheet.sheet_name,
            sheet_index=sheet_index,
            row_count=row_count,
            column_count=raw_sheet.column_count,
            metadata_row_count=header_detection.header_row or 1,
            empty_sheet=raw_sheet.empty_sheet or row_count == 0,
            detected_header_row=header_detection.header_row,
            header_confidence=header_detection.confidence,
            selected_date_column=date_detection.selected_column,
            date_column_confidence=date_detection.confidence,
            variable_column_count=len(profiles),
            status=status,
            review_reasons=review_reasons,
            header_detection=header_detection,
            date_detection=date_detection,
            date_column_candidates=[candidate.header for candidate in date_detection.candidates],
            date_column_indices=[candidate.column_index for candidate in date_detection.candidates],
            variable_columns=[profile.column_name for profile in profiles],
            issues=issues,
            header=headers,
        )
        return sheet_profile, profiles

    def _inspect_three_row_sheet(
        self,
        raw_sheet,
        date_column: str | None,
        raw_workbook,
        layout,
        sheet_index: int,
    ) -> tuple[SheetProfile, list[VariableProfile]]:
        headers = make_unique_headers(raw_sheet.rows[layout.name_row_index])
        unit_row = (
            raw_sheet.rows[layout.unit_row_index]
            if len(raw_sheet.rows) > layout.unit_row_index
            else []
        )
        frequency_row = (
            raw_sheet.rows[layout.frequency_row_index]
            if len(raw_sheet.rows) > layout.frequency_row_index
            else []
        )
        data_rows = raw_sheet.rows[layout.data_start_row_index :]
        row_count = len(data_rows)
        columns = [
            ColumnData(
                index=index,
                header=headers[index] if index < len(headers) else f"Column{index + 1}",
                values=[row[index] if index < len(row) else None for row in data_rows],
            )
            for index in range(max(len(headers), raw_sheet.column_count))
        ]
        explicit_date_column = date_column or (headers[0] if headers else None)
        date_detection = self.date_detector.detect(columns, explicit_date_column)
        issues: list[str] = []
        review_reasons: list[str] = []
        if date_detection.status in {"NEEDS_REVIEW", "UNSUPPORTED"}:
            issues.append(date_detection.reason or "date column detection failed.")
            review_reasons.extend(date_detection.reason_codes or ["DATE_NEEDS_REVIEW"])

        selected_date_index = date_detection.selected_column_index
        date_values = columns[selected_date_index].values if selected_date_index is not None else []
        unit_by_column: dict[int, str | None] = {}
        frequency_by_column: dict[int, str | None] = {}
        for index in range(len(headers)):
            unit_by_column[index] = (
                self._cell_text(unit_row[index]) if index < len(unit_row) else None
            )
            frequency_by_column[index] = (
                self._cell_text(frequency_row[index]) if index < len(frequency_row) else None
            )
        profiles = self.variable_extractor.extract(
            sheet_name=raw_sheet.sheet_name,
            columns=columns,
            date_detection=date_detection,
            file_name=raw_workbook.file_name,
            file_hash=raw_workbook.file_hash,
            date_values=date_values,
            row_count=row_count,
            sheet_index=sheet_index,
            unit_by_column=unit_by_column,
            declared_frequency_by_column=frequency_by_column,
        )
        if not profiles and not issues:
            issues.append("No variable columns were extracted.")
        status = "UNSUPPORTED" if date_detection.status == "UNSUPPORTED" else "NEEDS_REVIEW"
        if review_reasons:
            status = status
        else:
            status = "PROCESSED"
        sheet_profile = SheetProfile(
            sheet_name=raw_sheet.sheet_name,
            sheet_index=sheet_index,
            row_count=row_count,
            column_count=raw_sheet.column_count,
            metadata_row_count=layout.data_start_row_index,
            empty_sheet=raw_sheet.empty_sheet or row_count == 0,
            detected_header_row=layout.name_row_index + 1,
            header_confidence=layout.confidence,
            selected_date_column=date_detection.selected_column,
            date_column_confidence=date_detection.confidence,
            variable_column_count=len(profiles),
            status=status,
            review_reasons=review_reasons,
            header_detection=HeaderDetection(
                status="DETECTED",
                header_row=layout.name_row_index + 1,
                confidence=layout.confidence,
                reason=layout.reason,
                reason_code=layout.reason_code,
            ),
            date_detection=date_detection,
            date_column_candidates=[candidate.header for candidate in date_detection.candidates],
            date_column_indices=[candidate.column_index for candidate in date_detection.candidates],
            variable_columns=[profile.column_name for profile in profiles],
            issues=issues,
            header=headers,
        )
        return sheet_profile, profiles

    @staticmethod
    def _cell_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
