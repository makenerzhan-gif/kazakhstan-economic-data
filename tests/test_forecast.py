import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image
from statsmodels.tools.sm_exceptions import ConvergenceWarning

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from analysis import charts  # noqa: E402
from analysis import forecast  # noqa: E402
from analysis import forecast_charts  # noqa: E402
from analysis import forecast_report  # noqa: E402
from analysis import forecast_targets  # noqa: E402
from analysis import timeseries  # noqa: E402


def _long_df(indicator_id: str, rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [d for d, _ in rows],
        "variable": [indicator_id] * len(rows),
        "value": [v for _, v in rows],
    })


def test_mae_hand_computed_example():
    actual = pd.Series([10.0, 20.0, 30.0])
    fc = pd.Series([12.0, 18.0, 33.0])
    # |errors| = [2, 2, 3] -> mean = 7/3
    assert forecast._mae(actual, fc) == pytest.approx(7 / 3)


def test_rmse_hand_computed_example():
    actual = pd.Series([10.0, 20.0, 30.0])
    fc = pd.Series([12.0, 18.0, 33.0])
    # squared errors = [4, 4, 9] -> mean=17/3 -> sqrt
    assert forecast._rmse(actual, fc) == pytest.approx((17 / 3) ** 0.5)


def test_mape_hand_computed_example():
    actual = pd.Series([10.0, 20.0, 30.0])
    fc = pd.Series([12.0, 18.0, 33.0])
    # |err|/|actual| = [0.2, 0.1, 0.1] -> mean=0.13333... * 100
    assert forecast._mape(actual, fc) == pytest.approx(13.333333, abs=1e-4)


def test_forecast_target_recovers_a_known_deterministic_continuation():
    # Same spirit as decompose.py's known-shape recovery test: a
    # deliberately irregular (non-sinusoidal) seasonal pattern, long enough
    # to clear MIN_CYCLES many times over. With zero noise, a correctly
    # implemented ETS(A,A,A) backtest should reconstruct the held-out
    # continuation almost exactly.
    true_seasonal = [4, 2, -1, -3, -4, -2, 0, 1, 3, 2, -1, -1]
    assert sum(true_seasonal) == 0
    n = 96  # 8 years, well above (MIN_CYCLES*12 + horizon)=48
    trend = [100 + 0.8 * t for t in range(n)]
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    observed = [trend[t] + true_seasonal[t % 12] for t in range(n)]

    long_df = _long_df("TEST_FC", list(zip((d.strftime("%Y-%m-%d") for d in dates), observed)))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = forecast_targets.ForecastTarget(
        "TEST_FC", "test", "test rationale", period=12, horizon=12,
    )

    # A fully deterministic (zero-residual-variance) series is a known MLE
    # edge case -- statsmodels can't confirm convergence and warns, even
    # though the fit itself recovers the true continuation almost exactly.
    # Suppressed only here, not in forecast.py itself: real target series
    # didn't trigger this in manual verification against the live data, and
    # production forecasts on real, noisy data should surface a genuine
    # non-convergence rather than silently swallow it.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        result = forecast.forecast_target(target, long_df, {"TEST_FC": meta})

    assert result.backtest.mae == pytest.approx(0.0, abs=1e-4)
    assert result.backtest.rmse == pytest.approx(0.0, abs=1e-4)

    # history/predictions are retained for the charting pass -- confirm they
    # actually cover the windows their surrounding scalars already claim.
    assert len(result.history) == result.n
    assert result.history[0].date == result.date_start
    assert result.history[-1].date == result.date_end
    assert len(result.backtest.predictions) == result.backtest.horizon
    assert result.backtest.predictions[0].date == result.backtest.holdout_start
    assert result.backtest.predictions[-1].date == result.backtest.holdout_end


def test_forecast_target_raises_below_min_training_length():
    # period=12, horizon=12 -> needs train_n = n-12 >= MIN_CYCLES*12=36, i.e. n>=48.
    # n=47 leaves train_n=35, one short of the floor.
    dates = pd.date_range("2015-01-01", periods=47, freq="MS")
    long_df = _long_df("TEST_SHORT", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(47))))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = forecast_targets.ForecastTarget("TEST_SHORT", "test", "test rationale", period=12, horizon=12)
    with pytest.raises(forecast.ForecastGuardrailError, match="training"):
        forecast.forecast_target(target, long_df, {"TEST_SHORT": meta})


def test_forecast_target_raises_when_period_does_not_match_real_frequency():
    dates = pd.date_range("2015-01-01", periods=60, freq="MS")
    long_df = _long_df("TEST_MISMATCH", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(60))))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = forecast_targets.ForecastTarget("TEST_MISMATCH", "test", "test rationale", period=4, horizon=4)
    with pytest.raises(forecast.ForecastGuardrailError, match="frequency"):
        forecast.forecast_target(target, long_df, {"TEST_MISMATCH": meta})


def test_forecast_target_raises_when_horizon_does_not_match_period():
    dates = pd.date_range("2015-01-01", periods=60, freq="MS")
    long_df = _long_df("TEST_HZ", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(60))))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    # period=12 (correct) but horizon=4 (a quarterly horizon on a monthly target -- a config typo).
    target = forecast_targets.ForecastTarget("TEST_HZ", "test", "test rationale", period=12, horizon=4)
    with pytest.raises(forecast.ForecastGuardrailError, match="horizon"):
        forecast.forecast_target(target, long_df, {"TEST_HZ": meta})


def test_forecast_target_propagates_series_guardrail_error_unwrapped():
    dates = pd.date_range("2015-01-01", periods=60, freq="MS")
    long_df = _long_df("TEST_STALE", list(zip((d.strftime("%Y-%m-%d") for d in dates), range(60))))
    meta = {"frequency": "monthly", "observation_type": "period_total", "lifecycle": "stale_source"}
    target = forecast_targets.ForecastTarget("TEST_STALE", "test", "test rationale", period=12, horizon=12)
    with pytest.raises(timeseries.SeriesGuardrailError, match="lifecycle"):
        forecast.forecast_target(target, long_df, {"TEST_STALE": meta})


def _sample_result() -> forecast.ForecastResult:
    return forecast.ForecastResult(
        indicator_id="TEST_X", label="Test label", rationale="why", interpretation="reading",
        prep_description="level as published", period=12, horizon=12, n=60,
        date_start="2021-01-01", date_end="2025-12-01", model_spec=forecast.MODEL_SPEC,
        backtest=forecast.BacktestMetrics(
            train_n=48, train_start="2021-01-01", train_end="2024-12-01",
            holdout_start="2025-01-01", holdout_end="2025-12-01",
            horizon=12, mae=1.23, rmse=1.5, mape=2.34,
            predictions=[
                forecast.HistoryPoint(date="2025-01-01", value=108.0),
                forecast.HistoryPoint(date="2025-12-01", value=109.5),
            ],
        ),
        forecast_points=[
            forecast.ForecastPoint(date="2026-01-01", mean=110.0, pi_lower=105.0, pi_upper=115.0),
        ],
        history=[
            forecast.HistoryPoint(date="2021-01-01", value=100.0),
            forecast.HistoryPoint(date="2025-12-01", value=109.5),
        ],
    )


def test_build_report_contains_disclaimer_and_target_id():
    text = forecast_report.build_report([_sample_result()], run_date="2026-09-04")
    assert "DERIVED, NOT SOURCED" in text
    assert "TEST_X" in text
    assert "reading" in text
    assert "2.34%" in text  # MAPE


def test_build_report_labels_forward_section_as_unverified():
    text = forecast_report.build_report([_sample_result()], run_date="2026-09-04")
    assert "UNVERIFIED" in text


def test_build_report_renders_training_window_as_a_date_range():
    text = forecast_report.build_report([_sample_result()], run_date="2026-09-04")
    assert "2021-01-01 .. 2024-12-01 (48 observations)" in text


def test_build_report_handles_no_targets():
    text = forecast_report.build_report([], run_date="2026-09-04")
    assert "Forecasting" in text
    assert "Methodology" in text


def test_render_target_chart_writes_a_valid_png(tmp_path):
    n = 96
    trend = [100 + 0.5 * t for t in range(n)]
    seasonal = [4, 2, -1, -3, -4, -2, 0, 1, 3, 2, -1, -1]
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")
    observed = [trend[t] + seasonal[t % 12] for t in range(n)]
    long_df = _long_df("TEST_CHART", list(zip((d.strftime("%Y-%m-%d") for d in dates), observed)))
    meta = {"frequency": "monthly", "observation_type": "period_total"}
    target = forecast_targets.ForecastTarget("TEST_CHART", "test", "test rationale", period=12, horizon=12)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        result = forecast.forecast_target(target, long_df, {"TEST_CHART": meta})

    path = forecast_charts.render_target_chart(result, run_date="2026-09-04", out_dir=tmp_path)

    assert path.name == charts.chart_filename("forecast", "TEST_CHART", "2026-09-04")
    assert path.exists()
    assert path.stat().st_size > 1000
    img = Image.open(path)
    img.verify()
