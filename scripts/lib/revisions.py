"""Revision tracking (MASTER TASK section 10).

When a re-download shows a previously published value has changed, we record
the old value, new value, date of change, source, and reason (if known) under
metadata/revisions/ — and we never delete the old raw file that had the old value.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISIONS_ROOT = REPO_ROOT / "metadata" / "revisions"


@dataclass
class Revision:
    indicator_id: str
    period: str          # the observation date/period that was revised
    old_value: float
    new_value: float
    detected_date: str   # ISO date this revision was detected by the pipeline
    source: str
    reason: str = "not stated by source"


def detect_revisions(indicator_id: str, source: str, old_records: list[dict],
                      new_records: list[dict], detected_date: date) -> list[Revision]:
    old_by_period = {r["date"]: r.get("value") for r in old_records}
    revisions: list[Revision] = []
    for r in new_records:
        period, new_val = r["date"], r.get("value")
        old_val = old_by_period.get(period)
        if old_val is not None and new_val is not None and float(old_val) != float(new_val):
            revisions.append(Revision(
                indicator_id=indicator_id,
                period=period,
                old_value=float(old_val),
                new_value=float(new_val),
                detected_date=detected_date.isoformat(),
                source=source,
            ))
    return revisions


def append_revisions(revisions: list[Revision]) -> Path | None:
    if not revisions:
        return None
    REVISIONS_ROOT.mkdir(parents=True, exist_ok=True)
    path = REVISIONS_ROOT / f"{revisions[0].indicator_id.lower()}_revisions.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for rev in revisions:
            f.write(json.dumps(asdict(rev), ensure_ascii=False) + "\n")
    return path
