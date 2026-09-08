from __future__ import annotations

from datetime import datetime

from financial_variable_curation.inspection.date_utils import parse_date_value
from financial_variable_curation.models.enums import DataType
from financial_variable_curation.models.variable import VariableProfile


def _is_numeric_value(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", "").strip())
            return True
        except ValueError:
            return False
    return False


class QualityAnalyzer:
    def analyze(
        self,
        profile: VariableProfile,
        values: list[object],
        date_values: list[object],
        row_count: int,
    ) -> None:
        parsed_date_values = [parse_date_value(value) for value in date_values]
        valid_date_rows = [
            index for index, parsed in enumerate(parsed_date_values) if parsed is not None
        ]
        if valid_date_rows:
            analysis_values = [values[index] for index in valid_date_rows]
            observation_count = len(valid_date_rows)
        else:
            analysis_values = values
            observation_count = row_count

        non_null = [
            value for value in analysis_values if value is not None and str(value).strip() != ""
        ]
        profile.observation_count = observation_count
        profile.row_count = row_count
        profile.non_null_count = len(non_null)
        profile.missing_count = max(observation_count - len(non_null), 0)
        profile.missing_rate = round(profile.missing_count / observation_count, 4) if observation_count else 0.0
        profile.unique_value_count = len({str(value) for value in non_null})
        profile.unique_count = profile.unique_value_count
        profile.constant = profile.unique_value_count == 1
        profile.is_constant = profile.constant
        profile.all_empty = profile.non_null_count == 0
        profile.is_empty_column = profile.all_empty
        profile.is_empty = profile.all_empty
        profile.time_coverage = round(profile.non_null_count / observation_count, 4) if observation_count else 0.0
        profile.date_aligned_observation_count = profile.non_null_count if valid_date_rows else 0
        profile.numeric_parse_success_rate = round(
            sum(1 for value in non_null if _is_numeric_value(value)) / len(non_null), 4
        ) if non_null else 0.0

        self._detect_types(profile, non_null)
        self._analyze_dates(profile, values, parsed_date_values)
        profile.quality_score = self._quality_score(profile)

    @staticmethod
    def _detect_types(profile: VariableProfile, non_null: list[object]) -> None:
        if not non_null:
            profile.data_type = DataType.EMPTY
            return
        date_count = sum(1 for value in non_null if parse_date_value(value) is not None)
        numeric_count = sum(
            1 for value in non_null if parse_date_value(value) is None and _is_numeric_value(value)
        )
        boolean_count = sum(1 for value in non_null if isinstance(value, bool))
        text_count = sum(1 for value in non_null if not isinstance(value, bool) and not _is_numeric_value(value) and parse_date_value(value) is None)
        total = len(non_null)
        profile.numeric_rate = round(numeric_count / total, 4)
        profile.date_parse_rate = round(date_count / total, 4)
        profile.text_rate = round(text_count / total, 4)

        if profile.date_parse_rate >= 0.9:
            profile.data_type = DataType.DATE
        elif profile.numeric_rate >= 0.9:
            profile.data_type = DataType.NUMERIC
        elif boolean_count / total >= 0.9:
            profile.data_type = DataType.BOOLEAN
        elif profile.text_rate >= 0.9:
            profile.data_type = DataType.TEXT
        else:
            profile.data_type = DataType.MIXED

    @staticmethod
    def _analyze_dates(
        profile: VariableProfile,
        values: list[object],
        parsed_date_values: list[object],
    ) -> None:
        parsed_dates = [value for value in parsed_date_values if value is not None]
        if not parsed_dates:
            return
        date_objects = [value.date() for value in parsed_dates]
        start = min(date_objects)
        end = max(date_objects)
        profile.start_date = start
        profile.end_date = end
        profile.coverage_days = (end - start).days + 1
        profile.duplicate_date_count = len(date_objects) - len(set(date_objects))

        observation_dates = [
            parsed.date()
            for parsed, value in zip(parsed_date_values, values)
            if parsed is not None and value is not None and str(value).strip() != ""
        ]
        if observation_dates:
            profile.latest_observation_date = max(observation_dates)
            profile.latest_gap_days = max((end - profile.latest_observation_date).days, 0)

    @staticmethod
    def _quality_score(profile: VariableProfile) -> float:
        if profile.all_empty:
            return 0.0
        if profile.constant:
            return 10.0
        completeness = 60.0 * (1.0 - profile.missing_rate)
        usability = 20.0 * max(profile.numeric_rate, profile.date_parse_rate)
        uniqueness = 10.0 if profile.unique_value_count > 1 else 0.0
        coverage = 10.0 * (1.0 - profile.missing_rate)
        return round(completeness + usability + uniqueness + coverage, 2)
