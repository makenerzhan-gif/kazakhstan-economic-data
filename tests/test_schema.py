import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import validation


def test_validate_schema_flags_missing_columns():
    records = [{"period": "2026-01", "val": 1}]
    result = validation.validate_schema(records, "TEST")
    assert not result.ok
    assert "date" in str(result.errors)


def test_validate_schema_empty_dataset():
    result = validation.validate_schema([], "TEST")
    assert not result.ok


def test_validate_types_catches_bad_date_and_value():
    records = [{"date": "not-a-date", "value": "abc"}]
    result = validation.validate_types(records, "TEST")
    assert not result.ok
    assert len(result.errors) == 2


def test_validate_missing_and_duplicates():
    records = [
        {"date": "2026-01-01", "value": 1},
        {"date": "2026-01-01", "value": 2},
        {"date": "2026-02-01", "value": None},
    ]
    result = validation.validate_missing_and_duplicates(records, "TEST")
    assert not result.ok  # duplicate date
    assert any("missing value" in w for w in result.warnings)


def test_validate_no_impossible_values():
    records = [{"date": "2026-01-01", "value": -5}]
    result = validation.validate_no_impossible_values(records, "TEST", min_value=0)
    assert not result.ok


def test_check_structural_change_raises_with_full_context():
    try:
        validation.check_structural_change({"date", "value"}, {"date", "amount"}, "bns/gdp")
    except validation.StructuralChangeError as exc:
        msg = str(exc)
        assert "WHAT CHANGED" in msg and "EXPECTED" in msg and "ACTUAL" in msg and "ACTION REQUIRED" in msg
    else:
        raise AssertionError("expected StructuralChangeError")


def test_run_all_ok_case():
    records = [{"date": "2026-01-01", "value": 1.0}, {"date": "2026-02-01", "value": 1.1}]
    result = validation.run_all(records, "TEST", expected_frequency="monthly")
    assert result.ok


def test_validate_outliers_flags_real_jump():
    records = [{"date": "2026-01-01", "value": 100.0}, {"date": "2026-02-01", "value": 200.0}]
    result = validation.validate_outliers(records, "TEST")
    assert any("Unexpected jump" in w for w in result.warnings)


def test_validate_outliers_year_to_date_ignores_the_january_reset():
    records = [
        {"date": "2026-01-01", "value": 100.0},
        {"date": "2026-04-01", "value": 210.0},
        {"date": "2026-07-01", "value": 320.0},
        {"date": "2026-10-01", "value": 430.0},
        {"date": "2027-01-01", "value": 105.0},  # reset: raw drop of ~76%, not a real jump
    ]
    result = validation.validate_outliers(records, "TEST", cumulation="year_to_date")
    assert result.warnings == []


def test_validate_outliers_year_to_date_still_catches_a_real_anomaly():
    records = [
        {"date": "2026-01-01", "value": 100.0},
        {"date": "2026-04-01", "value": 210.0},   # own-period contribution: 110
        {"date": "2026-07-01", "value": 900.0},   # own-period contribution: 690 -- genuine spike
        {"date": "2026-10-01", "value": 1010.0},  # own-period contribution: 110
    ]
    result = validation.validate_outliers(records, "TEST", cumulation="year_to_date")
    assert any("own-period contribution" in w for w in result.warnings)
