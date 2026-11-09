"""KASE market indices and the corporate bond market (added 2026-11-09).

KASE_INDICES  the TradingView feed that fetchers/kase.py reads for TONIA, one symbol per index:
    INDEX_KASE (the equity index, 2000-07-12 = 100), KASE_TR (total return), KASE_BMY (corporate
    bond yield index, % p.a., from 2017-09) and KASE_BMC (its price index), MM_INDEX (money
    market), CAPBILLS_KZT (capitalisation of government securities, bn KZT, from 2016-10). Daily
    closes kept monthly: <SYMBOL>.AVG (mean of trading days) and <SYMBOL>.EOM (last trading day).
KASE_CORPORATE_BOND_VOLUMES  the monthly news item «объем торгов корпоративными облигациями на
    KASE составил …» (the news API), whose body carries a fixed-width table of primary and
    secondary market volumes, bn KZT, repo excluded; the January item holds the twelve months
    of the previous year.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import kase  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

NEWS_URL = "https://kase.kz/api/news"
SYMBOLS = {  # symbol: (first date expected, Russian name)
    "INDEX_KASE": ("2000-07-12", "Индекс KASE"), "KASE_TR": ("2024-12-31", "Индекс KASE полной доходности (KASE_TR)"),   # the feed carries no closes before 2024-12-31
    "KASE_BMY": ("2017-09-04", "Индекс доходности корпоративных облигаций KASE_BMY, % годовых"),
    "KASE_BMC": ("2017-09-04", "Ценовой индекс корпоративных облигаций KASE_BMC"),
    "MM_INDEX": ("2010-01-05", "Индикатор денежного рынка MM_INDEX, % годовых"),
    "CAPBILLS_KZT": ("2016-10-04", "Капитализация рынка ГЦБ, млрд тенге"),
}
MONTHS = {"январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6, "июль": 7, "август": 8,
          "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12}


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"kase/{ds['id']}: {what}")


def monthly_from_daily(daily: list[dict], symbol: str, name: str) -> list[dict]:
    by: dict[str, list[float]] = defaultdict(list)
    for r in daily:
        by[r["date"][:7] + "-01"].append(r["value"])
    out = []
    for m, vals in by.items():
        out.append({"date": m, "region": "national", "item_code": f"{symbol}.AVG", "item_name": f"{name}, в среднем за месяц", "value": round(sum(vals) / len(vals), 4)})
        out.append({"date": m, "region": "national", "item_code": f"{symbol}.EOM", "item_name": f"{name}, на конец месяца", "value": round(vals[-1], 4)})
    return out


def fetch_indices(ds: dict) -> tuple[list[dict], dict]:
    to = int(datetime.now(tz=timezone.utc).timestamp()) + 86400
    records, raw = [], {}
    for symbol in SYMBOLS:
        raw[symbol] = json.loads(kase._get(kase.TV_HISTORY_URL, {"symbol": symbol, "resolution": "D", "from": 0, "to": to}))
    kase._save_raw(ds["id"], json.dumps(raw, sort_keys=True).encode(), "json", {"source_url": kase.TV_HISTORY_URL, "symbols": list(SYMBOLS)})
    for symbol, (first, name) in SYMBOLS.items():
        daily = kase.parse_tv_history(raw[symbol], symbol)
        if daily[0]["date"] > first:
            _structural(ds, f"{symbol} starts {daily[0]['date']}, expected {first} or earlier")
        records += monthly_from_daily(daily, symbol, name)
    return records, {"frequency": "monthly", "source_url": kase.TV_HISTORY_URL, "dataset_id": "kase-tv/" + ",".join(SYMBOLS), "note": ds.get("note", "")}


# ---------------------------------------------------------------- corporate bond volumes

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
NUM = r"(\d[\d ]*(?:,\d+)?)"
ROW = re.compile(r"(?m)^\s*(\d{4}),\s*([IVX]+)\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"\s*$")
SEARCH = "объем торгов корпоративными облигациями на KASE составил"
FIRST_YEAR = 2017


def _num(s: str) -> float:
    return float(re.sub(r"\s", "", s).replace(",", "."))


def bond_rows(body: str) -> dict[str, tuple[float, float, float]]:
    """{YYYY-MM-01: (primary, secondary, total)} from the fixed-width table of a news item:
    «2026, VII    1 197,8     103,2 1 301,1»."""
    text = re.sub(r"<[^>]+>", "\n", body).replace("\xa0", " ")
    out = {}
    for m in ROW.finditer(text):
        month = ROMAN.get(m.group(2))
        if month:
            out[f"{m.group(1)}-{month:02d}-01"] = (_num(m.group(3)), _num(m.group(4)), _num(m.group(5)))
    return out


def _news(search: str, per_page: int = 100) -> list[dict]:
    """The news API lists matches newest first (a search term narrows the set; a year in the
    term keeps the items that mention it)."""
    data = json.loads(kase._get(NEWS_URL, {"search": search, "per_page": per_page, "page": 1, "language": "ru"}))
    return data.get("results") or []


def fetch_bond_volumes(ds: dict) -> tuple[list[dict], dict]:
    from fetchers import imf_dims
    fresh = imf_dims.stored_if_fresh(ds, "kase", ds["id"])
    if fresh:
        return fresh
    wanted = re.compile(r"^За (январь-\S+ \d{4} года|\d{4} год) объем торгов корпоративными облигациями")
    items = [it for it in _news(SEARCH, 10) if wanted.match(it.get("subject", ""))]       # the latest cumulative release
    seen = {it["id"] for it in items}
    for year in range(FIRST_YEAR, date.today().year):            # «За 2025 год …» (each January): the twelve months of that year
        for it in _news(f"За {year} год {SEARCH}"):
            if it["id"] not in seen and wanted.match(it.get("subject", "")):
                items.append(it)
                seen.add(it["id"])
    kase._save_raw(ds["id"], json.dumps(items, ensure_ascii=False, sort_keys=True).encode(), "json", {"source_url": NEWS_URL, "search": SEARCH})
    months: dict[str, tuple[float, float, float]] = {}
    for it in sorted(items, key=lambda it: it.get("create_datetime", ""), reverse=True):   # the latest release wins
        for d, v in bond_rows(it.get("body", "")).items():
            months.setdefault(d, v)
    if len(months) < 24:
        _structural(ds, f"only {len(months)} months parsed from {len(items)} news items")
    records = []
    for d, (p, s, t) in months.items():
        for code, name, v in (("PRIMARY", "Первичный рынок корпоративных облигаций, объём торгов, млрд тенге", p),
                              ("SECONDARY", "Вторичный рынок корпоративных облигаций, объём торгов (без репо), млрд тенге", s),
                              ("TOTAL", "Корпоративные облигации, объём торгов всего (без репо), млрд тенге", t)):
            records.append({"date": d, "region": "national", "item_code": code, "item_name": name, "value": v})
    return records, {"frequency": "monthly", "source_url": NEWS_URL, "dataset_id": "kase news: corporate bond volumes", "note": ds.get("note", "")}
