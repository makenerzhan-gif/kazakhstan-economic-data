"""Two annual BNS balance tables, national, read from their publication listings:

AGRI_BALANCE -- «Баланс ресурсов и использования основных продуктов сельского хозяйства»
  (stat.gov.kz → Сельское, лесное, охотничье и рыбное хозяйство → Электронные таблицы,
  publication 19517; editions 2017-2021, 2022, 2023, 2024, 2025, each covering five years).
  Ten products, one per table: grain, grain products, meat, milk, eggs, potatoes, fruit,
  sugar beet, sunflower seed, vegetable oil. Rows: stocks at the start of the year,
  production, imports, total resources; productive use (feed, seed, incubation), processing
  into food, other industrial use, losses, exports, possible personal consumption (total and
  per head, kg or pieces a year; calories from 2023), stocks at the end of the year, the
  import share of grain. Thousand tonnes (eggs: million pieces). The latest edition that
  covers a year wins: BNS revised livestock for 2022-2023 in the 2025 edition, and table 10
  (vegetable oil) dropped the stock rows for a stock change in 2025.

ENERGY_BALANCE_TJ / ENERGY_BALANCE_NATURAL -- «Топливно-энергетический баланс Республики
  Казахстан» (Энергетика → Электронные таблицы, publication 19275; one edition a year,
  2021-2025 in xlsx). A fuels × flows matrix, IEA layout: table 2 in terajoules (with a
  «Всего» column), table 1 in natural units (the fuel's own unit, with its net calorific
  value). Item «<fuel>.<flow>»: the fuel is the column heading's slug (the unit is part of the
  heading in table 1, so a fuel whose unit changed -- coke-oven gas TJ in 2021, million m³
  later -- starts a new series); the flow is the row's slug, prefixed by its block:
      TRANSFORM_IN / TRANSFORM_OUT   transformation input / output (by plant type)
      ENERGY_OWN_USE                 energy sector own use
      FINAL_ENERGY[.INDUSTRY|.TRANSPORT|.OTHER]   final consumption for energy purposes
      FINAL_NON_ENERGY               final consumption for non-energy purposes
  and by S<section> for the rows outside a block (S1.proizvodstvo_dobycha_…, S1.import,
  S1.eksport, S3.statisticheskie_raskhozhdeniya …). The 2021 edition lists more fuels (crude
  oil and condensate apart, electricity by source), so a few fuels are 2021 only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402
from fetchers.bns_resource_use import _ROW_RE, _to_float, _TRANSLIT  # noqa: E402

LISTINGS = {"agri": "https://stat.gov.kz/ru/industries/business-statistics/stat-forrest-village-hunt-fish/spreadsheets/?name=19517",
            "energy": "https://stat.gov.kz/ru/industries/business-statistics/stat-energy/spreadsheets/?name=19275"}
TITLES = {"agri": re.compile(r"баланс ресурсов и использования основных продуктов сельского хозяйства", re.I),
          "energy": re.compile(r"топливно-энергетический баланс", re.I)}
FILE_URL = "https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"

AGRI_PRODUCTS = {"1": ("GRAIN", r"зерно$"), "2": ("GRAIN_PRODUCTS", r"продукты переработки зерна"),
                 "3": ("MEAT", r"мясо и мясопродукты"), "4": ("MILK", r"молоко и молочные продукты"),
                 "5": ("EGGS", r"яйца и яйцепродукты"), "6": ("POTATOES", r"картофель"),
                 "7": ("FRUIT", r"фрукты, виноград"), "8": ("SUGAR_BEET", r"сахарная свекла"),
                 "9": ("SUNFLOWER_SEED", r"семена подсолнечника"), "10": ("VEG_OIL", r"растительное масло")}
AGRI_ARTICLES = [("STOCK_BEGIN", r"^запасы на начало года"), ("PROD", r"^производство$"), ("IMP", r"^импорт$"),
                 ("RES", r"^итого ресурсов"), ("PROD_USE", r"^производствен+ое потребление"), ("FEED", r"^на корм"),
                 ("SEED", r"^на посевные"), ("INCUB", r"^на инкубацию"), ("FOOD_PROC", r"^переработка на продовольственные"),
                 ("OTHER_IND", r"^прочее промышленное"), ("LOSS", r"^потери$"), ("EXP", r"^экспорт$"),
                 ("CONS", r"^возможное личное потребление"), ("CONS_PC", r"^возможное потребление на душу"),
                 ("KCAL", r"^калорийность"), ("STOCK_END", r"^запасы на конец года"),
                 ("STOCK_CHG", r"^изменение запасов"), ("IMPORT_SHARE", r"^доля импорта")]
AGRI_ARTICLES = [(c, re.compile(rx)) for c, rx in AGRI_ARTICLES]

TEB_BLOCKS = [("TRANSFORM_IN", r"^сектор преобразования\W+вход"), ("TRANSFORM_OUT", r"^сектор преобразования\W+выход"),
              ("ENERGY_OWN_USE", r"^потребление в энергетическом секторе"),
              ("FINAL_ENERGY", r"^конечное потребление (энергии )?для энергетических целей|^конечное потребление энергии$"),
              ("FINAL_NON_ENERGY", r"^конечное потребление для неэнергетических целей"),
              ("FINAL_ENERGY.INDUSTRY", r"^сектор промышленности"), ("FINAL_ENERGY.TRANSPORT", r"^сектор транспорта"),
              ("FINAL_ENERGY.OTHER", r"^другие секторы")]
TEB_BLOCKS = [(c, re.compile(rx)) for c, rx in TEB_BLOCKS]
# rows that close a block: back to the section level
TEB_TOP = re.compile(r"^(потери при технологических|доступно для конечного потребления|статистические расхождения|"
                     r"теплотворная способность|общее первичное потребление)")
_SECTION = re.compile(r"^(\d)\.\s*")


def slug(label: str) -> str:
    s = dims.normalise_label(label)
    s = re.sub(r"\s*\.\s*", ".", s)
    return re.sub(r"[^a-z0-9]+", "_", s.translate(_TRANSLIT)).strip("_")[:70]


def _structural(what: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        "STRUCTURAL CHANGE DETECTED in bns/balances", f"WHAT CHANGED: {what}",
        "ACTION REQUIRED: inspect the publication and scripts/fetchers/bns_balances.py"]))


# ---------------------------------------------------------------- agriculture

def _years(row) -> list[int] | None:
    ys = []
    for c in row[1:]:
        m = re.match(r"^\s*(\d{4})(?:\.0)?\s*\*?\s*$", str(c)) if c not in (None, "") else None
        if m:
            ys.append(int(m.group(1)))
        elif c not in (None, ""):
            return None
    return ys if len(ys) >= 3 and ys == list(range(ys[0], ys[0] + len(ys))) else None


def parse_agri(sheets: dict[str, list[list]]) -> list[dict]:
    out = []
    for name, rows in sheets.items():
        sheet = name.strip()
        if sheet not in AGRI_PRODUCTS:
            continue
        code, title_rx = AGRI_PRODUCTS[sheet]
        title = next((str(r[0]) for r in rows[:4] if r and r[0] and re.match(r"\s*\d+\.", str(r[0]))), "")
        if not re.search(title_rx, dims.normalise_label(title)):
            _structural(f"agricultural balance table {sheet} is {title!r}, expected {title_rx}")
        yi = next((i for i, r in enumerate(rows[:8]) if _years(r)), None)
        if yi is None:
            _structural(f"agricultural balance table {sheet}: no year row")
        years = _years(rows[yi])
        unit = next((" ".join(str(c).split()) for r in rows[:yi] for c in r if isinstance(c, str) and re.search(r"тонн|штук", c)), "")
        for r in rows[yi + 1:]:
            label = r[0] if r else None
            vals = [_to_float(v) for v in r[1:1 + len(years)]] if r else []
            if not isinstance(label, str) or not any(v is not None for v in vals):
                continue
            norm = dims.normalise_label(label).rstrip(" *")
            art = next((a for a, rx in AGRI_ARTICLES if rx.search(norm)), None)
            if art is None:
                _structural(f"agricultural balance table {sheet}: row {label!r} matches no article")
            row_unit = "" if art in ("CONS_PC", "KCAL", "IMPORT_SHARE") else f", {unit}"
            for y, v in zip(years, vals):
                if v is not None:
                    out.append({"date": f"{y:04d}-12-31", "region": dims.NATIONAL, "item_code": f"{code}.{art}",
                                "item_name": f"{title.split('.', 1)[-1].strip()} — {' '.join(label.split()).rstrip(' *')}{row_unit}",
                                "value": v})
    return out


# ---------------------------------------------------------------- fuel-energy balance

def parse_energy(rows: list[list], year: int) -> list[dict]:
    """One table (natural units or TJ) of one year's balance."""
    hi = next((i for i, r in enumerate(rows[:10]) if r and r[0] and str(r[0]).strip().lower().startswith("теплотворная")), None)
    if hi is None:   # the TJ table has no calorific-value row: the fuel row is the one before '1. …'
        hi = next((i for i, r in enumerate(rows[:12]) if r and r[0] and _SECTION.match(str(r[0]).strip())), None)
    if hi is None or hi < 2:
        _structural(f"energy balance {year}: no header rows")
    fi = next((i for i in range(hi - 1, -1, -1) if rows[i] and sum(1 for c in rows[i][1:] if c not in (None, "")) >= 3), None)
    gi = next((i for i in range(fi - 1, -1, -1) if rows[i] and any(c not in (None, "") for c in rows[i][1:])), None) if fi else None
    if fi is None or gi is None:
        _structural(f"energy balance {year}: no fuel heading rows")
    fuels_row, groups_row = rows[fi], rows[gi]           # fuel names; their groups (gas, electricity, heat, «Всего»)
    fuels = {}
    for c in range(1, max(len(fuels_row), len(groups_row))):
        label = (fuels_row[c] if c < len(fuels_row) else None) or (groups_row[c] if c < len(groups_row) else None)
        if label and str(label).strip():
            text = " ".join(str(label).split())
            fuels[c] = ("TOTAL" if dims.normalise_label(text) == "всего" else slug(text), text)
    if len(fuels) < 20:
        _structural(f"energy balance {year}: only {len(fuels)} fuel columns")
    out, seen = [], set()
    block, section = None, "0"
    for r in rows[hi:]:
        label = r[0] if r else None
        if not isinstance(label, str) or not label.strip():
            continue
        text = " ".join(label.split())
        norm = dims.normalise_label(text)
        if re.match(r"^\d\)", text):
            break                                      # the footnotes
        sec = _SECTION.match(norm)
        if sec:
            section, block = sec.group(1), None
            norm = norm[sec.end():]
            flow = f"S{section}.{slug(norm)}"
        else:
            hit = next((c for c, rx in TEB_BLOCKS if rx.search(norm)), None)
            if hit:
                block, flow = hit, hit
            elif TEB_TOP.search(norm) or block is None:
                block, flow = None, f"S{section}.{slug(norm)}"
            else:
                flow = f"{block}.{slug(norm)}"
        if flow in seen:
            _structural(f"energy balance {year}: flow {flow!r} twice ({text!r})")
        seen.add(flow)
        for c, (fuel, fuel_name) in fuels.items():
            v = _to_float(r[c]) if c < len(r) else None
            if v is not None:
                out.append({"date": f"{year:04d}-12-31", "region": dims.NATIONAL, "item_code": f"{fuel}.{flow}",
                            "item_name": f"{fuel_name} — {text}", "value": v})
    return out


# ---------------------------------------------------------------- update_dims entry point

_RUN: dict = {}


def _editions(kind: str) -> list[dict]:
    from fetchers import bns
    page = bns._download(LISTINGS[kind]).decode("utf-8", "replace")
    out = []
    for eid, title, published, size in _ROW_RE.findall(page):
        title = " ".join(title.split())
        years = [int(y) for y in re.findall(r"(\d{4})", title)]
        if TITLES[kind].search(title) and years and size.split(",")[-1].strip().lower() == "xlsx":
            out.append({"element_id": eid, "title": title, "year": max(years), "published": published})
    if not out:
        _structural(f"the {kind} listing {LISTINGS[kind]} lists no xlsx edition")
    return sorted(out, key=lambda e: e["year"])


def _read(kind: str) -> dict:
    """{'tables': {table: {(date, item): record}}, 'read': [...]}: every edition, oldest first,
    a later edition overriding the years it repeats."""
    if kind in _RUN:
        return _RUN[kind]
    from fetchers import bns, bns_dims
    tables: dict[str, dict] = {}
    read = []
    for e in _editions(kind):
        url = FILE_URL.format(eid=e["element_id"])
        content = bns._download(url)
        bns._save_raw(f"{kind.upper()}_BALANCE_{e['year']}", content, "xlsx",
                      {"source_url": url, "element_id": e["element_id"], "title": e["title"], "published": e["published"]})
        sheets = bns_dims._sheets(content)
        if kind == "agri":
            parts = {"agri": parse_agri(sheets)}
        else:
            parts = {}
            for name, table in (("1", "natural"), ("2", "tj")):
                rows = next((v for k, v in sheets.items() if k.strip() == name), None)
                if rows is None:
                    _structural(f"energy balance {e['title']!r}: no table {name}")
                parts[table] = parse_energy(rows, e["year"])
        for table, recs in parts.items():
            if kind == "energy":
                # one year per edition: a later edition of the same year replaces it whole
                tables[table] = {k: r for k, r in tables.get(table, {}).items() if k[0] != f"{e['year']:04d}-12-31"}
            for r in recs:
                tables.setdefault(table, {})[(r["date"], r["item_code"])] = r
        read.append(e["title"])
    _RUN[kind] = {"tables": tables, "read": read, "source_url": LISTINGS[kind]}
    return _RUN[kind]


def fetch(ds: dict) -> tuple[list[dict], dict]:
    """ds['balance']: 'agri', 'energy_natural' or 'energy_tj'."""
    kind, table = {"agri": ("agri", "agri"), "energy_natural": ("energy", "natural"), "energy_tj": ("energy", "tj")}[ds["balance"]]
    run = _read(kind)
    records = sorted(run["tables"].get(table, {}).values(), key=lambda r: (r["item_code"], r["date"]))
    latest = max((r["date"] for r in records), default=None)
    n = len({r["item_code"] for r in records if r["date"] == latest})
    if n < ds.get("min_items", 1):
        _structural(f"{ds['id']}: {n} items in {latest}, expected at least {ds.get('min_items')}")
    return records, {"frequency": "annual", "source_url": run["source_url"], "dataset_id": run["source_url"].rsplit("=", 1)[-1],
                     "note": ds.get("note", ""), "warnings": [], "editions_read": run["read"]}
