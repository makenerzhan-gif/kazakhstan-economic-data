"""Render a list of ForecastResult into the markdown report.

Pure string-building, same shape as scripts/analysis/seasonal_report.py's
build_report: one function in, one string out, no I/O. The `charts` import
below is the pure chart_filename() naming function only -- never
charts.save_figure() -- so this module stays genuinely zero-I/O; the actual
PNG is written by forecast_series.py calling forecast_charts.render_all()
before this module's build_report() ever runs.
"""
from __future__ import annotations

from . import charts
from .forecast import MIN_CYCLES, ForecastResult

DISCLAIMER = """**DERIVED, NOT SOURCED.** Every number below is computed by
`scripts/forecast_series.py` from `data/unified/macro_long.csv`. None of it
is published by БНС, НБ РК, Минфин, АРРФР, or the IMF; it does not belong in
`config/indicators.yaml`, `data/processed/`, or the sourced-data narrative in
`project_knowledge/`, and as of this report it is not synced into the Claude
Project. Treat every figure here as a starting point for a question, not a
finding on its own -- see Methodology and limitations at the end."""


def _methodology(min_cycles: int) -> str:
    return f"""## Methodology and limitations

- Forecasting is `statsmodels.tsa.exponential_smoothing.ets.ETSModel`, fixed
  spec ETS(A,A,A) -- additive error, additive trend, additive seasonal.
  `statsmodels.tsa.holtwinters.ExponentialSmoothing` (the classic
  implementation) was deliberately not used: its fitted result has no
  `get_prediction()`, only `.simulate()`, which would need manual
  quantile-taking to build a prediction interval.
- **Two fits per target, not one.** A *backtest* fit trains on all but the
  last `horizon` periods and is scored (MAE/RMSE/MAPE) against the real,
  already-known actuals for that window. A separate *forward* fit trains on
  the full series (including what the backtest held out) and forecasts
  `horizon` periods beyond the last real observation. The forward forecast
  has no held-out actual to compare against by construction -- its only
  evidence of plausibility is the backtest accuracy of the identical model
  spec, which is why it is labeled UNVERIFIED in every target section below,
  not presented with the same confidence as the backtest numbers.
- `horizon` is 12 periods for monthly targets and 4 for quarterly -- a
  one-year-ahead framing for both.
- Every target's post-holdout training length must clear {min_cycles} full
  seasonal cycles ({min_cycles} x period) before either fit runs at all --
  the same MIN_CYCLES={min_cycles} philosophy `scripts/analysis/decompose.py`
  applies to STL, independently reviewed for this pass and applied to the
  post-holdout training length rather than the full series.
- MAE = mean(|actual - forecast|); RMSE = sqrt(mean((actual - forecast)^2));
  MAPE = mean(|actual - forecast| / |actual|) x 100. All three are safe to
  compute for all 4 curated targets -- none has a value near zero anywhere
  in its history (see `forecast_targets.py` for the verified ranges).
- The 95% prediction interval comes from
  `get_prediction().summary_frame(alpha=0.05)`. For this additive spec
  specifically, statsmodels reports the interval as exact (closed-form), not
  simulated.
- Unlike the seasonal-decomposition pass's STL fit (`robust=True`), ETS has
  no outlier-downweighting mechanism -- a large one-time shock inside a
  target's training window (the 2020 COVID disruption, the 2022 KZT
  devaluation, both inside every curated target's history) is fit like any
  other observation and can influence the estimated smoothing parameters,
  not just the periods it actually occurred in.
- This report shows one MAE/RMSE/MAPE per target across the whole holdout
  window -- it does not say whether accuracy one period ahead differs from
  accuracy `horizon` periods ahead within the same backtest. A reasonable
  follow-up question, not answered here.
- This is a curated set of hand-picked targets, not every monthly/quarterly
  indicator in the dataset -- see `analysis/README.md` for the full
  feasibility sweep (shared with the decomposition pass) and why the rest
  were left out."""


def _format_number(v: float) -> str:
    """Thousands-separated, 2 decimals -- same formatting discipline as
    seasonal_report.py's _format_number (independently defined here, not
    imported, same feature-local-helper convention every report module in
    this project already keeps), for the same reason: GDP_NOMINAL-scale
    figures are unreadable at full precision.
    """
    return f"{v:,.2f}"


def _format_pct(v: float) -> str:
    return f"{v:.2f}%"


def _backtest_section(result: ForecastResult) -> list[str]:
    bt = result.backtest
    return [
        "",
        "**Backtest** (trained on all but the last observations, forecast "
        "compared against the real, already-known actuals for that window):",
        "",
        f"- Training window: {bt.train_start} .. {bt.train_end} ({bt.train_n} observations).",
        f"- Holdout window: {bt.holdout_start} .. {bt.holdout_end} ({bt.horizon} observations).",
        f"- MAE: {_format_number(bt.mae)}",
        f"- RMSE: {_format_number(bt.rmse)}",
        f"- MAPE: {_format_pct(bt.mape)}",
    ]


def _forecast_table(result: ForecastResult) -> list[str]:
    lines = [
        "",
        f"### Forward forecast -- UNVERIFIED ({result.horizon} periods beyond {result.date_end})",
        "",
        "No held-out actual exists for these periods -- they are beyond the "
        "last real observation. The only evidence this is plausible is the "
        "backtest above: the identical model spec's accuracy on the most "
        f"recent {result.horizon} periods where the real answer is already "
        "known. Treat this table as a starting point for a question, not a "
        "prediction to act on.",
        "",
        "| Date | Forecast | 95% interval |",
        "|---|---|---|",
    ]
    for pt in result.forecast_points:
        lines.append(f"| {pt.date} | {_format_number(pt.mean)} | "
                      f"{_format_number(pt.pi_lower)} .. {_format_number(pt.pi_upper)} |")
    return lines


def _chart_embed(indicator_id: str, run_date: str) -> list[str]:
    filename = charts.chart_filename("forecast", indicator_id, run_date)
    return ["", f"![{indicator_id} history, backtest, and forecast chart](charts/{filename})"]


def _target_section(result: ForecastResult, run_date: str) -> str:
    lines = [
        f"## {result.indicator_id}",
        "",
        f"**{result.label}**",
        "",
        f"*Why this candidate:* {result.rationale}",
        "",
        f"- Prepared as: {result.prep_description}",
        f"- Window: {result.date_start} .. {result.date_end} -- {result.n} observations, "
        f"period={result.period} ({'monthly' if result.period == 12 else 'quarterly'}).",
        f"- Model: {result.model_spec}",
    ]
    if result.caveats:
        lines.append("")
        for c in result.caveats:
            lines.append(f"- {c}")
    if result.interpretation:
        lines += ["", result.interpretation]
    lines += _chart_embed(result.indicator_id, run_date)
    lines += _backtest_section(result)
    lines += _forecast_table(result)
    return "\n".join(lines)


def build_report(results: list[ForecastResult], run_date: str) -> str:
    n_targets = len(results)
    parts = [
        f"# Forecasting -- {run_date}",
        "",
        DISCLAIMER,
        "",
        f"Curated set of {n_targets} targets, the same 4 the seasonal-decomposition "
        f"pass uses -- not every monthly/quarterly indicator in the dataset. See "
        f"`analysis/README.md` for the full feasibility sweep and why the rest "
        f"were left out.",
        "",
    ]
    for r in results:
        parts.append(_target_section(r, run_date))
        parts.append("")
    parts.append(_methodology(MIN_CYCLES))
    return "\n".join(parts) + "\n"
