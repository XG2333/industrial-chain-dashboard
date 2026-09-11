from __future__ import annotations

from dataclasses import dataclass

from financial_variable_curation.inspection.date_utils import is_date_header, parse_date_value
from financial_variable_curation.models.workbook import HeaderDetection

_MAX_AUTO_SCAN_ROWS = 10
_HEADER_CONFIDENCE_THRESHOLD = 0.55


@dataclass
class TripleHeaderLayout:
    detected: bool = False
    name_row_index: int = 0
    unit_row_index: int = 1
    frequency_row_index: int = 2
    data_start_row_index: int = 3
    confidence: float = 0.0
    reason: str = "three-row metadata header not detected."
    reason_code: str = "TRIPLE_HEADER_NOT_DETECTED"


class HeaderDetector:
    def detect(self, rows: list[list[object]], explicit_header_row: int | None = None) -> HeaderDetection:
        if rows:
            max_width = max(len(row) for row in rows)
            padded_rows = [list(row) + [None] * (max_width - len(row)) for row in rows]
        else:
            padded_rows = []

        if explicit_header_row is not None:
            return self._detect_explicit(padded_rows, explicit_header_row)
        return self._detect_auto(padded_rows)

    def detect_three_row_metadata(self, rows: list[list[object]]) -> TripleHeaderLayout:
        if len(rows) < 4:
            return TripleHeaderLayout()
        first_column = [
            HeaderDetector._cell_text(row[0]) if row else None
            for row in rows[:3]
        ]
        normalized = [
            value.lower().strip() if value else ""
            for value in first_column
        ]
        if (
            normalized[0] in {"指标名称", "指标", "名称", "indicator", "variable", "name"}
            and normalized[1] in {"单位", "unit", "units"}
            and normalized[2] in {"频率", "frequency", "freq", "频次"}
        ):
            return TripleHeaderLayout(
                detected=True,
                name_row_index=0,
                unit_row_index=1,
                frequency_row_index=2,
                data_start_row_index=3,
                confidence=1.0,
                reason="detected 指标名称/单位/频率 three-row metadata header.",
                reason_code="TRIPLE_HEADER_DETECTED",
            )

        if HeaderDetector._looks_like_triple_header(rows):
            return TripleHeaderLayout(
                detected=True,
                name_row_index=0,
                unit_row_index=1,
                frequency_row_index=2,
                data_start_row_index=3,
                confidence=0.85,
                reason="detected a generic three-row metadata header with a date first column.",
                reason_code="TRIPLE_HEADER_HEURISTIC",
            )
        return TripleHeaderLayout()

    @staticmethod
    def _looks_like_triple_header(rows: list[list[object]]) -> bool:
        if len(rows) < 4:
            return False
        name_row = [value for value in rows[0] if value is not None and str(value).strip()]
        unit_row = [value for value in rows[1] if value is not None and str(value).strip()]
        frequency_row = rows[2]
        data_row = rows[3]
        if len(name_row) < 2 or len(unit_row) < 2:
            return False
        frequency_values = [
            HeaderDetector._cell_text(value)
            for value in frequency_row
        ]
        frequency_like = sum(
            1
            for value in frequency_values
            if value is not None and HeaderDetector._is_frequency_value(value)
        )
        if frequency_like < max(1, len(frequency_values) // 2):
            return False
        return any(parse_date_value(value) is not None for value in data_row)

    @staticmethod
    def _is_frequency_value(value: str) -> bool:
        normalized = value.strip().lower().replace("度", "")
        return normalized in {
            "日", "周", "月", "季", "年",
            "daily", "weekly", "monthly", "quarterly", "annual",
            "d", "w", "m", "q", "a", "y",
        }

    @staticmethod
    def _cell_text(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _detect_explicit(rows: list[list[object]], explicit_header_row: int) -> HeaderDetection:
        if explicit_header_row < 1 or explicit_header_row > len(rows):
            return HeaderDetection(
                status="NEEDS_REVIEW",
                header_row=explicit_header_row,
                confidence=0.0,
                reason=f"explicit header_row={explicit_header_row} is outside the sheet row range.",
                reason_code="HEADER_OUT_OF_RANGE",
            )
        row_index = explicit_header_row - 1
        row = rows[row_index]
        non_empty = [value for value in row if value is not None and str(value).strip() != ""]
        if not non_empty:
            return HeaderDetection(
                status="NEEDS_REVIEW",
                header_row=explicit_header_row,
                confidence=0.0,
                reason="explicit header row is empty.",
                reason_code="HEADER_EMPTY",
            )
        return HeaderDetection(
            status="DETECTED",
            header_row=explicit_header_row,
            confidence=1.0,
            reason="explicit header_row was supplied by the user.",
            reason_code="HEADER_EXPLICIT",
        )

    @staticmethod
    def _detect_auto(rows: list[list[object]]) -> HeaderDetection:
        if not rows:
            return HeaderDetection(
                status="UNSUPPORTED",
                confidence=0.0,
                reason="sheet has no rows.",
                reason_code="HEADER_UNSUPPORTED_EMPTY_SHEET",
            )

        scored: list[tuple[int, float]] = []
        for row_index in range(min(_MAX_AUTO_SCAN_ROWS, len(rows))):
            score = HeaderDetector._score_header_row(rows, row_index)
            if score > 0:
                scored.append((row_index, score))

        if not scored:
            return HeaderDetection(
                status="NEEDS_REVIEW",
                confidence=0.0,
                reason="no high-confidence header row found in the first rows.",
                reason_code="HEADER_NOT_FOUND",
            )

        scored.sort(key=lambda item: item[1], reverse=True)
        best_index, best_score = scored[0]
        if best_score < _HEADER_CONFIDENCE_THRESHOLD:
            return HeaderDetection(
                status="NEEDS_REVIEW",
                confidence=best_score,
                reason=f"best header candidate confidence {best_score:.2f} is too low.",
                reason_code="HEADER_LOW_CONFIDENCE",
            )
        if len(scored) > 1 and best_score - scored[1][1] < 0.05:
            return HeaderDetection(
                status="NEEDS_REVIEW",
                confidence=best_score,
                reason="multiple similar header candidates found; refusing to guess.",
                reason_code="HEADER_AMBIGUOUS",
            )
        return HeaderDetection(
            status="DETECTED",
            header_row=best_index + 1,
            confidence=best_score,
            reason="auto-detected from a high-confidence header row.",
            reason_code="HEADER_AUTO_DETECTED",
        )

    @staticmethod
    def _score_header_row(rows: list[list[object]], row_index: int) -> float:
        row = rows[row_index]
        non_empty = [value for value in row if value is not None and str(value).strip() != ""]
        if not non_empty:
            return 0.0

        text_values = [value for value in non_empty if isinstance(value, str)]
        text_rate = len(text_values) / len(non_empty)
        date_count = sum(1 for value in non_empty if parse_date_value(value) is not None)
        numeric_count = sum(1 for value in non_empty if isinstance(value, (int, float)) and not isinstance(value, bool))
        unique_ratio = len(set(str(value) for value in non_empty)) / len(non_empty)
        header_keyword_bonus = 0.2 if any(is_date_header(str(value)) for value in non_empty) else 0.0
        has_variable_like_text = any(isinstance(value, str) and len(str(value)) >= 2 for value in non_empty)

        score = 0.35 * text_rate + 0.20 * unique_ratio + 0.20 * header_keyword_bonus
        if has_variable_like_text:
            score += 0.20
        if numeric_count / len(non_empty) > 0.6 or date_count / len(non_empty) > 0.6:
            score -= 0.40
        if not HeaderDetector._has_data_like_rows(rows, row_index):
            score -= 0.40
        return max(score, 0.0)

    @staticmethod
    def _has_data_like_rows(rows: list[list[object]], row_index: int) -> bool:
        for row in rows[row_index + 1 : row_index + 4]:
            if any(value is not None and str(value).strip() != "" for value in row):
                return any(
                    value is not None
                    and not isinstance(value, str)
                    and str(value).strip() != ""
                    for value in row
                )
        return False
