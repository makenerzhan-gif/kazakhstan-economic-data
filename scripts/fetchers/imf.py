"""IMF SDMX 3.0 API fetcher.

Confirmed live 2026-08-30 (see config/sources.yaml -> agencies.imf for the full
research trail). Base: https://api.imf.org/external/sdmx/3.0 . No auth required,
but a real User-Agent is needed (bare requests get edge-blocked on some imf.org
subdomains). We request the CSV representation rather than parsing the SDMX-JSON
schema by hand -- the JSON structure was not verified in detail during research,
whereas the CSV columns were confirmed to be clean and tabular.
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

BASE_URL = "https://api.imf.org/external/sdmx/3.0/data/dataflow"
HEADERS = {
    "Accept": "application/vnd.sdmx.data+csv",
    "User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)",
}

DATE_COL_CANDIDATES = ["TIME_PERIOD", "PERIOD", "YEAR", "DATE"]
VALUE_COL_CANDIDATES = ["OBS_VALUE", "VALUE", "VAL"]

SOURCE = "imf"


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def _parse_annual_csv(content: bytes, indicator_id: str, source_url: str) -> list[dict]:
    text = content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError(f"IMF API returned an empty CSV body for {source_url}")

    columns = set(rows[0].keys())
    date_col = next((c for c in DATE_COL_CANDIDATES if c in columns), None)
    value_col = next((c for c in VALUE_COL_CANDIDATES if c in columns), None)
    if date_col is None or value_col is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in imf/{indicator_id}",
                "WHAT CHANGED: IMF SDMX CSV response no longer has a recognizable date/value column",
                f"EXPECTED: a date column from {DATE_COL_CANDIDATES} and a value column from {VALUE_COL_CANDIDATES}",
                f"ACTUAL COLUMNS: {sorted(columns)}",
                "ACTION REQUIRED: inspect the live response at "
                f"{source_url} and update scripts/fetchers/imf.py's column candidates.",
            ])
        )

    records = []
    for row in rows:
        period = (row.get(date_col) or "").strip()
        raw_val = (row.get(value_col) or "").strip()
        if not period or not raw_val:
            continue
        # Annual WEO observations are labeled just by year (e.g. "2024"); we stamp them
        # at Jan 1 of that year as a documented convention, not an implied in-year timing.
        iso_date = f"{period}-01-01" if period.isdigit() and len(period) == 4 else period
        try:
            value = float(raw_val)
        except ValueError:
            continue
        records.append({"date": iso_date, "value": value})

    records.sort(key=lambda r: r["date"])
    return records


def _fetch_weo_series(indicator_id: str, dataflow: str, agency_code: str, version: str,
                       country: str, code: str) -> tuple[list[dict], dict]:
    url = f"{BASE_URL}/{agency_code}/{dataflow}/{version}/{country}.{code}"
    content = _download(url)

    today = date.today()
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, "csv", content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "source_url": url,
        "downloaded_at": datetime.now().isoformat(),
        "dataflow": dataflow,
        "agency_code": agency_code,
        "version": version,
        "country": country,
        "indicator_code": code,
    })

    records = _parse_annual_csv(content, indicator_id, url)
    manifest = {
        "frequency": "annual",
        "source_url": url,
        "dataset_id": f"{dataflow}/{version}",
    }
    return records, manifest


def fetch_gdp_growth() -> tuple[list[dict], dict]:
    return _fetch_weo_series("IMF_GDP_GROWTH", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGDP_RPCH")


def fetch_inflation() -> tuple[list[dict], dict]:
    return _fetch_weo_series("IMF_INFLATION", "WEO", "IMF.RES", "9.0.0", "KAZ", "PCPIPCH")


def fetch_current_account() -> tuple[list[dict], dict]:
    return _fetch_weo_series("IMF_CURRENT_ACCOUNT", "WEO", "IMF.RES", "9.0.0", "KAZ", "BCA_NGDPD")


def fetch_unemployment() -> tuple[list[dict], dict]:
    """WEO unemployment rate. Verified live 2026-08-30: indicator code LUR."""
    return _fetch_weo_series("IMF_UNEMPLOYMENT", "WEO", "IMF.RES", "9.0.0", "KAZ", "LUR")


def fetch_gov_balance() -> tuple[list[dict], dict]:
    """WEO general government net lending/borrowing, % of GDP.
    Verified live 2026-08-30: indicator code GGXCNL_NGDP."""
    return _fetch_weo_series("IMF_GOV_BALANCE", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGXCNL_NGDP")


def fetch_gov_debt() -> tuple[list[dict], dict]:
    """WEO general government gross debt, % of GDP.
    Verified live 2026-08-30: indicator code GGXWDG_NGDP."""
    return _fetch_weo_series("IMF_GOV_DEBT", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGXWDG_NGDP")


def fetch_population() -> tuple[list[dict], dict]:
    """WEO population. Verified live 2026-08-30: indicator code LP. Sanity-checked:
    2025 value (20,380,366) matches Kazakhstan's known population trajectory."""
    return _fetch_weo_series("IMF_POPULATION", "WEO", "IMF.RES", "9.0.0", "KAZ", "LP")


def fetch_nominal_gdp() -> tuple[list[dict], dict]:
    """WEO nominal GDP, national currency (KZT). Verified live 2026-08-30: indicator
    code NGDP. Cross-checked: 2024 value (136,693,318,000,000) matches our own
    BNS-sourced GDP_NOMINAL series (136,693,318,300,000) to within 0.0000002% --
    independent confirmation both series are correct."""
    return _fetch_weo_series("IMF_NOMINAL_GDP", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGDP")


def fetch_nominal_gdp_usd() -> tuple[list[dict], dict]:
    """WEO nominal GDP, USD. Verified live 2026-08-30: indicator code NGDPD."""
    return _fetch_weo_series("IMF_NOMINAL_GDP_USD", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGDPD")


def fetch_gdp_ppp() -> tuple[list[dict], dict]:
    """WEO GDP, PPP-adjusted (international dollars). Verified live 2026-08-30:
    indicator code PPPGDP."""
    return _fetch_weo_series("IMF_GDP_PPP", "WEO", "IMF.RES", "9.0.0", "KAZ", "PPPGDP")


def fetch_investment_ratio() -> tuple[list[dict], dict]:
    """WEO total investment, % of GDP. Verified live 2026-08-30: indicator code NID_NGDP."""
    return _fetch_weo_series("IMF_INVESTMENT_RATIO", "WEO", "IMF.RES", "9.0.0", "KAZ", "NID_NGDP")


def fetch_savings_ratio() -> tuple[list[dict], dict]:
    """WEO gross national savings, % of GDP. Verified live 2026-08-30: indicator code NGSD_NGDP."""
    return _fetch_weo_series("IMF_SAVINGS_RATIO", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGSD_NGDP")
