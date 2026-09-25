"""The external block for the QPM / BVAR models (added 2026-09-25): Russia and the United
States, later China and the euro area. Every endpoint here was found and checked live
before being wired in; the checks are in the notes and in project_knowledge/UPDATE_LOG.md.

Agencies, one raw/processed/metadata folder each:
- cbr  (Bank of Russia): the key rate -- DailyInfo SOAP method KeyRateXML, daily from
       2013-09-17, kept as the change points (effective dates, not decision dates: the
       16.00 of 15.12.2023 is in force from 2023-12-18); the official USD/RUB rate --
       /scripts/XML_dynamic.asp, daily, the date the rate APPLIES to.
- eec  (Eurasian Economic Commission): consumer prices of the EAEU members, monthly from
       2005 (Series_CPI/CPI_1.xls previous month = 100, CPI_3.xls same month of the
       previous year = 100). Rosstat is not reachable from the pipeline's runner; the EEC
       year-on-year figure for Russia equals the Bank of Russia's table in all 156 months
       2013-09..2026-08 within 0.05.
- imf  (IMF SDMX, QNEA): Russia's real GDP, quarterly, national currency, 2021 prices, not
       seasonally adjusted -- FROM 2014-Q1 ONLY: 2011-2013 sit on a different base (2013-Q4
       23.75 trn -> 2014-Q1 28.17 trn, a fake +44%).
- fred (Federal Reserve Bank of St. Louis): fredgraph.csv?id=<series>, no key.
"""
from __future__ import annotations

import csv
import io
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
_CACHE: dict[str, bytes] = {}


def _get(url: str, *, params=None, data=None, headers=None, attempts: int = 3, timeout: int = 60) -> bytes:
    key = f"{url}|{params!r}|{data!r}"
    if key not in _CACHE:
        for i in range(attempts):
            try:
                if data is None:
                    resp = requests.get(url, params=params, headers={**HEADERS, **(headers or {})}, timeout=timeout)
                else:
                    resp = requests.post(url, data=data, headers={**HEADERS, **(headers or {})}, timeout=timeout)
                resp.raise_for_status()
                _CACHE[key] = resp.content
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if i == attempts - 1:
                    raise
                time.sleep(2 * (i + 1))
    return _CACHE[key]


def _save_raw(agency: str, indicator_id: str, content: bytes, ext: str, info: dict) -> None:
    today = date.today()
    path = raw_store.save_raw_bytes(agency, indicator_id, today, ext, content)
    raw_store.write_download_manifest(agency, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, **info})


def _processed(agency: str, indicator_id: str) -> dict[str, float]:
    path = REPO_ROOT / "data" / "processed" / agency / f"{indicator_id.lower()}.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r.get("value") not in (None, "")}


def _structural(agency: str, indicator_id: str, what: str, url: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in {agency}/{indicator_id}",
        f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/foreign.py",
    ]))


# ---------------------------------------------------------------- Bank of Russia
CBR_SOAP_URL = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
CBR_XML_DYNAMIC_URL = "https://www.cbr.ru/scripts/XML_dynamic.asp"
CBR_USD_CODE = "R01235"
CBR_RATE_REFRESH_DAYS = 60
CBR_RUB_FIRST_DATE = "1998-01-01"   # the redenomination: 1995-97 values are in old rubles (3 623 in 1995)


def parse_cbr_key_rate(content: bytes) -> dict[str, float]:
    out = {}
    for kr in ET.fromstring(content).iter():
        if kr.tag.endswith("KR"):
            dt = next((c.text for c in kr if c.tag.endswith("DT")), None)
            rate = next((c.text for c in kr if c.tag.endswith("Rate")), None)
            if dt and rate:
                out[dt[:10]] = float(rate)
    return out


def fetch_ru_key_rate() -> tuple[list[dict], dict]:
    """Bank of Russia key rate, %, event-dated: the days a new level took effect."""
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<KeyRateXML xmlns="http://web.cbr.ru/"><fromDate>2013-09-01T00:00:00</fromDate>'
            f'<ToDate>{date.today().isoformat()}T00:00:00</ToDate></KeyRateXML></soap:Body></soap:Envelope>')
    content = _get(CBR_SOAP_URL, data=body.encode("utf-8"),
                   headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"http://web.cbr.ru/KeyRateXML"'})
    _save_raw("cbr", "RU_KEY_RATE", content, "xml", {"source_url": CBR_SOAP_URL, "method": "KeyRateXML"})
    daily = parse_cbr_key_rate(content)
    if len(daily) < 1000:
        _structural("cbr", "RU_KEY_RATE", f"only {len(daily)} daily rows from KeyRateXML", CBR_SOAP_URL)
    records, last = [], None
    for d in sorted(daily):
        if daily[d] != last:
            records.append({"date": d, "value": daily[d]})
            last = daily[d]
    return records, {"frequency": "irregular", "source_url": CBR_SOAP_URL, "dataset_id": "DailyInfo/KeyRateXML",
                     "note": "Percent per annum. One row per change of the Bank of Russia key rate, dated by the day "
                             "it TOOK EFFECT (the decision is usually the business day before), from 2013-09-17 (5.5%). "
                             "Collapsed from the daily series the web service returns."}


def parse_cbr_xml_dynamic(content: bytes) -> dict[str, float]:
    out = {}
    for rec in ET.fromstring(content).iter("Record"):
        d = rec.get("Date")
        nominal = rec.findtext("Nominal")
        value = rec.findtext("Value")
        if d and nominal and value:
            dd, mm, yyyy = d.split(".")
            out[f"{yyyy}-{mm}-{dd}"] = round(float(value.replace(",", ".")) / float(nominal.replace(",", ".")), 6)
    return out


def fetch_rub_usd(begin: date | None = None) -> tuple[list[dict], dict]:
    """Official RUB per USD, daily. Accumulated: each run reads the last CBR_RATE_REFRESH_DAYS days."""
    begin = begin or date.today() - timedelta(days=CBR_RATE_REFRESH_DAYS)
    params = {"date_req1": begin.strftime("%d/%m/%Y"), "date_req2": date.today().strftime("%d/%m/%Y"),
              "VAL_NM_RQ": CBR_USD_CODE}
    content = _get(CBR_XML_DYNAMIC_URL, params=params)
    _save_raw("cbr", "RUB_USD", content, "xml", {"source_url": CBR_XML_DYNAMIC_URL, "params": params})
    fresh = {d: v for d, v in parse_cbr_xml_dynamic(content).items() if d >= CBR_RUB_FIRST_DATE}
    merged = {**_processed("cbr", "RUB_USD"), **fresh}
    if not merged:
        _structural("cbr", "RUB_USD", "no <Record> rows in XML_dynamic and no history", CBR_XML_DYNAMIC_URL)
    return [{"date": d, "value": v} for d, v in sorted(merged.items())], {
        "frequency": "daily", "source_url": CBR_XML_DYNAMIC_URL, "dataset_id": f"XML_dynamic/{CBR_USD_CODE}",
        "note": "Rubles per US dollar, the Bank of Russia's official rate, dated by the day it APPLIES to (set the "
                "business day before), from 1998-01-01 (after the redenomination). Since mid-2024 it is set from "
                "the OTC market (Moscow Exchange dollar trading halted). Accumulated across runs."}


# ---------------------------------------------------------------- EEC consumer prices
EEC_CPI_URL = "https://eec.eaeunion.org/upload/files/dep_stat/econstat/Series_CPI/{file}"
EEC_CPI_FILES = {"mom": "CPI_1.xls", "yoy": "CPI_3.xls"}
RU_MONTH_COLUMNS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
                    "сентябрь", "октябрь", "ноябрь", "декабрь")


def parse_eec_cpi(content: bytes, country: str) -> dict[str, float]:
    sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
    header = next((sheet.row_values(i) for i in range(min(sheet.nrows, 10))
                   if [str(c).strip().lower() for c in sheet.row_values(i)[1:4]] == list(RU_MONTH_COLUMNS[:3])), None)
    if header is None:
        return {}
    month_col = {i: RU_MONTH_COLUMNS.index(str(c).strip().lower()) + 1 for i, c in enumerate(header)
                 if str(c).strip().lower() in RU_MONTH_COLUMNS}
    out, year = {}, None
    for i in range(sheet.nrows):
        row = sheet.row_values(i)
        m = next((re.match(r"^\s*(\d{4})\s+год", str(c)) for c in row[:2] if re.match(r"^\s*(\d{4})\s+год", str(c))), None)
        if m:
            year = int(m.group(1))
            continue
        if year and str(row[0]).strip() == country:
            for col, month in month_col.items():
                try:
                    out[f"{year:04d}-{month:02d}-01"] = float(str(row[col]).replace(",", "."))
                except (ValueError, IndexError):
                    continue
    return out


def _fetch_eec_cpi(country: str, basis: str, indicator_id: str) -> tuple[list[dict], dict]:
    url = EEC_CPI_URL.format(file=EEC_CPI_FILES[basis])
    content = _get(url)
    _save_raw("eec", indicator_id, content, "xls", {"source_url": url})
    values = parse_eec_cpi(content, country)
    if len(values) < 200:
        _structural("eec", indicator_id, f"only {len(values)} months for {country!r} in {EEC_CPI_FILES[basis]}", url)
    what = "previous month = 100" if basis == "mom" else "same month of the previous year = 100"
    return [{"date": d, "value": v} for d, v in sorted(values.items())], {
        "frequency": "monthly", "source_url": url, "dataset_id": f"eec/{EEC_CPI_FILES[basis]}/{country}",
        "note": f"Index, {what}: consumer prices, {country}, monthly from 2005-01, as published by the Eurasian "
                "Economic Commission from national statistics (one decimal, not seasonally adjusted)."}


def fetch_ru_cpi_mom() -> tuple[list[dict], dict]:
    return _fetch_eec_cpi("Россия", "mom", "RU_CPI_MOM")


def fetch_ru_cpi_yoy() -> tuple[list[dict], dict]:
    return _fetch_eec_cpi("Россия", "yoy", "RU_CPI_YOY")


# ---------------------------------------------------------------- IMF QNEA
IMF_QNEA_URL = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/QNEA/7.0.0/{country}.*.*.*.*.Q"
QNEA_FIRST_QUARTER = {"RUS": "2014-Q1"}


def parse_qnea_real_gdp(content: bytes, first_quarter: str) -> dict[str, float]:
    out = {}
    for r in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
        if (r.get("INDICATOR") == "B1GQ" and r.get("PRICE_TYPE") == "Q" and r.get("S_ADJUSTMENT") == "NSA"
                and r.get("TYPE_OF_TRANSFORMATION") == "XDC" and r.get("OBS_VALUE") and r.get("TIME_PERIOD")):
            m = re.match(r"^(\d{4})-Q([1-4])$", r["TIME_PERIOD"])
            if m and r["TIME_PERIOD"] >= first_quarter:
                y, q = int(m.group(1)), int(m.group(2))
                out[f"{y:04d}-{3 * q - 2:02d}-01"] = float(r["OBS_VALUE"])
    return out


def fetch_ru_gdp_real() -> tuple[list[dict], dict]:
    url = IMF_QNEA_URL.format(country="RUS")
    content = _get(url, headers={"Accept": "application/vnd.sdmx.data+csv"}, timeout=120)
    _save_raw("imf", "RU_GDP_REAL", content, "csv", {"source_url": url})
    values = parse_qnea_real_gdp(content, QNEA_FIRST_QUARTER["RUS"])
    if len(values) < 40:
        _structural("imf", "RU_GDP_REAL", f"only {len(values)} quarters of B1GQ/Q/NSA/XDC", url)
    return [{"date": d, "value": v} for d, v in sorted(values.items())], {
        "frequency": "quarterly", "source_url": url, "dataset_id": "IMF.STA/QNEA/7.0.0/RUS B1GQ Q NSA XDC",
        "note": "Rubles, real GDP of Russia at 2021 prices (chain-linked), quarterly, NOT seasonally adjusted, from "
                "2014-Q1: the IMF's 2011-2013 quarters sit on a different base (a fake +44% into 2014). Annual growth "
                "2020-2025: -2.65, 5.87, -1.44, 4.07, 4.92, 1.0."}


# ---------------------------------------------------------------- FRED
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SERIES = {
    "US_FED_FUNDS": ("FEDFUNDS", "monthly", "Percent, effective federal funds rate, monthly average."),
    "US_TREASURY_2Y": ("GS2", "monthly", "Percent, 2-year Treasury constant-maturity yield, monthly average."),
    "US_TREASURY_10Y": ("GS10", "monthly", "Percent, 10-year Treasury constant-maturity yield, monthly average."),
    "US_CPI": ("CPIAUCSL", "monthly", "Index 1982-84 = 100, CPI for all urban consumers, seasonally adjusted "
                                      "(seasonal factors are revised every February)."),
    "US_GDP_REAL": ("GDPC1", "quarterly", "Billions of chained 2017 dollars, seasonally adjusted annual rate "
                                          "(rebased at comprehensive revisions)."),
}


def parse_fred_csv(content: bytes, series: str) -> dict[str, float]:
    out = {}
    for r in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
        d = r.get("observation_date") or r.get("DATE")
        v = r.get(series)
        if d and v not in (None, "", "."):
            out[d] = float(v)
    return out


def _fetch_fred(indicator_id: str) -> tuple[list[dict], dict]:
    series, frequency, note = FRED_SERIES[indicator_id]
    content = _get(FRED_CSV_URL, params={"id": series})
    _save_raw("fred", indicator_id, content, "csv", {"source_url": FRED_CSV_URL, "series": series})
    values = parse_fred_csv(content, series)
    if len(values) < 100:
        _structural("fred", indicator_id, f"only {len(values)} observations of {series}", f"{FRED_CSV_URL}?id={series}")
    return [{"date": d, "value": v} for d, v in sorted(values.items())], {
        "frequency": frequency, "source_url": f"{FRED_CSV_URL}?id={series}", "dataset_id": f"FRED/{series}",
        "note": f"{note} FRED series {series}."}


def fetch_us_fed_funds() -> tuple[list[dict], dict]:
    return _fetch_fred("US_FED_FUNDS")


def fetch_us_treasury_2y() -> tuple[list[dict], dict]:
    return _fetch_fred("US_TREASURY_2Y")


def fetch_us_treasury_10y() -> tuple[list[dict], dict]:
    return _fetch_fred("US_TREASURY_10Y")


def fetch_us_cpi() -> tuple[list[dict], dict]:
    return _fetch_fred("US_CPI")


def fetch_us_gdp_real() -> tuple[list[dict], dict]:
    return _fetch_fred("US_GDP_REAL")
