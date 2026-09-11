from __future__ import annotations

from collections import Counter
from datetime import date, datetime

from financial_variable_curation.inspection.date_utils import date_format_signature, is_date_header, parse_date_value
from financial_variable_curation.inspection.workbook_profiler import ColumnData
from financial_variable_curation.models.workbook import DateCandidate, DateDetection


class DateDetector:
    def detect(
        self,
        columns: list[ColumnData],
        explicit_date_column: str | None = None,
    ) -> DateDetection:
        candidates: list[DateCandidate] = []
        for column in columns:
            candidate = self._score_column(column)
            if candidate is not None:
                candidates.append(candidate)

        if explicit_date_column is not None:
            return self._select_explicit(columns, candidates, explicit_date_column)

        high_confidence = [
            candidate
            for candidate in candidates
            if candidate.confidence >= 0.65 and candidate.date_parse_rate >= 0.8
        ]
        if len(high_confidence) == 1:
            selected = high_confidence[0]
            if self._has_severe_mixed_formats(selected, columns):
                return DateDetection(
                    status="NEEDS_REVIEW",
                    candidates=candidates,
                    confidence=selected.confidence,
                    reason="date column has severely mixed formats; refusing to guess.",
                    reason_codes=["DATE_MIXED_FORMAT"],
                )
            return DateDetection(
                status="DETECTED",
                selected_column=selected.header,
                selected_column_index=selected.column_index,
                candidates=candidates,
                confidence=selected.confidence,
                reason="single high-confidence date column detected.",
                reason_codes=["DATE_SINGLE_CANDIDATE"],
            )
        if len(high_confidence) > 1:
            return DateDetection(
                status="NEEDS_REVIEW",
                candidates=candidates,
                confidence=max(candidate.confidence for candidate in high_confidence),
                reason="multiple possible date columns detected; refusing to choose automatically.",
                reason_codes=["DATE_MULTIPLE_CANDIDATES"],
            )
        if candidates:
            return DateDetection(
                status="NEEDS_REVIEW",
                candidates=candidates,
                confidence=max(candidate.confidence for candidate in candidates),
                reason="date-like columns exist but no high-confidence date column could be determined.",
                reason_codes=["DATE_LOW_CONFIDENCE"],
            )
        return DateDetection(
            status="NO_DATE_COLUMN",
            confidence=0.0,
            reason="no date-like column detected.",
            reason_codes=["DATE_NO_COLUMN"],
        )

    @staticmethod
    def _select_explicit(
        columns: list[ColumnData],
        candidates: list[DateCandidate],
        explicit_date_column: str,
    ) -> DateDetection:
        target = None
        for column in columns:
            if column.header == explicit_date_column or str(column.index + 1) == explicit_date_column:
                target = column
                break
        if target is None:
            return DateDetection(
                status="NEEDS_REVIEW",
                candidates=candidates,
                reason=f"explicit date column '{explicit_date_column}' was not found.",
                reason_codes=["DATE_EXPLICIT_NOT_FOUND"],
            )

        candidate = next((item for item in candidates if item.column_index == target.index), None)
        if candidate is None or candidate.date_parse_rate < 0.6:
            return DateDetection(
                status="NEEDS_REVIEW",
                candidates=candidates,
                reason=f"explicit date column '{explicit_date_column}' is not reliably parseable.",
                reason_codes=["DATE_EXPLICIT_NOT_PARSEABLE"],
            )
        if DateDetector._has_severe_mixed_formats(candidate, columns):
            return DateDetection(
                status="NEEDS_REVIEW",
                candidates=candidates,
                confidence=candidate.confidence,
                reason="explicit date column has severely mixed formats.",
                reason_codes=["DATE_MIXED_FORMAT"],
            )
        return DateDetection(
            status="DETECTED",
            selected_column=target.header,
            selected_column_index=target.index,
            candidates=candidates,
            confidence=candidate.confidence,
            reason="date column selected by explicit user argument.",
            reason_codes=["DATE_EXPLICIT"],
        )

    @staticmethod
    def _score_column(column: ColumnData) -> DateCandidate | None:
        non_null = [value for value in column.values if value is not None and str(value).strip() != ""]
        if len(non_null) < 2:
            return None

        parsed_pairs = []
        for value in non_null:
            parsed = parse_date_value(value)
            if parsed is not None:
                parsed_pairs.append(parsed)
        if not parsed_pairs:
            return None

        parseable_ratio = len(parsed_pairs) / len(non_null)
        if parseable_ratio < 0.3:
            return None

        date_type_ratio = sum(1 for value in non_null if isinstance(value, (date, datetime))) / len(non_null)
        ordered = [parsed.date() for parsed in parsed_pairs]
        sorted_ordered = sorted(ordered)
        sorted_ratio = sum(left == right for left, right in zip(ordered, sorted_ordered)) / len(ordered)
        unique_ratio = len(set(ordered)) / len(ordered)
        coverage_days = (max(ordered) - min(ordered)).days + 1 if len(ordered) >= 2 else 1
        header_bonus = 0.20 if is_date_header(column.header) else 0.0
        confidence = (
            0.20 * date_type_ratio
            + 0.30 * parseable_ratio
            + 0.15 * sorted_ratio
            + 0.15 * unique_ratio
            + 0.20 * header_bonus
        )
        if coverage_days >= 5:
            confidence = min(confidence + 0.05, 1.0)
        return DateCandidate(
            column_index=column.index,
            header=column.header,
            confidence=round(confidence, 4),
            date_type_ratio=round(date_type_ratio, 4),
            date_parse_rate=round(parseable_ratio, 4),
            sorted_ratio=round(sorted_ratio, 4),
            unique_ratio=round(unique_ratio, 4),
            coverage_days=coverage_days,
            reason="date-like values detected.",
            reason_code="DATE_CANDIDATE",
        )

    @staticmethod
    def _has_severe_mixed_formats(candidate: DateCandidate, columns: list[ColumnData]) -> bool:
        column = next((item for item in columns if item.index == candidate.column_index), None)
        if column is None:
            return False
        non_null = [value for value in column.values if value is not None and str(value).strip() != ""]
        parsed_values = [value for value in non_null if parse_date_value(value) is not None]
        signatures = Counter(date_format_signature(value) for value in parsed_values)
        return len(signatures) >= 3
