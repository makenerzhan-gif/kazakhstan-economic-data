"""Bureau of National Statistics — dimensional tables (national accounts by section,
component and ownership form; population, labour and investment by region), read
from the xlsx export of each dynamic table.

Four sheet layouts cover all of config/dims.yaml (verified on the live files
2026-09-14; positions quoted below are what was seen, the parsers locate rows and
columns by content, not by position):

periods_across   one row per label, periods across the columns. The label is an
                 item (4439/4440/4441, 4452–4455, 4435–4437; sheet headers such as
                 "1 квартал 2024г.", "2024 год", " 2025 год7)8)") or a region
                 (5926, 5546, 5549, 102791–102800; headers "2024 год" or plain
                 "2024" / 2024.0). Quarterly columns are year-to-date and skipped.
region_blocks    one block per region introduced by a row with the КАТО code in
                 column A and the region name in column B, then one row per period
                 inside the block, one column per item. Item codes sit on the row
                 under the names (5931: B, 05 … 33, D, E) or come from the names
                 through the dictionary (5927 sections + ВРП + ЧН, 450904 sections).
year_subcolumns  one header cell per year spanning several sub-columns; sub_offset
                 picks the sub-column. Rows are items (4448 total/illegal, 4446 four
                 ownership columns, 5547 value/% pairs, 5831 five quarterly columns
                 with "год" last) or regions (102790, 443430/435/438: всего/мужчины/
                 женщины, district rows present and ignored).
group_blocks     6576: group label rows («Все население», «Мужчины», «Городское
                 население» …) each followed by the country row and one row per
                 region; the item is the group (ALL, URBAN, RURAL, ALL_MEN …).

Every data row must resolve to an item (or a region) through its dictionary; an
unresolved label is reported as a structural change and stops that dataset — a
renamed or added line in a BNS table is exactly the event that must not pass
silently. Datasets whose sheets carry rows below the region level (districts) say
`strict: false` and skip what does not resolve.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402
from fetchers import bns  # noqa: E402

# Anchored at the start on purpose: the income tables label quarters "1 квартал 2025 года",
# which CONTAINS "2025 год" — an unanchored search took Q1 for the annual value.
YEAR_IN_LABEL = re.compile(r"^\s*(\d{4})\s*год")
FOOTNOTE_ROW = re.compile(r"^\s*(\d\)|\*)")
MISSING = {"", "-", "–", "—", "…", "...", "..", "x", "х"}


def _to_float(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "").replace(" ", "")
    if s.lower() in MISSING:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None                                      # "в 4 раза" and the like


OLE2_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def is_legacy_xls(content: bytes) -> bool:
    """BNS serves some tables (5792, 8150, 8154, 8160, 8166) as legacy .xls (OLE2), not zip-based xlsx."""
    return content[:8] == OLE2_SIGNATURE


def _sheets(content: bytes) -> dict[str, list[list]]:
    out: dict[str, list[list]] = {}
    if is_legacy_xls(content):
        import xlrd
        book = xlrd.open_workbook(file_contents=content)
        for sh in book.sheets():
            out[sh.name] = [[(None if v == "" else v) for v in sh.row_values(r)] for r in range(sh.nrows)]
        return out
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    for ws in wb.worksheets:
        out[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return out


def _pick_sheets(grids: dict[str, list[list]], ds: dict) -> list[tuple[str, list[list]]]:
    if "sheets" in ds:
        missing = [s for s in ds["sheets"] if s not in grids]
        if missing:
            _structural(ds, f"sheet(s) {missing} not in the workbook", f"sheets {ds['sheets']}", list(grids))
        return [(s, grids[s]) for s in ds["sheets"]]
    pat = re.compile(ds["sheet_match"])
    hits = [(n, g) for n, g in grids.items() if pat.search(n)]
    if len(hits) != 1:
        _structural(ds, "sheet name pattern did not match exactly one sheet", ds["sheet_match"], list(grids))
    return hits


def _structural(ds: dict, what: str, expected, actual) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in bns/{ds['id']} (element {ds['element_id']})",
        f"WHAT CHANGED: {what}",
        f"EXPECTED: {expected}",
        f"ACTUAL: {actual}",
        "ACTION REQUIRED: open the xlsx export, compare with the layout described in "
        "scripts/fetchers/bns_dims.py, update the parser or dictionaries/, then re-run.",
    ]))


def _year_regex(ds: dict) -> re.Pattern:
    return re.compile(ds["year_regex"]) if ds.get("year_regex") else YEAR_IN_LABEL


def _annual_columns(row: list, year_regex: re.Pattern) -> dict[int, int]:
    """{year: column index} for the header cells that name a whole year."""
    cols = {}
    for j, cell in enumerate(row):
        if cell is None:
            continue
        m = year_regex.search(str(cell))
        if m and int(m.group(1)) not in cols:
            cols[int(m.group(1))] = j
    return cols


def _header_row(grid: list[list], year_regex: re.Pattern, ds: dict) -> int:
    i = next((i for i, row in enumerate(grid) if len(_annual_columns(row, year_regex)) >= 2), None)
    if i is None:
        _structural(ds, "no header row with at least two year cells", "a row of period labels", grid[:6])
    return i


def _item(label, ds: dict, dictionary: list[dict] | None) -> tuple[str, str] | None:
    """(code, name) for an item label: dataset overrides first, then the dictionary."""
    norm = dims.normalise_label(label)
    overrides = ds.get("label_overrides") or {}
    if norm in overrides:
        code = overrides[norm]
        name = next((e["name_ru"] for e in (dictionary or []) if e["code"] == code), str(label).strip())
        return code, name
    return dims.match_item(label, dictionary) if dictionary else None


def _row_key(label, ds: dict, dictionary, unmatched: list, row: list | None = None) -> tuple[str, str, str] | None:
    """(region, item_code, item_name) for a data row, by the dataset's row dimension."""
    if ds.get("row_dimension") == "region":
        reg = dims.match_region(label)
        if reg is None:
            unmatched.append(str(label).strip())
            return None
        return reg[0], ds["fixed_item"], ds.get("fixed_item_name", ds["fixed_item"])
    if "code_col" in ds:                                 # the item code sits in its own column (8150)
        code = dims.normalise_code(row[ds["code_col"]] if row and ds["code_col"] < len(row) else None)
        if code is None:
            return None                                  # an uncoded aggregate row — not an item
        return dims.NATIONAL, code.translate(str.maketrans("АВСDЕ", "ABCDE")), str(label).strip()
    item = _item(label, ds, dictionary)
    if item is None:
        unmatched.append(str(label).strip())
        return None
    return dims.NATIONAL, item[0], item[1]


def _unmatched(ds: dict, unmatched: list) -> None:
    if unmatched and ds.get("strict", True):
        what = "region rows" if ds.get("row_dimension") == "region" else "data rows"
        _structural(ds, f"{what} whose label matches no dictionary entry",
                    "every data label in dictionaries/regions.csv" if ds.get("row_dimension") == "region"
                    else f"every data label in dictionaries/{ds['dictionary']}.csv", unmatched)


def _rec(year: int, region: str, code: str, name: str, value: float) -> dict:
    return {"date": f"{year}-12-31", "region": region, "item_code": code, "item_name": name, "value": value}


# ---------------------------------------------------------------- parsers

def parse_periods_across(grid: list[list], dictionary: list[dict] | None, label_col: int, ds: dict,
                         year_regex: re.Pattern = YEAR_IN_LABEL) -> list[dict]:
    header_i = _header_row(grid, year_regex, ds)
    year_cols = _annual_columns(grid[header_i], year_regex)
    records, unmatched = [], []
    for row in grid[header_i + 1:]:
        label = row[label_col] if label_col < len(row) else None
        if label is None or not str(label).strip() or FOOTNOTE_ROW.match(str(label)):
            continue
        values = {y: _to_float(row[c]) for y, c in year_cols.items() if c < len(row)}
        if all(v is None for v in values.values()):
            continue                                    # a heading or a footnote, not data
        key = _row_key(label, ds, dictionary, unmatched, row)
        if key is None:
            continue
        region, code, name = key
        records += [_rec(y, region, code, name, v) for y, v in values.items() if v is not None]
    _unmatched(ds, unmatched)
    return records


def parse_product_blocks(grid: list[list], dictionary: list[dict], ds: dict, year_regex: re.Pattern) -> list[dict]:
    """5814: a product label row (name with its unit, no numbers) followed by the country row and
    the producing regions; years across. Products outside the dictionary are skipped, as are the
    legend and note rows at the bottom."""
    header_i = _header_row(grid, year_regex, ds)
    year_cols = _annual_columns(grid[header_i], year_regex)
    records, current = [], None
    for row in grid[header_i + 1:]:
        label = row[0] if row else None
        if label is None or not str(label).strip():
            continue
        values = {y: _to_float(row[c]) for y, c in year_cols.items() if c < len(row)}
        reg = dims.match_region(label)
        if reg is not None:
            if current is not None:
                code, name = current
                records += [_rec(y, reg[0], code, name, v) for y, v in values.items() if v is not None]
            continue
        if any(v is not None for v in values.values()):
            continue                                     # a numbered row that is not a region — not ours
        current = _item(label, ds, dictionary)           # None for products outside the dictionary and for notes
    return records


def parse_year_subcolumns(grid: list[list], dictionary: list[dict] | None, label_col: int, sub_offset: int, ds: dict,
                          year_regex: re.Pattern = YEAR_IN_LABEL) -> list[dict]:
    header_i = _header_row(grid, year_regex, ds)
    header = grid[header_i]
    year_cols = {}
    for y, c in _annual_columns(header, year_regex).items():
        target = c + sub_offset
        # A year with fewer sub-columns than the others (5547: 2003 has no "%" column)
        # would otherwise read the next year's first cell as its own.
        if sub_offset and target < len(header) and header[target] is not None and year_regex.search(str(header[target])):
            continue
        year_cols[y] = target
    records, unmatched = [], []
    for row in grid[header_i + 1:]:
        label = row[label_col] if label_col < len(row) else None
        if label is None or not str(label).strip() or FOOTNOTE_ROW.match(str(label)):
            continue
        values = {y: _to_float(row[c]) for y, c in year_cols.items() if c < len(row)}
        if all(v is None for v in values.values()):
            continue
        key = _row_key(label, ds, dictionary, unmatched)
        if key is None:
            continue
        region, code, name = key
        records += [_rec(y, region, code, name, v) for y, v in values.items() if v is not None]
    _unmatched(ds, unmatched)
    return records


def parse_region_blocks(grid: list[list], ds: dict, dictionary: list[dict] | None = None,
                        year_regex: re.Pattern = YEAR_IN_LABEL) -> list[dict]:
    head_i = next((i for i, row in enumerate(grid) if row and "като" in dims.normalise_label(row[0] or "")), None)
    if head_i is None or head_i + 1 >= len(grid):
        _structural(ds, "no 'код КАТО' header row", "a header row with item names", grid[:5])
    header, below = grid[head_i], grid[head_i + 1]
    items: dict[int, tuple[str, str]] = {}
    unmatched = []
    from_table = ds["dictionary"] == "from_table"
    for j in range(2, len(header)):
        name = re.sub(r"\s+", " ", str((below[j] if not from_table and j < len(below) and isinstance(below[j], str) and below[j].strip() else header[j]) or "")).strip()
        if not name:
            continue
        if from_table:
            code = dims.normalise_code(below[j] if j < len(below) else None)
            if code is None:
                if dims.normalise_label(name).startswith("промышленность"):
                    code = "IND"
                else:
                    _structural(ds, f"item column {name!r} has no code and is not the industry total", "a code under every item name", below)
            items[j] = (code, name)
        else:
            item = _item(name, ds, dictionary)
            if item is None:
                unmatched.append(name)
                continue
            items[j] = item
    if unmatched:
        _structural(ds, "item columns whose name matches no dictionary entry", f"every column name in dictionaries/{ds['dictionary']}.csv", unmatched)
    want_all = ds.get("regions", "national") == "all"
    records, region, bad_regions = [], None, []
    for row in grid[head_i + 1:]:
        if len(row) < 2:
            continue
        label = str(row[1] or "").strip()
        has_code = row[0] is not None and str(row[0]).strip() != ""
        if has_code and label and not year_regex.search(label):
            reg = dims.match_region(label)
            if reg is None:
                bad_regions.append(label)
                region = None
                continue
            region = reg[0] if (want_all or reg[0] == dims.NATIONAL) else None
            continue
        if region is None or not label:
            continue
        m = year_regex.search(label)
        if not m:
            continue                                     # quarterly / year-to-date row
        year = int(m.group(1))
        for j, (code, name) in items.items():
            v = _to_float(row[j]) if j < len(row) else None
            if v is not None:
                records.append(_rec(year, region, code, name, v))
    if bad_regions and ds.get("strict", True):
        _structural(ds, "region blocks whose name matches no dictionary entry", "every block name in dictionaries/regions.csv", bad_regions)
    return records


def parse_group_blocks(grid: list[list], ds: dict, year_regex: re.Pattern) -> list[dict]:
    """Group label rows («Все население», «Всего», «из них: пшеницы» …), each followed by the
    country row and the regions (6576 with the names in column B; the grain tables 8154/8160/8166
    with the names in column A). Rows under a group that is not in `groups` are skipped."""
    head_i = _header_row(grid, year_regex, ds)
    year_cols = _annual_columns(grid[head_i], year_regex)
    label_col = int(ds.get("label_col", 1))
    groups = {code: re.compile(pat) for code, pat in ds["groups"].items()}
    subgroups = set(ds.get("subgroups", []))
    top, item, records, unmatched = None, None, [], []
    for row in grid[head_i + 1:]:
        if len(row) <= label_col or row[label_col] is None or not str(row[label_col]).strip():
            continue
        label = str(row[label_col]).strip()
        values = {y: _to_float(row[c]) for y, c in year_cols.items() if c < len(row)}
        if all(v is None for v in values.values()):
            norm = dims.normalise_label(label)
            hit = next((code for code, pat in groups.items() if pat.search(norm)), None)
            if hit is None:
                if dims.match_region(label) is None:
                    top, item = (top, None) if ds.get("skip_unknown_groups") else (top, item)
                continue                                 # footnote, note, or a group outside `groups`
            if hit in subgroups:
                item = f"{top}_{hit}" if top else hit
            else:
                top, item = hit, hit
            continue
        reg = dims.match_region(label)
        if reg is None:
            unmatched.append(label)
            continue
        if item is None:
            if ds.get("skip_unknown_groups"):
                continue
            _structural(ds, "region rows before any group label", "a group label such as «Все население» first", label)
        records += [_rec(y, reg[0], item, item, v) for y, v in values.items() if v is not None]
    _unmatched(ds, unmatched)
    return records


# ---------------------------------------------------------------- entry point

def fetch(ds: dict) -> tuple[list[dict], dict]:
    url = f"https://stat.gov.kz/api/iblock/element/{ds['element_id']}/file/ru/"
    content = bns._download(url)
    bns._save_raw(ds["id"], content, "xls" if is_legacy_xls(content) else "xlsx", {"source_url": url, "element_id": ds["element_id"]})
    return parse(content, ds), {"frequency": ds["frequency"], "source_url": url, "dataset_id": str(ds["element_id"]),
                                "note": ds.get("note", "annual values from the xlsx export; quarterly year-to-date columns skipped")}


def parse(content: bytes, ds: dict) -> list[dict]:
    grids = _sheets(content)
    year_regex = _year_regex(ds)
    dictionary = dims.load_dictionary(ds["dictionary"]) if ds.get("dictionary") not in (None, "from_table") else None
    records: list[dict] = []
    for _, grid in _pick_sheets(grids, ds):
        if ds["layout"] == "periods_across":
            records += parse_periods_across(grid, dictionary, ds["label_col"], ds, year_regex)
        elif ds["layout"] == "region_blocks":
            records += parse_region_blocks(grid, ds, dictionary, year_regex)
        elif ds["layout"] == "year_subcolumns":
            records += parse_year_subcolumns(grid, dictionary, ds["label_col"], ds["sub_offset"], ds, year_regex)
        elif ds["layout"] == "group_blocks":
            records += parse_group_blocks(grid, ds, year_regex)
        elif ds["layout"] == "product_blocks":
            records += parse_product_blocks(grid, dictionary, ds, year_regex)
        else:
            raise ValueError(f"{ds['id']}: unknown layout {ds['layout']!r}")
    seen = {}
    for r in records:                                   # a later sheet wins on an overlapping (year, region, item)
        seen[(r["date"], r["region"], r["item_code"])] = r
    records = sorted(seen.values(), key=lambda r: (r["item_code"], r["region"], r["date"]))
    n_items, n_regions = len({r["item_code"] for r in records}), len({r["region"] for r in records})
    if n_items < ds.get("min_items", 1):
        _structural(ds, "fewer items than expected", f">= {ds['min_items']} item codes", f"{n_items}: {sorted({r['item_code'] for r in records})}")
    if n_regions < ds.get("min_regions", 1):
        _structural(ds, "fewer regions than expected", f">= {ds['min_regions']} regions", f"{n_regions}: {sorted({r['region'] for r in records})}")
    return records
