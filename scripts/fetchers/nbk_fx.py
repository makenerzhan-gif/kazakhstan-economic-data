"""Monthly average official KZT rates of the currencies of Kazakhstan's import partners
(added 2026-09-27, for an import-weighted effective exchange rate, fetchers/neer_import.py).

Source: the NBK report behind «Ежедневные официальные (рыночные) курсы валют»
(fetchers/nbk.OFFICIAL_RATES_REPORT_URL), one request PER CURRENCY: when several are asked
together, a currency with no rate on a day is left out of that day's row and the columns
after it shift, so a joint table cannot be read safely. Each row gives the quantity (1, 100
or 1000 units) and the rate; the value stored is KZT per ONE unit, averaged over the
weekdays of the month (weekend rows repeat Friday's rate).

Precision: the report prints two decimals, so a unit worth less than 1 KZT is printed
«0.1» or «0.05» until the NBK switched it to a quote per 100 (UZS; the Belarusian rouble
before its 2016 redenomination). Days whose printed rate is below 1.0 are dropped -- that
currency is simply missing for those months, not a false 50% move.

The Belarusian rouble is restated in post-2016 roubles (redenominate).

Accumulated: the first run loads 2010-01 onward; later runs re-read from the first day of
the previous month and recompute those months only.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import nbk  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

# ISO code: (report currency id, Russian name) -- ids checked against the report's own list.
CURRENCIES = {
    "USD": ("5", "Доллар США"), "EUR": ("6", "Евро"), "CNY": ("8", "Китайский юань"), "RUB": ("16", "Российский рубль"),
    "TRY": ("41", "Турецкая лира"), "KRW": ("25", "Южно-корейская вона"), "UZS": ("20", "Узбекский сум"),
    "KGS": ("10", "Кыргызский сом"), "BYN": ("38", "Белорусский рубль"), "JPY": ("26", "Японская иена"),
    "GBP": ("2", "Фунт стерлингов"), "INR": ("49", "Индийская рупия"), "CHF": ("23", "Швейцарский франк"),
    "CZK": ("43", "Чешская крона"), "PLN": ("39", "Польский злотый"), "AED": ("4", "Дирхам ОАЭ"),
    "TJS": ("44", "Таджикский сомони"), "AZN": ("48", "Азербайджанский манат"),
}
FIRST_DATE = date(2010, 1, 1)


def parse_single(html: str) -> dict[str, float]:
    """{ISO date: KZT per one unit} from a one-currency report (weekdays, printed rate >= 1)."""
    out = {}
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 3 or not re.match(r"^\d{4}-\d{2}-\d{2}$", cells[0]):
            continue
        try:
            quantity, rate = float(cells[1].replace(",", ".")), float(cells[2].replace(",", "."))
        except ValueError:
            continue
        if quantity > 0 and rate >= 1.0 and date.fromisoformat(cells[0]).weekday() < 5:
            out[cells[0]] = rate / quantity
    return out


def redenominate(code: str, daily: dict[str, float]) -> dict[str, float]:
    """The Belarusian rouble was redenominated 10 000 : 1 on 2016-07-01; the report quotes the
    old rouble (BYR) under the same name before that. Earlier rates are restated in BYN."""
    if code != "BYN":
        return daily
    return {d: v * 10000 if d < "2016-07-01" else v for d, v in daily.items()}


def monthly_means(daily: dict[str, float]) -> dict[str, float]:
    by_month: dict[str, list[float]] = defaultdict(list)
    for d, v in daily.items():
        by_month[d[:7] + "-01"].append(v)
    return {m: sum(v) / len(v) for m, v in by_month.items()}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    stored = dims.load_processed(ds["id"])
    today = date.today()
    begin = (today.replace(day=1) - timedelta(days=1)).replace(day=1) if stored else FIRST_DATE
    pages, records, empty = {}, [], []
    for code, (cid, name) in CURRENCIES.items():
        params = [("rates[]", cid), ("beginDate", begin.strftime("%d.%m.%Y")), ("endDate", today.strftime("%d.%m.%Y"))]
        resp = requests.get(nbk.OFFICIAL_RATES_REPORT_URL, headers=nbk.HEADERS, params=params, timeout=180)
        resp.raise_for_status()
        html = resp.content.decode("utf-8", "replace")
        pages[code] = html
        heads = [re.sub(r"\s+", " ", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)]
        if heads and not any(name.split()[0].upper()[:5] in h.upper() for h in heads):
            raise validation.StructuralChangeError(
                f"nbk_fx: currency id {cid} no longer answers {name!r} (headers {heads[:4]}) -- update CURRENCIES")
        months = monthly_means(redenominate(code, parse_single(html)))
        if not months:
            empty.append(code)
        records += [{"date": m, "region": dims.NATIONAL, "item_code": code, "item_name": f"{name}, тенге за 1 единицу (среднее за месяц)",
                     "value": round(v, 6)} for m, v in months.items()]
    if len(empty) > 3:
        raise validation.StructuralChangeError(f"nbk_fx: no rates for {empty} since {begin}")
    buf = gzip.compress(json.dumps(pages, ensure_ascii=False).encode(), mtime=0)
    path = raw_store.save_raw_bytes("nbk", ds["id"], today, "json.gz", buf)
    raw_store.write_download_manifest("nbk", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": nbk.OFFICIAL_RATES_REPORT_URL,
        "begin": begin.isoformat(), "currencies": {c: v[0] for c, v in CURRENCIES.items()}})
    fresh = {(r["item_code"], r["date"]) for r in records}
    records += [{**r, "value": float(r["value"])} for r in stored if (r["item_code"], r["date"]) not in fresh
                and r["date"] < begin.isoformat()]
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "monthly", "source_url": nbk.OFFICIAL_RATES_REPORT_URL, "dataset_id": "official-rates-report/monthly-mean",
        "note": ds.get("note", ""), "warnings": [f"no rates since {begin} for {empty}"] if empty else []}
