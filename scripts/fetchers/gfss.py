"""State Social Insurance Fund (ГФСС): social contributions and insured participants by region,
monthly (added 2026-09-27, a monthly wage-bill and formal-employment proxy).

Source: https://gfss.kz/ru/indicators-rus/financial-statements-rus/ lists the fund's reports as
/documents/<id>/<name>.xls[x]. Form «5-СО» («Сведения о суммах социальных отчислений и пени,
поступивших в АО "ГФСС", и числе участников системы обязательного социального страхования»)
has been published for every month since January 2016 -- under names that changed over time
(«6january2016.xls» to April 2020, «5may2020.xls», «5-со_-_Июнь_2022г.xls» …) and next to
quarterly, half-year and annual editions of the same form and to forms 6-СВ / 7-СР. A file is
therefore recognised by its content: the Russian sheet's title must name social contributions
and a single month («… за август 2026 года»); the month is read from the title.

Items, by region (the oblasts and three cities, dictionaries/regions.csv) and national (the
«Итого» row):
    CONTRIBUTIONS   social contributions received in the month, million KZT
    PENALTIES       penalties (пеня) received, million KZT
    PARTICIPANTS    participants for whom contributions were paid in the month, thousand persons
«Регион не определен» (contributions not attributed to a region) is kept at national level
as CONTRIBUTIONS_UNALLOCATED / PARTICIPANTS_UNALLOCATED; the regions plus it add up to the
«Итого» row (checked).

Reading contributions / participants as a wage proxy: the rate was 3.5% of income (between 1
and 7 minimum wages) to 2024 and 5% from 2025 (Social Code), so the level breaks in 2025-01;
growth rates within a rate regime are the usable signal.
"""
from __future__ import annotations

import io
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote, urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

PAGE_URL = "https://gfss.kz/ru/indicators-rus/financial-statements-rus/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
MONTHS_RU = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
MONTHS_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
NOT_MONTHLY = re.compile(r"кв\.|квартал|полугод|мес\.|year|годовой|^5-со_-_\d{4}")
UNALLOCATED = re.compile(r"не определен|анықталмаған|indefinite", re.I)


def _month_of(text: str) -> tuple[int, int] | None:
    s = text.lower()
    m = re.search(r"(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йя]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)\D{0,3}(\d{4})", s)
    if m:
        word = m.group(1)
        month = next(i for i, p in enumerate(MONTHS_RU, 1) if word.startswith(p))
        return int(m.group(2)), month
    m = re.search(r"(" + "|".join(MONTHS_EN) + r")(\d{4})", s)
    if m:
        return int(m.group(2)), MONTHS_EN.index(m.group(1)) + 1
    return None


def candidates(html: str) -> list[tuple[str, tuple[int, int] | None]]:
    """(url, (year, month) from the file name) of every file that may be a monthly 5-СО."""
    out = []
    for link in dict.fromkeys(re.findall(r'href="(/documents/\d+/[^"]+\.xlsx?)"', html)):
        name = unquote(link.rsplit("/", 1)[1]).lower()
        if name.startswith(("6-св", "7-ср", "7", "8")) or NOT_MONTHLY.search(name):
            continue
        if not (name.startswith(("5-со", "5-co", "5", "6")) and _month_of(name)):
            continue
        out.append((urljoin(PAGE_URL, link), _month_of(name)))
    return out


def _rows(content: bytes) -> list[list]:
    """Rows of the Russian 5-СО sheet (xls or xlsx), [] if the file is another form."""
    if content[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets = [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    else:
        import xlrd
        wb = xlrd.open_workbook(file_contents=content)
        sheets = [(sh.name, [sh.row_values(i) for i in range(sh.nrows)]) for sh in wb.sheets()]
    for name, rows in sheets:
        n = name.lower()
        if "со" in n and ("рус" in n or len(sheets) == 1):
            return rows
    return []


def parse(content: bytes) -> tuple[str, list[dict]] | None:
    rows = _rows(content)
    title = " ".join(str(c) for r in rows[:5] for c in r if c)
    if "социальных отчислений" not in title.lower():
        return None
    when = re.search(r"\b(?:за|в)\s+(\w+)\s+(\d{4})", title.lower())   # «за август 2026», «в июне 2021 года»
    ym = _month_of(f"{when.group(1)} {when.group(2)}") if when else None
    if ym is None:           # a quarter, half-year or annual edition
        return None
    d = f"{ym[0]}-{ym[1]:02d}-01"
    out, regions, total = [], {}, None
    for r in rows:
        cells = [c for c in r if c not in ("", None)]
        if len(cells) < 4 or not isinstance(cells[0], str):
            continue
        nums = [c for c in cells[1:] if isinstance(c, (int, float))]
        if len(nums) < 3:
            continue
        contrib, penalty, people = nums[-3], nums[-2], nums[-1]   # the 2016 English sheet adds a KATO code first
        label = " ".join(cells[0].split())
        if label.lower().startswith(("итого", "барлығы", "total")):
            total = (contrib, penalty, people)
            continue
        if UNALLOCATED.search(label):
            region = "UNALLOCATED"
        else:
            hit = dims.match_region(label)
            if hit is None:
                raise validation.StructuralChangeError(f"gfss 5-СО {d}: region {label!r} not in dictionaries/regions.csv")
            region = hit[0]
        regions[region] = (contrib, penalty, people)
    if total is None or len(regions) < 15:
        raise validation.StructuralChangeError(f"gfss 5-СО {d}: no «Итого» row or only {len(regions)} regions")
    for i, what in enumerate(("contributions", "penalties", "participants")):
        s = sum(v[i] for v in regions.values())
        if abs(s - total[i]) > 1e-3 * max(abs(total[i]), 1):
            raise validation.StructuralChangeError(f"gfss 5-СО {d}: regions sum to {s} {what}, «Итого» is {total[i]}")
    names = {"CONTRIBUTIONS": "Социальные отчисления, поступившие в ГФСС, млн тенге",
             "PENALTIES": "Пеня по социальным отчислениям, млн тенге",
             "PARTICIPANTS": "Участники, за которых поступили социальные отчисления, тыс. человек"}
    for region, (c, p, n) in list(regions.items()) + [("national", total)]:
        vals = {"CONTRIBUTIONS": c / 1000, "PENALTIES": p / 1000, "PARTICIPANTS": n}
        for item, v in vals.items():
            if region == "UNALLOCATED":
                if item != "PENALTIES":
                    out.append({"date": d, "region": dims.NATIONAL, "item_code": f"{item}_UNALLOCATED",
                                "item_name": names[item] + " (регион не определён)", "value": round(v, 6)})
                continue
            out.append({"date": d, "region": region, "item_code": item, "item_name": names[item], "value": round(v, 6)})
    return d, out


def fetch(ds: dict) -> tuple[list[dict], dict]:
    fresh = imf_dims.stored_if_fresh(ds, "gfss", ds["id"])
    if fresh:
        return fresh
    page = requests.get(PAGE_URL, headers=HEADERS, timeout=60)
    page.raise_for_status()
    stored = dims.load_processed(ds["id"])
    have = {r["date"] for r in stored}
    final = sorted(have)[-3] if len(have) >= 3 else ""   # older months than the last three are not re-read
    today = date.today()
    got: dict[str, list[dict]] = {}
    for url, ym in candidates(page.text):
        # months already stored and more than two months older than the latest are final
        if ym and f"{ym[0]}-{ym[1]:02d}-01" in have and f"{ym[0]}-{ym[1]:02d}-01" < final:
            continue
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=120)
                resp.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(3)
        try:
            parsed = parse(resp.content)
        except validation.StructuralChangeError:
            raise
        except Exception:   # not a spreadsheet of this form
            parsed = None
        if parsed is None:
            continue
        d, records = parsed
        raw_store.save_raw_bytes("gfss", f"5so_{d[:7]}", today, url.rsplit(".", 1)[1], resp.content)
        got[d] = records
    if not got and not stored:
        raise validation.StructuralChangeError(f"gfss: no monthly 5-СО file recognised on {PAGE_URL}")
    raw_store.write_download_manifest("gfss", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": PAGE_URL, "months_read": sorted(got)})
    records = [r for recs in got.values() for r in recs]
    records += [{**r, "value": float(r["value"])} for r in stored if r["date"] not in got]
    months = sorted({r["date"] for r in records})
    expected = {f"{y}-{m:02d}-01" for y in range(2016, today.year + 1) for m in range(1, 13)
                if f"{y}-{m:02d}-01" <= months[-1]}
    missing = sorted(expected - set(months))
    return sorted(records, key=lambda r: (r["item_code"], r["region"], r["date"])), {
        "frequency": "monthly", "source_url": PAGE_URL, "dataset_id": "ГФСС форма 5-СО", "note": ds.get("note", ""),
        "warnings": [f"months without a monthly 5-СО file: {missing}"] if missing else []}
