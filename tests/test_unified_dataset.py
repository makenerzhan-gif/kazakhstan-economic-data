import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import unified


def test_build_wide_pivots_correctly():
    long_rows = [
        {"date": "2026-01-01", "variable": "GDP_REAL", "value": "100"},
        {"date": "2026-01-01", "variable": "CPI", "value": "5"},
        {"date": "2026-02-01", "variable": "GDP_REAL", "value": "101"},
    ]
    fieldnames, rows = unified.build_wide(long_rows)
    assert fieldnames == ["date", "CPI", "GDP_REAL"]
    row0 = next(r for r in rows if r["date"] == "2026-01-01")
    assert row0["GDP_REAL"] == "100"
    assert row0["CPI"] == "5"
    row1 = next(r for r in rows if r["date"] == "2026-02-01")
    assert row1["CPI"] == ""  # missing for that date, not fabricated


def test_long_columns_match_spec():
    expected = [
        "date", "country", "region", "frequency", "variable", "value", "unit",
        "source", "source_version", "transformation", "last_updated",
    ]
    assert unified.LONG_COLUMNS == expected
