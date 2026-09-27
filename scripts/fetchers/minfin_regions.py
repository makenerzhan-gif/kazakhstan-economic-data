"""Local budgets by region, January-to-month, from Minfin's monthly Statistical Bulletin
(added 2026-09-27, for regional transfers and social spending).

Sheets of every bulletin edition (read through fetchers/minfin, so the archive mode and the
backfill cache of scripts/backfill_minfin_bulletins.py apply):
  * «табл 12» (all local budgets, region = national) and «табл 12.1» … «табл 12.20», one per
    region: 16 regions 2013-2017, 17 from 2018 (Shymkent), 20 from the November 2022 edition.
    The sheet number does not follow a fixed region order, so the region is read from the
    sheet's title («АКМОЛИНСКАЯ ОБЛАСТЬ», «ГОРОД АСТАНА»).
  * «табл 18» («табл 17» before September 2021): general transfers -- the subvention from the
    republican budget to each region and the budget withdrawal (изъятие) from donor regions.
Values: the column whose header names the edition's period («январь-июль отчет 2026» -- the
latest such header of the edition: some sheets print the same months of the previous year
first), in a December edition (annual columns only) the latest «YYYY г. отчет»; in million KZT, dated the first day of the period's last month (the dims convention for
year-to-date flows): 2026-07-01 = January-July 2026.

Items (Russian row labels, the last text cell of a row):
  REV, REV.TAX, REV.CIT, REV.PIT, REV.SOCIAL_TAX, REV.EXCISE, REV.NONTAX, REV.CAPITAL,
  REV.TRANSFERS; EXP and EXP.01 … EXP.15 (functional groups: 04 education, 05 health, 06 social
  assistance, 07 housing and utilities …); NET_LENDING; FIN_ASSETS; BALANCE (deficit − /
  surplus +); SUBVENTIONS and WITHDRAWALS (table 18). Targeted transfers received =
  REV.TRANSFERS − SUBVENTIONS.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import minfin  # noqa: E402
from lib import dims, validation  # noqa: E402

LINES = [  # (code, name, regex on the normalised Russian label)
    ("REV", "Доходы", r"^i\. доходы"),
    ("REV.TAX", "Налоговые поступления", r"^налоговые поступления"),
    ("REV.CIT", "Корпоративный подоходный налог", r"^корпоративный подоходный налог"),
    ("REV.PIT", "Индивидуальный подоходный налог", r"^индивидуальный подоходный налог"),
    ("REV.SOCIAL_TAX", "Социальный налог", r"^социальный налог"),
    ("REV.EXCISE", "Акцизы", r"^акцизы"),
    ("REV.NONTAX", "Неналоговые поступления", r"^неналоговые поступления"),
    ("REV.CAPITAL", "Поступления от продажи основного капитала", r"^поступления от продажи основного капитала"),
    ("REV.TRANSFERS", "Поступления трансфертов", r"^поступлени[ея] трансфертов"),
    ("EXP", "Затраты", r"^ii\. (затраты|расходы)"),
    ("NET_LENDING", "Чистое бюджетное кредитование", r"^iii\. чистое бюджетное кредитование"),
    ("FIN_ASSETS", "Сальдо по операциям с финансовыми активами", r"^iv\. сальдо по операциям с финансовыми"),
    ("BALANCE", "Дефицит (профицит) бюджета", r"^v\. дефицит"),
]
_LINES = [(c, n, re.compile(r)) for c, n, r in LINES]
ABBREVIATIONS = {"вост": "Восточно-", "зап": "Западно-", "сев": "Северо-", "юж": "Южно-"}  # «ВОСТ-КАЗАХСТАНСКАЯ ОБЛАСТЬ»
FUNCTION_RE = re.compile(r"^(\d{1,2})\.\s+(.+)$")


def _norm(text) -> str:
    return " ".join(str(text or "").replace("_x000D_", " ").split()).lower().replace("ё", "е")


def _value(cell) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell or "").strip().replace(" ", "").replace(",", ".")
    if s in ("-", "–", "—"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def _region_name(cell: str) -> str:
    """«ИСПОЛНЕНИЕ БЮДЖЕТА АКМОЛИНСКОЙ ОБЛАСТИ», «ВОСТ-КАЗАХСТАНСКАЯ ОБЛАСТЬ», «ГОРОДА АСТАНЫ» → the
    nominative form dictionaries/regions.csv knows."""
    t = " ".join(cell.split()).lower()
    t = re.sub(r"^исполнение (местного )?бюджета\s*", "", t)
    t = re.sub(r"^(вост|зап|сев|юж)\.?-", lambda m: ABBREVIATIONS[m.group(1)].lower(), t)
    t = re.sub(r"(\w+)ской област[иь]$", r"\1ская", t)
    t = re.sub(r"^област[иь]\s+", "", t)
    t = re.sub(r"^(города|город|г\.)\s*", "г. ", t)
    return t.replace("астаны", "астана").replace("шымкента", "шымкент").replace("нур-султана", "нур-султан")


def _region_of(rows: list[list]) -> tuple[str, str] | None:
    for row in rows[:5]:
        for cell in row or []:
            if isinstance(cell, str) and len(cell) < 80:
                hit = dims.match_region(_region_name(cell))
                if hit:
                    return hit
    return None


def budget_lines(rows: list[list], col: int) -> dict[str, tuple[str, float]]:
    """{item: (name, value)} of a table-12 sheet, values from column `col`."""
    out: dict[str, tuple[str, float]] = {}
    in_expenditure = False
    for r in rows:
        label = minfin._row_label(r)
        norm = _norm(label)
        if not norm or col >= len(r):
            continue
        v = _value(r[col])
        if v is None:
            continue
        hit = next(((c, n) for c, n, rx in _LINES if rx.search(norm)), None)
        if hit:
            in_expenditure = hit[0] == "EXP"
            out.setdefault(hit[0], (hit[1], v))
            continue
        m = FUNCTION_RE.match(" ".join(label.split()))
        if in_expenditure and m and 1 <= int(m.group(1)) <= 15:
            out.setdefault(f"EXP.{int(m.group(1)):02d}", (m.group(2).strip(), v))
    return out


def transfer_lines(rows: list[list], col: int) -> list[tuple[str, str, float]]:
    """(region code or national, SUBVENTIONS | WITHDRAWALS, value) from table 18 (17)."""
    out, block = [], None
    for r in rows:
        norm = _norm(minfin._row_label(r))
        if not norm or col >= len(r) or _value(r[col]) is None:
            continue
        v = _value(r[col])
        if norm.startswith("бюджетные изъятия из местных"):
            block = "WITHDRAWALS"
            out.append((dims.NATIONAL, block, v))
        elif norm.startswith("субвенции из республиканского"):
            block = "SUBVENTIONS"
            out.append((dims.NATIONAL, block, v))
        elif block == "WITHDRAWALS" and "изъяти" in norm:
            name = re.sub(r"^.*?бюджета\s+", "", norm)
            hit = dims.match_region(re.sub(r"^города\s+", "город ", name)) or dims.match_region(
                re.sub(r"(ой|ого) области$", "ая", re.sub(r"^областного бюджета\s+", "", name)))
            if hit:
                out.append((hit[0], block, v))
        elif block == "SUBVENTIONS":
            hit = dims.match_region(norm.replace("г.", "г. ").replace("  ", " "))
            if hit:
                out.append((hit[0], block, v))
            else:
                block = None
    return out


REPORT_YEAR_RE = re.compile(r"(\d{4})\s*г\.?\s*отчет|отчет\s*(\d{4})\s*г")


KZ_YEAR_RE = re.compile(r"(\d{4})\s*ж\.?\s*есеп")


def _header(cell) -> str | None:
    """A header cell with digit groups closed up: the December 2023 edition prints «2\xa0023»."""
    if not isinstance(cell, str):
        return None
    return " ".join(re.sub(r"(?<=\d)[\s\xa0](?=\d{3}\b)", "", cell).split())


AS_OF_JANUARY_RE = re.compile(r"на\s*1\s*январ\w*\s*(\d{4})")


def _period_of(text: str | None) -> tuple[int, int] | None:
    """As minfin._period_of, and «на 1 января 2023 г. отчет» (table 18 of the December 2022
    edition) = January-December 2022, not January 2023."""
    m = AS_OF_JANUARY_RE.search(text.lower()) if text else None
    return (int(m.group(1)) - 1, 12) if m else minfin._period_of(text)


def _period_cols(rows: list[list]) -> list[tuple[int, int, int]]:
    """Every (year, month, column) whose header names a January-to-month report."""
    return [(p[0], p[1], j) for row in rows[:15] for j, cell in enumerate(row or [])
            if (p := _period_of(_header(cell)))]


def _report_cols(rows: list[list]) -> list[tuple[int, int]]:
    """(year, column) of the annual «YYYY ж. есеп / YYYY г. отчет» headers; the Kazakh year
    wins when both are printed (табл 12.3 of the December 2020 edition heads its 2019 and 2020
    columns «2019 ж. есеп/ 2018 г. отчет», «2020 ж. есеп/ 2018 г. отчет»)."""
    out = []
    for row in rows[:15]:
        for j, cell in enumerate(row or []):
            text = _header(cell)
            m = REPORT_YEAR_RE.search(text) if text else None
            if m and not _period_of(text):
                kz = KZ_YEAR_RE.search(text)
                out.append((int(kz.group(1)) if kz else int(m.group(1) or m.group(2)), j))
    return out


def edition_records(sheets: dict[str, list[list]]) -> tuple[str | None, list[dict], list[str]]:
    """One edition: its period is the latest January-to-month header of its sheets (the
    same period a year earlier is printed beside it, and some sheets print it first), or,
    in a December edition that prints annual columns only, December of the latest report
    year. Each sheet is read from the column of exactly that period."""
    wanted = {n: rows for n, rows in sheets.items()
              if minfin._sheet_key(n).startswith("таб12") or minfin._sheet_key(n) in ("таб17", "таб18")}
    periods = [p[:2] for rows in wanted.values() for p in _period_cols(rows)]
    if periods:
        year, month = max(periods)
    else:
        years = [y for rows in wanted.values() for y, _ in _report_cols(rows)]
        if not years:
            return None, [], []
        year, month = max(years), 12

    def column(rows):
        col = next((c for y, m, c in _period_cols(rows) if (y, m) == (year, month)), None)
        if col is None and month == 12:   # December: the year's report column (tables 12.x print no «январь-декабрь»)
            col = min((c for y, c in _report_cols(rows) if y == year), default=None)
        return col
    d = f"{year}-{month:02d}-01"
    records, notes, seen = [], [], set()
    names = {"SUBVENTIONS": "Субвенции из республиканского бюджета", "WITHDRAWALS": "Бюджетные изъятия в республиканский бюджет"}
    for name, rows in wanted.items():
        key = minfin._sheet_key(name)
        col = column(rows)
        if key.startswith("таб12"):
            region = (dims.NATIONAL, "") if key == "таб12" else _region_of(rows)
            if region is None:
                notes.append(f"{name}: region not recognised")
                continue
            if col is None:
                notes.append(f"{name}: no column for {d}")
                continue
            if region[0] in seen:
                raise validation.StructuralChangeError(f"minfin_regions: two sheets for region {region[0]} in the {d} edition ({name})")
            seen.add(region[0])
            for item, (label, v) in budget_lines(rows, col).items():
                records.append({"date": d, "region": region[0], "item_code": item, "item_name": label, "value": v})
        elif col is not None and any("субвенции из республиканского" in _norm(minfin._row_label(r)) for r in rows):
            for region, item, v in transfer_lines(rows, col):
                records.append({"date": d, "region": region, "item_code": item, "item_name": names[item], "value": v})
    return d, records, notes


def fetch(ds: dict) -> tuple[list[dict], dict]:
    docs = minfin._bulletin_documents()
    if not docs:
        raise validation.StructuralChangeError("minfin_regions: no Statistical Bulletin in the listing")
    got: dict[str, list[dict]] = {}
    warnings = []
    for doc in docs:                          # newest first: an edition already read wins
        path = doc["full_text"][0]["document"]
        kind, wb = minfin._open_workbook(minfin._download(path), path)
        names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        wanted = [n for n in names if minfin._sheet_key(n).startswith("таб12") or minfin._sheet_key(n) in ("таб17", "таб18")]
        sheets = {n: list(minfin._iter_rows(kind, wb, n)) for n in wanted}   # edition_records picks the tables
        d, records, notes = edition_records(sheets)
        warnings += [f"{doc.get('id')}: {n}" for n in notes]
        if d and d not in got and records:
            got[d] = records
    stored = [{**r, "value": float(r["value"])} for r in dims.load_processed(ds["id"]) if r["date"] not in got]
    records = [r for recs in got.values() for r in recs] + stored
    # regions must add up to «табл 12» (all local budgets) -- a misread region shows here
    by = {}
    for r in records:
        by.setdefault((r["date"], r["item_code"]), {})[r["region"]] = r["value"]
    for (d, item), vals in sorted(by.items()):
        if item in ("REV", "EXP") and dims.NATIONAL in vals and len(vals) > 15:
            parts = sum(v for k, v in vals.items() if k != dims.NATIONAL)
            if abs(parts - vals[dims.NATIONAL]) > 0.005 * abs(vals[dims.NATIONAL]):
                warnings.append(f"{d} {item}: regions sum to {parts:.0f}, all local budgets {vals[dims.NATIONAL]:.0f}")
    if not records:
        raise validation.StructuralChangeError("minfin_regions: no regional sheet read from any bulletin")
    return sorted(records, key=lambda r: (r["item_code"], r["region"], r["date"])), {
        "frequency": "monthly", "source_url": minfin.LISTING_URL, "dataset_id": "Statistical Bulletin tables 12, 12.x, 18",
        "note": ds.get("note", ""), "warnings": warnings}
