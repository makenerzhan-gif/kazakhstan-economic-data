"""ETS(A,A,A) forecasting over the curated targets in forecast_targets.py.

Two fits per target: a BACKTEST fit trained on all but the last `horizon`
observations, scored against the real held-out actuals (MAE/RMSE/MAPE); and a
FORWARD fit trained on the full series, forecasting `horizon` periods beyond
the last real observation with a 95% prediction interval. The forward
forecast has no held-out actual to check itself against -- it is reported as
explicitly unverified (see forecast_report.py).

Reads data/unified/macro_long.csv only, via timeseries.prepare_level -- never
data/processed/ or data/raw/ directly. Every output is DERIVED, not sourced;
see analysis/README.md. Writes nothing to data/, config/, or
project_knowledge/.

Callers (scripts/forecast_series.py, tests/test_forecast.py) are responsible
for putting scripts/ on sys.path before importing this module, same
convention as scripts/analysis/decompose.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

from . import forecast_targets as targets_config
from . import timeseries

# Fixed for every target -- standard additive Holt-Winters via MLE
# state-space estimation. No damped trend, no multiplicative variant, no
# automatic model-order search: same "smallest decision surface" choice
# decompose.py's STL_ROBUST made -- a two-line change to override per-target
# if one ever needs to, not a redesign.
ERROR = "add"
TREND = "add"
SEASONAL = "add"
MODEL_SPEC = (
    "ETS(A,A,A) -- additive error, additive trend, additive seasonal "
    "(statsmodels.tsa.exponential_smoothing.ets.ETSModel, MLE state-space "
    "estimation, NOT statsmodels.tsa.holtwinters.ExponentialSmoothing: the "
    "classic implementation's fitted result has no get_prediction(), only "
    ".simulate(), which would need manual quantile-taking for an interval)"
)

# 95% prediction interval on the forward forecast.
ALPHA = 0.05

# This pass's own guardrail, applied to the POST-HOLDOUT training length
# (len(series) - horizon), not the full series -- decompose.py's MIN_CYCLES
# gates the full series instead, since it has no holdout split. Independently
# declared here at the same value/philosophy, not imported from decompose.py
# -- same "a different pass's decisions aren't inherited" split
# seasonal_targets.py already keeps from pairs.py. statsmodels' own floor is
# 2x seasonal_periods (raises ValueError below that, verified directly
# against 0.15.0); this pass requires 3x, the same margin-over-the-library's
# own minimum decompose.py already chose for STL.
MIN_CYCLES = 3


class ForecastGuardrailError(Exception):
    """Mirrors validation.StructuralChangeError's stop-loudly philosophy: raised
    when a target would violate a forecasting-safety rule rather than
    silently guessing.
    """


@dataclass
class BacktestMetrics:
    train_n: int
    train_start: str
    train_end: str
    holdout_start: str
    holdout_end: str
    horizon: int
    mae: float
    rmse: float
    mape: float


@dataclass
class ForecastPoint:
    date: str
    mean: float
    pi_lower: float
    pi_upper: float


@dataclass
class ForecastResult:
    indicator_id: str
    label: str
    rationale: str
    interpretation: str
    prep_description: str
    period: int
    horizon: int
    n: int
    date_start: str
    date_end: str
    model_spec: str
    backtest: BacktestMetrics
    forecast_points: list[ForecastPoint]
    caveats: list[str] = field(default_factory=list)


def _mae(actual: pd.Series, forecast: pd.Series) -> float:
    """Mean absolute error: mean(|actual - forecast|), same units as the series."""
    return float((actual - forecast).abs().mean())


def _rmse(actual: pd.Series, forecast: pd.Series) -> float:
    """Root mean squared error: sqrt(mean((actual - forecast)^2))."""
    return float(((actual - forecast) ** 2).mean() ** 0.5)


def _mape(actual: pd.Series, forecast: pd.Series) -> float:
    """Mean absolute percentage error: mean(|actual - forecast| / |actual|) * 100.

    Undefined for an actual value of exactly 0 -- not given a silent
    fallback, same "stop loudly rather than guess" spirit as the rest of
    this pass. Not a live concern for the 4 curated targets:
    forecast_targets.py documents each one's verified value range, and none
    comes near zero anywhere in its history.
    """
    return float(((actual - forecast).abs() / actual.abs()).mean() * 100.0)


def _fit_ets(series: pd.Series, period: int):
    """Fit the fixed ETS(A,A,A) spec (module constants ERROR/TREND/SEASONAL) on
    `series`. Used identically for both the backtest fit (series = the
    training split) and the forward fit (series = the full history) -- same
    spec, different input window, per this pass's two-fit design.
    """
    return ETSModel(
        series, error=ERROR, trend=TREND, seasonal=SEASONAL, seasonal_periods=period,
    ).fit(disp=False)


def forecast_target(
    target: targets_config.ForecastTarget,
    long_df: pd.DataFrame,
    indicators_by_id: dict[str, dict],
) -> ForecastResult:
    meta = indicators_by_id[target.indicator_id]

    expected_period = targets_config.FREQUENCY_TO_PERIOD.get(meta.get("frequency"))
    if expected_period != target.period:
        raise ForecastGuardrailError(
            f"{target.indicator_id}: configured period={target.period} does not match "
            f"its real frequency={meta.get('frequency')!r} (expected period="
            f"{expected_period}). Fix forecast_targets.py rather than proceeding."
        )

    expected_horizon = targets_config.PERIOD_TO_HORIZON.get(target.period)
    if expected_horizon != target.horizon:
        raise ForecastGuardrailError(
            f"{target.indicator_id}: configured horizon={target.horizon} does not match "
            f"period={target.period}'s expected horizon={expected_horizon} "
            f"(PERIOD_TO_HORIZON). Fix forecast_targets.py rather than proceeding."
        )

    s, prep_description = timeseries.prepare_level(
        target.indicator_id, meta, long_df,
        acknowledged_lifecycle=targets_config.ACKNOWLEDGED_LIFECYCLE,
        forecast_cutoff_year=targets_config.FORECAST_CUTOFF_YEAR.get(target.indicator_id),
    )
    # prepare_level already verified this is gap-free on this exact
    # (frequency-implied) regular grid -- asfreq here only attaches that
    # already-proven grid to the index so ETSModel doesn't have to infer it
    # (and warn that it's inferring it -- verified live: without this, every
    # fit emits ValueWarning: "No frequency information was provided...").
    # Reuses timeseries.FREQUENCY_OFFSET rather than a second copy:
    # forecast.py must use the IDENTICAL grid prepare_level's own gap check
    # just validated, not a value that could independently drift from it.
    s = s.asfreq(timeseries.FREQUENCY_OFFSET[meta["frequency"]])

    train_n = len(s) - target.horizon
    min_train_n = MIN_CYCLES * target.period
    if train_n < min_train_n:
        raise ForecastGuardrailError(
            f"{target.indicator_id}: {train_n} training observations ({len(s)} total "
            f"minus a {target.horizon}-period holdout) is below this pass's "
            f"{MIN_CYCLES}-cycle minimum ({min_train_n} for period={target.period}) -- "
            f"too short to backtest meaningfully."
        )

    train, holdout = s.iloc[:train_n], s.iloc[train_n:]
    backtest_forecast = _fit_ets(train, target.period).forecast(target.horizon)
    backtest = BacktestMetrics(
        train_n=train_n,
        train_start=train.index.min().strftime("%Y-%m-%d"),
        train_end=train.index.max().strftime("%Y-%m-%d"),
        holdout_start=holdout.index.min().strftime("%Y-%m-%d"),
        holdout_end=holdout.index.max().strftime("%Y-%m-%d"),
        horizon=target.horizon,
        mae=_mae(holdout, backtest_forecast),
        rmse=_rmse(holdout, backtest_forecast),
        mape=_mape(holdout, backtest_forecast),
    )

    forward_fit = _fit_ets(s, target.period)
    pred = forward_fit.get_prediction(start=len(s), end=len(s) + target.horizon - 1)
    frame = pred.summary_frame(alpha=ALPHA)
    forecast_points = [
        ForecastPoint(
            date=idx.strftime("%Y-%m-%d"), mean=float(row["mean"]),
            pi_lower=float(row["pi_lower"]), pi_upper=float(row["pi_upper"]),
        )
        for idx, row in frame.iterrows()
    ]

    return ForecastResult(
        indicator_id=target.indicator_id, label=target.label, rationale=target.rationale,
        interpretation=target.interpretation, prep_description=prep_description,
        period=target.period, horizon=target.horizon, n=len(s),
        date_start=s.index.min().strftime("%Y-%m-%d"), date_end=s.index.max().strftime("%Y-%m-%d"),
        model_spec=MODEL_SPEC, backtest=backtest, forecast_points=forecast_points,
    )


def run_all(target_list: list[targets_config.ForecastTarget] | None = None) -> list[ForecastResult]:
    target_list = targets_config.FORECAST_TARGETS if target_list is None else target_list
    long_df = timeseries.load_long()
    indicators_by_id = timeseries.load_indicators()
    return [forecast_target(t, long_df, indicators_by_id) for t in target_list]
