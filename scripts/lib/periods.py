"""Canonical period dating for the processed layer.

WHY THIS EXISTS. Until 2026-09-03 there was no shared date helper: every fetcher
built its own observation dates, in 23 separate places across five modules, and
each module had settled on a different convention. BNS dated periods at their
END, NBK at their START, Minfin was mixed within itself, and the IMF module
contained two parsers that disagree with each other -- `_parse_annual_csv`
stamps a year at 1 January and `_parse_sdmx_csv` stamps it at 31 December.

Nothing caught it, because the only check that could have was
`validate_frequency`, which measures the GAP between observations. The gap is
91 days whether a quarter is dated 2026-01-01 or 2026-03-31, so the check
passes under either convention and is blind to the difference.

WHAT IT COST. CPI moved to a source that dated months at their end, and every
join between CPI and the monthly production, trade and labour series silently
returned nothing. A join that returns nothing raises nothing; it had to be
found by counting conventions by hand.

WHAT IS NORMALISED, AND WHAT DELIBERATELY IS NOT.

Monthly and quarterly are normalised to the period START. For those two the
question is purely cosmetic: 2026-03-31 and 2026-01-01 denote the same quarter,
so relabelling cannot change what an observation means, and the start form is
what 125 of 125 monthly and the large majority of quarterly series already use.

ANNUAL IS LEFT ALONE. It is the one case where the date may carry meaning
beyond the label. Minfin's TAX_ARREARS_TOTAL is недоимка -- a STOCK, naturally
read "as at" its date -- while PENSION_CONTRIBUTIONS_RECEIVED on the very same
sheet and the same date is поступления, a FLOW over a year. Moving a stock from
1 January to 31 December keeps the year label but changes what the number
asserts, and the bulletin does not say which reading applies. Guessing there
would be the kind of silent error this module exists to prevent, so annual
series keep the date their fetcher produced and the mixed convention is
reported rather than corrected.

IRREGULAR is untouched by definition: those dates are events (MPC decisions,
auctions), not periods.
"""
from __future__ import annotations

from datetime import date

NORMALISED_FREQUENCIES = ("monthly", "quarterly")
QUARTER_FIRST_MONTH = {1: 1, 2: 1, 3: 1, 4: 4, 5: 4, 6: 4,
                       7: 7, 8: 7, 9: 7, 10: 10, 11: 10, 12: 10}


def canonical_date(iso_date: str, frequency: str, observation_type: str | None = None) -> str:
    """Return `iso_date` restated at the start of the period it falls in.

    Monthly and quarterly only; every other frequency is returned unchanged.
    Raises nothing on a malformed date -- it is returned as given, so a parsing
    problem surfaces as a validation failure rather than as a crash here.
    """
    if frequency not in NORMALISED_FREQUENCIES:
        return iso_date
    if observation_type == "point_in_time":
        # A stock or a rate AS AT a date: the date IS the observation, not a
        # label for a period, so restating it would move the measurement. A
        # balance reported at 30 June is not a balance at 1 June.
        return iso_date
    try:
        y, m, _ = (int(p) for p in str(iso_date).split("-"))
        month = m if frequency == "monthly" else QUARTER_FIRST_MONTH[m]
        return f"{y:04d}-{month:02d}-01"
    except (ValueError, KeyError):
        return iso_date


def normalise(records: list[dict], frequency: str,
              observation_type: str | None = None) -> list[dict]:
    """Apply `canonical_date` across a record list, preserving order.

    `observation_type` comes from indicators.yaml where it has been VERIFIED
    against the source document. Where it is absent the series is normalised as
    a period label, which is the safe default for monthly and quarterly: those
    two frequencies are the only ones normalised at all, and a period-dated
    observation is what the overwhelming majority of them are. An unverified
    point-in-time series at those frequencies would be mis-shifted by up to a
    month, which is why the field exists and why 338 indicators are still
    marked as needing a source check rather than assumed.
    """
    if frequency not in NORMALISED_FREQUENCIES or observation_type == "point_in_time":
        return records
    return [{**r, "date": canonical_date(r.get("date", ""), frequency)} for r in records]


# `date_basis` in indicators.yaml: how the SOURCE dates a flow or an average.
# NEXT_PERIOD_START is the NBK open-data habit of stamping a period with the day
# AFTER it ends -- report_date 2020-04-01 carries Q1 2020 of the balance of
# payments, 2026-08-01 the July KASE turnover. The value is right, the label is
# one period late, and every lag in a VAR built on it is off by one.
NEXT_PERIOD_START = "next_period_start"


def shift_back_one_period(iso_date: str, frequency: str) -> str:
    """The start of the period BEFORE the one `iso_date` falls in (monthly, quarterly)."""
    if frequency not in NORMALISED_FREQUENCIES:
        return iso_date
    try:
        y, m, _ = (int(p) for p in str(iso_date).split("-"))
    except ValueError:
        return iso_date
    step = 1 if frequency == "monthly" else 3
    if frequency == "quarterly":
        m = QUARTER_FIRST_MONTH[m]
    m -= step
    if m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}-01"


def apply_date_basis(records: list[dict], frequency: str, date_basis: str | None) -> list[dict]:
    """Relabel a source's dates to the period the observation covers.

    NOT idempotent, unlike `normalise`: call it exactly once, on freshly fetched
    records, before `normalise` -- never on records read back from the processed
    layer, which already carry the covered period.
    """
    if date_basis != NEXT_PERIOD_START:
        return records
    return [{**r, "date": shift_back_one_period(r.get("date", ""), frequency)} for r in records]


def convention_of(iso_date: str, frequency: str) -> str:
    """'start', 'end' or 'other' -- what convention a single date follows.

    Used by the validator to report series whose dates are internally
    inconsistent, which is a real defect at any frequency, as opposed to a
    series that consistently uses the convention this project does not prefer.
    """
    try:
        y, m, d = (int(p) for p in str(iso_date).split("-"))
    except ValueError:
        return "other"
    if frequency == "monthly":
        first, last = 1, _last_day(y, m)
    elif frequency == "quarterly":
        qm = QUARTER_FIRST_MONTH[m]
        first = 1 if m == qm else None
        last = _last_day(y, m) if m == qm + 2 else None
    elif frequency == "annual":
        first = 1 if m == 1 else None
        last = 31 if m == 12 else None
    else:
        return "other"
    if first is not None and d == first:
        return "start"
    if last is not None and d == last:
        return "end"
    return "other"


def _last_day(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]
