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


# row_code=1 "Денежная база (резервные деньги)" / row_code=2 "M0" / row_code=3 "M1".
# Verified live 2026-08-30 the same way as M2/M3: cross-referenced against the human-facing
# table's numbered rows and confirmed matching values (accounting for the same ~1-month
# report_date offset noted above).
ROW_CODE_MONETARY_BASE = "1"
ROW_CODE_M0 = "2"
ROW_CODE_M1 = "3"


def fetch_monetary_base() -> tuple[list[dict], dict]:
    """Monetary base (reserve money). row_code=1 -- see comment above ROW_CODE_MONETARY_BASE."""
    rows, _ = _fetch_monetary_aggregate_rows(ROW_CODE_MONETARY_BASE, "MONETARY_BASE")
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in rows]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={MONETARY_AGGREGATES_FORM_ID}",
        "dataset_id": "formId=51,row_code=1",
        "note": "report_date runs about one month ahead of the human page's column label -- not shifted here.",
    }
    return records, manifest


def fetch_m0() -> tuple[list[dict], dict]:
    """M0 -- cash in circulation outside the banking system. row_code=2."""
    rows, _ = _fetch_monetary_aggregate_rows(ROW_CODE_M0, "M0")
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in rows]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={MONETARY_AGGREGATES_FORM_ID}",
        "dataset_id": "formId=51,row_code=2",
        "note": "report_date runs about one month ahead of the human page's column label -- not shifted here.",
    }
    return records, manifest


def fetch_m1() -> tuple[list[dict], dict]:
    """M1. row_code=3."""
    rows, _ = _fetch_monetary_aggregate_rows(ROW_CODE_M1, "M1")
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in rows]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={MONETARY_AGGREGATES_FORM_ID}",
        "dataset_id": "formId=51,row_code=3",
        "note": "report_date runs about one month ahead of the human page's column label -- not shifted here.",
    }
    return records, manifest


# formId=34, "International Reserves and foreign currency assets of the National Fund of
# Republic of Kazakhstan" -- found 2026-08-30 via GET /api/v1/data/categories (category
# "monetary" -> subcategory "monetary statistics"). Confirmed live: total gross reserves
# (no subtype) = sum of its own subtype breakdown (monetary gold + assets in CFC) to the
# cent for a sample date, confirming this is a real total+breakdown structure, not
# fabricated. Same endpoint conveniently also carries National Fund FX assets as a
# `subtype`, discovered while investigating reserves -- solves both in one form.
RESERVES_NATFUND_FORM_ID = "34"


def _fetch_reserves_natfund_rows() -> list[dict]:
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": RESERVES_NATFUND_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1
    return all_rows


def fetch_fx_reserves() -> tuple[list[dict], dict]:
    """Gross international reserves (FX + gold), USD million, monthly.
    Verified live 2026-08-30: class_type='gross international reserves' with no
    `subtype` key is the total row; rows WITH a subtype ('monetary gold',
    'assets in cfc') are its breakdown, confirmed to sum to the total for a
    sample date.
    """
    rows = _fetch_reserves_natfund_rows()
    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "FX_RESERVES", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "FX_RESERVES", today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={RESERVES_NATFUND_FORM_ID}",
    })

    matching = [r for r in rows if r.get("class_type") == "gross international reserves" and "subtype" not in r]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/FX_RESERVES",
                "WHAT CHANGED: no total row found (class_type='gross international reserves', no subtype)",
                f"ACTION REQUIRED: inspect formId={RESERVES_NATFUND_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={RESERVES_NATFUND_FORM_ID}",
        "dataset_id": f"formId={RESERVES_NATFUND_FORM_ID},class_type=gross_international_reserves",
        "note": "USD million. Gross reserves (monetary gold + FX assets), no breakdown by component.",
    }
    return records, manifest


def fetch_national_fund_assets() -> tuple[list[dict], dict]:
    """National Fund of Kazakhstan -- foreign currency assets, USD million, monthly.
    Same formId=34 as FX_RESERVES (see its docstring). Verified live 2026-08-30."""
    rows = _fetch_reserves_natfund_rows()
    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "NATIONAL_FUND_ASSETS", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "NATIONAL_FUND_ASSETS", today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={RESERVES_NATFUND_FORM_ID}",
    })

    matching = [r for r in rows if r.get("subtype") == "foreign currency assets of the national fund of kazakhstan"]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/NATIONAL_FUND_ASSETS",
                "WHAT CHANGED: no row found with subtype='foreign currency assets of the national fund of kazakhstan'",
                f"ACTION REQUIRED: inspect formId={RESERVES_NATFUND_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={RESERVES_NATFUND_FORM_ID}",
        "dataset_id": f"formId={RESERVES_NATFUND_FORM_ID},subtype=national_fund_fx_assets",
        "note": "USD million. Foreign currency assets of the National Fund of Kazakhstan (sovereign wealth fund).",
    }
    return records, manifest


# formId=299, "The real effective exchange rate (REER), The real exchange rate (RER),
# The nominal effective exchange rate (NEER)". Verified live 2026-08-30: unlike the
# bilateral 'Real exchange rate' category (which needs a fx_currency_pair), the
# 'Real effective exchange rate' and 'The nominal effective exchange rate' categories
# are already basket-wide indices with no currency-pair dimension -- clean single series,
# distinguished only by `subcategory` (Including / Excluding oil trade). Using "Including
# oil trade" as the primary series since oil dominates KZ's actual trade weights.
REER_NEER_FORM_ID = "299"


def _fetch_effective_rate_rows(category: str) -> list[dict]:
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": REER_NEER_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1
    return [r for r in all_rows if r.get("category") == category and r.get("subcategory") == "Including oil trade"]


def fetch_reer() -> tuple[list[dict], dict]:
    """Real effective exchange rate (REER) index, including oil trade in the basket weights."""
    rows = _fetch_effective_rate_rows("Real effective exchange rate")
    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "REER", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "REER", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={REER_NEER_FORM_ID}",
    })
    if not rows:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/REER",
                "WHAT CHANGED: no rows found for category='Real effective exchange rate', subcategory='Including oil trade'",
                f"ACTION REQUIRED: inspect formId={REER_NEER_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in rows], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={REER_NEER_FORM_ID}",
        "dataset_id": f"formId={REER_NEER_FORM_ID},category=REER,including_oil_trade",
        "note": "Index. 'Excluding oil trade' variant also exists on the same form but is not fetched here.",
    }
    return records, manifest


def fetch_neer() -> tuple[list[dict], dict]:
    """Nominal effective exchange rate (NEER) index, including oil trade in the basket weights."""
    rows = _fetch_effective_rate_rows("The nominal effective exchange rate")
    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "NEER", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "NEER", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={REER_NEER_FORM_ID}",
    })
    if not rows:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/NEER",
                "WHAT CHANGED: no rows found for category='The nominal effective exchange rate', subcategory='Including oil trade'",
                f"ACTION REQUIRED: inspect formId={REER_NEER_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in rows], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={REER_NEER_FORM_ID}",
        "dataset_id": f"formId={REER_NEER_FORM_ID},category=NEER,including_oil_trade",
        "note": "Index. 'Excluding oil trade' variant also exists on the same form but is not fetched here.",
    }
    return records, manifest


# formId=62, "Депозиты в депозитных организациях". Verified live 2026-08-30: row_code='1'
# is "Всего депозитов" (total deposits) -- confirmed both structurally (first/headline row
# on the human-facing table at
# https://nationalbank.kz/ru/depositoryorganizationsdeposits/depozity-v-depozitnyh-organizaciyah-)
# and numerically (row_code=1, report_date=2025-12-01 -> 44457125.21 matches the page's
# "11.25" column exactly, same ~1-month report_date offset as formId=51).
DEPOSITS_FORM_ID = "62"
ROW_CODE_DEPOSITS_TOTAL = "1"


def fetch_deposits_total() -> tuple[list[dict], dict]:
    """Total resident deposits (individuals + non-bank legal entities) in second-tier
    banks and NBK, excluding central government/interbank deposits. Million KZT, monthly."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": DEPOSITS_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "DEPOSITS_TOTAL", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "DEPOSITS_TOTAL", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={DEPOSITS_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("row_code") == ROW_CODE_DEPOSITS_TOTAL]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/DEPOSITS_TOTAL",
                f"WHAT CHANGED: no rows found with row_code={ROW_CODE_DEPOSITS_TOTAL!r}",
                f"ACTION REQUIRED: inspect formId={DEPOSITS_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={DEPOSITS_FORM_ID}",
        "dataset_id": f"formId={DEPOSITS_FORM_ID},row_code={ROW_CODE_DEPOSITS_TOTAL}",
        "note": "Million KZT. report_date runs about one month ahead of the human page's column label -- not shifted here.",
    }
    return records, manifest


# formId=353, "Абсолютные и относительные параметры внешнего долга" (Absolute and relative
# parameters of external debt), found 2026-08-30 via GET /api/v1/data/categories -> category
# "external sector" -> subcategory "external debt". Resolves the gap logged earlier as
# EXTERNAL_DEBT_NOT_CONNECTED (formIds 358/293 checked then had no clean total row): this
# form's ed_code='Absolute indicators - External debt' with period='quarter' is a genuinely
# pre-aggregated single headline total, 85 rows, one per quarter, 2005-Q2 onward, no other
# dimension to sum across. (period='Year' rows for the same dates/values also exist and are
# excluded here to avoid mixing two granularities of the same already-aggregated series.)
EXTERNAL_DEBT_FORM_ID = "353"


def fetch_external_debt() -> tuple[list[dict], dict]:
    """Total gross external debt (public + private), USD million, quarterly.
    Verified live 2026-08-30. See EXTERNAL_DEBT_FORM_ID comment for how the clean
    aggregate row was found after two prior forms (358, 293) turned out to have
    no total row at all."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": EXTERNAL_DEBT_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "EXTERNAL_DEBT", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "EXTERNAL_DEBT", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={EXTERNAL_DEBT_FORM_ID}",
    })

    matching = [r for r in all_rows
                if r.get("ed_code") == "Absolute indicators - External debt" and r.get("period") == "quarter"]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/EXTERNAL_DEBT",
                "WHAT CHANGED: no rows found with ed_code='Absolute indicators - External debt', period='quarter'",
                f"ACTION REQUIRED: inspect formId={EXTERNAL_DEBT_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={EXTERNAL_DEBT_FORM_ID}",
        "dataset_id": f"formId={EXTERNAL_DEBT_FORM_ID},ed_code=Absolute indicators - External debt,period=quarter",
        "note": "USD million. Gross external debt total (public + private), no further breakdown.",
    }
    return records, manifest


# formId=27, "Кредиты банковского сектора экономике - ставки" (loan-market category).
# Found 2026-08-30 via the same categories endpoint. Resolves LOANS_TO_ECONOMY's sibling
# gap for rates: unlike the raw loan-volume forms (4, 445, 488, 493 -- all checked this
# session, all pure microdata with zero aggregate rows), this rates form carries its own
# `agg_level` field, and agg_level='1' rows have every other dimension (maturity, purpose,
# region, subject_type, enterprise_type, funding_type, residency) null except currency --
# i.e. NBK's own pre-computed, currency-only-split weighted average. 'National currency' is
# used as the headline figure (matches how KZT-denominated rates are conventionally quoted
# in NBK's own commentary); the foreign-currency variant also exists at the same agg_level
# but is not fetched here.
LENDING_RATE_FORM_ID = "27"


def fetch_lending_rate() -> tuple[list[dict], dict]:
    """Weighted average lending rate, second-tier banks, national currency, %, monthly.
    Verified live 2026-08-30. See LENDING_RATE_FORM_ID comment for how the aggregate
    was found via the form's own agg_level field rather than summing raw microdata."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": LENDING_RATE_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "LENDING_RATE", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "LENDING_RATE", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={LENDING_RATE_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("agg_level") == "1" and r.get("currency") == "National currency"]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/LENDING_RATE",
                "WHAT CHANGED: no rows found with agg_level='1', currency='National currency'",
                f"ACTION REQUIRED: inspect formId={LENDING_RATE_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={LENDING_RATE_FORM_ID}",
        "dataset_id": f"formId={LENDING_RATE_FORM_ID},agg_level=1,currency=National currency",
        "note": "%. Weighted average lending rate, national-currency loans only, all other dimensions "
                "(maturity/purpose/region/subject/entity size/funding source) aggregated by NBK itself.",
    }
    return records, manifest


# formId=268, "Средневзвешенные ставки вознаграждения банков второго уровня по привлеченным
# депозитам" (deposit-market category). Found 2026-08-30 via the same categories endpoint.
# Unlike form 27, this one has no explicit agg_level field, but deposit_term and
# deposit_type both take a null value for some rows -- confirmed this null represents
# NBK's own "all terms"/"all types" aggregation (not missing data) by checking that,
# within a given agent+currency, exactly one row per report_date has both fields null.
# 'Individuals' + 'National currency' is used as the headline figure (retail KZT deposits,
# the rate conventionally cited in NBK commentary); the other 3 agent/currency combinations
# exist at the same aggregation level but are not fetched here.
DEPOSIT_RATE_FORM_ID = "268"


def fetch_deposit_rate() -> tuple[list[dict], dict]:
    """Weighted average deposit rate, second-tier banks, individuals, national currency,
    %, monthly. Verified live 2026-08-30. See DEPOSIT_RATE_FORM_ID comment for how the
    aggregate was found. Sanity check: sits below LENDING_RATE and below BASE_RATE for
    the same recent months -- the expected deposit < lending spread direction."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": DEPOSIT_RATE_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "DEPOSIT_RATE", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "DEPOSIT_RATE", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={DEPOSIT_RATE_FORM_ID}",
    })

    matching = [r for r in all_rows
                if r.get("deposit_term") is None and r.get("deposit_type") is None
                and r.get("agent") == "Individuals" and r.get("currency") == "National currency"]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/DEPOSIT_RATE",
                "WHAT CHANGED: no rows found with deposit_term=None, deposit_type=None, "
                "agent='Individuals', currency='National currency'",
                f"ACTION REQUIRED: inspect formId={DEPOSIT_RATE_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={DEPOSIT_RATE_FORM_ID}",
        "dataset_id": f"formId={DEPOSIT_RATE_FORM_ID},agent=Individuals,currency=National currency",
        "note": "%. Weighted average deposit rate, individuals, national-currency deposits only, "
                "all terms/types aggregated by NBK itself.",
    }
    return records, manifest


# TONIA (Tenge OverNight Index Average), interbank overnight rate. Found 2026-08-30 via
# GET /api/v1/data/indicators, the same small endpoint that backs the homepage's headline
# indicators widget (base rate, inflation target, annual inflation, TONIA) -- NOT one of the
# formId-keyed Open Data forms. Supports from/to query params for history, but only returns
# data from late February 2026 onward (a rolling window, not the full API's usual multi-year
# depth) -- confirmed by testing 2020 and 2015 date ranges, both empty. Documented as a real
# limitation, not treated as broken.
INDICATORS_URL = "https://data.nationalbank.kz/api/v1/data/indicators"


def fetch_tonia() -> tuple[list[dict], dict]:
    """TONIA overnight interbank rate, %, daily. Verified live 2026-08-30: 184
    rows, 2026-02-24 to 2026-08-30, no gaps in that window. Only a rolling
    ~6-month history is available from this endpoint -- do not assume deeper
    history exists."""
    resp = requests.get(INDICATORS_URL, headers=HEADERS,
                         params={"from": "2000-01-01", "to": date.today().isoformat()}, timeout=30)
    resp.raise_for_status()
    rows = resp.json()

    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "TONIA", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "TONIA", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": INDICATORS_URL,
    })

    matching = [r for r in rows if r.get("tonia") is not None]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/TONIA",
                "WHAT CHANGED: no rows with a non-null 'tonia' field",
                f"ACTION REQUIRED: inspect {INDICATORS_URL} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["date"], "value": float(r["tonia"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "daily",
        "source_url": INDICATORS_URL,
        "dataset_id": "indicators-widget,field=tonia",
        "note": "%. Only a rolling ~6-month history is available from this endpoint -- do not "
                "assume deeper history exists; a gap in earlier years is expected, not a bug.",
    }
    return records, manifest


# formId=470, "Operations of the National fund and financial instruments of kazakhstani
# issuers". Found 2026-08-30 via GET /api/v1/data/categories. data_type='Transfers from
# National fund' is a clean single-dimension monthly series (30 rows, all unique dates,
# 2024-02 to 2026-07), no further breakdown to sum across.
NATIONAL_FUND_OPS_FORM_ID = "470"
NATIONAL_FUND_TRANSFERS_DATA_TYPE = "Transfers from National fund"


def fetch_national_fund_transfers() -> tuple[list[dict], dict]:
    """Transfers from the National Fund to the republican budget, billion KZT,
    monthly. Verified live 2026-08-30: 30 rows, 2024-02 to 2026-07, values
    230-600 bln KZT/month -- plausible scale given Kazakhstan's guaranteed
    annual transfer runs in the low trillions of KZT."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": NATIONAL_FUND_OPS_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "NATIONAL_FUND_TRANSFERS", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "NATIONAL_FUND_TRANSFERS", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={NATIONAL_FUND_OPS_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("data_type") == NATIONAL_FUND_TRANSFERS_DATA_TYPE]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/NATIONAL_FUND_TRANSFERS",
                f"WHAT CHANGED: no rows found with data_type={NATIONAL_FUND_TRANSFERS_DATA_TYPE!r}",
                f"ACTION REQUIRED: inspect formId={NATIONAL_FUND_OPS_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={NATIONAL_FUND_OPS_FORM_ID}",
        "dataset_id": f"formId={NATIONAL_FUND_OPS_FORM_ID},data_type={NATIONAL_FUND_TRANSFERS_DATA_TYPE}",
        "note": "Billion KZT.",
    }
    return records, manifest


# formId=35, "Results of trades on KASE". Found 2026-08-30 via the same categories endpoint.
# Multi-dimensional (type x currency), but picking a single currency ('US dollars') and a
# single type ('Volume of trade on KASE for the period (units of currency)') gives a clean,
# unambiguous single series -- no aggregation across categories needed or attempted.
KASE_FORM_ID = "35"
KASE_USD_VOLUME_TYPE = "Volume of trade on KASE for the period (units of currency)"
KASE_USD_CURRENCY = "US dollars"


def fetch_kase_usd_volume() -> tuple[list[dict], dict]:
    """USD/KZT trading volume on KASE (Kazakhstan Stock Exchange), USD,
    monthly. Verified live 2026-08-30: 20 rows, 2025-01 to 2026-08, values
    $6.7-9.7 billion/month -- plausible for Kazakhstan's FX market."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": KASE_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "KASE_USD_VOLUME", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "KASE_USD_VOLUME", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={KASE_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("type") == KASE_USD_VOLUME_TYPE and r.get("currency") == KASE_USD_CURRENCY]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/KASE_USD_VOLUME",
                f"WHAT CHANGED: no rows found with type={KASE_USD_VOLUME_TYPE!r}, currency={KASE_USD_CURRENCY!r}",
                f"ACTION REQUIRED: inspect formId={KASE_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={KASE_FORM_ID}",
        "dataset_id": f"formId={KASE_FORM_ID},type={KASE_USD_VOLUME_TYPE},currency={KASE_USD_CURRENCY}",
        "note": "USD. Trading volume for the USD/KZT pair specifically, not total KASE FX turnover "
                "across all currency pairs.",
    }
    return records, manifest


# formId=408, "International remittances by IMTS (by amounts)". Found 2026-08-30 via the
# same categories endpoint. Multi-dimensional (imts=money transfer system x
# money_transfer_sign=sent/received), but imts='Total' is NBK's own clean pre-aggregated row
# across all money transfer systems -- confirmed present and usable, unlike the loan/rate
# forms that had no such row at all.
REMITTANCES_FORM_ID = "408"


def _fetch_remittances(sign: str, indicator_id: str) -> tuple[list[dict], dict]:
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": REMITTANCES_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, "json", content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={REMITTANCES_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("imts") == "Total" and r.get("money_transfer_sign") == sign]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows found with imts='Total', money_transfer_sign={sign!r}",
                f"ACTION REQUIRED: inspect formId={REMITTANCES_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={REMITTANCES_FORM_ID}",
        "dataset_id": f"formId={REMITTANCES_FORM_ID},imts=Total,money_transfer_sign={sign}",
        "note": "Million KZT. Total across all international money transfer systems (MoneyGram, "
                "Unistream, Contact, Golden Crown, UPT, and others), via IMTS operators only -- "
                "does not capture remittances through other channels (e.g. bank wire transfers).",
    }
    return records, manifest


def fetch_remittances_sent() -> tuple[list[dict], dict]:
    """Outbound international money transfers via IMTS operators, million
    KZT, monthly. Verified live 2026-08-30: 58 rows, all unique dates,
    ~54-65 bln KZT/month recently."""
    return _fetch_remittances("money transfers sent", "REMITTANCES_SENT")


def fetch_remittances_received() -> tuple[list[dict], dict]:
    """Inbound international money transfers via IMTS operators, million
    KZT, monthly. Verified live 2026-08-30: 58 rows, all unique dates,
    ~15-18 bln KZT/month recently (consistently below REMITTANCES_SENT)."""
    return _fetch_remittances("money transfers received", "REMITTANCES_RECEIVED")
