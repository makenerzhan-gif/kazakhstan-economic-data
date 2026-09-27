"""BNS «Ресурсы и использование отдельных видов продукции (товаров) и сырья в Республике
Казахстан» (stat.gov.kz → Экономика → Внешний рынок → Электронные таблицы, publication 19065;
the 2019-2022 editions under the archive listing 72035). National, physical units.

For each product the balance of resources and their use, in the product's own unit (тыс.
тонн, млн. куб. м, штук …):

    RES   Ресурсы                           = PROD + IMP (+ EST)
    PROD  Производство (добыча)
    IMP   Импорт
    EST   Оценка — BNS's estimate added to resources for a few goods (2019-2023)
    USE   Использование                     = RES
    EXP   Экспорт
    DOM   Реализация на внутреннем рынке    = USE − EXP

Table 1 holds ~270 mining, manufacturing and utility products, table 2 grain and vegetables
(imports and exports only since 2022), table 3 the socially important food products (СЗПТ,
May 2022 onward).

Monthly editions (one a month, ~50 days after the month's end) give per row: the previous
month, January to the previous month, the month, January to the month, and the month and
January to the month a year earlier, then shares and indices. RESOURCE_USE_MONTHLY keeps the
three single-month columns: an edition for month t gives t, t−1 (revised) and t−12 (revised
again), and a later edition overrides an earlier one, so a month carries its latest print.
RESOURCE_USE_YTD keeps the three January-to-month columns the same way. The two differ: BNS
revises earlier months inside the cumulative figure only -- wheat exports January–March 2026
were 3.66 Mt in the March edition, and January–July 4.95 Mt in the July edition against
5.99 Mt for the sum of the latest single-month prints. For a year-to-date total use the YTD
dataset; the months of the last year are not final until the edition a year later.
The annual editions («… (2024г.)», about eleven months after the year, final data) give the
year and the year before — RESOURCE_USE_ANNUAL, 2021 onward (for other years sum the months).

Layouts: 2019-03 … 2022-01 xls, Kazakh in column A and Russian in the last column (bilingual
column headers); 2022-02 onward xlsx, Russian only; the columns keep their order throughout.
Labels are read from the last text cell of a row. Values 'x' (confidential) and '-' are
skipped. A product is a text row followed by a row labelled with one of the articles above.

Item codes: «<product slug>.<article>», the slug being the product's normalised Russian label
transliterated (as the CPI publication's items; a label over 90 characters is cut to 83 and
given a 6-character digest of the whole); table 3 products are prefixed «szpt_», table 2
«crops_». A handful of renamings over 2019-2026 are folded into one product (ALIASES); the
unit is part of the label, so «белье нижнее, штук» and «…, тыс.штук» stay two series.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

LISTING_URL = "https://stat.gov.kz/ru/industries/economy/foreign-market/spreadsheets/?name={name}{page}"
FILE_URL = "https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
PUBLICATION = "19065"
ARCHIVE_LISTING = "72035"
ARCHIVE = False         # scripts/backfill_resource_use.py: read every edition of both listings
KEEP_LATEST = 4         # monthly editions read on a daily run (each carries t, t-1 and t-12)

ARTICLES = [("RES", "Ресурсы", re.compile(r"^ресурсы$")),
            ("PROD", "Производство", re.compile(r"^производство( \(добыча\))?$")),
            ("IMP", "Импорт", re.compile(r"^импорт$")),
            ("EST", "Оценка", re.compile(r"^оценка$")),
            ("USE", "Использование", re.compile(r"^использование$")),
            ("EXP", "Экспорт", re.compile(r"^экспорт$")),
            ("DOM", "Реализация на внутреннем рынке", re.compile(r"^реализация на внутреннем рынке$"))]
ARTICLE_NAMES = {code: name for code, name, _ in ARTICLES}
SHEET_PREFIX = {"1": "", "2": "crops_", "3": "szpt_"}

# Renamings (normalised label, after _clean) folded into the current wording.
ALIASES = {
    "коньяки и напитки коньячные, тыс.литров": "коньяк и напитки коньячные, тыс.литров",
    "мясо птицы, пищевые субпродукты (данные производства приведены по мясу всех видов скота и птицы в убойном весе), тонн":
        "мясо птицы, пищевые субпродукты, тонн",
    "мясо птицы, пищевые субпродукты (данные производства приведены по мясу всех видов птиц в убойном весе), тонн":
        "мясо птицы, пищевые субпродукты, тонн",
    "хлопок, кардо и гребнечесаный, тонн": "хлопок, кардо- и гребнечесаный, тонн",
    "хлопок, кардои гребнечесаный, тонн": "хлопок, кардо- и гребнечесаный, тонн",
    "яйца в скорлупе, свежие, тыс.штук": "яйца, тыс.штук",
    "конина, тонн": "мясо конины, тонн",
    "мясо лошади, тонн": "мясо конины, тонн",
    "свинина, тонн": "мясо свинины, тонн",
}

_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
           "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
_MONTH_WORD = r"(?:январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
_MONTH_RE = re.compile(rf"({_MONTH_WORD})(?:\s*-\s*({_MONTH_WORD})?)?\s*(\d{{4}})")
_YEAR_RE = re.compile(r"^\s*(\d{4})(?:\.0)?\s*(?:г\.?|год)?\s*$")
MISSING = {"", "-", "–", "—", "x", "х", "...", "…"}


def _clean(label) -> str:
    s = dims.normalise_label(label)
    s = re.sub(r"\s*\.\s*", ".", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s*;\s*", "; ", s)
    s = s.strip(" .*")
    return ALIASES.get(s, s)


_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya"})


def product_code(sheet: str, label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", _clean(label).translate(_TRANSLIT)).strip("_")
    if len(s) > 90:        # long labels share long prefixes: keep them apart with a digest of the whole
        s = s[:83] + "_" + hashlib.md5(s.encode()).hexdigest()[:6]
    return SHEET_PREFIX[sheet] + s


def _to_float(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if s.lower() in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _article(label: str) -> str | None:
    norm = _clean(label)
    for code, _name, rx in ARTICLES:
        if rx.match(norm):
            return code
    return None


def _label(row) -> str | None:
    """The row's Russian label: its last text cell (Kazakh sits in column A of the xls years)."""
    texts = [c for c in row if isinstance(c, str) and c.strip() and _to_float(c) is None and c.strip().lower() not in MISSING]
    return texts[-1] if texts else None


def _month_of(cell) -> tuple[int, int, bool] | None:
    """(year, last month, is_range) of a column header -- the last Russian period named in it
    («январь-июнь 2026г.» -> (2026, 6, True)); a bilingual header's Kazakh part never matches."""
    hits = list(_MONTH_RE.finditer(str(cell or "").lower()))
    if not hits:
        return None
    m = hits[-1]
    word = m.group(2) or m.group(1)
    stem = next(k for k in sorted(_MONTHS, key=len, reverse=True) if word.startswith(k))
    return int(m.group(3)), _MONTHS[stem], m.group(2) is not None


def _shift(y: int, m: int, k: int) -> tuple[int, int]:
    n = y * 12 + (m - 1) + k
    return n // 12, n % 12 + 1


def _header(rows: list[list]) -> tuple[int, str, list]:
    """(index of the first data row, kind 'monthly'|'annual', column periods) of a data sheet.
    The period row is the one right under «Наименование продукции/Фактически за»."""
    for i, r in enumerate(rows[:8]):
        if any(isinstance(c, str) and "фактически" in c.lower() for c in r):
            periods = rows[i + 1]
            years = [(_YEAR_RE.match(str(c)) and int(_YEAR_RE.match(str(c)).group(1))) for c in periods[1:3]]
            if all(years):
                return i + 2, "annual", years
            cols = [_month_of(c) for c in periods[1:7]]
            return i + 2, "monthly", cols
    raise ValueError("no «Фактически за» header row")


def parse_sheet(sheet: str, rows: list[list]) -> tuple[str, list[tuple[str, str, str, str, str, float]]]:
    """(kind, [(measure, date, product code, product label, article, value)]) of one data sheet;
    measure 'monthly' (the single month), 'ytd' (January to the month) or 'annual'."""
    start, kind, cols = _header(rows)
    if kind == "monthly":
        cur = cols[2]
        if not cur or cur[2]:
            raise ValueError(f"table {sheet}: column 3 header is not a single month: {rows[start - 1][3]!r}")
        y, m = cur[0], cur[1]
        # (column index, the month it ends with): the previous month and January to it, the month
        # and January to it, the month and January to it a year earlier
        expect = {1: _shift(y, m, -1), 2: _shift(y, m, -1), 3: (y, m), 4: (y, m), 5: (y - 1, m), 6: (y - 1, m)}
        for col, (ey, em) in expect.items():
            got = cols[col - 1]
            if not got or (got[0], got[1]) != (ey, em) or (col % 2 and got[2]):
                raise ValueError(f"table {sheet}: column {col + 1} header {rows[start - 1][col]!r}, expected {'' if col % 2 else 'January to '}{em:02d}.{ey}")
        dated = {col: (f"{ey:04d}-{em:02d}-01", "monthly" if col % 2 else "ytd") for col, (ey, em) in expect.items()}
    else:
        dated = {1: (f"{cols[0]:04d}-12-31", "annual"), 2: (f"{cols[1]:04d}-12-31", "annual")}
        if cols[1] != cols[0] + 1:
            raise ValueError(f"table {sheet}: annual columns {cols}")
    out, product = [], None
    for r in rows[start:]:
        label = _label(r)
        if not label:
            continue
        art = _article(label)
        if art is None:
            product = label                    # a product (or a section heading, which no article follows)
            continue
        if product is None:
            continue
        code, name = product_code(sheet, product), " ".join(product.split())
        for col, (d, measure) in dated.items():
            v = _to_float(r[col]) if col < len(r) else None
            if v is not None:
                out.append((measure, d, code, name, art, v))
    return kind, out


def parse_workbook(sheets: dict[str, list[list]]) -> tuple[str, list[tuple]]:
    kinds, out = set(), []
    for name, rows in sheets.items():
        sheet = name.strip()
        if sheet not in SHEET_PREFIX:
            continue
        kind, recs = parse_sheet(sheet, rows)
        kinds.add(kind)
        out += recs
    if len(kinds) != 1:
        raise ValueError(f"data sheets of mixed or no kind: {kinds}")
    return kinds.pop(), out


# ---------------------------------------------------------------- listing and update_dims entry point

_ROW_RE = re.compile(r'element/(\d+)/file/ru/">\s*([^<]*?)\s*</a>.*?text-right">\s*([\d.]+)\s*<.*?<span class="mr-1">([^<]*)</span>', re.S)


def edition_of(title: str) -> tuple[str, int, int] | None:
    """('monthly', year, last month) or ('annual', year, 12) from an edition title."""
    t = title.lower()
    m = re.search(r"\((январь)(?:\s*-\s*([а-я]+))?\s*(\d{4})", t)
    if m:
        last = m.group(2) or "январь"
        stem = next((k for k in sorted(_MONTHS, key=len, reverse=True) if last.startswith(k)), None)
        return ("monthly", int(m.group(3)), _MONTHS[stem]) if stem else None
    m = re.search(r"\((\d{4})\s*г\.?\s*\)", t)
    return ("annual", int(m.group(1)), 12) if m else None


def parse_listing(page: str) -> list[dict]:
    out = []
    for eid, title, published, size in _ROW_RE.findall(page):
        title = re.sub(r"\s+", " ", title).strip()
        ed = edition_of(title)
        fmt = size.split(",")[-1].strip().lower()
        if ed and fmt in ("xls", "xlsx"):
            out.append({"element_id": eid, "title": title, "kind": ed[0], "year": ed[1], "month": ed[2],
                        "published": published, "format": fmt})
    return out


def _structural(what: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        "STRUCTURAL CHANGE DETECTED in bns/RESOURCE_USE (publication 19065)", f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: inspect {LISTING_URL.format(name=PUBLICATION, page='')} and scripts/fetchers/bns_resource_use.py"]))


def editions() -> list[dict]:
    """The editions to read, oldest first: on a daily run the latest KEEP_LATEST monthly and the
    latest annual edition of the listing's first page; in ARCHIVE mode every page of both listings."""
    from fetchers import bns
    names = (PUBLICATION, ARCHIVE_LISTING) if ARCHIVE else (PUBLICATION,)
    found: dict[str, dict] = {}
    for name in names:
        for page in range(1, 12 if ARCHIVE else 2):
            html = bns._download(LISTING_URL.format(name=name, page=f"&PAGEN_1={page}" if page > 1 else ""))
            rows = parse_listing(html.decode("utf-8", "replace"))
            new = [r for r in rows if r["element_id"] not in found]
            if not new:
                break
            found.update({r["element_id"]: r for r in new})
    listed = sorted(found.values(), key=lambda e: (e["year"], e["month"], e["kind"] == "annual", _published(e)))
    if not listed:
        _structural("the listing lists no xls/xlsx edition")
    if ARCHIVE:
        return listed
    monthly = [e for e in listed if e["kind"] == "monthly"][-KEEP_LATEST:]
    annual = [e for e in listed if e["kind"] == "annual"][-1:]
    return sorted(monthly + annual, key=lambda e: (e["year"], e["month"], _published(e)))


def _published(e: dict) -> str:
    m = re.match(r"(\d\d)\.(\d\d)\.(\d{4})", e.get("published") or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


_RUN: dict = {}


def _read() -> dict:
    """Parse the editions once per process: {'monthly': {...}, 'ytd': {...}, 'annual': {...}}
    keyed (date, code, article) -> (value, name); a later edition overrides an earlier one."""
    if _RUN:
        return _RUN
    from fetchers import bns, bns_dims
    out = {"monthly": {}, "ytd": {}, "annual": {}, "read": [], "release": None}
    for e in editions():
        url = FILE_URL.format(eid=e["element_id"])
        content = bns._download(url)
        ext = "xls" if bns_dims.is_legacy_xls(content) else "xlsx"
        if not ARCHIVE:
            bns._save_raw(f"RESOURCE_USE_{e['year']:04d}{e['month']:02d}{'_ANNUAL' if e['kind'] == 'annual' else ''}", content, ext,
                          {"source_url": url, "element_id": e["element_id"], "title": e["title"], "published": e["published"]})
        sheets = bns_dims._sheets(content)
        try:
            kind, recs = parse_workbook(sheets)
        except ValueError as exc:
            _structural(f"edition {e['title']!r}: {exc}")
        if kind != e["kind"]:
            _structural(f"edition {e['title']!r} is titled {e['kind']} but its tables are {kind}")
        for measure, d, code, name, art, v in recs:
            out[measure][(d, code, art)] = (v, name)
        out["read"].append(e["title"])
        out["release"] = _published(e) or out["release"]
    _RUN.update(out)
    return _RUN


def records_of(values: dict) -> list[dict]:
    return [{"date": d, "region": dims.NATIONAL, "item_code": f"{code}.{art}",
             "item_name": f"{name} — {ARTICLE_NAMES[art]}", "value": v}
            for (d, code, art), (v, name) in values.items()]


def fetch(ds: dict) -> tuple[list[dict], dict]:
    """ds['period']: 'monthly', 'ytd' or 'annual'. Stored history with the editions read laid over it."""
    run = _read()
    stored = {(r["date"], r["item_code"]): r for r in dims.load_processed(ds["id"])}
    fresh = records_of(run[ds["period"]])
    merged = {k: {**r, "value": float(r["value"])} for k, r in stored.items()}
    for r in fresh:
        merged[(r["date"], r["item_code"])] = r
    if not merged:
        _structural(f"no records for {ds['id']}")
    records = sorted(merged.values(), key=lambda r: (r["item_code"], r["date"]))
    for r in records:
        r.pop("transformation", None)
    latest = max(r["date"] for r in records)
    n = len({r["item_code"].rsplit(".", 1)[0] for r in records if r["date"] == latest})
    if n < ds.get("min_items", 1):
        _structural(f"{ds['id']}: {n} products in the latest period, expected at least {ds.get('min_items')}")
    return records, {"frequency": ds["frequency"], "source_url": LISTING_URL.format(name=PUBLICATION, page=""),
                     "dataset_id": PUBLICATION, "release": run["release"], "note": ds.get("note", ""),
                     "warnings": [], "editions_read": run["read"]}
