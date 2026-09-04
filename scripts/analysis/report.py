"""Render a list of PairResult into the markdown report.

Pure string-building, same shape as build_project_knowledge.py's
build_data_catalog/build_sources_md: one function in, one string out, no I/O.
"""
from __future__ import annotations

from .correlate import PairResult

DISCLAIMER = """**DERIVED, NOT SOURCED.** Every number below is computed by
`scripts/analyze_correlations.py` from `data/unified/macro_long.csv`. None of
it is published by БНС, НБ РК, Минфин, АРРФР, or the IMF; it does not belong
in `config/indicators.yaml`, `data/processed/`, or the sourced-data narrative
in `project_knowledge/`, and as of this report it is not synced into the
Claude Project. Treat every figure here as a starting point for a question,
not a finding on its own -- see Methodology and limitations at the end."""

METHODOLOGY = """## Methodology and limitations

- Correlation is Pearson (`pandas.Series.corr`, default method), computed on
  the transform stated per indicator above, over the intersection of
  available dates for each pair.
- Where a lag scan is shown: lag is counted in periods of the two series'
  own overlap after each side's transform -- row position, not recalculated
  against calendar dates. A gap in either series' history would shift
  everything after it by more than the stated lag's worth of calendar time;
  none of the series a lag scan runs on have gaps in their overlap window,
  but this is not re-verified per run.
- No statistical significance testing (p-values, confidence intervals) is
  computed -- that requires `scipy.stats`, deliberately not added in this
  slice. A coefficient alone, especially at small n, is not proof of a
  relationship -- this applies to every lag in a scan individually, not
  just the headline contemporaneous figure, and scanning several lags and
  reporting the strongest one is itself a form of multiple comparisons: the
  strongest lag in a short window is not automatically the true one.
- Correlation is not causation, and none of the above controls for
  confounders.
- This is a curated set of hand-picked pairs, not an all-pairs matrix over
  every indicator in the dataset -- see `analysis/README.md` for the full
  candidate list and why the rest were left out."""


def _format_r(r: float | None) -> str:
    return f"{r:.3f}" if r is not None else "undefined"


def _lag_table(result: PairResult) -> list[str]:
    """Lag scan as a markdown table plus a plain-language note on the
    strongest same-window reading -- described as descriptive, never as
    "the" lag, since scanning several lags and reporting the best one is a
    form of multiple comparisons (see Methodology and limitations)."""
    lines = [
        "",
        f"**Lag scan** (positive lag = {result.id_x} leads {result.id_y}):",
        "",
        "| Lag (periods) | r | n |",
        "|---|---|---|",
    ]
    for point in result.lag_profile:
        marker = " (contemporaneous)" if point.lag == 0 else ""
        lines.append(f"| {point.lag:+d}{marker} | {_format_r(point.r)} | {point.n} |")

    defined = [p for p in result.lag_profile if p.r is not None]
    if defined:
        best = max(defined, key=lambda p: abs(p.r))
        lines += [
            "",
            f"Strongest same-window reading: lag {best.lag:+d}, r = {_format_r(best.r)} "
            f"(n={best.n}). Descriptive only -- no significance test, and scanning "
            f"multiple lags means this is the best of several looks, not a confirmed "
            f"finding on its own.",
        ]
    return lines


def _pair_section(result: PairResult) -> str:
    lines = [
        f"## {result.id_x} vs {result.id_y}",
        "",
        f"**{result.label}**",
        "",
        f"*Why this pair:* {result.rationale}",
        "",
        f"| | {result.id_x} | {result.id_y} |",
        "|---|---|---|",
        f"| Transform applied | {result.transform_x} | {result.transform_y} |",
        "",
    ]
    if result.n:
        lines.append(f"- Overlap window: {result.date_start} .. {result.date_end} "
                      f"-- {result.n} observations.")
    else:
        lines.append("- No overlapping observations between the two series after transform.")
    lines.append(f"- **Pearson r = {_format_r(result.r)}**")
    if result.caveats:
        lines.append("")
        for c in result.caveats:
            lines.append(f"- {c}")
    if result.interpretation:
        lines += ["", result.interpretation]
    if result.lag_profile:
        lines += _lag_table(result)
    return "\n".join(lines)


def build_report(results: list[PairResult], run_date: str) -> str:
    n_pairs = len(results)
    parts = [
        f"# Correlation analysis -- {run_date}",
        "",
        DISCLAIMER,
        "",
        f"Curated set of {n_pairs} pairs, hand-picked for shared history and a "
        f"plausible economic relationship -- not an all-pairs matrix. See "
        f"`analysis/README.md` for the full candidate list and why the rest "
        f"were left out of v1.",
        "",
    ]
    for r in results:
        parts.append(_pair_section(r))
        parts.append("")
    parts.append(METHODOLOGY)
    return "\n".join(parts) + "\n"
