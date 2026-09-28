"""Seasonal decomposition over the curated targets in seasonal_targets.py:
X-13ARIMA-SEATS (US Census Bureau, X-11 seasonal factors d10, via scripts/lib/x13.py) by
default, robust STL as the fallback when no X-13 binary is available or X-13 rejects the
series -- the result's `method` and `caveats` say which ran and why.

X-13 components are turned into the same quantities STL gave: in multiplicative mode
(AICC chose logs) the seasonal effect in the series' own units is SA x (factor - 1) and the
strength measures use ln(factor), ln(trend), ln(irregular); in additive mode d10/d12/d13 are
already in the series' units. X-13 also removes the Kazakhstan calendar effects (working days,
Kurban Ait) when AICC keeps them, so its seasonal effect is net of calendar, STL's is not.

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

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from lib import x13

from . import seasonal_targets as targets_config
from . import timeseries

REPO_ROOT = Path(__file__).resolve().parents[2]

# STL's own documented minimum is roughly 2 full seasonal cycles and X-13's is
# 3 (x13.MIN_YEARS); this pass requires 3 for both, since all 4 curated targets clear it comfortably
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

# "x13" (default) or "stl". X-13 never downloads here: it uses the vendored/cached binary
# (x13.find_binary) or falls back to STL with a caveat.
SA_METHOD = "x13"


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
    mean_factor_pct: float | None = None  # X-13 multiplicative: mean (factor - 1) x 100


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
    method: str = "STL"          # "X-13 X-11" | "STL"
    model_description: str = ""  # X-13: ARIMA model, calendar, outliers, M7/Q


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


def seasonal_effect_table(seasonal: pd.Series, period: int,
                          factor_pct: pd.Series | None = None) -> list[SeasonalEffect]:
    """Average seasonal effect by calendar month (period=12) or quarter
    (period=4) -- a 12- or 4-row table, not a dump of every observation.
    `factor_pct` (X-13 multiplicative factors as % deviations) adds a mean per row."""
    if period == 12:
        grouper = seasonal.index.month
    elif period == 4:
        grouper = seasonal.index.quarter
    else:
        raise DecompositionGuardrailError(f"No calendar grouping known for period={period}.")
    grouped = seasonal.groupby(grouper)
    means = grouped.mean()
    counts = grouped.size()
    fmeans = None
    if factor_pct is not None:
        fmeans = factor_pct.groupby(factor_pct.index.month if period == 12 else factor_pct.index.quarter).mean()
    return [
        SeasonalEffect(period_of_year=int(k), mean_effect=float(means[k]), n_cycles=int(counts[k]),
                       mean_factor_pct=None if fmeans is None else float(fmeans[k]))
        for k in sorted(means.index)
    ]


@dataclass
class _Components:
    seasonal_level: pd.Series        # in the series' units
    seasonal: pd.Series              # on the scale the strengths use (log for multiplicative)
    trend: pd.Series
    trend_level: pd.Series
    resid: pd.Series
    factor_pct: pd.Series | None
    method: str
    description: str
    robust: bool


def _stl_components(s: pd.Series, period: int) -> _Components:
    fit = STL(s, period=period, robust=STL_ROBUST).fit()
    return _Components(fit.seasonal, fit.seasonal, fit.trend, fit.trend, fit.resid, None, "STL",
                       f"STL, robust={STL_ROBUST}", STL_ROBUST)


def _x13_components(s: pd.Series, period: int, name: str) -> _Components:
    res = x13.adjust(s, period, transform="auto", method="x11", calendar="kz", title=name)
    desc = res.summary(include_method=False)
    if res.mode == "multiplicative":
        return _Components(res.sa * (res.seasonal - 1.0), np.log(res.seasonal), np.log(res.trend), res.trend,
                           np.log(res.irregular), 100.0 * (res.seasonal - 1.0), "X-13 X-11", desc, False)
    return _Components(res.seasonal, res.seasonal, res.trend, res.trend, res.irregular, None, "X-13 X-11",
                       desc, False)


def decompose_target(
    target: targets_config.SeasonalTarget,
    long_df: pd.DataFrame,
    indicators_by_id: dict[str, dict],
    method: str | None = None,
) -> DecompositionResult:
    """method: "x13" | "stl"; None = SA_METHOD."""
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
        sample_start=target.sample_start,
    )

    min_n = MIN_CYCLES * target.period
    if len(s) < min_n:
        raise DecompositionGuardrailError(
            f"{target.indicator_id}: {len(s)} observations is below this pass's "
            f"{MIN_CYCLES}-cycle minimum ({min_n} for period={target.period}) -- too "
            f"short for a seasonal decomposition (X-13 or STL) to say anything meaningful."
        )

    method = SA_METHOD if method is None else method
    caveats: list[str] = []
    comp = None
    if method == "x13":
        try:
            comp = _x13_components(s, target.period, target.indicator_id)
        except x13.X13Error as e:  # includes X13Unavailable
            caveats.append(f"X-13ARIMA-SEATS could not be used ({e}); this target fell back to robust STL.")
    elif method != "stl":
        raise DecompositionGuardrailError(f"Unknown decomposition method {method!r} (x13 | stl).")
    if comp is None:
        comp = _stl_components(s, target.period)

    seasonal_strength = _variance_explained(comp.seasonal, comp.resid)
    trend_strength = _variance_explained(comp.trend, comp.resid)

    trend_start = float(comp.trend_level.iloc[0])
    trend_end = float(comp.trend_level.iloc[-1])
    trend_change_pct = ((trend_end / trend_start) - 1.0) * 100.0 if trend_start else None

    return DecompositionResult(
        indicator_id=target.indicator_id, label=target.label, rationale=target.rationale,
        interpretation=target.interpretation, prep_description=prep_description,
        period=target.period, n=len(s),
        date_start=s.index.min().strftime("%Y-%m-%d"), date_end=s.index.max().strftime("%Y-%m-%d"),
        robust=comp.robust, seasonal_strength=seasonal_strength, trend_strength=trend_strength,
        trend_start=trend_start, trend_end=trend_end, trend_change_pct=trend_change_pct,
        seasonal_by_period=seasonal_effect_table(comp.seasonal_level, target.period, comp.factor_pct),
        caveats=caveats, method=comp.method, model_description=comp.description,
    )


def run_all(target_list: list[targets_config.SeasonalTarget] | None = None) -> list[DecompositionResult]:
    target_list = targets_config.SEASONAL_TARGETS if target_list is None else target_list
    long_df = timeseries.load_long()
    indicators_by_id = timeseries.load_indicators()
    return [decompose_target(t, long_df, indicators_by_id) for t in target_list]
