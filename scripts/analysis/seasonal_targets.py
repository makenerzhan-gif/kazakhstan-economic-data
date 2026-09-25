"""Curated targets for the seasonal-decomposition pass.

Deliberately a small, hand-picked list, not every monthly/quarterly indicator
in the dataset -- a full sweep of all 247 monthly+quarterly indicators' actual
processed CSVs found only 4 that are both genuinely economically-seasonal and
have enough dense, gap-free history for STL to mean anything. See
analysis/README.md for the full sweep and why the rest were left out.

`rationale` is why the target was picked, written before seeing a result.
`interpretation` is what to keep in mind while reading the result -- written
once and reused across runs, same split as scripts/analysis/pairs.py.
"""
from __future__ import annotations

from dataclasses import dataclass

FREQUENCY_TO_PERIOD = {"monthly": 12, "quarterly": 4}


@dataclass(frozen=True)
class SeasonalTarget:
    indicator_id: str
    label: str
    rationale: str
    period: int  # 12 = monthly, 4 = quarterly -- STL's seasonal cycle length
    interpretation: str = ""


SEASONAL_TARGETS: list[SeasonalTarget] = [
    SeasonalTarget(
        "CPI", "Headline CPI, month-over-month (already a comparison index)",
        rationale=(
            "Already a published MoM comparison index (observation_type="
            "comparison_index, comparison_basis=mom, unit 'index, previous "
            "month = 100') -- decompose as published, same 'already a comparison, don't "
            "transform it' rule scripts/analysis/correlate.py already uses. "
            "Textbook seasonal candidate: 187 gap-free monthly points "
            "(2011-01..2026-07), 15.5x this pass's 3-cycle minimum."
        ),
        period=12,
        interpretation=(
            "Window includes the 2022 KZT devaluation's inflation spike and the "
            "2020 COVID disruption -- both large, transient, non-seasonal shocks. "
            "robust=True exists specifically so neither distorts the seasonal "
            "estimate for the calendar month it happened to land in, rather than "
            "the shock's size being permanently attributed to that month every year."
        ),
    ),
    SeasonalTarget(
        "EXPORTS", "Exports (total), monthly level",
        rationale=(
            "Raw monthly trade-flow level (thousand USD, observation_type="
            "period_total, no cumulation) -- decompose the level, not a growth "
            "rate: STL separates trend/seasonal/residual out of the level itself, "
            "and a growth-rate series would already be partially deseasonalized "
            "before STL ever saw it. 90 gap-free monthly points (2019-01..2026-06), "
            "7.5x the minimum -- shorter margin than CPI, still comfortable."
        ),
        period=12,
        interpretation=(
            "Same COVID/devaluation shock-window caveat as CPI. Also exposed to "
            "global commodity-price swings unrelated to calendar seasonality -- a "
            "real seasonal signal here more plausibly reflects shipment/logistics "
            "timing than price."
        ),
    ),
    SeasonalTarget(
        "IMPORTS", "Imports (total), monthly level",
        rationale=(
            "Same construction as EXPORTS (thousand USD, period_total, no "
            "cumulation, 90 gap-free points 2019-01..2026-06) -- run alongside it, "
            "not instead of it: imports and exports can carry different seasonal "
            "patterns (domestic demand timing vs. what Kazakhstan exports)."
        ),
        period=12,
        interpretation="Same COVID/devaluation and price-vs-timing caveat as EXPORTS.",
    ),
    SeasonalTarget(
        "GDP_NOMINAL", "Nominal GDP, quarterly level (de-cumulated)",
        rationale=(
            "cumulation=year_to_date -- runs through "
            "scripts.lib.transformations.decumulate_ytd before decomposition (via "
            "timeseries.prepare_level), then decomposes the de-cumulated own-period "
            "level as published. 66 gap-free quarterly points (2010-01..2026-04), "
            "16.5x the minimum -- the deepest margin of the four candidates."
        ),
        period=4,
        interpretation=(
            "Nominal KZT GDP grew roughly an order of magnitude over this window "
            "from real growth, inflation, and the 2022 devaluation combined -- "
            "trend dominates the raw level's variance by construction, which is "
            "exactly why seasonal strength is reported as a share of "
            "seasonal-plus-residual variance, not total variance (see the report's "
            "Methodology section)."
        ),
    ),
]

# Explicit, reviewed overrides. decompose.py refuses to run a target that needs
# one of these and isn't listed here -- fail loudly, never silently guess.
# Independently reviewed here, NOT imported from scripts/analysis/pairs.py --
# a different feature's overrides aren't inherited from a different pass's
# decisions.
# Empty as of this list: none of the 4 candidates carry a lifecycle flag or
# belong to the international_projection category.
ACKNOWLEDGED_LIFECYCLE: dict[str, str] = {}
FORECAST_CUTOFF_YEAR: dict[str, int] = {}
