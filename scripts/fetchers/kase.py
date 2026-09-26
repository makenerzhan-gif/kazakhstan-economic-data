"""Kazakhstan Stock Exchange (KASE): the money-market rate TONIA and the government
securities zero-coupon yield curve.

Found 2026-09-25. kase.kz was rebuilt as an Angular app with two machine-readable
surfaces behind it, neither needing authentication:

- The TradingView data feed the site's indicator charts read:
  GET /tv-charts/indicators/history?symbol=SYM&resolution=D&from=0&to=<unix>
  -> {"s": "ok", "t": [...], "c": [...], ...}; `t` is UTC midnight of the TRADE date,
  `c` the value. TONIA runs from 2001-09-02 (6 195 trading days to 2026-09-25) and
  its dates are trade dates -- including working Sundays such as 2025-01-05. KASE is
  TONIA's administrator; the NBK widget the pipeline read before served only
  2026-02-24 onward, stamped with the publication date (the next business day) and
  with Friday's value repeated over the weekend.

- The curve file: GET /en/app-gateway/documents/curve/ -> an Excel 97 .xls with the
  whole history of the daily Nelson-Siegel parameters (B0, B1, B2 as decimals, TAU in
  years) from 2019-11-04, newest first, dates as Excel serials. The spot yield at
  maturity t years is r(t) = B0 + B1*f + B2*(f - exp(-t/TAU)), f = (1 - exp(-t/TAU))/(t/TAU)
  -- on the 2026-09-25 curve this reproduces the values KASE's own API plots
  (/api/indicators/gsec-curve/) to three decimals at every tenor checked.
  Caveats carried into the notes: TAU wandered between 0.08 and 5.5 before 2024, so the
  long end of some daily fits is an artefact of the fit -- which is why the series are
  published here as MONTHLY AVERAGES of the daily curves; and the curve dated D appears
  to be built from the trades of the session before D (the file saved before trading
  on 2026-09-25 already carries a 2026-09-25 row).
"""
from __future__ import annotations

import math
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

SOURCE = "kase"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
TV_HISTORY_URL = "https://kase.kz/tv-charts/indicators/history"
CURVE_URL = "https://kase.kz/en/app-gateway/documents/curve/"
CURVE_TENORS = {"3M": 0.25, "6M": 0.5, "1Y": 1.0, "2Y": 2.0, "5Y": 5.0, "10Y": 10.0}
EXCEL_EPOCH = date(1899, 12, 30)

_CACHE: dict[str, bytes] = {}


def _get(url: str, params: dict | None = None, attempts: int = 3) -> bytes:
    key = url + repr(sorted((params or {}).items()))
    if key not in _CACHE:
        for i in range(attempts):
            try:
                resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
                resp.raise_for_status()
                _CACHE[key] = resp.content
                break
            except requests.RequestException:
                if i == attempts - 1:
                    raise
                time.sleep(2 * (i + 1))
    return _CACHE[key]


def _save_raw(indicator_id: str, content: bytes, ext: str, extra: dict) -> None:
    today = date.today()
    path = raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, **extra})


def parse_tv_history(payload: dict, symbol: str) -> list[dict]:
    if payload.get("s") != "ok" or not payload.get("t"):
        raise validation.StructuralChangeError("\n".join([
            f"STRUCTURAL CHANGE DETECTED in kase/{symbol}",
            f"WHAT CHANGED: the TradingView feed answered s={payload.get('s')!r} with {len(payload.get('t') or [])} points",
            "EXPECTED: s='ok' and the daily history",
            f"ACTION REQUIRED: inspect {TV_HISTORY_URL}?symbol={symbol}&resolution=D and update scripts/fetchers/kase.py",
        ]))
    records = {}
    for t, c in zip(payload["t"], payload["c"]):
        if c is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        records[d] = float(c)
    return [{"date": d, "value": v} for d, v in sorted(records.items())]


def fetch_tonia() -> tuple[list[dict], dict]:
    """TONIA, % per annum, daily by trade date, from 2001-09-02."""
    import json
    to = int(datetime.now(tz=timezone.utc).timestamp()) + 86400
    params = {"symbol": "TONIA", "resolution": "D", "from": 0, "to": to}
    content = _get(TV_HISTORY_URL, params)
    _save_raw("TONIA", content, "json", {"source_url": TV_HISTORY_URL, "params": params})
    records = parse_tv_history(json.loads(content), "TONIA")
    manifest = {
        "frequency": "daily", "source_url": f"{TV_HISTORY_URL}?symbol=TONIA&resolution=D",
        "dataset_id": "kase-tv/TONIA",
        "note": "Percent per annum. TONIA (Tenge OverNight Index Average): the weighted average rate of "
                "one-day repo transactions in government securities on KASE's automatic repo market, "
                "dated by TRADE date, from 2001-09-02 (the earliest values predate the index's formal "
                "launch and are KASE's own back-calculation). Moved on 2026-09-25 from the NBK widget "
                "(2026-02 onward, publication-dated) to KASE, the index administrator.",
    }
    return records, manifest


def ns_spot(t: float, b0: float, b1: float, b2: float, tau: float) -> float:
    """Nelson-Siegel spot rate at maturity t years, in the parameters' own units."""
    x = t / tau
    f = (1 - math.exp(-x)) / x
    return b0 + b1 * f + b2 * (f - math.exp(-x))


def parse_curve_xls(content: bytes) -> list[dict]:
    """[{date, B0, B1, B2, TAU}] for every day in the file, oldest first."""
    sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
    header_i = next((i for i in range(min(sheet.nrows, 20))
                     if [str(c).strip() for c in sheet.row_values(i)[1:5]] == ["B0", "B1", "B2", "TAU"]), None)
    if header_i is None:
        raise validation.StructuralChangeError("\n".join([
            "STRUCTURAL CHANGE DETECTED in kase/GS_YIELD curve file",
            "WHAT CHANGED: no header row '| B0 | B1 | B2 | TAU' in the first 20 rows of sheet 1",
            f"ACTION REQUIRED: inspect {CURVE_URL} and update scripts/fetchers/kase.py",
        ]))
    days = {}
    for i in range(header_i + 1, sheet.nrows):
        row = sheet.row_values(i)
        if not isinstance(row[0], float) or not all(isinstance(v, float) for v in row[1:5]):
            continue
        d = (EXCEL_EPOCH + timedelta(days=int(row[0]))).isoformat()
        days[d] = {"date": d, "B0": row[1], "B1": row[2], "B2": row[3], "TAU": row[4]}
    return [days[d] for d in sorted(days)]


def monthly_tenor_averages(curves: list[dict]) -> dict[str, list[dict]]:
    """{tenor: [{date: YYYY-MM-01, value: % p.a.}]}: the mean over the month's daily curves."""
    sums: dict[str, dict[str, list[float]]] = {k: defaultdict(list) for k in CURVE_TENORS}
    for c in curves:
        if c["TAU"] <= 0:
            continue
        month = c["date"][:7] + "-01"
        for k, t in CURVE_TENORS.items():
            sums[k][month].append(100 * ns_spot(t, c["B0"], c["B1"], c["B2"], c["TAU"]))
    return {k: [{"date": m, "value": round(sum(v) / len(v), 4)} for m, v in sorted(by_month.items())]
            for k, by_month in sums.items()}


def fetch_gs_yield(tenor: str) -> tuple[list[dict], dict]:
    indicator_id = f"GS_YIELD_{tenor}"
    content = _get(CURVE_URL)
    _save_raw("GS_YIELD_CURVE", content, "xls", {"source_url": CURVE_URL, "read_by": "GS_YIELD_*"})
    curves = parse_curve_xls(content)
    if len(curves) < 1000:
        raise validation.StructuralChangeError(
            f"kase/{indicator_id}: only {len(curves)} daily curves in {CURVE_URL}; expected the history from 2019-11-04")
    records = monthly_tenor_averages(curves)[tenor]
    last_month = records[-1]["date"][:7]
    days_in_last = sum(1 for c in curves if c["date"].startswith(last_month))
    manifest = {
        "frequency": "monthly", "source_url": CURVE_URL, "dataset_id": f"kase-gs-curve/{tenor}",
        "note": f"Percent per annum, zero-coupon yield of government securities at {tenor}, the MONTHLY "
                "AVERAGE of KASE's daily Nelson-Siegel curves (r(t) = B0 + B1*f + B2*(f - exp(-t/TAU))), "
                f"from 2019-11. The latest month ({last_month}) averages the {days_in_last} curves so far. "
                "Before 2024 TAU varied from 0.08 to 5.5, so the long end of individual daily fits can be "
                "an artefact; the monthly mean damps it but does not remove it.",
    }
    return records, manifest


def fetch_gs_yield_3m() -> tuple[list[dict], dict]:
    return fetch_gs_yield("3M")


def fetch_gs_yield_6m() -> tuple[list[dict], dict]:
    return fetch_gs_yield("6M")


def fetch_gs_yield_1y() -> tuple[list[dict], dict]:
    return fetch_gs_yield("1Y")


def fetch_gs_yield_2y() -> tuple[list[dict], dict]:
    return fetch_gs_yield("2Y")


def fetch_gs_yield_5y() -> tuple[list[dict], dict]:
    return fetch_gs_yield("5Y")


def fetch_gs_yield_10y() -> tuple[list[dict], dict]:
    return fetch_gs_yield("10Y")


def fetch_swap_1d() -> tuple[list[dict], dict]:
    """SWAP-1D (USD): KASE's weighted-average annualised rate on one-day USD/KZT FX swaps."""
    import json
    to = int(datetime.now(tz=timezone.utc).timestamp()) + 86400
    params = {"symbol": "SWAP_1D", "resolution": "D", "from": 0, "to": to}
    content = _get(TV_HISTORY_URL, params)
    _save_raw("SWAP_1D", content, "json", {"source_url": TV_HISTORY_URL, "params": params})
    records = parse_tv_history(json.loads(content), "SWAP_1D")
    manifest = {
        "frequency": "daily", "source_url": f"{TV_HISTORY_URL}?symbol=SWAP_1D&resolution=D",
        "dataset_id": "kase-tv/SWAP_1D",
        "note": "Percent per annum, KASE indicator «SWAP-1D (USD)» (fini code SWAP_USDKZT_1): weighted average "
                "annualised rate on one-day USD/KZT FX swaps on KASE, by trade date, from 2014-06-09. KASE publishes "
                "no definition beyond the name and unit. Behaviour checked 2026-09-26 against TONIA and the Fed "
                "funds rate (monthly means): 2024-2026 it tracks the differential TONIA - fed funds (mean gap -0.5 "
                "pp), but from 2022-12 to 2023-06, with the Fed at 4-5 %, it stayed at TONIA + 1 (15-17 %) instead "
                "of falling to the differential (11-12 %) -- either a large covered-parity deviation in those "
                "months or a different construction; read it with that in mind.",
    }
    return records, manifest
