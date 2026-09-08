from financial_variable_curation.pipeline.inspect import run_inspection


def test_inspection_detects_dates_variables_and_quality(sample_workbook) -> None:
    result = run_inspection(sample_workbook)
    names = {profile.column_name for profile in result.variable_profiles}
    assert "close_price" in names
    assert "constant_col" in names
    assert "empty_col" in names
    assert "date" not in names

    profiles = {profile.column_name: profile for profile in result.variable_profiles}
    assert profiles["empty_col"].all_empty is True
    assert profiles["constant_col"].constant is True
    assert profiles["high_missing"].missing_rate > 0.9
    assert profiles["close_price"].classification.category == "UNCLASSIFIED"
    assert profiles["close_price"].frequency.detected_frequency == "daily"
    assert profiles["close_price"].variable_id
    assert result.workbook_profile.file_hash


def test_inspection_review_list_is_populated(sample_workbook) -> None:
    result = run_inspection(sample_workbook)
    review_names = {profile.column_name for profile in result.needs_review_variables}
    assert "empty_col" in review_names
    assert "constant_col" in review_names
    assert "high_missing" in review_names
