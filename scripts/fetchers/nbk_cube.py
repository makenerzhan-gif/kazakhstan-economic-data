"""Item-level series summed from the NBK's fully disaggregated open-data forms.

Added 2026-11-07. Some data.nationalbank.kz forms publish no totals at all: every row is one
cell of a cross-tabulation (form 488, bank loans to the economy, crosses industry x purpose x
currency x maturity x region x borrower size x overdue x bank/non-bank; form 287, gross FDI
inflow, is one row per investor country). sources.yaml recorded 488/493 as «pure microdata,
no aggregation field» in 2026-08 — the rows are a partition, so a total is their sum. This
fetcher sums them into the items a dataset asks for.

A dataset (config/dims.yaml, `fetcher: nbk_cube`) gives
  form_id     the open-data form;
  filters     {field: value} pinned (compared without case and outer spaces, like nbk_dims);
  levels      a list of field lists; each level makes items whose code is the codes of its
              fields joined by «.» (level [industry] -> «C», [industry, sub_industry_1] -> «C.FOOD»);
  codes       {field: {raw value: code}} or {field: "countries"} (dictionaries/partner_countries.csv
              by English name, plus COUNTRY_ALIASES); a raw value missing from its map stops the
              dataset; a value mapped to null is dropped from that level (still in the total);
              a value mapped to "" (also the key "" for an empty field) contributes nothing to the
              item code, so a form's aggregation levels (form 27: all borrowers / by borrower /
              by purpose, each with its own empty fields) become items of different lengths;
              an empty field with no "" key drops the row from that level only;
  distinct    true: a rates form -- one value per item and date (a repeated row must carry the same
              value; two different values stop the dataset);
  sum_check   false: the levels are not checked against the total (rates, overlapping levels);
  field_aliases {level field: row field}: the same row field read through a second code map;
  names       optional {field: {raw value: Russian name}} for item names;
  total       optional item code for the sum of all filtered rows;
  date_basis  optional, as in indicators.yaml (next_period_start: the NBK stamps a flow with the
              day after its period);
  lookback_months  optional: once the dataset has data, fetch only report dates from that many
              months back (the API's startDate) and keep the older stored values. Form 488 has
              315 000 rows; the full download is for the first run.

A level whose items cover every filtered row must add up to the total (checked per date).
The fetched pages are archived gzip-compressed (the canonical form of lib/nbk_pages).
"""
from __future__ import annotations

import csv
import gzip
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import nbk  # noqa: E402
from lib import dims, nbk_pages, periods, raw_store, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_SIZE = 5000          # the API accepts it (checked 2026-11-07: 4 287 rows in one 2.5-second call)

# NBK spellings that differ from dictionaries/partner_countries.csv's English names, and the
# entities the dictionary does not have (codes as in the World Bank / ISO lists).
COUNTRY_ALIASES = {
    "american (eastern) samoa": "ASM", "czech republic": "CZE", "gibraltar (british)": "GIB",
    "hong kong special administrative region of china": "HKG", "iran, islamic republic": "IRN",
    "moldova, republic": "MDA", "new caledonia (french)": "NCL", "republic of the congo": "COG",
    "russia": "RUS", "samoa, independent state": "WSM", "syrian arab republic": "SYR",
    "the republic of korea": "KOR", "turks and caicos (brit.)": "TCA", "türkiye": "TUR", "usa": "USA",
    "vietnam": "VNM", "virgin islands (usa)": "VIR",
}
EXTRA_COUNTRIES = {  # raw name: (code, Russian name)
    "aruba": ("ABW", "Аруба"), "channel islands": ("CHI", "Нормандские острова"),
    "guinea-bissau": ("GNB", "Гвинея-Бисау"), "netherlands antilles": ("ANT", "Нидерландские Антилы"),
    "international organizations": ("INTORG", "Международные организации"),
    "not determined by country": ("UNALLOCATED", "Страна не определена"),
}

_PAGES: dict[tuple[str, str | None], list[dict]] = {}


def _norm(text) -> str:
    return " ".join(str(text or "").split()).casefold()


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"nbk/{ds['id']}: {what} (formId={ds['form_id']})")


def _countries() -> dict[str, tuple[str, str]]:
    with (REPO_ROOT / "dictionaries" / "partner_countries.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_code = {r["code"]: r["name_ru"] for r in rows}
    out = {_norm(r["name_en"]): (r["code"], r["name_ru"]) for r in rows}
    out.update({k: (c, by_code[c]) for k, c in COUNTRY_ALIASES.items()})
    out.update(EXTRA_COUNTRIES)
    return out


def fetch_pages(form_id: str, start: str | None = None) -> list[dict]:
    """All pages of a form (from report date `start` on, when given), once per process."""
    key = (form_id, start)
    if key not in _PAGES:
        pages, n, page = [], 0, 0
        while True:
            params = {"formId": form_id, "page": str(page), "pageSize": str(PAGE_SIZE)}
            if start:
                params["startDate"] = start
            resp = requests.get(nbk.MONETARY_AGGREGATES_URL, headers=nbk.HEADERS, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            pages.append(data)
            n += len(data["rows"])
            if n >= data["totalRows"] or not data["rows"]:
                break
            page += 1
        _PAGES[key] = pages
    return _PAGES[key]


def _code_maps(ds: dict) -> dict[str, dict[str, tuple[str | None, str]]]:
    """{field: {normalised raw value: (code or None, item name)}}."""
    out = {}
    for field, spec in ds["codes"].items():
        if spec == "countries":
            out[field] = _countries()
            continue
        names = {_norm(k): v for k, v in ds.get("names", {}).get(field, {}).items()}
        out[field] = {_norm(raw): (code, names.get(_norm(raw), str(raw).strip())) for raw, code in spec.items()}
    return out


def cube_records(rows: list[dict], ds: dict) -> list[dict]:
    filters = {k: _norm(v) for k, v in ds.get("filters", {}).items()}
    maps = _code_maps(ds)
    aliases = ds.get("field_aliases", {})      # {level field: row field}: one row field under two code maps
    levels = ds["levels"]
    sums: dict[tuple[str, str], float] = defaultdict(float)
    names: dict[str, str] = {}
    totals: dict[str, float] = defaultdict(float)
    level_sums = [defaultdict(float) for _ in levels]
    complete = [True] * len(levels)
    unknown = set()
    for r in rows:
        if any(_norm(r.get(k)) != v for k, v in filters.items()) or r.get("amount") in (None, ""):
            continue
        when, value = r["report_date"][:10], float(r["amount"])
        totals[when] += value
        for i, level in enumerate(levels):
            codes, labels, done = [], [], 0
            for field in level:
                raw = _norm(r.get(aliases.get(field, field)))
                if not raw and "" not in maps[field]:
                    break
                hit = maps[field].get(raw)
                if hit is None:
                    unknown.add((field, str(r.get(field)).strip()))
                    break
                if hit[0] is None:
                    break
                done += 1
                if hit[0] == "":
                    continue
                codes.append(hit[0])
                labels.append(hit[1])
            if done < len(level):
                complete[i] = False
                continue
            code = ".".join(codes)
            if ds.get("distinct") and (code, when) in sums:
                if abs(sums[(code, when)] - value) > 1e-6 * max(1.0, abs(value)):
                    _structural(ds, f"two different values for item {code} at {when}: {sums[(code, when)]} and {value}")
                continue                                  # the form repeats a row (486 prints 1997-2002 twice)
            sums[(code, when)] += value
            names[code] = " | ".join(labels)
            level_sums[i][when] += value
    if unknown:
        _structural(ds, f"values not in the dataset's code maps (config/dims.yaml): {sorted(unknown)}")
    for i, level in enumerate(levels):
        if not complete[i] or ds.get("sum_check") is False:
            continue
        for when, total in totals.items():
            if abs(level_sums[i][when] - total) > 1e-6 * max(1.0, abs(total)):
                _structural(ds, f"level {level} sums to {level_sums[i][when]} at {when}, the rows to {total}")
    out = [{"date": d, "region": dims.NATIONAL, "item_code": c, "item_name": names[c], "value": v}
           for (c, d), v in sums.items()]
    if ds.get("total"):
        out += [{"date": d, "region": dims.NATIONAL, "item_code": ds["total"], "item_name": ds.get("total_name", "Всего"),
                 "value": v} for d, v in totals.items()]
    return out


def _start(ds: dict) -> str | None:
    months = ds.get("lookback_months")
    if not months or not dims.load_processed(ds["id"]):
        return None
    today = date.today()
    y, m = divmod(today.year * 12 + today.month - 1 - int(months), 12)
    return date(y, m + 1, 1).isoformat()


def fetch(ds: dict) -> tuple[list[dict], dict]:
    start = _start(ds)
    pages = fetch_pages(ds["form_id"], start)
    rows = [r for p in pages for r in p["rows"]]
    today = date.today()
    path = raw_store.save_raw_bytes(nbk.SOURCE, ds["id"], today, "json.gz",
                                    gzip.compress(nbk_pages.canonical_form_bytes(pages), mtime=0))
    raw_store.write_download_manifest(nbk.SOURCE, ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": nbk.MONETARY_AGGREGATES_URL,
        "form_id": ds["form_id"], "start_date": start, "n_pages": len(pages), "total_rows": pages[0]["totalRows"],
        "raw_file": path.name if path is not None else None, "raw_format": nbk_pages.CANONICAL_FORMAT + " (gzip)",
        "raw_normalisation": nbk_pages.NORMALISATION})
    if not rows:
        _structural(ds, f"no rows{' from ' + start if start else ''}")
    records = cube_records(rows, ds)
    if ds.get("date_basis"):
        records = periods.apply_date_basis(records, ds["frequency"], ds["date_basis"])
    n_items = len({r["item_code"] for r in records})
    if n_items < ds.get("min_items", 1):
        _structural(ds, f"only {n_items} items")
    kept = []
    if start:
        fresh = {r["date"] for r in records}
        kept = [{"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
                 "value": float(r["value"])} for r in dims.load_processed(ds["id"]) if r["date"] < min(fresh)]
    note = ds.get("note", "") + (f" Report dates from {start} fetched; earlier values kept from the archive." if start else "")
    return sorted(records + kept, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": ds["frequency"], "source_url": f"{nbk.MONETARY_AGGREGATES_URL}?formId={ds['form_id']}",
        "dataset_id": f"formId={ds['form_id']}", "note": note}
