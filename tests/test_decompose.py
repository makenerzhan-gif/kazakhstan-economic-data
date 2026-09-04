import sys
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import charts  # noqa: E402
from analysis import decompose  # noqa: E402
from analysis import seasonal_charts  # noqa: E402
from analysis import seasonal_report  # noqa: E402
from analysis import seasonal_targets  # noqa: E402
from analysis import timeseries  # noqa: E402


def _long_df(indicator_id: str, rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [d for d, _ in rows],
        "variable": [indicator_id] * len(rows),
        "value": [v for _, v in rows],
    })


def test_variance_explained_hand_computed_example():
    seasonal = pd.Series([1.0, -1.0, 1.0, -1.0])
    resid = pd.Series([0.5, -0.5, 0.5, -0.5])
    # Var(resid) [ddof=1] = 1/3; Var(seasonal+resid) = Var([1.5,-1.5,1.5,-1.5]) = 3.0
    # Fs = 1 - (1/3)/3 = 8/9
    assert decompose._variance_explained(seasonal, resid) == pytest.approx(8 / 9)


def test_variance_explained_near_zero_when_component_is_negligible():
    # Almost pure noise, no real seasonal component: resid variance is close
    # to (component+resid) variance, so Fs should be close to 0.
    component = pd.Series([0.001, -0.001, 0.001, -0.001])
    resid = pd.Series([1.0, -1.0, 1.0, -1.0])
    assert decompose._variance_explained(component, resid) == pytest.approx(0.0, abs=0.01)


def test_variance_explained_returns_zero_not_nan_for_constant_input():
    component = pd.Series([2.0, 2.0, 2.0])
    resid = pd.Series([0.0, 0.0, 0.0])
    assert decompose._variance_explained(component, resid) == 0.0


def test_decompose_target_recovers_a_known_seasonal_shape():
    # Deliberately irregular (not a symmetric sine, which could mask an
    # off-by-a-few-months alignment bug), sums to exactly 0 so there's no
    # trend/seasonal offset ambiguity.
    true_seasonal = [4, 2, -1, -3, -4, -2, 0, 1, 3, 2, -1, -1]
    assert sum(true_seasonal) == 0
    trend = [100 + 0.8 * t for t in range(96)]  # 8 years, well above MIN_CYCLES*12=36
    dates = pd.date_range("2015-01-01", periods=96, freq="MS")
    observed = [trend[t] + true_seasonal[t % 12] for t in range(96)]

    long_df = _long_df("TEST_SEASONAL", list(zip((d.strftime("%Y-%m-%d") for d in dates), observed)))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = seasonal_targets.SeasonalTarget("TEST_SEASONAL", "test", "test rationale", period=12)

    result = decompose.decompose_target(target, long_df, {"TEST_SEASONAL": meta})

    assert result.seasonal_strength == pytest.approx(1.0, abs=0.01)
    recovered = {e.period_of_year: e.mean_effect for e in result.seasonal_by_period}
    for month, expected in enumerate(true_seasonal, start=1):
        assert recovered[month] == pytest.approx(expected, abs=0.05)


def test_decompose_target_raises_below_min_cycles():
    dates = pd.date_range("2024-01-01", periods=12, freq="MS")  # only 1 cycle
    long_df = _long_df("TEST_SHORT", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(12))))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = seasonal_targets.SeasonalTarget("TEST_SHORT", "test", "test rationale", period=12)
    with pytest.raises(decompose.DecompositionGuardrailError, match="cycle"):
        decompose.decompose_target(target, long_df, {"TEST_SHORT": meta})


def test_decompose_target_raises_when_period_does_not_match_real_frequency():
    dates = pd.date_range("2015-01-01", periods=48, freq="MS")
    long_df = _long_df("TEST_MISMATCH", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(48))))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    # period=4 (quarterly) configured against a monthly indicator -- a config typo.
    target = seasonal_targets.SeasonalTarget("TEST_MISMATCH", "test", "test rationale", period=4)
    with pytest.raises(decompose.DecompositionGuardrailError, match="frequency"):
        decompose.decompose_target(target, long_df, {"TEST_MISMATCH": meta})


def test_decompose_target_propagates_series_guardrail_error_unwrapped():
    # decompose_target must NOT catch/wrap timeseries.SeriesGuardrailError into
    # its own DecompositionGuardrailError -- same "let it propagate" behaviour
    # correlate_pair already uses for AnalysisGuardrailError.
    dates = pd.date_range("2015-01-01", periods=48, freq="MS")
    long_df = _long_df("TEST_STALE", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(48))))
    meta = {"frequency": "monthly", "observation_type": "period_total", "lifecycle": "stale_source"}
    target = seasonal_targets.SeasonalTarget("TEST_STALE", "test", "test rationale", period=12)
    with pytest.raises(timeseries.SeriesGuardrailError, match="lifecycle"):
        decompose.decompose_target(target, long_df, {"TEST_STALE": meta})


def test_build_report_contains_disclaimer_and_target_id():
    results = [
        decompose.DecompositionResult(
            indicator_id="TEST_X", label="Test label", rationale="why", interpretation="reading",
            prep_description="level as published", period=12, n=48,
            date_start="2022-01-01", date_end="2025-12-01", robust=True,
            seasonal_strength=0.5, trend_strength=0.3, trend_start=100.0, trend_end=110.0,
            trend_change_pct=10.0,
            seasonal_by_period=[decompose.SeasonalEffect(period_of_year=1, mean_effect=1.234, n_cycles=4)],
        ),
    ]
    text = seasonal_report.build_report(results, run_date="2026-09-04")
    assert "DERIVED, NOT SOURCED" in text
    assert "TEST_X" in text
    assert "0.500" in text  # seasonal strength
    assert "reading" in text
    assert "Jan" in text


def test_build_report_handles_no_targets():
    text = seasonal_report.build_report([], run_date="2026-09-04")
    assert "Seasonal decomposition" in text
    assert "Methodology" in text


def test_render_target_chart_writes_a_valid_png(tmp_path):
    true_seasonal = [4, 2, -1, -3, -4, -2, 0, 1, 3, 2, -1, -1]
    trend = [100 + 0.8 * t for t in range(96)]
    dates = pd.date_range("2015-01-01", periods=96, freq="MS")
    observed = [trend[t] + true_seasonal[t % 12] for t in range(96)]
    long_df = _long_df("TEST_CHART", list(zip((d.strftime("%Y-%m-%d") for d in dates), observed)))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = seasonal_targets.SeasonalTarget("TEST_CHART", "test", "test rationale", period=12)
    result = decompose.decompose_target(target, long_df, {"TEST_CHART": meta})

    path = seasonal_charts.render_target_chart(result, run_date="2026-09-04", out_dir=tmp_path)

    assert path.name == charts.chart_filename("seasonal", "TEST_CHART", "2026-09-04")
    assert path.exists()
    assert path.stat().st_size > 1000
    img = Image.open(path)
    img.verify()
