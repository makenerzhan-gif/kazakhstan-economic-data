"""World series kept as item-level datasets (added 2026-11-09): the FAO Food Price Index and the
UN World Population Prospects for Kazakhstan.

FAO_FOOD_PRICE_INDEX  https://www.fao.org/worldfoodsituation/foodpricesindex/en/ -- the nominal
    CSV (food_price_indices_data.csv: three header rows, a blank row, then «YYYY-MM,FFPI,Meat,
    Dairy,Cereals,Oils,Sugar» with padding columns), 2014-2016 = 100, monthly from 1990-01, the
    first Friday of the month; the last two or three months are revised.
UN_WPP_POPULATION  https://population.un.org/wpp/ (2024 revision), the bulk CSV files:
    TotalPopulationBySex (every variant, 1950-2100), PopulationByAge5GroupSex_Medium (summed into
    0-14, 15-64, 65+), Demographic_Indicators_Medium (births, deaths, fertility, life expectancy,
    net migration). Thousands of persons at 1 July; estimates to 2023, projections from 2024.
    The files are 17-30 MB each and change once a year, so the download is refreshed every
    `refresh_days` (default 30) and the Kazakhstan rows are archived.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
FAO_CSV = "https://www.fao.org/media/docs/worldfoodsituationlibraries/wfs-library/food_price_indices_data.csv"
FAO_ITEMS = {"Food Price Index": ("FFPI", "Индекс продовольственных цен ФАО"), "Meat": ("MEAT", "Мясо"), "Dairy": ("DAIRY", "Молочная продукция"),
             "Cereals": ("CEREALS", "Зерновые"), "Oils": ("OILS", "Растительные масла"), "Sugar": ("SUGAR", "Сахар")}
WPP_BASE = "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/"
WPP_FILES = {"total": "WPP2024_TotalPopulationBySex.csv.gz", "age": "WPP2024_PopulationByAge5GroupSex_Medium.csv.gz",
             "indicators": "WPP2024_Demographic_Indicators_Medium.csv.gz"}
WPP_LOCID = "398"
WPP_INDICATORS = {  # column: (code, Russian name)
    "TPopulation1Jan": ("POP_1JAN", "Население на 1 января, тыс. человек"),
    "Births": ("BIRTHS", "Число родившихся, тыс."), "Deaths": ("DEATHS", "Число умерших, тыс."),
    "TFR": ("TFR", "Суммарный коэффициент рождаемости"), "LEx": ("LIFE_EXPECTANCY", "Ожидаемая продолжительность жизни при рождении, лет"),
    "NetMigrations": ("NET_MIGRATION", "Сальдо миграции, тыс."), "MedianAgePop": ("MEDIAN_AGE", "Медианный возраст, лет"),
    "PopGrowthRate": ("GROWTH_RATE", "Темп прироста населения, %"), "IMR": ("INFANT_MORTALITY", "Младенческая смертность на 1000 родившихся")}
AGE_BANDS = (("AGE_0_14", 0, 14, "0-14 лет"), ("AGE_15_64", 15, 64, "15-64 года"), ("AGE_65", 65, 200, "65 лет и старше"))


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"{ds['agency']}/{ds['id']}: {what}")


def _get(url: str) -> bytes:
    last = None
    for _ in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=300)
            resp.raise_for_status()
            return resp.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
    raise last  # type: ignore[misc]


def _archive(agency: str, name: str, ext: str, content: bytes, url: str) -> None:
    today = date.today()
    path = raw_store.save_raw_bytes(agency, name, today, ext, content)
    raw_store.write_download_manifest(agency, name, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name if path else None, "source_url": url})


# ---------------------------------------------------------------- FAO

def fao_records(content: bytes, ds: dict) -> list[dict]:
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    head = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Date"), None)
    if head is None:
        _structural(ds, "no «Date» header row in the FAO csv")
    cols = {}
    for j, c in enumerate(rows[head]):
        if c.strip() in FAO_ITEMS:
            cols[j] = FAO_ITEMS[c.strip()]
    if len(cols) != 6:
        _structural(ds, f"header has {len(cols)} of the six indices: {rows[head][:8]}")
    out = []
    for r in rows[head + 1:]:
        if not r or not re.fullmatch(r"\d{4}-\d{2}", r[0].strip()):
            continue
        for j, (code, name) in cols.items():
            try:
                v = float(r[j])
            except (ValueError, IndexError):
                continue
            out.append({"date": f"{r[0].strip()}-01", "region": "world", "item_code": code, "item_name": name, "value": v})
    return out


def fetch_fao(ds: dict) -> tuple[list[dict], dict]:
    content = _get(FAO_CSV)
    _archive("fao", ds["id"], "csv", content, FAO_CSV)
    records = fao_records(content, ds)
    if len(records) < 2000 or max(r["date"] for r in records) < "2026-01-01":
        _structural(ds, f"{len(records)} values, latest {max((r['date'] for r in records), default='none')}")
    return records, {"frequency": "monthly", "source_url": FAO_CSV, "dataset_id": "FAO FFPI nominal csv", "note": ds.get("note", "")}


# ---------------------------------------------------------------- UN WPP

def _kaz_rows(content: bytes) -> list[dict]:
    with gzip.open(io.BytesIO(content), "rt", encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("LocID") == WPP_LOCID]


def wpp_records(total: list[dict], age: list[dict], indicators: list[dict], ds: dict) -> list[dict]:
    out = []
    variants = set()
    for r in total:
        var = re.sub(r"[^A-Za-z0-9]+", "_", r["Variant"]).strip("_").upper()
        variants.add(var)
        d = f"{int(float(r['Time']))}-12-31"
        out.append({"date": d, "region": "national", "item_code": f"TOTAL.{var}", "item_name": f"Население на 1 июля, тыс. человек (вариант {r['Variant']})",
                    "value": float(r["PopTotal"])})
        if var == "MEDIUM":
            out.append({"date": d, "region": "national", "item_code": "MALE", "item_name": "Мужчины на 1 июля, тыс. (средний вариант)", "value": float(r["PopMale"])})
            out.append({"date": d, "region": "national", "item_code": "FEMALE", "item_name": "Женщины на 1 июля, тыс. (средний вариант)", "value": float(r["PopFemale"])})
    if "MEDIUM" not in variants or "HIGH" not in variants or "LOW" not in variants:
        _structural(ds, f"variants {sorted(variants)}: MEDIUM, HIGH and LOW expected")
    bands: dict[tuple[str, str], float] = defaultdict(float)
    for r in age:
        start = int(r["AgeGrpStart"])
        for code, lo, hi, _ in AGE_BANDS:
            if lo <= start <= hi:
                bands[(code, f"{int(float(r['Time']))}-12-31")] += float(r["PopTotal"])
    names = {c: n for c, _, _, n in AGE_BANDS}
    out += [{"date": d, "region": "national", "item_code": c, "item_name": f"Население {names[c]} на 1 июля, тыс. (средний вариант)", "value": round(v, 3)}
            for (c, d), v in bands.items()]
    for r in indicators:
        d = f"{int(float(r['Time']))}-12-31"
        for col, (code, name) in WPP_INDICATORS.items():
            if r.get(col) not in (None, ""):
                out.append({"date": d, "region": "national", "item_code": code, "item_name": f"{name} (средний вариант)", "value": float(r[col])})
    return out


def fetch_wpp(ds: dict) -> tuple[list[dict], dict]:
    fresh = imf_dims.stored_if_fresh(ds, "un", ds["id"])
    if fresh:
        return fresh
    parts = {}
    for key, fname in WPP_FILES.items():
        url = WPP_BASE + fname
        rows = _kaz_rows(_get(url))
        if not rows:
            _structural(ds, f"no Kazakhstan (LocID {WPP_LOCID}) rows in {fname}")
        parts[key] = rows
    buf = io.StringIO()
    for key, rows in parts.items():
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        buf.write(f"# {WPP_FILES[key]}\n")
        w.writeheader()
        w.writerows(rows)
    _archive("un", ds["id"], "csv", buf.getvalue().encode(), WPP_BASE)
    records = wpp_records(parts["total"], parts["age"], parts["indicators"], ds)
    return records, {"frequency": "annual", "source_url": WPP_BASE, "dataset_id": "WPP2024 bulk csv, LocID 398", "note": ds.get("note", "")}
