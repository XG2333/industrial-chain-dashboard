from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter

from financial_variable_curation.inspection.frequency_detector import FrequencyDetector
from financial_variable_curation.inspection.pseudo_frequency_detector import PseudoFrequencyDetector
from financial_variable_curation.inspection.quality_analyzer import QualityAnalyzer
from financial_variable_curation.inspection.workbook_profiler import ColumnData
from financial_variable_curation.models.variable import FrequencyProfile, VariableProfile
from financial_variable_curation.models.workbook import DateDetection

_COMMENT_HEADER_TOKENS = (
    "备注",
    "说明",
    "注释",
    "note",
    "comment",
    "description",
)


def make_unique_headers(headers: list[object]) -> list[str]:
    normalized = [str(value) if value is not None else f"Column{index + 1}" for index, value in enumerate(headers)]
    counts: Counter[str] = Counter()
    unique: list[str] = []
    for index, header in enumerate(normalized):
        counts[header] += 1
        if counts[header] == 1:
            unique.append(header)
        else:
            unique.append(f"{header}__col_{index + 1}")
    return unique


class VariableExtractor:
    def __init__(self) -> None:
        self.quality_analyzer = QualityAnalyzer()
        self.frequency_detector = FrequencyDetector()
        self.pseudo_frequency_detector = PseudoFrequencyDetector()

    def extract(
        self,
        sheet_name: str,
        columns: list[ColumnData],
        date_detection: DateDetection,
        file_name: str,
        file_hash: str | None,
        date_values: list[object],
        row_count: int,
        sheet_index: int = 0,
        unit_by_column: dict[int, str | None] | None = None,
        declared_frequency_by_column: dict[int, str | None] | None = None,
    ) -> list[VariableProfile]:
        selected_date_index = date_detection.selected_column_index
        profiles: list[VariableProfile] = []
        for column in columns:
            if column.index == selected_date_index:
                continue
            declared_frequency = self._normalize_declared_frequency(
                (declared_frequency_by_column or {}).get(column.index)
            )
            unit_hint = self._extract_unit_hint(column.header)
            explicit_unit = (unit_by_column or {}).get(column.index)
            if explicit_unit:
                unit_hint = explicit_unit
            profile = VariableProfile(
                variable_id=self._stable_variable_id(file_hash, sheet_name, column.index, column.header),
                file_name=file_name,
                file_hash=file_hash,
                sheet_name=sheet_name,
                sheet_index=sheet_index,
                column_index=column.index,
                column_position=column.index,
                column_name=column.header,
                original_header=column.header,
                original_name=column.header,
                normalized_header=self._normalize_header(column.header),
                normalized_name=self._normalize_header(column.header),
                column_letter=self._column_letter(column.index),
                date_column_name=date_detection.selected_column,
                unit_hint=unit_hint,
                declared_frequency=declared_frequency,
                is_comment_column=self._is_comment_header(column.header),
            )
            self.quality_analyzer.analyze(profile, column.values, date_values, row_count)
            profile.inferred_data_type = profile.data_type.value
            profile.is_empty = profile.all_empty
            profile.is_numeric_candidate = (
                profile.data_type.value in {"NUMERIC", "BOOLEAN"}
                or profile.numeric_parse_success_rate >= 0.8
            )
            profile.is_text_description = profile.is_comment_column or (
                profile.data_type.value == "TEXT" and profile.text_rate >= 0.8
            )
            profile.is_valid_variable = not profile.is_comment_column and not profile.all_empty
            actual_frequency = self.frequency_detector.detect(date_values)
            profile.frequency = actual_frequency
            if declared_frequency:
                profile.declared_frequency = declared_frequency
                profile.frequency = FrequencyProfile(
                    detected_frequency=declared_frequency,
                    confidence=1.0,
                    reason_code="DECLARED_FREQUENCY",
                    frequency_reason_codes=["DECLARED_FREQUENCY"],
                    notes=[
                        "Declared frequency from the metadata row is authoritative. "
                        f"Actual date interval detection returned {actual_frequency.detected_frequency}."
                    ],
                )
                profile.inferred_frequency = declared_frequency.upper()
            elif actual_frequency.detected_frequency not in {"unknown", "irregular"}:
                profile.inferred_frequency = actual_frequency.detected_frequency.upper()
            self.pseudo_frequency_detector.detect(profile, column.values, date_values)
            profile.review_reasons = self._review_reasons(profile)
            profile.profile_status = "NEEDS_REVIEW" if profile.review_reasons else "PROCESSED"
            profiles.append(profile)
        return profiles

    @staticmethod
    def _normalize_header(header: str) -> str:
        normalized = unicodedata.normalize("NFKC", header).strip().lower()
        return re.sub(r"\s+", "_", normalized)

    @staticmethod
    def _extract_unit_hint(header: str) -> str | None:
        match = re.search(r"[(（]([^)）]+)[)）]", header)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _normalize_declared_frequency(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower().replace("度", "")
        aliases = {
            "日": "daily",
            "daily": "daily",
            "d": "daily",
            "周": "weekly",
            "weekly": "weekly",
            "w": "weekly",
            "月": "monthly",
            "monthly": "monthly",
            "m": "monthly",
            "季": "quarterly",
            "quarterly": "quarterly",
            "q": "quarterly",
            "年": "annual",
            "annual": "annual",
            "a": "annual",
            "y": "annual",
        }
        return aliases.get(normalized)

    @staticmethod
    def _is_comment_header(header: str) -> bool:
        lowered = header.lower()
        return any(token in lowered for token in _COMMENT_HEADER_TOKENS)

    @staticmethod
    def _stable_variable_id(
        file_hash: str | None,
        sheet_name: str,
        column_index: int,
        header: str,
    ) -> str:
        payload = f"{file_hash or 'unknown'}|{sheet_name}|{column_index}|{header}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _column_letter(column_index: int) -> str:
        letters = ""
        number = column_index + 1
        while number > 0:
            number, remainder = divmod(number - 1, 26)
            letters = chr(65 + remainder) + letters
        return letters

    @staticmethod
    def _review_reasons(profile: VariableProfile) -> list[str]:
        reasons: list[str] = []
        if profile.all_empty:
            reasons.append("EMPTY_COLUMN")
        if profile.constant:
            reasons.append("CONSTANT_COLUMN")
        if profile.missing_rate > 0.5:
            reasons.append("HIGH_MISSING_RATE")
        if profile.is_comment_column:
            reasons.append("TEXT_DESCRIPTION")
        if profile.is_pseudo_high_frequency:
            reasons.append("PSEUDO_HIGH_FREQUENCY")
        return reasons
