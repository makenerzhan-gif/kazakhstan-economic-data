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
