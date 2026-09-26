"""Writes the PROCESSED layer: one CSV per (agency, indicator) with columns
date,value,transformation. This is what scripts/lib/unified.py reads to build
the long/wide unified dataset.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import yaml

from . import periods

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_ROOT = REPO_ROOT / "data" / "processed"
INDICATORS_PATH = REPO_ROOT / "config" / "indicators.yaml"


# The label every year-to-date series carries in the `transformation` column. Until
# 2026-09-25 only GDP_NOMINAL said so; 30-odd other series flagged
# `cumulation: year_to_date` in indicators.yaml went out as plain "level".
YTD_TRANSFORMATION = "level (year-to-date cumulative, as published -- not decumulated to discrete quarters)"
YTD_TRANSFORMATION_MONTHLY = "level (year-to-date cumulative, as published -- not decumulated to discrete months)"


@lru_cache(maxsize=1)
def _indicators() -> dict[str, dict]:
    indicators = yaml.safe_load(INDICATORS_PATH.read_text(encoding="utf-8"))["indicators"]
    return {i["id"]: i for i in indicators}


def _observation_types() -> dict[str, str | None]:
    return {k: v.get("observation_type") for k, v in _indicators().items()}


def default_transformation(indicator_id: str, transformation: str) -> str:
    """"level" for a year-to-date series is restated as the explicit year-to-date label."""
    ind = _indicators().get(indicator_id, {})
    if transformation == "level" and ind.get("cumulation") == "year_to_date":
        return YTD_TRANSFORMATION if ind.get("frequency") == "quarterly" else YTD_TRANSFORMATION_MONTHLY
    return transformation


COLUMNS = ["date", "value", "transformation"]


def write_processed(agency: str, indicator_id: str, records: list[dict],
                    transformation: str = "level", frequency: str | None = None) -> Path:
    """Write one indicator's processed CSV.

    Dates are restated to the canonical convention here rather than in each
    fetcher: this is the ONE place every series passes through, so a new
    fetcher gets the convention without having to know about it, and no
    existing one had to be edited. See lib/periods.py for which
    frequencies are normalised and why annual deliberately is not.

    The indicator's `observation_type` is looked up here too: without it a
    point-in-time stock dated 2026-06-30 was restated to 2026-04-01, undoing the
    exemption the updater had just applied -- the National Fund's end-of-June
    portfolio landed a quarter before the state debt measured the same day.
    """
    if frequency:
        records = periods.normalise(records, frequency, _observation_types().get(indicator_id))
    out_dir = PROCESSED_ROOT / agency
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{indicator_id.lower()}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in records:
            # A record may carry its own label (an IMF projection year inside a series of
            # outturns); otherwise the series-wide one.
            writer.writerow({"date": r["date"], "value": r["value"],
                             "transformation": default_transformation(indicator_id, r.get("transformation") or transformation)})
    return path
