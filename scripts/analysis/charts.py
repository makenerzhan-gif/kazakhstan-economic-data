"""Shared chart-rendering plumbing for the decomposition and forecasting
passes' PNG charts. What to plot lives in seasonal_charts.py/
forecast_charts.py, not here -- same shared/feature-local split
timeseries.py already keeps from decompose.py/forecast.py.

matplotlib.pyplot is deliberately NOT imported at module level: only
chart_filename() (pure string formatting) is safe for a zero-I/O module like
seasonal_report.py/forecast_report.py to import without pulling in
matplotlib's own import-time machinery. add_disclaimer()/save_figure()
import matplotlib.pyplot locally, deferred until a chart is actually
rendered. Callers that DO need to draw (seasonal_charts.py/forecast_charts.py)
must `from . import charts` before their own `import matplotlib.pyplot`, so
matplotlib.use("Agg") below runs before pyplot locks in a backend.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this is a script/CLI context, no display

DEFAULT_DPI = 120
DISCLAIMER_TEXT = "DERIVED, NOT SOURCED -- see analysis/README.md"


def chart_filename(prefix: str, indicator_id: str, run_date: str) -> str:
    """Pure naming convention, no I/O. Shared by the chart-builder modules
    (where to save) and the report modules (what relative link to embed) so
    the two can never drift apart.
    """
    return f"{prefix}_{indicator_id}_{run_date}.png"


def add_disclaimer(fig) -> None:
    """Small 'DERIVED, NOT SOURCED' footer stamped into the image itself --
    a PNG can be shared/embedded standalone, disconnected from its report's
    surrounding disclaimer text. Called automatically by save_figure(); chart
    builders should not need to call this directly.
    """
    fig.text(0.5, 0.01, DISCLAIMER_TEXT, ha="center", va="bottom",
              fontsize=8, color="0.4")


def save_figure(fig, path: Path) -> None:
    """Stamp the disclaimer, ensure path.parent exists, save at DEFAULT_DPI,
    close the figure. matplotlib keeps every created figure registered (and
    in memory) until plt.close() runs -- a loop over 4 targets that skips
    this leaks all 4.
    """
    import matplotlib.pyplot as plt  # deferred: see module docstring

    add_disclaimer(fig)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DEFAULT_DPI, bbox_inches="tight")
    plt.close(fig)
