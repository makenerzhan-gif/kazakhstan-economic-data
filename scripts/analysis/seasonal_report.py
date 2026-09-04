"""Render a list of DecompositionResult into the markdown report.

Pure string-building, same shape as build_project_knowledge.py's
build_data_catalog/build_sources_md and scripts/analysis/report.py's
build_report: one function in, one string out, no I/O. The `charts` import
below is the pure chart_filename() naming function only -- never
charts.save_figure() -- so this module stays genuinely zero-I/O; the actual
PNG is written by decompose_seasonality.py calling seasonal_charts.render_all()
before this module's build_report() ever runs.
"""
from __future__ import annotations

from . import charts
from .decompose import MIN_CYCLES, DecompositionResult

DISCLAIMER = """**DERIVED, NOT SOURCED.** Every number below is computed by
`scripts/decompose_seasonality.py` from `data/unified/macro_long.csv`. None of
it is published by БНС, НБ РК, Минфин, АРРФР, or the IMF; it does not belong
in `config/indicators.yaml`, `data/processed/`, or the sourced-data narrative
in `project_knowledge/`, and as of this report it is not synced into the
Claude Project. Treat every figure here as a starting point for a question,
not a finding on its own -- see Methodology and limitations at the end."""

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
QUARTER_NAMES = ["Q1", "Q2", "Q3", "Q4"]


def _methodology(min_cycles: int) -> str:
    return f"""## Methodology and limitations

- Decomposition is STL (`statsmodels.tsa.seasonal.STL`, seasonal-trend
  decomposition via LOESS), run with `robust=True` on every target: each
  target's window contains at least one large, transient, non-seasonal shock
  (the 2020 COVID disruption, the 2022 KZT devaluation), and a non-robust fit
  would let one anomalous period bleed into the seasonal estimate for that
  calendar position across every year, not just the year it happened.
- Every target is required to clear {min_cycles} full seasonal cycles of
  history before decomposition runs at all (stricter than STL's own
  documented ~2-cycle minimum) -- refused, not attempted with a louder
  caveat, below that bar.
- **Seasonal strength** is `max(0, 1 - Var(resid)/Var(seasonal+resid))` (the
  standard Hyndman & Athanasopoulos measure), not `Var(seasonal)/Var(original)`.
  The difference matters for a strongly-trending series: the naive ratio would
  be dominated by trend and understate seasonality. 0 means the seasonal
  component explains nothing beyond noise; 1 means the residual is
  negligible next to it.
- STL's trend estimate is a LOESS smooth and is less reliable at the very
  start and end of the window than in the middle (less data on one side to
  smooth against) -- the reported trend start/end values inherit that edge
  effect and should be read as approximate, not exact boundary values.
- This is a curated set of hand-picked targets, not every monthly/quarterly
  indicator in the dataset -- see `analysis/README.md` for the full
  feasibility sweep and why the rest were left out."""


def _format_number(v: float) -> str:
    """Thousands-separated, 2 decimals -- readable at CPI's ~100-point scale
    and at EXPORTS/GDP_NOMINAL's multi-digit KZT/USD scale alike, without
    per-indicator unit-scaling logic."""
    return f"{v:,.2f}"


def _format_effect(v: float) -> str:
    return f"{v:+,.2f}"


def _seasonal_table(result: DecompositionResult) -> list[str]:
    names = MONTH_NAMES if result.period == 12 else QUARTER_NAMES
    lines = [
        "",
        "**Average seasonal effect by calendar " + ("month" if result.period == 12 else "quarter") + ":**",
        "",
        "| Period | Mean seasonal effect | Cycles averaged |",
        "|---|---|---|",
    ]
    for effect in result.seasonal_by_period:
        name = names[effect.period_of_year - 1]
        lines.append(f"| {name} | {_format_effect(effect.mean_effect)} | {effect.n_cycles} |")
    return lines


def _chart_embed(indicator_id: str, run_date: str) -> list[str]:
    filename = charts.chart_filename("seasonal", indicator_id, run_date)
    return ["", f"![{indicator_id} average seasonal effect chart](charts/{filename})"]


def _target_section(result: DecompositionResult, run_date: str) -> str:
    trend_word = "rose" if result.trend_end >= result.trend_start else "fell"
    trend_pct = (f", {abs(result.trend_change_pct):.1f}%"
                 if result.trend_change_pct is not None else "")
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
        f"- **Seasonal strength: {result.seasonal_strength:.3f}** (0-1 scale; see "
        f"Methodology for the formula).",
        f"- Trend: {_format_number(result.trend_start)} -> {_format_number(result.trend_end)} "
        f"({trend_word}{trend_pct} over the window).",
    ]
    if result.caveats:
        lines.append("")
        for c in result.caveats:
            lines.append(f"- {c}")
    if result.interpretation:
        lines += ["", result.interpretation]
    lines += _chart_embed(result.indicator_id, run_date)
    lines += _seasonal_table(result)
    return "\n".join(lines)


def build_report(results: list[DecompositionResult], run_date: str) -> str:
    n_targets = len(results)
    parts = [
        f"# Seasonal decomposition -- {run_date}",
        "",
        DISCLAIMER,
        "",
        f"Curated set of {n_targets} targets, hand-picked for having enough dense, "
        f"gap-free history to make STL decomposition meaningful, and being "
        f"genuinely seasonal in the classic sense -- not every monthly/quarterly "
        f"indicator in the dataset. See `analysis/README.md` for the full "
        f"feasibility sweep and why the rest were left out.",
        "",
    ]
    for r in results:
        parts.append(_target_section(r, run_date))
        parts.append("")
    parts.append(_methodology(MIN_CYCLES))
    return "\n".join(parts) + "\n"
