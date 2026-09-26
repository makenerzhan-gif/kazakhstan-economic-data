"""Kazakhstan sovereign Eurobonds: KASE settlement-price valuations -> yields and the spread
over US Treasuries (country risk premium for the r* / UIP / rating work). Added 2026-09-26.

SOURCE. The Kazakhstan Stock Exchange values every listed security daily («расчетные цены»,
its methodology: market prices where there are trades, otherwise capped by external bid/ask
quotes, with Refinitiv/Bloomberg last prices as a fallback since July 2023) and publishes
the valuations free, without login or signed requests:
- 2024-08-01 onward: GET https://kase.kz/ru/app-gateway/documents/risk/DD.MM.YYYY/ (trailing
  slash required) -> xls, sheet «Расчетные цены_ФР» (code, ISIN, issuer, clean, dirty, YTM,
  days to maturity on 30/360). Files for earlier dates carry no price sheet.
- 2003 to 2024-07-31: the CMS listing https://kase.kz/cms/api/market-prices (Strapi, JSON,
  filters on date) -> one zip per valuation date with an xls/xlsx inside. Layouts: to 2020-06
  a sheet «Еврооблигации МФ РК» (НИН, code, days, YTM, clean, dirty, ..., coupon); 2020-07 to
  2020-10 clean prices only; 2020-11 to 2024-07 «Расчетные цены» with a price-type column
  («Рыночная» / «Индикативная»). Weekly files in 2014-2016, daily after.
Checked 2026-09-26: London Stock Exchange's last trade in XS1263139856 (27.07.2026) 105.354
against KASE's 105.642; our 30/360 semi-annual YTM reproduces KASE's to 0.01 pp.
Other free sources were checked and rejected (AIX: no trades, not all bonds; LSE: snapshot
only, history behind a signed widget; Deutsche Börse: requests must carry headers computed
from a key in its JavaScript -- not reproduced here; NBK / IMF / FRED / World Bank: no series).

WHAT IS BUILT. The LAST valuation of each month (a month-end observation, dated at the
first day of the month like the other monthly series). Per issue: clean price and YTM
(KASE's; computed from the clean price where KASE left it blank, 2019-12 to 2020-10 for the
USD bonds). Spread = YTM minus the US Treasury constant-maturity yield (FRED DGS5/7/10/20/30
on the valuation date, linearly interpolated at the bond's remaining maturity).

QUALITY -- read before use. 2020-11 to 2022-07 only the 2044 bond is quoted and its values
are often stale or flagged «Индикативная» (e.g. 25 bp in June 2022, a stress month; the price
is unchanged across May and June 2022). From 2022-08 the 2045 bond is quoted and from 2024
the long bonds agree with each other within about 20 bp. Hence the headline
KZ_EUROBOND_SPREAD is the 2044 bond to 2020-10, MISSING 2020-11 to 2022-07, and the 2045 bond
from 2022-08; the per-issue datasets keep every month.

Accumulates: months already processed are kept, only missing months and the last two are
fetched on each run (the first run back-fills from 2014-10; KASE resets connections under
load, so requests are spaced and retried).
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, raw_store, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
RISK_URL = "https://kase.kz/ru/app-gateway/documents/risk/{d:%d.%m.%Y}/"
CMS_URL = "https://kase.kz/cms/api/market-prices"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
RISK_FILES_FROM = date(2024, 8, 1)
FIRST_MONTH = date(2014, 10, 1)
SPACING = 1.5                                    # seconds between KASE requests

# USD Eurobonds of the Ministry of Finance with the terms used to compute a yield where KASE
# gives none (30/360, semi-annual). Coupons and maturities checked 2026-09-26: KASE's own
# YTM is reproduced to 0.01 pp, its 30/360 days-to-maturity hit these dates, and the 2014-2020
# files carry the coupon column (3.875 / 4.875 / 5.125).
USD_BONDS = {
    "XS1120709669": ("KZ_05_2410", 3.875, date(2024, 10, 14)),
    "XS1120709826": ("KZ_06_4410", 4.875, date(2044, 10, 14)),
    "XS1263054519": ("KZ_07_2507", 5.125, date(2025, 7, 21)),
    "XS1263139856": ("KZ_22_4507", 6.5, date(2045, 7, 21)),
    "XS2914770545": ("KZ_23_3504", 4.714, date(2035, 4, 9)),
    "XS3093655341": ("KZ_24_3207", 5.0, date(2032, 7, 1)),
    "XS3093658014": ("KZ_25_3707", 5.5, date(2037, 7, 1)),
}
BENCHMARK = [  # (from month, to month, ISIN); months outside every window are left missing
    (date(2014, 10, 1), date(2020, 10, 1), "XS1120709826"),
    (date(2022, 8, 1), date(9999, 12, 1), "XS1263139856"),
]
_CACHE: dict = {}


def _get(url: str, params: dict | None = None, attempts: int = 5) -> bytes:
    for i in range(attempts):
        try:
            time.sleep(SPACING)
            resp = requests.get(url, params=params, headers=HEADERS, timeout=90)
            resp.raise_for_status()
            return resp.content
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 404:
                raise
            if i == attempts - 1:
                raise
            time.sleep(5 * (i + 1))
    raise RuntimeError("unreachable")


def _num(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("\xa0", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------- parsing
def parse_workbook(content: bytes) -> dict[str, dict]:
    """{ISIN: {code, clean, dirty, ytm, days, kind}} for the Ministry of Finance Eurobonds
    (ISIN XS…, KASE code KZ_nn_yymm) in any sheet with a «Торговый код» header row."""
    out: dict[str, dict] = {}
    for _name, df in pd.read_excel(io.BytesIO(content), sheet_name=None, header=None).items():
        rows = df.values.tolist()
        hi = next((i for i, r in enumerate(rows[:15])
                   if any(isinstance(c, str) and c.strip() == "Торговый код" for c in r)), None)
        if hi is None:
            continue
        head = [" ".join(str(c).split()) if isinstance(c, str) else "" for c in rows[hi]]
        below = [" ".join(str(c).split()) if isinstance(c, str) else "" for c in rows[hi + 1]] if hi + 1 < len(rows) else []
        col: dict[str, int] = {}
        for j, h in enumerate(head):
            if h == "Торговый код":
                col["code"] = j
            elif h in ("ISIN", "НИН"):
                col["isin"] = j
            elif h.startswith("Дней до погашения"):
                col["days"] = j
            elif h.startswith("Доходность"):
                col["ytm"] = j
            elif h.startswith(("Расчетная цена", "Рыночная цена")) and "clean" not in col:
                col["clean"] = j
            elif "грязн" in h and "dirty" not in col:
                col["dirty"] = j
        if "clean" in col and "dirty" not in col and col["clean"] + 1 < len(below) and "грязн" in below[col["clean"] + 1]:
            col["dirty"] = col["clean"] + 1
        if not {"code", "isin", "clean"} <= set(col):
            continue
        for r in rows[hi + 1:]:
            isin = str(r[col["isin"]]).strip() if col["isin"] < len(r) else ""
            code = str(r[col["code"]]).strip() if col["code"] < len(r) else ""
            if not (isin.startswith("XS") and code.startswith("KZ_")):
                continue
            clean = _num(r[col["clean"]])
            if clean is None:
                continue
            kind = next((str(c).strip() for c in r if isinstance(c, str) and c.strip() in ("Рыночная", "Индикативная")), "")
            rec = {"code": code, "clean": clean, "dirty": _num(r[col["dirty"]]) if "dirty" in col else None,
                   "ytm": _num(r[col["ytm"]]) if "ytm" in col else None,
                   "days": _num(r[col["days"]]) if "days" in col else None, "kind": kind}
            # Two files for one date (market and indicative) -- the market valuation wins.
            if isin not in out or (out[isin]["kind"] == "Индикативная" and kind != "Индикативная"):
                out[isin] = rec
    return out


def parse_zip(content: bytes) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.lower().endswith((".xls", ".xlsx")):
                try:
                    got = parse_workbook(z.read(name))
                except Exception:  # noqa: BLE001 -- one unreadable member must not sink the date
                    continue
                for k, v in got.items():
                    if k not in out or (out[k]["kind"] == "Индикативная" and v["kind"] != "Индикативная"):
                        out[k] = v
    return out


# ---------------------------------------------------------------- one month-end
def _cms_listing(gte: date, lte: date) -> list[dict]:
    params = {"filters[date][$gte]": gte.isoformat(), "filters[date][$lte]": lte.isoformat(),
              "pagination[pageSize]": 100, "sort": "date:desc", "populate": "deep"}
    return json.loads(_get(CMS_URL, params=params))["data"]


def _save(name: str, rows: dict, info: dict) -> None:
    content = json.dumps({"rows": rows, **info}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    today = date.today()
    raw_store.save_raw_bytes("kase", f"EUROBOND_VALUATION_{name}", today, "json", content)


def month_end(month: date) -> tuple[date, dict[str, dict]] | None:
    """(valuation date, rows) of the last valuation in the month, or None."""
    nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = min(nxt - timedelta(days=1), date.today())
    if last >= RISK_FILES_FROM:
        d = last
        while d >= max(month, last - timedelta(days=10)):
            if d.weekday() < 5:
                try:
                    content = _get(RISK_URL.format(d=d))
                except requests.HTTPError:
                    content = b""
                if content[:4] == b"\xd0\xcf\x11\xe0" or content[:2] == b"PK":
                    rows = parse_workbook(content)
                    if rows:
                        _save(d.isoformat(), rows, {"source_url": RISK_URL.format(d=d)})
                        return d, rows
            d -= timedelta(days=1)
        return None
    by_date: dict[str, list[tuple[str, str]]] = {}
    for rec in _cms_listing(max(month, last - timedelta(days=12)), last):
        f = rec.get("file") or {}
        url, name, title = f.get("url", ""), f.get("name", ""), rec.get("title", "")
        if not url or any(x in name for x in ("notliq", "fut_price", "afn")):
            continue
        if "оценки" in title or "индикативными" in title or "Price" in name:
            by_date.setdefault(rec["date"], []).append((url, name))
    for d in sorted(by_date, reverse=True):
        rows: dict[str, dict] = {}
        for url, name in by_date[d]:
            try:
                content = _get("https://kase.kz" + url)
                got = parse_zip(content) if name.lower().endswith(".zip") else parse_workbook(content)
            except Exception:  # noqa: BLE001 -- two archive zips are known to be corrupt; the date's twin is used
                continue
            for k, v in got.items():
                if k not in rows or (rows[k]["kind"] == "Индикативная" and v["kind"] != "Индикативная"):
                    rows[k] = v
        if rows:
            _save(d, rows, {"source_url": CMS_URL, "files": [n for _, n in by_date[d]]})
            return date.fromisoformat(d), rows
    return None


# ---------------------------------------------------------------- yields and Treasuries
def _d360(a: date, b: date) -> int:
    d1 = min(a.day, 30)
    d2 = 30 if (b.day == 31 and d1 == 30) else b.day
    return 360 * (b.year - a.year) + 30 * (b.month - a.month) + (d2 - d1)


def _add_months(d: date, m: int) -> date:
    y, mo = d.year + (d.month - 1 + m) // 12, (d.month - 1 + m) % 12 + 1
    return d.replace(year=y, month=mo)


def ytm_from_clean(clean: float, settle: date, maturity: date, coupon: float) -> float:
    """Yield to maturity, % p.a., semi-annual 30/360, from a clean price in % of par."""
    dates = [maturity]
    while dates[-1] > settle:
        dates.append(_add_months(dates[-1], -6))
    prev, nxt = dates[-1], dates[-2]
    future = sorted(c for c in dates if c > settle)
    dirty = clean + coupon * _d360(prev, settle) / 360
    frac = _d360(settle, nxt) / 180

    def pv(y: float) -> float:
        return sum((coupon / 2 + (100 if c == maturity else 0)) / (1 + y / 2) ** (frac + i) for i, c in enumerate(future))

    lo, hi = -0.05, 0.5
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pv(mid) > dirty else (lo, mid)
    return round(100 * (lo + hi) / 2, 4)


UST_SERIES = {5: "DGS5", 7: "DGS7", 10: "DGS10", 20: "DGS20", 30: "DGS30"}


def treasury_curve() -> dict[int, dict[str, float]]:
    if "ust" not in _CACHE:
        curve = {}
        for tenor, series in UST_SERIES.items():
            content = requests.get(FRED_URL, params={"id": series}, headers=HEADERS, timeout=90).content
            raw_store.save_raw_bytes("fred", f"UST_{series}", date.today(), "csv", content)
            vals = {}
            for r in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
                d, v = r.get("observation_date") or r.get("DATE"), r.get(series)
                if d and v not in (None, "", "."):
                    vals[d] = float(v)
            curve[tenor] = vals
        _CACHE["ust"] = curve
    return _CACHE["ust"]


def treasury_yield(on: date, years: float, curve: dict[int, dict[str, float]]) -> float | None:
    """The constant-maturity yield at `years`, linear between 5/7/10/20/30, on the last
    FRED date at or before `on` (within 7 days)."""
    points = {}
    for tenor, vals in curve.items():
        d = on
        while d > on - timedelta(days=7) and d.isoformat() not in vals:
            d -= timedelta(days=1)
        if d.isoformat() in vals:
            points[tenor] = vals[d.isoformat()]
    if not points:
        return None
    tenors = sorted(points)
    if years <= tenors[0]:
        return points[tenors[0]]
    if years >= tenors[-1]:
        return points[tenors[-1]]
    for a, b in zip(tenors, tenors[1:]):
        if a <= years <= b:
            return points[a] + (points[b] - points[a]) * (years - a) / (b - a)
    return None


# ---------------------------------------------------------------- history
def _months(start: date, end: date) -> list[date]:
    out, m = [], start
    while m <= end:
        out.append(m)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def history() -> dict[str, dict]:
    """{YYYY-MM-01: {"date": valuation date, "bonds": {ISIN: {code, clean, ytm}}}} -- the
    processed history plus the months missing from it and the last two."""
    if "history" in _CACHE:
        return _CACHE["history"]
    hist: dict[str, dict] = {}
    for kind, ds in (("clean", "EUROBOND_PRICE_BY_ISSUE"), ("ytm", "EUROBOND_YTM_BY_ISSUE")):
        for r in dims.load_processed(ds):
            m = hist.setdefault(r["date"], {"date": None, "bonds": {}})
            m["bonds"].setdefault(r["item_code"], {"code": r["item_name"].split(" ")[0]})[kind] = float(r["value"])
    dates_path = REPO_ROOT / "data" / "processed" / "kase" / "eurobond_valuation_dates.json"
    if dates_path.exists():
        for k, v in json.loads(dates_path.read_text(encoding="utf-8")).items():
            if k in hist:
                hist[k]["date"] = v
    today = date.today()
    months = _months(FIRST_MONTH, today.replace(day=1))
    refresh = {m.isoformat() for m in months[-2:]}
    for m in months:
        key = m.isoformat()
        if key in hist and key not in refresh and hist[key].get("date"):
            continue
        got = month_end(m)
        if got is None:
            continue
        vdate, rows = got
        bonds = {}
        for isin, r in rows.items():
            ytm = r["ytm"]
            if isin in USD_BONDS:
                _code, coupon, maturity = USD_BONDS[isin]
                if maturity <= vdate:
                    continue
                calc = ytm_from_clean(r["clean"], vdate, maturity, coupon)
                if ytm is None:
                    ytm = calc
                elif abs(calc - ytm) > 0.1 and r["kind"] != "Индикативная":
                    raise validation.StructuralChangeError(
                        f"kase/eurobonds {isin} {vdate}: KASE YTM {ytm} but {calc} from the clean price {r['clean']} "
                        f"-- check the coupon/maturity in USD_BONDS or the column mapping")
            if ytm is None:
                continue
            bonds[isin] = {"code": r["code"], "clean": r["clean"], "ytm": round(ytm, 4)}
        if bonds:
            hist[key] = {"date": vdate.isoformat(), "bonds": bonds}
    dates_path.parent.mkdir(parents=True, exist_ok=True)
    dates_path.write_text(json.dumps({k: v["date"] for k, v in sorted(hist.items()) if v.get("date")}, indent=0),
                          encoding="utf-8")
    _CACHE["history"] = hist
    return hist


def spreads() -> dict[str, dict[str, float]]:
    """{month: {ISIN: spread in bp}} for the USD bonds."""
    if "spreads" in _CACHE:
        return _CACHE["spreads"]
    curve = treasury_curve()
    out: dict[str, dict[str, float]] = {}
    for month, m in history().items():
        if not m.get("date"):
            continue
        vdate = date.fromisoformat(m["date"])
        for isin, b in m["bonds"].items():
            if isin not in USD_BONDS or "ytm" not in b:
                continue
            years = (USD_BONDS[isin][2] - vdate).days / 365.25
            ust = treasury_yield(vdate, years, curve)
            if ust is not None:
                out.setdefault(month, {})[isin] = round(100 * (b["ytm"] - ust), 1)
    _CACHE["spreads"] = out
    return out


# ---------------------------------------------------------------- datasets
def _label(isin: str, code: str) -> str:
    if isin in USD_BONDS:
        _c, cpn, mat = USD_BONDS[isin]
        return f"{code} {isin} USD {cpn}% {mat.isoformat()}"
    return f"{code} {isin}"


def fetch(ds: dict) -> tuple[list[dict], dict]:
    hist = history()
    measure = ds["measure"]                       # clean | ytm | spread
    records = []
    if measure == "spread":
        for month, by in spreads().items():
            for isin, v in by.items():
                records.append({"date": month, "region": dims.NATIONAL, "item_code": isin,
                                "item_name": _label(isin, hist[month]["bonds"][isin]["code"]), "value": v})
    else:
        for month, m in hist.items():
            for isin, b in m["bonds"].items():
                if measure in b:
                    records.append({"date": month, "region": dims.NATIONAL, "item_code": isin,
                                    "item_name": _label(isin, b.get("code", "")), "value": b[measure]})
    if len({r["date"] for r in records}) < 100:
        raise validation.StructuralChangeError(f"kase/{ds['id']}: only {len({r['date'] for r in records})} months")
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "monthly", "source_url": "https://kase.kz/ru/app-gateway/documents/risk/DD.MM.YYYY/ ; " + CMS_URL,
        "dataset_id": "kase/settlement-prices/MinFin-eurobonds", "note": ds.get("note", "")}


def _benchmark(month: str) -> str | None:
    m = date.fromisoformat(month)
    return next((isin for a, b, isin in BENCHMARK if a <= m <= b), None)


def fetch_benchmark(indicator_id: str) -> tuple[list[dict], dict]:
    hist, sp = history(), spreads()
    records = []
    for month in sorted(hist):
        isin = _benchmark(month)
        if isin is None:
            continue
        if indicator_id == "KZ_EUROBOND_SPREAD":
            v = sp.get(month, {}).get(isin)
        else:
            v = hist[month]["bonds"].get(isin, {}).get("ytm")
        if v is not None:
            records.append({"date": month, "value": v})
    unit = "basis points over US Treasuries" if indicator_id == "KZ_EUROBOND_SPREAD" else "percent per annum"
    return records, {
        "frequency": "monthly", "source_url": "https://kase.kz (settlement prices) ; FRED DGS5/7/10/20/30",
        "dataset_id": "kase/settlement-prices+FRED",
        "note": (f"{unit.capitalize()}, last KASE valuation of the month of the benchmark long USD Eurobond of the "
                 "Ministry of Finance: 4.875% 2044 (XS1120709826) to 2020-10, 6.5% 2045 (XS1263139856) from 2022-08; "
                 "2020-11 to 2022-07 deliberately missing (only stale/indicative 2044 quotes -- see "
                 "EUROBOND_*_BY_ISSUE). Spread against the FRED constant-maturity Treasury yield interpolated at the "
                 "bond's remaining maturity on the valuation date. Not EMBI: one bond, KASE's valuation.")}


def fetch_kz_eurobond_spread() -> tuple[list[dict], dict]:
    return fetch_benchmark("KZ_EUROBOND_SPREAD")


def fetch_kz_eurobond_yield() -> tuple[list[dict], dict]:
    return fetch_benchmark("KZ_EUROBOND_YIELD")
