"""U.S. Energy Information Administration — Short-Term Energy Outlook (STEO).

One file, verified live 2026-09-14: https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx,
the monthly-table workbook of the current STEO release (the per-table 2tab.xlsx and
the annual STEO_a.xlsx that older links point to answer 404). Sheets used:

  Dates   'Forecast Month -' <month year>, 'Last Historical Month---' <YYYYMM>: the
          release and the boundary between history and forecast.
  2tab    'Table 2. Energy Prices'. A 'Forecast date:' row carries the year over the
          first month of each year, the next row the month abbreviations, then one row
          per series with the EIA series id in column A (BREPUUS Brent spot average,
          WTIPUUS WTI, …) and the description in column B; monthly values across.

Values are stored monthly, dated the 1st of the month like the rest of the monthly
layer; months after the last historical month carry transformation 'forecast'. The
annual figure the outlook quotes (the "Brent spot price, annual average" of the
overview table) is the mean of the twelve monthly values — the model contract takes
it with `annual: mean`.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402
from fetchers import bns, bns_dims  # noqa: E402

SOURCE = "eia"
STEO_URL = "https://www.eia.gov/outlooks/steo/xls/STEO_m.xlsx"
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
YEAR = re.compile(r"^\s*(\d{4})(\.0)?\s*$")


def _structural(ds: dict, what: str, expected, actual) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in eia/{ds['id']} (sheet {ds.get('sheet')!r})",
        f"WHAT CHANGED: {what}", f"EXPECTED: {expected}", f"ACTUAL: {actual}",
        "ACTION REQUIRED: open STEO_m.xlsx, compare with the layout described in scripts/fetchers/eia.py, "
        "update the parser or the dataset's item list in config/dims.yaml, then re-run.",
    ]))


def read_dates(grid: list[list], ds: dict) -> tuple[str, int]:
    """(forecast month label, last historical month as YYYYMM) from the 'Dates' sheet."""
    label, last = None, None
    for row in grid:
        key = str(row[0] or "").strip().lower() if row else ""
        value = next((c for c in row[1:] if c is not None and str(c).strip()), None)   # the value's column varies
        if value is None:
            continue
        if key.startswith("forecast month"):
            label = str(value).strip()
        elif key.startswith("last historical month"):
            last = int(float(value))
    if label is None or last is None:
        _structural(ds, "'Dates' sheet without forecast month / last historical month", "both rows", grid[:8])
    return label, last


def parse_table(grid: list[list], ds: dict, last_historical: int) -> list[dict]:
    """Monthly records for the series ids listed in ds['items'] ({id: name_ru})."""
    hdr = next((i for i, row in enumerate(grid) if row and str(row[0] or "").strip().lower().startswith("forecast date")), None)
    if hdr is None or hdr + 1 >= len(grid):
        _structural(ds, "no 'Forecast date:' header row", "a year row over a month row", grid[:6])
    years, months = grid[hdr], grid[hdr + 1]
    columns: dict[int, tuple[int, int]] = {}
    year = None
    for j in range(1, max(len(years), len(months))):
        y = YEAR.match(str(years[j])) if j < len(years) and years[j] is not None else None
        if y:
            year = int(y.group(1))
        m = MONTHS.get(str(months[j] or "").strip().lower()[:3]) if j < len(months) else None
        if year is not None and m:
            columns[j] = (year, m)
    if len(columns) < 12:
        _structural(ds, "fewer than twelve month columns", "year over month header", [years[:16], months[:16]])
    wanted = dict(ds["items"])
    records, found = [], set()
    for row in grid[hdr + 2:]:
        code = str(row[0] or "").strip() if row else ""
        if code not in wanted:
            continue
        found.add(code)
        for j, (y, m) in columns.items():
            value = bns_dims._to_float(row[j]) if j < len(row) else None
            if value is None:
                continue
            records.append({"date": f"{y}-{m:02d}-01", "region": ds.get("region", "world"), "item_code": code,
                            "item_name": wanted[code], "value": value,
                            "transformation": "forecast" if y * 100 + m > last_historical else "level"})
    missing = sorted(set(wanted) - found)
    if missing:
        _structural(ds, "series ids not found in column A", sorted(wanted), f"missing {missing}")
    return records


def fetch(ds: dict) -> tuple[list[dict], dict]:
    url = ds.get("url", STEO_URL)
    content = bns._download(url)
    today = date.today()
    raw_store.save_raw_bytes(SOURCE, ds["id"], today, "xlsx", content)
    raw_store.write_download_manifest(SOURCE, ds["id"], today, {"downloaded_at": datetime.now().isoformat(), "source_url": url, "sheet": ds["sheet"]})
    grids = bns_dims._sheets(content)
    for name in ("Dates", ds["sheet"]):
        if name not in grids:
            _structural(ds, "sheet not in the workbook", name, list(grids))
    release, last_historical = read_dates(grids["Dates"], ds)
    records = parse_table(grids[ds["sheet"]], ds, last_historical)
    return records, {"frequency": ds["frequency"], "source_url": url, "dataset_id": f"STEO_m.xlsx#{ds['sheet']}",
                     "note": ds.get("note", "") + f" STEO release: {release}; last historical month {last_historical}.",
                     "release": release, "warnings": [], "transformation": "level (history) / forecast (months after the last historical month)"}
