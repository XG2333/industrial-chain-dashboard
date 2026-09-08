# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

from scripts.apply_indicator_tags import _extract_frequency
from scripts.catalog_utils import column_freq, resolve_annualized_frequency
from scripts.lithium_rules import detect_indicator_freq as lithium_detect
from scripts.lithium_selection_rules import actual_frequency as lithium_actual
from scripts.silicon_selection_rules import actual_frequency as silicon_actual
from scripts.tin_rules import detect_indicator_freq as tin_detect


def test_annualized_frequency_override() -> None:
    name = "SMM: 干法隔膜年化产能-预测值: 月度"
    assert resolve_annualized_frequency(name) == "年度"
    assert lithium_detect(name, "月度") == "年度"
    assert tin_detect(name, "月度") == "年度"
    assert lithium_actual(name, "月度") == "年度"
    assert silicon_actual(name, "月度") == "年度"
    assert _extract_frequency("年度", name) == "年度"


def test_plain_monthly_name_not_overridden() -> None:
    name = "SMM: 干法隔膜产能: 月度"
    assert resolve_annualized_frequency(name) is None
    assert lithium_detect(name, "月度") == "月度"


def test_column_freq_uses_annualized_override() -> None:
    df = pd.DataFrame(
        [
            ["指标名称", "SMM: 干法隔膜年化产能-预测值: 月度"],
            ["单位", "万平方米"],
            ["频率", "月"],
            ["2026-07-31", "1025400"],
        ]
    )
    assert column_freq(df, 2, 1, "SMM: 干法隔膜年化产能-预测值: 月度", "年度") == "年度"
