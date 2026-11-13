"""Deposits in depository organisations by currency and holder, 1997-12 on (added 2026-11-13).

Source: the "records" JSON behind the NBK page «Депозиты в депозитных организациях» --
    https://nationalbank.kz/ru/depositoryorganizationsdeposits/depozity-v-depozitnyh-organizaciyah-/records
        ?beginMount=1&beginYear=1990&endMount=12&endYear=YYYY
the same mechanism as the monetary surveys (fetchers/nbk_records.py). One dict per month, million
KZT, stock at the END of the month named by the year-month of reporting_date (the day and hour
are noise: '1997-12-08', '2026-09-30 22:00:00'); each record is dated the first day of the NEXT
month, as the surveys and DEPOSITS_TOTAL are (the record '2026-09…' = DEPOSITS_TOTAL at
2026-10-01, 51 455 187).

It is the only source with the currency split for LEGAL ENTITIES over a long history: open-data
form 62 starts in 2021-12 and its legal-entity rows and total disagree with this page for all of
2022 and at the latest date (2022-06-01: 15 062 734 against 25 242 427), form 42 starts in 2023.

Items: TOTAL, KZT, FX, each also .LEGAL (non-bank legal entities) and .HOUSEHOLDS, and the
transferable / other split. Checked on every date (StructuralChangeError): total = KZT + FX,
each currency = legal entities + households, within 1 mln.
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import nbk  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

RECORDS_URL = "https://nationalbank.kz/ru/depositoryorganizationsdeposits/depozity-v-depozitnyh-organizaciyah-/records"
META = {"note_kz", "note_ru", "note_en", "published_at", "reporting_date"}
FIELDS = {  # NBK key: (item code, Russian name)
    "total_deposit": ("TOTAL", "Депозиты, всего"),
    "total_deposit_nc": ("KZT", "Депозиты в национальной валюте"),
    "total_deposit_nc_nb_le": ("KZT.LEGAL", "Депозиты в национальной валюте: небанковские юридические лица"),
    "total_deposit_nc_np": ("KZT.HOUSEHOLDS", "Депозиты в национальной валюте: физические лица"),
    "total_deposit_fc": ("FX", "Депозиты в иностранной валюте"),
    "total_deposit_fc_nb_le": ("FX.LEGAL", "Депозиты в иностранной валюте: небанковские юридические лица"),
    "total_deposit_fc_np": ("FX.HOUSEHOLDS", "Депозиты в иностранной валюте: физические лица"),
    "o_t_a_d_nb_le": ("TOTAL.LEGAL", "Депозиты небанковских юридических лиц"),
    "o_t_a_d_np": ("TOTAL.HOUSEHOLDS", "Депозиты физических лиц"),
    "transferable_deposit_nc": ("KZT.TRANSFERABLE", "Переводимые депозиты в национальной валюте"),
    "transferable_deposit_nc_nb_le": ("KZT.TRANSFERABLE.LEGAL", "Переводимые депозиты в национальной валюте: юридические лица"),
    "transferable_deposit_nc_np": ("KZT.TRANSFERABLE.HOUSEHOLDS", "Переводимые депозиты в национальной валюте: физические лица"),
    "other_deposit_nc": ("KZT.OTHER", "Другие депозиты в национальной валюте"),
    "other_deposit_nc_nb_le": ("KZT.OTHER.LEGAL", "Другие депозиты в национальной валюте: юридические лица"),
    "other_deposit_nc_np": ("KZT.OTHER.HOUSEHOLDS", "Другие депозиты в национальной валюте: физические лица"),
    "transferable_deposit_fc": ("FX.TRANSFERABLE", "Переводимые депозиты в иностранной валюте"),
    "transferable_deposit_fc_nb_le": ("FX.TRANSFERABLE.LEGAL", "Переводимые депозиты в иностранной валюте: юридические лица"),
    "transferable_deposit_fc_np": ("FX.TRANSFERABLE.HOUSEHOLDS", "Переводимые депозиты в иностранной валюте: физические лица"),
    "other_deposit_fc": ("FX.OTHER", "Другие депозиты в иностранной валюте"),
    "other_deposit_fc_nb_le": ("FX.OTHER.LEGAL", "Другие депозиты в иностранной валюте: юридические лица"),
    "other_deposit_fc_np": ("FX.OTHER.HOUSEHOLDS", "Другие депозиты в иностранной валюте: физические лица"),
}
IDENTITIES = (("TOTAL", ("KZT", "FX")), ("KZT", ("KZT.LEGAL", "KZT.HOUSEHOLDS")), ("FX", ("FX.LEGAL", "FX.HOUSEHOLDS")))


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"nbk/{ds['id']}: {what} ({RECORDS_URL})")


def as_at(reporting_date: str) -> str:
    """'2026-09-30 22:00:00' (the stock at the end of September) -> '2026-10-01'."""
    y, m = int(reporting_date[:4]), int(reporting_date[5:7])
    return date(y + (m == 12), m % 12 + 1, 1).isoformat()


def deposit_records(data: list[dict], ds: dict) -> list[dict]:
    if not isinstance(data, list) or not data or not all(isinstance(r, dict) and r.get("reporting_date") for r in data):
        _structural(ds, f"expected a list of records with reporting_date, got {str(data)[:200]}")
    unknown = {k for r in data for k in r} - META - set(FIELDS)
    if unknown:
        _structural(ds, f"new field keys {sorted(unknown)}: map them in nbk_deposits.FIELDS")
    out, seen = [], set()
    for r in data:
        when = as_at(str(r["reporting_date"]))
        if when in seen:
            _structural(ds, f"two records for the month before {when}")
        seen.add(when)
        vals = {FIELDS[k][0]: float(v) for k, v in r.items() if k in FIELDS and v is not None}
        for whole, parts in IDENTITIES:
            if whole in vals and all(p in vals for p in parts) and abs(vals[whole] - sum(vals[p] for p in parts)) > 1.0:
                _structural(ds, f"{whole} = {vals[whole]} but {' + '.join(parts)} = {sum(vals[p] for p in parts)} at {when}")
        out += [{"date": when, "region": dims.NATIONAL, "item_code": FIELDS[k][0], "item_name": FIELDS[k][1], "value": float(v)}
                for k, v in r.items() if k in FIELDS and v is not None]
    if len(seen) < ds.get("min_periods", 300):
        _structural(ds, f"only {len(seen)} monthly records")
    return sorted(out, key=lambda x: (x["item_code"], x["date"]))


def fetch(ds: dict) -> tuple[list[dict], dict]:
    params = {"beginMount": 1, "beginYear": 1990, "endMount": 12, "endYear": date.today().year}
    resp = nbk._download(RECORDS_URL, params)
    today = date.today()
    path = raw_store.save_raw_bytes(nbk.SOURCE, ds["id"], today, "json", resp.content)
    raw_store.write_download_manifest(nbk.SOURCE, ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": RECORDS_URL, "params": params,
        "raw_file": path.name if path is not None else None})
    try:
        data = resp.json()
    except ValueError as exc:
        _structural(ds, f"the records endpoint no longer returns JSON: {resp.text[:200]!r} ({exc})")
    return deposit_records(data, ds), {"frequency": "monthly", "source_url": RECORDS_URL, "dataset_id": "nbk-page/deposits-records",
                                       "note": ds.get("note", "")}
