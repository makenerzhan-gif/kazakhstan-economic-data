"""Render a list of PairResult into the markdown report.

Pure string-building, same shape as build_project_knowledge.py's
build_data_catalog/build_sources_md: one function in, one string out, no I/O.
"""
from __future__ import annotations

from .correlate import SIGNIFICANCE_ALPHA, PairResult

DISCLAIMER = """**DERIVED, NOT SOURCED.** Every number below is computed by
`scripts/analyze_correlations.py` from `data/unified/macro_long.csv`. None of
it is published by БНС, НБ РК, Минфин, АРРФР, or the IMF; it does not belong
in `config/indicators.yaml`, `data/processed/`, or the sourced-data narrative
in `project_knowledge/`, and as of this report it is not synced into the
Claude Project. Treat every figure here as a starting point for a question,
not a finding on its own -- see Methodology and limitations at the end."""

METHODOLOGY = f"""## Methodology and limitations

- Correlation is Pearson (`scipy.stats.pearsonr`, which also gives the
  p-value below -- the same r `pandas.Series.corr` would give), computed on
  the transform stated per indicator above, over the intersection of
  available dates for each pair.
- The p-value tests the null hypothesis of no linear correlation (rho=0)
  against a t-distribution, which assumes the underlying data is
  approximately bivariate normal -- not verified for any series here, and
  probably false for some of them (growth rates in particular can be
  skewed). Read it as a rough guide, not an exact one, especially at the
  small sample sizes some of these pairs have.
- "Significant at {SIGNIFICANCE_ALPHA:.0%}" below means p < {SIGNIFICANCE_ALPHA}
  for that single test. This report runs several such tests (one per pair,
  plus one per lag on the pairs with a lag scan) without correcting for
  that -- at {SIGNIFICANCE_ALPHA:.0%}, roughly 1 in 20 tests would clear the
  bar by chance alone even with no real relationship anywhere, and a lag
  scan's own "strongest reading" is the best of several such tests by
  construction. Treat any single significant reading, especially a lag
  scan's best one, as a lead worth checking again, not a conclusion.
- Significant is not the same as strong: the p-value mainly reflects sample
  size, so a large-n pair can flag "significant" on a coefficient too weak
  to matter for anything (REER and NEER vs CPI both do exactly this in this
  report -- n>180 makes r around -0.2 to -0.25 clear the bar easily), while
  a genuinely strong relationship at small n can fail to. Read the r value
  for how strong the relationship is; read the p-value only for how
  confidently this sample rules out "no relationship at all."
- Correlation is not causation, and none of the above controls for
  confounders.
- This is a curated set of hand-picked pairs, not an all-pairs matrix over
  every indicator in the dataset -- see `analysis/README.md` for the full
  candidate list and why the rest were left out."""


def _format_r(r: float | None) -> str:
    return f"{r:.3f}" if r is not None else "undefined"


def _format_p(p: float | None) -> str:
    if p is None:
        return "undefined"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _significance_note(p: float | None) -> str:
    if p is None:
        return ""
    return (f", significant at {SIGNIFICANCE_ALPHA:.0%}" if p < SIGNIFICANCE_ALPHA
            else f", not significant at {SIGNIFICANCE_ALPHA:.0%}")


def _lag_table(result: PairResult) -> list[str]:
    """Lag scan as a markdown table plus a plain-language note on the
    strongest same-window reading -- described as descriptive, never as
    "the" lag, since scanning several lags and reporting the best one is a
    form of multiple comparisons (see Methodology and limitations)."""
    lines = [
        "",
        f"**Lag scan** (positive lag = {result.id_x} leads {result.id_y}):",
        "",
        "| Lag (periods) | r | p | n |",
        "|---|---|---|---|",
    ]
    for point in result.lag_profile:
        marker = " (contemporaneous)" if point.lag == 0 else ""
        lines.append(f"| {point.lag:+d}{marker} | {_format_r(point.r)} | "
                      f"{_format_p(point.p)} | {point.n} |")

    defined = [pt for pt in result.lag_profile if pt.r is not None]
    if defined:
        best = max(defined, key=lambda pt: abs(pt.r))
        lines += [
            "",
            f"Strongest same-window reading: lag {best.lag:+d}, r = {_format_r(best.r)}, "
            f"p = {_format_p(best.p)}{_significance_note(best.p)} (n={best.n}). "
            f"Descriptive only -- scanning multiple lags means this is the best of "
            f"several looks, not a confirmed finding on its own; see Methodology.",
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
    lines.append(f"- **Pearson r = {_format_r(result.r)}** "
                  f"(p = {_format_p(result.p)}{_significance_note(result.p)})")
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
