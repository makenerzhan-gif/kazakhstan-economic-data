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


def _count_tests(results: list[PairResult]) -> int:
    """Total distinct significance tests represented in this report: one per
    pair's headline correlation, plus one per NON-ZERO lag in any lag scan --
    lag=0 in a scan is the same test as that pair's headline, not a second
    one, so it isn't counted twice."""
    n = len(results)
    for r in results:
        if r.lag_profile:
            n += sum(1 for pt in r.lag_profile if pt.lag != 0)
    return n


def _methodology(n_tests: int, corrected_alpha: float) -> str:
    return f"""## Methodology and limitations

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
  for that single test in isolation.
- **Multiple comparisons.** This report represents {n_tests} distinct tests
  (one per pair, plus one per non-zero lag on the pairs with a lag scan --
  a lag scan's own contemporaneous point is the same test as that pair's
  headline, not counted again). At {SIGNIFICANCE_ALPHA:.0%} uncorrected,
  roughly 1 in 20 tests would clear the bar by chance alone even with no
  real relationship anywhere in the data, and a lag scan's "strongest
  reading" is the best of several such tests by construction. "Survives
  Bonferroni correction" below means p < {corrected_alpha:.4f}
  ({SIGNIFICANCE_ALPHA} / {n_tests}, the standard conservative adjustment
  for testing {n_tests} hypotheses in one report). Treat a reading that is
  significant uncorrected but does not survive correction as a lead worth
  checking again with fresh data, not a conclusion.
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


def _bonferroni_clause(p: float | None, corrected_alpha: float) -> str:
    if p is None:
        return ""
    return ("; survives Bonferroni correction" if p < corrected_alpha
            else "; does not survive Bonferroni correction")


def _significance_note(p: float | None, corrected_alpha: float) -> str:
    """The Bonferroni clause is appended only when the uncorrected test is
    itself significant -- a reading that already misses the easier bar
    trivially misses the stricter corrected one too (corrected_alpha is
    always <= SIGNIFICANCE_ALPHA), so stating that as well would be noise.
    """
    if p is None:
        return ""
    if p < SIGNIFICANCE_ALPHA:
        return f", significant at {SIGNIFICANCE_ALPHA:.0%}" + _bonferroni_clause(p, corrected_alpha)
    return f", not significant at {SIGNIFICANCE_ALPHA:.0%}"


def _lag_table(result: PairResult, corrected_alpha: float) -> list[str]:
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
            f"p = {_format_p(best.p)}{_significance_note(best.p, corrected_alpha)} "
            f"(n={best.n}). Descriptive only -- scanning multiple lags means this is "
            f"the best of several looks, not a confirmed finding on its own; see "
            f"Methodology.",
        ]
    return lines


def _pair_section(result: PairResult, corrected_alpha: float) -> str:
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
                  f"(p = {_format_p(result.p)}{_significance_note(result.p, corrected_alpha)})")
    if result.caveats:
        lines.append("")
        for c in result.caveats:
            lines.append(f"- {c}")
    if result.interpretation:
        lines += ["", result.interpretation]
    if result.lag_profile:
        lines += _lag_table(result, corrected_alpha)
    return "\n".join(lines)


def build_report(results: list[PairResult], run_date: str) -> str:
    n_pairs = len(results)
    n_tests = _count_tests(results)
    corrected_alpha = SIGNIFICANCE_ALPHA / n_tests if n_tests else SIGNIFICANCE_ALPHA

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
        parts.append(_pair_section(r, corrected_alpha))
        parts.append("")
    parts.append(_methodology(n_tests, corrected_alpha))
    return "\n".join(parts) + "\n"
