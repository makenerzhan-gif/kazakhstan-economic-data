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


# formId=305, "Inflation expectations". Found 2026-08-30 via the same categories endpoint.
# Single-dimension already (only one category value present: 'Inflation expectations') --
# no aggregation needed or attempted.
INFLATION_EXPECTATIONS_FORM_ID = "305"


def fetch_inflation_expectations() -> tuple[list[dict], dict]:
    """Consumer inflation expectations (survey-based), %, monthly. Verified
    live 2026-08-30: 126 rows, 2016-01 to 2026-07, all unique dates, recent
    values ~12-15% -- plausible given current actual annual inflation
    (~10.2%, per NBK's own homepage figure)."""
    resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                         params={"formId": INFLATION_EXPECTATIONS_FORM_ID, "page": "0", "pageSize": "500"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rows = data["rows"]

    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "INFLATION_EXPECTATIONS", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "INFLATION_EXPECTATIONS", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={INFLATION_EXPECTATIONS_FORM_ID}",
    })

    if not rows:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/INFLATION_EXPECTATIONS",
                "WHAT CHANGED: zero rows returned",
                f"ACTION REQUIRED: inspect formId={INFLATION_EXPECTATIONS_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in rows], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={INFLATION_EXPECTATIONS_FORM_ID}",
        "dataset_id": f"formId={INFLATION_EXPECTATIONS_FORM_ID}",
        "note": "%. Survey-based expected inflation over the next 12 months.",
    }
    return records, manifest


# formId=339, "The Business Activity Index" -- NBK's own PMI-style survey indicator.
# Multi-dimensional by sector (Trade, Mining, Construction, Service, Production), but
# index_type='Business activity index by economy' is NBK's own clean pre-aggregated
# headline row across all sectors.
BUSINESS_ACTIVITY_FORM_ID = "339"
BUSINESS_ACTIVITY_TOTAL_TYPE = "Business activity index by economy"


def fetch_business_activity_index() -> tuple[list[dict], dict]:
    """Business Activity Index (economy-wide, survey-based, ~50 = neutral),
    monthly. Verified live 2026-08-30: 79 rows, all unique dates, recent
    values ~49.5-51.6 -- hovering near the neutral 50 mark, plausible."""
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": BUSINESS_ACTIVITY_FORM_ID, "page": str(page), "pageSize": "500"},
                             timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data["rows"])
        if len(all_rows) >= data["totalRows"]:
            break
        page += 1

    today = date.today()
    content = json.dumps(all_rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "BUSINESS_ACTIVITY_INDEX", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "BUSINESS_ACTIVITY_INDEX", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={BUSINESS_ACTIVITY_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("index_type") == BUSINESS_ACTIVITY_TOTAL_TYPE]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/BUSINESS_ACTIVITY_INDEX",
                f"WHAT CHANGED: no rows found with index_type={BUSINESS_ACTIVITY_TOTAL_TYPE!r}",
                f"ACTION REQUIRED: inspect formId={BUSINESS_ACTIVITY_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={BUSINESS_ACTIVITY_FORM_ID}",
        "dataset_id": f"formId={BUSINESS_ACTIVITY_FORM_ID},index_type={BUSINESS_ACTIVITY_TOTAL_TYPE}",
        "note": "Index, ~50 = neutral (no change in business activity vs. prior period).",
    }
    return records, manifest


# formId=303, "Non-cash payments". Found 2026-08-30 via the categories endpoint. Already
# single-dimension (only one class_1 value present: 'Non-cash payments of the population')
# -- no aggregation needed or attempted. Short series (5 annual rows) but real and clean.
NON_CASH_PAYMENTS_FORM_ID = "303"


def fetch_non_cash_payments_share() -> tuple[list[dict], dict]:
    """Share of non-cash payments in total household payments, %, annual.
    Verified live 2026-08-30: 5 rows (2022-2026), all unique dates, rising
    from 73.6% (2022) to 89.0% (2025) before dipping to 82.9% (2026,
    presumably a partial-year figure) -- plausible trend for a rapidly
    digitalizing payments market."""
    resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                         params={"formId": NON_CASH_PAYMENTS_FORM_ID, "page": "0", "pageSize": "500"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    rows = data["rows"]

    today = date.today()
    content = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    raw_store.save_raw_bytes(SOURCE, "NON_CASH_PAYMENTS_SHARE", today, "json", content)
    raw_store.write_download_manifest(SOURCE, "NON_CASH_PAYMENTS_SHARE", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={NON_CASH_PAYMENTS_FORM_ID}",
    })

    if not rows:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/NON_CASH_PAYMENTS_SHARE",
                "WHAT CHANGED: zero rows returned",
                f"ACTION REQUIRED: inspect formId={NON_CASH_PAYMENTS_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in rows], key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={NON_CASH_PAYMENTS_FORM_ID}",
        "dataset_id": f"formId={NON_CASH_PAYMENTS_FORM_ID}",
        "note": "%. From-the-beginning-of-the-year figure as of each report_date.",
    }
    return records, manifest


# formId=314, "Financial Soundness Indicators" -- IMF-standard FSI series. Found 2026-08-30
# via the categories endpoint. Multi-dimensional (subject x indicator x sub_subject), but
# subject='Core FSIs for Deposit takers' + a specific `indicator` value gives a clean,
# already-computed ratio -- no aggregation needed, NBK computes these ratios itself.
FSI_FORM_ID = "314"
FSI_SUBJECT = "Core FSIs for Deposit takers"


def _fetch_fsi(indicator_name: str, indicator_id: str) -> tuple[list[dict], dict]:
    all_rows: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": FSI_FORM_ID, "page": str(page), "pageSize": "500"},
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
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{MONETARY_AGGREGATES_URL}?formId={FSI_FORM_ID}",
    })

    matching = [r for r in all_rows if r.get("indicator") == indicator_name and r.get("subject") == FSI_SUBJECT]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows found with indicator={indicator_name!r}, subject={FSI_SUBJECT!r}",
                f"ACTION REQUIRED: inspect formId={FSI_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )
    records = sorted([{"date": r["report_date"], "value": float(r["amount"])} for r in matching], key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={FSI_FORM_ID}",
        "dataset_id": f"formId={FSI_FORM_ID},subject={FSI_SUBJECT},indicator={indicator_name}",
        "note": "%. Banking-sector Financial Soundness Indicator, second-tier banks (deposit takers).",
    }
    return records, manifest


def fetch_capital_adequacy_ratio() -> tuple[list[dict], dict]:
    """Bank capital adequacy ratio (regulatory capital to risk-weighted
    assets), %, quarterly. Verified live 2026-08-30: 18 rows, all unique
    dates, ~21.4-21.5% recently -- well above the Basel minimum (~8%),
    indicating a well-capitalized banking sector."""
    return _fetch_fsi("Regulatory capital to risk-weighted assets", "CAPITAL_ADEQUACY_RATIO")


def fetch_npl_ratio() -> tuple[list[dict], dict]:
    """Non-performing loans ratio (NPLs to total gross loans), %, quarterly.
    Verified live 2026-08-30: 18 rows, all unique dates, ~2.9-3.3% recently
    -- a healthy level for a banking system."""
    return _fetch_fsi("Nonperforming loans to total gross loans", "NPL_RATIO")


def fetch_bank_roa() -> tuple[list[dict], dict]:
    """Bank return on assets (ROA), %, quarterly. Found 2026-08-31 in the
    same formId=314 Financial Soundness Indicators form already connected
    for CAPITAL_ADEQUACY_RATIO/NPL_RATIO/LOANS_TO_ECONOMY -- checked its
    other `indicator` values under the same subject and found this is one
    of many additional clean, single-valued (per-quarter) ratio indicators
    present. Verified live: 18 rows, all unique dates, ~4.95-5.21% recently
    -- consistent with the same 2024-Q2 data-currency cutoff as every other
    indicator sourced from this specific NBK form/subject (not a new
    staleness issue introduced here)."""
    return _fetch_fsi("Return on assets", "BANK_ROA")


def fetch_bank_roe() -> tuple[list[dict], dict]:
    """Bank return on equity (ROE), %, quarterly. Same form/subject as
    BANK_ROA. Verified live 2026-08-31: 18 rows, all unique dates,
    ~31.7-36.8% recently -- high but plausible for Kazakhstan's banking
    sector, known for wide margins."""
    return _fetch_fsi("Return on equity", "BANK_ROE")


def fetch_loans_to_economy() -> tuple[list[dict], dict]:
    """Total gross loans, second-tier banks (deposit takers), million KZT,
    quarterly. Resolves the LOANS_TO_ECONOMY gap logged as not_connected in
    an earlier batch (formIds 4/445/488/493 -- raw loan microdata with zero
    aggregate rows in any of them). Found this batch by going back to the
    SAME Financial Soundness Indicators form (314) already connected for
    CAPITAL_ADEQUACY_RATIO/NPL_RATIO and checking its other `indicator`
    values -- 'Total gross loans' is NBK's own already-aggregated headline
    figure, no summation needed. Verified live 2026-08-30: 18 rows, all
    unique dates, ~25.9-30.3 trillion KZT (2023-2024) -- a plausible scale
    for Kazakhstan's total bank credit stock. Note the source unit is
    thousand KZT; converted to million KZT here for consistency with other
    KZT-denominated indicators in this project."""
    records, manifest = _fetch_fsi("Total gross loans", "LOANS_TO_ECONOMY")
    for r in records:
        r["value"] = r["value"] / 1000.0
    manifest["note"] = (
        "Million KZT (converted from the source's thousand-KZT unit). Banking-sector "
        "Financial Soundness Indicator, second-tier banks (deposit takers)."
    )
    return records, manifest


# ---------------------------------------------------------------------------
# FDI_NET_INFLOW: found 2026-08-31 via GET /api/v1/data/categories, category
# "external sector" -> "balance of payments" -> formId=337 "Direct
# investments according to the directional principle: flows for the
# period" -- the standard IMF BPM6-style "directional principle" net FDI
# flow series (as opposed to the many gross/asset-liability/by-country/by-
# sector variants also present in this category, e.g. formIds 286-335,
# 400-403 -- those give geographic/sectoral breakdowns of the same
# underlying flows, not picked here). Row matched by the exact code
# 'Direct investment in reporting economy (net inflow)' combined with
# direction_code='Direct investment in Kazakhstan' (this exact code string
# also appears once with direction_code=None, labeled 'Net direct
# investment' -- a different, netted-against-outflow headline figure, not
# used here to keep this indicator as the standard BPM6 "net inflow"
# concept specifically). Verified live 2026-08-31 with full pagination: 85
# quarterly points, 2005-Q2 through 2026-Q2, ranging from USD -2,495.6
# million (2026-Q1, a net-disinvestment quarter) to several USD 4,000+
# million quarters around 2008-2009 -- genuinely volatile, including
# negative quarters, a real and expected pattern for BPM6 net FDI flows
# (loan repayments/divestments can exceed new investment in a given
# quarter), not a data error.
# ---------------------------------------------------------------------------
FDI_FORM_ID = "337"
FDI_CODE = "Direct investment in reporting economy (net inflow)"
FDI_DIRECTION = "Direct investment in Kazakhstan"


def _fetch_nbk_form_paginated(form_id: str, indicator_id: str) -> list[dict]:
    """Shared full-pagination fetcher for any data.nationalbank.kz open-data
    form. Loops page=0,1,2,... until all totalRows are collected (verified
    live this session that page=0 and page=1 are NOT full duplicates at
    production pageSize=500 -- adjacent pages just share one harmless
    overlapping boundary row -- see the FDI_NET_INFLOW/GOV_SECURITIES_MEUKAM
    module comments for the investigation that ruled out a data-loss bug
    here). Saves every page as the raw archive and returns the flat row
    list; callers filter for their own target row(s) and raise
    StructuralChangeError themselves if nothing matches, since what
    "matching" means is form-specific.
    """
    all_rows: list[dict] = []
    raw_pages: list[dict] = []
    page = 0
    while True:
        resp = requests.get(MONETARY_AGGREGATES_URL, headers=HEADERS,
                             params={"formId": form_id, "page": str(page), "pageSize": "500"},
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
        "source_url": MONETARY_AGGREGATES_URL, "form_id": form_id,
        "n_pages": len(raw_pages), "total_rows": raw_pages[0]["totalRows"],
    })
    return all_rows


def fetch_fdi_net_inflow() -> tuple[list[dict], dict]:
    """Net foreign direct investment inflow to Kazakhstan, BPM6 directional
    principle, USD million, quarterly. See FDI_FORM_ID module comment above
    for how the row was disambiguated from several related FDI series in
    the same form."""
    all_rows = _fetch_nbk_form_paginated(FDI_FORM_ID, "FDI_NET_INFLOW")

    matching = [r for r in all_rows if r.get("code") == FDI_CODE and r.get("direction_code") == FDI_DIRECTION]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/FDI_NET_INFLOW",
                f"WHAT CHANGED: no rows found with code={FDI_CODE!r}, direction_code={FDI_DIRECTION!r} in formId={FDI_FORM_ID}",
                "EXPECTED: the standard BPM6 net-inflow row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={FDI_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={FDI_FORM_ID}",
        "dataset_id": f"formId={FDI_FORM_ID},code={FDI_CODE},direction={FDI_DIRECTION}",
        "note": "USD million. Net foreign direct investment inflow to Kazakhstan (BPM6 "
                "directional principle) -- from the balance of payments financial account, "
                "not the same concept as domestic fixed-capital investment (INVESTMENT).",
    }
    return records, manifest


# ---------------------------------------------------------------------------
# GOV_SECURITIES_MEUKAM: found 2026-08-31 via the same categories browse,
# category "securities" -> formId=430 "Structure of national currency
# denominated Government Securities in Circulation" -- the closest thing to
# a "domestic government securities market" aggregate available (a
# previously-noted gap: earlier research into formIds 16/17/430 concluded
# "no aggregate found"). Re-checked live this session: formId=430 gives an
# END-OF-PERIOD OUTSTANDING STOCK (not a flow, unlike formIds 16/17 which
# are auction/secondary-market transaction VOLUMES) broken down by
# instrument type (14 distinct sec_type values: МЕККАМ, МЕUКАМ, МЕОКАМ,
# METIKAM, Municipal Government Securities, Notes of NBK, etc.) -- but,
# confirmed by listing every sec_type value across the full series, there
# is genuinely NO "Total" row provided by the source. Rather than fabricate
# a total by summing components ourselves (inconsistent with this
# project's practice of not computing aggregates the source agency doesn't
# itself publish -- see POVERTY_HEADCOUNT's notes for the same principle
# applied to a ratio), this connects only the single largest, most
# economically meaningful component -- 'МЕUКАМ' (medium/long-term treasury
# bonds), which alone is ~22.4 trillion KZT as of 2026-08, an order of
# magnitude larger than every other instrument type combined. Labeled
# precisely as this one instrument, not as "total government securities
# market", to avoid overstating what this actually measures. Verified live
# 2026-08-31 with full pagination: 199 monthly points, 2010-02 through
# 2026-08, all unique dates, million KZT.
# ---------------------------------------------------------------------------
GOV_SECURITIES_FORM_ID = "430"
GOV_SECURITIES_MEUKAM_TYPE = "МЕUКАМ"


def fetch_gov_securities_meukam() -> tuple[list[dict], dict]:
    """MEUKAM (medium/long-term treasury bonds) outstanding, million KZT,
    end of month. See GOV_SECURITIES_FORM_ID module comment above for why
    this single instrument was picked over a fabricated cross-instrument
    total."""
    all_rows = _fetch_nbk_form_paginated(GOV_SECURITIES_FORM_ID, "GOV_SECURITIES_MEUKAM")

    matching = [r for r in all_rows if r.get("sec_type") == GOV_SECURITIES_MEUKAM_TYPE]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/GOV_SECURITIES_MEUKAM",
                f"WHAT CHANGED: no rows found with sec_type={GOV_SECURITIES_MEUKAM_TYPE!r} in formId={GOV_SECURITIES_FORM_ID}",
                "EXPECTED: the МЕUКАМ instrument-type row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={GOV_SECURITIES_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={GOV_SECURITIES_FORM_ID}",
        "dataset_id": f"formId={GOV_SECURITIES_FORM_ID},sec_type={GOV_SECURITIES_MEUKAM_TYPE}",
        "note": "Million KZT, end of month. МЕUКАМ (medium/long-term treasury bonds) outstanding "
                "-- the single largest domestic government securities instrument type, NOT a "
                "total across all instrument types (the source publishes no such total; other "
                "types include МЕККАМ, МЕОКАМ, METIKAM, Municipal Government Securities, Notes "
                "of NBK -- the latter is a central-bank sterilization instrument, not strictly "
                "a government security).",
    }
    return records, manifest


# ---------------------------------------------------------------------------
# IIP_NET / IIP_ASSETS / IIP_LIABILITIES: found 2026-08-31 via GET
# /api/v1/data/categories -> "external sector" -> "international investment
# position" -> formId=309 "International Investment Position of Kazakhstan:
# standard presentation". This form has 16 classification dimensions
# (sector, instrument class x4 sub-levels, term type, etc.) for its detailed
# breakdown rows, but three completely UNCLASSIFIED headline rows also exist
# per period: attribute_code='Net International Investment Position' (no
# class_type_code at all), and attribute_code='Assets'/'Liabilities' each
# paired with a matching class_type_code of the same name and nothing else
# set -- found by filtering the full row set for entries with every
# classification field empty except these two, which left exactly 3 unique
# combinations. Verified live: Assets - Liabilities = Net to the cent for a
# sample quarter (160,536.11 - 232,516.43 = -71,980.32, 2021-Q1) -- confirms
# these are genuinely the top-level aggregates, not a coincidence. 22
# quarterly points each, 2021-Q1 through 2026-Q1 (a shorter history than
# most other NBK indicators -- this presentation format doesn't appear to
# extend further back on this endpoint), USD million.
# ---------------------------------------------------------------------------
IIP_FORM_ID = "309"
IIP_NET_ATTRIBUTE = "Net International Investment Position"
IIP_ASSETS_ATTRIBUTE = "Assets"
IIP_LIABILITIES_ATTRIBUTE = "Liabilities"


def _fetch_iip_row(attribute: str, indicator_id: str, note: str) -> tuple[list[dict], dict]:
    all_rows = _fetch_nbk_form_paginated(IIP_FORM_ID, indicator_id)

    matching = [r for r in all_rows if r.get("attribute_code") == attribute
                and r.get("class_type_code") in (None, attribute)
                and not r.get("sector_code") and not r.get("instrument_class_code")
                and not r.get("functional_category_code")]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no unclassified rows found with attribute_code={attribute!r} in formId={IIP_FORM_ID}",
                "EXPECTED: the top-level unclassified aggregate row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={IIP_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={IIP_FORM_ID}",
        "dataset_id": f"formId={IIP_FORM_ID},attribute_code={attribute}",
        "note": note,
    }
    return records, manifest


def fetch_iip_net() -> tuple[list[dict], dict]:
    """Net International Investment Position of Kazakhstan, USD million,
    quarterly (foreign assets minus foreign liabilities). Negative = net
    external liability position (typical for an FDI-heavy emerging
    market)."""
    return _fetch_iip_row(
        IIP_NET_ATTRIBUTE, "IIP_NET",
        "USD million. Net International Investment Position (total foreign assets held by "
        "Kazakhstan residents minus total foreign liabilities owed by Kazakhstan residents). "
        "Negative values indicate a net external liability position.",
    )


def fetch_iip_assets() -> tuple[list[dict], dict]:
    """Total foreign assets held by Kazakhstan residents, USD million,
    quarterly (IIP asset side)."""
    return _fetch_iip_row(
        IIP_ASSETS_ATTRIBUTE, "IIP_ASSETS",
        "USD million. Total foreign assets held by Kazakhstan residents (International "
        "Investment Position, asset side).",
    )


def fetch_iip_liabilities() -> tuple[list[dict], dict]:
    """Total foreign liabilities owed by Kazakhstan residents, USD million,
    quarterly (IIP liability side)."""
    return _fetch_iip_row(
        IIP_LIABILITIES_ATTRIBUTE, "IIP_LIABILITIES",
        "USD million. Total foreign liabilities owed by Kazakhstan residents (International "
        "Investment Position, liability side).",
    )


# ---------------------------------------------------------------------------
# CURRENT_ACCOUNT_BALANCE: found 2026-08-31 via GET /api/v1/data/categories
# -> "external sector" -> "balance of payments" -> formId=324 "Current
# account of the balance of payments". Same shape as the IIP forms above:
# many classified breakdown rows (by sector, instrument, transaction type),
# plus one completely unclassified headline row per quarter -- code='Current
# account', account_type_code='Current account', every other classification
# field empty -- was the very first row returned by the API, no search
# needed. Verified live: 24 quarterly points, 2020-Q2 through 2026-Q2, USD
# million, recently negative (e.g. -5,180.4 in 2026-Q1) -- a current account
# deficit, a plausible and well-known pattern for Kazakhstan given large
# FDI-related income outflows even alongside a goods trade surplus.
# ---------------------------------------------------------------------------
CURRENT_ACCOUNT_FORM_ID = "324"
CURRENT_ACCOUNT_CODE = "Current account"


def fetch_current_account_balance() -> tuple[list[dict], dict]:
    """Current account balance of the balance of payments, USD million,
    quarterly. Negative = deficit."""
    all_rows = _fetch_nbk_form_paginated(CURRENT_ACCOUNT_FORM_ID, "CURRENT_ACCOUNT_BALANCE")

    matching = [r for r in all_rows if r.get("code") == CURRENT_ACCOUNT_CODE
                and r.get("account_type_code") == CURRENT_ACCOUNT_CODE
                and not r.get("instrument_type_code") and not r.get("sector_economy_type_code")]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/CURRENT_ACCOUNT_BALANCE",
                f"WHAT CHANGED: no unclassified rows found with code={CURRENT_ACCOUNT_CODE!r} in formId={CURRENT_ACCOUNT_FORM_ID}",
                "EXPECTED: the top-level unclassified current-account-balance row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={CURRENT_ACCOUNT_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={CURRENT_ACCOUNT_FORM_ID}",
        "dataset_id": f"formId={CURRENT_ACCOUNT_FORM_ID},code={CURRENT_ACCOUNT_CODE}",
        "note": "USD million. Current account balance of the balance of payments. Negative "
                "values indicate a deficit.",
    }
    return records, manifest


# ---------------------------------------------------------------------------
# PENSION_FUND_ASSETS: found 2026-08-31 in formId=25 "Information on the
# volume of pension savings and the number of individual pension accounts
# of contributors" (category "financial sector" -> pension funds). Most
# rows in this form are receipts/disposals FLOWS (contributions, payouts,
# fees) broken down by class_subtype1/2/3, plus a "Cost of one conventional
# unit of pension assets" NAV-per-unit series and an account-count series --
# but under class_type='Pension savings' specifically, one row per month has
# every class_subtype field empty: the total STOCK of pension savings held
# by Kazakhstan's Unified Accumulative Pension Fund (UAPF/ЕНПФ), roughly
# consistent with (though not exactly equal to, likely a small residual
# component not broken out) the sum of its own compulsory/voluntary/
# compulsory-professional sub-rows for the same date. Verified live: 43
# unique monthly dates, 2023-01 through 2026-08, thousand KZT -- 27.07
# trillion KZT as of 2026-08, a plausible scale for Kazakhstan's national
# pension fund (one of the country's largest institutional investors).
# ---------------------------------------------------------------------------
PENSION_FUND_FORM_ID = "25"
PENSION_FUND_CLASS_TYPE = "Pension savings"


def fetch_pension_fund_assets() -> tuple[list[dict], dict]:
    """Total pension savings held by Kazakhstan's Unified Accumulative
    Pension Fund (UAPF/ЕНПФ), million KZT, end of month."""
    all_rows = _fetch_nbk_form_paginated(PENSION_FUND_FORM_ID, "PENSION_FUND_ASSETS")

    matching = [r for r in all_rows if r.get("class_type") == PENSION_FUND_CLASS_TYPE
                and not r.get("class_subtype1") and not r.get("class_subtype2") and not r.get("class_subtype3")]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/PENSION_FUND_ASSETS",
                f"WHAT CHANGED: no unclassified rows found with class_type={PENSION_FUND_CLASS_TYPE!r} in formId={PENSION_FUND_FORM_ID}",
                "EXPECTED: the top-level unclassified pension-savings total row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={PENSION_FUND_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"]) / 1000.0} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={PENSION_FUND_FORM_ID}",
        "dataset_id": f"formId={PENSION_FUND_FORM_ID},class_type={PENSION_FUND_CLASS_TYPE}",
        "note": "Million KZT (converted from the source's thousand-KZT unit). Total pension "
                "savings held by Kazakhstan's Unified Accumulative Pension Fund (UAPF/ЕНПФ), "
                "end of month.",
    }
    return records, manifest


# ---------------------------------------------------------------------------
# INSURANCE_PREMIUMS_GENERAL / INSURANCE_PREMIUMS_LIFE: found 2026-08-31 in
# formId=132 "Total statement on insurance premiums of insurance
# (reinsurance) organizations" (category "financial sector" -> insurance).
# Row matched: pnl_subtype='Insurance premiums accepted under insurance
# contracts' AND insurance_type='Total' (this dimension also has
# 'Compulsory insurance'/'Voluntary personal insurance'/'Voluntary property
# insurance' sub-values, correctly excluded) AND no residency filter set
# (the residency dimension separately breaks the same total into
# Residents/Non-residents sub-rows). insurance_org_type has only two
# values, 'General' and 'Life' (general/non-life insurers vs life
# insurers) -- NO combined-total value exists across this dimension, so
# rather than fabricate a General+Life sum ourselves, this connects both
# as separate, honestly-labeled indicators. Verified live with full
# pagination: 31 unique monthly dates each, 2023-02 through 2026-07,
# thousand KZT.
# ---------------------------------------------------------------------------
INSURANCE_PREMIUMS_FORM_ID = "132"
INSURANCE_PREMIUMS_PNL_SUBTYPE = "Insurance premiums accepted under insurance contracts"


def _fetch_insurance_premiums(org_type: str, indicator_id: str, note: str) -> tuple[list[dict], dict]:
    all_rows = _fetch_nbk_form_paginated(INSURANCE_PREMIUMS_FORM_ID, indicator_id)

    matching = [r for r in all_rows if r.get("pnl_subtype") == INSURANCE_PREMIUMS_PNL_SUBTYPE
                and r.get("insurance_type") == "Total" and r.get("insurance_org_type") == org_type
                and not r.get("residency")]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no unclassified-residency rows found with pnl_subtype={INSURANCE_PREMIUMS_PNL_SUBTYPE!r}, "
                f"insurance_type='Total', insurance_org_type={org_type!r} in formId={INSURANCE_PREMIUMS_FORM_ID}",
                "EXPECTED: the top-level total-premiums row for this organization type",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={INSURANCE_PREMIUMS_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"]) / 1000.0} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={INSURANCE_PREMIUMS_FORM_ID}",
        "dataset_id": f"formId={INSURANCE_PREMIUMS_FORM_ID},insurance_org_type={org_type},insurance_type=Total",
        "note": note,
    }
    return records, manifest


def fetch_insurance_premiums_general() -> tuple[list[dict], dict]:
    """Total insurance premiums accepted, general (non-life) insurance
    organizations, million KZT, monthly (year-to-date cumulative within
    each calendar year, per the source's own reporting convention)."""
    return _fetch_insurance_premiums(
        "General", "INSURANCE_PREMIUMS_GENERAL",
        "Million KZT (converted from the source's thousand-KZT unit). Total insurance "
        "premiums accepted under insurance and reinsurance contracts, GENERAL (non-life) "
        "insurance organizations. Not the same total as INSURANCE_PREMIUMS_LIFE -- the "
        "source provides no combined General+Life aggregate.",
    )


def fetch_insurance_premiums_life() -> tuple[list[dict], dict]:
    """Total insurance premiums accepted, life insurance organizations,
    million KZT, monthly."""
    return _fetch_insurance_premiums(
        "Life", "INSURANCE_PREMIUMS_LIFE",
        "Million KZT (converted from the source's thousand-KZT unit). Total insurance "
        "premiums accepted under insurance and reinsurance contracts, LIFE insurance "
        "organizations. Not the same total as INSURANCE_PREMIUMS_GENERAL -- the source "
        "provides no combined General+Life aggregate.",
    )


# ---------------------------------------------------------------------------
# PENSION_PAYMENTS: found 2026-08-31 in formId=29 "Information on the volume
# of pension savings and the number of individual pension accounts of
# contributors" (category "financial sector" -> accumulative pension
# system). Row matched: class_type='Pension savings payments',
# row_code='Pension savings payments' (the unclassified top-level total --
# excludes per-country and per-reason sub-rows) AND type='thsd. tenge'
# (this form ALSO reports the identical row_code/class_type combination
# twice more per date with type='Units' for headcount/transaction-count
# series -- excluding on `type` was required to get exactly one row per
# date, verified live). Year-to-date cumulative within each calendar year,
# same convention as PENSION_FUND_ASSETS/INSURANCE_PREMIUMS_*. Verified
# live with full pagination: 44 unique monthly dates, 2023-01 through
# 2026-08, thousand KZT (1.16 trillion KZT YTD as of Jan 2023 alone,
# consistent with Kazakhstan's well-publicized 2023 one-time pension
# withdrawal program for housing/medical/education use).
# ---------------------------------------------------------------------------
PENSION_PAYMENTS_FORM_ID = "29"
PENSION_PAYMENTS_CLASS_TYPE = "Pension savings payments"


def fetch_pension_payments() -> tuple[list[dict], dict]:
    """Total pension savings payments made from Kazakhstan's Unified
    Accumulative Pension Fund (UAPF/ЕНПФ), million KZT, monthly
    (year-to-date cumulative within each calendar year)."""
    all_rows = _fetch_nbk_form_paginated(PENSION_PAYMENTS_FORM_ID, "PENSION_PAYMENTS")

    matching = [r for r in all_rows if r.get("class_type") == PENSION_PAYMENTS_CLASS_TYPE
                and r.get("row_code") == PENSION_PAYMENTS_CLASS_TYPE and r.get("type") == "thsd. tenge"]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/PENSION_PAYMENTS",
                f"WHAT CHANGED: no unclassified rows found with class_type={PENSION_PAYMENTS_CLASS_TYPE!r}, "
                "type='thsd. tenge' in formId=" + PENSION_PAYMENTS_FORM_ID,
                "EXPECTED: the top-level unclassified pension-payments total row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={PENSION_PAYMENTS_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"]) / 1000.0} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={PENSION_PAYMENTS_FORM_ID}",
        "dataset_id": f"formId={PENSION_PAYMENTS_FORM_ID},class_type={PENSION_PAYMENTS_CLASS_TYPE}",
        "note": "Million KZT (converted from the source's thousand-KZT unit). Total pension "
                "savings payments made from Kazakhstan's Unified Accumulative Pension Fund "
                "(UAPF/ЕНПФ) -- year-to-date cumulative within each calendar year, resets each "
                "January.",
    }
    return records, manifest


# ---------------------------------------------------------------------------
# RESERVES_IMPORT_COVER: found 2026-08-31 in formId=469 "The indicators of
# the adequacy of the international reserves of the Republic of Kazakhstan"
# (category "external sector"). A small form with 5 named `indicator`
# values per report_date. Verified live with full pagination: 50 unique
# quarterly dates, 2014-Q1 through 2026-Q2, smooth/continuous throughout.
#
# The form's OTHER 3 percent-denominated indicators (Guidotti rule,
# financing-potential-outflow, financing-liabilities-in-broad-money) were
# investigated and explicitly DECLINED: starting exactly 2026-01-01 their
# values drop ~100x in magnitude (e.g. Guidotti: 135.9 -> 1.495 between
# 2025-10-01 and 2026-01-01) while still labeled value_type1='percent', and
# the broad-money indicator's `indicator` label field is missing entirely
# from those same two dates onward. This is a confirmed, current source-side
# structural break (verified by inspecting the raw rows directly, not
# guessed), not a real economic collapse -- reconciling it would mean
# guessing whether to rescale old or new values, which the MASTER TASK rules
# forbid. Only the unaffected "number of months" import-cover indicator is
# connected.
# ---------------------------------------------------------------------------
RESERVE_ADEQUACY_FORM_ID = "469"


def _fetch_reserve_adequacy(indicator_label: str, indicator_id: str, note: str) -> tuple[list[dict], dict]:
    all_rows = _fetch_nbk_form_paginated(RESERVE_ADEQUACY_FORM_ID, indicator_id)

    matching = [r for r in all_rows if r.get("indicator") == indicator_label]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows found with indicator={indicator_label!r} in formId={RESERVE_ADEQUACY_FORM_ID}",
                "EXPECTED: this named reserve-adequacy indicator series",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={RESERVE_ADEQUACY_FORM_ID} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={RESERVE_ADEQUACY_FORM_ID}",
        "dataset_id": f"formId={RESERVE_ADEQUACY_FORM_ID},indicator={indicator_label}",
        "note": note,
    }
    return records, manifest


def fetch_reserves_import_cover() -> tuple[list[dict], dict]:
    """International reserves adequacy for financing imports, number of
    months of import cover, quarterly. NBK's own benchmark: adequate level
    is at least 3 months."""
    return _fetch_reserve_adequacy(
        "The value of the international reserves adequate for financing imports",
        "RESERVES_IMPORT_COVER",
        "Number of months of import cover provided by Kazakhstan's international reserves. "
        "NBK's own stated adequate level: at least 3 months.",
    )


# ---------------------------------------------------------------------------
# PRODUCTION_VOLUME_DIFFUSION_INDEX / PRODUCTION_EXPECTATIONS_DIFFUSION_INDEX
# / DEMAND_DIFFUSION_INDEX / DEMAND_EXPECTATIONS_DIFFUSION_INDEX: found
# 2026-08-31 in NBK's "Survey Results" -> "Enterprise Monitoring" category
# (quarterly business-tendency survey of Kazakhstani enterprises, similar
# methodology to BUSINESS_ACTIVITY_INDEX/formId=339 but form-specific).
# formId=365 "Production volume" and formId=366 "Demand for goods/service"
# each break their diffusion index down by `industry` (Professional
# services, Real estate, IT, etc.) AND publish a genuine economy-wide
# `industry`='All sectors' aggregate row -- no fabrication needed, this
# aggregate is the source's own. A diffusion index >50 signals expansion,
# <50 contraction, =50 neutral (standard PMI-style convention, confirmed by
# the "expectations" vs "actual" pairing and the values oscillating around
# 50). Verified live with full pagination and zero duplicate dates: formId=365
# series have 42 quarterly points each (2016-Q2 to 2026-Q3), formId=366
# series have 86 quarterly points each (2005-Q2 to 2026-Q3, the longest
# history found in any NBK survey form so far).
# ---------------------------------------------------------------------------
def _fetch_enterprise_survey_index(form_id: str, indicator_code: str, indicator_id: str, note: str) -> tuple[list[dict], dict]:
    all_rows = _fetch_nbk_form_paginated(form_id, indicator_id)

    matching = [r for r in all_rows if r.get("industry") == "All sectors" and r.get("indicator_code") == indicator_code]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows found with industry='All sectors', indicator_code={indicator_code!r} in formId={form_id}",
                "EXPECTED: the economy-wide aggregate diffusion-index row",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={form_id} and update scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={form_id}",
        "dataset_id": f"formId={form_id},industry=All sectors,indicator_code={indicator_code}",
        "note": note,
    }
    return records, manifest


def fetch_production_volume_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise monitoring survey: economy-wide diffusion index of
    reported production volume change, quarterly. >50 expansion, <50
    contraction, =50 neutral."""
    return _fetch_enterprise_survey_index(
        "365", "Production volume - Diffusion index", "PRODUCTION_VOLUME_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' reported change in production volume over "
        "the quarter.",
    )


def fetch_production_expectations_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise monitoring survey: economy-wide diffusion index of
    expected production volume change next quarter."""
    return _fetch_enterprise_survey_index(
        "365", "Production volume expectations - Diffusion index", "PRODUCTION_EXPECTATIONS_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' EXPECTED production volume change next "
        "quarter.",
    )


def fetch_demand_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise monitoring survey: economy-wide diffusion index of
    reported demand for goods/services, quarterly."""
    return _fetch_enterprise_survey_index(
        "366", "Demand - Diffusion index", "DEMAND_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' reported change in demand for their "
        "goods/services over the quarter.",
    )


def fetch_demand_expectations_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise monitoring survey: economy-wide diffusion index of
    expected demand for goods/services next quarter."""
    return _fetch_enterprise_survey_index(
        "366", "Demand expectations - Diffusion index", "DEMAND_EXPECTATIONS_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' EXPECTED demand for their goods/services "
        "next quarter.",
    )
