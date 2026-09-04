"""STL seasonal decomposition over the curated targets in seasonal_targets.py.

Reads data/unified/macro_long.csv only, via timeseries.prepare_level -- never
data/processed/ or data/raw/ directly. Every output is DERIVED, not sourced;
see analysis/README.md. Writes nothing to data/, config/, or
project_knowledge/.

Callers (scripts/decompose_seasonality.py, tests/test_decompose.py) are
responsible for putting scripts/ on sys.path before importing this module,
same convention as scripts/lib/*.py and scripts/analysis/correlate.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from statsmodels.tsa.seasonal import STL

from . import seasonal_targets as targets_config
from . import timeseries

REPO_ROOT = Path(__file__).resolve().parents[2]

# STL's own documented minimum is roughly 2 full seasonal cycles; this pass
# requires 3, stricter, since all 4 curated targets clear it comfortably
# (7.5x-16.5x) and a series that barely clears 2 cycles would be a shakier
# decomposition than this report should present without a much louder caveat.
MIN_CYCLES = 3

# Every curated target's window contains at least one large, transient,
# non-seasonal shock (the 2020 COVID disruption, the 2022 KZT devaluation).
# STL's seasonal-LOESS borrows strength across cycles, so a non-robust fit
# lets one anomalous period bleed into the seasonal estimate for that
# calendar position across every year, not just the year it happened.
# robust=True's bisquare downweighting is built for exactly this, at
# negligible extra cost on series this short. A single module constant
# rather than a per-target field: all 4 candidates share the same
# justification today; making it per-target is a two-line change if one
# ever needs to opt out, not a redesign.
STL_ROBUST = True


class DecompositionGuardrailError(Exception):
    """Mirrors validation.StructuralChangeError's stop-loudly philosophy: raised
    when a target would violate a decomposition-safety rule rather than
    silently guessing.
    """


@dataclass
class SeasonalEffect:
    period_of_year: int  # calendar month 1-12 (period==12) or quarter 1-4 (period==4)
    mean_effect: float
    n_cycles: int


@dataclass
class DecompositionResult:
    indicator_id: str
    label: str
    rationale: str
    interpretation: str
    prep_description: str
    period: int
    n: int
    date_start: str
    date_end: str
    robust: bool
    seasonal_strength: float
    trend_strength: float | None
    trend_start: float
    trend_end: float
    trend_change_pct: float | None
    seasonal_by_period: list[SeasonalEffect]
    caveats: list[str] = field(default_factory=list)


def _variance_explained(component: pd.Series, resid: pd.Series) -> float:
    """max(0, 1 - Var(resid)/Var(component+resid)) -- the standard Hyndman &
    Athanasopoulos measure of how much a component (seasonal, or trend)
    explains relative to what's left after removing the other component.
    NOT Var(component)/Var(original): for a strongly-trending series (e.g.
    GDP_NOMINAL) that would be dominated by trend and understate seasonality.

    Returns 0.0 (not NaN) when component+resid is constant -- an undefined
    ratio is reported as "explains nothing measurable", not as a crash.
    """
    denom = (component + resid).var()
    if not denom or pd.isna(denom):
        return 0.0
    return max(0.0, 1.0 - resid.var() / denom)


def seasonal_effect_table(seasonal: pd.Series, period: int) -> list[SeasonalEffect]:
    """Average seasonal effect by calendar month (period=12) or quarter
    (period=4) -- a 12- or 4-row table, not a dump of every observation."""
    if period == 12:
        grouper = seasonal.index.month
    elif period == 4:
        grouper = seasonal.index.quarter
    else:
        raise DecompositionGuardrailError(f"No calendar grouping known for period={period}.")
    grouped = seasonal.groupby(grouper)
    means = grouped.mean()
    counts = grouped.size()
    return [
        SeasonalEffect(period_of_year=int(k), mean_effect=float(means[k]), n_cycles=int(counts[k]))
        for k in sorted(means.index)
    ]


def decompose_target(
    target: targets_config.SeasonalTarget,
    long_df: pd.DataFrame,
    indicators_by_id: dict[str, dict],
) -> DecompositionResult:
    meta = indicators_by_id[target.indicator_id]

    expected_period = targets_config.FREQUENCY_TO_PERIOD.get(meta.get("frequency"))
    if expected_period != target.period:
        raise DecompositionGuardrailError(
            f"{target.indicator_id}: configured period={target.period} does not match "
            f"its real frequency={meta.get('frequency')!r} (expected period="
            f"{expected_period}). Fix seasonal_targets.py rather than proceeding."
        )

    s, prep_description = timeseries.prepare_level(
        target.indicator_id, meta, long_df,
        acknowledged_lifecycle=targets_config.ACKNOWLEDGED_LIFECYCLE,
        forecast_cutoff_year=targets_config.FORECAST_CUTOFF_YEAR.get(target.indicator_id),
    )

    min_n = MIN_CYCLES * target.period
    if len(s) < min_n:
        raise DecompositionGuardrailError(
            f"{target.indicator_id}: {len(s)} observations is below this pass's "
            f"{MIN_CYCLES}-cycle minimum ({min_n} for period={target.period}) -- too "
            f"short for STL to say anything meaningful."
        )

    fit = STL(s, period=target.period, robust=STL_ROBUST).fit()

    seasonal_strength = _variance_explained(fit.seasonal, fit.resid)
    trend_strength = _variance_explained(fit.trend, fit.resid)

    trend_start = float(fit.trend.iloc[0])
    trend_end = float(fit.trend.iloc[-1])
    trend_change_pct = ((trend_end / trend_start) - 1.0) * 100.0 if trend_start else None

    return DecompositionResult(
        indicator_id=target.indicator_id, label=target.label, rationale=target.rationale,
        interpretation=target.interpretation, prep_description=prep_description,
        period=target.period, n=len(s),
        date_start=s.index.min().strftime("%Y-%m-%d"), date_end=s.index.max().strftime("%Y-%m-%d"),
        robust=STL_ROBUST, seasonal_strength=seasonal_strength, trend_strength=trend_strength,
        trend_start=trend_start, trend_end=trend_end, trend_change_pct=trend_change_pct,
        seasonal_by_period=seasonal_effect_table(fit.seasonal, target.period),
    )


def run_all(target_list: list[targets_config.SeasonalTarget] | None = None) -> list[DecompositionResult]:
    target_list = targets_config.SEASONAL_TARGETS if target_list is None else target_list
    long_df = timeseries.load_long()
    indicators_by_id = timeseries.load_indicators()
    return [decompose_target(t, long_df, indicators_by_id) for t in target_list]
