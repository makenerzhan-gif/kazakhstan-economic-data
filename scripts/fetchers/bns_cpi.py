"""BNS consumer price publication: «Индекс потребительских цен и производные показатели в
Республике Казахстан» (form Т-15-02-М, monthly, stat.gov.kz → Экономика → Цены →
Электронные таблицы, publication id 19117) and its predecessor «Индекс потребительских
цен в Республике Казахстан» (publication id 166775, May 1999 – December 2022).

One edition = one month. Each table gives, per row, the month against the previous month,
against December of the previous year, against the same month of the previous year,
against a fixed December (2002, 2005, 2010, 2015 or 2020 — not kept, it is a chain of the
monthly indices) and January–month against January–month of the previous year (average
since the start of the year). The quarterly columns of the March/June/September/December
editions are skipped. Measures kept:

    mom      previous month = 100
    ytd      December of the previous year = 100
    yoy      same month of the previous year = 100
    avg_yoy  January–month against January–month of the previous year = 100

In a January edition «к декабрю» is both mom and ytd, and «январь к январю» both yoy and
avg_yoy; in December «к декабрю прошлого года» is both ytd and yoy.

Layouts seen (every edition from July 2004 to August 2026 was read on 2026-09-27):
  2004-07 … 2007-12   xls in a rar, Russian labels
  2008-01 … 2012-02   xls in a rar, «Kazakh\\nRussian» in one cell
  2012-03 … 2019-04   xls/xlsx in a rar/zip, «Kazakh Russian» on one line or Kazakh alone (the
                      Russian label recovered by scripts/backfill_cpi_publication.py)
  2019-05 … 2022-12   xlsx, Kazakh in column A, Russian in the last column
  2022-10 …           Т-15-02-М xlsx, Russian only; adds the core inflation, retail price
                      and contribution tables
Before July 2004 the archive holds text tables in html (a different, pre-COICOP grouping);
they are not read.

Tables are recognised by their titles, rows by content; nothing is positional. A row's
item code comes from its Russian label: the aggregates (total, the three groups, the
COICOP divisions) through dictionaries/cpi_aggregates.csv, which spans every wording BNS
used since 2004; the individual goods and services by a transliterated slug of the label,
so an item BNS renames starts a new series (the basket is revised every January).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MEASURES = ("mom", "ytd", "yoy", "avg_yoy")

_DATIVE = {"январю": 1, "февралю": 2, "марту": 3, "апрелю": 4, "маю": 5, "июню": 6, "июлю": 7,
           "августу": 8, "сентябрю": 9, "октябрю": 10, "ноябрю": 11, "декабрю": 12}
_DATIVE_RE = re.compile(r"(" + "|".join(_DATIVE) + r")\s*(\d{4})")
_AVG_RE = re.compile(r"январ\w*\s*-\s*\w+.*?к\s+январю\s*-")
_QUARTER_RE = re.compile(r"квартал|(?<![а-яәғқңөұүһі])тоқсан")     # not желтоқсан (December)
_KAZAKH_LETTERS = set("әғқңөұүһі")
MISSING = {"", "-", "–", "—", "…", "...", "..", "x", "х"}


def to_float(v) -> float | None:
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
        return None


def is_kazakh(text: str) -> bool:
    return any(c in _KAZAKH_LETTERS for c in str(text).lower())


def _text(v) -> str:
    return "" if v is None or to_float(v) is not None else re.sub(r"[ \t\xa0]+", " ", str(v)).strip()


def column_measures(descriptor: str, year: int, month: int) -> list[str]:
    """The measures a column holds, from its header text (the lowest non-empty header cell of
    the column). A Kazakh+Russian cell is read by its Russian words only."""
    s = re.sub(r"\s+", " ", descriptor.lower())
    if _QUARTER_RE.search(s):
        return []
    if _AVG_RE.search(s):
        return ["avg_yoy"]
    hits = _DATIVE_RE.findall(s)
    if not hits:
        return []
    target = (int(hits[-1][1]), _DATIVE[hits[-1][0]])
    prev = (year, month - 1) if month > 1 else (year - 1, 12)
    out = []
    if target == prev:
        out.append("mom")
    if target == (year - 1, 12):
        out.append("ytd")
    if target == (year - 1, month):
        out.append("yoy")
        if month == 1:
            out.append("avg_yoy")
    return out


def split_label(cells: list) -> tuple[str, str]:
    """(Kazakh, Russian) label of a data row; either may be empty. Russian sits in the last
    text cell (2019–2022), after a line break in column A (2008–2012), or alone in column A."""
    first = str(cells[0] or "").strip()
    tail = [_text(c) for c in cells[1:]]
    tail = [t for t in tail if t and t.lower() not in MISSING and re.search(r"[а-яёa-z]", t.lower())]
    if tail and first:
        return re.sub(r"\s+", " ", first), re.sub(r"\s+", " ", tail[-1])
    if not first and tail:
        first = tail[-1]
    lines = [ln.strip() for ln in first.split("\n") if ln.strip()]
    if len(lines) > 1:
        for i in range(1, len(lines)):
            if lines[i][:1].isupper() and not is_kazakh(" ".join(lines[i:])):
                return " ".join(lines[:i]), " ".join(lines[i:])
    joined = re.sub(r"\s+", " ", first)
    return split_inline(joined)


def split_inline(text: str) -> tuple[str, str]:
    """«Көлік Транспорт», «Денсаулық сақтау Здравоохранение»: some 2012–2019 editions put both
    languages on one line. The Russian part is the tail that starts with a capital letter and
    has no Kazakh letter, after a head that has one. A line with no Kazakh letter is Russian;
    one that cannot be split is Kazakh."""
    if not is_kazakh(text):
        return "", text
    tokens = text.split(" ")
    for i in range(1, len(tokens)):
        head, tail = " ".join(tokens[:i]), " ".join(tokens[i:])
        if tokens[i][:1].isupper() and not is_kazakh(tail) and re.search(r"[а-яё]", tail.lower()):
            if is_kazakh(head):
                return head, tail
    return text, ""


@dataclass
class Row:
    kz: str
    ru: str
    values: dict[str, float]
    block: str | None = None           # regional tables: the item heading the block (Russian or Kazakh)
    block_kz: str | None = None


@dataclass
class Table:
    title: str
    kind: str                           # national / regional / core / retail / retail_regional / contribution
    section: str | None                 # food / nonfood / services / None
    rows: list[Row] = field(default_factory=list)
    columns: dict[int, list[str]] = field(default_factory=dict)
    repaired: str | None = None         # a header BNS mislabelled, and how it was read


def table_kind(title: str) -> tuple[str, str | None] | None:
    t = re.sub(r"\s+", " ", title.lower())
    if "вклад" in t or "үлес" in t:
        return "contribution", None
    if "базов" in t and "инфляц" in t:
        return "core", None
    if "розничных цен" in t:
        return ("retail_regional" if "регион" in t else "retail"), None
    if "потребительских цен" in t or "тұтыну бағасының" in t or re.search(r"индекс цен на (не)?продовольственные|индекс цен на платные", t):
        if "регион" in t or "өңірлер" in t:
            return "regional", None
        if "групп населения" in t or "доход" in t:
            return None
        section = ("nonfood" if "непродовольствен" in t or "азық-түлік емес" in t else
                   "food" if "продовольствен" in t or "азық-түлік тауарларына" in t else
                   "services" if "платные услуги" in t or "ақылы қызмет" in t else None)
        return "national", section
    return None


def _title(grid: list[list]) -> str:
    parts = []
    for row in grid[:4]:
        for c in row:
            t = _text(c)
            if t and not re.fullmatch(r"(в процентах|пайызбен|пайызбен в процентах)", t.lower()):
                parts.append(t)
    return " ".join(parts)


def _numeric_cols(row: list) -> list[int]:
    return [j for j, c in enumerate(row) if j > 0 and to_float(c) is not None]


def parse_grid(grid: list[list], year: int, month: int) -> Table | None:
    """One sheet. None when the sheet is not a price table (cover, contents, notes)."""
    title = _title(grid)
    kind = table_kind(title)
    if kind is None or len(grid) < 5:
        return None
    table = Table(title=title, kind=kind[0], section=kind[1])
    first_data = next((i for i, r in enumerate(grid) if i >= 2 and r and _text(r[0]) and _numeric_cols(r)
                       and not re.match(r"^\d+\.?\s", _text(r[0]))), None)
    if first_data is None:
        return None
    header = grid[:first_data]
    width = max(len(r) for r in grid)
    if kind[0] == "contribution":
        table.columns = _contribution_columns(header, width)
        _january_contribution(table, month)
    else:
        for j in range(1, width):
            cells = [str(r[j]) for r in header if j < len(r) and _text(r[j])]
            if cells:
                m = column_measures(cells[-1], year, month)
                if m:
                    table.columns[j] = m
        _repair_yoy(table, header, width, year, month)
    if not table.columns:
        return table
    block, block_kz = None, None
    for r in grid[first_data - (1 if table.kind in ("regional", "retail_regional") else 0):]:
        r = list(r) + [None] * (width - len(r))
        nums = {j: to_float(r[j]) for j in table.columns if to_float(r[j]) is not None}
        kz, ru = split_label(r)
        if not (kz or ru):
            continue
        if not nums:
            if table.kind in ("regional", "retail_regional") and not re.search(r"^(ответствен|жауапты|исп\.|тел|e-mail|№|от \d|©)", (ru or kz).lower()):
                block, block_kz = ru, kz
            continue
        values = {}
        for j, v in nums.items():
            for m in table.columns[j]:
                values.setdefault(m, v)
        table.rows.append(Row(kz=kz, ru=ru, values=values, block=block, block_kz=block_kz))
    return table


def _repair_yoy(table: Table, header: list[list], width: int, year: int, month: int) -> None:
    """February 2026 headed the year-on-year column «январю 2025г.» (for «февралю 2025г.»).
    When no column reads as year-on-year, the one column left over that points into the
    previous year other than its December (a fixed base is always a December) is taken as it."""
    if any("yoy" in m for m in table.columns.values()):
        return
    spare = []
    for j in range(1, width):
        if j in table.columns:
            continue
        cells = [str(r[j]) for r in header if j < len(r) and _text(r[j])]
        hits = _DATIVE_RE.findall(re.sub(r"\s+", " ", cells[-1].lower())) if cells else []
        if hits and int(hits[-1][1]) == year - 1 and _DATIVE[hits[-1][0]] != 12 and not _AVG_RE.search(cells[-1].lower()):
            spare.append(j)
    if len(spare) == 1:
        table.columns[spare[0]] = ["yoy"] + (["avg_yoy"] if month == 1 else [])
        table.repaired = f"column {spare[0]} headed {cells_text(header, spare[0])!r} read as year-on-year"


def cells_text(header: list[list], j: int) -> str:
    return " / ".join(_text(r[j]) for r in header if j < len(r) and _text(r[j]))


def _contribution_columns(header: list[list], width: int) -> dict[int, list[str]]:
    """Т-15-02-М table 6 and publication 27168: «К предыдущему месяцу» / «К декабрю
    предыдущего года», each over «темп прироста» and «вклад в прирост цен». Only the
    contributions are kept (the growth rates are the index minus 100)."""
    out: dict[int, list[str]] = {}
    top = ""
    for j in range(1, width):
        cells = [_text(r[j]).lower() for r in header if j < len(r) and _text(r[j])]
        for c in cells:
            if "предыдущему месяцу" in c or "өткен айға" in c:
                top = "mom"
            elif "декабрю" in c or "желтоқсан" in c:
                top = "ytd"
        if cells and ("вклад" in cells[-1] or "үлес" in cells[-1]) and top:
            out[j] = [top]
    return out


def _january_contribution(table: Table, month: int) -> None:
    """A January contribution table has one block, headed «к декабрю» or «к предыдущему
    месяцу» depending on the year: in January the two are the same thing."""
    if month == 1 and table.kind == "contribution" and len({m for ms in table.columns.values() for m in ms}) == 1:
        for j in table.columns:
            table.columns[j] = ["mom", "ytd"]


# ---------------------------------------------------------------- codes

_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya"})

CORE_PATTERNS = (  # table «Базовая инфляция»: the goods excluded, as BNS lists them
    ("CORE_EX7", "Базовая инфляция без учёта фруктов и овощей, ЖКУ, ж/д транспорта, связи, бензина, дизтоплива и угля",
     re.compile(r"жилищно-?\s*коммунальн")),
    ("CORE_EX3", "Базовая инфляция без учёта фруктов и овощей, бензина и угля", re.compile(r"бензин")),
    ("CORE_EX_FV", "Базовая инфляция без учёта фруктов и овощей", re.compile(r"^фрукты и овощи$")),
)


def slug(label: str) -> str:
    """Item code of an individual good or service: its normalised Russian label, transliterated."""
    from lib import dims
    s = dims.normalise_label(label)
    s = re.sub(r"\bа[иий]-?\s*(\d\d)", r"аи-\1", s)          # «АИ-92», «Ай-92», «АИ92» are one grade
    s = s.translate(_TRANSLIT)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s[:80]


def item_of(label: str, kind: str) -> tuple[str, str]:
    """(item_code, item_name) of a row. Aggregates get their dictionary code and canonical
    name; core-inflation rows a CORE_* code; everything else the slug and the label as printed."""
    from lib import dims
    name = re.sub(r"\s+", " ", label).strip()
    if kind == "core":
        norm = dims.normalise_label(name)
        for code, cname, rx in CORE_PATTERNS:
            if rx.search(norm):
                return code, cname
        raise ValueError(f"core inflation row not recognised: {label!r}")
    hit = dims.match_item(name, dims.load_dictionary("cpi_aggregates"))
    return hit if hit else (slug(name), name)


_REGION_KEYS = (  # checked in order on the normalised (Kazakh-folded) text of the whole row
    ("national", r"республик"), ("ALA", r"алматы каласы|г\.? ?алматы|город алматы"), ("AST", r"астана|нур-?султан"),
    ("SHM", r"шымкент"), ("ABY", r"\bабай"), ("AKM", r"акмол"), ("AKT", r"актоб|актюб"), ("ALM", r"алматы|алматинск"),
    ("ATY", r"атырау"), ("ZKO", r"батыс|западно"), ("ZHM", r"жамбыл"), ("ZHT", r"жетису|жетысу"), ("KRG", r"караганд"),
    ("KST", r"костанай"), ("KZL", r"кызылорд"), ("MNG", r"мангыстау|мангистау"), ("YKO", r"онтустик|южно"),
    ("PVL", r"павлодар"), ("SKO", r"солтустик|северо"), ("TRK", r"туркистан|туркестан"), ("ULT", r"улытау"),
    ("VKO", r"шыгыс|восточно"),
)


def region_of(row: Row) -> str | None:
    """Region code of a regional-table row from its Russian and/or Kazakh name (2019–2022
    editions print the regions in Kazakh only, some split over two cells)."""
    from lib import dims
    text = dims.normalise_label(f"{row.kz} {row.ru}").replace(" ", " ")
    for code, rx in _REGION_KEYS:
        if re.search(rx, text):
            return code
    return None


# ---------------------------------------------------------------- one edition → records

DATASET_PREFIX = {"national": "CPI_DETAIL", "regional": "CPI_DETAIL", "core": "CPI_DETAIL",
                  "retail": "RETAIL_PRICES", "retail_regional": "RETAIL_PRICES", "contribution": "CPI_CONTRIBUTION"}
REGIONAL_ITEMS = {"TOTAL", "GOODS", "FOOD", "NONFOOD", "SERVICES"}


def edition_records(tables: list[Table], year: int, month: int, resolve=None) -> tuple[dict[str, list[dict]], list[str]]:
    """{dataset_id: records} for one edition, and the problems met (conflicting duplicates,
    unrecognised regions). `resolve(kz, ru) -> ru` supplies the Russian label for the
    Kazakh-labelled editions (the backfill); the current publication is Russian and needs none.
    Regional tables keep only the blocks of the total and the groups. A row printed twice with
    the same value (a division in the summary and again as a heading in the detail) is one
    record; with different values the first is kept and the clash reported."""
    resolve = resolve or (lambda kz, ru: ru)
    date_ = f"{year:04d}-{month:02d}-01"
    out: dict[str, dict[tuple, dict]] = {}
    problems: list[str] = []
    for t in tables:
        prefix = DATASET_PREFIX[t.kind]
        labels = {} if t.kind in ("regional", "retail_regional") else qualified_labels(t, resolve)
        for r in t.rows:
            region = "national"
            if t.kind in ("regional", "retail_regional"):
                block = resolve(r.block_kz or "", r.block or "")
                code, name = item_of(block, t.kind)
                if code not in REGIONAL_ITEMS:
                    continue
                region = region_of(r)
                if region is None:
                    problems.append(f"{date_} {prefix} {t.kind}: region not recognised: {r.kz!r} / {r.ru!r}")
                    continue
            else:
                label = labels[id(r)]
                if not label:
                    problems.append(f"{date_} {prefix} {t.kind}: no Russian label for {r.kz!r}")
                    continue
                code, name = item_of(label, t.kind)
            for measure, value in r.values.items():
                ds = f"{prefix}_{measure.upper()}"
                key = (region, code)
                bucket = out.setdefault(ds, {})
                if key in bucket:
                    if abs(bucket[key]["value"] - value) > 1e-9:
                        problems.append(f"{date_} {ds} {code}@{region}: {bucket[key]['value']} kept, {value} ({name!r}) dropped")
                    continue
                bucket[key] = {"date": date_, "region": region, "item_code": code, "item_name": name, "value": value}
    return {ds: list(b.values()) for ds, b in out.items()}, problems


# Labels printed twice in one table with different values (2004–2020): «Мужская», «Женская»,
# «Детская» under «Верхняя одежда» and again under «Обувь»; «Колготки», «Сорочка верхняя»
# under the women's/men's and again under the children's clothing. Each occurrence gets the
# heading it sits under: «Мужская (обувь)», «Колготки (детская)».
_GROUP_HEADINGS = re.compile(r"^(верхняя одежда|одежда|обувь)$")
_GENDER_HEADINGS = re.compile(r"^(мужская|женская|детская)( одежда)?$|^одежда для (мужчин|женщин|детей|мальчиков|девочек)")


def qualified_labels(t: Table, resolve) -> dict[int, str]:
    from lib import dims
    labels = {id(r): resolve(r.kz, r.ru) for r in t.rows}
    norm = [dims.normalise_label(labels[id(r)]) for r in t.rows]
    values: dict[str, list] = {}
    for n, r in zip(norm, t.rows):
        values.setdefault(n, []).append(r.values)
    clashing = {n for n, v in values.items() if len(v) > 1 and any(x != v[0] for x in v[1:])}
    for i, r in enumerate(t.rows):
        if norm[i] not in clashing:
            continue
        heading_rx = _GROUP_HEADINGS if _GENDER_HEADINGS.match(norm[i]) else _GENDER_HEADINGS
        ctx = next((labels[id(t.rows[j])] for j in range(i - 1, -1, -1) if heading_rx.match(norm[j])), None)
        if ctx:
            labels[id(r)] = f"{labels[id(r)]} ({ctx.strip().lower()})"
    return labels


def parse_workbook(grids: dict[str, list[list]], year: int, month: int) -> list[Table]:
    tables = []
    for grid in grids.values():
        t = parse_grid(grid, year, month)
        if t is not None and t.rows:
            tables.append(t)
    return tables


# ---------------------------------------------------------------- the publication list

_MONTH_STEMS = (("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4), ("ма[йя]", 5), ("июн", 6), ("июл", 7),
                ("август", 8), ("сентябр", 9), ("октябр", 10), ("ноябр", 11), ("декабр", 12))


def edition_month(title: str) -> tuple[int, int] | None:
    """(year, month) of an edition from its title's parenthesis: «(август 2026 года)»,
    «( 2023 г. сентябрь)», «(10.2023)», «(  Сентябрь  2025 года)»."""
    m = re.search(r"\(([^()]*)\)\s*$", title.strip())
    if not m:
        return None
    s = m.group(1).lower()
    y = re.search(r"(20\d\d|19\d\d)", s)
    if not y:
        return None
    num = re.search(r"\b(\d{1,2})\.(?:20|19)\d\d", s)
    if num:
        return int(y.group(1)), int(num.group(1))
    for stem, month in _MONTH_STEMS:
        if re.search(stem, s):
            return int(y.group(1)), month
    return None


LISTING_URL = "https://stat.gov.kz/ru/industries/economy/prices/spreadsheets/?name={name}"
FILE_URL = "https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
PUBLICATION = "19117"                 # Т-15-02-М, October 2022 onward
PREDECESSORS = ("166775", "27168")    # «Индекс потребительских цен в РК» 1999-2022; «Вклад …» 2020-2022
_ROW_RE = re.compile(r'element/(\d+)/file/ru/">\s*([^<]*?)\s*</a>.*?text-right">([\d.]+)<.*?<span class="mr-1">([^<]*)</span>', re.S)


def parse_listing(page: str) -> list[dict]:
    """[{element_id, title, year, month, published, format}] from a spreadsheets listing page."""
    out = []
    for eid, title, published, size in _ROW_RE.findall(page):
        title = re.sub(r"\s+", " ", title).strip()
        ym = edition_month(title)
        if ym:
            out.append({"element_id": eid, "title": title, "year": ym[0], "month": ym[1], "published": published,
                        "format": size.split(",")[-1].strip().lower()})
    return sorted(out, key=lambda e: (e["year"], e["month"]))


# ---------------------------------------------------------------- update_dims entry point

_RUN: dict = {}           # one listing and one parse of each edition per process, shared by the datasets
KEEP_LATEST = 3           # editions re-read on every run (BNS republishes the latest month on occasion)


def _structural(what: str) -> None:
    from lib import validation
    raise validation.StructuralChangeError("\n".join([
        "STRUCTURAL CHANGE DETECTED in bns/CPI publication (Т-15-02-М)", f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: inspect {LISTING_URL.format(name=PUBLICATION)} and scripts/fetchers/bns_cpi.py"]))


def _latest_editions(stored_months: set[str]) -> tuple[dict[str, list[dict]], dict]:
    """Records of the editions not yet in the store, plus the latest KEEP_LATEST, and a
    manifest for all of them; computed once per process."""
    if "records" in _RUN:
        return _RUN["records"], _RUN["manifest"]
    from fetchers import bns, bns_dims
    page = bns._download(LISTING_URL.format(name=PUBLICATION)).decode("utf-8", "replace")
    listing = parse_listing(page)
    if not listing:
        _structural("the listing page lists no edition of «Индекс потребительских цен и производные показатели»")
    wanted = [e for e in listing if f"{e['year']:04d}-{e['month']:02d}-01" not in stored_months] + listing[-KEEP_LATEST:]
    records: dict[str, list[dict]] = {}
    warnings, read = [], []
    for e in sorted({e["element_id"]: e for e in wanted}.values(), key=lambda e: (e["year"], e["month"])):
        url = FILE_URL.format(eid=e["element_id"])
        content = bns._download(url)
        ext = "xls" if bns_dims.is_legacy_xls(content) else "xlsx"
        bns._save_raw(f"CPI_PUBLICATION_{e['year']:04d}{e['month']:02d}", content, ext,
                      {"source_url": url, "element_id": e["element_id"], "title": e["title"], "published": e["published"]})
        tables = parse_workbook(bns_dims._sheets(content), e["year"], e["month"])
        kinds = {t.kind for t in tables}
        if not {"national", "regional"} <= kinds:
            _structural(f"edition {e['title']!r}: no national and regional CPI tables among {sorted(kinds)}")
        recs, problems = edition_records(tables, e["year"], e["month"])
        warnings += [(p.split()[1], p) for p in problems if len(p.split()) > 1]
        warnings += [(DATASET_PREFIX[t.kind], f"{e['year']}-{e['month']:02d} {t.kind}: {t.repaired}") for t in tables if t.repaired]
        for ds_id, rs in recs.items():
            records.setdefault(ds_id, []).extend(rs)
        read.append(f"{e['year']}-{e['month']:02d}")
    latest = listing[-1]
    manifest = {"frequency": "monthly", "source_url": LISTING_URL.format(name=PUBLICATION), "dataset_id": PUBLICATION,
                "release": _iso(latest["published"]), "editions_read": read, "warnings": warnings}
    _RUN.update(records=records, manifest=manifest)
    return records, manifest


def _iso(ddmmyyyy: str) -> str | None:
    m = re.match(r"(\d\d)\.(\d\d)\.(\d{4})", ddmmyyyy or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def fetch(ds: dict) -> tuple[list[dict], dict]:
    """Stored history (the backfill of 2004-07 … 2022-09 from the predecessor publications, and
    every edition read since) with the new or re-read editions laid over it."""
    from lib import dims
    stored = dims.load_processed(ds["id"])
    fresh, manifest = _latest_editions({r["date"] for r in stored})
    merged = {(r["date"], r["region"], r["item_code"]): {**r, "value": float(r["value"])} for r in stored}
    for r in fresh.get(ds["id"], []):
        merged[(r["date"], r["region"], r["item_code"])] = r
    if not merged:
        _structural(f"no records for {ds['id']}")
    records = sorted(merged.values(), key=lambda r: (r["item_code"], r["region"], r["date"]))
    for r in records:
        r.pop("transformation", None)
    own = [text for tag, text in manifest["warnings"] if ds["id"].startswith(tag)]
    return records, {**manifest, "warnings": own, "note": ds.get("note", "")}
