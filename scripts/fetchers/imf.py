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
import time
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


def _download(url: str, attempts: int = 3) -> bytes:
    """Download with a retry on TRANSPORT-level failures only.

    imf.org was observed on 2026-09-01 intermittently resetting connections
    (ConnectionResetError 10054) on a couple of arbitrary indicators per run --
    a different pair each time, which is the signature of flaky transport rather
    than a problem with any one dataset.

    Only ConnectionError/Timeout are retried. HTTP status errors are deliberately
    NOT retried and NOT swallowed: a 404 or a 500 can mean the dataset moved or
    changed shape, and the MASTER TASK rules require that to fail loudly rather
    than be papered over by repetition. Retries are announced on stderr so a
    flaky source stays visible in the run output instead of silently passing.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt < attempts:
                print(f"imf: transport error on {url} (attempt {attempt}/{attempts}), "
                      f"retrying in {attempt}s: {type(exc).__name__}", file=sys.stderr)
                time.sleep(attempt)
    raise last_exc  # type: ignore[misc]


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


def fetch_gov_revenue_ratio() -> tuple[list[dict], dict]:
    """WEO general government revenue, % of GDP. Verified live 2026-08-30: indicator
    code GGR_NGDP. Cross-checked: 2031 value (19.57%) minus IMF_GOV_EXPENDITURE_RATIO's
    2031 value (21.28%) = -1.71%, matching IMF_GOV_BALANCE's own 2031 value (-1.72%)
    to within rounding -- internally consistent across three independently-fetched series."""
    return _fetch_weo_series("IMF_GOV_REVENUE_RATIO", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGR_NGDP")


def fetch_gov_expenditure_ratio() -> tuple[list[dict], dict]:
    """WEO general government expenditure, % of GDP. Verified live 2026-08-30: indicator
    code GGX_NGDP. See fetch_gov_revenue_ratio for the cross-check against IMF_GOV_BALANCE."""
    return _fetch_weo_series("IMF_GOV_EXPENDITURE_RATIO", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGX_NGDP")


def fetch_export_volume_growth() -> tuple[list[dict], dict]:
    """WEO export volume growth, % change. Verified live 2026-08-30: indicator code TX_RPCH."""
    return _fetch_weo_series("IMF_EXPORT_VOLUME_GROWTH", "WEO", "IMF.RES", "9.0.0", "KAZ", "TX_RPCH")


def fetch_import_volume_growth() -> tuple[list[dict], dict]:
    """WEO import volume growth, % change. Verified live 2026-08-30: indicator code TM_RPCH."""
    return _fetch_weo_series("IMF_IMPORT_VOLUME_GROWTH", "WEO", "IMF.RES", "9.0.0", "KAZ", "TM_RPCH")


def fetch_current_account_usd() -> tuple[list[dict], dict]:
    """WEO current account balance, USD level (companion to IMF_CURRENT_ACCOUNT, which is
    % of GDP). Verified live 2026-08-30: indicator code BCA. Cross-checked: 2031 value
    (-$9.953bn) / IMF_NOMINAL_GDP_USD's 2031 value ($501.68bn) = -1.984%, matching
    IMF_CURRENT_ACCOUNT's own 2031 value (-1.984%) essentially exactly."""
    return _fetch_weo_series("IMF_CURRENT_ACCOUNT_USD", "WEO", "IMF.RES", "9.0.0", "KAZ", "BCA")


def fetch_gdp_per_capita_ppp() -> tuple[list[dict], dict]:
    """WEO GDP per capita, PPP (international dollars). Verified live 2026-08-30:
    indicator code PPPPC."""
    return _fetch_weo_series("IMF_GDP_PER_CAPITA_PPP", "WEO", "IMF.RES", "9.0.0", "KAZ", "PPPPC")


def fetch_gdp_world_share_ppp() -> tuple[list[dict], dict]:
    """WEO share of world GDP based on PPP, %. Verified live 2026-08-30: indicator
    code PPPSH."""
    return _fetch_weo_series("IMF_GDP_WORLD_SHARE_PPP", "WEO", "IMF.RES", "9.0.0", "KAZ", "PPPSH")


def fetch_inflation_eop() -> tuple[list[dict], dict]:
    """WEO inflation, end of period consumer prices, % change (companion to
    IMF_INFLATION, which is average-period). Verified live 2026-08-30: indicator
    code PCPIEPCH."""
    return _fetch_weo_series("IMF_INFLATION_EOP", "WEO", "IMF.RES", "9.0.0", "KAZ", "PCPIEPCH")


def fetch_gov_net_debt_ratio() -> tuple[list[dict], dict]:
    """WEO general government net debt, % of GDP (companion to IMF_GOV_DEBT, which
    is gross debt). Verified live 2026-08-30: indicator code GGXWDN_NGDP.
    Cross-checked: 2031 value (8.99% of GDP) sits well below IMF_GOV_DEBT's own
    2031 gross-debt value (32.11%) -- expected direction given Kazakhstan's large
    National Fund financial assets offset gross liabilities in the net calculation."""
    return _fetch_weo_series("IMF_GOV_NET_DEBT_RATIO", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGXWDN_NGDP")


def fetch_nominal_gdp_deflator() -> tuple[list[dict], dict]:
    """WEO GDP deflator, index. Verified live 2026-08-30: indicator code NGDP_D."""
    return _fetch_weo_series("IMF_GDP_DEFLATOR_INDEX", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGDP_D")


def fetch_real_gdp_national_currency() -> tuple[list[dict], dict]:
    """WEO real GDP, national currency, constant prices (companion to IMF_GDP_GROWTH,
    which is the % change of this same underlying series). Verified live 2026-08-30:
    indicator code NGDP_R. (Tried LE -- WEO employment level -- first; it returned
    zero populated rows for Kazakhstan in this vintage, so it was dropped rather
    than forced in with empty data.)"""
    return _fetch_weo_series("IMF_REAL_GDP", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGDP_R")


def fetch_gov_expenditure_level() -> tuple[list[dict], dict]:
    """WEO general government total expenditure, national currency level
    (companion to IMF_GOV_EXPENDITURE_RATIO, which is % of GDP). Verified live
    2026-08-30: indicator code GGX. Cross-checked: 2031 value
    (69,450,172,320,000 KZT) / IMF_NOMINAL_GDP's 2031 value
    (326,326,260,159,000 KZT) = 21.284%, matching IMF_GOV_EXPENDITURE_RATIO's
    own 2031 value (21.282%) to within rounding. (Tried NID -- WEO total
    investment level -- and NGSD -- national savings level -- first; both
    returned zero populated rows for Kazakhstan, only their _NGDP ratio
    variants exist, so neither was forced in.)"""
    return _fetch_weo_series("IMF_GOV_EXPENDITURE", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGX")


def fetch_gov_revenue_level() -> tuple[list[dict], dict]:
    """WEO general government total revenue, national currency level
    (companion to IMF_GOV_REVENUE_RATIO, which is % of GDP). Verified live
    2026-08-30: indicator code GGR. Cross-checked: 2031 value
    (63,848,275,603,000 KZT) / IMF_NOMINAL_GDP's 2031 value matches
    IMF_GOV_REVENUE_RATIO's own 2031 value (19.566%) to within rounding."""
    return _fetch_weo_series("IMF_GOV_REVENUE", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGR")


def fetch_cpi_index() -> tuple[list[dict], dict]:
    """WEO consumer price index, level (companion to IMF_INFLATION, which is
    the % change of this same underlying series). Verified live 2026-08-30:
    indicator code PCPI."""
    return _fetch_weo_series("IMF_CPI_INDEX", "WEO", "IMF.RES", "9.0.0", "KAZ", "PCPI")


def fetch_gov_balance_level() -> tuple[list[dict], dict]:
    """WEO general government net lending/borrowing, national currency level
    (companion to IMF_GOV_BALANCE, which is % of GDP). Verified live
    2026-08-30: indicator code GGXCNL. Cross-checked: 2031 value
    (-5,601,896,717,000 KZT) / IMF_NOMINAL_GDP's 2031 value
    (326,326,260,159,000 KZT) = -1.717%, matching IMF_GOV_BALANCE's own 2031
    value (-1.717%) almost exactly. (Tried BM/BX -- WEO imports/exports of
    goods, USD level -- first; both returned zero populated rows for
    Kazakhstan, so neither was forced in.)"""
    return _fetch_weo_series("IMF_GOV_BALANCE_LEVEL", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGXCNL")


def fetch_ppp_exchange_rate() -> tuple[list[dict], dict]:
    """WEO implied PPP conversion rate, national currency per international
    dollar. Verified live 2026-08-30: indicator code PPPEX. Sanity-checked:
    2031 value (~249.8 KZT/int'l$) sits well below the market exchange rate
    (~486 KZT/USD, per NBK's own July 2026 reference rate) -- the expected
    direction for a developing economy, where a lower domestic price level
    means fewer tenge are needed to buy the same PPP-comparable basket than
    the nominal market rate would suggest."""
    return _fetch_weo_series("IMF_PPP_EXCHANGE_RATE", "WEO", "IMF.RES", "9.0.0", "KAZ", "PPPEX")


def fetch_structural_balance() -> tuple[list[dict], dict]:
    """WEO general government structural balance, % of potential GDP
    (excludes cyclical effects, unlike IMF_GOV_BALANCE's headline actual
    balance). Verified live 2026-08-30: indicator code GGSB_NPGDP. Sanity-
    checked: values are close to but not identical to IMF_GOV_BALANCE's
    (e.g. 2029: -1.93% structural vs -1.97% actual) -- the expected small
    gap between a structural and an actual/headline fiscal balance measure,
    not a data error. (Tried NGAP_NPGDP -- WEO output gap -- first; it
    returned 2 rows with empty OBS_VALUE for Kazakhstan, so it was dropped
    rather than forced in.)"""
    return _fetch_weo_series("IMF_STRUCTURAL_BALANCE", "WEO", "IMF.RES", "9.0.0", "KAZ", "GGSB_NPGDP")


def fetch_cpi_eop_index() -> tuple[list[dict], dict]:
    """WEO consumer price index, end-of-period level (companion to
    IMF_INFLATION_EOP, which is the % change of this same underlying
    series, and to IMF_CPI_INDEX, which is the average-period level).
    Verified live 2026-08-30: indicator code PCPIE."""
    return _fetch_weo_series("IMF_CPI_EOP_INDEX", "WEO", "IMF.RES", "9.0.0", "KAZ", "PCPIE")


def fetch_gdp_per_capita_national_currency() -> tuple[list[dict], dict]:
    """WEO GDP per capita, national currency (nominal). Verified live
    2026-08-30: indicator code NGDPPC. Cross-checked: 2031 value
    (15,068,912.72 KZT) is consistent with IMF_NOMINAL_GDP's 2031 value
    (326,326,260,159,000 KZT) divided by a population near IMF_POPULATION's
    own trajectory (~21.6M by 2031, extrapolated) -- 326,326,260,159,000 /
    21,650,000 ~= 15,072,000, matching to within rounding. (Tried TX/TM --
    WEO exports/imports of goods and services, USD level -- and TXG_D first;
    all returned zero populated rows for Kazakhstan, so none were forced in.)
    """
    return _fetch_weo_series("IMF_GDP_PER_CAPITA_NATIONAL", "WEO", "IMF.RES", "9.0.0", "KAZ", "NGDPPC")


# ---------------------------------------------------------------------------
# Commodity block: crude oil price and commodity terms of trade.
#
# Both come from IMF.RES dataflows that sit alongside the WEO one this module
# already uses, found 2026-09-01 by listing /structure/dataflow/IMF.RES:
#   PCPS 9.0.0 -- Primary Commodity Price System
#   CTOT 5.0.1 -- Commodity Terms of Trade
#
# The series keys were NOT guessed. Querying a partial key returns HTTP 200 with
# an empty body rather than an error, so a wrong key looks like a working request
# that found nothing -- exactly the failure mode that hides mistakes. The keys
# below were read off a full wildcard download of each dataflow.
#
# PCPS dimension order is COUNTRY.INDICATOR.DATA_TRANSFORMATION.FREQUENCY, where
# COUNTRY is the aggregate G001 (world) rather than a real country. CTOT is
# COUNTRY.INDICATOR.WGT_TYPE.FREQUENCY.
# ---------------------------------------------------------------------------
MONTH_END = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
             7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _parse_sdmx_csv(content: bytes, indicator_id: str, source_url: str) -> list[dict]:
    """Parse an SDMX 2.0 CSV response, handling annual, quarterly and monthly
    TIME_PERIOD forms (2024, 2024-Q1, 2024-M01)."""
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    if not rows:
        raise ValueError(f"IMF API returned an empty CSV body for {source_url}")

    columns = set(rows[0].keys())
    date_col = next((c for c in DATE_COL_CANDIDATES if c in columns), None)
    value_col = next((c for c in VALUE_COL_CANDIDATES if c in columns), None)
    if date_col is None or value_col is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in imf/{indicator_id}",
                f"WHAT CHANGED: no recognised date/value column in the CSV response",
                f"ACTUAL columns: {sorted(columns)}",
                f"ACTION REQUIRED: inspect {source_url} and update scripts/fetchers/imf.py",
            ])
        )

    records = []
    for row in rows:
        period = (row.get(date_col) or "").strip()
        raw = (row.get(value_col) or "").strip()
        if not period or not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        try:
            if "-M" in period:
                # Month START. Every monthly series in this project is dated at
                # the start of its month -- 122 of 125 after a convention sweep
                # on 2026-09-03 -- so month-end here meant OIL_PRICE and the two
                # commodity terms-of-trade series could not be joined on date to
                # any BNS or NBK monthly series. A join that silently returns
                # nothing raises nothing; this had to be found by looking.
                # Quarterly and annual stay at period end, which is what the
                # rest of the project uses for those frequencies.
                y, m = period.split("-M")
                year, month, day = int(y), int(m), 1
            elif "-Q" in period:
                y, q = period.split("-Q")
                year, month = int(y), int(q) * 3
                day = MONTH_END[month]
            else:
                year, month, day = int(period), 12, 31
        except (ValueError, KeyError):
            continue
        records.append({"date": f"{year:04d}-{month:02d}-{day:02d}", "value": value})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in imf/{indicator_id}",
                "WHAT CHANGED: the response parsed but produced zero usable observations",
                "EXPECTED: at least one row with a period and a numeric value. NOTE: this API "
                "answers a WRONG series key with HTTP 200 and an empty body, so an empty result "
                "usually means the key no longer matches, not that the data is gone",
                f"ACTION REQUIRED: inspect {source_url} and update scripts/fetchers/imf.py",
            ])
        )
    records.sort(key=lambda r: r["date"])
    return records


def _fetch_sdmx_monthly(indicator_id: str, dataflow: str, version: str, key: str,
                        note: str) -> tuple[list[dict], dict]:
    url = f"{BASE_URL}/IMF.RES/{dataflow}/{version}/{key}"
    content = _download(url)

    today = date.today()
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, "csv", content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "source_url": url, "downloaded_at": datetime.now().isoformat(),
        "dataflow": dataflow, "version": version, "series_key": key,
    })

    records = _parse_sdmx_csv(content, indicator_id, url)
    manifest = {
        "frequency": "monthly",
        "source_url": url,
        "dataset_id": f"{dataflow}/{version}/{key}",
        "note": note,
    }
    return records, manifest


def fetch_oil_price() -> tuple[list[dict], dict]:
    """Crude oil price, US dollars per barrel, monthly.

    IMF's APSP -- the Average Petroleum Spot Price, the simple average of Brent,
    Dubai Fateh and WTI. PCPS carries no standalone Brent series (checked: the
    indicator codelist has PCOIL for coconut oil, PHEATOIL, POLVOIL, PPOIL and so
    on, but the only crude entries are POILAPSP and POPEC, the OPEC basket), so
    APSP is the reference crude price this source offers.

    This closes the audit's largest single gap: Kazakhstan is an oil exporter and
    the dataset carried no oil price at all, so nothing linked world prices to
    exports, the budget or the National Fund.
    """
    return _fetch_sdmx_monthly(
        "OIL_PRICE", "PCPS", "9.0.0", "G001.POILAPSP.USD.M",
        "US dollars per barrel. IMF APSP crude oil price -- the simple average of Brent, "
        "Dubai Fateh and West Texas Intermediate. A world price, not a Kazakhstan-specific "
        "export price: KEBCO sells at a differential to Brent that this series does not "
        "capture.")


def fetch_commodity_terms_of_trade() -> tuple[list[dict], dict]:
    """Kazakhstan's commodity terms of trade, index, monthly, rolling weights."""
    return _fetch_sdmx_monthly(
        "COMMODITY_TERMS_OF_TRADE", "CTOT", "5.0.1", "KAZ.CEMPI_CTOTNX_TT.R_RW_IX.M",
        "Index. Price of Kazakhstan's commodity exports relative to its commodity imports. "
        "COMMODITY terms of trade, not overall terms of trade -- it covers the commodity "
        "basket only, and says nothing about manufactured trade. Rolling-weight variant: the "
        "export basket is re-weighted over time, which suits a series running from 1992; the "
        "fixed-weight variant is published separately as "
        "COMMODITY_TERMS_OF_TRADE_FIXED_WEIGHTS rather than one being chosen for you.")


def fetch_commodity_terms_of_trade_fixed_weights() -> tuple[list[dict], dict]:
    """Kazakhstan's commodity terms of trade, index, monthly, fixed weights."""
    return _fetch_sdmx_monthly(
        "COMMODITY_TERMS_OF_TRADE_FIXED_WEIGHTS", "CTOT", "5.0.1",
        "KAZ.CEMPI_CTOTNX_TT.R_FW_IX.M",
        "Index. The fixed-weight variant of COMMODITY_TERMS_OF_TRADE. Both weightings are "
        "published by the source; both are carried here so the choice between them stays "
        "visible rather than being made silently.")
