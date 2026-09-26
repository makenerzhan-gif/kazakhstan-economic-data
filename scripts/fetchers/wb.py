"""World Bank — Commodity Markets: the Pink Sheet history (annual and monthly prices,
annual indices, nominal US dollars) and the Commodity Markets Outlook forecast table.

Files (verified live 2026-09-14/15 by downloading and reading each one):

  CMO page   https://www.worldbank.org/en/research/commodity-markets — lists the current
             file links. The document id in a thedocs.worldbank.org path changes with
             every release (…/5d903e…-0350012021/… was the January 2025 vintage,
             …/74e8be…-0050012026/… the September 2026 one), so the links are read off
             the page at run time and the last confirmed URL in config/dims.yaml is the
             fallback when the page cannot be read. The manifest records which was used.
  annual     CMO-Historical-Data-Annual.xlsx. 'Annual Prices (Nominal)': a row of series
             names, a row of units, then one row per year (1960–) with the year in the
             first column. 'Annual Indices (Nominal)': a four-row header in which each
             column's name sits on exactly one row (the group hierarchy), 2010=100.
  monthly    CMO-Historical-Data-Monthly.xlsx, 'Monthly Prices': same shape with 'YYYYMmm'
             rows; scripts/update_wb.py takes the Brent column from it (OIL_PRICE_BRENT).
  forecasts  CMO-<Month>-<Year>-Forecasts.xlsx — the page links the PDF, the xlsx sits at
             the same path (checked for April 2026). Sheet 'Forecast': a header row
             'Commodity … Unit 2024 2025 2026f 2027f …' (the percent-change and
             difference blocks further right repeat the 'f' years), an INDEXES block and
             a PRICES block with group-heading rows (no values) in between. Only the
             'f' columns are taken: the forecast datasets hold forecasts, the history
             datasets hold history.

Neither file carries series codes any more, so dictionaries/wb_commodities.csv and
wb_commodity_indices.csv define them (modelled on the Pink Sheet mnemonics) and their
regexes match the labels of both files ("Logs, Cameroon" in the history, "Logs,
Africa" in the forecast table; "Non-energy **" and "Non-Energy"). A column or row whose
label matches no entry is a structural change and stops the dataset — as for BNS. The
units row of the price sheets is checked against the dictionary's unit, so a series
that changes its unit stops the dataset rather than passing a number in a new scale.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, raw_store, validation  # noqa: E402
from fetchers import bns, bns_dims  # noqa: E402

SOURCE = "wb"
CMO_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
# Last confirmed links (2026-09-15); dims.yaml carries the same for the datasets it defines.
FALLBACK_MONTHLY = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
LINK = re.compile(r"https://thedocs\.worldbank\.org/[^\"'\s<>]+?/related/(CMO-[^\"'\s<>]+?\.(?:xlsx|pdf))")
FORECAST_PDF = re.compile(r"^CMO-[A-Za-z]+-\d{4}-Forecasts\.pdf$")
YEAR_CELL = re.compile(r"^\s*(\d{4})(f?)\s*$")
MONTH_CELL = re.compile(r"^\s*(\d{4})M(\d{2})\s*$")
RELEASED = re.compile(r"(Released|Updated on)[:\s]+(.+)", re.IGNORECASE)
UNIT_CANON = str.maketrans({"(": "", ")": ""})
PAGE_FILES = {"annual": "CMO-Historical-Data-Annual.xlsx", "monthly": "CMO-Historical-Data-Monthly.xlsx"}


# ---------------------------------------------------------------- locating the files

def discover_links(html: str) -> dict[str, str]:
    """{file name: url} for every CMO file the page links; first occurrence wins."""
    out: dict[str, str] = {}
    for m in LINK.finditer(html):
        out.setdefault(m.group(1), m.group(0))
    return out


def current_url(kind: str, fallback: str) -> tuple[str, bool]:
    """(url, discovered) — the link the CMO page carries today for `kind`
    ('annual' | 'monthly' | 'forecasts'), else the fallback."""
    try:
        links = discover_links(bns._download(CMO_PAGE).decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001 — the page is a convenience; the fallback is a confirmed link
        return fallback, False
    if kind == "forecasts":
        pdf = next((u for n, u in links.items() if FORECAST_PDF.match(n)), None)
        return (pdf[: -len(".pdf")] + ".xlsx", True) if pdf else (fallback, False)
    name = PAGE_FILES[kind]
    return (links[name], True) if name in links else (fallback, False)


def download(kind: str, fallback: str) -> tuple[bytes, str, list[str]]:
    """(content, url used, warnings). The discovered link is tried first; an HTTP error
    there (the xlsx-beside-the-pdf assumption failing for a new release, say) falls back
    to the confirmed link and says so."""
    url, discovered = current_url(kind, fallback)
    warnings = [] if discovered else [f"CMO page gave no link for {kind}; used the fallback {fallback}"]
    try:
        return bns._download(url), url, warnings
    except requests.HTTPError as exc:
        if url == fallback:
            raise
        warnings.append(f"discovered link {url} failed ({exc}); used the fallback {fallback}")
        return bns._download(fallback), fallback, warnings


def _save_raw(dataset_id: str, content: bytes, info: dict) -> None:
    today = date.today()
    raw_store.save_raw_bytes(SOURCE, dataset_id, today, "xlsx", content)
    raw_store.write_download_manifest(SOURCE, dataset_id, today, {"downloaded_at": datetime.now().isoformat(), **info})


# ---------------------------------------------------------------- parsing

def _structural(ds: dict, what: str, expected, actual) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in wb/{ds['id']} (sheet {ds.get('sheet')!r})",
        f"WHAT CHANGED: {what}", f"EXPECTED: {expected}", f"ACTUAL: {actual}",
        "ACTION REQUIRED: open the World Bank file, compare with the layout described in "
        "scripts/fetchers/wb.py, update the parser or dictionaries/wb_*.csv, then re-run.",
    ]))


def _period(cell) -> str | None:
    """ISO date for a period cell: a year (int or '2024') -> 31 December, 'YYYYMmm' -> the 1st."""
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return f"{int(cell)}-12-31" if 1900 <= cell <= 2100 else None
    s = str(cell or "").strip()
    m = MONTH_CELL.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    m = YEAR_CELL.match(s)
    return f"{m.group(1)}-12-31" if m and not m.group(2) else None


def _first_data_row(grid: list[list], ds: dict) -> int:
    i = next((i for i, row in enumerate(grid) if row and _period(row[0])), None)
    if i is None:
        _structural(ds, "no data row with a period in the first column", "rows starting with a year or 'YYYYMmm'", grid[:8])
    return i


def _match(label, dictionary: list[dict], ds: dict, unmatched: list) -> dict | None:
    hit = dims.match_item(label, dictionary, dims.normalise_label_en)
    if hit is None:
        unmatched.append(str(label).strip())
        return None
    return next(e for e in dictionary if e["code"] == hit[0])


def _unmatched(ds: dict, unmatched: list, where: str) -> None:
    if unmatched and ds.get("strict", True):
        _structural(ds, f"{where} whose label matches no dictionary entry",
                    f"every label in dictionaries/{ds['dictionary']}.csv", unmatched)


def _unit(cell) -> str:
    return re.sub(r"\s+", " ", str(cell or "").translate(UNIT_CANON).replace("cents", "¢")).strip().lower()


def release_note(grid: list[list]) -> str | None:
    """'Updated on September 02, 2026' / 'Released: April 2026' from the sheet's top rows."""
    for row in grid[:6]:
        for cell in row:
            m = RELEASED.search(str(cell or ""))
            if m:
                return m.group(2).strip()
    return None


def parse_prices(grid: list[list], ds: dict) -> list[dict]:
    """'Annual Prices (Nominal)' / 'Monthly Prices': names row, units row, period rows."""
    dictionary = dims.load_dictionary(ds["dictionary"])
    start = _first_data_row(grid, ds)
    if start < 2 or not any(isinstance(c, str) and c.strip() for c in grid[start - 2][1:]):
        _structural(ds, "no names row two rows above the first data row", "names row, units row, data", grid[max(0, start - 3):start + 1])
    names, units = grid[start - 2], grid[start - 1]
    columns: dict[int, dict] = {}
    unmatched: list[str] = []
    for j, label in enumerate(names):
        if j == 0 or not (isinstance(label, str) and label.strip()):
            continue
        entry = _match(label, dictionary, ds, unmatched)
        if entry is None:
            continue
        if entry.get("unit") and j < len(units) and _unit(units[j]) != _unit(entry["unit"]):
            _structural(ds, f"unit of {entry['code']} ({label.strip()!r}) changed", entry["unit"], str(units[j]))
        columns[j] = entry
    _unmatched(ds, unmatched, "series columns")
    records = []
    for row in grid[start:]:
        when = _period(row[0]) if row else None
        if when is None:
            continue
        for j, entry in columns.items():
            value = bns_dims._to_float(row[j]) if j < len(row) else None
            if value is not None:
                records.append({"date": when, "region": ds.get("region", "world"), "item_code": entry["code"],
                                "item_name": entry["name_ru"], "value": value})
    return records


def parse_indices(grid: list[list], ds: dict) -> list[dict]:
    """'Annual Indices (Nominal)': a multi-row header, each column named on exactly one row."""
    dictionary = dims.load_dictionary(ds["dictionary"])
    start = _first_data_row(grid, ds)
    header = [row for row in grid[:start] if not RELEASED.search(str(row[0] or "")) and any(isinstance(c, str) and c.strip() for c in row[1:])]
    width = max(len(r) for r in grid[:start + 1])
    columns: dict[int, dict] = {}
    unmatched: list[str] = []
    for j in range(1, width):
        labels = [r[j] for r in header if j < len(r) and isinstance(r[j], str) and r[j].strip()]
        if not labels:
            continue
        if len(labels) > 1:
            _structural(ds, f"column {j} carries several header labels", "one label per column", labels)
        entry = _match(labels[0], dictionary, ds, unmatched)
        if entry is not None:
            columns[j] = entry
    _unmatched(ds, unmatched, "index columns")
    records = []
    for row in grid[start:]:
        when = _period(row[0]) if row else None
        if when is None:
            continue
        for j, entry in columns.items():
            value = bns_dims._to_float(row[j]) if j < len(row) else None
            if value is not None:
                records.append({"date": when, "region": ds.get("region", "world"), "item_code": entry["code"],
                                "item_name": entry["name_ru"], "value": value})
    return records


def parse_forecasts(grid: list[list], ds: dict) -> list[dict]:
    """The CMO 'Forecast' sheet, one section ('prices' | 'indices') per dataset, 'f' years only."""
    dictionary = dims.load_dictionary(ds["dictionary"])
    hdr = next((i for i, row in enumerate(grid) if row and str(row[0] or "").strip().lower() == "commodity"), None)
    if hdr is None:
        _structural(ds, "no header row starting with 'Commodity'", "'Commodity … Unit 2024 2025 2026f 2027f'", grid[:6])
    years: dict[int, int] = {}
    for j, cell in enumerate(grid[hdr]):
        m = YEAR_CELL.match(str(cell or ""))
        if m and m.group(2) and int(m.group(1)) not in years:      # the first 'f' column per year = the level
            years[int(m.group(1))] = j
    if not years:
        _structural(ds, "no forecast ('YYYYf') columns in the header row", "at least one 'YYYYf' cell", grid[hdr])
    # Sub-groups are indented by putting the label in column B or C; the label is the first
    # text cell left of the 'Unit' column (or of the first year column when there is none).
    label_end = next((j for j, c in enumerate(grid[hdr]) if str(c or "").strip().lower() == "unit"), min(years.values()))
    wanted = ds["section"]
    section, unmatched, records = None, [], []
    for row in grid[hdr + 1:]:
        label = next((str(c).strip() for c in row[:label_end] if isinstance(c, str) and c.strip()), "")
        upper = label.upper()
        if upper.startswith("INDEXES"):
            section = "indices"
            continue
        if upper.startswith("PRICES"):
            section = "prices"
            continue
        values = {y: (bns_dims._to_float(row[j]) if j < len(row) else None) for y, j in years.items()}
        if not label or section != wanted or all(v is None for v in values.values()):
            continue                                          # blank line, group heading, notes, or the other section
        entry = _match(label, dictionary, ds, unmatched)
        if entry is None:
            continue
        for y, v in values.items():
            if v is not None:
                records.append({"date": f"{y}-12-31", "region": ds.get("region", "world"), "item_code": entry["code"],
                                "item_name": entry["name_ru"], "value": v, "transformation": "forecast"})
    _unmatched(ds, unmatched, f"{wanted} rows")
    return records


# ---------------------------------------------------------------- entry points

def fetch(ds: dict) -> tuple[list[dict], dict]:
    """Dimensional datasets (config/dims.yaml): table = annual_prices | annual_indices |
    forecast_prices | forecast_indices."""
    table = ds["table"]
    kind = "forecasts" if table.startswith("forecast") else ("monthly" if table.startswith("monthly") else "annual")
    content, url, warnings = download(kind, ds["fallback_url"])
    _save_raw(ds["id"], content, {"source_url": url, "sheet": ds["sheet"]})
    grids = bns_dims._sheets(content)
    if ds["sheet"] not in grids:
        _structural(ds, "sheet not in the workbook", ds["sheet"], list(grids))
    grid = grids[ds["sheet"]]
    if table in ("annual_prices", "monthly_prices"):
        records = parse_prices(grid, ds)
    elif table in ("annual_indices", "monthly_indices"):
        records = parse_indices(grid, ds)
    elif table in ("forecast_prices", "forecast_indices"):
        records = parse_forecasts(grid, ds)
    else:
        raise ValueError(f"{ds['id']}: unknown table {table!r}")
    n_items = len({r["item_code"] for r in records})
    if n_items < ds.get("min_items", 1):
        _structural(ds, "fewer items than expected", f">= {ds['min_items']} item codes", f"{n_items}: {sorted({r['item_code'] for r in records})}")
    release = release_note(grid)
    return records, {"frequency": ds["frequency"], "source_url": url, "dataset_id": f"{Path(url).name}#{ds['sheet']}",
                     "note": ds.get("note", "") + (f" File release: {release}." if release else ""),
                     "release": release, "warnings": warnings,
                     "transformation": "forecast" if kind == "forecasts" else "level"}


def fetch_brent_monthly() -> tuple[list[dict], dict]:
    """OIL_PRICE_BRENT for the scalar layer: the 'Crude oil, Brent' column of the monthly
    Pink Sheet, US dollars per barrel, monthly average of daily spot quotations."""
    content, url, warnings = download("monthly", FALLBACK_MONTHLY)
    _save_raw("OIL_PRICE_BRENT", content, {"source_url": url, "sheet": "Monthly Prices"})
    grids = bns_dims._sheets(content)
    ds = {"id": "OIL_PRICE_BRENT", "sheet": "Monthly Prices", "dictionary": "wb_commodities", "strict": True}
    if ds["sheet"] not in grids:
        _structural(ds, "sheet not in the workbook", ds["sheet"], list(grids))
    grid = grids[ds["sheet"]]
    records = [{"date": r["date"], "value": r["value"]} for r in parse_prices(grid, ds) if r["item_code"] == "CRUDE_BRENT"]
    if not records:
        _structural(ds, "no 'Crude oil, Brent' column", "CRUDE_BRENT among the series columns", grid[4][:6])
    release = release_note(grid)
    return records, {"frequency": "monthly", "source_url": url, "dataset_id": f"{Path(url).name}#Monthly Prices",
                     "note": "US dollars per barrel, monthly average of daily Brent (38° API) spot quotations as published in "
                             "the World Bank Pink Sheet (nominal). A world benchmark, not the Kazakh export price: KEBCO trades "
                             "at a differential to Brent." + (f" File release: {release}." if release else ""),
                     "release": release, "warnings": warnings}
