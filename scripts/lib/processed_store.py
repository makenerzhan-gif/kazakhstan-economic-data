"""Writes the PROCESSED layer: one CSV per (agency, indicator) with columns
date,value,transformation. This is what scripts/lib/unified.py reads to build
the long/wide unified dataset.
"""
from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_ROOT = REPO_ROOT / "data" / "processed"

COLUMNS = ["date", "value", "transformation"]


def write_processed(agency: str, indicator_id: str, records: list[dict], transformation: str = "level") -> Path:
    out_dir = PROCESSED_ROOT / agency
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{indicator_id.lower()}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for r in records:
            writer.writerow({"date": r["date"], "value": r["value"], "transformation": transformation})
    return path
