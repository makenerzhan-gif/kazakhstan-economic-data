"""Budget classifications from Minfin's monthly Statistical Bulletin (added 2026-11-13).

Two item-level datasets, both January-to-month in million KZT, dated the first day of the
period's last month (the dims convention for year-to-date flows), one edition per date, read
through fetchers/minfin (so its listing, download cache and archive mode apply):

BUDGET_EXPENDITURE_ECONOMIC_YTD (fetch_economic) -- the economic classification of expenditure:
  «табл 6»  state budget (republican + local, consolidated), subclasses;
  «табл 10» republican budget, subclasses and specifics;
  «таб 11»  local budgets, subclasses and specifics.
  Item <BUDGET>.<code>, BUDGET = STATE / REP / LOCAL; code = TOTAL, CAT1 … CAT6 (categories:
  1 current, 2 capital, 3 budget loans, 4 acquisition of financial assets, 6 PPP obligations),
  the three-digit subclass (110 wages, 210 interest on domestic loans, 320 transfers to
  individuals …) or specific (111 pay, 323 pensions …), and GFS.<nn>: the subclasses regrouped
  into the IMF's GFSM 2014 economic classification (GFS_MAP below) -- a bridge by SUBCLASS, so an
  approximation: «другие текущие затраты» (160) holds «особые затраты», scholarships sit in 320,
  and the budget is on a cash basis with no consumption of fixed capital (GFS 23).
  The classification is the one the bulletin prints; the order that defined it (Minfin
  order 403 of 18.09.2014) was replaced in April 2025 and the bulletin's rows changed little.
  Checked in every edition (StructuralChangeError): subclasses add up to their category and
  the categories to the total, within 0.5 mln KZT + 0.01 %.

RESOURCE_PAYMENTS_YTD (fetch_resource) -- payments for the use of natural resources and
  export duties on oil in the STATE budget, from «табл 4» (receipts by budget code), i.e. the
  payments of everyone EXCEPT the organisations of the oil sector, whose direct taxes go to
  the National Fund (the NF_*_YTD scalars). Items MET_NON_OIL (mineral extraction tax),
  MET_COMMON_MINERALS (from the 2026 editions), EPT_NON_OIL, BONUS_NON_OIL, RENT_TAX_NON_OIL,
  PSA_SHARE_NON_OIL, PSA_ADDITIONAL, HISTORICAL_COSTS, RESOURCE_USE_TOTAL (the subclass total, which
  also holds water, forest, land and spectrum fees), EXPORT_DUTY_CRUDE, EXPORT_DUTY_OIL_PRODUCTS.
  Derived: NON_OIL_SUBSOIL = the subsoil payments of the non-oil sector (MET + common minerals
  + EPT + bonuses + rent tax + PSA + historical costs); OIL_SECTOR_NF = the oil sector's direct
  taxes paid into the National Fund (NF_OIL_DIRECT_TAXES_YTD, when that month exists);
  OIL_TOTAL = OIL_SECTOR_NF + the two export duties. «Oil sector» is the Government's list of
  crude-oil and condensate producers, NOT ОКЭД division 06; «non-oil» is everyone else --
  metal ores, coal, uranium, gas, building materials -- NOT division 07. Corporate income tax
  and VAT of mining companies are not separable from other payers and are outside both.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import minfin  # noqa: E402
from fetchers import minfin_regions as mr  # noqa: E402
from lib import dims, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ECON_SHEETS = {"таб6": "STATE", "таб10": "REP", "таб11": "LOCAL"}
BUDGET_NAMES = {"STATE": "Государственный бюджет", "REP": "Республиканский бюджет", "LOCAL": "Местные бюджеты"}
CATEGORIES = [(1, r"^текущие затраты"), (2, r"^капитальные затраты"), (3, r"^бюджетные кредиты"),
              (4, r"^приобретение финансовых активов"), (5, r"^погашение займов"), (6, r"^выполнение государственных обязательств по проектам")]
# GFSM 2014 item: (lowest, highest) subclass. 8xx (PPP obligations) is left out: it mixes
# interest, investment compensation and operating payments.
GFS_MAP = {"21": [(110, 139)], "22": [(140, 169)], "24": [(210, 229)], "25": [(310, 319)], "27": [(320, 329)],
           "26": [(330, 349), (440, 449)], "28": [(170, 199), (350, 399)], "31": [(410, 439)], "32": [(510, 699)]}
GFS_NAMES = {"21": "оплата труда работников (GFS 21: подклассы 110-130)", "22": "использование товаров и услуг (GFS 22: 140-160)",
             "24": "проценты (GFS 24: 210-220)", "25": "субсидии (GFS 25: 310)", "27": "социальные пособия (GFS 27: 320)",
             "26": "гранты другим уровням управления и за границу (GFS 26: 330-340, 440)", "28": "прочие расходы (GFS 28: 170, 360-370)",
             "31": "приобретение нефинансовых активов (GFS 31: 410-430)",
             "32": "бюджетные кредиты и приобретение финансовых активов (GFS 32, не расход: 510-620)"}


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"minfin/{ds['id']}: {what}")


def _code(cell) -> str | None:
    """A three-digit classification code in a cell ('110', 110.0), else None («L01 Категория расходов»)."""
    if isinstance(cell, float) and cell.is_integer():
        cell = int(cell)
    s = str(cell).strip() if cell is not None else ""
    return s if re.fullmatch(r"\d{3}", s) else None


def _label(row) -> str:
    return " ".join(minfin._row_label(row).replace("_x000D_", " ").split())


def economic_lines(rows: list[list], col: int, with_specifics: bool) -> list[tuple[str, str, float]]:
    """[(code, Russian label, value)] of one sheet: TOTAL, CAT<n>, subclasses, specifics."""
    out, category = [], None
    for r in rows:
        if col >= len(r):
            continue
        value, label = mr._value(r[col]), _label(r)
        if value is None or not label:
            continue
        norm = mr._norm(label)
        sub = _code(r[1]) if len(r) > 1 else None
        spec = _code(r[2]) if with_specifics and len(r) > 2 else None
        if norm.startswith("всего"):
            out.append(("TOTAL", "Всего", value))
        elif spec:
            out.append((spec, label, value))
        elif sub:
            # the bulletin prints «370» with no name where the row is the educational grant
            out.append((sub, label if not re.fullmatch(r"\d{3}", label) else f"Подкласс {sub}", value))
        else:
            hit = next((n for n, rx in CATEGORIES if re.search(rx, norm)), None)
            if hit is not None and hit != category:          # «Приобретение финансовых активов» is category 4 and subclass 610
                category = hit
                out.append((f"CAT{hit}", label, value))
    return out


def check_sums(lines: list[tuple[str, str, float]], ds: dict, where: str) -> None:
    vals, order = {}, []
    for code, _, v in lines:
        vals[code] = v
        order.append(code)
    cats = [c for c in order if c.startswith("CAT")]
    # the PDF editions of 2005-2012 print whole millions: every term of a sum can be half a million off
    whole = all(float(v).is_integer() for v in vals.values())
    tol = lambda x, n=1: 0.5 + 1e-4 * abs(x) + (0.5 * n if whole else 0.0)   # noqa: E731
    if "TOTAL" not in vals or not cats:                                  # nothing to check against: not this table
        _structural(ds, f"{where}: no «Всего» row or no category rows")
    if "TOTAL" in vals and cats and abs(sum(vals[c] for c in cats) - vals["TOTAL"]) > tol(vals["TOTAL"], len(cats)):
        _structural(ds, f"{where}: categories sum to {sum(vals[c] for c in cats):.1f}, «Всего» is {vals['TOTAL']:.1f}")
    current = None
    parts: dict[str, float] = {}
    count: dict[str, int] = {}
    for code in order:
        if code.startswith("CAT"):
            current = code
        elif current and re.fullmatch(r"\d{2}0", code):                  # subclasses end in 0, specifics do not
            parts[current] = parts.get(current, 0.0) + vals[code]
            count[current] = count.get(current, 0) + 1
    for cat, total in parts.items():
        if abs(total - vals[cat]) > tol(vals[cat], count[cat]):
            _structural(ds, f"{where}: the subclasses of {cat} sum to {total:.1f}, the category is {vals[cat]:.1f}")


def gfs_lines(lines: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    subs = {int(c): v for c, _, v in lines if re.fullmatch(r"\d{2}0", c)}
    out = []
    for item, ranges in GFS_MAP.items():
        hit = [v for c, v in subs.items() if any(lo <= c <= hi for lo, hi in ranges)]
        if hit:
            out.append((f"GFS.{item}", GFS_NAMES[item], round(sum(hit), 4)))
    return out


def _edition_period(sheets: dict[str, list[list]]) -> tuple[int, int] | None:
    periods = [p[:2] for rows in sheets.values() for p in mr._period_cols(rows)]
    if periods:
        return max(periods)
    years = [y for rows in sheets.values() for y, _ in mr._report_cols(rows)]
    return (max(years), 12) if years else None


def _column(rows: list[list], year: int, month: int) -> int | None:
    col = next((c for y, m, c in mr._period_cols(rows) if (y, m) == (year, month)), None)
    if col is None and month == 12:
        col = min((c for y, c in mr._report_cols(rows) if y == year), default=None)
    return col


def economic_edition(sheets: dict[str, list[list]], ds: dict, gfs: bool = True) -> tuple[str | None, list[dict], list[str]]:
    wanted = {minfin._sheet_key(n): rows for n, rows in sheets.items() if minfin._sheet_key(n) in ECON_SHEETS}
    period = _edition_period(wanted)
    if period is None:
        return None, [], []
    year, month = period
    d = f"{year}-{month:02d}-01"
    records, notes = [], []
    for key, budget in ECON_SHEETS.items():
        rows = wanted.get(key)
        col = _column(rows, year, month) if rows else None
        if col is None:
            notes.append(f"{d}: no {budget} sheet or period column")
            continue
        lines = economic_lines(rows, col, with_specifics=key != "таб6")
        try:
            check_sums(lines, ds, f"{d} {budget}")
        except validation.StructuralChangeError as exc:
            if not minfin.BULLETIN_ARCHIVE:
                raise
            notes += [f"SKIPPED {budget} -- {str(exc)[:200]}"] + _top_rows({key: rows})   # the other budgets of the edition are kept
            continue
        for code, label, v in lines + (gfs_lines(lines) if gfs else []):
            records.append({"date": d, "region": dims.NATIONAL, "item_code": f"{budget}.{code}",
                            "item_name": f"{BUDGET_NAMES[budget]}: {label}", "value": round(v, 4)})
    return d, records, notes


def _editions(wanted_keys) -> list[tuple[dict, dict[str, list[list]], list[str]]]:
    docs = minfin._bulletin_documents()
    if not docs:
        raise validation.StructuralChangeError("minfin_classification: no Statistical Bulletin in the listing")
    out = []
    for doc in docs:                                   # newest first: an edition already read wins
        path = doc["full_text"][0]["document"]
        kind, wb = minfin._open_workbook(minfin._download(path), path)
        names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        out.append((doc, {n: list(minfin._iter_rows(kind, wb, n)) for n in names if minfin._sheet_key(n) in wanted_keys}, list(names)))
    return out


EDITION_NOTES: dict[str, list[str]] = {}       # dataset id -> what every edition gave (the backfill script prints it in full)


def _top_rows(sheets: dict[str, list[list]], limit: int = 40) -> list[str]:
    """The rows of each sheet that carry no code below the first level (header, totals, categories):
    enough to see how an unfamiliar edition is laid out."""
    out = []
    for name, rows in sheets.items():
        out.append(f"    [{name}] {len(rows)} rows")
        shown = 0
        for i, r in enumerate(rows):
            cells = [str(c).strip().replace("\n", " ")[:38] for c in r[:9] if c not in (None, "")]
            low = [c for c in r[1:4] if re.fullmatch(r"\d{1,3}(\.0)?", str(c).strip() if c is not None else "")]
            if cells and (i < 9 or not low) and shown < limit:
                out.append(f"      {i}: {cells}")
                shown += 1
    return out


def _read_editions(ds: dict, wanted_keys, edition) -> tuple[dict[str, list[dict]], list[str]]:
    """Every listed edition through `edition(sheets) -> (date, records, notes)`, newest first (an
    edition already read wins). In the daily run a broken edition stops the dataset. In archive mode
    (scripts/backfill_minfin_bulletins.py: years of older editions, whose layout may differ) it is
    skipped and reported with the sheets it has, so that one odd year does not cost the rest."""
    got, warnings, dumped = {}, [], set()
    for doc, sheets, names in _editions(wanted_keys):
        tag = f"{doc.get('id')} «{(doc.get('title') or '')[:60]}»"
        try:
            d, records, notes = edition(sheets)
        except validation.StructuralChangeError as exc:
            if not minfin.BULLETIN_ARCHIVE:
                raise
            warnings.append(f"{tag}: SKIPPED -- {str(exc)[:300]}")
            kind = re.sub(r"[\d.,-]+", "#", str(exc).split(":", 2)[-1])[:60]         # one layout dump per kind of break
            if kind not in dumped and len(dumped) < 12:
                dumped.add(kind)
                warnings += _top_rows(sheets)
            continue
        if d is None and minfin.BULLETIN_ARCHIVE:
            notes = notes + ["no period found"]
        if minfin.BULLETIN_ARCHIVE:
            kept, show = [], True
            for n in notes:                              # a layout dump for the first few breaks of each kind only
                if n.startswith("SKIPPED"):
                    kind = re.sub(r"[\d.,-]+", "#", n)[:70]
                    show = kind not in dumped and len(dumped) < 14
                    dumped.add(kind)
                    kept.append(n)
                elif n.startswith("    "):
                    if show:
                        kept.append(n)
                else:
                    kept.append(n)
            if any(not n.startswith(("SKIPPED", "    ")) for n in kept):   # a sheet was not found: say which the edition has
                kept.append(f"sheets: {[str(n)[:14] for n in names]}")
            notes = kept
        warnings += [n if n.startswith("    ") else f"{tag}: {n}" for n in notes]
        if d and d not in got and records:
            got[d] = records
    EDITION_NOTES[ds["id"]] = warnings
    return got, warnings


def _merge(ds: dict, got: dict[str, list[dict]]) -> list[dict]:
    stored = [{"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
               "value": float(r["value"])} for r in dims.load_processed(ds["id"]) if r["date"] not in got]
    records = [r for recs in got.values() for r in recs] + stored
    if not records:
        _structural(ds, "nothing read from any bulletin")
    return sorted(records, key=lambda r: (r["item_code"], r["date"]))


# The economic classification of expenditure was renumbered from 2013 (130 is «Приобретение товаров» in 2012 and
# «Выплата заработной платы отдельным категориям граждан…» from 2013), so the editions of 2005-2012 are a dataset of
# their own: the same code is not the same item across that line, and the GFS bridge is written for the new codes.
OLD_CLASSIFICATION_BEFORE = "2013-01-01"


def fetch_economic(ds: dict) -> tuple[list[dict], dict]:
    def edition(sheets):
        d, records, notes = economic_edition(sheets, ds)
        if d and d < OLD_CLASSIFICATION_BEFORE:
            return d, [], []
        return d, records, notes
    got, warnings = _read_editions(ds, set(ECON_SHEETS), edition)
    return _merge(ds, got), {"frequency": "monthly", "source_url": minfin.LISTING_URL,
                             "dataset_id": "Statistical Bulletin tables 6, 10, 11", "note": ds.get("note", ""), "warnings": warnings}


def fetch_economic_old(ds: dict) -> tuple[list[dict], dict]:
    """The editions of 2005-2012 (PDF, read through fetchers/minfin_pdf.py), under the classification of those
    years. The daily run has none of them listed and returns the stored rows; the history is loaded by
    scripts/backfill_minfin_bulletins.py --yearly 2005-2012."""
    meta = {"frequency": "monthly", "source_url": minfin.LISTING_URL, "dataset_id": "Statistical Bulletin, economic classification of expenditure, 2005-2012",
            "note": ds.get("note", ""), "warnings": []}
    if not minfin.BULLETIN_ARCHIVE:
        return _merge(ds, {}), meta

    def edition(sheets):
        d, records, notes = economic_edition(sheets, ds, gfs=False)
        if d and d >= OLD_CLASSIFICATION_BEFORE:
            return d, [], []
        return d, records, notes
    got, meta["warnings"] = _read_editions(ds, set(ECON_SHEETS), edition)
    return _merge(ds, got), meta


# ---------------------------------------------------------------- resource payments

RESOURCE_LINES = [  # (code, Russian name, regex on the normalised label); the first match of a row wins
    ("RESOURCE_USE_TOTAL", "Поступления за использование природных и других ресурсов, всего", r"^поступления за использование природных и других ресурсов"),
    ("EPT_NON_OIL", "Налог на сверхприбыль, кроме организаций нефтяного сектора", r"^налог на сверхприбыль"),
    ("BONUS_NON_OIL", "Бонусы, кроме организаций нефтяного сектора", r"^бонусы"),
    ("MET_COMMON_MINERALS", "НДПИ на общераспространённые полезные ископаемые, подземные воды и лечебные грязи", r"^налог на добычу полезных ископаемых на общераспространенные"),
    ("MET_NON_OIL", "Налог на добычу полезных ископаемых, кроме организаций нефтяного сектора", r"^налог на добычу полезных ископаемых"),
    ("RENT_TAX_NON_OIL", "Рентный налог на экспорт, кроме организаций нефтяного сектора", r"^рентный налог на экспорт"),
    ("PSA_SHARE_NON_OIL", "Доля Республики Казахстан по разделу продукции, кроме организаций нефтяного сектора", r"^доля республики казахстан по разделу продукции"),
    ("PSA_ADDITIONAL", "Дополнительный платёж недропользователя по контракту о разделе продукции", r"^дополнительный платеж недропользователя"),
    ("HISTORICAL_COSTS", "Платёж по возмещению исторических затрат", r"^платеж по возмещению исторических затрат"),
    ("EXPORT_DUTY_CRUDE", "Вывозные таможенные пошлины на сырую нефть", r"^вывозные таможенные пошлины на сырую нефть"),
    ("EXPORT_DUTY_OIL_PRODUCTS", "Вывозные таможенные пошлины на товары, выработанные из нефти", r"^вывозные таможенные пошлины на товары, выработанные из нефти"),
]
_RESOURCE = [(c, n, re.compile(r)) for c, n, r in RESOURCE_LINES]
SUBSOIL = ("MET_NON_OIL", "MET_COMMON_MINERALS", "EPT_NON_OIL", "BONUS_NON_OIL", "RENT_TAX_NON_OIL", "PSA_SHARE_NON_OIL",
           "PSA_ADDITIONAL", "HISTORICAL_COSTS")
REQUIRED = ("RESOURCE_USE_TOTAL", "MET_NON_OIL", "EXPORT_DUTY_CRUDE")


def resource_lines(rows: list[list], col: int) -> dict[str, float]:
    out = {}
    for r in rows:
        if col >= len(r):
            continue
        value, norm = mr._value(r[col]), mr._norm(_label(r)).replace("общераспространенныеполезные", "общераспространенные полезные")
        if value is None or not norm:
            continue
        code = next((c for c, _, rx in _RESOURCE if rx.search(norm)), None)
        if code and code not in out:                 # the same label lower down (arrears tables) is not read
            out[code] = value
    return out


def _nf_oil_direct() -> dict[str, float]:
    path = REPO_ROOT / "data" / "processed" / "minfin" / "nf_oil_direct_taxes_ytd.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["date"][:7] + "-01": float(r["value"]) for r in csv.DictReader(f) if r.get("value")}


def resource_edition(sheets: dict[str, list[list]], ds: dict, nf: dict[str, float]) -> tuple[str | None, list[dict], list[str]]:
    rows = next((rows for n, rows in sheets.items() if minfin._sheet_key(n) == "таб4"), None)
    period = _edition_period({"таб4": rows}) if rows else None
    if period is None:
        return None, [], []
    year, month = period
    d = f"{year}-{month:02d}-01"
    col = _column(rows, year, month)
    if col is None:
        return d, [], [f"{d}: no period column in «табл 4»"]
    vals = resource_lines(rows, col)
    missing = [c for c in REQUIRED if c not in vals]
    if missing:
        _structural(ds, f"{d}: «табл 4» has no row for {missing}")
    # No «subsoil <= subclass total» check: the subclass also holds fees that can be negative in a
    # month (refunds of the radio-spectrum fee: -5 362 mln in January 2026, when subsoil payments
    # were 58 862 and the subclass total 54 876).
    subsoil = sum(vals.get(c, 0.0) for c in SUBSOIL)
    names = {c: n for c, n, _ in RESOURCE_LINES}
    names["NON_OIL_SUBSOIL"] = "Платежи недропользователей, кроме нефтяного сектора (НДПИ, сверхприбыль, бонусы, рентный налог, СРП, исторические затраты), расчёт"
    vals["NON_OIL_SUBSOIL"] = subsoil
    duties = vals["EXPORT_DUTY_CRUDE"] + vals.get("EXPORT_DUTY_OIL_PRODUCTS", 0.0)
    if d in nf:
        names["OIL_SECTOR_NF"] = "Прямые налоги организаций нефтяного сектора в Национальный фонд (NF_OIL_DIRECT_TAXES_YTD)"
        names["OIL_TOTAL"] = "Нефтяной сектор: прямые налоги в Национальный фонд и вывозные пошлины на нефть и нефтепродукты, расчёт"
        vals["OIL_SECTOR_NF"], vals["OIL_TOTAL"] = nf[d], nf[d] + duties
    return d, [{"date": d, "region": dims.NATIONAL, "item_code": c, "item_name": names[c], "value": round(v, 4)}
               for c, v in vals.items()], []


def fetch_resource(ds: dict) -> tuple[list[dict], dict]:
    nf = _nf_oil_direct()
    def edition(sheets):
        d, records, notes = resource_edition(sheets, ds, nf)
        if d and d < OLD_CLASSIFICATION_BEFORE and records:
            # the PDF editions: the lines are found by name, so the table they stand in must first add up
            _, receipts, _ = receipts_edition(sheets, {"id": ds["id"]})
            if not any(r["item_code"] == "STATE.TOTAL" for r in receipts):
                return d, [], [f"{d}: «табл 4» does not add up, its resource lines are not taken"]
        return d, records, notes
    got, warnings = _read_editions(ds, {"таб4"}, edition)
    return _merge(ds, got), {"frequency": "monthly", "source_url": minfin.LISTING_URL,
                             "dataset_id": "Statistical Bulletin table 4", "note": ds.get("note", ""), "warnings": warnings}


# ---------------------------------------------------------------- receipts by budget code

RECEIPT_SHEETS = {"таб4": "STATE", "таб8(дох)": "REP"}
# «ПОСТУПЛЕНИЯ*» in the 2019-2020 editions, «I. ДОХОДЫ» in the PDF of January 2008
RECEIPT_TOP = (("TOTAL", r"^поступления\*?$"), ("REVENUE", r"^(i\.\s*)?доходы\*?$"))
REVENUE_CATEGORIES = ("1", "2", "3", "4", "5")      # «ДОХОДЫ»; «ПОСТУПЛЕНИЯ» adds 6 and 7
# The 2026 Budget Code put «Специальные поступления» in as category 4 and moved the three after it
# down by one (transfers 4 -> 5, repayment of budget loans 5 -> 6, sale of financial assets 6 -> 7).
# A category is therefore recognised by its name and always stored under its 2026 number, so that
# one code is one thing in every year.
RECEIPT_CATEGORIES = (("1", r"^налоговые поступления"), ("2", r"^неналоговые поступления"),
                      ("3", r"^поступления от продажи основного капитала"), ("4", r"^специальные поступления"),
                      ("5", r"^поступления (официальных )?трансфертов"), ("6", r"^погашение бюджетных кредитов"),
                      ("7", r"^поступления от продажи финансовых активов"),
                      ("8", r"^поступлени[ея] займов"),
                      ("9", r"^(используемые остатки|движение остатков) бюджетных средств"))
# 8 and 9 (borrowing and the use of balances) were printed in the table until 2021 under the old
# numbers 7 and 8; «ПОСТУПЛЕНИЯ» of those editions includes them.


def _digits(cell, width: int) -> str | None:
    """A code cell: «1», «05», 5.0 -> the code padded to its width; blank or the «L01 ...» filler -> None."""
    if cell is None:
        return None
    s = str(cell).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s.zfill(width) if re.fullmatch(r"\d{1,%d}" % width, s) else None


def _code_offset(rows: list[list]) -> int | None:
    """Column of the category code: the numbering row «1 2 3 4 ...» under the header marks it."""
    for r in rows[:15]:
        cells = [str(c).strip()[:-2] if re.fullmatch(r"\d+\.0", str(c).strip()) else str(c).strip() for c in r]
        for i in range(len(cells) - 3):
            if cells[i:i + 4] == ["1", "2", "3", "4"]:
                return i
    return None


def receipt_lines(rows: list[list], col: int, off: int) -> list[tuple[str, str, float]]:
    """(code, label, value): TOTAL, REVENUE, category «1», class «105», subclass «1053», specific «105306»."""
    out, cat, cls, sub, started, printed = [], None, None, None, False, None
    for r in rows:
        if col >= len(r) or off + 4 > len(r):
            continue
        value, label = mr._value(r[col]), _label(r)
        if value is None or not label:
            continue
        c = [_digits(r[off + i], w) for i, w in enumerate((1, 2, 1, 2))]
        if c == ["1", "02", "3", "04"] and not started:          # the numbering row itself
            continue
        if not any(c):
            top = next((code for code, rx in RECEIPT_TOP if re.search(rx, mr._norm(label))), None)
            if top:
                out.append((top, label, value))
                started = True
            elif started and re.search(RECEIPT_CATEGORIES[-1][1], mr._norm(label)):
                # the republican table of 2019-2021 prints the use of balances with no code at all
                cat, cls, sub = RECEIPT_CATEGORIES[-1][0], None, None
                out.append((cat, label, value))
            continue
        started = True
        if c[0] and c[0] != printed and not any(c[1:]):          # a category row: its name decides the number
            cat = next((code for code, rx in RECEIPT_CATEGORIES if re.search(rx, mr._norm(label))), None)
            if cat is None:
                raise ValueError(f"unknown receipt category «{label[:60]}»")
            printed, cls, sub = c[0], None, None
            out.append((cat, label, value))
        elif c[0] and c[0] != printed:
            raise ValueError(f"category {c[0]} on «{label[:40]}» without a category row")
        elif c[3]:
            cls, sub = c[1] or cls, c[2] or sub
            if not (cat and cls and sub):
                raise ValueError(f"specific «{label[:40]}» before its category, class or subclass")
            out.append((cat + cls + sub + c[3], label, value))
        elif c[2]:
            sub = c[2]
            if not (cat and cls):
                raise ValueError(f"subclass «{label[:40]}» before its category or class")
            out.append((cat + cls + sub, label, value))
        elif c[1]:
            cls, sub = c[1], None
            if not cat:
                raise ValueError(f"class «{label[:40]}» before its category")
            out.append((cat + cls, label, value))
        else:
            raise ValueError(f"category row {c[0]} twice: «{label[:40]}»")
    return out


def check_receipts(lines: list[tuple[str, str, float]], revenue_optional: bool = False) -> list[str]:
    """Every level must equal the sum of the one below it; returns the breaks (empty when all hold)."""
    vals, bad = {}, []
    for code, _, v in lines:
        if code in vals:
            bad.append(f"code {code} twice")
        vals[code] = v
    whole = all(float(v).is_integer() for v in vals.values())     # the PDF editions of 2005-2012 print whole millions
    slack = lambda n: 0.5 * (n + 1) if whole else 0.0             # noqa: E731
    def children(parent, n):
        return [v for k, v in vals.items() if k.isdigit() and len(k) == n and k.startswith(parent)]
    for code, v in vals.items():
        if not code.isdigit() or len(code) == 6:
            continue
        kids = children(code, {1: 3, 3: 4, 4: 6}[len(code)])
        if not kids:
            if code != "9":                              # the use of balances is one figure with nothing under it
                bad.append(f"{code} has no lines below it")
        elif abs(sum(kids) - v) > max(1.0, 1e-6 * abs(v)) + slack(len(kids)):
            bad.append(f"{code}: {v:.1f} against {sum(kids):.1f} below it")
    cats = {k: v for k, v in vals.items() if k.isdigit() and len(k) == 1}
    for top, keys in (("REVENUE", REVENUE_CATEGORIES), ("TOTAL", tuple("123456789"))):
        if top not in vals:
            if not (top == "REVENUE" and revenue_optional):
                bad.append(f"no {top} row")
        elif abs(sum(cats.get(k, 0.0) for k in keys) - vals[top]) > max(2.0, 1e-6 * abs(vals[top])) + slack(len(keys)):
            bad.append(f"{top}: {vals[top]:.1f} against {sum(cats.get(k, 0.0) for k in keys):.1f} in categories")
    return bad


def receipts_edition(sheets: dict[str, list[list]], ds: dict) -> tuple[str | None, list[dict], list[str]]:
    wanted = {minfin._sheet_key(n): rows for n, rows in sheets.items() if minfin._sheet_key(n) in RECEIPT_SHEETS}
    period = _edition_period(wanted)
    if period is None:
        return None, [], []
    year, month = period
    d = f"{year}-{month:02d}-01"
    records, notes = [], []
    for key, budget in RECEIPT_SHEETS.items():
        rows = wanted.get(key)
        col = _column(rows, year, month) if rows else None
        off = _code_offset(rows) if rows else None
        if col is None or off is None:
            notes.append(f"{d}: no {budget} sheet, period column or code columns")
            continue
        try:
            lines, bad = receipt_lines(rows, col, off), []
        except ValueError as exc:
            lines, bad = [], [str(exc)]
        cats = sum(v for c, _, v in lines if c in REVENUE_CATEGORIES)
        if any(c == "REVENUE" and v == 0 for c, _, v in lines) and cats > 0:
            # the republican table of January-March 2021 prints «ДОХОДЫ» as 0: the cell is left out, not replaced
            lines = [x for x in lines if x[0] != "REVENUE"]
            lines.insert(1, ("REVENUE_MISSING", "", cats))
            notes.append(f"{d} {budget}: «ДОХОДЫ» is printed as 0 (categories 1-5 give {cats:.1f}); the row is omitted")
        bad = bad or check_receipts([x for x in lines if x[0] != "REVENUE_MISSING"], revenue_optional=any(x[0] == "REVENUE_MISSING" for x in lines))
        lines = [x for x in lines if x[0] != "REVENUE_MISSING"]
        if bad and minfin.BULLETIN_ARCHIVE:
            # Editions of 2015-2018 leave some specifics out of the printed table, so a subclass can exceed the
            # lines under it while every level above adds up. Such an edition is kept as printed and the
            # subclasses concerned are reported; any other break still drops the budget.
            # Not for the PDF editions (before 2013): there a subclass that does not add up is as likely a
            # code read one row off, and the sum is the only guard.
            incomplete = [b for b in bad if re.match(r"\d{4}[: ]", b)]
            if len(incomplete) == len(bad) and d >= OLD_CLASSIFICATION_BEFORE:
                notes.append(f"{d} {budget}: INCOMPLETE specifics, kept as printed -- " + "; ".join(bad[:6]))
                bad = []
        if bad:
            if not minfin.BULLETIN_ARCHIVE:
                _structural(ds, f"{d} {budget}: " + "; ".join(bad[:5]))
            notes += [f"SKIPPED {budget} -- {d}: " + "; ".join(bad[:4])] + _top_rows({key: rows})
            continue
        for code, label, v in lines:
            records.append({"date": d, "region": dims.NATIONAL, "item_code": f"{budget}.{code}",
                            "item_name": f"{BUDGET_NAMES[budget]}: {label}", "value": round(v, 4)})
    return d, records, notes


def fetch_receipts(ds: dict) -> tuple[list[dict], dict]:
    got, warnings = _read_editions(ds, set(RECEIPT_SHEETS), lambda sheets: receipts_edition(sheets, ds))
    return _merge(ds, got), {"frequency": "monthly", "source_url": minfin.LISTING_URL,
                             "dataset_id": "Statistical Bulletin tables 4 and 8", "note": ds.get("note", ""), "warnings": warnings}
