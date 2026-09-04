"""Curated pairs for the v1 correlation pass.

Deliberately hand-picked and reviewed -- NOT an all-pairs matrix over 430
indicators. A blind matrix over series of wildly different length, frequency,
and quality would mostly produce spurious correlations; adding a pair here is
a reviewed decision, not a config toggle. See analysis/README.md for the
selection rationale and the candidates deliberately left out of v1.

`rationale` is why the pair was picked, written before seeing a result.
`interpretation` is what to keep in mind while reading the result -- structural
caveats a human should weigh in, written once and reused across runs. Neither
field states a specific r or n: those come from the live computation and
belong in the report table, not frozen into this file's prose. correlate.py
never generates economic narrative on its own -- only the mechanical caveats
(sample size, index-vs-flow mismatch) that follow directly from the numbers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pair:
    id_x: str
    id_y: str
    label: str
    rationale: str
    resample_to: str | None = None  # set when the two native frequencies differ
    interpretation: str = ""


PAIRS: list[Pair] = [
    Pair(
        "CPI_YOY", "CORE_CPI_YOY_EX3", "Headline vs core inflation (ex-3)",
        rationale=(
            "Both already-published YoY comparison indices (observation_type="
            "comparison_index) sharing the same base convention; core (ex "
            "food and energy-adjacent items) should broadly track headline "
            "inflation."
        ),
        interpretation=(
            "Strong co-movement is expected here almost by construction -- "
            "core is a subset of the same basket headline is built from. A "
            "weak reading would be the surprising result worth chasing, not "
            "a strong one."
        ),
    ),
    Pair(
        "OIL_PRICE", "EXCHANGE_RATE", "Oil price vs USD/KZT",
        rationale=(
            "Classic oil-exporter pass-through question: does a costlier or "
            "cheaper barrel show up in the tenge the same month."
        ),
        resample_to="monthly",
        interpretation=(
            "NBK manages the exchange rate rather than floating it freely, "
            "so a same-month linear read may understate a lagged or "
            "asymmetric response. Resampling the daily rate to a monthly "
            "mean also blurs when in the month a move happened, and the "
            "overlap window folds very different regimes (COVID recovery, "
            "the 2022 devaluation, disinflation) into one number. A lagged "
            "or YoY-basis version is a reasonable next step, not built here."
        ),
    ),
    Pair(
        "REER", "CPI", "Real effective exchange rate vs headline inflation",
        rationale=(
            "REER is meant to net out relative price levels against trading "
            "partners; checking it against domestic CPI is a natural first "
            "read."
        ),
        interpretation=(
            "This compares a slow-moving fixed-base level index against a "
            "fast month-over-month comparison -- a weak correlation is "
            "expected from that mismatch in what's being measured, not "
            "necessarily evidence of no relationship."
        ),
    ),
    Pair(
        "NEER", "CPI", "Nominal effective exchange rate vs headline inflation",
        rationale=(
            "Same question as REER vs CPI without the inflation adjustment "
            "already baked into the index, run alongside it for comparison."
        ),
        interpretation="Same level-vs-comparison mismatch caveat as REER vs CPI.",
    ),
    Pair(
        "GOV_REVENUE", "GOV_EXPENDITURE", "Budget revenue vs expenditure",
        rationale=(
            "Both minfin, annual, verified to share the same period-end "
            "(12-31) date convention over the same 2014-2025 window -- one "
            "of the cleanest-matched pairs in the whole dataset."
        ),
        interpretation=(
            "Only 12 annual observations means roughly 11 usable points "
            "after taking growth rates -- treat any result as descriptive, "
            "not confirmatory, regardless of how large the coefficient is."
        ),
    ),
    Pair(
        "OIL_PRICE", "OIL_EXPORTS_VALUE", "Oil price vs crude export value",
        rationale=(
            "Tests whether more expensive oil shows up in the value of what "
            "BNS records as actually exported, independent of the "
            "exchange-rate pass-through question above."
        ),
        interpretation=(
            "Export value moves with shipped volume as well as price, and "
            "volume has its own logistics-driven variation independent of "
            "price -- a weak reading doesn't mean price is irrelevant to "
            "revenue, only that value alone doesn't isolate the price effect. "
            "See OIL_PRICE vs OIL_EXPORTS_VOLUME below for a direct check of "
            "that volume-noise explanation."
        ),
    ),
    Pair(
        "CPI_YOY", "CORE_CPI_YOY_EX7", "Headline vs core inflation (ex-7)",
        rationale=(
            "Same question as headline vs core (ex-3) above, with the wider "
            "exclusion basket -- run alongside it rather than in place of it, "
            "since the two core measures can diverge from each other even "
            "when both track headline."
        ),
        interpretation=(
            "Same construction caveat as CPI_YOY vs CORE_CPI_YOY_EX3: strong "
            "co-movement is the expected result, not evidence of anything "
            "beyond core being a subset of the headline basket."
        ),
    ),
    Pair(
        "OIL_PRICE", "OIL_EXPORTS_VOLUME", "Oil price vs crude export volume",
        rationale=(
            "Direct counterpart to OIL_PRICE vs OIL_EXPORTS_VALUE: if price "
            "and volume move independently, that's the mechanism behind "
            "value's weak correlation with price above, not evidence price "
            "doesn't matter."
        ),
        interpretation=(
            "A near-zero reading here is the supporting case for that "
            "explanation; a strong one (in either direction) would mean the "
            "value result above needs a different explanation."
        ),
    ),
]

# Explicit, reviewed overrides. correlate.py refuses to run a pair that needs
# one of these and isn't listed here -- fail loudly, never silently guess.
# Empty as of this list: none of the pairs above touch a lifecycle-flagged or
# international_projection-category indicator.
ACKNOWLEDGED_LIFECYCLE: dict[str, str] = {}
FORECAST_CUTOFF_YEAR: dict[str, int] = {}
