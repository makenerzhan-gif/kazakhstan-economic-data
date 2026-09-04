"""Per-target forecast chart: the full historical actual line, the backtest's
predicted values overlaid on the holdout window (the visual form of what
"backtest" means), and the forward forecast + 95% interval band continuing
past the last real observation, clearly marked UNVERIFIED and visually
separated by a vertical marker at the last real observation.

Needs forecast.py's history/predictions fields (added specifically for this
chart -- see forecast.py's HistoryPoint and the comments at its two capture
sites) since neither the historical series nor the backtest's per-period
predictions were previously retained on ForecastResult/BacktestMetrics.
"""
from __future__ import annotations

from pathlib import Path

from . import charts  # noqa: E402 -- must run matplotlib.use("Agg") first
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .forecast import ForecastResult

FIGSIZE = (11, 5)


def render_target_chart(result: ForecastResult, run_date: str, out_dir: Path) -> Path:
    hist_dates = pd.to_datetime([p.date for p in result.history])
    bt_dates = pd.to_datetime([p.date for p in result.backtest.predictions])
    fwd_dates = pd.to_datetime([p.date for p in result.forecast_points])

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(hist_dates, [p.value for p in result.history], label="Actual", color="tab:blue")
    ax.plot(bt_dates, [p.value for p in result.backtest.predictions],
             label="Backtest prediction", color="tab:orange", linestyle="--")
    ax.plot(fwd_dates, [p.mean for p in result.forecast_points],
             label="Forward forecast (UNVERIFIED)", color="tab:green", linestyle="--")
    ax.fill_between(
        fwd_dates,
        [p.pi_lower for p in result.forecast_points],
        [p.pi_upper for p in result.forecast_points],
        color="tab:green", alpha=0.2, label="95% interval",
    )
    ax.axvline(hist_dates[-1], color="gray", linestyle=":", linewidth=1)
    ax.set_title(f"{result.indicator_id} -- history, backtest, and forecast")
    ax.legend(loc="best", fontsize=8)
    fig.autofmt_xdate()

    path = out_dir / charts.chart_filename("forecast", result.indicator_id, run_date)
    charts.save_figure(fig, path)
    return path


def render_all(results: list[ForecastResult], run_date: str, out_dir: Path) -> list[Path]:
    return [render_target_chart(r, run_date, out_dir) for r in results]
