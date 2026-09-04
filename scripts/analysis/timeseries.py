"""Shared level-preparation for time-series passes that want a series' history
AS A LEVEL, not as-published-comparison or growth-rate -- today:
scripts/analysis/decompose.py (STL). Anticipated: a forecasting slice, which
wants the same level and the same two guardrails (lifecycle, IMF
forecast-year contamination) -- see analysis/README.md's note that
forecasting risks exactly that contamination if built before this exists.

Reads data/unified/macro_long.csv only -- same boundary as correlate.py.

NOT correlate.prepare_indicator: that one defaults to growth_rate for
anything not already a published comparison index. Decomposition (and
forecasting) want the level itself -- STL separates trend/seasonal/residual
OUT of the level, so growth-rate-ing first would hand it an already
partially-deseasonalized series.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from lib import transformations  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
UNIFIED_LONG = REPO_ROOT / "data" / "unified" / "macro_long.csv"
INDICATORS_YAML = REPO_ROOT / "config" / "indicators.yaml"

FREQUENCY_OFFSET = {"monthly": "MS", "quarterly": "QS"}


class SeriesGuardrailError(Exception):
    """Mirrors validation.StructuralChangeError's stop-loudly philosophy: raised
    when a series can't be safely reduced to a clean historical level rather
    than silently guessing.
    """


def load_indicators(path: Path = INDICATORS_YAML) -> dict[str, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))["indicators"]
    return {ind["id"]: ind for ind in data}


def load_long(path: Path = UNIFIED_LONG) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"date": str, "variable": str})


def _series_for(long_df: pd.DataFrame, indicator_id: str) -> pd.Series:
    """Raw (date -> value) for one indicator, sorted ascending, NaNs dropped.
    Same body as correlate._series_for -- kept here too rather than imported,
    since correlate.py is a feature-local module this one shouldn't depend on.
    """
    rows = long_df.loc[long_df["variable"] == indicator_id, ["date", "value"]].dropna()
    if rows.empty:
        raise SeriesGuardrailError(f"{indicator_id}: no data rows in {UNIFIED_LONG.name}")
    idx = pd.to_datetime(rows["date"])
    s = pd.Series(rows["value"].to_numpy(dtype=float), index=idx, name=indicator_id)
    return s.sort_index()


def _to_transform_series(s: pd.Series) -> transformations.Series:
    return [(d.strftime("%Y-%m-%d"), (None if pd.isna(v) else float(v))) for d, v in s.items()]


def _from_transform_series(rows: transformations.Series, name: str) -> pd.Series:
    dates = pd.to_datetime([d for d, _ in rows])
    values = [v if v is not None else float("nan") for _, v in rows]
    return pd.Series(values, index=dates, name=name)


def _check_gap_free(s: pd.Series, indicator_id: str, frequency: str) -> None:
    """Reindex onto a regular calendar grid; raise if that reveals a gap.

    STL (and any future forecaster) assumes row N means the same calendar
    position every cycle. All indicators this module has been used on so far
    are gap-free -- this check is what keeps that true as the pipeline
    re-runs daily and new months/quarters land, not a defense against a
    known problem today.
    """
    offset = FREQUENCY_OFFSET.get(frequency)
    if offset is None:
        raise SeriesGuardrailError(
            f"{indicator_id}: gap-checking is only implemented for monthly/quarterly "
            f"(got frequency={frequency!r})."
        )
    reindexed = s.asfreq(offset)
    if len(reindexed) != len(s):
        missing = reindexed[reindexed.isna()].index
        raise SeriesGuardrailError(
            f"{indicator_id}: history is not gap-free on a regular {offset} grid -- "
            f"missing {len(missing)} period(s), starting {missing[0].date()}. A gap "
            f"would silently misalign a seasonal-effect table built by calendar "
            f"position; fix the source gap or explicitly handle it before proceeding."
        )


def prepare_level(
    indicator_id: str,
    meta: dict,
    long_df: pd.DataFrame,
    *,
    acknowledged_lifecycle: dict[str, str] | None = None,
    forecast_cutoff_year: int | None = None,
) -> tuple[pd.Series, str]:
    """Decumulate (if cumulation == year_to_date) -> forecast cutoff (if an
    IMF international_projection series) -> verify gap-free on a regular
    calendar grid -> return the level AS-IS. Never applies growth_rate --
    decomposition and forecasting want the level itself.

    Returns (prepared series, human-readable description of what was done),
    same convention as correlate.prepare_indicator.

    Raises SeriesGuardrailError if:
    - meta['lifecycle'] is set and indicator_id isn't in acknowledged_lifecycle.
    - meta['category'] == 'international_projection' and forecast_cutoff_year
      is None (this series bakes IMF WEO forecast years into the same column
      as historical actuals).
    - the resulting level has a gap on its own frequency's regular grid.
    """
    acknowledged_lifecycle = acknowledged_lifecycle or {}

    if meta.get("lifecycle") and indicator_id not in acknowledged_lifecycle:
        raise SeriesGuardrailError(
            f"{indicator_id}: carries lifecycle={meta['lifecycle']!r} (a known structural "
            f"break in its history) and is not in the caller's acknowledged-lifecycle "
            f"overrides. Add it there with a note on why it's still safe to use, or "
            f"leave this indicator out."
        )

    s = _series_for(long_df, indicator_id)
    steps: list[str] = []

    if meta.get("category") == "international_projection":
        if forecast_cutoff_year is None:
            raise SeriesGuardrailError(
                f"{indicator_id}: category=international_projection -- this series bakes "
                f"IMF WEO forecast years into the same column as historical actuals. Pass "
                f"forecast_cutoff_year=<last actual year>, or leave this indicator out."
            )
        s = s[s.index.year <= forecast_cutoff_year]
        steps.append(f"actuals through {forecast_cutoff_year} (WEO forecast years excluded)")

    if meta.get("cumulation") == "year_to_date":
        s = _from_transform_series(
            transformations.decumulate_ytd(_to_transform_series(s)), indicator_id
        )
        steps.append("de-cumulated (year-to-date total -> own-period contribution)")

    _check_gap_free(s, indicator_id, meta.get("frequency", ""))
    steps.append("verified gap-free on a regular calendar grid")
    steps.append("level as published (no growth-rate transform)")

    return s, "; ".join(steps)
