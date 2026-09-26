"""Item-level datasets for the gravity model of Kazakhstan's trade (added 2026-09-25): trade
by partner country, partner GDP and population, tariffs. Items are ISO 3166 alpha-3 codes
(dictionaries/partner_countries.csv maps BNS's Russian names). Checked live before wiring in:

- BNS «Основные показатели внешней торговли РК по странам» (indicator 312101, listing name
  19182): one xls/xlsx per edition, a sheet per year ('2025' or '12_2025'), partner rows from
  «Всего», thousand USD. Full-year editions are listed from data year 2021; the 2021
  edition's second sheet carries 2020. A listed partner with a blank cell (no flow that
  direction) is stored as 0 -- zeros matter to a PPML gravity estimate. Each data year is read from its FINAL edition (July, title «(2025г.)») when there is one, else
  the preliminary («январь-декабрь»); country rows sum exactly to «Всего» in every year.
  Mapping the names checked against WITS for 2023: 204 partners, differences above 25%
  only for four small flows.
- WITS TradeStats (UN Comtrade data), SDMX-JSON, no key: 1995-2023. Equal to BNS for the
  EAEU partners, but far BELOW it for non-EAEU flows in 2020-2022 (world exports 2021 53.1
  against 60.3 bn USD) -- use BNS from 2020.
- World Bank WDI API v2: GDP (current and constant 2015 USD) and population for every
  economy (aggregates dropped), 2000 onward.
- WITS TradeStats-Tariff: Kazakhstan's MFN and applied tariff averages, overall and by partner.
- The same World Bank API with source=3 serves the Worldwide Governance Indicators (rating
  models; codes GOV_WGI_*.EST since the 2025 WGI revision -- the old GE.EST answer error 120).
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
_CACHE: dict[str, bytes] = {}


def _get(url: str, timeout: int = 120) -> bytes:
    if url not in _CACHE:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        _CACHE[url] = resp.content
    return _CACHE[url]


def _without_prepared_stamp(content: bytes) -> bytes | None:
    """WITS stamps every answer with header.prepared (the request time), so two downloads of
    unchanged data never match byte for byte; compare them without it."""
    try:
        payload = json.loads(content)
        payload.get("header", {}).pop("prepared", None)
        return json.dumps(payload, sort_keys=True).encode()
    except (ValueError, AttributeError):
        return None


def _save_raw(agency: str, name: str, content: bytes, ext: str, info: dict) -> None:
    today = date.today()
    latest = raw_store.latest_raw_file(agency, name)
    path = None
    if ext == "json" and latest is not None and latest.suffix == ".json":
        stripped = _without_prepared_stamp(content)
        if stripped is not None and stripped == _without_prepared_stamp(latest.read_bytes()):
            path = latest                              # the same data as the last archived download
    if path is None:
        path = raw_store.save_raw_bytes(agency, name, today, ext, content)
    raw_store.write_download_manifest(agency, name, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, **info})


def _structural(ds: dict, what: str, url: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in {ds['agency']}/{ds['id']}",
        f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/gravity.py",
    ]))


def partner_names() -> dict[str, tuple[str, str]]:
    """casefolded Russian name -> (ISO3, English name)."""
    path = REPO_ROOT / "dictionaries" / "partner_countries.csv"
    with path.open(encoding="utf-8") as f:
        return {" ".join(r["name_ru"].split()).casefold(): (r["code"], r["name_en"]) for r in csv.DictReader(f)}


# ---------------------------------------------------------------- BNS trade by partner
BNS_LISTING_URL = ("https://stat.gov.kz/ru/industries/economy/foreign-market/spreadsheets/"
                   "?year={year}&name=19182&period=&type=spreadsheets")
BNS_FILE_URL = "https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
BNS_EDITION_TITLE = re.compile(r"по странам\s*\((?P<prelim>январь-декабрь\s*)?(?P<year>\d{4})\s*г\.?\)")
BNS_AGGREGATE_ROWS = {"всего", "страны снг", "страны еаэс", "страны вне еаэс", "остальные страны мира", "европа",
                      "страны ес", "страны вне ес", "азия", "америка", "африка", "австралия и океания"}
BNS_FIRST_LISTING_YEAR = 2021


def parse_bns_listing(page: str) -> list[dict]:
    out = []
    parts = re.split(r'<div class="divTableRow" id="bx_\d+_(\d+)">', page)
    for i in range(1, len(parts), 2):
        eid, body = parts[i], parts[i + 1]
        a = re.search(r'<a href="/api/iblock/element/\d+/file/\w+/">\s*(.*?)\s*</a>', body, re.S)
        d = re.search(r'text-right">\s*(\d\d\.\d\d\.\d{4})', body)
        if a:
            out.append({"eid": eid, "title": html.unescape(a.group(1).strip()),
                        "released": datetime.strptime(d.group(1), "%d.%m.%Y").date().isoformat() if d else ""})
    return out


def full_year_editions(listings: list[dict]) -> dict[int, dict]:
    """{data year: the edition to read}: the final one if published, else the latest preliminary."""
    best: dict[int, dict] = {}
    for r in listings:
        m = BNS_EDITION_TITLE.search(r["title"])
        if not m:
            continue                                   # «январь-июль 2026г.» and other partial years
        rank = (not m.group("prelim"), r["released"])
        year = int(m.group("year"))
        if year not in best or rank > best[year]["rank"]:
            best[year] = {**r, "rank": rank, "final": not m.group("prelim")}
    return best


def parse_bns_partner_file(content: bytes, measure: str) -> dict[int, dict[str, float]]:
    """{year: {partner name: thousand USD}} for 'exports' or 'imports', country rows only."""
    col = {"exports": 3, "imports": 5}[measure]
    book = pd.ExcelFile(io.BytesIO(content))
    out: dict[int, dict[str, float]] = {}
    for sheet in book.sheet_names:
        m = re.fullmatch(r"(?:12_)?(\d{4})", str(sheet).strip())
        if not m:
            continue
        grid = book.parse(sheet, header=None)
        first = grid.index[grid[0].astype(str).str.strip() == "Всего"]
        if len(first) == 0:
            continue
        rows: dict[str, float] = {}
        total = None
        for i in range(first[0], len(grid)):
            name = grid.iat[i, 0]
            if pd.isna(name):
                continue
            name = " ".join(str(name).split())
            cell = grid.iat[i, col]
            if pd.isna(cell):
                value = 0.0                            # a listed partner with a blank cell: no flow that way
            else:
                try:
                    value = float(cell)
                except (TypeError, ValueError):
                    continue
            if name == "Всего":
                total = value
            elif name.casefold() not in BNS_AGGREGATE_ROWS and not name.startswith("*"):
                rows[name] = value
        if total is not None and abs(sum(rows.values()) - total) > max(1.0, 1e-6 * total):
            raise ValueError(f"sheet {sheet}: countries sum to {sum(rows.values()):.1f}, «Всего» is {total:.1f}")
        out[int(m.group(1))] = rows
    return out


def fetch_bns_partner_trade(ds: dict) -> tuple[list[dict], dict]:
    names = partner_names()
    listings = []
    for year in range(BNS_FIRST_LISTING_YEAR, date.today().year + 1):
        listings += parse_bns_listing(_get(BNS_LISTING_URL.format(year=year), timeout=60).decode("utf-8", "replace"))
    editions = full_year_editions(listings)
    if len(editions) < 5:
        _structural(ds, f"only {len(editions)} full-year editions found on the listing pages", BNS_LISTING_URL)
    values: dict[int, dict[str, float]] = {}
    used = {}
    # Oldest edition first, so each data year ends up read from the edition chosen for it.
    for data_year, ed in sorted(editions.items()):
        url = BNS_FILE_URL.format(eid=ed["eid"])
        content = _get(url)
        _save_raw("bns", f"TRADE_BY_PARTNER_{ed['eid']}", content, "xlsx" if content[:2] == b"PK" else "xls",
                  {"source_url": url, "title": ed["title"], "released": ed["released"]})
        try:
            per_year = parse_bns_partner_file(content, ds["measure"])
        except ValueError as exc:
            _structural(ds, f"edition {ed['eid']}: {exc}", url)
        for year, rows in per_year.items():
            # A file also carries the previous year; that sheet is used only for a year with
            # no full-year edition of its own on the listings (2020, in the 2021 edition).
            if year == data_year or (year not in editions and year not in values):
                values[year] = rows
                used[year] = f"{ed['eid']} ({'final' if ed['final'] else 'preliminary'}, {ed['released']})"
    records, unknown = [], set()
    for year, rows in values.items():
        for name, v in rows.items():
            hit = names.get(name.casefold())
            if hit is None:
                unknown.add(name)
                continue
            records.append({"date": f"{year}-12-31", "region": "national", "item_code": hit[0],
                            "item_name": name, "value": v})
    if unknown:
        _structural(ds, f"partner names not in dictionaries/partner_countries.csv: {sorted(unknown)}", BNS_LISTING_URL)
    return records, {"frequency": "annual", "source_url": BNS_LISTING_URL.format(year="YYYY"),
                     "dataset_id": "bns/312101", "note": ds.get("note", "") + " Editions read: " +
                     "; ".join(f"{y}: {e}" for y, e in sorted(used.items())) + "."}


# ---------------------------------------------------------------- WITS
WITS_TRADE_URL = ("https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade/reporter/kaz/year/all/"
                  "partner/all/product/Total/indicator/{indicator}?format=JSON")
WITS_TARIFF_URL = ("https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-tariff/reporter/kaz/year/all/"
                   "partner/{partner}/product/Total/indicator/{indicator}?format=JSON")
# WITS still uses a few pre-ISO codes for partners.
WITS_LEGACY_CODES = {"ROM": "ROU", "SER": "SRB", "ZAR": "COD", "SUD": "SDN", "MNT": "MNE", "TMP": "TLS"}
WITS_AGGREGATES = {"WLD", "EAS", "ECS", "LCN", "MEA", "NAC", "SAS", "SSF", "UNS", "BLX", "OAS", "EUN", "ARB"}


def parse_sdmx_json(payload: dict) -> list[dict]:
    structure = payload["structure"]
    series_dims = structure["dimensions"]["series"]
    obs_dims = structure["dimensions"]["observation"]
    rows = []
    for key, series in payload["dataSets"][0]["series"].items():
        base = {d["id"]: d["values"][int(i)] for d, i in zip(series_dims, key.split(":"))}
        for okey, obs in series["observations"].items():
            row = {k: v["id"] for k, v in base.items()}
            row["_names"] = {k: v.get("name") for k, v in base.items()}
            for d, i in zip(obs_dims, okey.split(":")):
                row[d["id"]] = d["values"][int(i)]["id"]
            row["value"] = obs[0]
            rows.append(row)
    return rows


def fetch_wits_partner_trade(ds: dict) -> tuple[list[dict], dict]:
    url = WITS_TRADE_URL.format(indicator=ds["indicator"])
    content = _get(url)
    _save_raw("wits", ds["id"], content, "json", {"source_url": url})
    records = []
    for r in parse_sdmx_json(json.loads(content)):
        code = WITS_LEGACY_CODES.get(r["PARTNER"], r["PARTNER"])
        if code in WITS_AGGREGATES or r["value"] is None:
            continue
        records.append({"date": f"{r['TIME_PERIOD']}-12-31", "region": "national", "item_code": code,
                        "item_name": r["_names"].get("PARTNER") or code, "value": float(r["value"])})
    if len({r["item_code"] for r in records}) < 100:
        _structural(ds, f"only {len({r['item_code'] for r in records})} partners", url)
    return records, {"frequency": "annual", "source_url": url, "dataset_id": f"wits/tradestats-trade/{ds['indicator']}",
                     "note": ds.get("note", "")}


def fetch_wits_tariffs(ds: dict) -> tuple[list[dict], dict]:
    records = []
    for indicator in ds["indicators"]:
        url = WITS_TARIFF_URL.format(partner=ds.get("partner", "wld"), indicator=indicator)
        content = _get(url)
        _save_raw("wits", f"{ds['id']}_{indicator}", content, "json", {"source_url": url})
        for r in parse_sdmx_json(json.loads(content)):
            if r["value"] is None:
                continue
            if ds.get("partner", "wld") == "wld":
                code, name = indicator.replace("-", "_"), indicator
            else:
                code = WITS_LEGACY_CODES.get(r["PARTNER"], r["PARTNER"])
                if code in WITS_AGGREGATES:
                    continue
                name = r["_names"].get("PARTNER") or code
            records.append({"date": f"{r['TIME_PERIOD']}-12-31", "region": "national", "item_code": code,
                            "item_name": name, "value": float(r["value"])})
    if not records:
        _structural(ds, "no tariff observations", WITS_TARIFF_URL)
    return records, {"frequency": "annual", "source_url": WITS_TARIFF_URL.format(partner=ds.get("partner", "wld"),
                                                                                  indicator=",".join(ds["indicators"])),
                     "dataset_id": f"wits/tradestats-tariff/{ds.get('partner', 'wld')}", "note": ds.get("note", "")}


# ---------------------------------------------------------------- World Bank WDI
WDI_URL = ("https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&per_page=20000"
           "&date={first}:{year}")
WDI_COUNTRIES_URL = "https://api.worldbank.org/v2/country?format=json&per_page=400"


def fetch_wdi(ds: dict) -> tuple[list[dict], dict]:
    countries = json.loads(_get(WDI_COUNTRIES_URL))[1]
    economies = {c["id"]: c["name"] for c in countries if c.get("region", {}).get("value") != "Aggregates"}
    url = WDI_URL.format(indicator=ds["indicator"], first=ds.get("first_year", 2000), year=date.today().year)
    if ds.get("wb_source"):                      # e.g. 3 = Worldwide Governance Indicators (codes GOV_WGI_*)
        url += f"&source={ds['wb_source']}"
    content = _get(url)
    _save_raw("wb", ds["id"], content, "json", {"source_url": url})
    meta, rows = json.loads(content)
    if meta.get("pages", 1) > 1:
        _structural(ds, f"the answer spans {meta['pages']} pages (per_page too small)", url)
    records = [{"date": f"{r['date']}-12-31", "region": "world", "item_code": r["countryiso3code"],
                "item_name": economies[r["countryiso3code"]], "value": float(r["value"])}
               for r in rows if r.get("value") is not None and r.get("countryiso3code") in economies]
    if len({r["item_code"] for r in records}) < 180:
        _structural(ds, f"only {len({r['item_code'] for r in records})} economies with data", url)
    return records, {"frequency": "annual", "source_url": url, "dataset_id": f"wdi/{ds['indicator']}",
                     "note": ds.get("note", "") + f" WDI last updated {meta.get('lastupdated', '?')}.",
                     "release": meta.get("lastupdated")}


TABLES = {"bns_partner_trade": fetch_bns_partner_trade, "wits_partner_trade": fetch_wits_partner_trade,
          "wits_tariffs": fetch_wits_tariffs, "wdi": fetch_wdi}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    return TABLES[ds["table"]](ds)
