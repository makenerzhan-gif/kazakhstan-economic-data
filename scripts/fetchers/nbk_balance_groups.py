"""Second-tier banks' balance-account groups: borrowings from the government, local executive
bodies and the national managing holding (group 2030), from international financial
organisations (2040) and from other banks and organisations doing some banking operations (2050).
Added 2026-09-27 for the quasi-fiscal block: funds of the budget and of the holdings (Baiterek,
Damu) placed in banks, monthly from 2010, where open-data forms have nothing before 2023.

Source: NBK «Сведения по остаткам на балансовых и внебалансовых счетах» (from 2026 «Сведения об
остатках … банков второго уровня_2026»), one workbook per year on the page
https://nationalbank.kz/ru/news/banks-performance (redirects to the current year's rubric; the
year tabs link /ru/news/banks-performance/rubrics/<id>, ids not in year order: 2016 = 1950,
2017 = 1949). Each workbook has one sheet per as-at date «01.MM.YYYY» (trailing spaces common),
plus a second 01.01 sheet «с ЗО» / «(ЗО)» / «ЗО» -- after the final (year-end closing) turnovers;
2022 has only the «с ЗО» one. Banks in rows, an «Итого»/«ИТОГ» row, one column per balance-account
group, thousand KZT. Two header layouts:
  - to 2022: row 4 holds «<name> (NNNN)», the code in parentheses at the end;
  - from 2023: row 5 holds the codes (1000, 1010, …), row 6 the names.
xls (BIFF) for most years, xlsx for 2014-2016 and 2026.

Written: items G2030, G2040, G2050, million KZT (thousand / 1000), dated the sheet's as-at date;
01.01 from the «ЗО» sheet when there is one (it differs from the plain sheet only at 01.01.2010:
G2050 1 243.1 bn against 1 242.7 bn).

Checks, enforced: every workbook has a header with the three groups under the expected names
(GROUP_NAMES; an unknown wording stops the dataset); the total row equals the sum of the bank rows
for each group within 5 thousand KZT (off by at most 1 on all 216 sheets 2010-2026); every sheet name is an
as-at date of the workbook's year.

Verified (bn KZT): G2030 01.01.2010 47.5, 01.01.2011 58.4, 01.01.2013 329.4, 01.01.2015 399.8,
01.01.2016 162.0, 01.12.2021 69.8, 01.01.2023 85.5, 01.02.2023 211.9, 01.01.2026 683.7,
01.08.2026 712.0. G2050 01.01.2023 742.6, 01.02.2023 575.5.

Pitfalls:
  - BREAK at 2023-02-01: group 2030 was widened to «…, национального управляющего холдинга и
    специального фонда развития частного предпринимательства» (Damu): +126 bn in 2030 and -167 bn
    in 2050 that month, i.e. Damu's placements moved from 2050 to 2030. G2030 + G2050 is the
    continuous aggregate across the break (it also holds interbank borrowing).
  - 2050 also holds interbank and repo-like borrowing: 1.42-1.75 trn in 2022-04..09.
  - Group 2030 is what banks OWE to these lenders; the holdings' conditional deposits sit in
    customer accounts (group 2200), not here.
Past years do not change: a year's workbook is downloaded when the processed file has no date in
that year, and the current and previous years on every refresh (the rest is carried forward);
between refreshes (`refresh_days`, imf_dims.stored_if_fresh) the stored records are returned.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import requests
import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims, nbk  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

SOURCE = "nbk"
SITE = "https://nationalbank.kz"
LANDING_URL = SITE + "/ru/news/banks-performance"
RUBRIC_URL = SITE + "/ru/news/banks-performance/rubrics/{id}"
TAB_RE = re.compile(r'href="/ru/news/banks-performance/rubrics/(\d+)"[^>]*>\s*(\d{4})\s*</a>')
FILE_RE = re.compile(r'href="(/file/download/\d+)"[^>]*download>\s*([^<]*?)\s*</a>')
FILE_TITLE = re.compile(r"остатк\w* на балансовых и внебалансовых счетах", re.I)
SHEET_RE = re.compile(r"^\s*(\d{2})\.(\d{2})\.(\d{4})\s*(.*?)\s*$")
TOTAL_LABELS = {"итого", "итог", "всего"}
GROUPS = ("2030", "2040", "2050")
GROUP_NAMES = {
    "2030": ("Займы, полученные от Правительства Республики Казахстан, местных исполнительных органов "
             "Республики Казахстан и национального управляющего холдинга (с 01.02.2023 -- и специального "
             "фонда развития частного предпринимательства)"),
    "2040": "Займы, полученные от международных финансовых организаций",
    "2050": "Займы, полученные от других банков и организаций, осуществляющих отдельные виды банковских операций",
}
# Header wordings accepted per group (whitespace-normalised, «(NNNN)» dropped).
_KNOWN_WORDINGS = {
    "2030": re.compile(r"^займы, полученные от правительства республики казахстан, местных исполнительных органов "
                       r"республики казахстан(,| и) национального управляющего холдинга"
                       r"( и специального фонда развития частного предпринимательства)?$"),
    "2040": re.compile(r"^займы, полученные от международных финансовых организаций$"),
    "2050": re.compile(r"^займы, полученные от других банков и организаций, осуществляющих отдельные виды "
                       r"банковских операций$"),
}
DAMU_BREAK = "2023-02-01"
TOTAL_TOLERANCE = 5.0  # thousand KZT: cells carry fractions, the total is rounded (1.0 off on 01.06.2022)


def _error(what: str, lines: list[str], action: str = "inspect the workbook and update scripts/fetchers/nbk_balance_groups.py"):
    return validation.StructuralChangeError("\n".join(
        [f"STRUCTURAL CHANGE DETECTED in nbk/{what}", *lines, f"ACTION REQUIRED: {action}"]))


# ---------------------------------------------------------------- discovery and download

def year_rubrics(html: str) -> dict[int, str]:
    """{year: rubric id} from the year tabs of any banks-performance page."""
    return {int(y): rid for rid, y in TAB_RE.findall(html)}


def balance_file_link(html: str) -> str | None:
    hits = [url for url, title in FILE_RE.findall(html) if FILE_TITLE.search(" ".join(title.split()))]
    return hits[0] if hits else None


def _get(url: str) -> requests.Response:
    resp = requests.get(url, headers=nbk.HEADERS, timeout=120)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------- workbook parsing

def workbook_sheets(content: bytes):
    """(sheet name, rows) for an xls or xlsx workbook."""
    if content[:2] == b"PK":
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for ws in wb.worksheets:
            yield ws.title, [list(r) for r in ws.iter_rows(values_only=True)]
    else:
        wb = xlrd.open_workbook(file_contents=content)
        for sh in wb.sheets():
            yield sh.name, [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]


def _code(cell) -> str | None:
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return str(int(cell)) if float(cell).is_integer() and 1000 <= cell <= 9999 else None
    s = str(cell or "").strip()
    return s[:4] if re.fullmatch(r"\d{4}(\.0+)?", s) else None


def find_header(rows: list[list]) -> tuple[int, dict[str, int], dict[str, str]] | None:
    """(last header row, {group code: column}, {group code: name}) for either layout."""
    for i, r in enumerate(rows[:15]):
        cells = [str(x or "").strip() for x in r]
        paren = {m.group(1): c for c, x in enumerate(cells) if (m := re.search(r"\((\d{4})\)$", x))}
        if len(paren) > 10:
            return i, paren, {k: re.sub(r"\s*\(\d{4}\)$", "", cells[c]) for k, c in paren.items()}
        coded = {}
        for c, x in enumerate(r):
            code = _code(x)
            if code and code not in coded:
                coded[code] = c
        if len(coded) > 10 and i + 1 < len(rows):
            nxt = rows[i + 1]
            return i + 1, coded, {k: str(nxt[c] if c < len(nxt) else "") for k, c in coded.items()}
    return None


def _num(cell) -> float | None:
    if cell in (None, ""):
        return None
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return float(cell)
    s = str(cell).replace("\xa0", "").replace(" ", "").replace(",", ".")
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def sheet_totals(rows: list[list], where: str) -> dict[str, float]:
    """{group: total, thousand KZT} of one sheet, checked against the sum of the bank rows."""
    header = find_header(rows)
    if header is None:
        raise _error(where, ["WHAT CHANGED: no header row with balance-account group codes"])
    hrow, cols, names = header
    missing = [g for g in GROUPS if g not in cols]
    if missing:
        raise _error(where, [f"WHAT CHANGED: groups {missing} not in the header"])
    for g in GROUPS:
        wording = " ".join(names[g].split()).lower()
        if not _KNOWN_WORDINGS[g].match(wording):
            raise _error(where, [f"WHAT CHANGED: group {g} is now named {names[g]!r}",
                                 f"EXPECTED: {_KNOWN_WORDINGS[g].pattern}"],
                         "a definition change -- record the break in the module docstring and dims.yaml note, "
                         "then add the wording to _KNOWN_WORDINGS")
    total_rows = [j for j, r in enumerate(rows) if j > hrow and len(r) > 1
                  and str(r[1] or "").strip().lower().rstrip(":") in TOTAL_LABELS]
    if not total_rows:
        raise _error(where, ["WHAT CHANGED: no «Итого»/«ИТОГ» row in column B"])
    t = total_rows[0]
    out = {}
    for g in GROUPS:
        c = cols[g]
        total = _num(rows[t][c] if c < len(rows[t]) else None) or 0.0
        banks = sum(v for r in rows[hrow + 1:t] if c < len(r) and (v := _num(r[c])) is not None)
        if abs(total - banks) > TOTAL_TOLERANCE:
            raise _error(where, [f"WHAT CHANGED: group {g} total {total:,.0f} != sum of bank rows {banks:,.0f}"])
        out[g] = total
    return out


def workbook_records(content: bytes, year: int, label: str = "") -> list[dict]:
    """Records (million KZT) of one yearly workbook; for 01.01 the «ЗО» sheet wins."""
    by_date: dict[str, tuple[bool, dict[str, float]]] = {}
    for name, rows in workbook_sheets(content):
        m = SHEET_RE.match(name)
        if not m or int(m.group(3)) != year or not 1 <= int(m.group(2)) <= 12 or m.group(1) != "01":
            if not any(any(c not in (None, "") for c in r) for r in rows):
                continue  # an empty stray sheet
            raise _error(f"BANKS_BALANCE_GROUPS {label}", [f"WHAT CHANGED: sheet {name!r} is not «01.MM.{year}»"])
        d = f"{m.group(3)}-{m.group(2)}-01"
        final = "зо" in m.group(4).lower()
        if m.group(4) and not final:
            raise _error(f"BANKS_BALANCE_GROUPS {label}", [f"WHAT CHANGED: unknown sheet suffix in {name!r}"])
        totals = sheet_totals(rows, f"BANKS_BALANCE_GROUPS {label} sheet {name.strip()!r}")
        if d not in by_date or (final and not by_date[d][0]):
            by_date[d] = (final, totals)
    return [{"date": d, "region": dims.NATIONAL, "item_code": f"G{g}", "item_name": GROUP_NAMES[g],
             "value": totals[g] / 1000.0}
            for d, (_, totals) in sorted(by_date.items()) for g in GROUPS]


# ---------------------------------------------------------------- dims fetcher

def fetch(ds: dict) -> tuple[list[dict], dict]:
    """dims.yaml dataset (fetcher nbk_balance_groups); `from_year` (default 2010) = first workbook."""
    fresh = imf_dims.stored_if_fresh(ds, SOURCE, ds["id"])  # `refresh_days` (monthly source, ~1 MB a year)
    if fresh:
        return fresh
    today = date.today()
    first = int(ds.get("from_year", 2010))
    landing = _get(LANDING_URL)
    rubrics = year_rubrics(landing.text)
    if not rubrics or max(rubrics) < today.year - 1:
        raise _error(ds["id"], ["WHAT CHANGED: no year tabs (/rubrics/<id> «YYYY») on the banks-performance page",
                                f"ACTUAL: {sorted(rubrics.items())[-5:]}"])
    old = dims.load_processed(ds["id"])
    have_years = {int(r["date"][:4]) for r in old}
    years = [y for y in sorted(rubrics) if y >= first and (y >= today.year - 1 or y not in have_years)]
    records: list[dict] = []
    files = {}
    for y in years:
        html = landing.text if landing.url.rstrip("/").endswith(rubrics[y]) else _get(RUBRIC_URL.format(id=rubrics[y])).text
        link = balance_file_link(html)
        if link is None:
            raise _error(ds["id"], [f"WHAT CHANGED: no «Сведения по остаткам на балансовых…» file on rubric {rubrics[y]} ({y})"])
        content = _get(SITE + link).content
        ext = "xlsx" if content[:2] == b"PK" else "xls"
        raw_id = f"BANKS_BALANCE_ACCOUNTS_{y}"
        raw_store.save_raw_bytes(SOURCE, raw_id, today, ext, content)
        raw_store.write_download_manifest(SOURCE, raw_id, today, {
            "downloaded_at": datetime.now().isoformat(), "source_url": SITE + link,
            "rubric": RUBRIC_URL.format(id=rubrics[y]), "read_by": ds["id"]})
        files[y] = SITE + link
        records += workbook_records(content, y, str(y))
    fresh = {int(r["date"][:4]) for r in records}
    carried = [{"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
                "value": float(r["value"])} for r in old if int(r["date"][:4]) not in fresh and int(r["date"][:4]) >= first]
    records = sorted(carried + records, key=lambda r: (r["item_code"], r["date"]))
    raw_store.write_download_manifest(SOURCE, ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": LANDING_URL, "workbooks": files})
    return records, {
        "frequency": "monthly", "source_url": LANDING_URL,
        "dataset_id": "nbk-banks-performance/balance-accounts",
        "note": ds.get("note", ""),
        "warnings": [f"workbooks read: {', '.join(f'{y} {u}' for y, u in files.items())}; "
                     f"{len({r['date'] for r in carried})} earlier dates carried forward from the processed file"],
    }
