from __future__ import annotations

import statistics
from collections import Counter

from financial_variable_curation.inspection.date_utils import parse_date_value
from financial_variable_curation.models.variable import FrequencyProfile


class FrequencyDetector:
    def detect(self, date_values: list[object]) -> FrequencyProfile:
        parsed = [parsed for value in date_values if (parsed := parse_date_value(value)) is not None]
        unique_dates = sorted({value.date() for value in parsed})
        if len(unique_dates) < 3:
            return FrequencyProfile(
                detected_frequency="unknown",
                confidence=0.0,
                reason_code="INSUFFICIENT_DATES",
                frequency_reason_codes=["INSUFFICIENT_DATES"],
                notes=["Fewer than two unique dates are available for frequency detection."],
            )

        intervals = [
            (right - left).days
            for left, right in zip(unique_dates, unique_dates[1:])
            if right > left
        ]
        if not intervals:
            return FrequencyProfile(
                detected_frequency="unknown",
                confidence=0.0,
                reason_code="DUPLICATE_ONLY_DATES",
                frequency_reason_codes=["DUPLICATE_ONLY_DATES"],
                notes=["All available dates are duplicates."],
            )

        counter = Counter(intervals)
        major_interval, major_count = counter.most_common(1)[0]
        major_ratio = major_count / len(intervals)
        median_interval = float(statistics.median(intervals))
        confidence = round(major_ratio * min(1.0, len(intervals) / 10.0), 4)

        detected, reason_code = self._classify(major_interval, median_interval, major_ratio)
        return FrequencyProfile(
            detected_frequency=detected,
            median_interval_days=round(median_interval, 2),
            major_interval_days=int(major_interval),
            major_interval_ratio=round(major_ratio, 4),
            confidence=confidence,
            reason_code=reason_code,
            frequency_reason_codes=[reason_code],
            notes=[f"major interval={major_interval} days, ratio={major_ratio:.2f}"],
        )

    @staticmethod
    def _classify(major_interval: int, median_interval: float, major_ratio: float) -> tuple[str, str]:
        if major_interval <= 2 and major_ratio >= 0.5:
            return "daily", "DAILY_INTERVALS"
        if major_interval == 7 and major_ratio >= 0.5:
            return "weekly", "WEEKLY_INTERVALS"
        if 28 <= major_interval <= 31 and (major_ratio >= 0.5 or 28 <= median_interval <= 31):
            return "monthly", "MONTHLY_INTERVALS"
        if 90 <= major_interval <= 92 and (major_ratio >= 0.5 or 90 <= median_interval <= 92):
            return "quarterly", "QUARTERLY_INTERVALS"
        if 360 <= major_interval <= 366 and (major_ratio >= 0.5 or 360 <= median_interval <= 366):
            return "annual", "ANNUAL_INTERVALS"
        return "irregular", "MIXED_INTERVALS"
