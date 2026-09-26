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


# ---------------------------------------------------------------- external debt service schedule
# formId=346 «External debt service schedule» (added 2026-09-25, for rating models: the debt
# falling due over the next two years). One vintage per quarter, dated as at report_date;
# the API keeps only the last two vintages (2026-01-01 and 2026-04-01 on 2026-09-25), so the
# earlier ones are carried forward from data/processed (the archive accumulates, as the
# pipeline's rolling-window sources do). Checked: the principal rows of a vintage sum to
# EXTERNAL_DEBT at that date (182 778.2 mln USD at 2026-04-01) -- enforced below.
SCHEDULE_SECTORS = {"General government": "GG", "Central Bank": "CB", "Banks": "BANKS", "Other sectors": "OTHER",
                    "Direct investment: Intercompany lending": "FDI_LOANS"}
SCHEDULE_TYPES = {"Principal (forecast)": "PRINCIPAL", "Interests  (forecast)": "INTEREST",
                  "Interests (forecast)": "INTEREST"}
SCHEDULE_PERIODS = {"on demand": "ON_DEMAND", "within 1-3 months": "M01_03", "within 4-6 months": "M04_06",
                    "within 7-9 months": "M07_09", "within 10-12 months": "M10_12", "within 13-15 months": "M13_15",
                    "within 16-18 months": "M16_18", "within 19-21 months": "M19_21", "within 22-24 months": "M22_24",
                    "after 2 years": "AFTER_2Y", "no information": "NO_INFO"}


def debt_schedule_records(rows: list[dict]) -> list[dict]:
    out, unknown = [], set()
    for r in rows:
        period = SCHEDULE_PERIODS.get((r.get("repayment_period") or "").strip())
        if r.get("memo_items"):
            sector, kind = "MEMO", "GOODS"
        else:
            sector = SCHEDULE_SECTORS.get(r.get("economy_sector_type"))
            kind = SCHEDULE_TYPES.get(r.get("repayment_type"))
        if None in (period, sector, kind):
            unknown.add((r.get("economy_sector_type"), r.get("repayment_type"), r.get("repayment_period"), r.get("memo_items")))
            continue
        name = (f"{r.get('memo_items', '').strip()} | {r['repayment_period']}" if sector == "MEMO"
                else f"{r['economy_sector_type']} | {r['repayment_type'].replace('  ', ' ')} | {r['repayment_period']}")
        out.append({"date": r["report_date"][:10], "region": dims.NATIONAL, "item_code": f"{sector}_{kind}_{period}",
                    "item_name": name, "value": float(r["amount"])})
    if unknown:
        raise validation.StructuralChangeError(f"nbk formId=346: unrecognised rows {sorted(map(str, unknown))[:5]}")
    return out


def fetch_debt_schedule(ds: dict) -> tuple[list[dict], dict]:
    import csv
    rows = nbk._fetch_nbk_form_paginated(ds["form_id"], ds["id"])
    records = debt_schedule_records(rows)
    if not records:
        raise validation.StructuralChangeError(f"nbk/{ds['id']}: no rows in formId={ds['form_id']}")
    # The principal rows must add up to the external debt stock published for the same date.
    debt_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "nbk" / "external_debt.csv"
    if debt_path.exists():
        with debt_path.open(encoding="utf-8") as f:
            stock = {r["date"]: float(r["value"]) for r in csv.DictReader(f)}
        for d in sorted({r["date"] for r in records}):
            principal = sum(r["value"] for r in records if r["date"] == d and "_PRINCIPAL_" in r["item_code"])
            if d in stock and abs(principal - stock[d]) > 1.0:
                raise validation.StructuralChangeError(
                    f"nbk/{ds['id']}: principal due at {d} sums to {principal:.1f}, EXTERNAL_DEBT is {stock[d]:.1f}")
    fresh = {r["date"] for r in records}
    kept = [r for r in dims.load_processed(ds["id"]) if r["date"] not in fresh]
    records += [{**r, "value": float(r["value"])} for r in kept]
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "quarterly", "source_url": f"{nbk.MONETARY_AGGREGATES_URL}?formId={ds['form_id']}",
        "dataset_id": f"formId={ds['form_id']}", "note": ds.get("note", "") +
        f" Vintages from the API: {sorted(fresh)}; carried forward from the archive: {sorted({r['date'] for r in kept})}."}
