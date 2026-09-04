import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import correlate  # noqa: E402
from analysis import pairs as pairs_config  # noqa: E402
from analysis import report  # noqa: E402


def _long_df(indicator_id: str, rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [d for d, _ in rows],
        "variable": [indicator_id] * len(rows),
        "value": [v for _, v in rows],
    })


def test_prepare_indicator_uses_comparison_index_as_is():
    long_df = _long_df("TEST_IDX", [("2026-01-01", 100.0), ("2026-02-01", 105.0)])
    meta = {"frequency": "monthly", "observation_type": "comparison_index"}
    s, desc = correlate.prepare_indicator("TEST_IDX", meta, long_df)
    assert list(s.values) == [100.0, 105.0]
    assert "as-is" in desc


def test_prepare_indicator_applies_growth_rate_to_raw_level():
    long_df = _long_df("TEST_LEVEL", [("2026-01-01", 100.0), ("2026-02-01", 110.0)])
    meta = {"frequency": "monthly", "observation_type": "point_in_time"}
    s, desc = correlate.prepare_indicator("TEST_LEVEL", meta, long_df)
    assert len(s) == 1  # growth_rate drops the first point (nothing to diff against)
    assert s.iloc[0] == pytest.approx(10.0)
    assert "growth_rate" in desc


def test_prepare_indicator_decumulates_year_to_date_before_growth_rate():
    long_df = _long_df("TEST_YTD", [
        ("2026-01-01", 100.0), ("2026-04-01", 210.0),
        ("2026-07-01", 320.0), ("2026-10-01", 430.0),
    ])
    meta = {"frequency": "quarterly", "observation_type": "period_total", "cumulation": "year_to_date"}
    s, desc = correlate.prepare_indicator("TEST_YTD", meta, long_df)
    # de-cumulated own-period contributions are [100, 110, 110, 110]: Q1=100
    # (nothing to subtract), Q2..Q4 each contribute 110. growth_rate on that
    # series is then +10% (110 vs 100) followed by two 0% steps (110 vs 110).
    assert "de-cumulated" in desc
    assert list(s.values) == pytest.approx([10.0, 0.0, 0.0])


def test_prepare_indicator_raises_for_lifecycle_without_acknowledgement():
    long_df = _long_df("TEST_STALE", [("2026-01-01", 1.0)])
    meta = {"frequency": "monthly", "observation_type": "point_in_time", "lifecycle": "stale_source"}
    assert "TEST_STALE" not in pairs_config.ACKNOWLEDGED_LIFECYCLE
    with pytest.raises(correlate.AnalysisGuardrailError, match="lifecycle"):
        correlate.prepare_indicator("TEST_STALE", meta, long_df)


def test_prepare_indicator_raises_for_international_projection_without_cutoff():
    long_df = _long_df("TEST_WEO", [("2026-01-01", 1.0), ("2031-01-01", 2.0)])
    meta = {"frequency": "annual", "observation_type": "point_in_time",
            "category": "international_projection"}
    with pytest.raises(correlate.AnalysisGuardrailError, match="forecast"):
        correlate.prepare_indicator("TEST_WEO", meta, long_df)


def test_prepare_indicator_excludes_years_past_forecast_cutoff():
    long_df = _long_df("TEST_WEO", [
        ("2024-01-01", 100.0), ("2025-01-01", 110.0), ("2031-01-01", 999.0),
    ])
    meta = {"frequency": "annual", "observation_type": "comparison_index",
            "category": "international_projection"}
    s, desc = correlate.prepare_indicator("TEST_WEO", meta, long_df, forecast_cutoff_year=2025)
    assert 999.0 not in s.values
    assert "2025" in desc


def test_prepare_indicator_resamples_daily_to_monthly_mean():
    # EXCHANGE_RATE really is mapped to "mean" in config/frequency.yaml -- using
    # the real id lets this test exercise the real (not guessed) aggregation method.
    long_df = _long_df("EXCHANGE_RATE", [
        ("2026-01-05", 100.0), ("2026-01-15", 200.0), ("2026-01-25", 300.0),  # mean 200
        ("2026-02-05", 400.0), ("2026-02-15", 400.0), ("2026-02-25", 400.0),  # mean 400
    ])
    meta = {"frequency": "daily", "observation_type": "point_in_time"}
    s, desc = correlate.prepare_indicator(
        "EXCHANGE_RATE", meta, long_df, resample_to="monthly"
    )
    assert "resampled" in desc
    # after resample: Jan=200, Feb=400 -> growth_rate = +100%
    assert len(s) == 1
    assert s.iloc[0] == pytest.approx(100.0)


def test_prepare_indicator_raises_when_resample_target_has_no_aggregation_method():
    long_df = _long_df("TEST_NO_METHOD", [("2026-01-05", 1.0), ("2026-02-05", 2.0)])
    meta = {"frequency": "daily", "observation_type": "point_in_time"}
    with pytest.raises(correlate.AnalysisGuardrailError, match="frequency.yaml"):
        correlate.prepare_indicator("TEST_NO_METHOD", meta, long_df, resample_to="monthly")


def test_check_consistent_annual_convention_raises_on_mismatch():
    dates_x = ["2020-01-01", "2021-01-01", "2022-01-01"]
    dates_y = ["2020-12-31", "2021-12-31", "2022-12-31"]
    with pytest.raises(correlate.AnalysisGuardrailError, match="period-"):
        correlate.check_consistent_annual_convention("X", dates_x, "Y", dates_y)


def test_check_consistent_annual_convention_passes_on_match():
    dates_x = ["2020-01-01", "2021-01-01"]
    dates_y = ["2020-01-01", "2021-01-01"]
    correlate.check_consistent_annual_convention("X", dates_x, "Y", dates_y)  # no raise


def test_correlate_pair_flags_small_sample():
    pair = pairs_config.Pair("A", "B", "label", "rationale")
    long_df = pd.concat([
        _long_df("A", [("2026-01-01", 1.0), ("2026-02-01", 2.0), ("2026-03-01", 3.0)]),
        _long_df("B", [("2026-01-01", 10.0), ("2026-02-01", 20.0), ("2026-03-01", 30.0)]),
    ])
    indicators_by_id = {
        "A": {"frequency": "monthly", "observation_type": "comparison_index"},
        "B": {"frequency": "monthly", "observation_type": "comparison_index"},
    }
    result = correlate.correlate_pair(pair, long_df, indicators_by_id)
    assert result.n == 3
    assert result.r == pytest.approx(1.0)
    assert any("small sample" in c for c in result.caveats)


def test_build_report_contains_disclaimer_and_every_pair_label():
    results = [
        correlate.PairResult(
            id_x="A", id_y="B", label="A vs B", rationale="why", interpretation="reading",
            transform_x="as-is", transform_y="as-is", n=10,
            date_start="2026-01-01", date_end="2026-10-01", r=0.5, caveats=["n=10 -- small"],
        ),
    ]
    text = report.build_report(results, run_date="2026-09-04")
    assert "DERIVED, NOT SOURCED" in text
    assert "A vs B" in text
    assert "0.500" in text
    assert "n=10 -- small" in text
    assert "reading" in text


def test_build_report_handles_undefined_correlation():
    results = [
        correlate.PairResult(
            id_x="A", id_y="B", label="A vs B", rationale="why", interpretation="",
            transform_x="as-is", transform_y="as-is", n=0,
            date_start=None, date_end=None, r=None, caveats=["no overlap"],
        ),
    ]
    text = report.build_report(results, run_date="2026-09-04")
    assert "undefined" in text
