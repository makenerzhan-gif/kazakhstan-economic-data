"""Per-target seasonal-effect bar chart, rendered from DecompositionResult
alone -- decompose.py needed no changes for this: seasonal_by_period already
carries everything a bar chart needs (verified live against decompose.run_all()
during planning; the seasonal strengths it reproduced matched the already-
shipped report exactly).

MONTH_NAMES/QUARTER_NAMES are duplicated from seasonal_report.py rather than
imported -- same feature-local-helper convention every report module in this
project already keeps (see forecast_report.py's _format_number docstring).
"""
from __future__ import annotations

from pathlib import Path

from . import charts  # noqa: E402 -- must run matplotlib.use("Agg") first
import matplotlib.pyplot as plt  # noqa: E402

from .decompose import DecompositionResult

FIGSIZE = (8, 5)
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
QUARTER_NAMES = ["Q1", "Q2", "Q3", "Q4"]


def render_target_chart(result: DecompositionResult, run_date: str, out_dir: Path) -> Path:
    names = MONTH_NAMES if result.period == 12 else QUARTER_NAMES
    labels = [names[e.period_of_year - 1] for e in result.seasonal_by_period]
    values = [e.mean_effect for e in result.seasonal_by_period]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    # Positive/negative coloring is informative, not decorative: "which
    # calendar positions run above/below the yearly average" is exactly
    # what the adjacent markdown table already reports.
    colors = ["tab:blue" if v >= 0 else "tab:red" for v in values]
    ax.bar(labels, values, color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(f"{result.indicator_id} -- average seasonal effect by "
                 f"{'month' if result.period == 12 else 'quarter'}")
    ax.set_ylabel("Mean seasonal effect")

    path = out_dir / charts.chart_filename("seasonal", result.indicator_id, run_date)
    charts.save_figure(fig, path)
    return path


def render_all(results: list[DecompositionResult], run_date: str, out_dir: Path) -> list[Path]:
    return [render_target_chart(r, run_date, out_dir) for r in results]
