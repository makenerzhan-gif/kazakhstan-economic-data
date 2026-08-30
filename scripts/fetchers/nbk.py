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


MONETARY_AGGREGATES_URL = "https://data.nationalbank.kz/api/v1/data"
MONETARY_AGGREGATES_FORM_ID = "51"

# Verified live 2026-08-30 by cross-checking numeric values against the human-facing
# table at https://nationalbank.kz/ru/monetarybase/denezhnaya-baza-i-agregaty-shirokoy-denezhnoy-massy
# (opened in a real browser -- the row labels aren't in any API response, only on that
# rendered page). Row numbering there matches row_code exactly ("4. M2", "5. M3
# (денежная масса)"), and the actual amounts line up 1:1 (e.g. row_code=4,
# report_date=2026-07-01 -> 48128860.58 vs the page's M2 column for the corresponding
# month -> 48 128 861). Note report_date in the API appears to be the 1st of the month
# AFTER the period the value describes (the page's own month labels are one month
# earlier than the API's report_date for the same number) -- we store report_date
# verbatim rather than guessing a shift, and record this observation in metadata.
ROW_CODE_M2 = "4"
ROW_CODE_M3 = "5"


def _fetch_monetary_aggregate_rows(row_code: str, indicator_id: str) -> tuple[list[dict], bytes]:
    all_rows: list[dict] = []
    raw_pages: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": MONETARY_AGGREGATES_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_pages.append(data)
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    raw_content = json.dumps(raw_pages, ensure_ascii=False).encode("utf-8")
    today = date.today()
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, "json", raw_content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_url": MONETARY_AGGREGATES_URL, "form_id": MONETARY_AGGREGATES_FORM_ID,
        "row_code": row_code, "n_pages": len(raw_pages), "total_rows_all_codes": raw_pages[0]["totalRows"],
    })

    matching = [r for r in all_rows if r.get("row_code") == row_code]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows found with row_code={row_code!r} in formId=51",
                "EXPECTED: at least one row for this code (previously verified against the "
                "human-facing table at nationalbank.kz/ru/monetarybase/...)",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: re-verify the row_code mapping at {MONETARY_AGGREGATES_URL} "
                "and the human-facing page before trusting this indicator again.",
            ])
        )
    return matching, raw_content


def fetch_m2() -> tuple[list[dict], dict]:
    """M2 money supply. See ROW_CODE_M2 comment above for how the mapping was verified."""
    rows, _ = _fetch_monetary_aggregate_rows(ROW_CODE_M2, "M2")
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in rows]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={MONETARY_AGGREGATES_FORM_ID}",
        "dataset_id": "formId=51,row_code=4",
        "note": "report_date is the API's own field, observed to run about one month ahead "
                "of the corresponding column label on the human-facing NBK page -- not shifted here.",
    }
    return records, manifest


def fetch_m3() -> tuple[list[dict], dict]:
    """M3 money supply. See ROW_CODE_M3 comment above for how the mapping was verified."""
    rows, _ = _fetch_monetary_aggregate_rows(ROW_CODE_M3, "M3")
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in rows]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={MONETARY_AGGREGATES_FORM_ID}",
        "dataset_id": "formId=51,row_code=5",
        "note": "report_date is the API's own field, observed to run about one month ahead "
                "of the corresponding column label on the human-facing NBK page -- not shifted here.",
    }
    return records, manifest
