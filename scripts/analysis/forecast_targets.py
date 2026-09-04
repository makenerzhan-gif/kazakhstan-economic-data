"""Curated targets for the forecasting pass.

Same 4 candidates as the seasonal-decomposition pass
(scripts/analysis/seasonal_targets.py) -- CPI, EXPORTS, IMPORTS,
GDP_NOMINAL -- independently re-justified here against THIS pass's own
guardrail (a 3x-period floor on the POST-HOLDOUT training length, not the
full series decompose.py gates). Not imported from seasonal_targets.py: a
different feature's rationale isn't inherited from a different pass's
decisions, same split scripts/analysis/pairs.py and seasonal_targets.py
already keep from each other.

`rationale` is why the target was picked, written before seeing a forecast
result. `interpretation` is what to keep in mind while reading the result.
"""
from __future__ import annotations

from dataclasses import dataclass

FREQUENCY_TO_PERIOD = {"monthly": 12, "quarterly": 4}

# Both curated frequencies get a one-year-ahead horizon: 12 monthly periods,
# 4 quarterly periods. A lookup dict, not a formula, for the same reason
# FREQUENCY_TO_PERIOD above is one: explicit and reviewable, and the one
# place to extend if a future target ever needs a different horizon
# convention -- not a redesign.
PERIOD_TO_HORIZON = {12: 12, 4: 4}


@dataclass(frozen=True)
class ForecastTarget:
    indicator_id: str
    label: str
    rationale: str
    period: int  # 12 = monthly, 4 = quarterly -- same meaning as SeasonalTarget.period
    horizon: int  # forecast steps ahead; cross-checked against PERIOD_TO_HORIZON at run time
    interpretation: str = ""


FORECAST_TARGETS: list[ForecastTarget] = [
    ForecastTarget(
        "CPI", "Headline CPI, month-over-month -- 12-month-ahead forecast",
        rationale=(
            "Already a published MoM comparison index -- same level "
            "timeseries.prepare_level returns for the decomposition pass, "
            "forecast directly with no additional transform. This pass's own "
            "guardrail is a 3x-period floor on the POST-holdout training "
            "length (MIN_CYCLES=3, applied here rather than to the full "
            "series): n=187, horizon=12 leaves 175 training observations "
            "against a 36-observation floor -- 4.86x margin, the deepest of "
            "the four candidates. Value range 99.9-105.2 across the full "
            "history, never near zero -- MAPE is safe to compute."
        ),
        period=12, horizon=12,
        interpretation=(
            "Same 2022 KZT devaluation / 2020 COVID shock caveat as the "
            "decomposition pass's CPI entry, but ETS(A,A,A) has no analogue "
            "to STL's robust=True -- there is no outlier-downweighting here. "
            "Both shocks sit inside this target's training window and are "
            "fit like any other observation; they can influence the "
            "estimated smoothing parameters, not just the periods they "
            "actually occurred in. Read the forward forecast with that in "
            "mind."
        ),
    ),
    ForecastTarget(
        "EXPORTS", "Exports (total), monthly level -- 12-month-ahead forecast",
        rationale=(
            "Raw monthly trade-flow level (thousand USD, no cumulation) -- "
            "forecast the level directly, same reasoning the decomposition "
            "pass used (a growth-rate transform would already be partially "
            "deseasonalized before the model ever saw it). n=90, horizon=12 "
            "leaves 78 training observations against a 36-observation "
            "floor -- 2.17x margin, the tightest of the four candidates but "
            "still comfortably clearing it. Value range 2.64M-9.81M "
            "(thousand USD), never near zero -- MAPE-safe."
        ),
        period=12, horizon=12,
        interpretation=(
            "Same devaluation/COVID caveat as CPI, sharper here: no "
            "robust-fitting mechanism in ETS, and a shorter, noisier "
            "history (2.17x margin vs CPI's 4.86x) than the decomposition "
            "pass's easiest candidate. Also exposed to global "
            "commodity-price swings unrelated to calendar seasonality, same "
            "caveat the decomposition pass already carries for this target."
        ),
    ),
    ForecastTarget(
        "IMPORTS", "Imports (total), monthly level -- 12-month-ahead forecast",
        rationale=(
            "Same construction and margin as EXPORTS (thousand USD, no "
            "cumulation, n=90, train=78, 2.17x margin over this pass's 3x "
            "floor) -- run alongside it, not instead of it, same reason the "
            "decomposition pass did: imports and exports can carry "
            "different dynamics. Value range 2.18M-7.12M (thousand USD), "
            "MAPE-safe."
        ),
        period=12, horizon=12,
        interpretation="Same caveats as EXPORTS.",
    ),
    ForecastTarget(
        "GDP_NOMINAL", "Nominal GDP, quarterly level (de-cumulated) -- 4-quarter-ahead forecast",
        rationale=(
            "cumulation=year_to_date -- de-cumulated by "
            "timeseries.prepare_level before forecasting, same as the "
            "decomposition pass. n=66, horizon=4 leaves 62 training "
            "observations against a 12-observation floor (3x4) -- 5.17x "
            "margin. Post-decumulation range 4.02e12-59.88e13 KZT, never "
            "near zero -- MAPE-safe despite the huge scale."
        ),
        period=4, horizon=4,
        interpretation=(
            "Nominal KZT GDP grew roughly an order of magnitude over this "
            "window (real growth + inflation + the 2022 devaluation "
            "combined) -- trend dominates by construction, same context the "
            "decomposition pass's report gives. A trend this strong can "
            "make the additive-trend assumption itself a bigger source of "
            "forward-forecast risk than the seasonal component is; the "
            "backtest MAPE is the only real evidence either way."
        ),
    ),
]

# Explicit, reviewed overrides. forecast.py refuses to run a target that needs
# one of these and isn't listed here -- fail loudly, never silently guess.
# Independently reviewed here, NOT imported from seasonal_targets.py or
# pairs.py -- a different feature's overrides aren't inherited from a
# different pass's decisions.
# Empty as of this list: none of the 4 candidates carry a lifecycle flag or
# belong to the international_projection category.
ACKNOWLEDGED_LIFECYCLE: dict[str, str] = {}
FORECAST_CUTOFF_YEAR: dict[str, int] = {}
