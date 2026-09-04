import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import timeseries  # noqa: E402


def _long_df(indicator_id: str, rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [d for d, _ in rows],
        "variable": [indicator_id] * len(rows),
        "value": [v for _, v in rows],
    })


def test_prepare_level_returns_level_as_is_for_a_plain_series():
    long_df = _long_df("TEST_LEVEL", [("2026-01-01", 100.0), ("2026-02-01", 110.0)])
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    s, desc = timeseries.prepare_level("TEST_LEVEL", meta, long_df)
    assert list(s.values) == [100.0, 110.0]  # unchanged -- no growth_rate applied
    assert "level as published" in desc


def test_prepare_level_decumulates_before_returning():
    long_df = _long_df("TEST_YTD", [
        ("2026-01-01", 100.0), ("2026-04-01", 210.0),
        ("2026-07-01", 320.0), ("2026-10-01", 430.0),
    ])
    meta = {"frequency": "quarterly", "observation_type": "period_total", "cumulation": "year_to_date"}
    s, desc = timeseries.prepare_level("TEST_YTD", meta, long_df)
    assert list(s.values) == pytest.approx([100.0, 110.0, 110.0, 110.0])
    assert "de-cumulated" in desc


def test_prepare_level_raises_for_lifecycle_without_acknowledgement():
    long_df = _long_df("TEST_STALE", [("2026-01-01", 1.0), ("2026-02-01", 2.0)])
    meta = {"frequency": "monthly", "observation_type": "point_in_time", "lifecycle": "stale_source"}
    with pytest.raises(timeseries.SeriesGuardrailError, match="lifecycle"):
        timeseries.prepare_level("TEST_STALE", meta, long_df)


def test_prepare_level_allows_lifecycle_when_acknowledged():
    long_df = _long_df("TEST_STALE", [("2026-01-01", 1.0), ("2026-02-01", 2.0)])
    meta = {"frequency": "monthly", "observation_type": "point_in_time", "lifecycle": "stale_source"}
    s, desc = timeseries.prepare_level(
        "TEST_STALE", meta, long_df,
        acknowledged_lifecycle={"TEST_STALE": "fine for this purpose"},
    )
    assert list(s.values) == [1.0, 2.0]


def test_prepare_level_raises_for_international_projection_without_cutoff():
    long_df = _long_df("TEST_WEO", [("2026-01-01", 1.0), ("2027-01-01", 2.0), ("2028-01-01", 3.0)])
    meta = {"frequency": "annual", "observation_type": "point_in_time",
            "category": "international_projection"}
    with pytest.raises(timeseries.SeriesGuardrailError, match="forecast"):
        timeseries.prepare_level("TEST_WEO", meta, long_df)


def test_forecast_cutoff_actually_excludes_post_cutoff_rows():
    # A long_df that's gap-free monthly *after* the cutoff filter is applied,
    # so this isolates the cutoff logic from the separate gap-free guardrail.
    long_df = _long_df("TEST_WEO2", [
        (f"2024-{m:02d}-01", 100.0 + m) for m in range(1, 13)
    ] + [("2031-01-01", 999.0)])
    meta = {"frequency": "monthly", "observation_type": "point_in_time",
            "category": "international_projection"}
    s, desc = timeseries.prepare_level("TEST_WEO2", meta, long_df, forecast_cutoff_year=2024)
    assert 999.0 not in s.values
    assert "2024" in desc


def test_prepare_level_raises_on_a_gap():
    long_df = _long_df("TEST_GAP", [
        ("2026-01-01", 1.0), ("2026-02-01", 2.0), ("2026-04-01", 4.0),  # March missing
    ])
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    with pytest.raises(timeseries.SeriesGuardrailError, match="gap-free"):
        timeseries.prepare_level("TEST_GAP", meta, long_df)


def test_prepare_level_passes_on_a_gap_free_series():
    long_df = _long_df("TEST_NOGAP", [
        ("2026-01-01", 1.0), ("2026-02-01", 2.0), ("2026-03-01", 3.0),
    ])
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    s, desc = timeseries.prepare_level("TEST_NOGAP", meta, long_df)
    assert len(s) == 3
