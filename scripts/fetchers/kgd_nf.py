"""Receipts of the National Fund by budget code, from the State Revenue Committee (КГД).

    NF_RECEIPTS_BY_CODE_KGD_YTD   monthly, January to the month, million KZT, 2021 on

Source: gov.kz, project `kgd`, direction 655 «Статистика», «Динамика поступлений в Национальный
фонд … в разрезе КБК» (the API also serves the English title «Dynamics of revenues to the
national fund … by BCC»). One small workbook per edition, sheet «налоги», thousand tenge:

    column A   budget code (101105 corporate income tax of the oil sector, 105322 excess profit
               tax, 105325 bonuses, 105326 mineral extraction tax, 105327 rent tax on export,
               105328 the Republic's share under production sharing, 105329 the subsoil user's
               additional payment; 204201-204203 and 206111 non-tax; 303102 sale of farm land)
    column B   label
    C … N      «January», «January-February», … «January-December»: every edition restates
               every month of its year so far

Why it is here: the Ministry of Finance's National Fund statement (the NF_*_YTD scalar series)
stopped at 1 July 2026; KGD posts this file monthly, two to five weeks after the month. Checked
2026-11-13 on the months both publish: every December of 2021-2025 and June 2026 are equal for
all seven taxes; inside a year the two can differ by the timing of a payment (at most 0.5 % of
the tax total in 2023-2026, 5 % in February 2021), so the two are NOT spliced into one series.

Not in the file: the fund's investment income, the transfers out of it, privatisation proceeds.

A year is taken from the edition that covers the most months (the newest among equals). Years
no listed edition covers keep their stored rows.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import minfin  # noqa: E402
from lib import dims, validation  # noqa: E402

STATISTICS_DIRECTION = "655"
KNOWN_ACTIVITIES = ("87372", "85298", "1533")      # 2026, late 2025, 2021 to mid-2025: a new one appears with each year
TITLE_RE = re.compile(r"(national\s+fund|национальн\w*\s+фонд|ұлттық\s+қор).*(bcc|kbk|cbc|кбк|бсж)", re.IGNORECASE | re.DOTALL)
CODES = {"101105": ("CIT", "Корпоративный подоходный налог с организаций нефтяного сектора"),
         "105322": ("EXCESS_PROFIT_TAX", "Налог на сверхприбыль от организаций нефтяного сектора"),
         "105325": ("BONUSES", "Бонусы от организаций нефтяного сектора"),
         "105326": ("MET", "Налог на добычу полезных ископаемых от организаций нефтяного сектора"),
         "105327": ("RENT_TAX_EXPORT", "Рентный налог на экспорт от организаций нефтяного сектора"),
         "105328": ("PSA_SHARE", "Доля Республики Казахстан по разделу продукции от организаций нефтяного сектора"),
         "105329": ("PSA_ADDITIONAL", "Дополнительный платёж недропользователя по контракту о разделе продукции"),
         "204201": ("FINES_ADMIN", "Административные штрафы, налагаемые на организации нефтяного сектора"),
         "204202": ("FINES_OTHER", "Прочие штрафы, пени, санкции с организаций нефтяного сектора"),
         "204203": ("SUBSOIL_DAMAGES", "Средства, полученные от недропользователей по искам о возмещении вреда"),
         "206111": ("OTHER_NONTAX", "Другие неналоговые поступления от организаций нефтяного сектора"),
         "303102": ("LAND_SALES", "Поступления от продажи земельных участков сельскохозяйственного назначения")}
TAXES = ("CIT", "EXCESS_PROFIT_TAX", "BONUSES", "MET", "RENT_TAX_EXPORT", "PSA_SHARE", "PSA_ADDITIONAL")
TOTALS = (("TAX_TOTAL", "Налоговые поступления в Национальный фонд, всего", r"total\s+tax|итого\s+налог|всего\s+налог"),
          ("TOTAL", "Поступления в Национальный фонд по перечисленным кодам, всего", r"total\s+for|итого|всего"))


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"kgd/{ds['id']}: {what}")


def _number(cell) -> float | None:
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _code(cell) -> str | None:
    text = str(cell).strip() if cell is not None else ""
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return text if re.fullmatch(r"\d{6}", text) else None


def parse_workbook(content: bytes) -> tuple[int, int, dict[str, list[float]]] | None:
    """(year, months covered, {item: twelve year-to-date values in THOUSAND tenge}) or None when the
    workbook is not this table (the regional companion, a different report)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            by_code = {c: r for r in rows if r and (c := _code(r[0])) in CODES}
            if "101105" not in by_code or "105326" not in by_code:
                continue
            head = " ".join(str(c) for r in rows[:3] for c in r if c is not None)
            years = re.findall(r"\b(20\d{2})\b", head)
            if not years:
                return None
            cit = [_number(c) for c in by_code["101105"][2:14]]
            months = max((i + 1 for i, v in enumerate(cit) if v is not None), default=0)
            if not months:
                return None
            out = {CODES[c][0]: [(_number(x) or 0.0) for x in (r[2:14] + [None] * 12)[:12]] for c, r in by_code.items()}
            for item, _, rx in TOTALS:
                row = next((r for r in rows if r and _code(r[0]) is None and len(r) > 1 and r[1] is not None
                            and re.search(rx, str(r[1]), re.IGNORECASE)
                            and not (item == "TOTAL" and re.search(TOTALS[0][2], str(r[1]), re.IGNORECASE))
                            and _number(r[2]) is not None), None)
                if row is not None:
                    out[item] = [(_number(x) or 0.0) for x in (row[2:14] + [None] * 12)[:12]]
            return int(years[-1]), months, out
    finally:
        wb.close()
    return None


def check(year: int, months: int, values: dict[str, list[float]]) -> list[str]:
    """The seven taxes must add up to the printed tax total, and all twelve codes to the grand total."""
    bad = []
    for m in range(months):
        taxes = sum(values.get(t, [0.0] * 12)[m] for t in TAXES)
        everything = sum(v[m] for k, v in values.items() if k not in ("TAX_TOTAL", "TOTAL"))
        for item, parts in (("TAX_TOTAL", taxes), ("TOTAL", everything)):
            if item not in values:
                bad.append(f"{year}: no {item} row")
            elif abs(values[item][m] - parts) > max(1.0, 1e-6 * abs(parts)):
                bad.append(f"{year}-{m + 1:02d} {item}: {values[item][m]:.1f} against {parts:.1f} in its lines")
    return bad


def _documents() -> list[dict]:
    found: dict = {}
    # The API's filters are not documented; the same documents are asked for in the three ways the
    # other gov.kz fetchers use, and whatever answers is merged.
    queries = [{"projects": "eq:kgd", "activities": a} for a in KNOWN_ACTIVITIES]
    queries += [{"directions": STATISTICS_DIRECTION, "activities": a} for a in KNOWN_ACTIVITIES]
    queries += [{"projects": "eq:kgd", "directions": STATISTICS_DIRECTION, "page": str(p)} for p in range(1, 4)]
    queries += [{"projects": "kgd", "title": t} for t in ("Национальный фонд", "national fund")]
    for params in queries:
        try:
            batch = minfin._list_documents(**params)
        except Exception:  # noqa: BLE001  (a listing that fails must not hide the others)
            continue
        for d in batch:
            found.setdefault(d.get("id"), d)
    docs = [d for d in found.values() if TITLE_RE.search(d.get("title") or "") and d.get("full_text")]
    return sorted(docs, key=lambda d: d.get("created_date") or "", reverse=True)


def fetch(ds: dict) -> tuple[list[dict], dict]:
    docs = _documents()
    if not docs:
        _structural(ds, "no «Динамика поступлений в Национальный фонд в разрезе КБК» document in the KGD listing")
    best: dict[int, tuple[int, dict[str, list[float]]]] = {}
    warnings, read = [], 0
    for doc in docs:                                    # newest first: among editions with the same coverage the newest wins
        for attachment in doc["full_text"]:
            path = str(attachment.get("document") or "")
            if not path.lower().endswith(".xlsx"):
                continue
            try:
                parsed = parse_workbook(minfin._download(path))
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{doc.get('id')}: not read ({str(exc)[:80]})")
                continue
            if parsed is None:
                continue
            year, months, values = parsed
            read += 1
            bad = check(year, months, values)
            if bad:
                warnings.append(f"{doc.get('id')}: SKIPPED -- {'; '.join(bad[:3])}")
                continue
            if year not in best or months > best[year][0]:
                best[year] = (months, values)
    if not best:
        _structural(ds, f"none of {len(docs)} documents holds a table that adds up ({read} read)")
    names = {v[0]: v[1] for v in CODES.values()} | {t[0]: t[1] for t in TOTALS}
    records = []
    for year, (months, values) in best.items():
        for item, series in values.items():
            for m in range(months):
                records.append({"date": f"{year}-{m + 1:02d}-01", "region": dims.NATIONAL, "item_code": item,
                                "item_name": names[item], "value": round(series[m] / 1000.0, 4)})
    fresh = {r["date"][:4] for r in records}
    records += [{"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
                 "value": float(r["value"])} for r in dims.load_processed(ds["id"]) if r["date"][:4] not in fresh]
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "monthly", "source_url": "https://www.gov.kz/memleket/entities/kgd/activities/directions?lang=ru",
        "dataset_id": "KGD: Динамика поступлений в Национальный фонд в разрезе КБК", "note": ds.get("note", ""), "warnings": warnings}
