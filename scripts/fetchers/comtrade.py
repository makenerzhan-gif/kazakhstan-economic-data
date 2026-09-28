"""Kazakhstan's imports by partner country from UN Comtrade, annual (added 2026-09-27, the
weights of fetchers/neer_import.py).

Source: the keyless public preview of the Comtrade API,
    https://comtradeapi.un.org/public/v1/preview/C/A/B4?reporterCode=398&period=YYYY
        &flowCode=M&cmdCode=<BEC>&customsCode=C00&motCode=0&partner2Code=0
(reporter Kazakhstan, imports, all partners in one answer; the preview caps an answer at 500
rows, far above the ~130 partners). Classification B4 = BEC rev.4 as converted by UN Stats
from the HS declarations. Baskets (config `baskets`):
    CONSUMER  BEC 112 + 122 (food and beverages for household consumption), 522 (non-industrial
              transport equipment), 61, 62, 63 (durable, semi-durable, non-durable consumer goods)
    TOTAL     cmdCode TOTAL in classification H* (all goods), for comparison.
Item = <BASKET>.<M49 partner code>, value = CIF imports in million USD; <BASKET>.0 = World.
The partner rows of a basket must sum to its World row within 1% (enforced), otherwise the
answer was cut off.

Known weaknesses (as the source says, not corrected here): customs statistics of
Kazakhstan record imports from EAEU partners by statistical survey, not declarations; China
is under-recorded against China's own exports to Kazakhstan; 2020-2022 carry large
partner-attribution changes (re-exports via the EAEU after 2022).
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

URL = "https://comtradeapi.un.org/public/v1/preview/C/A/{clf}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
BASKETS = {"CONSUMER": ("B4", ["112", "122", "522", "61", "62", "63"]), "TOTAL": ("HS", ["TOTAL"])}
PARTNER_NAMES = {  # M49 code: name in the genitive, for item names (others read «страна M49 …»)
    643: "России", 156: "Китая", 792: "Турции", 276: "Германии", 380: "Италии", 860: "Узбекистана", 251: "Франции",
    842: "США", 112: "Беларуси", 616: "Польши", 724: "Испании", 699: "Индии", 804: "Украины", 757: "Швейцарии",
    704: "Вьетнама", 372: "Ирландии", 410: "Республики Корея", 50: "Бангладеш", 218: "Эквадора", 364: "Ирана",
    826: "Великобритании", 360: "Индонезии", 417: "Кыргызстана", 579: "Норвегии", 528: "Нидерландов", 642: "Румынии",
    705: "Словении", 348: "Венгрии", 56: "Бельгии", 268: "Грузии", 752: "Швеции", 458: "Малайзии", 203: "Чехии",
    795: "Туркменистана", 40: "Австрии", 762: "Таджикистана", 208: "Дании", 404: "Кении", 100: "Болгарии",
    586: "Пакистана", 392: "Японии", 784: "ОАЭ", 31: "Азербайджана", 764: "Таиланда", 76: "Бразилии",
    246: "Финляндии", 620: "Португалии", 300: "Греции", 703: "Словакии", 440: "Литвы", 428: "Латвии", 233: "Эстонии",
    191: "Хорватии", 51: "Армении", 498: "Молдовы", 344: "Гонконга", 490: "прочей Азии (Тайвань)"}
BASKET_NAMES = {"CONSUMER": "Импорт потребительских товаров (BEC 112, 122, 522, 61, 62, 63)", "TOTAL": "Импорт товаров, всего"}


def _get(clf: str, year: int, cmd: str) -> dict:
    params = {"reporterCode": "398", "period": str(year), "flowCode": "M", "cmdCode": cmd,
              "customsCode": "C00", "motCode": "0", "partner2Code": "0"}
    for attempt in range(5):
        try:
            resp = requests.get(URL.format(clf=clf), params=params, headers=HEADERS, timeout=120)
            if resp.status_code == 429:
                raise requests.RequestException("rate limited")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError


def basket_values(answers: list[dict]) -> dict[int, float]:
    """{partner code: USD} summed over the basket's codes; 0 = World."""
    out: dict[int, float] = defaultdict(float)
    for a in answers:
        for r in a.get("data") or []:
            if r.get("flowCode") == "M" and r.get("partner2Code") in (0, None):
                out[int(r["partnerCode"])] += float(r.get("primaryValue") or 0)
    return dict(out)


def fetch(ds: dict) -> tuple[list[dict], dict]:
    names = PARTNER_NAMES
    stored = dims.load_processed(ds["id"])
    have_years = {r["date"][:4] for r in stored}
    last_year = date.today().year - 1
    # Years before the stored ones (first_year moved back: 2010 -> 1995 on 2026-09-28) are read even
    # inside the refresh window, and only they: the refresh of recent years keeps its own schedule.
    backfill = [y for y in range(ds.get("first_year", 2010), last_year - 2) if str(y) not in have_years]
    fresh = imf_dims.stored_if_fresh(ds, "comtrade", ds["id"])
    if fresh and not backfill:
        return fresh
    # Past years are revised for about two years after first release; older years are kept.
    years = backfill if fresh else [y for y in range(ds.get("first_year", 2010), last_year + 1)
                                    if str(y) not in have_years or y >= last_year - 2]
    raw, records, warnings = {}, [], []
    for year in years:
        for basket, (clf, cmds) in BASKETS.items():
            answers = []
            for cmd in cmds:
                answers.append(_get(clf, year, cmd))
                time.sleep(1.0)
            raw[f"{year}_{basket}"] = answers
            values = basket_values(answers)
            if not values.get(0):
                if year >= last_year:
                    warnings.append(f"{year} {basket}: not reported yet")
                    continue
                raise validation.StructuralChangeError(f"comtrade: no World row for {basket} {year}")
            parts = sum(v for p, v in values.items() if p != 0)
            if abs(parts - values[0]) > 0.01 * values[0]:
                raise validation.StructuralChangeError(
                    f"comtrade: {basket} {year} partners sum to {parts / 1e6:.0f}, World is {values[0] / 1e6:.0f} mln USD")
            for p, v in values.items():
                records.append({"date": f"{year}-12-31", "region": dims.NATIONAL, "item_code": f"{basket}.{p}",
                                "item_name": f"{BASKET_NAMES[basket]} из {names.get(p, 'страна M49 ' + str(p)) if p else 'всех стран'}, млн долл. США",
                                "value": round(v / 1e6, 6)})
    today = date.today()
    if raw:
        path = raw_store.save_raw_bytes("comtrade", ds["id"], today, "json.gz", gzip.compress(json.dumps(raw).encode(), mtime=0))
        raw_store.write_download_manifest("comtrade", ds["id"], today, {
            "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": URL.format(clf="<B4|HS>"),
            "years": years})
    fetched = {r["date"] for r in records}
    records += [{**r, "value": float(r["value"])} for r in stored if r["date"] not in fetched]
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "annual", "source_url": URL.format(clf="B4"), "dataset_id": "comtrade-preview reporter 398 imports",
        "note": ds.get("note", ""), "warnings": warnings}
