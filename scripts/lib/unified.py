"""Build the unified dataset in long and wide format (MASTER TASK section 9).

Long format: date, country, region, frequency, variable, value, unit, source,
             source_version, transformation, last_updated
Wide format: date, <one column per indicator id>

Both are derived purely from data/processed/** + metadata/** — never from raw
directly, and never invent a row for a period that isn't actually in processed data.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_ROOT = REPO_ROOT / "data" / "processed"
UNIFIED_ROOT = REPO_ROOT / "data" / "unified"
METADATA_ROOT = REPO_ROOT / "metadata"

LONG_COLUMNS = [
    "date", "country", "region", "frequency", "variable", "value", "unit",
    "source", "source_version", "transformation", "last_updated",
]


def _load_processed_series(agency: str, indicator_id: str) -> list[dict]:
    path = PROCESSED_ROOT / agency / f"{indicator_id.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_long(indicators: list[dict]) -> list[dict]:
    """`indicators` is the parsed config/indicators.yaml `indicators` list."""
    rows: list[dict] = []
    for ind in indicators:
        agency, ind_id = ind["agency"], ind["id"]
        meta = json.loads((METADATA_ROOT / agency / f"{ind_id.lower()}.json").read_text(encoding="utf-8")) \
            if (METADATA_ROOT / agency / f"{ind_id.lower()}.json").exists() else {}
        for rec in _load_processed_series(agency, ind_id):
            rows.append({
                "date": rec.get("date"),
                "country": "KZ",
                "region": "national",
                "frequency": ind.get("frequency"),
                "variable": ind_id,
                "value": rec.get("value"),
                "unit": ind.get("unit"),
                "source": agency,
                "source_version": meta.get("download_date"),
                "transformation": rec.get("transformation", "level"),
                "last_updated": meta.get("last_update_date"),
            })
    rows.sort(key=lambda r: (r["date"] or "", r["variable"]))
    return rows


def write_long_csv(rows: list[dict], path: Path | None = None) -> Path:
    path = path or (UNIFIED_ROOT / "macro_long.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LONG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_wide(long_rows: list[dict]) -> tuple[list[str], list[dict]]:
    """Pivot long rows to one column per variable, one row per date.
    Returns (fieldnames, rows). Dates with no data for a given variable get ''.
    """
    variables = sorted({r["variable"] for r in long_rows})
    by_date: dict[str, dict] = {}
    for r in long_rows:
        by_date.setdefault(r["date"], {})[r["variable"]] = r["value"]
    fieldnames = ["date"] + variables
    rows = []
    for d in sorted(by_date):
        row = {"date": d}
        for v in variables:
            row[v] = by_date[d].get(v, "")
        rows.append(row)
    return fieldnames, rows


def write_wide_csv(fieldnames: list[str], rows: list[dict], path: Path | None = None) -> Path:
    path = path or (UNIFIED_ROOT / "macro_wide.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
