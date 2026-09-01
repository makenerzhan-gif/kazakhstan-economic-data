"""National Bank of Kazakhstan fetcher.

Confirmed live 2026-08-30 (see config/sources.yaml -> agencies.nbk). Open Data
Repository base https://data.nationalbank.kz/api/v1 -- no auth/CAPTCHA on the
data-serving endpoints used here.
"""
from __future__ import annotations

import csv
import json
import sys
import time
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
# First date the per-date rates endpoint serves a TRUSTWORTHY value, probed 2026-09-01.
# The window itself opens a few days earlier, but 07.05.2021 is a Kazakhstan public holiday
# for which the endpoint substitutes the latest available rate (464.77, against neighbours of
# 426.99) instead of reporting no data -- so the series deliberately starts after it. The
# window also rolls forward, which is why the fetcher accumulates across runs rather than
# re-pulling a fixed recent window.
EXCHANGE_RATE_EARLIEST = date(2021, 5, 10)


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

    fresh = {row["effectiveDate"]: float(row["rate"]) for row in data}
    # Accumulated: this endpoint returns a FIXED window of the 15 most recent
    # decisions and ignores every paging/date parameter tried (verified 2026-09-01),
    # so without merging, each decision falls out of the series as newer ones land.
    # NOT collapsed: the endpoint returns one row per MPC DECISION, and a decision to
    # hold the rate is itself an event worth keeping. Collapsing repeats here dropped 15
    # decisions to 6 distinct levels, discarding every hold.
    records = _merge_accumulated("BASE_RATE", fresh)
    manifest = {
        "frequency": "daily",
        "source_url": BASE_RATE_URL,
        "dataset_id": "base-rate",
        "note": "event-dated (rate valid until the next MPC decision), not literal daily observations",
    }
    return records, manifest


def _parse_usd_from_rates_xml(content: bytes) -> float | None:
    """Pull the USD rate out of one get_rates.cfm response, or None."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    for item in root.findall(".//item"):
        title_el = item.find("title")
        if title_el is not None and (title_el.text or "").strip() == "USD":
            desc_el = item.find("description")
            if desc_el is not None and desc_el.text:
                try:
                    return float(desc_el.text.strip())
                except ValueError:
                    return None
            return None
    return None


def _assert_no_isolated_spike(ordered: list[dict]) -> None:
    """Raise if a point spikes away from both neighbours and back again.

    This guards against the source substituting a wrong LEVEL for a date it does
    not actually publish. Observed live 2026-09-01: 07.05.2021 -- a Kazakhstan
    public holiday, and the first date inside the endpoint's window -- came back
    as 464.77, the latest rate available at request time, instead of the
    "информации нет" the endpoint returns for dates outside the window. Both
    neighbouring days were 426.99. Nothing inside that single response looked
    wrong: it was self-consistent, carrying change=+37.78, which reconstructs
    426.99 exactly.

    An isolated spike is the signature. Real tenge devaluations are sustained
    moves, not one-day round trips -- checked against Feb-Mar 2022, where the
    rate ran 428 -> 503 over two weeks and this check stays silent, and against
    the full 1364-point backfill, where it fires on nothing.
    """
    for i in range(1, len(ordered) - 1):
        a, b, c = ordered[i - 1]["value"], ordered[i]["value"], ordered[i + 1]["value"]
        if not a or not b:
            continue
        left = (b / a - 1) * 100
        right = (c / b - 1) * 100
        if abs(left) > 5 and abs(right) > 5 and left * right < 0:
            raise validation.StructuralChangeError(
                "\n".join([
                    "STRUCTURAL CHANGE DETECTED in nbk/EXCHANGE_RATE",
                    f"WHAT CHANGED: isolated spike at {ordered[i]['date']} -- "
                    f"{a} -> {b} -> {c} ({left:+.2f}% then {right:+.2f}%)",
                    "EXPECTED: the tenge moves in sustained steps, not one-day spikes that reverse",
                    "ACTUAL: this is the signature of the endpoint returning the latest available "
                    "rate for a date it does not publish, instead of reporting no data",
                    f"ACTION REQUIRED: request {ordered[i]['date']} from {RATES_CFM_URL} directly, "
                    "compare it against its neighbours, and exclude the date if the source is "
                    "substituting a value",
                ])
            )


def fetch_exchange_rate_usd(recheck_days: int = 14, max_new: int | None = None) -> tuple[list[dict], dict]:
    """Official daily USD/KZT rate, accumulated across runs.

    The source serves ONE DATE PER REQUEST: nationalbank.kz/rss/get_rates.cfm
    ?fdate=DD.MM.YYYY. Verified live 2026-09-01 that it offers no range
    interface -- passing `tdate` alongside `fdate` is silently ignored and the
    response still covers the single `fdate` -- and that rates_all.xml carries
    only today's snapshot across 48 currencies, not a history.

    The window is LIMITED AND ROLLING. Probing back on 2026-09-01: 2020, 2015,
    2010, 2005 and 2000 all answer "на выбранную дату информации нет", while
    2022 through 2026 answer normally, and the boundary sits in early May 2021
    (05.05.2021 absent, 11.05.2021 present). Because the window rolls forward,
    history reachable today stops being reachable later -- so this fetcher
    ACCUMULATES rather than re-pulling a fixed recent window: it reads what has
    already been processed, requests only the dates still missing plus the last
    `recheck_days` days, and returns the merged series.

    This replaces an implementation that re-fetched a 14-day window every run and
    therefore always produced a 14-day series, discarding everything older. The
    dataset held only 2026-08-19..2026-09-01 for what is the most-used
    macroeconomic series in the country.

    Only weekdays are requested -- no rate is published for weekends. Public
    holidays stay permanently "missing" and are re-asked each run, which costs a
    few dozen requests rather than thousands.

    Each date's raw XML is archived separately rather than merged before saving,
    keeping raw data an unmodified copy of what the source returned.
    """
    today = date.today()
    existing = _load_processed_series("EXCHANGE_RATE")

    wanted: list[date] = []
    d = EXCHANGE_RATE_EARLIEST
    while d <= today:
        if d.weekday() < 5:
            wanted.append(d)
        d += timedelta(days=1)

    recheck_from = today - timedelta(days=recheck_days)
    to_fetch = [d for d in wanted if d.isoformat() not in existing or d >= recheck_from]
    if max_new is not None:
        # Keep the tail when capped, so a capped run still advances the current
        # end of the series rather than only backfilling ancient history.
        to_fetch = to_fetch[-max_new:]

    fetched: dict[str, float] = {}
    attempted = 0
    for d in to_fetch:
        attempted += 1
        try:
            resp = requests.get(RATES_CFM_URL, headers=HEADERS,
                                params={"fdate": d.strftime("%d.%m.%Y")}, timeout=30)
        except requests.exceptions.RequestException:
            continue
        if resp.status_code != 200 or not resp.content:
            continue
        raw_store.save_raw_bytes(SOURCE, f"EXCHANGE_RATE_{d.isoformat()}", today, "xml", resp.content)
        value = _parse_usd_from_rates_xml(resp.content)
        if value is not None:
            fetched[d.isoformat()] = value
        time.sleep(0.25)

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in nbk/EXCHANGE_RATE",
                f"WHAT CHANGED: no USD rate parsed from any of {attempted} requests, and no "
                "previously-processed history exists to fall back on",
                "EXPECTED: a USD item carrying a rate for at least one requested date",
                f"ACTUAL: zero parseable USD entries across {attempted} requests to {RATES_CFM_URL}",
                "ACTION REQUIRED: inspect the live XML response and update scripts/fetchers/nbk.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, "EXCHANGE_RATE", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": RATES_CFM_URL,
        "earliest_available": EXCHANGE_RATE_EARLIEST.isoformat(),
        "already_had": len(existing), "requested": attempted, "newly_parsed": len(fetched),
        "total_after_merge": len(merged),
    })

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    _assert_no_isolated_spike(records)

    manifest = {
        "frequency": "daily",
        "source_url": RATES_CFM_URL,
        "dataset_id": "get_rates.cfm",
        "note": "Official NBK USD/KZT rate. The endpoint serves one date per request and its "
                "window rolls forward (nothing before early May 2021 was reachable on "
                "2026-09-01), so this series is accumulated across runs: each run fetches only "
                "the dates still missing plus the last two weeks, then merges with what was "
                "already processed. Weekends are not requested. The series starts 2021-05-10 "
                "rather than at the window edge because 07.05.2021, a public holiday, is served "
                "with a substituted rate instead of a no-data response.",
    }
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
    fresh = {r["date"]: float(r["tonia"]) for r in matching}
    # Accumulated: this endpoint serves only a rolling ~6-month window, so a
    # fetcher returning just the window would drop older days on every run.
    records = _merge_accumulated("TONIA", fresh)
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


# ---------------------------------------------------------------------------
# Remaining NBK "Enterprise Monitoring" survey indicators, all found 2026-08-31
# by probing the category's forms and reusing the same
# `industry`='All sectors' + `indicator_code` match as the production/demand
# indices above. Every series below was verified live with full pagination and
# zero duplicate dates, and its point count was checked to EXACTLY equal the
# number of calendar quarters in its own date range (42 for 2016-Q2..2026-Q3,
# 86 for 2005-Q2..2026-Q3, 26 for 2020-Q2..2026-Q3) -- i.e. genuinely regular
# quarterly series with no gaps, not merely "no duplicates".
#
# Note these are not all diffusion indices: formId=347 reports averages in
# percent/months, 369 a weighted-average percent, 378/368 shares of
# respondents in percent, and 392 a weighted-average percent. Units are stated
# per indicator in config/indicators.yaml and in each note below.
#
# formId=360 "Change in average wage" was investigated and DECLINED: despite
# every row being labeled `period`='quarter', the actual reporting dates are
# SEMI-ANNUAL (2016-04, 2016-10, 2017-04, 2017-10, ... for the actual series;
# Jan/Jul for the expectations series), switching to consecutive quarters only
# in 2026. Publishing a mid-series frequency change as "quarterly" would be
# wrong, so it is left unconnected rather than mislabeled.
# ---------------------------------------------------------------------------
def fetch_loan_rate_acceptable_kzt() -> tuple[list[dict], dict]:
    """Interest rate on tenge loans that surveyed enterprises consider
    acceptable, percent per annum, quarterly."""
    return _fetch_enterprise_survey_index(
        "347", "Acceptable interest rate of loans in tenge", "LOAN_RATE_ACCEPTABLE_KZT",
        "Percent per annum, average across respondents. NBK enterprise monitoring survey, "
        "economy-wide ('All sectors'): the interest rate on TENGE loans that surveyed "
        "enterprises report as acceptable for borrowing. A survey-reported willingness "
        "measure, not a market rate -- compare against LENDING_RATE for the actual rate.",
    )


def fetch_loan_rate_acceptable_fx() -> tuple[list[dict], dict]:
    """Interest rate on foreign-currency loans that surveyed enterprises
    consider acceptable, percent per annum, quarterly."""
    return _fetch_enterprise_survey_index(
        "347", "Acceptable interest rate of loans in foreign currency", "LOAN_RATE_ACCEPTABLE_FX",
        "Percent per annum, average across respondents. NBK enterprise monitoring survey, "
        "economy-wide ('All sectors'): the interest rate on FOREIGN-CURRENCY loans that "
        "surveyed enterprises report as acceptable for borrowing. A survey-reported "
        "willingness measure, not a market rate.",
    )


def fetch_loan_term_acceptable_kzt() -> tuple[list[dict], dict]:
    """Loan term on tenge loans that surveyed enterprises consider
    acceptable, months, quarterly."""
    return _fetch_enterprise_survey_index(
        "347", "Acceptable term of loans in tenge", "LOAN_TERM_ACCEPTABLE_KZT",
        "Months, average across respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): the loan maturity on TENGE loans that surveyed enterprises report "
        "as acceptable for borrowing.",
    )


def fetch_loan_term_acceptable_fx() -> tuple[list[dict], dict]:
    """Loan term on foreign-currency loans that surveyed enterprises consider
    acceptable, months, quarterly."""
    return _fetch_enterprise_survey_index(
        "347", "Acceptable term of loans in foreign currency", "LOAN_TERM_ACCEPTABLE_FX",
        "Months, average across respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): the loan maturity on FOREIGN-CURRENCY loans that surveyed "
        "enterprises report as acceptable for borrowing.",
    )


def fetch_inventories_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of reported
    inventory change, quarterly."""
    return _fetch_enterprise_survey_index(
        "362", "Inventories - Diffusion index", "INVENTORIES_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' reported change in inventories over the "
        "quarter.",
    )


def fetch_inventories_expectations_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of expected
    inventory change next quarter."""
    return _fetch_enterprise_survey_index(
        "362", "Inventories expectations - Diffusion index", "INVENTORIES_EXPECTATIONS_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' EXPECTED change in inventories next "
        "quarter.",
    )


def fetch_import_price_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of reported
    imported-goods price change, quarterly."""
    return _fetch_enterprise_survey_index(
        "363", "Price of imported goods - Diffusion index", "IMPORT_PRICE_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' reported change in the price of IMPORTED "
        "goods over the quarter -- an imported-inflation pressure gauge.",
    )


def fetch_import_price_expectations_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of expected
    imported-goods price change next quarter."""
    return _fetch_enterprise_survey_index(
        "363", "Price expectations for imported goods - Diffusion index",
        "IMPORT_PRICE_EXPECTATIONS_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' EXPECTED change in the price of IMPORTED "
        "goods next quarter.",
    )


def fetch_raw_materials_price_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of reported raw
    materials price change, quarterly."""
    return _fetch_enterprise_survey_index(
        "364", "Price for raw materials - Diffusion index", "RAW_MATERIALS_PRICE_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' reported change in raw materials prices "
        "over the quarter -- a cost-push inflation gauge. History back to 2005-Q2.",
    )


def fetch_raw_materials_price_expectations_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of expected raw
    materials price change next quarter."""
    return _fetch_enterprise_survey_index(
        "364", "Price for raw materials expectations - Diffusion index",
        "RAW_MATERIALS_PRICE_EXPECTATIONS_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' EXPECTED change in raw materials prices "
        "next quarter. History back to 2005-Q2.",
    )


def fetch_capacity_utilization() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide capacity utilization level,
    percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "369", "Capacity utilization - Weighted Average", "CAPACITY_UTILIZATION",
        "Percent, weighted average across respondents. NBK enterprise monitoring survey, "
        "economy-wide ('All sectors') level of production capacity actually in use -- a "
        "standard output-gap/slack indicator.",
    )


def fetch_finished_goods_price_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of reported
    finished-goods price change, quarterly."""
    return _fetch_enterprise_survey_index(
        "387", "Price for finished goods - Diffusion index", "FINISHED_GOODS_PRICE_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' reported change in their own FINISHED "
        "GOODS prices over the quarter -- an output-price/pass-through inflation gauge. "
        "History back to 2005-Q2.",
    )


def fetch_finished_goods_price_expectations_diffusion_index() -> tuple[list[dict], dict]:
    """NBK enterprise survey: economy-wide diffusion index of expected
    finished-goods price change next quarter."""
    return _fetch_enterprise_survey_index(
        "387", "Price for finished goods expectations - Diffusion index",
        "FINISHED_GOODS_PRICE_EXPECTATIONS_DIFFUSION_INDEX",
        "Diffusion index (0-100, 50=neutral). NBK enterprise monitoring survey, economy-wide "
        "('All sectors') aggregate of enterprises' EXPECTED change in their own FINISHED "
        "GOODS prices next quarter -- a firm-side inflation-expectations gauge, complementing "
        "the household-side INFLATION_EXPECTATIONS. History back to 2005-Q2.",
    )


def fetch_overdue_accounts_payable_share() -> tuple[list[dict], dict]:
    """NBK enterprise survey: share of enterprises reporting overdue accounts
    payable, percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "378", "Overdue accounts payable", "OVERDUE_ACCOUNTS_PAYABLE_SHARE",
        "Percent, share of surveyed respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): share of enterprises reporting OVERDUE ACCOUNTS PAYABLE -- a "
        "corporate-distress indicator.",
    )


def fetch_overdue_accounts_receivable_share() -> tuple[list[dict], dict]:
    """NBK enterprise survey: share of enterprises reporting overdue accounts
    receivable, percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "378", "Overdue accounts receivable", "OVERDUE_ACCOUNTS_RECEIVABLE_SHARE",
        "Percent, share of surveyed respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): share of enterprises reporting OVERDUE ACCOUNTS RECEIVABLE -- a "
        "payment-chain stress indicator.",
    )


def fetch_overdue_bank_loans_share() -> tuple[list[dict], dict]:
    """NBK enterprise survey: share of enterprises reporting overdue bank
    loan debt, percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "378", "Overdue debt on bank loans", "OVERDUE_BANK_LOANS_SHARE",
        "Percent, share of surveyed respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): share of enterprises reporting OVERDUE DEBT ON BANK LOANS -- the "
        "survey-side counterpart to the banking sector's NPL_RATIO.",
    )


def fetch_enterprise_debt_burden() -> tuple[list[dict], dict]:
    """NBK enterprise survey: average share of revenue going to loan
    payments, percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "392", "Average debt burden", "ENTERPRISE_DEBT_BURDEN",
        "Percent, weighted average across respondents. NBK enterprise monitoring survey, "
        "economy-wide ('All sectors'): share of enterprise revenue going to loan payments.",
    )


def fetch_exporters_share() -> tuple[list[dict], dict]:
    """NBK enterprise survey: share of enterprises engaged in export
    activity, percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "368", "Foreign Economic Activity - export", "EXPORTERS_SHARE",
        "Percent, share of surveyed respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): share of enterprises engaged in EXPORT activity only (the survey "
        "reports export-only, import-only, both, and neither as four separate shares).",
    )


def _fetch_nbk_exact_row(form_id: str, match: dict, indicator_id: str, note: str,
                          frequency: str) -> tuple[list[dict], dict]:
    """Fetch one fully-pinned series out of an NBK form.

    `match` names every classification field that must be set, and to what.
    A row qualifies only if it matches all of them AND has NO other
    classification field set -- so a row carrying an extra breakdown
    dimension (by region, by counterparty, etc.) can never be silently
    picked up as if it were the headline figure.

    Requiring exactly one qualifying row per report_date is itself the
    structural-change guard: if the source adds a new breakdown dimension to
    this series, the count per date changes and this raises rather than
    silently returning one arbitrary row of several.

    Values are compared case-insensitively and whitespace-stripped. This is
    NOT sloppiness: the NBK API was observed on 2026-08-31 returning the same
    field with different casing between otherwise identical requests (formId=445
    `period` came back as both 'month' and 'Month'), and some forms pad their
    labels (formId=340 reports `type` as ' mln USD' with a leading space).
    Only presentation differs -- the classification itself is the same -- so
    exact-string pinning would break intermittently for no real reason.
    """
    all_rows = _fetch_nbk_form_paginated(form_id, indicator_id)

    def norm(value) -> str:
        return str(value).strip().casefold()

    normalized_match = {k: norm(v) for k, v in match.items()}

    def qualifies(row: dict) -> bool:
        for key, want in normalized_match.items():
            if key not in row or norm(row[key]) != want:
                return False
        for key, value in row.items():
            if key in ("report_date", "amount") or key in match:
                continue
            if value not in (None, ""):
                return False
        return True

    matching = [r for r in all_rows if qualifies(r)]
    if not matching:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows in formId={form_id} match {match!r} with no other "
                "classification field set",
                "EXPECTED: one row per period for exactly this series",
                "ACTUAL: zero matching rows",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={form_id} and update scripts/fetchers/nbk.py",
            ])
        )

    dates = [r["report_date"] for r in matching]
    duplicates = sorted({d for d in dates if dates.count(d) > 1})
    if duplicates:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: formId={form_id} now returns more than one row per date for "
                f"{match!r} -- the source appears to have added a breakdown dimension",
                f"EXPECTED: exactly one row per report_date",
                f"ACTUAL: {len(duplicates)} duplicated date(s), e.g. {duplicates[:3]}",
                f"ACTION REQUIRED: inspect {MONETARY_AGGREGATES_URL}?formId={form_id}, identify the new "
                "dimension, and pin it in the match dict in scripts/fetchers/nbk.py",
            ])
        )

    records = [{"date": r["report_date"], "value": float(r["amount"])} for r in matching]
    records.sort(key=lambda r: r["date"])
    pinned = ",".join(f"{k}={v}" for k, v in sorted(match.items()))
    manifest = {
        "frequency": frequency,
        "source_url": f"{MONETARY_AGGREGATES_URL}?formId={form_id}",
        "dataset_id": f"formId={form_id},{pinned}",
        "note": note,
    }
    return records, manifest


def fetch_importers_share() -> tuple[list[dict], dict]:
    """NBK enterprise survey: share of enterprises engaged in import
    activity, percent, quarterly."""
    return _fetch_enterprise_survey_index(
        "368", "Foreign Economic Activity - import", "IMPORTERS_SHARE",
        "Percent, share of surveyed respondents. NBK enterprise monitoring survey, economy-wide "
        "('All sectors'): share of enterprises engaged in IMPORT activity only (the survey "
        "reports export-only, import-only, both, and neither as four separate shares).",
    )


def fetch_payments_total_value() -> tuple[list[dict], dict]:
    """Total Payments Value (All Instruments) (billion KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "419", {'period': 'Month', 'type': 'billions KZT', 'payment_instrument': 'Total'},
        "PAYMENTS_TOTAL_VALUE",
        "Billion KZT. Total value of all payments made through Kazakhstan payment instruments in the month (gross payment turnover, all instruments combined).",
        "monthly",
    )


def fetch_cashless_payments_value() -> tuple[list[dict], dict]:
    """Cashless Payments Value (billion KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "419", {'period': 'Month', 'type': 'billions KZT', 'payment_instrument': 'cashless payments'},
        "CASHLESS_PAYMENTS_VALUE",
        "Billion KZT. Value of cashless (non-cash) payments in the month. Read together with CASH_WITHDRAWALS_VALUE as a cash-vs-cashless split, and with NON_CASH_PAYMENTS_SHARE.",
        "monthly",
    )


def fetch_cash_withdrawals_value() -> tuple[list[dict], dict]:
    """Cash Withdrawals Value (billion KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "419", {'period': 'Month', 'type': 'billions KZT', 'payment_instrument': 'cash withdrawals'},
        "CASH_WITHDRAWALS_VALUE",
        "Billion KZT. Value of cash withdrawals in the month -- the cash side of the payment mix.",
        "monthly",
    )


def fetch_payment_cards_value() -> tuple[list[dict], dict]:
    """Payment Card Transactions Value (billion KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "419", {'period': 'Month', 'type': 'billions KZT', 'payment_instrument': 'Payment cards, including:'},
        "PAYMENT_CARDS_VALUE",
        "Billion KZT. Value of payment-card transactions in the month (the source own 'Payment cards, including:' aggregate row, covering both cashless card payments and card cash withdrawals).",
        "monthly",
    )


def fetch_household_deposits_fixed_term_kzt() -> tuple[list[dict], dict]:
    """Household Fixed-Term Deposits, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "261", {'type': 'Balance (mln. tenge)', 'currency': 'National currency', 'deposit_type': 'Fixed term'},
        "HOUSEHOLD_DEPOSITS_FIXED_TERM_KZT",
        "Million KZT, end of month. Fixed-term deposits of INDIVIDUALS in second-tier banks, denominated in TENGE. Together with the _FX series this is the standard household deposit dollarization pair.",
        "monthly",
    )


def fetch_household_deposits_fixed_term_fx() -> tuple[list[dict], dict]:
    """Household Fixed-Term Deposits, Foreign Currency (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "261", {'type': 'Balance (mln. tenge)', 'currency': 'Foreign currency', 'deposit_type': 'Fixed term'},
        "HOUSEHOLD_DEPOSITS_FIXED_TERM_FX",
        "Million KZT equivalent, end of month. Fixed-term deposits of INDIVIDUALS in second-tier banks, denominated in FOREIGN CURRENCY.",
        "monthly",
    )


def fetch_household_deposits_demand_kzt() -> tuple[list[dict], dict]:
    """Household Current/Demand Deposits, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "261", {'type': 'Balance (mln. tenge)', 'currency': 'National currency', 'deposit_type': 'Current account and demand'},
        "HOUSEHOLD_DEPOSITS_DEMAND_KZT",
        "Million KZT, end of month. Current-account and demand deposits of INDIVIDUALS in second-tier banks, in TENGE.",
        "monthly",
    )


def fetch_household_deposits_demand_fx() -> tuple[list[dict], dict]:
    """Household Current/Demand Deposits, Foreign Currency (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "261", {'type': 'Balance (mln. tenge)', 'currency': 'Foreign currency', 'deposit_type': 'Current account and demand'},
        "HOUSEHOLD_DEPOSITS_DEMAND_FX",
        "Million KZT equivalent, end of month. Current-account and demand deposits of INDIVIDUALS in second-tier banks, in FOREIGN CURRENCY.",
        "monthly",
    )


def fetch_household_deposits_saving_kzt() -> tuple[list[dict], dict]:
    """Household Savings Deposits, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "261", {'type': 'Balance (mln. tenge)', 'currency': 'National currency', 'deposit_type': 'Saving'},
        "HOUSEHOLD_DEPOSITS_SAVING_KZT",
        "Million KZT, end of month. Savings deposits of INDIVIDUALS in second-tier banks, in TENGE.",
        "monthly",
    )


def fetch_household_deposits_saving_fx() -> tuple[list[dict], dict]:
    """Household Savings Deposits, Foreign Currency (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "261", {'type': 'Balance (mln. tenge)', 'currency': 'Foreign currency', 'deposit_type': 'Saving'},
        "HOUSEHOLD_DEPOSITS_SAVING_FX",
        "Million KZT equivalent, end of month. Savings deposits of INDIVIDUALS in second-tier banks, in FOREIGN CURRENCY.",
        "monthly",
    )


def fetch_loans_business_kzt() -> tuple[list[dict], dict]:
    """Bank Loans to Business, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "445", {'period': 'Month', 'type': 'mln. of KZT, end of period', 'creditors': 'Banking sector', 'currency': 'National currency', 'subject_type': 'Business'},
        "LOANS_BUSINESS_KZT",
        "Million KZT, end of month. Outstanding banking-sector loans to BUSINESS borrowers, in TENGE.",
        "monthly",
    )


def fetch_loans_business_fx() -> tuple[list[dict], dict]:
    """Bank Loans to Business, Foreign Currency (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "445", {'period': 'Month', 'type': 'mln. of KZT, end of period', 'creditors': 'Banking sector', 'currency': 'Foreign currency', 'subject_type': 'Business'},
        "LOANS_BUSINESS_FX",
        "Million KZT equivalent, end of month. Outstanding banking-sector loans to BUSINESS borrowers, in FOREIGN CURRENCY -- the corporate side of credit dollarization.",
        "monthly",
    )


def fetch_loans_individuals_kzt() -> tuple[list[dict], dict]:
    """Bank Loans to Individuals, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "445", {'period': 'Month', 'type': 'mln. of KZT, end of period', 'creditors': 'Banking sector', 'currency': 'National currency', 'subject_type': 'Individuals'},
        "LOANS_INDIVIDUALS_KZT",
        "Million KZT, end of month. Outstanding banking-sector loans to INDIVIDUALS, in TENGE -- Kazakhstan household credit stock.",
        "monthly",
    )


def fetch_loans_individuals_fx() -> tuple[list[dict], dict]:
    """Bank Loans to Individuals, Foreign Currency (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "445", {'period': 'Month', 'type': 'mln. of KZT, end of period', 'creditors': 'Banking sector', 'currency': 'Foreign currency', 'subject_type': 'Individuals'},
        "LOANS_INDIVIDUALS_FX",
        "Million KZT equivalent, end of month. Outstanding banking-sector loans to INDIVIDUALS, in FOREIGN CURRENCY (a very small residual stock since FX retail lending was restricted).",
        "monthly",
    )


def fetch_loans_microfinance_individuals() -> tuple[list[dict], dict]:
    """Microfinance Loans to Individuals, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "445", {'period': 'Month', 'type': 'mln. of KZT, end of period', 'creditors': 'Microfinance activities', 'currency': 'National currency', 'subject_type': 'Individuals'},
        "LOANS_MICROFINANCE_INDIVIDUALS",
        "Million KZT, end of month. Outstanding MICROFINANCE-sector loans to INDIVIDUALS, in TENGE -- non-bank consumer credit, outside the banking-sector aggregates.",
        "monthly",
    )


def fetch_loans_microfinance_business() -> tuple[list[dict], dict]:
    """Microfinance Loans to Business, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "445", {'period': 'Month', 'type': 'mln. of KZT, end of period', 'creditors': 'Microfinance activities', 'currency': 'National currency', 'subject_type': 'Business'},
        "LOANS_MICROFINANCE_BUSINESS",
        "Million KZT, end of month. Outstanding MICROFINANCE-sector loans to BUSINESS borrowers, in TENGE.",
        "monthly",
    )


def fetch_external_debt_long_term() -> tuple[list[dict], dict]:
    """External Debt, Long-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "340", {'period': 'Quarter', 'type': ' mln USD', 'class_type': 'Total External debt of Kazakhstan', 'matiruty': 'Long-term'},
        "EXTERNAL_DEBT_LONG_TERM",
        "USD million, end of quarter. LONG-TERM portion of Kazakhstan total gross external debt. Together with EXTERNAL_DEBT_SHORT_TERM this is the maturity split behind EXTERNAL_DEBT.",
        "quarterly",
    )


def fetch_external_debt_short_term() -> tuple[list[dict], dict]:
    """External Debt, Short-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "340", {'period': 'Quarter', 'type': ' mln USD', 'class_type': 'Total External debt of Kazakhstan', 'matiruty': 'Short-term'},
        "EXTERNAL_DEBT_SHORT_TERM",
        "USD million, end of quarter. SHORT-TERM portion of Kazakhstan total gross external debt -- the rollover-risk component, and the numerator concept behind reserve-adequacy rules such as RESERVES_IMPORT_COVER.",
        "quarterly",
    )


def fetch_private_external_debt_intercompany() -> tuple[list[dict], dict]:
    """Private External Debt: Intercompany Lending (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "340", {'period': 'Quarter', 'type': ' mln USD', 'class_type': 'Private Sector External Debt', 'matiruty': 'Long-term', 'name_eng': 'Direct investment: Intercompany lending'},
        "PRIVATE_EXTERNAL_DEBT_INTERCOMPANY",
        "USD million, end of quarter. Long-term private-sector external debt in the form of DIRECT INVESTMENT INTERCOMPANY LENDING -- the dominant component of Kazakhstan external debt, largely oil-sector parent-to-subsidiary financing rather than market borrowing.",
        "quarterly",
    )


def fetch_private_external_debt_banks_other_lt() -> tuple[list[dict], dict]:
    """Private External Debt: Banks and Other Sectors, Long-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "340", {'period': 'Quarter', 'type': ' mln USD', 'class_type': 'Private Sector External Debt', 'matiruty': 'Long-term', 'name_eng': 'Banks and Other Sectors'},
        "PRIVATE_EXTERNAL_DEBT_BANKS_OTHER_LT",
        "USD million, end of quarter. Long-term private-sector external debt of BANKS AND OTHER SECTORS, excluding intercompany lending -- the market-borrowing part of private external debt.",
        "quarterly",
    )


def fetch_gold_bullion_sales() -> tuple[list[dict], dict]:
    """Refined Gold Bullion Bars Sold to the Public (pieces, quarterly)."""
    return _fetch_nbk_exact_row(
        "476", {'period': 'quarter', 'type': 'pieces'},
        "GOLD_BULLION_SALES",
        "Number of bars. Refined gold bullion bars sold to the public by second-tier banks and non-bank exchange offices -- a retail gold-demand / household savings-behavior indicator.",
        "quarterly",
    )


def fetch_remittances_sent_usd() -> tuple[list[dict], dict]:
    """Remittances Sent, US Dollars (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "411", {'period': 'Month', 'type': 'mln. KZT', 'currency_code': 'US Dollar', 'money_transfer_sign': 'money transfers sent'},
        "REMITTANCES_SENT_USD",
        "Million KZT equivalent. Cross-border money transfers SENT from Kazakhstan denominated in US DOLLARS. Currency composition behind the REMITTANCES_SENT total.",
        "monthly",
    )


def fetch_remittances_sent_kzt() -> tuple[list[dict], dict]:
    """Remittances Sent, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "411", {'period': 'Month', 'type': 'mln. KZT', 'currency_code': 'Tenge', 'money_transfer_sign': 'money transfers sent'},
        "REMITTANCES_SENT_KZT",
        "Million KZT. Cross-border money transfers SENT from Kazakhstan denominated in TENGE.",
        "monthly",
    )


def fetch_remittances_sent_rub() -> tuple[list[dict], dict]:
    """Remittances Sent, Russian Rubles (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "411", {'period': 'Month', 'type': 'mln. KZT', 'currency_code': 'Rubles', 'money_transfer_sign': 'money transfers sent'},
        "REMITTANCES_SENT_RUB",
        "Million KZT equivalent. Cross-border money transfers SENT from Kazakhstan denominated in RUSSIAN RUBLES.",
        "monthly",
    )


def fetch_remittances_received_usd() -> tuple[list[dict], dict]:
    """Remittances Received, US Dollars (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "411", {'period': 'Month', 'type': 'mln. KZT', 'currency_code': 'US Dollar', 'money_transfer_sign': 'money transfers received'},
        "REMITTANCES_RECEIVED_USD",
        "Million KZT equivalent. Cross-border money transfers RECEIVED in Kazakhstan denominated in US DOLLARS.",
        "monthly",
    )


def fetch_remittances_received_kzt() -> tuple[list[dict], dict]:
    """Remittances Received, Tenge (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "411", {'period': 'Month', 'type': 'mln. KZT', 'currency_code': 'Tenge', 'money_transfer_sign': 'money transfers received'},
        "REMITTANCES_RECEIVED_KZT",
        "Million KZT. Cross-border money transfers RECEIVED in Kazakhstan denominated in TENGE.",
        "monthly",
    )


def fetch_remittances_received_rub() -> tuple[list[dict], dict]:
    """Remittances Received, Russian Rubles (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "411", {'period': 'Month', 'type': 'mln. KZT', 'currency_code': 'Rubles', 'money_transfer_sign': 'money transfers received'},
        "REMITTANCES_RECEIVED_RUB",
        "Million KZT equivalent. Cross-border money transfers RECEIVED in Kazakhstan denominated in RUSSIAN RUBLES.",
        "monthly",
    )


def fetch_external_debt_gov_loans_lt() -> tuple[list[dict], dict]:
    """External Debt: General Government Loans, Long-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "293", {'maturity': 'Long-term', 'period': 'quarter', 'type': 'USD mln', 'investment_type': 'Loans ', 'sector_economy_type': 'General Government'},
        "EXTERNAL_DEBT_GOV_LOANS_LT",
        "USD million, end of quarter. Long-term external debt of the GENERAL GOVERNMENT in the form of LOANS -- the sovereign borrowing component of external debt.",
        "quarterly",
    )


def fetch_external_debt_banks_loans_lt() -> tuple[list[dict], dict]:
    """External Debt: Bank Loans, Long-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "293", {'maturity': 'Long-term', 'period': 'quarter', 'type': 'USD mln', 'investment_type': 'Loans ', 'sector_economy_type': 'Banks'},
        "EXTERNAL_DEBT_BANKS_LOANS_LT",
        "USD million, end of quarter. Long-term external debt of BANKS in the form of LOANS.",
        "quarterly",
    )


def fetch_external_debt_banks_securities_lt() -> tuple[list[dict], dict]:
    """External Debt: Bank Debt Securities, Long-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "293", {'maturity': 'Long-term', 'period': 'quarter', 'type': 'USD mln', 'investment_type': 'Debt securities ', 'sector_economy_type': 'Banks'},
        "EXTERNAL_DEBT_BANKS_SECURITIES_LT",
        "USD million, end of quarter. Long-term external debt of BANKS in the form of DEBT SECURITIES (eurobond-style market borrowing).",
        "quarterly",
    )


def fetch_external_debt_other_securities_lt() -> tuple[list[dict], dict]:
    """External Debt: Other Sectors Debt Securities, Long-Term (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "293", {'maturity': 'Long-term', 'period': 'quarter', 'type': 'USD mln', 'investment_type': 'Debt securities ', 'sector_economy_type': 'Other Sectors'},
        "EXTERNAL_DEBT_OTHER_SECURITIES_LT",
        "USD million, end of quarter. Long-term external debt of OTHER SECTORS (non-bank corporates) in the form of DEBT SECURITIES.",
        "quarterly",
    )


def fetch_gov_securities_secondary_nbk_notes() -> tuple[list[dict], dict]:
    """Government Securities Secondary Market: NBK Notes Volume (million KZT, monthly)."""
    return _fetch_nbk_exact_row(
        "16", {'code': 'NBK Notes', 'type': 'Transactions volume (mln. tenge)'},
        "GOV_SECURITIES_SECONDARY_NBK_NOTES",
        "Million KZT. Secondary-market transaction volume in NBK Notes -- a liquidity/turnover measure for the National Bank short-term sterilization instrument, distinct from the outstanding stock in GOV_SECURITIES_MEUKAM.",
        "monthly",
    )


def fetch_exchange_rate_eur_otc() -> tuple[list[dict], dict]:
    """EUR/KZT OTC Average Bid Rate (KZT per 1 EUR, monthly)."""
    return _fetch_nbk_exact_row(
        "41", {'currency': 'Euro', 'type': 'Average rate - bid'},
        "EXCHANGE_RATE_EUR_OTC",
        "KZT per 1 EUR. Average BID rate on Kazakhstan's over-the-counter FX market. Distinct from the official NBK rate (EXCHANGE_RATE, USD only) -- this is a market average, and the form also publishes a near-identical 'Average rate - offer' series.",
        "monthly",
    )


def fetch_exchange_rate_rub_otc() -> tuple[list[dict], dict]:
    """RUB/KZT OTC Average Bid Rate (KZT per 1 RUB, monthly)."""
    return _fetch_nbk_exact_row(
        "41", {'currency': 'Russian ruble', 'type': 'Average rate - bid'},
        "EXCHANGE_RATE_RUB_OTC",
        "KZT per 1 RUB. Average BID rate on Kazakhstan's over-the-counter FX market -- relevant given Russia's weight in Kazakhstan's trade and remittance flows.",
        "monthly",
    )


def fetch_exchange_rate_usd_otc() -> tuple[list[dict], dict]:
    """USD/KZT OTC Average Bid Rate (KZT per 1 USD, monthly)."""
    return _fetch_nbk_exact_row(
        "41", {'currency': 'US dollars', 'type': 'Average rate - bid'},
        "EXCHANGE_RATE_USD_OTC",
        "KZT per 1 USD. Average BID rate on Kazakhstan's over-the-counter FX market. Compare against EXCHANGE_RATE, which is the official NBK rate -- the two are different concepts and will not match exactly.",
        "monthly",
    )


def fetch_fx_otc_volume_usd() -> tuple[list[dict], dict]:
    """FX OTC Market Volume, US Dollars (Bid) (USD million, monthly)."""
    return _fetch_nbk_exact_row(
        "41", {'currency': 'US dollars', 'type': 'Volume - bid (mln. units of currency)'},
        "FX_OTC_VOLUME_USD",
        "Million USD. Purchase (bid) turnover in US dollars on Kazakhstan's over-the-counter FX market.",
        "monthly",
    )


def fetch_fx_otc_volume_eur() -> tuple[list[dict], dict]:
    """FX OTC Market Volume, Euro (Bid) (EUR million, monthly)."""
    return _fetch_nbk_exact_row(
        "41", {'currency': 'Euro', 'type': 'Volume - bid (mln. units of currency)'},
        "FX_OTC_VOLUME_EUR",
        "Million EUR. Purchase (bid) turnover in euro on Kazakhstan's over-the-counter FX market.",
        "monthly",
    )


def fetch_fx_otc_volume_rub() -> tuple[list[dict], dict]:
    """FX OTC Market Volume, Russian Rubles (Bid) (RUB million, monthly)."""
    return _fetch_nbk_exact_row(
        "41", {'currency': 'Russian ruble', 'type': 'Volume - bid (mln. units of currency)'},
        "FX_OTC_VOLUME_RUB",
        "Million RUB. Purchase (bid) turnover in Russian rubles on Kazakhstan's over-the-counter FX market.",
        "monthly",
    )


def fetch_ofc_net_foreign_assets() -> tuple[list[dict], dict]:
    """Other Financial Corporations: Net Foreign Assets (million KZT, quarterly)."""
    return _fetch_nbk_exact_row(
        "26", {'class_type': 'Net foreign assets', 'type': 'Stocks (mln. tenge)', 'code': 'Net foreign assets', 'row_code': 'Net foreign assets'},
        "OFC_NET_FOREIGN_ASSETS",
        "Million KZT. NET FOREIGN ASSETS of other financial corporations (non-bank financial sector: pension fund, insurers, brokers, etc.), from NBK's analytical survey. Equals claims on nonresidents less liabilities to nonresidents.",
        "quarterly",
    )


def fetch_ofc_claims_on_nonresidents() -> tuple[list[dict], dict]:
    """Other Financial Corporations: Claims on Nonresidents (million KZT, quarterly)."""
    return _fetch_nbk_exact_row(
        "26", {'class_type': 'Net foreign assets', 'type': 'Stocks (mln. tenge)', 'code': 'Claims on nonresidents', 'row_code': 'Claims on nonresidents', 'subtype1': 'Claims on nonresidents'},
        "OFC_CLAIMS_ON_NONRESIDENTS",
        "Million KZT. Gross CLAIMS ON NONRESIDENTS held by other financial corporations -- the asset side of OFC_NET_FOREIGN_ASSETS.",
        "quarterly",
    )


def fetch_ofc_liabilities_to_nonresidents() -> tuple[list[dict], dict]:
    """Other Financial Corporations: Liabilities to Nonresidents (million KZT, quarterly)."""
    return _fetch_nbk_exact_row(
        "26", {'class_type': 'Net foreign assets', 'type': 'Stocks (mln. tenge)', 'code': 'Less: liabilities to nonresidents', 'row_code': 'Liabilities to nonresidents', 'subtype1': 'Liabilities to nonresidents'},
        "OFC_LIABILITIES_TO_NONRESIDENTS",
        "Million KZT. Gross LIABILITIES TO NONRESIDENTS of other financial corporations -- the liability side of OFC_NET_FOREIGN_ASSETS.",
        "quarterly",
    )


def fetch_ofc_claims_on_banking_system() -> tuple[list[dict], dict]:
    """Other Financial Corporations: Claims on Banking System (million KZT, quarterly)."""
    return _fetch_nbk_exact_row(
        "26", {'class_type': 'Claims on banking system', 'code': 'Claims on banking system', 'row_code': 'Claims on banking system', 'type': 'Stocks (mln. tenge)'},
        "OFC_CLAIMS_ON_BANKING_SYSTEM",
        "Million KZT. Claims of other financial corporations on Kazakhstan's banking system -- the non-bank financial sector's exposure to banks.",
        "quarterly",
    )


def fetch_external_debt_general_government() -> tuple[list[dict], dict]:
    """External Debt: General Government (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "349", {'class_type': 'Debt', 'ed_code': 'External Debt - General Government', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_GENERAL_GOVERNMENT",
        "USD million, end of quarter. Gross external debt of the GENERAL GOVERNMENT. Part of the sector split that sums exactly to EXTERNAL_DEBT_EX_INTERCOMPANY.",
        "quarterly",
    )


def fetch_external_debt_central_bank() -> tuple[list[dict], dict]:
    """External Debt: Central Bank (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "349", {'class_type': 'Debt', 'ed_code': 'External Debt - Central Bank', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_CENTRAL_BANK",
        "USD million, end of quarter. Gross external debt of the CENTRAL BANK (National Bank of Kazakhstan).",
        "quarterly",
    )


def fetch_external_debt_banks() -> tuple[list[dict], dict]:
    """External Debt: Banks (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "349", {'class_type': 'Debt', 'ed_code': 'External Debt - Banks', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_BANKS",
        "USD million, end of quarter. Gross external debt of BANKS (second-tier banking sector).",
        "quarterly",
    )


def fetch_external_debt_other_sectors() -> tuple[list[dict], dict]:
    """External Debt: Other Sectors (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "349", {'class_type': 'Debt', 'ed_code': 'External Debt - Other Sectors', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_OTHER_SECTORS",
        "USD million, end of quarter. Gross external debt of OTHER SECTORS (non-bank corporates and households), excluding intercompany lending.",
        "quarterly",
    )


def fetch_external_debt_ex_intercompany() -> tuple[list[dict], dict]:
    """External Debt Excluding Intercompany Lending (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "349", {'class_type': 'Debt', 'ed_code': 'External Debt - Reference: ED not included intercompany lending', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_EX_INTERCOMPANY",
        "USD million, end of quarter. Gross external debt EXCLUDING direct-investment intercompany lending -- the market-borrowing measure. Intercompany lending dominates Kazakhstan's headline external debt (largely oil-sector parent-to-subsidiary financing), so this is the more comparable figure.",
        "quarterly",
    )


def fetch_external_debt_public_sector() -> tuple[list[dict], dict]:
    """External Debt: Public Sector (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "350", {'class_type': 'Debt', 'ed_code': 'External Debt - Reference: Public sector ED', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_PUBLIC_SECTOR",
        "USD million, end of quarter. PUBLIC SECTOR external debt (government, central bank, and entities controlled by government). With EXTERNAL_DEBT_PRIVATE_SECTOR this sums exactly to total EXTERNAL_DEBT.",
        "quarterly",
    )


def fetch_external_debt_private_sector() -> tuple[list[dict], dict]:
    """External Debt: Private Sector (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "350", {'class_type': 'Debt', 'ed_code': 'External Debt - Private sector ED', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_PRIVATE_SECTOR",
        "USD million, end of quarter. PRIVATE SECTOR external debt. With EXTERNAL_DEBT_PUBLIC_SECTOR this sums exactly to total EXTERNAL_DEBT.",
        "quarterly",
    )


def fetch_external_debt_gov_guaranteed() -> tuple[list[dict], dict]:
    """External Debt: Government and Government-Guaranteed (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "350", {'class_type': 'Debt', 'ed_code': 'External Debt - Reference: Government and government guaranteed ED', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_GOV_GUARANTEED",
        "USD million, end of quarter. Government and GOVERNMENT-GUARANTEED external debt -- the sovereign's direct plus contingent external obligations.",
        "quarterly",
    )


def fetch_external_debt_loans() -> tuple[list[dict], dict]:
    """External Debt: Loans (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "351", {'class_type': 'Debt', 'ed_code': 'External Debt - Loans', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_LOANS",
        "USD million, end of quarter. External debt in the form of LOANS -- the largest instrument category. Part of the instrument split that sums exactly to total EXTERNAL_DEBT.",
        "quarterly",
    )


def fetch_external_debt_debt_securities() -> tuple[list[dict], dict]:
    """External Debt: Debt Securities (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "351", {'class_type': 'Debt', 'ed_code': 'External Debt - Debt securities', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_DEBT_SECURITIES",
        "USD million, end of quarter. External debt in the form of DEBT SECURITIES (eurobonds and similar market instruments).",
        "quarterly",
    )


def fetch_external_debt_trade_credits() -> tuple[list[dict], dict]:
    """External Debt: Trade Credits and Advances (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "351", {'class_type': 'Debt', 'ed_code': 'External Debt - Trade credits and advances', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_TRADE_CREDITS",
        "USD million, end of quarter. External debt in the form of TRADE CREDITS AND ADVANCES.",
        "quarterly",
    )


def fetch_external_debt_currency_deposits() -> tuple[list[dict], dict]:
    """External Debt: Currency and Deposits (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "351", {'class_type': 'Debt', 'ed_code': 'External Debt - Currency and deposits', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_CURRENCY_DEPOSITS",
        "USD million, end of quarter. External debt in the form of CURRENCY AND DEPOSITS (mainly non-resident deposits held with Kazakhstani banks).",
        "quarterly",
    )


def fetch_external_debt_sdr() -> tuple[list[dict], dict]:
    """External Debt: Special Drawing Rights (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "351", {'class_type': 'Debt', 'ed_code': 'External Debt - Special drawing rights', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_SDR",
        "USD million, end of quarter. External debt in the form of SPECIAL DRAWING RIGHTS (the IMF SDR allocation, carried as a liability).",
        "quarterly",
    )


def fetch_external_debt_other_liabilities() -> tuple[list[dict], dict]:
    """External Debt: Other Debt Liabilities (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "351", {'class_type': 'Debt', 'ed_code': 'External Debt - Other debt liabilities', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_OTHER_LIABILITIES",
        "USD million, end of quarter. OTHER debt liabilities -- the residual instrument category completing the split.",
        "quarterly",
    )


def fetch_external_debt_due_within_year() -> tuple[list[dict], dict]:
    """External Debt Due Within One Year (Remaining Maturity) (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "348", {'class_type': 'Debt', 'ed_code': 'External Debt- Reference: ED due for payment within one year', 'period': 'quarter', 'type': 'USD mln'},
        "EXTERNAL_DEBT_DUE_WITHIN_YEAR",
        "USD million, end of quarter. External debt DUE FOR PAYMENT WITHIN ONE YEAR on a remaining-maturity basis -- short-term debt plus the current portion of long-term debt. This is the rollover-risk measure, and is larger than EXTERNAL_DEBT_SHORT_TERM, which is on an original-maturity basis.",
        "quarterly",
    )


def fetch_reserves_and_national_fund() -> tuple[list[dict], dict]:
    """International Reserves plus National Fund Assets (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'financial', 'code': 'Reserve assets + Foreign assets of the National Fund,  end of period ', 'investment_type_code': 'Reserve assets and National Fund', 'period': 'quarter', 'type': 'USD mln'},
        "RESERVES_AND_NATIONAL_FUND",
        "USD million, end of quarter. NBK reserve assets PLUS the foreign assets of the National Fund -- Kazakhstan's total external buffer. Held separately from FX_RESERVES (NBK reserves only, monthly) and NATIONAL_FUND_ASSETS (fund only, monthly); this is the combined figure on a balance-of-payments basis, with history back to 2005.",
        "quarterly",
    )


def fetch_reserves_and_nf_import_cover() -> tuple[list[dict], dict]:
    """Reserves plus National Fund, Import Cover (number of months, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'financial', 'code': 'Reserve assets and National Fund  in months of import of goods and services', 'investment_type_code': 'Reserve assets and National Fund', 'period': 'quarter', 'type': 'USD mln'},
        "RESERVES_AND_NF_IMPORT_COVER",
        "Months of goods-and-services imports covered by reserve assets PLUS National Fund foreign assets. Broader than RESERVES_IMPORT_COVER, which counts NBK reserve assets only.",
        "quarterly",
    )


def fetch_reserves_and_nf_gdp_share() -> tuple[list[dict], dict]:
    """Reserves plus National Fund, % of GDP (% of GDP, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'financial', 'code': 'in % of GDP2', 'investment_type_code': 'Reserve assets and National Fund', 'period': 'quarter', 'type': 'USD mln'},
        "RESERVES_AND_NF_GDP_SHARE",
        "Percent of GDP. Reserve assets plus National Fund foreign assets as a share of GDP.",
        "quarterly",
    )


def fetch_national_fund_gdp_share() -> tuple[list[dict], dict]:
    """National Fund Foreign Assets, % of GDP (% of GDP, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'financial', 'code': 'in % of GDP2', 'investment_type_code': 'National Fund', 'period': 'quarter', 'type': 'USD mln'},
        "NATIONAL_FUND_GDP_SHARE",
        "Percent of GDP. Foreign assets of the National Fund of Kazakhstan as a share of GDP.",
        "quarterly",
    )


def fetch_reserve_assets_gdp_share() -> tuple[list[dict], dict]:
    """NBK Reserve Assets, % of GDP (% of GDP, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'financial', 'code': 'in % of GDP2', 'investment_type_code': 'Reserve assets NBK', 'period': 'quarter', 'type': 'USD mln'},
        "RESERVE_ASSETS_GDP_SHARE",
        "Percent of GDP. NBK reserve assets as a share of GDP.",
        "quarterly",
    )


def fetch_financial_account_balance() -> tuple[list[dict], dict]:
    """Financial Account Balance (excluding reserve assets) (USD million, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'financial', 'code': 'Financial account (excluding reserve assets)', 'investment_type_code': 'financial', 'period': 'quarter', 'type': 'USD mln'},
        "FINANCIAL_ACCOUNT_BALANCE",
        "USD million. Balance of the FINANCIAL ACCOUNT of the balance of payments, excluding reserve assets -- the direct counterpart to CURRENT_ACCOUNT_BALANCE.",
        "quarterly",
    )


def fetch_bop_overall_balance_gdp_share() -> tuple[list[dict], dict]:
    """Balance of Payments Overall Balance, % of GDP (% of GDP, quarterly)."""
    return _fetch_nbk_exact_row(
        "485", {'account_type_code': 'Overall balance', 'code': 'in % of GDP1', 'investment_type_code': 'Overall balance', 'period': 'quarter', 'type': 'USD mln'},
        "BOP_OVERALL_BALANCE_GDP_SHARE",
        "Percent of GDP. OVERALL BALANCE of the balance of payments.",
        "quarterly",
    )


# ---------------------------------------------------------------------------
# Rolling-window sources: accumulate instead of re-pulling.
#
# Three NBK endpoints serve only a recent window and silently drop older data:
#   - get_rates.cfm (official FX rate)      -- window opens early May 2021
#   - /api/v1/data/base-rate                -- a fixed 15 most recent decisions
#   - /api/v1/data/indicators               -- a rolling ~6 months
# Verified on the last two, 2026-09-01: base-rate ignores every paging and date
# parameter tried (limit/size/count/pageSize/page/fromDate/startDate/dateFrom/
# all/years) and always returns exactly 15 rows; indicators accepts `from`/`to`
# (but NOT `fromDate`/`toDate`, which are ignored) yet still answers only from
# 2026-02-24 -- asking for 2010-2015, 2020-2022 or 2024-2025 returns zero rows.
#
# Because these windows roll forward, a fetcher that returns only what the
# endpoint currently serves loses history permanently on every run. These
# helpers merge each fetch with what has already been processed, so the series
# grows instead of sliding.
# ---------------------------------------------------------------------------
def _load_processed_series(indicator_id: str) -> dict[str, float]:
    """Points already written for this indicator, keyed by date."""
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[row["date"]] = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
    return out


def _merge_accumulated(indicator_id: str, fresh: dict[str, float],
                       collapse_repeats: bool = False) -> list[dict]:
    """Merge freshly-fetched points with everything already processed.

    `collapse_repeats` is for EVENT-DATED series -- a policy rate or a published
    inflation figure that is carried unchanged between announcements. Keeping one
    row per calendar day would bury a handful of real decisions under hundreds of
    repetitions, so only the points where the value actually changes are kept.
    """
    merged = {**_load_processed_series(indicator_id), **fresh}
    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    if collapse_repeats:
        kept = []
        for r in records:
            if not kept or r["value"] != kept[-1]["value"]:
                kept.append(r)
        records = kept
    return records


def _fetch_indicators_widget() -> list[dict]:
    """Full current window of the indicators widget (base rate, TONIA, annual
    inflation, inflation target). `from`/`to` are the parameter names that work."""
    resp = requests.get(INDICATORS_URL, headers=HEADERS,
                        params={"from": "2000-01-01", "to": date.today().isoformat()}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _fetch_indicators_field(field: str, indicator_id: str, note: str,
                            frequency: str, collapse_repeats: bool) -> tuple[list[dict], dict]:
    rows = _fetch_indicators_widget()
    today = date.today()
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, "json",
                             json.dumps(rows, ensure_ascii=False).encode("utf-8"))

    matching = {r["date"]: float(r[field]) for r in rows
                if r.get(field) is not None and r.get("date")}
    existing = _load_processed_series(indicator_id)
    if not matching and not existing:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in nbk/{indicator_id}",
                f"WHAT CHANGED: no rows with a non-null {field!r} field, and no previously "
                "processed history to fall back on",
                f"ACTUAL: {len(rows)} rows returned, none carrying {field!r}",
                f"ACTION REQUIRED: inspect {INDICATORS_URL} and update scripts/fetchers/nbk.py",
            ])
        )

    records = _merge_accumulated(indicator_id, matching, collapse_repeats=collapse_repeats)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": INDICATORS_URL,
        "field": field, "already_had": len(existing), "in_window": len(matching),
        "total_after_merge": len(records),
    })
    manifest = {
        "frequency": frequency,
        "source_url": INDICATORS_URL,
        "dataset_id": f"indicators-widget,field={field}",
        "note": note,
    }
    return records, manifest


def fetch_annual_inflation() -> tuple[list[dict], dict]:
    """Annual (year-on-year) consumer inflation, percent, as published by NBK.

    Event-dated. The source stamps this value on every calendar day, but it only
    STEPS when a new CPI reading is released -- verified 2026-09-01: across the
    186-day window it took 7 distinct values, changing on 2026-03-03, 04-02,
    05-05, 06-02, 07-02 and 08-04, i.e. in the first days of each month. Storing
    it daily would bury six real releases under 186 repeated rows, so only the
    change points are kept, dated when the figure appeared.

    This is the headline inflation measure the dataset previously lacked: the
    existing CPI series carries only month-on-month percent change, from which a
    year-on-year rate cannot be read directly.
    """
    return _fetch_indicators_field(
        "annualInflation", "ANNUAL_INFLATION",
        "Percent, year-on-year. Dated at the day the figure appeared on NBK's indicators "
        "widget, which is the CPI release date -- not the month the reading refers to. "
        "Event-dated: only the days the published value changed are stored. Accumulated "
        "across runs because the source window rolls (~6 months).",
        "irregular", True)


def fetch_inflation_target() -> tuple[list[dict], dict]:
    """NBK's official inflation target, percent. Event-dated -- one point per
    change. Constant at 5.0 across the whole window observed on 2026-09-01, so
    this series exists to record WHEN the target moves, and will stay short by
    design."""
    return _fetch_indicators_field(
        "inflationTarget", "INFLATION_TARGET",
        "Percent. NBK's official inflation target. Event-dated: one point per change, so a "
        "flat target produces a single row. Accumulated across runs because the source "
        "window rolls (~6 months).",
        "irregular", True)
