from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from financial_variable_curation.inspection.date_utils import parse_date_value
from financial_variable_curation.models.variable import VariableProfile


class PseudoFrequencyDetector:
    def detect(
        self,
        profile: VariableProfile,
        values: list[object],
        date_values: list[object],
    ) -> None:
        if profile.frequency.detected_frequency != "daily":
            return

        by_date: dict[object, object] = {}
        parsed_dates = [parse_date_value(value) for value in date_values]
        for parsed, value in zip(parsed_dates, values):
            if parsed is not None and value is not None and str(value).strip() != "":
                by_date[parsed.date()] = value
        if len(by_date) < 5:
            return

        ordered = sorted(by_date.items())
        values_ordered = [value for _, value in ordered]
        change_count = sum(
            1 for index in range(1, len(values_ordered)) if values_ordered[index] != values_ordered[index - 1]
        )
        unchanged_ratio = 1.0 - change_count / max(len(values_ordered) - 1, 1)

        monthly_values: dict[tuple[int, int], set[str]] = defaultdict(set)
        for day, value in ordered:
            monthly_values[(day.year, day.month)].add(str(value))
        monthly_change_median = statistics.median(
            [max(len(values) - 1, 0) for values in monthly_values.values()]
        )

        change_dates = [ordered[index][0] for index in range(1, len(ordered)) if values_ordered[index] != values_ordered[index - 1]]
        same_day_ratio = 0.0
        if change_dates:
            day_counter = Counter(day.day for day in change_dates)
            same_day_ratio = max(day_counter.values()) / len(change_dates)

        reasons: list[str] = []
        if monthly_change_median <= 1:
            reasons.append("MONTHLY_STABLE")
        if unchanged_ratio >= 0.8:
            reasons.append("LOW_CHANGE_RATIO")
        if same_day_ratio >= 0.8:
            reasons.append("SAME_DAY_CHANGES")

        if not reasons:
            return

        profile.is_pseudo_high_frequency = True
        profile.pseudo_frequency_confidence = round(
            max(monthly_change_median <= 1, unchanged_ratio, same_day_ratio), 4
        )
        profile.pseudo_frequency_reason = ";".join(reasons)
        profile.pseudo_frequency_reason_codes = reasons
