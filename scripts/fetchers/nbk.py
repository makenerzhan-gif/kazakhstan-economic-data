"""National Bank of Kazakhstan fetcher.

Confirmed live 2026-08-30 (see config/sources.yaml -> agencies.nbk). Open Data
Repository base https://data.nationalbank.kz/api/v1 -- no auth/CAPTCHA on the
data-serving endpoints used here.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
SOURCE = "nbk"

BASE_RATE_URL = "https://data.nationalbank.kz/api/v1/data/base-rate"
RATES_CFM_URL = "https://nationalbank.kz/rss/get_rates.cfm"


def _download(url: str, params: dict | None = None) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp


def fetch_base_rate() -> tuple[list[dict], dict]:
    """Base rate history. Verified live 2026-08-30: full history returned in one
    call (date-filter query params are silently ignored), JSON list of
    {effectiveDate, rate, corridorLower, corridorUpper}. Note this is an
    event-dated series (one row per rate CHANGE, not one row per calendar day) --
    the rate stays constant between MPC decisions, so gaps of several weeks
    between records are expected and not a data quality problem.
    """
    resp = _download(BASE_RATE_URL)
    content = resp.content
    today = date.today()
    raw_store.save_raw_bytes(SOURCE, "BASE_RATE", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "BASE_RATE", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": BASE_RATE_URL,
    })

    data = resp.json()
    if not isinstance(data, list) or not data or "effectiveDate" not in data[0] or "rate" not in data[0]:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/BASE_RATE",
                "WHAT CHANGED: response is no longer a list of {effectiveDate, rate, ...} objects",
                "EXPECTED: JSON list with effectiveDate and rate fields",
                f"ACTUAL: {str(data)[:300]}",
                f"ACTION REQUIRED: inspect {BASE_RATE_URL} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": row["effectiveDate"], "value": float(row["rate"])} for row in data]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "daily",
        "source_url": BASE_RATE_URL,
        "dataset_id": "base-rate",
        "note": "event-dated (rate valid until the next MPC decision), not literal daily observations",
    }
    return records, manifest


def fetch_exchange_rate_usd(days_back: int = 14) -> tuple[list[dict], dict]:
    """Official daily USD/KZT rate, last `days_back` calendar days.

    Verified live 2026-08-30: the JSON current-rate endpoint always returns
    today's snapshot only (date-filter params are silently ignored), so a real
    historical series has to be built by querying the legacy per-date XML
    endpoint (nationalbank.kz/rss/get_rates.cfm?fdate=DD.MM.YYYY) once per date.
    Each date's raw XML is archived separately (not merged before saving) to
    keep raw data an unmodified copy of what the source actually returned.
    Limited to a recent window per run rather than looping over the entire
    history -- deep backfill is a deliberate separate one-time job, not part
    of the regular incremental update.
    """
    today = date.today()
    records: list[dict] = []
    for i in range(days_back):
        d = today - timedelta(days=i)
        fdate = d.strftime("%d.%m.%Y")
        resp = requests.get(RATES_CFM_URL, headers=HEADERS, params={"fdate": fdate}, timeout=30)
        if resp.status_code != 200 or not resp.content:
            continue
        raw_store.save_raw_bytes(SOURCE, f"EXCHANGE_RATE_{d.isoformat()}", today, "xml", resp.content)
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            continue
        usd_value = None
        for item in root.findall(".//item"):
            title_el = item.find("title")
            if title_el is not None and (title_el.text or "").strip() == "USD":
                desc_el = item.find("description")
                if desc_el is not None and desc_el.text:
                    try:
                        usd_value = float(desc_el.text.strip())
                    except ValueError:
                        usd_value = None
                break
        if usd_value is not None:
            records.append({"date": d.isoformat(), "value": usd_value})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/EXCHANGE_RATE",
                "WHAT CHANGED: no USD rate could be parsed from any of the last "
                f"{days_back} days' responses",
                "EXPECTED: an <item><title>USD</title><description>{rate}</description></item> "
                "element for at least one recent date",
                f"ACTUAL: zero parseable USD entries across {days_back} requests to {RATES_CFM_URL}",
                "ACTION REQUIRED: inspect the live XML response and update scripts/fetchers/nbk.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, "EXCHANGE_RATE", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": RATES_CFM_URL, "days_back": days_back,
        "n_records": len(records),
    })

    records.sort(key=lambda r: r["date"])
    manifest = {"frequency": "daily", "source_url": RATES_CFM_URL, "dataset_id": "get_rates.cfm"}
    return records, manifest
