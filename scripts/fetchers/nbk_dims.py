"""Item-level NBK series: the enterprise monitoring survey by sector (open-data forms).

Added 2026-09-25. The scalar CAPACITY_UTILIZATION (fetchers/nbk.py) keeps only the
'All sectors' row of formId=369; the same form carries the weighted-average capacity
utilisation of 13 sectors, quarterly from 2016-Q2, dated as the scalar is (report_date,
the first day of the survey quarter). Sectors are mapped to ОКЭД letters; «N.R.S» is
the NBK's pool of sections N, R and S. An unknown sector stops the dataset.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import nbk  # noqa: E402
from lib import dims, validation  # noqa: E402

SURVEY_SECTORS = {
    "All sectors": "TOTAL", "Agriculture": "A", "Mining": "B", "Manufacturing": "C", "Electricity supply": "D",
    "Water supply": "E", "Construction": "F", "Trade": "G", "Transport and warehousing": "H",
    "Accommodation and food service": "I", "Information and communication": "J", "Real estate activities": "L",
    "Professional, scientific and technical activities": "M", "N.R.S": "NRS",
}


def survey_records(rows: list[dict], indicator_code: str) -> list[dict]:
    out, unknown = [], set()
    for r in rows:
        if r.get("indicator_code") != indicator_code or r.get("amount") in (None, ""):
            continue
        code = SURVEY_SECTORS.get(r.get("industry"))
        if code is None:
            unknown.add(r.get("industry"))
            continue
        out.append({"date": r["report_date"][:10], "region": dims.NATIONAL, "item_code": code,
                    "item_name": r["industry"], "value": float(r["amount"])})
    if unknown:
        raise validation.StructuralChangeError(
            f"nbk survey {indicator_code!r}: sectors not in fetchers/nbk_dims.SURVEY_SECTORS: {sorted(unknown)}")
    return sorted(out, key=lambda r: (r["item_code"], r["date"]))


def fetch(ds: dict) -> tuple[list[dict], dict]:
    rows = nbk._fetch_nbk_form_paginated(ds["form_id"], ds["id"])
    records = survey_records(rows, ds["indicator_code"])
    if len({r["item_code"] for r in records}) < ds.get("min_items", 10):
        raise validation.StructuralChangeError(
            f"nbk/{ds['id']}: only {len({r['item_code'] for r in records})} sectors in formId={ds['form_id']}")
    return records, {"frequency": "quarterly", "source_url": f"{nbk.MONETARY_AGGREGATES_URL}?formId={ds['form_id']}",
                     "dataset_id": f"formId={ds['form_id']},indicator_code={ds['indicator_code']}",
                     "note": ds.get("note", "")}
