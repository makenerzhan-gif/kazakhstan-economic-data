"""Damu Entrepreneurship Development Fund: loans approved for interest-rate subsidy, by region,
programme, ОКЭД section and business size (added 2026-09-27, for the quasi-fiscal block).

Source: damu.kz «Отчеты» (https://damu.kz/ru/reports/reports/), the monthly edition of «Отчет
по проектам субсидирования на DD.MM.YYYY г.xlsx». Its first sheet lists every project since
1 January 2010 (≈120 000 rows): region, ОКЭД section, lender, business size, the loan amount
approved for subsidy, programme, year and -- from 2024 only -- month of approval. The file
name changes with every edition (a new /upload/iblock/<hash>/ path), so the link is read from
the page each time.

Aggregates written (KZT bn; COUNT.* in projects), by approval year (dated YYYY-01-01) or, for
the monthly dataset, approval month from 2024:
    TOTAL, COUNT.TOTAL, PROG.<programme>, SEC.<ОКЭД letter>, SIZE.<size>
Checked on every edition: the region totals equal the file's own summary sheet «ВСЕ
НАПРАВЛЕНИЯ …» (sum over programmes) within 1% -- the summary counts a few projects
under a variant spelling of a new region («область Абай») that the microdata keeps apart,
0.3 bn of 8 900 bn on the 01.09.2026 edition.

The file is a snapshot: a project cancelled later disappears from every later edition, so
past years are revised (the revision log records it). Amounts are loans APPROVED for subsidy,
not disbursements and not the subsidy paid (the budget cost is in Minfin's table 8).
"""
from __future__ import annotations

import io
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

PAGE_URL = "https://damu.kz/ru/reports/reports/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
LINK_RE = re.compile(r'href="([^"]*Отчет по проектам субсидирования на (\d{2})\.(\d{2})\.(\d{4})[^"]*\.xlsx)"')
PROGRAMMES = {"ПС": ("PS", "Портфельное субсидирование"), "ПС 200": ("PS200", "Портфельное субсидирование ПС 200"),
              "ДКБ": ("DKB", "Дорожная карта бизнеса 2020/2025"), "Нацпроект": ("NATPROJECT", "Национальный проект по развитию предпринимательства 2021-2025"),
              "ПСЭ": ("PSE", "Пострадавшие сектора экономики (2020-2021)"), "ЕКП МСП": ("EKP_MSP", "Единая комплексная программа, МСП"),
              "ЕКП МСКП": ("EKP_MSKP", "Единая комплексная программа, МСКП"), "ЭПВ": ("EPV", "Экономика простых вещей"),
              "Іскер аймақ": ("ISKER", "Единая программа поддержки малого бизнеса «Іскер аймақ»")}
SIZES = {"микро": "MICRO", "малый": "SMALL", "средний": "MEDIUM", "крупный": "LARGE"}
MONTHS = {m: i for i, m in enumerate(["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
                                      "сентябрь", "октябрь", "ноябрь", "декабрь"], 1)}
# The section is the first letter of «C-Обрабатывающая промышленность»; T is typed in Cyrillic once.
CYRILLIC_LOOKALIKES = str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX")
COLUMNS = {"region": "Регион", "section": "Секция.Наименование", "size": "Заемщик.Размер бизнеса субъекта",
           "amount": "Сумма кредита, одобренная к субсидированию", "programme": "Программа", "year": "Год", "month": "Месяц"}
_CACHE: dict[str, tuple[bytes, str, str]] = {}


def _latest_link(html: str) -> tuple[str, str]:
    links = sorted(((y, m, d), url) for url, d, m, y in LINK_RE.findall(html))
    if not links:
        raise validation.StructuralChangeError(
            f"STRUCTURAL CHANGE DETECTED in damu/subsidised loans\nWHAT CHANGED: no «Отчет по проектам субсидирования "
            f"на DD.MM.YYYY» xlsx link on {PAGE_URL}")
    (y, m, d), url = links[-1]
    return urljoin(PAGE_URL, quote(url, safe="/:%")), f"{y}-{m}-{d}"


def download() -> tuple[bytes, str, str]:
    if "file" not in _CACHE:
        page = requests.get(PAGE_URL, headers=HEADERS, timeout=60)
        page.raise_for_status()
        url, as_of = _latest_link(page.text)
        resp = requests.get(url, headers=HEADERS, timeout=300)
        resp.raise_for_status()
        _CACHE["file"] = (resp.content, url, as_of)
    return _CACHE["file"]


def _region(label: str) -> tuple[str, str]:
    hit = dims.match_region(str(label).replace("*", ""))
    if hit is None:
        raise validation.StructuralChangeError(f"damu: region {label!r} not in dictionaries/regions.csv")
    return hit


def parse(content: bytes) -> tuple[list[dict], dict[str, float]]:
    """Project rows as dicts (region code, year, month or None, programme, section, size, amount)
    and the summary sheet's total per region (KZT)."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows = wb.worksheets[0].iter_rows(values_only=True)
    col = None
    for row in rows:
        cells = [" ".join(str(c or "").split()) for c in row]
        if "Регион" in cells:
            missing = [v for v in COLUMNS.values() if v not in cells]
            if missing:
                raise validation.StructuralChangeError(f"damu: columns {missing} missing from the project sheet")
            col = {k: cells.index(v) for k, v in COLUMNS.items()}
            break
    if col is None:
        raise validation.StructuralChangeError("damu: no header row with «Регион» on the first sheet")
    projects, unknown = [], set()
    for row in rows:
        if not row or row[col["region"]] in (None, "") or not isinstance(row[col["amount"]], (int, float)):
            continue
        prog = PROGRAMMES.get(" ".join(str(row[col["programme"]] or "").split()))
        size = SIZES.get(str(row[col["size"]] or "").strip().lower())
        section = str(row[col["section"]] or "").strip()[:1].upper().translate(CYRILLIC_LOOKALIKES)
        month = row[col["month"]]
        month = MONTHS.get(str(month).strip().lower()) if month not in (None, "") else None
        if prog is None or size is None or not ("A" <= section <= "U"):
            unknown.add((row[col["programme"]], row[col["size"]], row[col["section"]]))
            continue
        projects.append({"region": _region(row[col["region"]])[0], "year": int(row[col["year"]]), "month": month,
                         "programme": prog[0], "section": section, "size": size, "amount": float(row[col["amount"]])})
    if unknown:
        raise validation.StructuralChangeError(f"damu: unknown programme/size/section values {sorted(map(str, unknown))[:5]}")
    summary: dict[str, float] = defaultdict(float)
    for row in wb.worksheets[1].iter_rows(values_only=True):
        label = row[11] if len(row) > 11 else None
        if label and dims.match_region(str(label).replace("*", "")):
            summary[_region(label)[0]] += sum(v for v in row[12:18] if isinstance(v, (int, float)))
        elif label and "итог" in str(label).lower() and summary:
            break
    return projects, dict(summary)


def aggregate(projects: list[dict], monthly: bool) -> list[dict]:
    sums: dict[tuple[str, str, str], float] = defaultdict(float)
    names = {"TOTAL": "Сумма кредитов, одобренных к субсидированию, всего, млрд тенге",
             "COUNT.TOTAL": "Количество проектов, одобренных к субсидированию"}
    names.update({f"PROG.{c}": f"{n}, млрд тенге" for c, n in PROGRAMMES.values()})
    names.update({f"SIZE.{c}": f"Размер бизнеса: {s}, млрд тенге" for s, c in SIZES.items()})
    for p in projects:
        if monthly and p["month"] is None:
            continue
        d = f"{p['year']}-{p['month']:02d}-01" if monthly else f"{p['year']}-01-01"
        bn = p["amount"] / 1e9
        for region in (p["region"], dims.NATIONAL):
            for item in ("TOTAL", f"PROG.{p['programme']}", f"SIZE.{p['size']}") + (() if monthly else (f"SEC.{p['section']}",)):
                sums[(d, region, item)] += bn
            sums[(d, region, "COUNT.TOTAL")] += 1
    return [{"date": d, "region": region, "item_code": item,
             "item_name": names.get(item, f"Секция ОКЭД {item[4:]}, млрд тенге"), "value": round(v, 6)}
            for (d, region, item), v in sorted(sums.items(), key=lambda kv: (kv[0][2], kv[0][1], kv[0][0]))]


def fetch(ds: dict) -> tuple[list[dict], dict]:
    fresh = imf_dims.stored_if_fresh(ds, "damu", ds["id"])
    if fresh:
        return fresh
    content, url, as_of = download()
    today = date.today()
    path = raw_store.save_raw_bytes("damu", "SUBSIDISED_LOANS", today, "xlsx", content)
    raw_store.write_download_manifest("damu", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": url, "edition_as_of": as_of})
    projects, summary = parse(content)
    by_region: dict[str, float] = defaultdict(float)
    for p in projects:
        by_region[p["region"]] += p["amount"]
    for region, total in summary.items():
        if abs(by_region.get(region, 0.0) - total) > 0.01 * max(total, 1.0):
            raise validation.StructuralChangeError(
                f"damu: {region} projects sum to {by_region.get(region, 0) / 1e9:.2f} bn, the summary sheet says {total / 1e9:.2f} bn")
    if len(summary) < 17:
        raise validation.StructuralChangeError(f"damu: summary sheet gave only {len(summary)} regions")
    records = aggregate(projects, monthly=ds["frequency"] == "monthly")
    return records, {"frequency": ds["frequency"], "source_url": url, "dataset_id": f"damu subsidy report as of {as_of}",
                     "note": ds.get("note", "") + f" Edition as of {as_of}: {len(projects)} projects."}
