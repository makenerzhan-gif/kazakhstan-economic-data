"""Documented transformations applied to PROCESSED data.

Raw data is never touched by these — they read from data/raw (via the caller)
and write to data/processed. Every function's docstring states its exact formula
so DATA_DICTIONARY.md can quote it verbatim.
"""
from __future__ import annotations

import math

Series = list[tuple[str, float | None]]  # (date, value), sorted ascending by date


def level(series: Series) -> Series:
    """Identity transform: value as published, no change."""
    return list(series)


def log(series: Series) -> Series:
    """ln(value). Undefined (None) for value <= 0."""
    return [(d, math.log(v) if v is not None and v > 0 else None) for d, v in series]


def difference(series: Series, periods: int = 1) -> Series:
    """value[t] - value[t-periods]."""
    out: Series = []
    for i, (d, v) in enumerate(series):
        if i < periods or v is None or series[i - periods][1] is None:
            out.append((d, None))
        else:
            out.append((d, v - series[i - periods][1]))
    return out


def growth_rate(series: Series, periods: int = 1) -> Series:
    """(value[t] / value[t-periods] - 1) * 100, i.e. percent change over `periods` observations."""
    out: Series = []
    for i, (d, v) in enumerate(series):
        if i < periods or v is None or series[i - periods][1] in (None, 0):
            out.append((d, None))
        else:
            prev = series[i - periods][1]
            out.append((d, (v / prev - 1) * 100))
    return out


def yoy(series: Series, obs_per_year: int) -> Series:
    """Year-over-year % change: growth_rate with periods = obs_per_year
    (12 for monthly, 4 for quarterly, 1 for annual, 365 for daily -- daily YoY
    is rarely meaningful and callers should prefer monthly-aggregated series).
    """
    return growth_rate(series, periods=obs_per_year)


def qoq(series: Series) -> Series:
    """Quarter-over-quarter % change. Series must already be at quarterly frequency."""
    return growth_rate(series, periods=1)


def mom(series: Series) -> Series:
    """Month-over-month % change. Series must already be at monthly frequency."""
    return growth_rate(series, periods=1)


def deflate(nominal_series: Series, price_index_series: Series, base_value: float = 100.0) -> Series:
    """Real value = nominal / (price_index / base_value).

    `price_index_series` must be aligned date-for-date with `nominal_series`
    (join on date before calling); mismatched dates produce None for that point.
    """
    index_by_date = dict(price_index_series)
    out: Series = []
    for d, nominal in nominal_series:
        idx = index_by_date.get(d)
        if nominal is None or idx in (None, 0):
            out.append((d, None))
        else:
            out.append((d, nominal / (idx / base_value)))
    return out


def rebase_index(series: Series, new_base_date: str, new_base_value: float = 100.0) -> Series:
    """Rebase an index series so that value at `new_base_date` == new_base_value.
    rebased[t] = value[t] / value[base_date] * new_base_value
    """
    base = dict(series).get(new_base_date)
    if base in (None, 0):
        raise ValueError(f"Cannot rebase: no non-zero value found at base date {new_base_date}")
    return [(d, (v / base * new_base_value) if v is not None else None) for d, v in series]


def seasonal_adjust_placeholder(series: Series) -> Series:
    """Seasonal adjustment is NOT implemented in stage 1 (needs enough history for
    X-13ARIMA-SEATS / STL to be meaningful, and only some of the stage-1 indicators
    are even seasonal in a way that matters). Returns the input unchanged and callers
    must tag the resulting metadata `transformation` field as 'seasonal_adjustment:none'
    rather than implying adjustment happened.
    """
    return list(series)


TRANSFORMATION_REGISTRY = {
    "level": level,
    "log": log,
    "difference": difference,
    "growth": growth_rate,
    "yoy": yoy,
    "qoq": qoq,
    "mom": mom,
    "deflate": deflate,
    "rebase_index": rebase_index,
}
