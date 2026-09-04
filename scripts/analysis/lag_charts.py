"""Per-pair lag-scan bar chart (Pearson r vs lag), rendered only for pairs
that set max_lag > 0 in pairs.py (today: 3 of 8 -- OIL_PRICE vs
EXCHANGE_RATE, vs OIL_EXPORTS_VALUE, vs OIL_EXPORTS_VOLUME). Pairs without a
lag scan get no chart -- a single r/p scalar has nothing to plot as a
function of lag.

Same bar-chart visual language as seasonal_charts.py (discrete x positions,
zero line, sign-colored bars): lag is a small number of discrete shifts, not
a continuous time series like forecast_charts.py's line chart.

Needs no changes to correlate.py -- PairResult.lag_profile (a list of
LagPoint(lag, r, p, n)) already carries everything this chart needs.
"""
from __future__ import annotations

from pathlib import Path

from . import charts  # noqa: E402 -- must run matplotlib.use("Agg") first
import matplotlib.pyplot as plt  # noqa: E402

from .correlate import PairResult

FIGSIZE = (8, 5)


def _pair_key(result: PairResult) -> str:
    return f"{result.id_x}_{result.id_y}"


def render_pair_chart(result: PairResult, run_date: str, out_dir: Path) -> Path | None:
    """Returns None (renders nothing) for a pair with no lag scan."""
    if not result.lag_profile:
        return None

    defined = [pt for pt in result.lag_profile if pt.r is not None]
    labels = [f"{pt.lag:+d}" for pt in defined]
    values = [pt.r for pt in defined]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    colors = ["tab:blue" if v >= 0 else "tab:red" for v in values]
    ax.bar(labels, values, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(f"{result.id_x} vs {result.id_y} -- lag scan "
                 f"(positive lag = {result.id_x} leads {result.id_y})")
    ax.set_xlabel("Lag (periods)")
    ax.set_ylabel("Pearson r")
    if len(defined) < len(result.lag_profile):
        n_undefined = len(result.lag_profile) - len(defined)
        ax.text(0.5, 1.02, f"{n_undefined} lag(s) undefined, not shown",
                transform=ax.transAxes, ha="center", va="bottom", fontsize=8, color="0.4")

    path = out_dir / charts.chart_filename("lag", _pair_key(result), run_date)
    charts.save_figure(fig, path)
    return path


def render_all(results: list[PairResult], run_date: str, out_dir: Path) -> list[Path]:
    paths = [render_pair_chart(r, run_date, out_dir) for r in results]
    return [p for p in paths if p is not None]
