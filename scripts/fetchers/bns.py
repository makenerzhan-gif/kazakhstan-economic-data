"""Bureau of National Statistics (stat.gov.kz) fetcher.

Confirmed live 2026-08-30 (see config/sources.yaml -> agencies.bns). Download
pattern: GET https://stat.gov.kz/api/iblock/element/{elementId}/{json|csv}/file/ru/
-> 302 redirect -> static file, no auth/CAPTCHA. Field layout for each indicator
below was determined by actually downloading and inspecting the live file this
session (not guessed) -- see the per-function docstring for what was verified.
"""
from __future__ import annotations

import calendar
import csv
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
SOURCE = "bns"


_DOWNLOAD_CACHE: dict[str, bytes] = {}


def _download(url: str) -> bytes:
    """GET once per process: several indicators read one file (the export workbook,
    the industrial cube), and the World Bank / EIA fetchers reuse this too."""
    if url not in _DOWNLOAD_CACHE:
        resp = requests.get(url, headers=HEADERS, timeout=120)
        resp.raise_for_status()
        _DOWNLOAD_CACHE[url] = resp.content
    return _DOWNLOAD_CACHE[url]


def _save_raw(indicator_id: str, content: bytes, ext: str, extra_manifest: dict) -> None:
    today = date.today()
    path = raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "raw_file": path.name,
        **extra_manifest,
    })


def _dd_mm_yyyy_to_iso(s: str) -> str:
    return datetime.strptime(s, "%d.%m.%Y").date().isoformat()


def _fetch_cpi_cube_legacy() -> tuple[list[dict], dict]:
    """CPI, national, month-over-month index (% of previous period), category 'Товары и услуги'.

    Verified live 2026-08-30: file is TSV (tab-separated, despite the "/csv/" URL),
    UTF-8 with BOM, columns NAM/DAT/PERIOD/КАТО(по каталогу)/LКАТО(по каталогу)/
    ССП/LССП/ГНКИПЦ01_2753/LГНКИПЦ01_2753/VAL. Region names live in the "КАТО(по
    каталогу)" column (not the "L"-prefixed one, which is always "0" in this file);
    same for comparison type ("ССП") and category ("ГНКИПЦ01_2753"). Filtered to
    region == 'РЕСПУБЛИКА КАЗАХСТАН', comparison == 'отчетный период к предыдущему
    периоду' (month-over-month), category == 'Товары и услуги' (the only category
    present in this particular open-data file -- it's already the all-items total).
    """
    element_id = 1549
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/csv/file/ru/"
    content = _download(url)
    _save_raw("CPI", content, "csv", {"source_url": url, "element_id": element_id})

    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    header, data_rows = rows[0], rows[1:]
    col = {name: i for i, name in enumerate(header)}
    try:
        period_i = col["PERIOD"]
        region_i = col["КАТО(по каталогу)"]
        comparison_i = col["ССП"]
        category_i = col["ГНКИПЦ01_2753"]
        val_i = col["VAL"]
    except KeyError as exc:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/CPI",
                f"WHAT CHANGED: expected column {exc} not present",
                f"EXPECTED: PERIOD, КАТО(по каталогу), ССП, ГНКИПЦ01_2753, VAL",
                f"ACTUAL COLUMNS: {header}",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        ) from exc

    TARGET_REGION = "РЕСПУБЛИКА КАЗАХСТАН"
    TARGET_COMPARISON = "отчетный период к предыдущему периоду"
    TARGET_CATEGORY = "Товары и услуги"

    records = []
    for row in data_rows:
        if row[region_i] != TARGET_REGION or row[comparison_i] != TARGET_COMPARISON or row[category_i] != TARGET_CATEGORY:
            continue
        period = row[period_i]  # e.g. "201911"
        if len(period) != 6 or not period.isdigit():
            continue
        iso_date = f"{period[:4]}-{period[4:]}-01"
        try:
            value = float(row[val_i])
        except ValueError:
            continue
        records.append({"date": iso_date, "value": value})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/CPI",
                "WHAT CHANGED: no rows matched the expected national/MoM/total-category filter",
                f"EXPECTED: region={TARGET_REGION!r}, comparison={TARGET_COMPARISON!r}, category={TARGET_CATEGORY!r}",
                "ACTUAL: zero matching rows in the downloaded file",
                f"ACTION REQUIRED: inspect {url} for renamed filter values and update scripts/fetchers/bns.py",
            ])
        )

    records.sort(key=lambda r: r["date"])
    manifest = {"frequency": "monthly", "source_url": url, "dataset_id": str(element_id)}
    return records, manifest


RU_MONTHS = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
MONTH_HEADER_RE = re.compile(r"^(\S+)\s+(\d{4})\s+года\*?$")
TRADE_TOTAL_ROW_LABEL = "Республики Казахстан"


def _parse_trade_workbook(content: bytes, indicator_id: str, url: str) -> list[dict]:
    """Shared parser for the BNS exports/imports XLSX files.

    Verified live 2026-08-30 by actually downloading and reading both files (56MB
    exports, 93MB imports -- read in openpyxl read_only mode, only the first ~4
    rows of each sheet are touched, so this stays fast despite the file size).
    Structure: one sheet per year (plus a partial-year sheet for the current year,
    e.g. 'январь-июнь 2026 года'), skipping two description sheets ('Метаданные',
    'Показатель'). Each data sheet's row 2 (0-indexed row 1) is a header with one
    label per month ('январь 2025 года', trailing '*' for preliminary months),
    each spanning 3 columns [tonnes, additional unit, thousand USD]. Row 4
    (0-indexed row 3) is the national total, literally labeled 'Республики
    Казахстан' in column A -- confirmed to be the very first data row, before any
    regional or product-level breakdown rows.
    """
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    records: list[dict] = []

    for sheet_name in wb.sheetnames:
        if sheet_name in ("Метаданные", "Показатель"):
            continue
        ws = wb[sheet_name]
        header_row = total_row = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 1:
                header_row = row
            elif i == 3:
                total_row = row
                break

        if header_row is None or total_row is None:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: sheet '{sheet_name}' has fewer than 4 rows",
                    "EXPECTED: header row at index 1, national-total row at index 3",
                    f"ACTUAL: header_row={header_row!r} total_row={total_row!r}",
                    f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
                ])
            )

        label = (total_row[0] or "").strip()
        if label != TRADE_TOTAL_ROW_LABEL:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: row 4 of sheet '{sheet_name}' is no longer the national total",
                    f"EXPECTED column-A label: {TRADE_TOTAL_ROW_LABEL!r}",
                    f"ACTUAL: {label!r}",
                    f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
                ])
            )

        for col_idx, cell in enumerate(header_row):
            if not cell:
                continue
            m = MONTH_HEADER_RE.match(str(cell).strip())
            if not m:
                continue
            month_num = RU_MONTHS.get(m.group(1).lower())
            if month_num is None:
                continue
            usd_col = col_idx + 2
            value = total_row[usd_col] if usd_col < len(total_row) else None
            if value is None:
                continue
            records.append({"date": f"{int(m.group(2)):04d}-{month_num:02d}-01", "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                "WHAT CHANGED: zero month/value pairs extracted from any sheet",
                "EXPECTED: at least one parsed monthly total",
                "ACTUAL: none",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        )

    records.sort(key=lambda r: r["date"])
    return records


def fetch_imports() -> tuple[list[dict], dict]:
    """Imports, national total, monthly, thousand USD -- the import workbook (element
    446906), same shape as the export one that scripts/fetchers/bns_trade.py reads."""
    element_id = 446906
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/file/ru/"
    content = _download(url)
    _save_raw("IMPORTS", content, "xlsx", {"source_url": url, "element_id": element_id})
    records = _parse_trade_workbook(content, "IMPORTS", url)
    manifest = {"frequency": "monthly", "source_url": url, "dataset_id": str(element_id)}
    return records, manifest


TALDAU_TREE_DATA_URL = "https://taldau.stat.gov.kz/ru/NewIndex/GetIndexTreeData"
# Taldau's periodId is not documented; these three were established by fetching
# each and reading the returned date keys. periodId=4 gives month-end dates,
# 5 gives quarter-ends and 7 gives year-ends. The manifest used to report every
# Taldau series as annual regardless, which was simply wrong for the quarterly
# and monthly ones.
TALDAU_PERIOD_FREQUENCY = {"4": "monthly", "5": "quarterly", "7": "annual"}
GDP_REAL_INDEX_ID = "2979005"  # "индекс физического объема ВВП методом производства"
NATIONAL_TERM_ID = "741880"    # РЕСПУБЛИКА КАЗАХСТАН
REGIONS_DIC_ID = "67"          # the classifier dictionary id for the region dimension


def fetch_gdp_real() -> tuple[list[dict], dict]:
    """Real GDP -- physical volume index (production method), national, annual.
    Value is % of the corresponding prior period (100 = no change), matching
    how BNS itself publishes it (not a rebased index level).

    This is on Taldau (taldau.stat.gov.kz), a different system from the
    stat.gov.kz /open-data/ file API used for the rest of BNS's indicators here
    -- its "NewIndex" delivery is a stateful ExtJS single-page app, not a
    one-shot file download. An earlier research pass (2026-08-30, same day)
    concluded this indicator was reachable but not yet parseable after several
    blind parameter guesses against the wrong endpoint (Api/GetIndexData)
    returned empty results.

    Cracked open this session by instrumenting XMLHttpRequest in a real browser
    session (Claude Browser tool) to capture the ACTUAL request the page's own
    ExtJS grid makes when it loads data -- not by guessing further. The two
    parameters that were missing before: p_measure_id=7 and p_dicIds=67 (a
    classifier-dictionary id, NOT the term id -- previous attempts conflated
    the two). The captured call was independently re-verified with a plain,
    cookie-less `requests.post` (confirmed stateless: no session/auth/CSRF
    needed at all).

    Endpoint: POST https://taldau.stat.gov.kz/ru/NewIndex/GetIndexTreeData
    Response: a JSON list of tree nodes; the root node (id=741880, "РЕСПУБЛИКА
    КАЗАХСТАН") carries the actual annual values as keys 'yDDDYYYY' (e.g.
    'y122009') where the last 4 digits are the calendar year. periodId=7 means
    annual ("Год") -- GetPeriodList also showed a periodId=9 "Квартал с
    накоплением" (quarter, cumulative) option for this same index, which would
    give quarterly granularity, but that variant's response shape was not
    captured/verified this session -- left for a future pass rather than guessed.
    """
    return _fetch_taldau_annual_index(
        GDP_REAL_INDEX_ID, "GDP_REAL",
        note="Physical volume index of GDP, production method, % of prior period (100=no change). "
             "A final-use-method variant also exists on Taldau (indexId 700974) but is not fetched here.",
    )


def _fetch_taldau_annual_index(index_id: str, indicator_id: str, note: str,
                                measure_id: str = "7", terms: str | None = None,
                                dic_ids: str = REGIONS_DIC_ID,
                                period_id: str = "7") -> tuple[list[dict], dict]:
    """Shared fetcher for any Taldau "NewIndex" indicator following the pattern
    discovered for GDP_REAL: national series, root term id 741880. See
    fetch_gdp_real's docstring for how this mechanism was cracked. Each new
    index_id used here was verified live this session (real HTTP 200, at least
    one parsed period) before being wired into update_bns.py -- not assumed to
    work by analogy alone.

    Some indicators (e.g. average wage) are classified across MULTIPLE
    dictionaries at once (region + industry + locality-type + enterprise-size +
    sex, etc.) rather than just region -- for those, `measure_id`, `terms`
    (comma-joined term ids, one per dictionary, each defaulting to its "Всего"/
    total value), and `dic_ids` (comma-joined dictionary ids, same order) must
    be captured from a real browser session (same technique as GDP_REAL) rather
    than guessed -- guessing measure_id=7 and a single dic_ids for a
    multi-dictionary index reliably returns HTTP 500, not wrong data, so this
    fails loudly rather than silently.

    `period_id` defaults to "7" (annual, "Год") but is overridable -- despite
    this function's name, the response's own date keys ('yMMYYYY', e.g.
    'y092012' for a Q3-2012 quarterly point) already carry the true month, not
    just the year, so a non-annual `period_id` (e.g. "5" for quarterly, found
    for HOUSING_PRICE_INDEX via the live ExtJS tree, same technique as above)
    is parsed correctly into a proper quarter-end date rather than silently
    collapsed into "one record per year" -- which would have produced multiple
    records sharing the same date and corrupted the series. This was caught
    live before shipping: an early attempt kept the old year-only parsing and
    it would have merged 4 quarters a year into duplicate December 31 dates.
    """
    body = {
        "p_parent_id": "", "p_index_id": index_id, "p_keyword": "",
        "p_period_id": period_id, "p_measure_id": measure_id, "p_term_id": NATIONAL_TERM_ID,
        "p_terms": terms or NATIONAL_TERM_ID, "p_dicIds": dic_ids, "idx": "0",
        "filter": '[{"property":null,"value":null}]', "id": "",
    }
    resp = requests.post(TALDAU_TREE_DATA_URL, data=body,
                          headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"}, timeout=30)
    resp.raise_for_status()
    content = resp.content
    _save_raw(indicator_id, content, "json", {
        "source_url": TALDAU_TREE_DATA_URL, "index_id": index_id, "request_body": body,
    })

    data = json.loads(content)
    match = next((entry for entry in data if entry.get("id") == NATIONAL_TERM_ID), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no tree node with id={NATIONAL_TERM_ID!r} in the response",
                "EXPECTED: the national root node",
                f"ACTUAL: {[e.get('id') for e in data]}",
                f"ACTION REQUIRED: inspect {TALDAU_TREE_DATA_URL} (index_id={index_id}) and update scripts/fetchers/bns.py",
            ])
        )

    records = []
    for key, value in match.items():
        if not (isinstance(key, str) and key.startswith("y") and key[1:].isdigit() and len(key) == 7):
            continue
        month_str, year_str = key[1:3], key[3:]
        try:
            month = int(month_str)
            year = int(year_str)
            v = float(value)
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        # DATE CONVENTION. Quarterly and annual Taldau series are stamped at the
        # PERIOD END, matching how the rest of this project dates those
        # frequencies. MONTHLY ones are stamped at the period START, because 113
        # of the project's 125 monthly series already do -- including CPI before
        # it moved to Taldau. Emitting month-end here silently broke every join
        # between CPI and the monthly production, trade and labour series, which
        # is a worse failure than an inconsistent-looking date because nothing
        # raises: the join just returns nothing.
        if period_id == TALDAU_PERIOD_MONTHLY:
            records.append({"date": f"{year:04d}-{month:02d}-01", "value": v})
        else:
            last_day = calendar.monthrange(year, month)[1]
            records.append({"date": f"{year:04d}-{month:02d}-{last_day:02d}", "value": v})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                "WHAT CHANGED: zero year/value pairs extracted from the national node",
                f"ACTUAL keys present: {list(match.keys())}",
                f"ACTION REQUIRED: inspect {TALDAU_TREE_DATA_URL} (index_id={index_id}) and update scripts/fetchers/bns.py",
            ])
        )

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": TALDAU_PERIOD_FREQUENCY.get(period_id, "annual"),
        "source_url": TALDAU_TREE_DATA_URL,
        "dataset_id": f"taldau-index-{index_id}",
        "note": note,
    }
    return records, manifest


def fetch_gdp_per_capita() -> tuple[list[dict], dict]:
    """Nominal GDP per capita, production method. Verified live 2026-08-30 via
    the shared Taldau mechanism (see fetch_gdp_real)."""
    return _fetch_taldau_annual_index(
        "2709380", "GDP_PER_CAPITA",
        note="Nominal GDP per capita, production method, KZT. Taldau indexId 2709380.",
    )


def fetch_gdp_deflator() -> tuple[list[dict], dict]:
    """GDP deflator, production method. Verified live 2026-08-30."""
    return _fetch_taldau_annual_index(
        "2970978", "GDP_DEFLATOR",
        note="GDP deflator, production method, % of prior period. Taldau indexId 2970978.",
    )


def fetch_gfcf() -> tuple[list[dict], dict]:
    """Gross fixed capital formation, national-accounts investment concept, KZT.
    Distinct from INVESTMENT (BNS's enterprise-survey 'investment in fixed
    capital' series). Verified live 2026-08-30."""
    return _fetch_taldau_annual_index(
        "700906", "GFCF",
        note="Gross fixed capital formation, national accounts, KZT. Distinct from the BNS/"
             "INVESTMENT enterprise-survey series. Taldau indexId 700906.",
    )


def fetch_gfcf_volume_index() -> tuple[list[dict], dict]:
    """Physical volume index of gross fixed capital formation. Verified live 2026-08-30."""
    return _fetch_taldau_annual_index(
        "700981", "GFCF_VOLUME_INDEX",
        note="Physical volume index of gross fixed capital formation, % of prior period. Taldau indexId 700981.",
    )


def fetch_net_exports() -> tuple[list[dict], dict]:
    """Net exports of goods and services, national accounts, KZT. Verified live 2026-08-30."""
    return _fetch_taldau_annual_index(
        "2709378", "NET_EXPORTS",
        note="Net exports of goods and services, national accounts, KZT. Taldau indexId 2709378.",
    )


def fetch_household_consumption() -> tuple[list[dict], dict]:
    """Household final consumption expenditure, national accounts, KZT. Verified live 2026-08-30."""
    return _fetch_taldau_annual_index(
        "700966", "HOUSEHOLD_CONSUMPTION",
        note="Household final consumption expenditure, national accounts, KZT. Taldau indexId 700966.",
    )


def fetch_compensation_employees() -> tuple[list[dict], dict]:
    """Compensation of employees, income-side national accounts, KZT. Verified live 2026-08-30."""
    return _fetch_taldau_annual_index(
        "700938", "COMPENSATION_EMPLOYEES",
        note="Compensation of employees, income account, KZT. Taldau indexId 700938.",
    )


def fetch_avg_wage() -> tuple[list[dict], dict]:
    """Average monthly nominal wage per worker, KZT. Taldau indexId 702972 (found
    under Taldau's "Статистика труда и занятости" category, GetIndustryByID/702832).

    Unlike the national-accounts indicators above, this one is classified across
    5 dictionaries at once (region, economic activity, locality type, enterprise
    size, sex) -- blind measure_id=7/dicIds=67 guessing (by analogy to GDP_REAL)
    returned HTTP 500. Cracked the same way as GDP_REAL: instrumented XHR in a
    real browser session to capture the actual request
    (measure_id=1; terms=741880,741885,741917,3629946,741935 -- the "Всего"/
    total value in each of the 5 dictionaries; dic_ids=68,859,776,2813,576).
    Verified live 2026-08-30 with a plain, stateless requests.post using these
    captured params. Values (KZT/month) are consistent with independently
    reported figures (e.g. ~150K KZT in 2017 rising to ~443K KZT average for
    2025, in the same range as BNS's own Q4-2025 press figure of 473K KZT --
    plausible since Q4 sits above the annual average in an up-trending series).
    """
    return _fetch_taldau_annual_index(
        "702972", "AVG_WAGE",
        note="Average monthly nominal wage per worker, KZT. Taldau indexId 702972.",
        measure_id="1", dic_ids="68,859,776,2813,576",
        terms="741880,741885,741917,3629946,741935",
    )


# More single-region-dimension Taldau national-accounts indices (same simple mechanism as
# GDP_REAL: measure_id=7, dicIds=67), verified live 2026-08-30 -- indexIds sourced from the
# same GetIndustryByID/700894 category list gathered during the GDP_REAL research.
def fetch_gdp_income_method() -> tuple[list[dict], dict]:
    """GDP, income method, KZT. Cross-checked: matches GDP_NOMINAL (production method)
    exactly for 2025 (159,608,552,900,000 both) -- as expected, since both are the same
    total GDP measured two different ways. Taldau indexId 2709435."""
    return _fetch_taldau_annual_index(
        "2709435", "GDP_INCOME_METHOD",
        note="GDP, income method, KZT. Taldau indexId 2709435.",
    )


def fetch_gross_output() -> tuple[list[dict], dict]:
    """Gross output, production account, KZT. Taldau indexId 700912."""
    return _fetch_taldau_annual_index("700912", "GROSS_OUTPUT", note="Gross output, production account, KZT. Taldau indexId 700912.")


def fetch_taxes_on_products() -> tuple[list[dict], dict]:
    """Taxes on products, production account, KZT. Taldau indexId 700928."""
    return _fetch_taldau_annual_index("700928", "TAXES_ON_PRODUCTS", note="Taxes on products, production account, KZT. Taldau indexId 700928.")


def fetch_net_taxes_on_products() -> tuple[list[dict], dict]:
    """Net taxes on products (taxes minus subsidies), production account, KZT. Taldau indexId 700925."""
    return _fetch_taldau_annual_index("700925", "NET_TAXES_ON_PRODUCTS", note="Net taxes on products, production account, KZT. Taldau indexId 700925.")


def fetch_subsidies() -> tuple[list[dict], dict]:
    """Subsidies on production and imports, KZT. Taldau indexId 2709434."""
    return _fetch_taldau_annual_index("2709434", "SUBSIDIES", note="Subsidies on production and imports, KZT. Taldau indexId 2709434.")


def fetch_intermediate_consumption() -> tuple[list[dict], dict]:
    """Intermediate consumption, production account, KZT. Taldau indexId 700914."""
    return _fetch_taldau_annual_index("700914", "INTERMEDIATE_CONSUMPTION", note="Intermediate consumption, production account, KZT. Taldau indexId 700914.")


def fetch_gross_accumulation() -> tuple[list[dict], dict]:
    """Gross accumulation, national accounts, KZT. Same 2010-2013 gap as GFCF/NET_EXPORTS/
    HOUSEHOLD_CONSUMPTION (22 of 26 possible years). Taldau indexId 2709376."""
    return _fetch_taldau_annual_index("2709376", "GROSS_ACCUMULATION", note="Gross accumulation, national accounts, KZT. Same 2010-2013 gap as GFCF. Taldau indexId 2709376.")


def fetch_import_volume_index() -> tuple[list[dict], dict]:
    """Physical volume index of imports of goods and services, % of prior period.
    Same 2010-2013 gap as GFCF. Taldau indexId 700982."""
    return _fetch_taldau_annual_index("700982", "IMPORT_VOLUME_INDEX", note="Physical volume index of imports of goods and services, % of prior period. Same 2010-2013 gap as GFCF. Taldau indexId 700982.")


def fetch_export_volume_index() -> tuple[list[dict], dict]:
    """Physical volume index of exports of goods and services, % of prior period.
    Same 2010-2013 gap as GFCF. Taldau indexId 700983."""
    return _fetch_taldau_annual_index("700983", "EXPORT_VOLUME_INDEX", note="Physical volume index of exports of goods and services, % of prior period. Same 2010-2013 gap as GFCF. Taldau indexId 700983.")


def fetch_total_consumption_expenditure() -> tuple[list[dict], dict]:
    """Total final consumption expenditure (households + government), KZT.
    Same 2010-2013 gap as GFCF. Taldau indexId 700965."""
    return _fetch_taldau_annual_index("700965", "TOTAL_CONSUMPTION_EXPENDITURE", note="Total final consumption expenditure, KZT. Same 2010-2013 gap as GFCF. Taldau indexId 700965.")


def fetch_capital_consumption() -> tuple[list[dict], dict]:
    """Consumption of fixed capital (depreciation), income account, KZT. Taldau indexId 700944."""
    return _fetch_taldau_annual_index("700944", "CAPITAL_CONSUMPTION", note="Consumption of fixed capital (depreciation), income account, KZT. Taldau indexId 700944.")


def fetch_retail_trade() -> tuple[list[dict], dict]:
    """Retail trade turnover, value terms, KZT. Taldau indexId 702038 (code 171202,
    "Объем розничной торговли в стоимостном выражении"), found under Taldau's
    "Статистика внутренней торговли" category (GetIndustryByID/702017) via the
    site's own keyword search API (POST /ru/Search/getSearchPageGridData,
    keyword="розничной торговли") -- the two indexIds found earlier via a plain
    web search (701830, 703076) both turned out to be wrong indicators entirely
    (701830 is fixed-capital investment by use, code 161103; 703076 was never
    identified) and were discarded rather than guessed into use.

    Classified across 3 dictionaries at once (region, ownership form, goods
    type) -- blind measure_id=7/dicIds=67 guessing returned HTTP 500, same
    failure mode as AVG_WAGE. Cracked without a fresh XHR capture: queried the
    already-loaded ExtJS page's live component tree directly
    (Ext.ComponentQuery.query('treepanel') -> indexTreeGrid's store.lastOptions)
    to read the exact params the page itself was already using
    (measure_id=1; terms=741880,741907,741894 -- the "Всего" total in each of
    the 3 dictionaries; dic_ids=67,59,676). Verified live 2026-08-30 with a
    plain, stateless requests.post using these params. Values are plausible
    KZT retail turnover: ~558 billion in 2000 rising to ~27.7 trillion in 2025,
    consistent with BNS's own published growth-rate commentary for this series.
    """
    return _fetch_taldau_annual_index(
        "702038", "RETAIL_TRADE",
        note="Retail trade turnover, value terms, KZT. Taldau indexId 702038.",
        measure_id="1", dic_ids="67,59,676",
        terms="741880,741907,741894",
    )


def fetch_construction() -> tuple[list[dict], dict]:
    """Volume of construction works (services) performed, KZT. Taldau indexId
    701885 (code 162101, "Объем выполненных строительных работ (услуг)"), found
    under Taldau's "Статистика инвестиций и строительства" category via the
    site's own keyword search API (keyword="объем строительных работ") --
    resolves the CONSTRUCTION_NOT_CONNECTED gap logged as "not researched" in
    an earlier session.

    Classified across 4 dictionaries (region, ownership form, activity type, a
    4th unlabeled dimension) -- the default single-dimension guess 500'd.
    Params recovered via the same live-ExtJS-tree technique as RETAIL_TRADE
    (Ext.ComponentQuery.query('indexTreeGrid')[0].store.getProxy().extraParams)
    rather than a fresh XHR capture. Verified live 2026-08-30: ~4.9 trillion KZT
    (2020) rising to ~10.8 trillion KZT (2025), a plausible scale and trend for
    total construction works volume.
    """
    return _fetch_taldau_annual_index(
        "701885", "CONSTRUCTION",
        note="Volume of construction works (services) performed, KZT. Taldau indexId 701885.",
        measure_id="1", dic_ids="68,60,71,2987",
        terms="741880,741908,741919,18753820",
    )


def fetch_real_wage_index() -> tuple[list[dict], dict]:
    """Real wage index, % of prior period (100 = no change). Taldau indexId
    702976 (code 25210103, "индекс реальной заработной платы") -- companion to
    AVG_WAGE (nominal KZT level); this is the inflation-adjusted growth rate.
    Found via keyword search ("индекс реальной заработной платы"). Classified
    across 5 dictionaries, same shape as AVG_WAGE; params recovered via the
    live ExtJS component tree. Verified live 2026-08-30: values in the
    98-108% range, consistent with real wages roughly tracking (slightly
    above or below) the prior year in most years -- plausible.
    """
    return _fetch_taldau_annual_index(
        "702976", "REAL_WAGE_INDEX",
        note="Real wage index, % of prior period. Taldau indexId 702976.",
        measure_id="7", dic_ids="68,859,2813,576,848",
        terms="741880,741885,3629946,741935,2695730",
    )


def fetch_births_total() -> tuple[list[dict], dict]:
    """Number of live births, persons/year. Taldau indexId 703839 (code
    612101, "Число родившихся (живыми)"), found via keyword search
    ("родившихся"). Classified across 3 dictionaries; params recovered via
    the live ExtJS component tree. Verified live 2026-08-30: ~403,893 (2022)
    declining to ~335,005 (2025), a plausible birth-count trajectory and
    magnitude for Kazakhstan's ~20 million population.
    """
    return _fetch_taldau_annual_index(
        "703839", "BIRTHS_TOTAL",
        note="Number of live births, persons/year. Taldau indexId 703839.",
        measure_id="23", dic_ids="67,749,576",
        terms="741880,741917,741935",
    )


def fetch_deaths_total() -> tuple[list[dict], dict]:
    """Number of deaths, persons/year. Taldau indexId 703847 (code 612201,
    "Число умерших"), found via keyword search ("умерших"). Same 3-dictionary
    shape as BIRTHS_TOTAL; params recovered via the live ExtJS component tree.
    Verified live 2026-08-30: ~130,000-135,000/year (2022-2025), a plausible
    death-count magnitude for Kazakhstan's ~20 million population.
    """
    return _fetch_taldau_annual_index(
        "703847", "DEATHS_TOTAL",
        note="Number of deaths, persons/year. Taldau indexId 703847.",
        measure_id="23", dic_ids="67,749,576",
        terms="741880,741917,741935",
    )


MONTH_CUMULATIVE_DECEMBER_KEY_RE = re.compile(r"^y12(\d{4})$")


def _fetch_taldau_annual_from_monthly_cumulative(
    index_id: str, indicator_id: str, note: str, unit_note: str,
    measure_id: str, dic_ids: str, terms: str,
) -> tuple[list[dict], dict]:
    """Shared fetcher for Taldau indicators published as period_id=8 ("month
    with accumulation" / year-to-date cumulative) rather than period_id=7
    (plain annual) -- discovered for HOUSING_COMMISSIONED and PPI, both left
    not_connected in an earlier session because their keys are 'y{MM}{YYYY}'
    (e.g. 'y042026' = cumulative Jan-Apr 2026), which the plain-annual
    _fetch_taldau_annual_index helper's date-parsing logic would silently
    mis-handle (it takes the LAST 4 characters of any 'y...' key as the year
    and stamps every match at Dec 31, so multiple months in the same year
    would collide onto one date rather than erroring loudly).

    This helper instead takes ONLY the December key ('y12{YYYY}') per year as
    that year's annual total -- BNS's own convention for both a genuine
    year-to-date SUM (HOUSING_COMMISSIONED: monotonically increasing through
    the year) and a year-to-date cumulative AVERAGE (PPI: not monotonic,
    moves toward the eventual December figure which is the number BNS itself
    publishes as "the" annual PPI). The intermediate monthly values are
    intentionally NOT emitted as independent monthly datapoints in either
    case, since presenting a cumulative figure as if it were a monthly
    increment would misrepresent the series.
    """
    body = {
        "p_parent_id": "", "p_index_id": index_id, "p_keyword": "",
        "p_period_id": "8", "p_measure_id": measure_id, "p_term_id": NATIONAL_TERM_ID,
        "p_terms": terms, "p_dicIds": dic_ids, "idx": "0",
        "filter": '[{"property":null,"value":null}]', "id": "",
    }
    resp = requests.post(TALDAU_TREE_DATA_URL, data=body,
                          headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"}, timeout=30)
    resp.raise_for_status()
    content = resp.content
    _save_raw(indicator_id, content, "json", {
        "source_url": TALDAU_TREE_DATA_URL, "index_id": index_id, "request_body": body,
    })

    data = json.loads(content)
    match = next((entry for entry in data if entry.get("id") == NATIONAL_TERM_ID), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no tree node with id={NATIONAL_TERM_ID!r} in the response",
                "EXPECTED: the national root node",
                f"ACTUAL: {[e.get('id') for e in data]}",
                f"ACTION REQUIRED: inspect {TALDAU_TREE_DATA_URL} (index_id={index_id}) and update scripts/fetchers/bns.py",
            ])
        )

    records = []
    for key, value in match.items():
        m = MONTH_CUMULATIVE_DECEMBER_KEY_RE.match(key) if isinstance(key, str) else None
        if not m:
            continue
        year = int(m.group(1))
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        records.append({"date": f"{year:04d}-12-31", "value": v})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                "WHAT CHANGED: zero December ('y12{YYYY}') keys found on the national node",
                f"ACTUAL keys present: {list(match.keys())}",
                f"ACTION REQUIRED: inspect {TALDAU_TREE_DATA_URL} (index_id={index_id}) and update scripts/fetchers/bns.py",
            ])
        )

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": TALDAU_TREE_DATA_URL,
        "dataset_id": f"taldau-index-{index_id}",
        "note": f"{unit_note} Full-year total taken from the December year-to-date-cumulative "
                "key; intermediate months not emitted.",
    }
    return records, manifest


def fetch_housing_commissioned() -> tuple[list[dict], dict]:
    """Housing commissioned, total floor area, m2 per 1000 population, annual.
    Taldau indexId 701938 (code 163212, "Ввод в эксплуатацию общей площади
    жилых домов в расчете на 1000 человек населения"). Only a per-1000-
    population variant exists on Taldau, no absolute-total variant was found.
    Verified live 2026-08-30 that the December key is a genuine year-to-date
    SUM (confirmed monotonically non-decreasing month-over-month within 2025:
    Jan=38 ... Dec=986.2). Values: 441.2 (2014) rising to 986.2 (2025)
    m2/1000 population, a plausible trend for housing construction intensity
    over a decade. See _fetch_taldau_annual_from_monthly_cumulative for why
    this needed a dedicated (period_id=8) mechanism.
    """
    return _fetch_taldau_annual_from_monthly_cumulative(
        "701938", "HOUSING_COMMISSIONED",
        note="Housing commissioned, total floor area, m2 per 1000 population. Taldau indexId 701938.",
        unit_note="m2 per 1000 population.",
        measure_id="1", dic_ids="68", terms=NATIONAL_TERM_ID,
    )


def fetch_ppi() -> tuple[list[dict], dict]:
    """Producer price index (industrial products), % of same period prior
    year, cumulative from start of year -- BNS's own standard annual PPI
    figure (the December value). Taldau indexId 703039 (code 261201, "Индекс
    цен предприятий-производителей промышленной продукции (товаров, услуг)"),
    found via Taldau's site search API. Resolves the PPI gap logged earlier
    as not_connected (the gov.kz CSV/JSON route was found stale/malformed at
    the source). Classified across 5 dictionaries; params recovered via the
    live ExtJS component tree, same technique as CONSTRUCTION/RETAIL_TRADE.
    Verified live 2026-08-30: values NOT monotonic within a year (2025:
    Jan=109.4 declining to Dec=107.1, a cumulative average rather than a
    cumulative sum, unlike HOUSING_COMMISSIONED) -- confirming December is
    genuinely BNS's own "the year's PPI" figure, same convention as how CPI's
    annual figure is reported, not an artifact of picking an arbitrary month.
    """
    return _fetch_taldau_annual_from_monthly_cumulative(
        "703039", "PPI",
        note="Producer price index, industrial products, % of same period prior year. Taldau indexId 703039.",
        unit_note="% of same period prior year (cumulative from start of year).",
        measure_id="1", dic_ids="67,848,2513,2854,3068",
        terms="741880,2695732,4150464,15698719,18716910",
    )


def fetch_wholesale_trade() -> tuple[list[dict], dict]:
    """Wholesale trade turnover, value terms, KZT, annual -- companion to
    RETAIL_TRADE. Taldau indexId 702020 (code 171101, "Объем оптовой торговли
    в стоимостном выражении"), found via the same site search technique as
    RETAIL_TRADE. Same 3-dictionary shape (region/ownership form/goods type),
    same "Всего" terms. Verified live 2026-08-30: ~31.1 trillion KZT (2021)
    to ~47.2 trillion KZT (2024). Cross-checked: wholesale/retail ratio for
    2024 (47.164T / 23.559T ~= 2.0) matches the ~66%/33% wholesale/retail
    split for Kazakhstan's domestic trade sector cited in independent BNS
    commentary found during RETAIL_TRADE's own research.
    """
    return _fetch_taldau_annual_index(
        "702020", "WHOLESALE_TRADE",
        note="Wholesale trade turnover, value terms, KZT. Taldau indexId 702020.",
        measure_id="1", dic_ids="68,59,676",
        terms="741880,741907,741894",
    )


def fetch_retail_trade_volume_index() -> tuple[list[dict], dict]:
    """Physical volume index of retail trade, % of prior period -- companion
    to RETAIL_TRADE (which is in value/nominal terms). Taldau indexId 702041
    (code 171203, "Индекс физического объема розничной торговли"). Classified
    across 6 dictionaries; params recovered via the live ExtJS component
    tree. Verified live 2026-08-30: 105-111% range (2021-2024), consistent
    with the ~107% figure cited in independent BNS commentary for a recent
    comparable period.
    """
    return _fetch_taldau_annual_index(
        "702041", "RETAIL_TRADE_VOLUME_INDEX",
        note="Physical volume index of retail trade, % of prior period. Taldau indexId 702041.",
        measure_id="7", dic_ids="68,776,676,848,853,2985",
        terms="741880,741917,741894,2695732,2658135,18121059",
    )


def fetch_emissions() -> tuple[list[dict], dict]:
    """Volume of atmospheric pollutant emissions, metric tonnes, annual.
    Taldau indexId 705070 (code 157502, "Объем выбросов загрязняющих веществ
    в атмосферу"). Classified across 3 dictionaries; params recovered via the
    live ExtJS component tree. IMPORTANT UNIT NOTE: the raw API value is in
    KILOGRAMS, not the metric tonnes shown on Taldau's own human-facing
    summary page -- confirmed by comparing the category page's displayed 2025
    figure (2,280,913.734 tonnes) against this API call's raw 2025 value
    (2,280,913,734.12), an exact /1000 relationship. Converted to tonnes here
    to match the officially displayed unit, the same pattern as Minfin's
    thousand-KZT-to-million-KZT conversion for GOV_DEBT.
    """
    records, manifest = _fetch_taldau_annual_index(
        "705070", "EMISSIONS",
        note="Volume of atmospheric pollutant emissions, metric tonnes (converted from the API's "
             "raw kg values -- see fetch_emissions docstring). Taldau indexId 705070.",
        measure_id="11", dic_ids="68,1212,3042",
        terms="741880,741885,16194312",
    )
    for r in records:
        r["value"] = r["value"] / 1000.0
    manifest["note"] = manifest.get("note", "") + " Values converted from kg (source's raw unit) to metric tonnes."
    return records, manifest


def fetch_freight_turnover() -> tuple[list[dict], dict]:
    """Freight turnover, tonne-km, annual -- companion to PASSENGER_TURNOVER.
    Taldau indexId 702179 (code 181104, "Грузооборот"). Classified across 4
    dictionaries; params recovered via the live ExtJS component tree.
    Verified live 2026-08-30: ~504-597 billion tonne-km (2022-2025), a
    plausible order of magnitude for Kazakhstan's freight transport sector.
    """
    return _fetch_taldau_annual_index(
        "702179", "FREIGHT_TURNOVER",
        note="Freight turnover, tonne-km. Taldau indexId 702179.",
        measure_id="43", dic_ids="68,1214,59,4309",
        terms="741880,741335,741907,19805998",
    )


def fetch_passenger_turnover() -> tuple[list[dict], dict]:
    """Passenger turnover, passenger-km, annual -- companion to
    FREIGHT_TURNOVER. Taldau indexId 702177 (code 181102, "Пассажирооборот").
    Classified across 7 dictionaries; params recovered via the live ExtJS
    component tree. Verified live 2026-08-30: ~247-267 billion passenger-km
    (2014-2016), a plausible order of magnitude for Kazakhstan's passenger
    transport sector.
    """
    return _fetch_taldau_annual_index(
        "702177", "PASSENGER_TURNOVER",
        note="Passenger turnover, passenger-km. Taldau indexId 702177.",
        measure_id="41", dic_ids="67,1214,90,59,230,681,2984",
        terms="741880,741335,741927,741907,741906,808076,17901749",
    )


def fetch_agriculture_output() -> tuple[list[dict], dict]:
    """Gross agricultural output (crop + livestock production), KZT, annual.
    Taldau indexId 701189, found by browsing the "Статистика сельского,
    лесного, охотничьего и рыбного хозяйства" category page directly
    (GetIndustryByID/701185) rather than keyword search -- several keyword
    phrasings for this indicator returned zero results even though the
    category's own "main indicators" summary listed it as the very first
    entry. Classified across 3 dictionaries; params recovered via the live
    ExtJS component tree. Verified live 2026-08-30: value matches the
    category page's own displayed 2025 figure (9,704,982.0 million KZT)
    exactly once expressed in the same KZT units used throughout this
    project's other BNS national-accounts-style indicators (no unit
    conversion needed, unlike EMISSIONS).
    """
    return _fetch_taldau_annual_index(
        "701189", "AGRICULTURE_OUTPUT",
        note="Gross agricultural output (crop + livestock), KZT. Taldau indexId 701189.",
        measure_id="1", dic_ids="67,488,773",
        terms="741880,450122,734928",
    )


def fetch_per_capita_income() -> tuple[list[dict], dict]:
    """Average per capita nominal money income, KZT/month, annual. Taldau
    indexId 704447, found by browsing the "Статистика уровня жизни" category
    page (GetIndustryByID/704444). Standard single-dimension mechanism worked
    directly (measure_id=7, dicIds=67) -- no live ExtJS capture needed.
    Verified live 2026-08-30: matches the category page's own displayed 2025
    figure (238,070 KZT) exactly.
    """
    return _fetch_taldau_annual_index(
        "704447", "PER_CAPITA_INCOME",
        note="Average per capita nominal money income, KZT/month. Taldau indexId 704447.",
    )


def fetch_real_income_index() -> tuple[list[dict], dict]:
    """Real money income index, % of prior period -- companion to
    PER_CAPITA_INCOME (nominal level). Taldau indexId 704449, found the same
    way as PER_CAPITA_INCOME. Standard single-dimension mechanism worked
    directly. Verified live 2026-08-30: matches the category page's own
    displayed 2025 figure (98.9%) exactly. POVERTY_RATE was searched for on
    this same category page and not found -- only these two income
    indicators have RK-wide totals shown at the category level.
    """
    return _fetch_taldau_annual_index(
        "704449", "REAL_INCOME_INDEX",
        note="Real money income index, % of prior period. Taldau indexId 704449.",
    )


def fetch_telecom_services() -> tuple[list[dict], dict]:
    """Telecommunications services volume, KZT, annual. Taldau indexId
    702379 (code 192101, "Объем услуг связи по видам"), found via keyword
    search ("связи"). Classified across 4 dictionaries; params recovered via
    the live ExtJS component tree. Verified live 2026-08-30: ~1.12-1.50
    trillion KZT (2022-2025), a plausible scale for Kazakhstan's telecom
    sector.
    """
    return _fetch_taldau_annual_index(
        "702379", "TELECOM_SERVICES",
        note="Telecommunications services volume, KZT. Taldau indexId 702379.",
        measure_id="1", dic_ids="68,59,230,1693",
        terms="741880,741907,741906,18064429",
    )


def fetch_doctors_total() -> tuple[list[dict], dict]:
    """Total number of doctors (all specialties), persons, year-end, annual.
    Taldau indexId 704315 (code 631501, "Списочная численность врачей всех
    специальностей на конец года"), found via keyword search ("численность
    врачей") -- picked over the per-10000-population variant (704316) as the
    absolute headline count. Standard single-dimension mechanism worked
    directly. Verified live 2026-08-30: ~78,227 (2021) rising to ~83,379
    (2024), a plausible count and trend for Kazakhstan's medical workforce.
    """
    return _fetch_taldau_annual_index(
        "704315", "DOCTORS_TOTAL",
        note="Total number of doctors (all specialties), persons, year-end. Taldau indexId 704315.",
    )


def fetch_energy_intensity() -> tuple[list[dict], dict]:
    """Energy intensity of GDP, tonnes of oil equivalent per thousand USD.
    Taldau indexId 702139, found by browsing the "Статистика энергетики и
    товарных рынков" category page (GetIndustryByID/18814801) -- external
    trade, tourism, education, healthcare, and services category pages were
    also browsed this session and found empty or stale (2008-only data),
    unlike energy which had two live current indicators. Standard single-
    dimension mechanism worked directly. Verified live 2026-08-30: ~0.30-0.32
    toe/thousand USD (2023-2025).
    """
    return _fetch_taldau_annual_index(
        "702139", "ENERGY_INTENSITY",
        note="Energy intensity of GDP, toe per thousand USD. Taldau indexId 702139.",
    )


def fetch_energy_consumption() -> tuple[list[dict], dict]:
    """Total primary energy consumption, thousand tonnes of oil equivalent,
    annual -- companion to ENERGY_INTENSITY. Taldau indexId 77394629, same
    category page. Classified across 2 dictionaries; params recovered via
    the live ExtJS component tree. Verified live 2026-08-30: matches the
    category page's own displayed 2025 figure (80,051 thousand toe, rounded)
    almost exactly (80,050.5).
    """
    return _fetch_taldau_annual_index(
        "77394629", "ENERGY_CONSUMPTION",
        note="Total primary energy consumption, thousand toe. Taldau indexId 77394629.",
        measure_id="2908", dic_ids="68,4834",
        terms="741880,77356561",
    )


def parse_sheet_dump_row(data: dict, sheet: str, label: str) -> list[dict]:
    """[{date: YYYY-12-31, value}] from a BNS xlsx-as-JSON dump ({sheet: [row dicts]}): the
    header row is the one whose cells hold years, the data row the one with a cell equal to
    `label` (whitespace-normalised)."""
    rows = data.get(sheet)
    if not isinstance(rows, list):
        return []
    years: dict[str, int] = {}
    for r in rows:
        cand = {k: int(v) for k, v in r.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
                and float(v).is_integer() and 1900 <= v <= 2100}
        if len(cand) >= 5:
            years = cand
            break
    target = " ".join(label.split())
    for r in rows:
        if any(isinstance(v, str) and " ".join(v.split()) == target for v in r.values()):
            out = []
            for k, y in years.items():
                v = r.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out.append({"date": f"{y:04d}-12-31", "value": float(v)})
            if out:                                 # a title row repeats the label without values
                return sorted(out, key=lambda x: x["date"])
    return []


def fetch_final_energy_consumption() -> tuple[list[dict], dict]:
    """Total final energy consumption, thousand tonnes of oil equivalent,
    annual -- companion to ENERGY_CONSUMPTION (primary consumption, which
    includes conversion losses this excludes). Found on the "Статистика
    энергетики" open-data page's own "Динамические ряды" list (a stat.gov.kz
    open-data json_cube file, element_id=8582 -- the SAME mechanism as
    GDP_NOMINAL/IND_PROD, distinct from the Taldau mechanism used for
    ENERGY_CONSUMPTION itself). Verified live 2026-08-30: single cube slice
    (region='РЕСПУБЛИКА КАЗАХСТАН', 'Всего'), 11 annual periods (2015-2025),
    values ~38,378 to ~48,483 thousand toe -- consistently below
    ENERGY_CONSUMPTION's primary-consumption values (~70,252-80,050 for the
    overlapping years), the expected direction since final consumption
    excludes conversion/transformation losses.
    """
    element_id = 8582
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw("FINAL_ENERGY_CONSUMPTION", content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    # 2026-09-26: BNS replaced this element's json_cube (a list of slices with termNames)
    # by a dump of the xlsx -- {sheet name: [row dicts]} -- whose sheet «Показатель» carries
    # the series from 1991 (the cube began in 2015). The overlapping 2015-2025 values are
    # the same. Both formats are read; anything else is a structural change.
    if isinstance(data, dict):
        records = parse_sheet_dump_row(data, "Показатель", "Общее конечное потребление энергии")
        if len(records) < 11:
            raise validation.StructuralChangeError(
                f"bns/FINAL_ENERGY_CONSUMPTION: sheet dump of {url} gave {len(records)} years; "
                f"sheets {list(data)[:6]}")
        return records, {
            "frequency": "annual", "source_url": url, "dataset_id": str(element_id),
            "note": "Thousand toe, from 1991 (BNS element 8582, sheet «Показатель»). Excludes "
                    "conversion/transformation losses, unlike primary consumption (ENERGY_CONSUMPTION).",
        }
    if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
        raise validation.StructuralChangeError(
            f"bns/FINAL_ENERGY_CONSUMPTION: {url} is neither a json_cube list nor a sheet dump ({type(data).__name__})")

    TARGET = ["РЕСПУБЛИКА КАЗАХСТАН", "Всего"]
    match = next((entry for entry in data if entry.get("termNames") == TARGET), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/FINAL_ENERGY_CONSUMPTION",
                "WHAT CHANGED: no cube slice matched the expected national/total combo",
                f"EXPECTED termNames: {TARGET}",
                "ACTUAL: no matching entry in the downloaded file",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        )

    records = []
    for p in match["periods"]:
        try:
            records.append({"date": _dd_mm_yyyy_to_iso(p["date"]), "value": float(p["value"])})
        except (ValueError, KeyError):
            continue
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": url,
        "dataset_id": str(element_id),
        "note": "Thousand toe. Excludes conversion/transformation losses, unlike primary consumption (ENERGY_CONSUMPTION).",
    }
    return records, manifest


def fetch_renewable_energy_share() -> tuple[list[dict], dict]:
    """Share of renewable energy sources in electricity production
    (excluding large hydro), %, annual. Found on the same "Статистика
    энергетики" open-data page (element_id=8581, same json_cube mechanism as
    FINAL_ENERGY_CONSUMPTION). Verified live 2026-08-30: single cube slice
    (region='РЕСПУБЛИКА КАЗАХСТАН' only, no further dimension), 5 annual
    periods (2021-2025), rising from 3.46% to 7.02% -- a plausible growth
    trend for a rapidly expanding renewables sector, and matches the page's
    own displayed "Key Indicator" figure (7.0%, rounded) for the latest year.
    """
    element_id = 8581
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw("RENEWABLE_ENERGY_SHARE", content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    TARGET = ["РЕСПУБЛИКА КАЗАХСТАН"]
    match = next((entry for entry in data if entry.get("termNames") == TARGET), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/RENEWABLE_ENERGY_SHARE",
                "WHAT CHANGED: no cube slice matched the expected national combo",
                f"EXPECTED termNames: {TARGET}",
                "ACTUAL: no matching entry in the downloaded file",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        )

    records = []
    for p in match["periods"]:
        try:
            records.append({"date": _dd_mm_yyyy_to_iso(p["date"]), "value": float(p["value"])})
        except (ValueError, KeyError):
            continue
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": url,
        "dataset_id": str(element_id),
        "note": "%. Excludes large hydroelectric power stations from the renewable total.",
    }
    return records, manifest


def fetch_poverty_headcount() -> tuple[list[dict], dict]:
    """Total population with income below the national subsistence minimum
    (величина прожиточного минимума) -- BNS's own official poverty headcount,
    persons, annual. Taldau indexId 2928350 (code 64410201, "Общая
    численность населения с доходами ниже величины прожиточного минимума"),
    found via keyword search ("доходами ниже величины прожиточного
    минимума"). Resolves the POVERTY_RATE gap noted in multiple earlier
    sessions -- confirmed via the indicator's own "Паспорт" (passport) page
    that this is the genuine national headline methodology (household budget
    survey D003/D004/D008, "Методологическое положение по статистике,
    Издание 4, Астана 2018"), not a fabricated proxy.

    Deliberately an ABSOLUTE COUNT, not a %: only a headcount series was
    found (this one, plus a parallel households-count variant and gender-of-
    household-head breakdowns) -- no distinct population-SHARE (%) series was
    found anywhere on Taldau despite repeated searches across multiple
    sessions. Computing a % ourselves (headcount / POPULATION_BNS) was
    deliberately NOT done, consistent with this project's practice of not
    fabricating derived ratios the source agency doesn't itself publish.

    Values are genuinely small (~90,000-147,000 range, 2010-2024) --
    initially looked implausibly low against commonly-cited international
    poverty-rate figures (which use different, higher thresholds), but
    confirmed correct: BNS's own national subsistence-minimum threshold
    produces a low measured population share by design, and the values
    exactly match the indicator's own displayed chart on Taldau.

    A related indicator, "Величина прожиточного минимума" (the subsistence
    minimum threshold itself, KZT/month, indexId 704492), was also found but
    NOT implemented -- its Taldau tree returns a hidden intermediate node
    requiring genuine parent/child recursion (a different, deeper API
    interaction pattern than every other indicator connected this session),
    not a one-shot flat query. Left for a future session with budget for
    that specific capability.
    """
    return _fetch_taldau_annual_index(
        "2928350", "POVERTY_HEADCOUNT",
        note="Population below the national subsistence minimum, persons. Taldau indexId 2928350.",
        measure_id="23", dic_ids="67,270",
        terms="741880,545805",
    )


def fetch_migration_arrivals() -> tuple[list[dict], dict]:
    """External migration arrivals (immigration), national, annual, persons.
    Taldau indexId 2929752 (code 613201, "Внешняя миграция по всем потокам -
    прибытие"), found via the site's own keyword search API (keyword=
    "миграция") among a cluster of related migration indicators (internal
    migration, migration by CIS/non-CIS partner, migration broken down by
    marital status/education/occupation) -- this "all flows" arrivals total
    was picked as the clean headline external-migration figure over the
    more granular partner/demographic breakdowns.

    Classified across 4 dictionaries (region, plus 3 more) -- the default
    single-dimension guess (measure_id=7, dic_ids=67) 500'd, same failure
    mode as AVG_WAGE/RETAIL_TRADE/CONSTRUCTION. Params recovered via the
    live ExtJS component tree technique (same as those indicators):
    Ext.ComponentQuery.query('indexTreeGrid')[0].store.getProxy().extraParams
    on the live page (https://taldau.stat.gov.kz/ru/NewIndex/GetIndex/2929752),
    giving measure_id=23, dic_ids=67,749,76,576, terms=741880,741917,39360,741935.
    Verified live 2026-08-31 with a plain, cookie-less requests.post using
    these params, and cross-checked the extracted 2000-2025 values against
    the page's own rendered chart/table -- exact match (e.g. 2000: 47,442;
    2025: 23,761)."""
    return _fetch_taldau_annual_index(
        "2929752", "MIGRATION_ARRIVALS",
        note="External migration arrivals (immigration), national total, persons. All migration "
        "flows combined (not broken down by CIS/non-CIS partner or demographic group). Taldau "
        "indexId 2929752.",
        measure_id="23", dic_ids="67,749,76,576",
        terms="741880,741917,39360,741935",
    )


def fetch_migration_departures() -> tuple[list[dict], dict]:
    """External migration departures (emigration), national, annual, persons.
    Taldau indexId 2929753 (code 613202, "Внешняя миграция по всем потокам -
    выбытие") -- the paired "departures" counterpart to MIGRATION_ARRIVALS,
    found in the same search. Same 4-dictionary classification and params as
    MIGRATION_ARRIVALS confirmed to work for this index too (both indices
    share the same underlying region/demographic dictionary structure, per
    the site's own paired-indicator convention). Verified live 2026-08-31:
    2000: 155,749 departures vs only 47,442 arrivals that same year (a large
    net outflow, consistent with Kazakhstan's well-documented post-Soviet
    emigration wave in that period) falling to 7,608 by 2025, well below
    2025 arrivals (23,761) -- a plausible reversal to net inflow in recent
    years."""
    return _fetch_taldau_annual_index(
        "2929753", "MIGRATION_DEPARTURES",
        note="External migration departures (emigration), national total, persons. All migration "
        "flows combined (not broken down by CIS/non-CIS partner or demographic group). Taldau "
        "indexId 2929753.",
        measure_id="23", dic_ids="67,749,76,576",
        terms="741880,741917,39360,741935",
    )


def fetch_labor_productivity() -> tuple[list[dict], dict]:
    """Labor productivity, national, annual, KZT per employed person. Taldau
    indexId 4023003 (code 111216, "производительность труда"), the only hit
    for a keyword search on that exact phrase. Verified live 2026-08-31 with
    the default single-dimension (region-only) params -- no browser-based
    parameter cracking needed for this one, unlike most other Taldau
    indicators connected this session. 26 annual values (2000-2025), rising
    from 395,200 to 14,791,000 KZT/worker -- plausible order of magnitude
    against GDP_NOMINAL (~99.7 trillion KZT in 2025) divided by Kazakhstan's
    roughly 9 million employed persons (~11.1 million KZT/worker), close
    enough to the actual figure given this uses a different underlying
    formula (likely gross value added per worker, not GDP per worker) --
    not cross-checked to the decimal, just confirmed to be the right order
    of magnitude rather than a wildly wrong unit or scale.

    A related search for "индекс цен на жилье" (housing price index) also
    found a single candidate (indexId 703083, code 261605, "Индексы цен на
    рынке жилья") -- classified across 3 dictionaries, params recovered via
    the live ExtJS tree (measure_id=7, dicIds=67,848,2817,
    terms=741880,2695732,18120823, quarterly period_id=5) and confirmed to
    return real data (35 quarterly points), but NOT implemented: the
    source's OWN displayed period list ends at Q4 2020 -- this series is
    discontinued/stale on BNS's own site, not a fetcher problem, and adding
    a 5+ year stale series didn't meet this project's bar for current data.
    Investigating this quarterly index did surface and fix a real latent bug
    in _fetch_taldau_annual_index, though: it always stamped records at
    year-end (Dec 31) regardless of the response's own month, which would
    have silently collapsed 4 quarters into duplicate December 31 dates for
    any future quarterly index -- fixed by parsing the actual month out of
    the response's 'yMMYYYY' keys instead of assuming year-end, with zero
    behavior change for already-shipped annual indicators (re-verified live
    against GDP_REAL after the change)."""
    return _fetch_taldau_annual_index(
        "4023003", "LABOR_PRODUCTIVITY",
        note="Labor productivity, national, KZT per employed person, annual. Taldau indexId "
        "4023003.",
    )


def fetch_tourism_value_added() -> tuple[list[dict], dict]:
    """Tourism Direct Gross Value Added (KZT, annual)."""
    return _fetch_taldau_annual_index(
        "77237375", "TOURISM_VALUE_ADDED",
        note="KZT. Gross value added created directly by tourism, from BNS's Tourism Satellite Account (Taldau code 115103). Same KZT scale as GDP_INCOME_METHOD and the other BNS national-accounts series.",
    )


def fetch_tourism_gdp_share() -> tuple[list[dict], dict]:
    """Tourism Direct Gross Value Added, Share of GDP (% of GDP, annual)."""
    return _fetch_taldau_annual_index(
        "77237377", "TOURISM_GDP_SHARE",
        note="Percent of GDP contributed directly by tourism (Taldau code 115105), from BNS's Tourism Satellite Account.",
    )


def fetch_tourism_employment() -> tuple[list[dict], dict]:
    """Employment in Tourism Industries (persons, annual)."""
    return _fetch_taldau_annual_index(
        "77237378", "TOURISM_EMPLOYMENT",
        note="Number of persons employed in tourism industries (Taldau code 115604).",
    )


def fetch_tourism_employment_share() -> tuple[list[dict], dict]:
    """Tourism Employment, Share of Total Employment (% of total employed, annual)."""
    return _fetch_taldau_annual_index(
        "77237384", "TOURISM_EMPLOYMENT_SHARE",
        note="Percent of Kazakhstan's total employed population working in tourism industries (Taldau code 11560102).",
    )


def fetch_tourism_inbound_consumption() -> tuple[list[dict], dict]:
    """Inbound Tourism Consumption (KZT, annual)."""
    return _fetch_taldau_annual_index(
        "77237367", "TOURISM_INBOUND_CONSUMPTION",
        note="KZT. Consumption attributable to INBOUND tourism -- spending in Kazakhstan by non-resident visitors (Taldau code 11510104). The tourism-export side.",
    )


def fetch_tourism_outbound_consumption() -> tuple[list[dict], dict]:
    """Outbound Tourism Consumption (KZT, annual)."""
    return _fetch_taldau_annual_index(
        "77237368", "TOURISM_OUTBOUND_CONSUMPTION",
        note="KZT. Consumption attributable to OUTBOUND tourism -- spending abroad by Kazakhstani residents (Taldau code 11510105). The tourism-import side.",
    )


def fetch_tourism_inbound_trips() -> tuple[list[dict], dict]:
    """Inbound Tourism Trips (trips, annual)."""
    return _fetch_taldau_annual_index(
        "2972978", "TOURISM_INBOUND_TRIPS",
        note="Number of inbound tourism trips (Taldau code 115801). Short series -- the source publishes it only from 2020.",
    )


def fetch_tourism_domestic_trips() -> tuple[list[dict], dict]:
    """Domestic Tourism Trips (trips, annual)."""
    return _fetch_taldau_annual_index(
        "3768950", "TOURISM_DOMESTIC_TRIPS",
        note="Number of domestic tourism trips by residents within Kazakhstan (Taldau code 115803). Short series -- published only from 2020.",
    )


def fetch_tourism_outbound_trips() -> tuple[list[dict], dict]:
    """Outbound Tourism Trips (trips, annual)."""
    return _fetch_taldau_annual_index(
        "3768952", "TOURISM_OUTBOUND_TRIPS",
        note="Number of outbound tourism trips by Kazakhstani residents (Taldau code 115805). Short series -- published only from 2020.",
    )


def fetch_tourism_inbound_nights() -> tuple[list[dict], dict]:
    """Inbound Tourism Nights Spent (nights, annual)."""
    return _fetch_taldau_annual_index(
        "2972979", "TOURISM_INBOUND_NIGHTS",
        note="Number of nights spent in Kazakhstan by inbound visitors (Taldau code 115802). Short series -- published only from 2020.",
    )


def fetch_life_expectancy() -> tuple[list[dict], dict]:
    """Life expectancy at birth, MONTHS, annual.

    Taldau indexId 703906 (code 614101). This index is classified across three
    dictionaries at once (region 67, locality type 64, sex 576) and returns
    HTTP 500 under the project's default single-dictionary params, so its real
    params were captured from the live page's own ExtJS store
    (Ext.ComponentQuery.query('indexTreeGrid')[0].getStore().getProxy().extraParams)
    -- the same technique used for GDP_REAL/AVG_WAGE/RETAIL_TRADE.

    UNIT WARNING: the source returns this series under measure_id=154, whose
    values are MONTHS, not years -- 905.28 for 2024, not 75.4. That reading was
    verified, not assumed: dividing by 12 reproduces Kazakhstan's published life
    expectancy exactly across the whole series, including the COVID dip
    (2000: 65.45, 2016: 72.41, 2020: 71.37, 2024: 75.44). The values are stored
    here exactly as the source returns them, in months, rather than silently
    divided -- divide by 12 for the conventional years figure.
    """
    return _fetch_taldau_annual_index(
        "703906", "LIFE_EXPECTANCY",
        note="Months. Life expectancy at birth for the total population "
             "(both sexes, all localities, national). The source publishes this in MONTHS "
             "under measure_id=154 -- divide by 12 for the conventional figure in years "
             "(2024: 905.28 months = 75.44 years).",
        measure_id="154",
        terms="741880,741917,741935",
        dic_ids="67,64,576",
    )


def fetch_crude_birth_rate() -> tuple[list[dict], dict]:
    """Crude Birth Rate (per 1000 population, annual).

    Taldau indexId 703840. Multi-dictionary index: dicIds=67,749,576,
    terms=741880,741917,741935 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "703840", "CRUDE_BIRTH_RATE",
        note="Births per 1000 population (Taldau code 612101). Cross-checks against the existing BIRTHS_TOTAL and POPULATION_BNS series.",
        measure_id="648",
        terms="741880,741917,741935",
        dic_ids="67,749,576",
    )


def fetch_total_fertility_rate() -> tuple[list[dict], dict]:
    """Total Fertility Rate (children per woman, annual).

    Taldau indexId 77212253. Multi-dictionary index: dicIds=67,749,
    terms=741880,741917 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "77212253", "TOTAL_FERTILITY_RATE",
        note="Average number of children a woman would bear over her lifetime at current age-specific fertility rates (Taldau code 61210102).",
        measure_id="2906",
        terms="741880,741917",
        dic_ids="67,749",
    )


def fetch_crude_death_rate() -> tuple[list[dict], dict]:
    """Crude Death Rate (per 1000 population, annual).

    Taldau indexId 703848. Multi-dictionary index: dicIds=67,749,576,
    terms=741880,741917,741935 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "703848", "CRUDE_DEATH_RATE",
        note="Deaths per 1000 population (Taldau code 612201). With CRUDE_BIRTH_RATE this gives the rate of natural increase.",
        measure_id="648",
        terms="741880,741917,741935",
        dic_ids="67,749,576",
    )


def fetch_infant_mortality_rate() -> tuple[list[dict], dict]:
    """Infant Mortality Rate (per 1000 live births, annual).

    Taldau indexId 703850. Multi-dictionary index: dicIds=67,749,576,
    terms=741880,741917,741935 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "703850", "INFANT_MORTALITY_RATE",
        note="Deaths of children under one year per 1000 live births (Taldau code 612202) -- a standard development and health-system indicator.",
        measure_id="2798",
        terms="741880,741917,741935",
        dic_ids="67,749,576",
    )


def fetch_under5_mortality_rate() -> tuple[list[dict], dict]:
    """Under-Five Mortality Rate (per 1000 live births, annual).

    Taldau indexId 4630524. Multi-dictionary index: dicIds=67,749,576,
    terms=741880,741917,741935 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "4630524", "UNDER5_MORTALITY_RATE",
        note="Deaths of children under five per 1000 live births. Supersedes the older Taldau under-5 series (indexId 703852), which stops in 2012.",
        measure_id="2798",
        terms="741880,741917,741935",
        dic_ids="67,749,576",
    )


def fetch_stillbirth_rate() -> tuple[list[dict], dict]:
    """Stillbirth Rate (per 1000 births, annual).

    Taldau indexId 703845. Multi-dictionary index: dicIds=67,749,576,
    terms=741880,741917,741935 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "703845", "STILLBIRTH_RATE",
        note="Stillbirths per 1000 births (Taldau code 61210501).",
        measure_id="648",
        terms="741880,741917,741935",
        dic_ids="67,749,576",
    )


def fetch_innovation_expenditure() -> tuple[list[dict], dict]:
    """Expenditure on Innovation (KZT, annual).

    Taldau indexId 16174986. Multi-dictionary index: dicIds=68,915,304,1198,
    terms=741880,741885,808348,3451399 -- i.e. РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего + Всего.
    These parameters were obtained programmatically (see fetch_life_expectancy and
    config/sources.yaml for the GetSegmentList method), then verified live.
    """
    return _fetch_taldau_annual_index(
        "16174986", "INNOVATION_EXPENDITURE",
        note="KZT. Total enterprise spending on innovation (Taldau code 231...). Short series -- the source publishes it only from 2022. Same KZT scale as the other BNS value series.",
        measure_id="1",
        terms="741880,741885,808348,3451399",
        dic_ids="68,915,304,1198",
    )


def fetch_organizations_using_computers() -> tuple[list[dict], dict]:
    """Organizations Using Computers (units, annual).

    Taldau indexId 703648, dicIds=68,915, terms=741880,741885
    (РЕСПУБЛИКА КАЗАХСТАН + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "703648", "ORGANIZATIONS_USING_COMPUTERS",
        note="Number of organizations using computers.",
        measure_id="5",
        terms="741880,741885",
        dic_ids="68,915",
    )


def fetch_computers_in_organizations() -> tuple[list[dict], dict]:
    """Computers Used in Organizations (units, annual).

    Taldau indexId 703649, dicIds=68,915, terms=741880,741885
    (РЕСПУБЛИКА КАЗАХСТАН + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "703649", "COMPUTERS_IN_ORGANIZATIONS",
        note="Number of computers in use in organizations.",
        measure_id="5",
        terms="741880,741885",
        dic_ids="68,915",
    )


def fetch_computers_internet_connected() -> tuple[list[dict], dict]:
    """Computers Connected to the Internet (units, annual).

    Taldau indexId 703651, dicIds=68,915, terms=741880,741885
    (РЕСПУБЛИКА КАЗАХСТАН + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "703651", "COMPUTERS_INTERNET_CONNECTED",
        note="Number of organizational computers connected to the internet. Read against COMPUTERS_IN_ORGANIZATIONS as a connectivity ratio.",
        measure_id="5",
        terms="741880,741885",
        dic_ids="68,915",
    )


def fetch_workers_using_computers() -> tuple[list[dict], dict]:
    """Workers Using a Computer at Work (persons, annual).

    Taldau indexId 703675, dicIds=68,915, terms=741880,741885
    (РЕСПУБЛИКА КАЗАХСТАН + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "703675", "WORKERS_USING_COMPUTERS",
        note="Number of workers who used a computer at work at least once a week.",
        measure_id="23",
        terms="741880,741885",
        dic_ids="68,915",
    )


def fetch_workers_using_internet() -> tuple[list[dict], dict]:
    """Workers Using an Internet-Connected Computer at Work (persons, annual).

    Taldau indexId 703676, dicIds=67,915, terms=741880,741885
    (РЕСПУБЛИКА КАЗАХСТАН + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "703676", "WORKERS_USING_INTERNET",
        note="Number of workers who use an internet-connected computer for work.",
        measure_id="23",
        terms="741880,741885",
        dic_ids="67,915",
    )


def fetch_ecommerce_retail_orders() -> tuple[list[dict], dict]:
    """E-Commerce Retail Orders (orders, annual).

    Taldau indexId 18199189, dicIds=67,915,853, terms=741880,741885,2658135
    (РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "18199189", "ECOMMERCE_RETAIL_ORDERS",
        note="Number of retail orders placed over the internet. Short series -- the source publishes it only from 2022.",
        measure_id="5",
        terms="741880,741885,2658135",
        dic_ids="67,915,853",
    )


def fetch_ecommerce_services_value() -> tuple[list[dict], dict]:
    """Services Sold via Own Internet Resource (KZT, annual).

    Taldau indexId 77212521, dicIds=67,915,853,2956, terms=741880,741885,2658135,4628511
    (РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего + Всего). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "77212521", "ECOMMERCE_SERVICES_VALUE",
        note="KZT. Value of services sold through an organization's own internet resource. Short series -- published only from 2022. Same KZT scale as the other BNS value series.",
        measure_id="1",
        terms="741880,741885,2658135,4628511",
        dic_ids="67,915,853,2956",
    )


def fetch_doctors_per_10k() -> tuple[list[dict], dict]:
    """Doctors per 10,000 Population (per 10000 population, annual).

    Taldau indexId 704316, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "704316", "DOCTORS_PER_10K",
        note="Doctors of all specialties per 10,000 population -- the density counterpart to the existing DOCTORS_TOTAL headcount.",
        measure_id="23",
        terms="741880",
        dic_ids="67",
    )


def fetch_hospital_beds() -> tuple[list[dict], dict]:
    """Hospital Beds (units, annual).

    Taldau indexId 704310, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "704310", "HOSPITAL_BEDS",
        note="Total number of hospital beds.",
        measure_id="742",
        terms="741880",
        dic_ids="67",
    )


def fetch_hospital_beds_per_10k() -> tuple[list[dict], dict]:
    """Hospital Beds per 10,000 Population (per 10000 population, annual).

    Taldau indexId 704311, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the
    GetSegmentList method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "704311", "HOSPITAL_BEDS_PER_10K",
        note="Hospital beds per 10,000 population -- health-system capacity relative to population.",
        measure_id="742",
        terms="741880",
        dic_ids="67",
    )


def fetch_sme_gdp_share() -> tuple[list[dict], dict]:
    """SME Share of GDP (% of GDP, annual).

    Taldau indexId 19824647, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "19824647", "SME_GDP_SHARE",
        note="Percent of GDP produced by small and medium enterprises. Equals SMALL_BUSINESS_GDP_SHARE plus MEDIUM_BUSINESS_GDP_SHARE exactly (32.2 + 6.7 = 38.9 in 2024), which is the source's own decomposition, not one computed here.",
        measure_id="7",
        terms="741880",
        dic_ids="67",
    )


def fetch_small_business_gdp_share() -> tuple[list[dict], dict]:
    """Small Business Share of GDP (% of GDP, annual).

    Taldau indexId 20380630, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "20380630", "SMALL_BUSINESS_GDP_SHARE",
        note="Percent of GDP produced by SMALL enterprises.",
        measure_id="7",
        terms="741880",
        dic_ids="67",
    )


def fetch_medium_business_gdp_share() -> tuple[list[dict], dict]:
    """Medium Business Share of GDP (% of GDP, annual).

    Taldau indexId 20380634, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "20380634", "MEDIUM_BUSINESS_GDP_SHARE",
        note="Percent of GDP produced by MEDIUM enterprises.",
        measure_id="7",
        terms="741880",
        dic_ids="67",
    )


def fetch_small_business_value_added() -> tuple[list[dict], dict]:
    """Small Business Gross Value Added (KZT, annual).

    Taldau indexId 20380637, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "20380637", "SMALL_BUSINESS_VALUE_ADDED",
        note="KZT. Gross value added produced by SMALL enterprises. Same KZT scale as the other BNS national-accounts series.",
        measure_id="1",
        terms="741880",
        dic_ids="67",
    )


def fetch_medium_business_value_added() -> tuple[list[dict], dict]:
    """Medium Business Gross Value Added (KZT, annual).

    Taldau indexId 20380641, dicIds=67, terms=741880
    (РЕСПУБЛИКА КАЗАХСТАН). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "20380641", "MEDIUM_BUSINESS_VALUE_ADDED",
        note="KZT. Gross value added produced by MEDIUM enterprises.",
        measure_id="1",
        terms="741880",
        dic_ids="67",
    )


def fetch_housing_investment() -> tuple[list[dict], dict]:
    """Investment in Housing Construction (KZT, annual).

    Taldau indexId 701834, dicIds=68,776,459, terms=741880,741917,807855
    (РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "701834", "HOUSING_INVESTMENT",
        note="KZT. Investment in residential construction -- the housing component behind the broader INVESTMENT series.",
        measure_id="1",
        terms="741880,741917,807855",
        dic_ids="68,776,459",
    )


def fetch_ict_specialists() -> tuple[list[dict], dict]:
    """ICT Specialists (persons, annual).

    Taldau indexId 19096214, dicIds=68,915, terms=741880,741885
    (РЕСПУБЛИКА КАЗАХСТАН + Всего). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "19096214", "ICT_SPECIALISTS",
        note="Number of ICT specialists (educated or specially trained in ICT) -- the workforce side of the digital-economy indicators.",
        measure_id="23",
        terms="741880,741885",
        dic_ids="68,915",
    )


def fetch_graduates_hired() -> tuple[list[dict], dict]:
    """University Graduates Hired in the Reporting Year (persons, annual).

    Taldau indexId 703000, dicIds=68,859,2813,576, terms=741880,741885,3629946,741935
    (РЕСПУБЛИКА КАЗАХСТАН + Всего + Всего + Всего). Parameters obtained via the GetSegmentList
    method and confirmed to be an all-totals slice before use.
    """
    return _fetch_taldau_annual_index(
        "703000", "GRADUATES_HIRED",
        note="Number of specialists with higher education hired from among that year's university graduates -- a graduate-absorption measure for the labour market.",
        measure_id="23",
        terms="741880,741885,3629946,741935",
        dic_ids="68,859,2813,576",
    )


# ---------------------------------------------------------------------------
# OIL_PRODUCTION: crude oil output in physical terms, from the BNS publication
# "Основные показатели работы промышленности Республики Казахстан".
#
# Earlier passes concluded BNS did not publish oil production. That was wrong
# twice over: it is not in Taldau's 3,700-indicator catalogue and not in the
# stat.gov.kz industrial cubes (which are index-only and stop at 2023), but it
# IS in this monthly publication, sheet "3 " ("Произведено продукции в
# натуральном выражении по видам промышленной продукции"), row "Нефть, включая
# конденсат газовый, тыс.тонн".
#
# Two structural facts drive the implementation:
#
# 1. Each edition reports ONE month. Its columns are [previous month, reporting
#    month, reporting period YTD, same month last year, same period last year,
#    % vs previous month, % vs same month last year]. So a single download
#    yields two usable monthly points -- the reporting month and the same month
#    a year earlier -- and nothing else that can be turned into a clean monthly
#    series (the YTD columns are a different frequency and are not mixed in).
#
# 2. The site keeps only a SHORT ARCHIVE -- three monthly editions were
#    available on 2026-09-01. The series therefore starts small and GROWS: like
#    EXCHANGE_RATE, it merges each fetch with what is already processed, so a
#    month captured today is not lost when its edition drops off the page.
#
# The reporting month is derived from the publication date, which each file
# states on its own cover sheet: published 17.08.2026 carries July data.
#
# Checks that this is the right row, all from the same edition: its 2026
# year-to-date column reads 53,208 thousand tonnes over seven months (~91 Mt a
# year) against 58,358 for the same period of 2025 (~100 Mt a year), an 8.8%
# year-on-year fall consistent with Kazakhstan cutting back from its 2025 record.
# And 2025 output of ~100 Mt against OIL_EXPORTS_VOLUME's 76.3 Mt for the same
# year is a 76% export ratio, with the remainder refined domestically -- the
# right shape for Kazakhstan.
#
# Element ids are NOT hardcoded: they rotate as editions are republished. Every
# element linked from the industry page is downloaded, and only workbooks that
# actually contain the expected sheet and row are used.
# ---------------------------------------------------------------------------
INDUSTRY_PAGE_URL = "https://stat.gov.kz/ru/industries/business-statistics/stat-industrial-production/"
OIL_PRODUCTION_ROW_MARKER = "Нефть, включая конденсат газовый"
OIL_PRODUCTION_SHEET = "3"
PUBLISHED_RE = re.compile(r"Дата опубликования:\s*(\d{2})\.(\d{2})\.(\d{4})")


def _industry_publication_elements() -> list[int]:
    resp = requests.get(INDUSTRY_PAGE_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    ids = []
    for m in re.finditer(r"/api/iblock/element/(\d+)/file/", resp.text):
        eid = int(m.group(1))
        if eid not in ids:
            ids.append(eid)
    if not ids:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/OIL_PRODUCTION",
                f"WHAT CHANGED: no /api/iblock/element/<id>/file/ links on {INDUSTRY_PAGE_URL}",
                "EXPECTED: the industry page lists its publications as downloadable elements",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )
    return ids


def fetch_oil_production() -> tuple[list[dict], dict]:
    """Crude oil and gas condensate output, thousand tonnes, monthly.

    Accumulated across runs -- see the block comment above for why (the source
    keeps only about three monthly editions online at a time).
    """
    existing = {}
    path = Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE / "oil_production.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    inspected = 0
    for eid in _industry_publication_elements():
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
        except Exception:
            continue
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() == OIL_PRODUCTION_SHEET), None)
        if sheet is None:
            continue

        published = None
        for sh in ("Обложка", "Метаданные"):
            if sh not in wb.sheetnames:
                continue
            for row in wb[sh].iter_rows(max_row=20, values_only=True):
                for cell in row:
                    if isinstance(cell, str):
                        m = PUBLISHED_RE.search(cell)
                        if m:
                            published = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                            break
                if published:
                    break
            if published:
                break
        if published is None:
            continue

        oil_row = None
        for row in wb[sheet].iter_rows(values_only=True):
            label = next((c for c in row[:3] if isinstance(c, str)), "")
            if OIL_PRODUCTION_ROW_MARKER in label:
                oil_row = row
                break
        if oil_row is None:
            continue

        inspected += 1
        _save_raw(f"OIL_PRODUCTION_{eid}", content, "xlsx",
                  {"source_url": url, "element_id": eid, "published": published.isoformat()})

        # An edition published in month M reports month M-1.
        rep_year, rep_month = (published.year, published.month - 1) if published.month > 1 else (published.year - 1, 12)
        numbers = [c for c in oil_row if isinstance(c, (int, float))]
        if len(numbers) < 4:
            continue
        # columns: previous month, reporting month, YTD, same month last year, ...
        fetched[f"{rep_year:04d}-{rep_month:02d}-01"] = float(numbers[1])
        prev_year_month = f"{rep_year - 1:04d}-{rep_month:02d}-01"
        fetched[prev_year_month] = float(numbers[3])
        prev_month_y, prev_month_m = (rep_year, rep_month - 1) if rep_month > 1 else (rep_year - 1, 12)
        fetched[f"{prev_month_y:04d}-{prev_month_m:02d}-01"] = float(numbers[0])

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/OIL_PRODUCTION",
                f"WHAT CHANGED: none of the industry-page publications contained sheet "
                f"{OIL_PRODUCTION_SHEET!r} with a row matching {OIL_PRODUCTION_ROW_MARKER!r}, "
                "and no previously processed history exists",
                f"ACTUAL: {inspected} workbook(s) had the expected shape",
                f"ACTION REQUIRED: inspect {INDUSTRY_PAGE_URL} and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    manifest = {
        "frequency": "monthly",
        "source_url": INDUSTRY_PAGE_URL,
        "dataset_id": "osnovnye-pokazateli-promyshlennosti/sheet-3/neft-vklyuchaya-kondensat",
        "note": "Thousand tonnes. Crude oil including gas condensate, from the monthly BNS "
                "publication 'Основные показатели работы промышленности', sheet 3 (output in "
                "physical terms). Each edition reports one month, and the site keeps only about "
                "three editions online, so this series is ACCUMULATED across runs and grows "
                "month by month. Element ids are resolved from the page each run rather than "
                "hardcoded, because editions are republished under new ids.",
    }
    return records, manifest


# ---------------------------------------------------------------------------
# Monthly industrial output and the industrial production index, from sheet 2
# of the same "Основные показатели работы промышленности" publication that
# supplies OIL_PRODUCTION.
#
# This is what fixes the audit's staleness finding: the existing IND_PROD and
# its three sub-indices are ANNUAL and stop at 2023, because they come from the
# stat.gov.kz cubes, which have not been updated since. The publication layer
# carries the same concepts MONTHLY and current.
#
# Sheet 2 column layout, read from its own header (row 3 states the unit as
# "млн. теңге"): [number of enterprises, previous month, reporting month,
# year-to-date, index vs previous month, index vs same month last year, index
# for the period vs same period last year]. After dropping non-numeric cells
# those land at positions 0..6, so value columns are 1 and 2 and the
# year-on-year index is 5.
#
# As with OIL_PRODUCTION, the site keeps only about three monthly editions, so
# these series ACCUMULATE across runs. Value series gain two points per edition
# (reporting month and the previous month); the index series gains one, because
# the sheet publishes an index only for the reporting month.
# ---------------------------------------------------------------------------
INDUSTRY_SHEET_VALUES = "2"
# The unit is written three different ways across editions: "млн. теңге", "млн.теңге"
# (no space) and "млн. тенге" (Russian е instead of Kazakh ң). Same unit each time, so the
# check strips whitespace and accepts either spelling rather than demanding one form --
# the same class of source inconsistency as the Latin/Cyrillic H seen in Minfin's sheets.
INDUSTRY_UNIT_PREFIX = "млн."
INDUSTRY_UNIT_WORDS = ("теңге", "тенге")


def _industry_publication_rows(sheet_name: str, row_marker: str, indicator_id: str) -> list[tuple]:
    """Yield (published_date, numeric_cells) for every edition carrying the row.

    Element ids are resolved from the page each run rather than hardcoded --
    editions are republished under new ids.
    """
    found = []
    for eid in _industry_publication_elements():
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() == sheet_name), None)
        if sheet is None:
            continue

        published = None
        for sh in ("Обложка", "Метаданные"):
            if sh not in wb.sheetnames:
                continue
            for row in wb[sh].iter_rows(max_row=20, values_only=True):
                for cell in row:
                    if isinstance(cell, str):
                        m = PUBLISHED_RE.search(cell)
                        if m:
                            published = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                            break
                if published:
                    break
            if published:
                break
        if published is None:
            continue

        ws = wb[sheet]
        unit_ok = False
        target = None
        for row in ws.iter_rows(values_only=True):
            for cell in row[:9]:
                if isinstance(cell, str):
                    flat = "".join(cell.split())
                    if INDUSTRY_UNIT_PREFIX in flat and any(w in flat for w in INDUSTRY_UNIT_WORDS):
                        unit_ok = True
            label = next((c for c in row[:2] if isinstance(c, str)), "")
            if target is None and label.strip().startswith(row_marker):
                target = [c for c in row if isinstance(c, (int, float))]
        if target is None:
            continue
        if not unit_ok:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: sheet {sheet_name!r} of element {eid} no longer declares its unit "
                    f"as {INDUSTRY_UNIT_PREFIX!r} plus one of {INDUSTRY_UNIT_WORDS!r}",
                    "EXPECTED: the value columns are million KZT; a changed unit would rescale the "
                    "whole series silently",
                    f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
                ])
            )
        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": url, "element_id": eid, "published": published.isoformat(),
                   "sheet": sheet_name, "row": row_marker})
        found.append((published, target))
    return found


def _fetch_industry_series(row_marker: str, indicator_id: str, note: str,
                           index_series: bool = False) -> tuple[list[dict], dict]:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    for published, nums in _industry_publication_rows(INDUSTRY_SHEET_VALUES, row_marker, indicator_id):
        if len(nums) < 6:
            continue
        rep_y, rep_m = (published.year, published.month - 1) if published.month > 1 else (published.year - 1, 12)
        if index_series:
            fetched[f"{rep_y:04d}-{rep_m:02d}-01"] = float(nums[5])
        else:
            fetched[f"{rep_y:04d}-{rep_m:02d}-01"] = float(nums[2])
            prev_y, prev_m = (rep_y, rep_m - 1) if rep_m > 1 else (rep_y - 1, 12)
            fetched[f"{prev_y:04d}-{prev_m:02d}-01"] = float(nums[1])

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no edition on {INDUSTRY_PAGE_URL} carried sheet "
                f"{INDUSTRY_SHEET_VALUES!r} with a row starting {row_marker!r}, and no "
                "previously processed history exists",
                f"ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    manifest = {
        "frequency": "monthly",
        "source_url": INDUSTRY_PAGE_URL,
        "dataset_id": f"osnovnye-pokazateli-promyshlennosti/sheet-2/{row_marker}",
        "note": note,
    }
    return records, manifest


def fetch_industrial_output() -> tuple[list[dict], dict]:
    """Industrial output, million KZT, monthly."""
    return _fetch_industry_series(
        "Промышленность", "INDUSTRIAL_OUTPUT",
        "Million KZT. Value of industrial output (goods and services), all industry. Monthly and "
        "current, unlike the existing IND_PROD, which is an annual index from the stat.gov.kz "
        "cubes and stops at 2023. Accumulated across runs because the source keeps only about "
        "three monthly editions online.")


def fetch_industrial_production_index() -> tuple[list[dict], dict]:
    """Industrial production index, same month previous year = 100, monthly."""
    return _fetch_industry_series(
        "Промышленность", "INDUSTRIAL_PRODUCTION_INDEX",
        "Index, same month of the previous year = 100. The monthly, current replacement for the "
        "annual IND_PROD series, which stops at 2023. One point per edition, since the sheet "
        "publishes an index only for the reporting month.",
        index_series=True)


def fetch_mining_output() -> tuple[list[dict], dict]:
    """Mining and quarrying output, million KZT, monthly."""
    return _fetch_industry_series(
        "Горнодобывающая промышленность", "MINING_OUTPUT",
        "Million KZT. Value of output of mining and quarrying -- the sector that carries "
        "Kazakhstan's oil, gas, coal and ore extraction. Read against MANUFACTURING_OUTPUT for "
        "the resource-versus-processing split.")


def fetch_manufacturing_output() -> tuple[list[dict], dict]:
    """Manufacturing output, million KZT, monthly."""
    return _fetch_industry_series(
        "Обрабатывающая промышленность", "MANUFACTURING_OUTPUT",
        "Million KZT. Value of manufacturing output -- the non-extractive half of industry, and "
        "the usual measure of diversification progress.")


# ---------------------------------------------------------------------------
# Fixed capital investment, from the monthly publication "Статистика инвестиций"
# (sheet 1, "Инвестиции в основной капитал по видам затрат").
#
# The existing INVESTMENT series is ANNUAL and stops at 2022 -- one of the
# staleness findings in the sector audit. This is the current, monthly-published
# replacement, reached the same way as OIL_PRODUCTION and INDUSTRIAL_OUTPUT: via
# the publication layer rather than the stat.gov.kz cubes.
#
# The figures are YEAR-TO-DATE CUMULATIVE, not monthly flows -- the sheet's own
# column header reads "к соответствующему периоду прошлого года" (against the
# same PERIOD of last year), and the July 2026 edition reports 11,464,246,834
# thousand KZT, which is 11.46 trillion for seven months and about 19.6 trillion
# a year. That is Kazakhstan's actual investment scale, and it confirms the
# cumulative reading: a single month at that level would be implausible.
# Labelled as cumulative rather than silently mixed with monthly series.
#
# Column layout after dropping non-numeric cells: [total value, index vs same
# period last year, small enterprises, their index, medium, their index, large,
# ...]. One point per edition, so like the other publication-layer series this
# one ACCUMULATES across runs.
# ---------------------------------------------------------------------------
INVEST_PAGE_URL = "https://stat.gov.kz/ru/industries/business-statistics/stat-invest/"
INVEST_ROW_MARKER = "Инвестиции в основной капитал"
INVEST_UNIT_WORDS = ("тыс.теңге", "тыс.тенге")
# The investment section mixes MONTHLY editions with an ANNUAL one. They are told apart
# by the gap to the next publication, which each file states on its own cover: about a
# month for monthly editions, a year for the annual one. Without this, the annual file
# (published 03.07.2026) was read as the June 2026 month and produced 23.5 trillion KZT
# against July's 11.46 -- an impossible drop for a year-to-date series, which is what
# exposed it.
NEXT_PUBLISHED_RE = re.compile(r"Дата следующего опубликования:\s*(\d{2})\.(\d{2})\.(\d{4})")
MAX_EDITION_GAP_DAYS = 70


def _publication_elements(page_url: str, indicator_id: str) -> list[int]:
    resp = requests.get(page_url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    ids: list[int] = []
    for m in re.finditer(r"/api/iblock/element/(\d+)/file/", resp.text):
        eid = int(m.group(1))
        if eid not in ids:
            ids.append(eid)
    if not ids:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no /api/iblock/element/<id>/file/ links on {page_url}",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )
    return ids


def _fetch_investment_series(value_index: int, indicator_id: str, note: str,
                             unit_check: bool) -> tuple[list[dict], dict]:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    for eid in _publication_elements(INVEST_PAGE_URL, indicator_id):
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() == "1"), None)
        if sheet is None:
            continue

        published = None
        for sh in ("Обложка", "Метаданные"):
            if sh not in wb.sheetnames:
                continue
            for row in wb[sh].iter_rows(max_row=20, values_only=True):
                for cell in row:
                    if isinstance(cell, str):
                        m = PUBLISHED_RE.search(cell)
                        if m:
                            published = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                            break
                if published:
                    break
            if published:
                break
        next_published = None
        for sh in ("Обложка", "Метаданные"):
            if sh not in wb.sheetnames:
                continue
            for row in wb[sh].iter_rows(max_row=20, values_only=True):
                for cell in row:
                    if isinstance(cell, str):
                        m = NEXT_PUBLISHED_RE.search(cell)
                        if m:
                            next_published = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                            break
                if next_published:
                    break
            if next_published:
                break
        if published is None:
            continue
        if next_published is not None and (next_published - published).days > MAX_EDITION_GAP_DAYS:
            # Annual edition, not a monthly one -- see NEXT_PUBLISHED_RE above.
            continue

        unit_ok = not unit_check
        target = None
        for row in wb[sheet].iter_rows(values_only=True):
            for cell in row[:10]:
                if isinstance(cell, str) and any(w in "".join(cell.split()) for w in INVEST_UNIT_WORDS):
                    unit_ok = True
            label = next((c for c in row[:2] if isinstance(c, str)), "")
            if target is None and label.strip() == INVEST_ROW_MARKER:
                target = [c for c in row if isinstance(c, (int, float))]
        if target is None or len(target) <= value_index:
            continue
        if not unit_ok:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: sheet 1 of element {eid} no longer declares its unit as one of "
                    f"{INVEST_UNIT_WORDS!r}",
                    "EXPECTED: thousand KZT; a changed unit would rescale the series silently",
                    f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
                ])
            )

        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": url, "element_id": eid, "published": published.isoformat()})
        rep_y, rep_m = (published.year, published.month - 1) if published.month > 1 else (published.year - 1, 12)
        fetched[f"{rep_y:04d}-{rep_m:02d}-01"] = float(target[value_index])

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no edition on {INVEST_PAGE_URL} carried sheet 1 with a row equal to "
                f"{INVEST_ROW_MARKER!r}, and no previously processed history exists",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    if unit_check:
        # Year-to-date cumulation can only rise within a calendar year. A fall means an
        # edition of the wrong periodicity slipped in -- which is exactly how the annual
        # file was caught before the periodicity filter above existed.
        for a, b in zip(records, records[1:]):
            if a["date"][:4] == b["date"][:4] and b["value"] < a["value"]:
                raise validation.StructuralChangeError(
                    "\n".join([
                        f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                        f"WHAT CHANGED: year-to-date value falls within {a['date'][:4]}: "
                        f"{a['date']}={a['value']:,.0f} then {b['date']}={b['value']:,.0f}",
                        "EXPECTED: a cumulative series cannot decrease inside a calendar year",
                        "EXPECTED CONSEQUENCE: an edition of the wrong periodicity (annual rather "
                        "than monthly) has most likely been included",
                        f"ACTION REQUIRED: inspect {INVEST_PAGE_URL} and update scripts/fetchers/bns.py",
                    ])
                )
    manifest = {
        "frequency": "monthly",
        "source_url": INVEST_PAGE_URL,
        "dataset_id": f"statistika-investiciy/sheet-1/{INVEST_ROW_MARKER}/col{value_index}",
        "note": note,
    }
    return records, manifest


def fetch_investment_fixed_capital() -> tuple[list[dict], dict]:
    """Investment in fixed capital, thousand KZT, year-to-date cumulative."""
    return _fetch_investment_series(
        0, "INVESTMENT_FIXED_CAPITAL",
        "Thousand KZT, YEAR-TO-DATE CUMULATIVE (not a monthly flow) -- the sheet reports against "
        "the same PERIOD of the previous year. Replaces the annual INVESTMENT series, which stops "
        "at 2022. Accumulated across runs because the source keeps only a handful of editions "
        "online. 11.46 trillion KZT for January-July 2026, about 19.6 trillion a year.",
        unit_check=True)


def fetch_investment_index() -> tuple[list[dict], dict]:
    """Investment in fixed capital, index against the same period a year earlier."""
    return _fetch_investment_series(
        1, "INVESTMENT_INDEX",
        "Index, same period of the previous year = 100, year-to-date. The real-terms companion to "
        "INVESTMENT_FIXED_CAPITAL, which is in current prices.",
        unit_check=False)


MONTH_END_DAYS = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}


# ---------------------------------------------------------------------------
# EXPORT_PRICE_INDEX / IMPORT_PRICE_INDEX: from the prices section publication
# "Индекс цен экспортных поставок / импортных поступлений товаров".
#
# The sector audit listed export and import price indices as a high-priority
# external-sector gap: the dataset held physical VOLUME indices for trade but no
# price indices, so nominal trade movements could not be split into price and
# quantity, and terms of trade could not be built from actual trade at all.
# (COMMODITY_TERMS_OF_TRADE from the IMF covers the commodity basket only.)
#
# Two details make this file easy to get wrong:
#
# 1. Its cover carries NO publication date -- unlike every other publication
#    used here. The reporting month is instead taken from the sheet's own header
#    text, "Июнь 2026г. к", which is more reliable anyway: it states the period
#    the numbers describe rather than when the file was posted.
#
# 2. Row 5 carries SEVEN different comparisons side by side: against the previous
#    month, against last December, against the same month a year earlier, against
#    December 2020, and three quarterly ones. Only the third is a normal
#    year-on-year monthly index. Picking the wrong column would produce a series
#    that looks entirely plausible -- the December-2020 base column reads 234.4
#    for exports, which would pass any range check while meaning something else
#    completely.
# ---------------------------------------------------------------------------
TRADE_PRICE_PAGE_URL = "https://stat.gov.kz/ru/industries/economy/prices/"
TRADE_PRICE_HEADER_RE = re.compile(r"([А-Яа-яЁё]+)\s+(\d{4})\s*г\.?\s*к")
TRADE_PRICE_YOY_INDEX = 2  # 0: vs previous month, 1: vs last December, 2: vs same month last year


def _fetch_trade_price_index(sheet_prefix: str, row_marker: str, indicator_id: str,
                             note: str) -> tuple[list[dict], dict]:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    for eid in _publication_elements(TRADE_PRICE_PAGE_URL, indicator_id):
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip().rstrip(".") == sheet_prefix), None)
        if sheet is None:
            continue

        rep = None
        target = None
        for row in wb[sheet].iter_rows(values_only=True):
            for cell in row[:6]:
                if rep is None and isinstance(cell, str):
                    m = TRADE_PRICE_HEADER_RE.search(cell)
                    if m and m.group(1).lower() in RU_MONTHS:
                        rep = (int(m.group(2)), RU_MONTHS[m.group(1).lower()])
            label = next((c for c in row[:2] if isinstance(c, str)), "")
            if target is None and label.strip().startswith(row_marker):
                target = [c for c in row if isinstance(c, (int, float))]
        if rep is None or target is None or len(target) <= TRADE_PRICE_YOY_INDEX:
            continue

        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": url, "element_id": eid,
                   "reporting_month": f"{rep[0]:04d}-{rep[1]:02d}", "sheet": sheet})
        year, month = rep
        # Month START, matching the 120 other monthly series in this project.
        # These two shipped on month-end dates, which silently prevented every
        # join against the monthly production, trade and price series -- a join
        # that returns nothing raises nothing, so it had to be found by looking.
        fetched[f"{year:04d}-{month:02d}-01"] = float(target[TRADE_PRICE_YOY_INDEX])

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no publication on {TRADE_PRICE_PAGE_URL} carried a sheet "
                f"{sheet_prefix!r} with a row starting {row_marker!r} and a parseable "
                "'<Month> <year>г. к' header, and no processed history exists",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    manifest = {
        "frequency": "monthly",
        "source_url": TRADE_PRICE_PAGE_URL,
        "dataset_id": f"indeks-cen-vneshney-torgovli/sheet-{sheet_prefix}/{row_marker}",
        "note": note,
    }
    return records, manifest


def fetch_export_price_index() -> tuple[list[dict], dict]:
    """Export price index, same month previous year = 100, monthly."""
    return _fetch_trade_price_index(
        "1", "Экспорт - всего", "EXPORT_PRICE_INDEX",
        "Index, same month of the previous year = 100. Price of Kazakhstan's goods exports. The "
        "dataset previously held only physical VOLUME indices for trade, so nominal moves could "
        "not be split into price and quantity. Read against IMPORT_PRICE_INDEX for terms of "
        "trade across all goods -- broader than COMMODITY_TERMS_OF_TRADE, which covers the "
        "commodity basket only. The source sheet also publishes six other comparisons on the "
        "same row (against last December, against December 2020, and three quarterly ones); "
        "this is specifically the year-on-year monthly one.")


def fetch_import_price_index() -> tuple[list[dict], dict]:
    """Import price index, same month previous year = 100, monthly."""
    return _fetch_trade_price_index(
        "2", "Импорт - всего", "IMPORT_PRICE_INDEX",
        "Index, same month of the previous year = 100. Price of Kazakhstan's goods imports, on "
        "the same basis and from the same publication as EXPORT_PRICE_INDEX.")


# ---------------------------------------------------------------------------
# CPI_YOY / CPI_YTD: year-on-year and since-December inflation, from the SAME
# open-data file that already feeds CPI (element 1549).
#
# Same lesson as oil exports: an already-connected source was not fully read.
# The audit called annual inflation a CRITICAL gap, noting that CPI holds only
# month-on-month percent change so a year-on-year rate cannot be derived from
# it. But the file has an "ССП" (comparison type) dimension with THIRTY values,
# and the project was filtering on one of them. Year-on-year was in the download
# the whole time.
#
# Distinct comparison values include: against the previous period (what CPI
# uses), against the same period a year earlier, against December of the
# previous year, and a family of fixed-base ones (December 2000, 2001, 2002,
# 2005, 2010, 2015, 2018, 2020, 2022). The product dimension has only one value
# in this file -- "Товары и услуги", the all-items total -- so the audit's
# food/non-food/services split is NOT here and remains open.
#
# 178 monthly points, 2011-01 to 2025-10. Cross-checked against the separately
# sourced NBK ANNUAL_INFLATION: 12.6% here for October 2025 runs into 12.2% in
# February 2026 and 10.2% by August 2026 there -- two independent sources on one
# trajectory.
#
# fetch_cpi above predates this helper and repeats the same parse for the
# month-on-month case. It is deliberately left untouched rather than refactored:
# it is a shipped indicator, and the duplication is cheaper than the risk.
# ---------------------------------------------------------------------------
CPI_ELEMENT_ID = 1549
CPI_REGION = "РЕСПУБЛИКА КАЗАХСТАН"
CPI_CATEGORY = "Товары и услуги"


def _fetch_cpi_by_comparison(comparison: str, indicator_id: str,
                             note: str) -> tuple[list[dict], dict]:
    url = f"https://stat.gov.kz/api/iblock/element/{CPI_ELEMENT_ID}/csv/file/ru/"
    content = _download(url)
    _save_raw(indicator_id, content, "csv",
              {"source_url": url, "element_id": CPI_ELEMENT_ID, "comparison": comparison})

    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter="\t"))
    header, data_rows = rows[0], rows[1:]
    col = {name: i for i, name in enumerate(header)}
    try:
        period_i = col["PERIOD"]
        region_i = col["КАТО(по каталогу)"]
        comparison_i = col["ССП"]
        category_i = col["ГНКИПЦ01_2753"]
        val_i = col["VAL"]
    except KeyError as exc:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: expected column {exc} not present",
                f"ACTUAL COLUMNS: {header}",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        ) from exc

    records = []
    for row in data_rows:
        if len(row) <= val_i:
            continue
        if (row[region_i] != CPI_REGION or row[comparison_i] != comparison
                or row[category_i] != CPI_CATEGORY):
            continue
        period = row[period_i]
        if len(period) != 6 or not period.isdigit():
            continue
        try:
            value = float(row[val_i])
        except ValueError:
            continue
        records.append({"date": f"{period[:4]}-{period[4:]}-01", "value": value})

    if not records:
        available = sorted({r[comparison_i] for r in data_rows if len(r) > comparison_i})
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no rows matched comparison={comparison!r} for "
                f"region={CPI_REGION!r}, category={CPI_CATEGORY!r}",
                f"ACTUAL comparison values present: {available[:6]}",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        )

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "monthly",
        "source_url": url,
        "dataset_id": f"{CPI_ELEMENT_ID},comparison={comparison}",
        "note": note,
    }
    return records, manifest


def _fetch_cpi_yoy_cube_legacy() -> tuple[list[dict], dict]:
    """Consumer price index, same month previous year = 100, monthly."""
    return _fetch_cpi_by_comparison(
        "отчетный период к соответствующему периоду прошлого года", "CPI_YOY",
        "Index, same month of the previous year = 100 -- so 112.6 means 12.6% annual inflation. "
        "This is the headline inflation rate. The existing CPI series carries only "
        "month-on-month change, from which this cannot be derived; both come from the same "
        "open-data file, which has a comparison-type dimension with thirty values. Independently "
        "consistent with the NBK-sourced ANNUAL_INFLATION series.")


def _fetch_cpi_ytd_cube_legacy() -> tuple[list[dict], dict]:
    """Consumer price index against December of the previous year, monthly."""
    return _fetch_cpi_by_comparison(
        "отчетный период к декабрю прошлого года", "CPI_YTD",
        "Index, December of the previous year = 100 -- cumulative inflation so far this year, the "
        "form Kazakhstan's own commentary usually quotes. Same file and dimension as CPI_YOY.")


# ---------------------------------------------------------------------------
# Monthly retail and wholesale trade, from the BNS publication
# "Статистика внутренней торговли" (section "Внутренний рынок").
#
# The sector audit flagged monthly retail trade as a real-sector gap. The
# dataset already held RETAIL_TRADE, WHOLESALE_TRADE and
# RETAIL_TRADE_VOLUME_INDEX -- but all three are ANNUAL, from the stat.gov.kz
# cubes. This is the same staleness pattern already fixed for industry and
# investment: the publication layer carries the same concepts monthly.
#
# Finding the section took three wrong guesses. stat-dom-trade, stat-trade and
# stat-domestic-trade all return HTTP 500; the real slug is "local-market",
# under /economy/ rather than /business-statistics/. Section slugs are now
# taken from the site's own industry index rather than guessed.
#
# Two traps in the workbook:
#
# 1. Sheet 1 repeats every row label. "Розничная торговля, всего" appears at
#    the top for the whole country and AGAIN below a "Сельская местность"
#    heading for rural areas only (718bn against 9,016bn). Only the FIRST
#    occurrence is national, so matching is first-hit, not last.
#
# 2. Sheet 2 carries "Республика Казахстан" twice as well -- once under a
#    "Розничная торговля" heading and once under "Оптовая торговля". Lookups
#    are therefore anchored to the section heading, the same fix the Minfin
#    debt-structure rows needed.
#
# The reporting month is read from the sheet's own header ("май 2026г.")
# rather than derived from the publication date. Both agree -- the edition
# published 12.06.2026 reports May -- but the header states the period the
# numbers describe instead of when the file was posted.
#
# The two sheets publish the reporting month's value independently, so the
# index fetcher cross-checks sheet 2 against sheet 1 and refuses the edition
# if they disagree.
# ---------------------------------------------------------------------------
LOCAL_MARKET_PAGE_URL = "https://stat.gov.kz/ru/industries/economy/local-market/"
LOCAL_MARKET_MONTH_RE = re.compile(r"^([А-Яа-яЁё]+)\s+(\d{4})\s*г\.?$")
LOCAL_MARKET_VALUE_TITLE = "1. Объем реализации товаров"
LOCAL_MARKET_INDEX_TITLE = "2. Индексы физического объема"
LOCAL_MARKET_UNIT_WORDS = ("тыс.тенге", "тыс.теңге")
LOCAL_MARKET_REGION = "Республика Казахстан"


def _local_market_editions(indicator_id: str):
    """Yield (reporting_year, reporting_month, workbook, element_id, content).

    Only editions whose sheet 1 carries the expected title are returned, which
    filters out the e-commerce publication that shares the section (its sheets
    are numbered 1.1, 1.2, ...) and any other file listed on the page.
    """
    for eid in _publication_elements(LOCAL_MARKET_PAGE_URL, indicator_id):
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() == "1"), None)
        if sheet is None:
            continue

        title_ok = False
        reporting = None
        for row in wb[sheet].iter_rows(max_row=8, values_only=True):
            for cell in row:
                if not isinstance(cell, str):
                    continue
                text = cell.strip()
                if text.startswith(LOCAL_MARKET_VALUE_TITLE):
                    title_ok = True
                m = LOCAL_MARKET_MONTH_RE.match(text)
                if m and m.group(1).lower() in RU_MONTHS:
                    reporting = (int(m.group(2)), RU_MONTHS[m.group(1).lower()])
        if not title_ok or reporting is None:
            continue
        yield reporting[0], reporting[1], wb, eid, content


def _local_market_row(ws, marker: str, after: str | None = None) -> list | None:
    """First numeric row whose label starts with `marker`, optionally only
    after a row whose label equals `after`."""
    armed = after is None
    for row in ws.iter_rows(values_only=True):
        label = next((c for c in row[:2] if isinstance(c, str)), "")
        label = label.strip()
        if not armed:
            if label == after:
                armed = True
            continue
        if label.startswith(marker):
            nums = [c for c in row if isinstance(c, (int, float))]
            if nums:
                return nums
    return None


def _load_local_market_history(indicator_id: str) -> dict:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue
    return existing


def _local_market_result(indicator_id: str, existing: dict, fetched: dict,
                         what: str, note: str) -> tuple[list[dict], dict]:
    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no edition on {LOCAL_MARKET_PAGE_URL} yielded {what}, "
                "and no previously processed history exists",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )
    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    manifest = {
        "frequency": "monthly",
        "source_url": LOCAL_MARKET_PAGE_URL,
        "dataset_id": f"statistika-vnutrenney-torgovli/{what}",
        "note": note,
    }
    return records, manifest


def _fetch_local_market_value(row_marker: str, indicator_id: str,
                              note: str) -> tuple[list[dict], dict]:
    existing = _load_local_market_history(indicator_id)
    fetched: dict[str, float] = {}
    for year, month, wb, eid, content in _local_market_editions(indicator_id):
        ws = wb[next(s for s in wb.sheetnames if s.strip() == "1")]
        unit_ok = False
        for row in ws.iter_rows(max_row=8, values_only=True):
            for cell in row:
                if isinstance(cell, str) and any(w in "".join(cell.split()) for w in LOCAL_MARKET_UNIT_WORDS):
                    unit_ok = True
        nums = _local_market_row(ws, row_marker)
        if nums is None or len(nums) < 2:
            continue
        if not unit_ok:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: sheet 1 of element {eid} no longer declares its unit as one "
                    f"of {LOCAL_MARKET_UNIT_WORDS!r}",
                    "EXPECTED: thousand KZT; a changed unit would rescale the series silently",
                    "ACTION REQUIRED: inspect the publication and update scripts/fetchers/bns.py",
                ])
            )
        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/",
                   "element_id": eid, "reporting_month": f"{year:04d}-{month:02d}",
                   "sheet": "1", "row": row_marker})
        # nums: [year-to-date, reporting month, share YTD, share month]
        fetched[f"{year:04d}-{month:02d}-01"] = float(nums[1])

    return _local_market_result(indicator_id, existing, fetched,
                                f"sheet-1/{row_marker}", note)


def _fetch_local_market_index(section: str, value_marker: str, indicator_id: str,
                              note: str) -> tuple[list[dict], dict]:
    existing = _load_local_market_history(indicator_id)
    fetched: dict[str, float] = {}
    for year, month, wb, eid, content in _local_market_editions(indicator_id):
        sheet = next((s for s in wb.sheetnames if s.strip() == "2"), None)
        if sheet is None:
            continue
        ws = wb[sheet]
        if not any(isinstance(c, str) and c.strip().startswith(LOCAL_MARKET_INDEX_TITLE)
                   for row in ws.iter_rows(max_row=4, values_only=True) for c in row):
            continue
        nums = _local_market_row(ws, LOCAL_MARKET_REGION, after=section)
        if nums is None or len(nums) < 5:
            continue

        # Sheet 2 republishes the reporting month's value that sheet 1 carries.
        # They are produced independently, so a mismatch means one of the two
        # lookups has drifted onto the wrong row.
        cross = _local_market_row(wb[next(s for s in wb.sheetnames if s.strip() == "1")], value_marker)
        if cross is None or len(cross) < 2 or abs(cross[1] - nums[1]) > 1:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: element {eid} sheet 2 reports {nums[1]!r} for the reporting "
                    f"month under {section!r}, but sheet 1 row {value_marker!r} reports "
                    f"{cross[1] if cross and len(cross) > 1 else None!r}",
                    "EXPECTED: the two sheets publish the same monthly value",
                    "ACTION REQUIRED: inspect the publication and update scripts/fetchers/bns.py",
                ])
            )

        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/",
                   "element_id": eid, "reporting_month": f"{year:04d}-{month:02d}",
                   "sheet": "2", "section": section})
        # nums: [YTD value, month value, month vs same month last year,
        #        month vs previous month, period vs same period last year]
        fetched[f"{year:04d}-{month:02d}-01"] = float(nums[2])

    return _local_market_result(indicator_id, existing, fetched,
                                f"sheet-2/{section}", note)


def fetch_retail_trade_monthly() -> tuple[list[dict], dict]:
    """Retail trade turnover, thousand KZT, monthly."""
    return _fetch_local_market_value(
        "Розничная торговля, всего", "RETAIL_TRADE_MONTHLY",
        "Thousand KZT, single month (not cumulative). Retail sales of goods and services, whole "
        "country. The existing RETAIL_TRADE series carries the same concept ANNUALLY from the "
        "stat.gov.kz cubes; this is the monthly publication behind it. Accumulated across runs "
        "because the source keeps only a few editions online. Note the source sheet repeats this "
        "row label for rural areas alone further down -- this is the national figure.")


def fetch_wholesale_trade_monthly() -> tuple[list[dict], dict]:
    """Wholesale trade turnover, thousand KZT, monthly."""
    return _fetch_local_market_value(
        "Оптовая торговля", "WHOLESALE_TRADE_MONTHLY",
        "Thousand KZT, single month. Wholesale sales of goods, whole country, from the same sheet "
        "as RETAIL_TRADE_MONTHLY. Wholesale runs roughly twice retail in Kazakhstan (19.6 against "
        "9.0 trillion KZT over January-May 2026). Monthly companion to the annual WHOLESALE_TRADE.")


def fetch_retail_trade_index_monthly() -> tuple[list[dict], dict]:
    """Retail trade physical volume index, same month previous year = 100."""
    return _fetch_local_market_index(
        "Розничная торговля", "Розничная торговля, всего", "RETAIL_TRADE_INDEX_MONTHLY",
        "Index, same month of the previous year = 100 -- retail volume in REAL terms, the "
        "consumption-side companion to RETAIL_TRADE_MONTHLY, which is in current prices. Monthly "
        "replacement for the annual RETAIL_TRADE_VOLUME_INDEX. The source row also publishes "
        "month-on-month and year-to-date comparisons; this is the year-on-year monthly one.")


def fetch_wholesale_trade_index_monthly() -> tuple[list[dict], dict]:
    """Wholesale trade physical volume index, same month previous year = 100."""
    return _fetch_local_market_index(
        "Оптовая торговля", "Оптовая торговля", "WHOLESALE_TRADE_INDEX_MONTHLY",
        "Index, same month of the previous year = 100. Wholesale volume in real terms, on the same "
        "basis as RETAIL_TRADE_INDEX_MONTHLY and from the same sheet, which carries a separate "
        "regional block per trade type.")


# ---------------------------------------------------------------------------
# Monthly construction output, from the BNS publication "Основные показатели
# предприятий и организаций, осуществляющих строительную деятельность"
# (section "Строительство и инновации").
#
# Closes the audit's construction gap in the real sector.
#
# THE MIXED-PERIODICITY TRAP AGAIN, and this time the source hands over the
# answer. The section carries three cadences side by side:
#
#   335623  published 18.08.2026, next 17.09.2026  (+30d)  Январь-июль 2026
#   347225  published 17.07.2026, next 18.08.2026  (+32d)  Январь-июнь 2026
#   5224    published 24.07.2026, next 23.10.2026  (+91d)  quarterly, different
#                                                          publication entirely
#   347234  published 03.07.2026, next 05.07.2027 (+367d)  2025 год -- ANNUAL
#
# The annual edition has the SAME sheet name and the SAME row label, and its
# value (10.85 trillion KZT for 2025) would be read as a monthly year-to-date
# point if nothing separated it. This is exactly what went wrong with
# INVESTMENT_FIXED_CAPITAL before the edition-gap filter was added.
#
# Unlike the investment publication, this one states BOTH facts on its cover:
# the interval to the next release (which identifies the cadence) and the
# period the numbers cover ("Январь-июль 2026 года"). So the reporting month is
# READ, not inferred from the publication date, and editions are admitted only
# when their release interval is monthly.
#
# Values are YEAR-TO-DATE CUMULATIVE -- the column header says "в процентах к
# соответствующему ПЕРИОДУ прошлого года" and the cover names a January-to-month
# span. 5.06 trillion KZT for January-July 2026 against 10.85 trillion for all
# of 2025 is consistent: construction in Kazakhstan is strongly back-loaded, so
# seven months carrying about 40% of the year is the expected seasonal shape,
# not a contradiction of the +15.3% growth the same row reports.
# ---------------------------------------------------------------------------
CONSTRUCTION_PAGE_URL = "https://stat.gov.kz/ru/industries/business-statistics/stat-inno-build/"
CONSTRUCTION_ROW_MARKER = "Объем выполненных строительных работ"
CONSTRUCTION_UNIT_WORDS = ("тыс.теңге", "тыс.тенге")
CONSTRUCTION_PERIOD_RE = re.compile(r"^(?:Январь\s*-\s*)?([А-Яа-яЁё]+)\s+(\d{4})\s*года$")
CONSTRUCTION_NEXT_RE = re.compile(r"Дата следующего опубликования:\s*(\d{2})\.(\d{2})\.(\d{4})")
CONSTRUCTION_MAX_GAP_DAYS = 40  # a monthly release; the annual one is 367, the quarterly 91


def _fetch_construction_series(value_index: int, indicator_id: str, note: str,
                               unit_check: bool) -> tuple[list[dict], dict]:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    for eid in _publication_elements(CONSTRUCTION_PAGE_URL, indicator_id):
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() in ("1.", "1")), None)
        if sheet is None:
            continue

        published = nxt = None
        period = None
        for sh in wb.sheetnames[:3]:
            for row in wb[sh].iter_rows(max_row=24, values_only=True):
                for cell in row:
                    if not isinstance(cell, str):
                        continue
                    text = cell.strip()
                    m = PUBLISHED_RE.search(text)
                    if m:
                        published = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                    m2 = CONSTRUCTION_NEXT_RE.search(text)
                    if m2:
                        nxt = date(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
                    m3 = CONSTRUCTION_PERIOD_RE.match(text)
                    if m3 and m3.group(1).lower() in RU_MONTHS:
                        period = (int(m3.group(2)), RU_MONTHS[m3.group(1).lower()])
            if published and period:
                break

        # Admit monthly editions only. The annual and quarterly releases share
        # this sheet name and row label, and their values are not comparable.
        if published is None or nxt is None or period is None:
            continue
        if (nxt - published).days > CONSTRUCTION_MAX_GAP_DAYS:
            continue

        unit_ok = not unit_check
        target = None
        for row in wb[sheet].iter_rows(values_only=True):
            for cell in row[:8]:
                if isinstance(cell, str) and any(w in "".join(cell.split()) for w in CONSTRUCTION_UNIT_WORDS):
                    unit_ok = True
            label = next((c for c in row[:2] if isinstance(c, str)), "")
            if target is None and label.strip().startswith(CONSTRUCTION_ROW_MARKER):
                target = [c for c in row if isinstance(c, (int, float))]
        if target is None or len(target) <= value_index:
            continue
        if not unit_ok:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                    f"WHAT CHANGED: sheet {sheet!r} of element {eid} no longer declares its unit "
                    f"as one of {CONSTRUCTION_UNIT_WORDS!r}",
                    "EXPECTED: thousand KZT; a changed unit would rescale the series silently",
                    f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
                ])
            )

        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": url, "element_id": eid,
                   "published": published.isoformat(), "next_publication": nxt.isoformat(),
                   "period": f"{period[0]:04d}-{period[1]:02d}", "sheet": sheet})
        fetched[f"{period[0]:04d}-{period[1]:02d}-01"] = float(target[value_index])

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no monthly edition on {CONSTRUCTION_PAGE_URL} carried a sheet '1.' "
                f"with a row starting {CONSTRUCTION_ROW_MARKER!r}, a cover period and a release "
                f"interval of at most {CONSTRUCTION_MAX_GAP_DAYS} days, and no processed history "
                "exists",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]

    # Year-to-date values cannot fall inside a calendar year. If one does, an
    # edition of a different periodicity has slipped past the gap filter -- the
    # failure mode that produced a 23.5-trillion "June" investment figure.
    if value_index == 0:
        for prev, cur in zip(records, records[1:]):
            if prev["date"][:4] == cur["date"][:4] and cur["value"] < prev["value"]:
                raise validation.StructuralChangeError(
                    "\n".join([
                        f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                        f"WHAT CHANGED: year-to-date value fell within {cur['date'][:4]} -- "
                        f"{prev['date']}={prev['value']:,.0f} then {cur['date']}={cur['value']:,.0f}",
                        "EXPECTED: a cumulative series never decreases inside a year; a fall means "
                        "editions of different periodicity have been mixed",
                        f"ACTION REQUIRED: inspect {CONSTRUCTION_PAGE_URL} and update "
                        "scripts/fetchers/bns.py",
                    ])
                )

    manifest = {
        "frequency": "monthly",
        "source_url": CONSTRUCTION_PAGE_URL,
        "dataset_id": f"stroitelnaya-deyatelnost/sheet-1/{CONSTRUCTION_ROW_MARKER}/col{value_index}",
        "note": note,
    }
    return records, manifest


def fetch_construction_output() -> tuple[list[dict], dict]:
    """Construction work performed, thousand KZT, year-to-date cumulative."""
    return _fetch_construction_series(
        0, "CONSTRUCTION_OUTPUT",
        "Thousand KZT, YEAR-TO-DATE CUMULATIVE (not a monthly flow) -- the cover names a "
        "January-to-month span and the sheet compares against the same PERIOD of the previous "
        "year. 5.06 trillion KZT for January-July 2026. Kazakhstan's construction is strongly "
        "seasonal and back-loaded, so seven months carry only about 40% of the annual total. "
        "The section also publishes annual and quarterly editions with the same sheet and row "
        "label; only editions whose cover states a monthly release interval are read. "
        "Accumulated across runs because the source keeps only a few editions online.",
        unit_check=True)


def fetch_construction_index() -> tuple[list[dict], dict]:
    """Construction work, index against the same period a year earlier."""
    return _fetch_construction_series(
        1, "CONSTRUCTION_INDEX",
        "Index, same period of the previous year = 100, year-to-date. The real-terms companion to "
        "CONSTRUCTION_OUTPUT, which is in current prices.",
        unit_check=False)


# ---------------------------------------------------------------------------
# Quarterly labour market and wages, from two BNS publications:
#   "Основные индикаторы рынка труда Республики Казахстан"  (stat-empt-unempl)
#   "Численность наемных работников, фонд заработной платы, среднемесячная
#    заработная плата"                                       (stat-wags)
#
# Closes several audit items at once: labour force participation, the
# unemployment counts behind the rate, youth and long-term unemployment, and
# quarterly wages. The dataset previously held UNEMPLOYMENT (quarterly, but
# stale since 2025-06), EMPLOYED_TOTAL (annual), AVG_WAGE (annual) and
# REAL_WAGE_INDEX (annual) -- no participation rate at all.
#
# BOTH SECTIONS MIX ANNUAL AND QUARTERLY EDITIONS under identical titles and
# identical sheet names, the same trap as construction. The discriminator here
# is cleaner than a release-interval heuristic: every quarterly edition names
# its quarter on the cover ("I квартал 2026 года"), and the annual ones say
# "2025 год" instead. An edition whose cover carries no quarter is not read.
# The release interval is checked as well, so both would have to change
# together for an annual figure to be mistaken for a quarterly one.
#
# Column 1 of the labour table is "Все население" (everyone aged 15 and over);
# the columns beside it split by sex and then repeat the whole set for the
# working-age population only. Only the first is read.
#
# Cross-check on wages: annual AVG_WAGE reads 443,315 KZT for 2025 and this
# publication reads 445,068 KZT for Q1 2026 -- two independently sourced series
# meeting where they should.
# ---------------------------------------------------------------------------
LABOUR_PAGE_URL = "https://stat.gov.kz/ru/industries/labor-and-income/stat-empt-unempl/"
WAGES_PAGE_URL = "https://stat.gov.kz/ru/industries/labor-and-income/stat-wags/"
QUARTER_RE = re.compile(r"\b(IV|III|II|I)\s*квартал\w*\s+(\d{4})", re.I)
QUARTER_NUM = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
# Quarter START, matching lib/periods.py. This mapping used to give quarter
# ENDS, which put every series from this helper on a different convention
# from the rest of the project. It survived the convention sweep because the
# sweep normalised what was WRITTEN, while the accumulate merge here keys on
# what the fetcher BUILDS -- so stored 2026-01-01 and fresh 2026-03-31 both
# survived the merge and then collapsed onto one date, which surfaced as 24
# duplicate-date errors rather than as anything subtle.
QUARTER_START = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
LABOUR_SHEET_TITLE = "1. Основные индикаторы рынка труда"
WAGES_SHEET_TITLE = "1. Численность наемных работников"
QUARTERLY_MAX_GAP_DAYS = 100  # the annual editions in both sections run 344-366


def _quarterly_editions(page_url: str, sheet_name: str, sheet_title: str,
                        indicator_id: str):
    """Yield (year, quarter, worksheet, element_id, content) for quarterly editions.

    Editions whose cover does not name a quarter, or whose next release is more
    than a quarter away, are skipped -- that is what keeps the annual editions
    published under the same title out of a quarterly series.
    """
    for eid in _publication_elements(page_url, indicator_id):
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() == sheet_name), None)
        if sheet is None:
            continue

        cover = next((s for s in wb.sheetnames if s.strip().startswith("Обложка")), None)
        if cover is None:
            continue
        published = nxt = None
        quarter = None
        for row in wb[cover].iter_rows(max_row=24, values_only=True):
            for cell in row:
                if not isinstance(cell, str):
                    continue
                text = cell.strip()
                m = PUBLISHED_RE.search(text)
                if m:
                    published = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                m2 = CONSTRUCTION_NEXT_RE.search(text)
                if m2:
                    nxt = date(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
                m3 = QUARTER_RE.search(text)
                if m3:
                    quarter = (int(m3.group(2)), QUARTER_NUM[m3.group(1).lower()])
        if quarter is None:
            continue
        if published and nxt and (nxt - published).days > QUARTERLY_MAX_GAP_DAYS:
            continue

        ws = wb[sheet]
        if not any(isinstance(c, str) and c.strip().startswith(sheet_title)
                   for row in ws.iter_rows(max_row=4, values_only=True) for c in row):
            continue
        yield quarter[0], quarter[1], ws, eid, content


def _fetch_quarterly_publication_row(page_url: str, sheet_name: str, sheet_title: str,
                                     row_marker: str, value_index: int, exact: bool,
                                     indicator_id: str, note: str,
                                     unit: str, identity=None) -> tuple[list[dict], dict]:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    for year, quarter, ws, eid, content in _quarterly_editions(
            page_url, sheet_name, sheet_title, indicator_id):
        target = None
        for row in ws.iter_rows(values_only=True):
            label = next((c for c in row[:2] if isinstance(c, str)), "")
            label = label.strip()
            hit = (label == row_marker) if exact else label.startswith(row_marker)
            if target is None and hit:
                target = [c for c in row if isinstance(c, (int, float))]
        if target is None or len(target) <= value_index:
            continue
        if identity is not None:
            identity(ws, float(target[value_index]), indicator_id, eid)
        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/",
                   "element_id": eid, "quarter": f"{year:04d}Q{quarter}",
                   "sheet": sheet_name, "row": row_marker})
        fetched[f"{year:04d}-{QUARTER_START[quarter]}"] = float(target[value_index])

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no quarterly edition on {page_url} carried sheet {sheet_name!r} "
                f"titled {sheet_title!r} with a row matching {row_marker!r}, and no processed "
                "history exists",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]
    manifest = {
        "frequency": "quarterly",
        "source_url": page_url,
        "dataset_id": f"{sheet_title}/{row_marker}/col{value_index}",
        "note": note,
        "unit": unit,
    }
    return records, manifest


def _fetch_labour_row(row_marker: str, indicator_id: str, note: str,
                      unit: str, identity_check: bool = False) -> tuple[list[dict], dict]:
    # Column 1 is "Все население"; the rest split by sex and repeat for the
    # working-age population.
    return _fetch_quarterly_publication_row(
        LABOUR_PAGE_URL, "1.", LABOUR_SHEET_TITLE, row_marker, 0, False,
        indicator_id, note, unit,
        identity=_labour_identity if identity_check else None)


def _labour_identity(ws, value: float, indicator_id: str, eid: int) -> None:
    """Employed + unemployed must equal the labour force, on the same sheet.

    The table states all three independently, so this is a real check on the
    row lookups rather than a restatement of one number. It is run while the
    worksheet is already open, so it costs no extra download.
    """
    parts = {}
    for row in ws.iter_rows(values_only=True):
        label = next((c for c in row[:2] if isinstance(c, str)), "").strip()
        for key, marker in (("employed", "Занятое население, человек"),
                            ("unemployed", "Безработное население, человек")):
            if key not in parts and label.startswith(marker):
                nums = [c for c in row if isinstance(c, (int, float))]
                if nums:
                    parts[key] = float(nums[0])
    if len(parts) != 2:
        return
    total = parts["employed"] + parts["unemployed"]
    if abs(total - value) > 1:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: element {eid} reports a labour force of {value:,.0f}, but "
                f"employed ({parts['employed']:,.0f}) plus unemployed "
                f"({parts['unemployed']:,.0f}) is {total:,.0f}",
                "EXPECTED: the table states all three independently and they must add up; a "
                "mismatch means a row lookup has drifted",
                f"ACTION REQUIRED: inspect {LABOUR_PAGE_URL} and update scripts/fetchers/bns.py",
            ])
        )


def _fetch_wage_row(value_index: int, indicator_id: str, note: str,
                    unit: str) -> tuple[list[dict], dict]:
    return _fetch_quarterly_publication_row(
        WAGES_PAGE_URL, "1", WAGES_SHEET_TITLE, "Всего", value_index, True,
        indicator_id, note, unit)


def fetch_labor_force() -> tuple[list[dict], dict]:
    """Labour force, persons, quarterly."""
    return _fetch_labour_row(
        "Рабочая сила, человек", "LABOR_FORCE",
        "Persons aged 15 and over who are employed or unemployed, whole country. 9.84 million in "
        "Q1 2026. The denominator behind the unemployment and participation rates. Checked "
        "against the same sheet's employed and unemployed counts, which must add up to it.",
        "persons", identity_check=True)


def fetch_labor_force_participation_rate() -> tuple[list[dict], dict]:
    """Labour force participation rate, percent, quarterly."""
    return _fetch_labour_row(
        "Уровень участия в рабочей силе", "LABOR_FORCE_PARTICIPATION_RATE",
        "Percent of the population aged 15 and over that is in the labour force. 67.2% in Q1 2026. "
        "Flagged by the sector audit as missing entirely: without it, a falling unemployment rate "
        "cannot be told apart from people leaving the labour force.", "% of population 15+")


def fetch_employed_quarterly() -> tuple[list[dict], dict]:
    """Employed population, persons, quarterly."""
    return _fetch_labour_row(
        "Занятое население, человек", "EMPLOYED_QUARTERLY",
        "Persons. Quarterly companion to the annual EMPLOYED_TOTAL. 9.39 million in Q1 2026, of "
        "whom 7.29 million are employees and 2.10 million self-employed -- a split that matters in "
        "Kazakhstan, where self-employment absorbs much of what would otherwise be unemployment.",
        "persons")


def fetch_unemployed_persons() -> tuple[list[dict], dict]:
    """Unemployed population, persons, quarterly."""
    return _fetch_labour_row(
        "Безработное население, человек", "UNEMPLOYED_PERSONS",
        "Persons. The count behind the existing UNEMPLOYMENT rate series, which is stale since "
        "2025-06. 446,049 in Q1 2026.", "persons")


def fetch_youth_unemployment_rate() -> tuple[list[dict], dict]:
    """Youth unemployment rate, percent, quarterly."""
    return _fetch_labour_row(
        "Уровень молодежной безработицы", "YOUTH_UNEMPLOYMENT_RATE",
        "Percent. Unemployment among people aged 15-34, as the source defines youth (Law «On State Youth Policy»). 3.0% in "
        "Q1 2026 -- below the headline rate of 4.5%, the reverse of the usual pattern in most "
        "economies.", "%")


def fetch_long_term_unemployment_rate() -> tuple[list[dict], dict]:
    """Long-term unemployment rate, percent, quarterly."""
    return _fetch_labour_row(
        "Уровень долгосрочной безработицы", "LONG_TERM_UNEMPLOYMENT_RATE",
        "Percent. Share of the labour force unemployed for a year or more. 1.6% in Q1 2026, about "
        "a third of total unemployment -- the structural component of the headline rate.", "%")


def fetch_avg_wage_quarterly() -> tuple[list[dict], dict]:
    """Average monthly nominal wage, KZT, quarterly."""
    return _fetch_wage_row(
        3, "AVG_WAGE_QUARTERLY",
        "KZT per month, including small enterprises. Quarterly companion to the annual AVG_WAGE. "
        "445,068 KZT in Q1 2026, against 443,315 KZT for all of 2025 in the annual series -- two "
        "independently sourced series meeting where they should.", "KZT")


def fetch_real_wage_index_quarterly() -> tuple[list[dict], dict]:
    """Real wage index, same quarter previous year = 100, quarterly."""
    return _fetch_wage_row(
        7, "REAL_WAGE_INDEX_QUARTERLY",
        "Index, same quarter of the previous year = 100. Wages after inflation. 99.8 in Q1 2026 -- "
        "nominal wages up 11.5% year on year but real wages flat, which is the number that matters "
        "for consumption. The source row also publishes a quarter-on-quarter version; this is the "
        "year-on-year one.", "index (same quarter previous year = 100)")


# ---------------------------------------------------------------------------
# Monthly transport, from the BNS publication "Основные показатели работы
# транспорта по видам экономической деятельности" (section "Транспорт").
#
# Closes the audit's freight and passenger turnover gap. The existing
# FREIGHT_TURNOVER is ANNUAL and PASSENGER_TURNOVER is annual AND stops at 2016.
#
# TWO THINGS HERE ARE UNLIKE EVERY OTHER PUBLICATION USED IN THIS PROJECT.
#
# 1. THE CELLS ARE TEXT, NOT NUMBERS. openpyxl returns '540451.13' as a string.
#    The isinstance(cell, (int, float)) filter used everywhere else in this
#    module would have returned an EMPTY list of values here, and the fetcher
#    would have silently found nothing. Values are parsed with _transport_num,
#    and columns are addressed by ABSOLUTE POSITION rather than by their
#    position among the numeric cells -- the latter is meaningless when some
#    cells hold a dash for a mode that does not carry that traffic.
#
# 2. THE COVER CARRIES NO PUBLICATION DATE, only the period ("Январь-июль 2026
#    года"). That is the better of the two anyway, and it is what is used.
#
# Column layout of sheet '1.', read from the header rows:
#   c1 перевезено грузов, тыс. тонн      c2 % to same period last year
#   c3 грузооборот, млн. т-км            c4 %
#   c5 перевезено пассажиров, тыс. чел.  c6 %
#   c7 пассажирооборот, млн. п-км        c8 %
#   c9 доходы от перевозок, млн. теңге
#
# RECONCILIATION AGAINST THE EXISTING ANNUAL SERIES -- one matches, one does not:
#
#   Freight turnover:   298,327.53 mln t-km for January-July 2026 annualises to
#                       511 bn t-km, against 512.6 bn in the annual
#                       FREIGHT_TURNOVER for 2025. Effectively exact.
#   Passenger turnover: 54,627.9 mln p-km for January-July 2026 annualises to
#                       about 94 bn p-km, against 266.8 bn in the annual
#                       PASSENGER_TURNOVER for 2016 -- a level roughly three
#                       times higher.
#
# The passenger break is NOT explained here. The old annual series ends in 2016
# and the long-run archive in the same section covers passengers CARRIED, a
# different indicator, so nothing available resolves it. The two are therefore
# kept as separate series and must not be spliced. Recorded as an open question
# rather than smoothed over.
# ---------------------------------------------------------------------------
TRANSPORT_PAGE_URL = "https://stat.gov.kz/ru/industries/business-statistics/stat-transport/"
TRANSPORT_SHEET_TITLE = "1. Основные показатели работы транспорта"
TRANSPORT_ROW_MARKER = "Всего"
TRANSPORT_COL_FREIGHT_CARRIED = 1
TRANSPORT_COL_FREIGHT_TURNOVER = 3
TRANSPORT_COL_PASSENGERS_CARRIED = 5
TRANSPORT_COL_PASSENGER_TURNOVER = 7
TRANSPORT_BLANKS = {"-", "–", "…", ".."}


def _transport_num(cell):
    """Parse a cell that may be a number, a numeric string, or a dash."""
    if isinstance(cell, (int, float)):
        return float(cell)
    if not isinstance(cell, str):
        return None
    text = cell.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not text or text in TRANSPORT_BLANKS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fetch_transport_column(column: int, indicator_id: str, note: str,
                            cumulative: bool) -> tuple[list[dict], dict]:
    existing = {}
    path = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
            / f"{indicator_id.lower()}.csv")
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    for eid in _publication_elements(TRANSPORT_PAGE_URL, indicator_id):
        url = f"https://stat.gov.kz/api/iblock/element/{eid}/file/ru/"
        try:
            content = _download(url)
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception:
            continue
        sheet = next((s for s in wb.sheetnames if s.strip() == "1."), None)
        if sheet is None:
            continue
        ws = wb[sheet]
        if not any(isinstance(c, str) and c.strip().startswith(TRANSPORT_SHEET_TITLE)
                   for row in ws.iter_rows(max_row=3, values_only=True) for c in row):
            continue

        period = None
        for sh in wb.sheetnames[:3]:
            for row in wb[sh].iter_rows(max_row=24, values_only=True):
                for cell in row:
                    if isinstance(cell, str):
                        m = CONSTRUCTION_PERIOD_RE.match(cell.strip())
                        if m and m.group(1).lower() in RU_MONTHS:
                            period = (int(m.group(2)), RU_MONTHS[m.group(1).lower()])
            if period:
                break
        if period is None:
            continue

        value = None
        for row in ws.iter_rows(values_only=True):
            label = next((c for c in row[:1] if isinstance(c, str)), "")
            if label.strip().startswith(TRANSPORT_ROW_MARKER) and len(row) > column:
                value = _transport_num(row[column])
                break
        if value is None:
            continue

        _save_raw(f"{indicator_id}_{eid}", content, "xlsx",
                  {"source_url": url, "element_id": eid,
                   "period": f"{period[0]:04d}-{period[1]:02d}", "sheet": "1.",
                   "column": column})
        fetched[f"{period[0]:04d}-{period[1]:02d}-01"] = value

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                f"WHAT CHANGED: no edition on {TRANSPORT_PAGE_URL} carried sheet '1.' titled "
                f"{TRANSPORT_SHEET_TITLE!r} with a row starting {TRANSPORT_ROW_MARKER!r}, a "
                f"parseable value in column {column} and a cover period, and no processed "
                "history exists",
                "NOTE: this sheet stores its values as TEXT, not numbers -- a numeric-cell filter "
                "finds nothing here",
                "ACTION REQUIRED: inspect the page and update scripts/fetchers/bns.py",
            ])
        )

    records = [{"date": k, "value": v} for k, v in sorted(merged.items())]

    if cumulative:
        for prev, cur in zip(records, records[1:]):
            if prev["date"][:4] == cur["date"][:4] and cur["value"] < prev["value"]:
                raise validation.StructuralChangeError(
                    "\n".join([
                        f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                        f"WHAT CHANGED: year-to-date value fell within {cur['date'][:4]} -- "
                        f"{prev['date']}={prev['value']:,.1f} then "
                        f"{cur['date']}={cur['value']:,.1f}",
                        "EXPECTED: a cumulative series never decreases inside a year",
                        f"ACTION REQUIRED: inspect {TRANSPORT_PAGE_URL} and update "
                        "scripts/fetchers/bns.py",
                    ])
                )

    manifest = {
        "frequency": "monthly",
        "source_url": TRANSPORT_PAGE_URL,
        "dataset_id": f"pokazateli-raboty-transporta/sheet-1/vsego/col{column}",
        "note": note,
    }
    return records, manifest


def fetch_freight_turnover_monthly() -> tuple[list[dict], dict]:
    """Freight turnover, million tonne-km, year-to-date cumulative."""
    return _fetch_transport_column(
        TRANSPORT_COL_FREIGHT_TURNOVER, "FREIGHT_TURNOVER_MONTHLY",
        "Million tonne-km, YEAR-TO-DATE CUMULATIVE, all modes. Monthly companion to the annual "
        "FREIGHT_TURNOVER, and it reconciles with it: 298,327.53 mln t-km for January-July 2026 "
        "annualises to 511 bn against 512.6 bn reported for 2025. Note the source stores these "
        "cells as TEXT rather than numbers.", cumulative=True)


def fetch_passenger_turnover_monthly() -> tuple[list[dict], dict]:
    """Passenger turnover, million passenger-km, year-to-date cumulative."""
    return _fetch_transport_column(
        TRANSPORT_COL_PASSENGER_TURNOVER, "PASSENGER_TURNOVER_MONTHLY",
        "Million passenger-km, YEAR-TO-DATE CUMULATIVE, all modes. DO NOT SPLICE THIS ONTO THE "
        "ANNUAL PASSENGER_TURNOVER SERIES. That series ends in 2016 at 266.8 bn p-km, while this "
        "one reads 54,627.9 mln p-km for January-July 2026, or about 94 bn annualised -- roughly "
        "a third of the old level. The break is unexplained: nothing published in this section "
        "resolves it, since the long-run archive there covers passengers CARRIED, a different "
        "indicator. Kept as a separate series and flagged rather than smoothed over.",
        cumulative=True)


def fetch_freight_carried() -> tuple[list[dict], dict]:
    """Freight carried, thousand tonnes, year-to-date cumulative."""
    return _fetch_transport_column(
        TRANSPORT_COL_FREIGHT_CARRIED, "FREIGHT_CARRIED",
        "Thousand tonnes, YEAR-TO-DATE CUMULATIVE, all modes. Physical tonnage, the companion to "
        "FREIGHT_TURNOVER_MONTHLY, which weights tonnage by distance. Read together they separate "
        "how much moved from how far it moved.", cumulative=True)


def fetch_passengers_carried() -> tuple[list[dict], dict]:
    """Passengers carried, thousand people, year-to-date cumulative."""
    return _fetch_transport_column(
        TRANSPORT_COL_PASSENGERS_CARRIED, "PASSENGERS_CARRIED",
        "Thousand people, YEAR-TO-DATE CUMULATIVE, all modes. The count companion to "
        "PASSENGER_TURNOVER_MONTHLY.", cumulative=True)


# ---------------------------------------------------------------------------
# Income inequality and poverty depth, from the quarterly BNS publication
# "Основные показатели дифференциации доходов населения" (section
# "Уровень жизни"), sheet 5 "Основные показатели бедности".
#
# Closes the audit's Gini gap. The dataset held POVERTY_HEADCOUNT but no
# measure of how income is DISTRIBUTED, so a falling poverty rate could not be
# told apart from a widening gap above the poverty line.
#
# Read by fetchers/bns_living.py from every edition of the publication (its
# listing, name=18651), quarterly and annual kept apart by the cover text.
#
# THE COUNTRY ROW IS LABELLED IN KAZAKH -- "Қазақстан Республикасы" -- in the
# quarterly editions, even in the Russian-language file; the annual ones use
# "Республика Казахстан". Both are accepted.
#
# Sheet 5 column layout: [глубина бедности %, острота бедности %, коэффициент
# Джини по 10% группам, коэффициент Джини по 20% группам, соотношение доходов
# 10% наиболее и 10% наименее обеспеченных].
#
# The sheet publishes TWO Gini coefficients, computed over decile and quintile
# groups (0.283 and 0.269 for Q1 2026). The decile one is taken as the headline
# because it is the finer partition; the quintile variant is a methodological
# alternative of the same concept and is deliberately not added as a separate
# series.
# ---------------------------------------------------------------------------
LIVING_PAGE_URL = "https://stat.gov.kz/ru/industries/labor-and-income/stat-life/"


# Until 2026-09-25 these read only the editions linked from LIVING_PAGE_URL -- the latest
# one -- so each series held a single quarter. They now read every edition of the
# «Основные показатели дифференциации доходов» listing (III quarter 2022 onward, the
# columns found by header text) through fetchers/bns_living.py; the Gini adds Taldau's
# quarterly history (704502) for the quarters before the first edition.
POVERTY_COLUMNS = {0: ("depth", None), 1: ("severity", None), 2: ("gini10", "704502"), 4: ("ratio", None)}


def _fetch_poverty_row(value_index: int, indicator_id: str, note: str,
                       unit: str) -> tuple[list[dict], dict]:
    from fetchers import bns_living
    key, taldau_index = POVERTY_COLUMNS[value_index]
    records, manifest = bns_living.poverty_series(indicator_id, key, "quarterly", taldau_index, note)
    manifest["unit"] = unit
    return records, manifest


def fetch_gini_coefficient() -> tuple[list[dict], dict]:
    """Gini coefficient over decile groups, quarterly."""
    return _fetch_poverty_row(
        2, "GINI_COEFFICIENT",
        "Gini coefficient of income, computed over 10% (decile) population groups. 0.283 for "
        "Q1 2026 -- low by international standards. The dataset held POVERTY_HEADCOUNT but no "
        "measure of how income is DISTRIBUTED, so a falling poverty rate could not be told apart "
        "from a widening gap above the poverty line. The source also publishes a quintile-based "
        "Gini (0.269 for the same quarter); this is the decile one, the finer partition.",
        "coefficient (0-1)")


def fetch_decile_income_ratio() -> tuple[list[dict], dict]:
    """Ratio of income of the richest to the poorest decile, quarterly."""
    return _fetch_poverty_row(
        4, "DECILE_INCOME_RATIO",
        "Ratio of the income of the richest 10% to the poorest 10%. 5.66 in Q1 2026. Reads the "
        "same distribution as GINI_COEFFICIENT but at the tails, where the Gini is least "
        "sensitive.", "ratio")


def fetch_poverty_depth() -> tuple[list[dict], dict]:
    """Poverty depth, percent, quarterly."""
    return _fetch_poverty_row(
        0, "POVERTY_DEPTH",
        "Percent. How far below the subsistence minimum the poor fall on average, weighted by the "
        "population -- 0.9% in Q1 2026. POVERTY_HEADCOUNT counts who is poor; this measures how "
        "poor, and the two can move in opposite directions.", "%")


def fetch_poverty_severity() -> tuple[list[dict], dict]:
    """Poverty severity, percent, quarterly."""
    return _fetch_poverty_row(
        1, "POVERTY_SEVERITY",
        "Percent. The squared poverty gap, which weights the deepest shortfalls most heavily -- "
        "0.2% in Q1 2026. Read with POVERTY_DEPTH and POVERTY_HEADCOUNT as the standard "
        "Foster-Greer-Thorbecke set.", "%")


# ---------------------------------------------------------------------------
# CORE INFLATION, from Taldau. The audit listed it as a monetary-sector gap and
# it had never been searched for.
#
# THE SOURCE PUBLISHES TWO CORE BASKETS, not one, and they are separate Taldau
# indexes rather than two terms of one dimension:
#   55056856  "базовый ИПЦ без трех составляющих"  -- excludes fruit and
#             vegetables, petrol and coal
#   55056857  "базовый ИПЦ без семи составляющих"  -- also excludes regulated
#             utilities, rail transport and others
# The parent index 703082 ("Базовый индекс потребительских цен") returns an
# EMPTY segment list for every period tried, so it is a catalogue heading
# rather than a series.
#
# periodId=5 IS QUARTERLY HERE, not monthly. Fourteen points span 2023-03-31 to
# 2026-06-30, and the values confirm it: the period-on-period reading is
# 102.6-103.2, which as a monthly rate would annualise to about 36% and as a
# quarterly rate to about 11% -- matching the year-on-year reading of
# 111.4-112.5 on the same rows. Taking it for monthly would have overstated
# inflation threefold while still looking like a plausible index.
#
# BOTH COMPARISON BASES COME FROM DICTIONARY 848, the same one CPI_YOY uses.
# The site's default segment shows period-on-period for the three-component
# basket and year-on-year for the seven-component one; the other two
# combinations are the same published dimension with the other term selected,
# and all four were fetched live and checked for plausibility before shipping.
#
# CROSS-CHECK against the separately-sourced headline series: core runs 111.4
# (ex-3) and 111.9 (ex-7) for Q2 2026, against CPI_YOY of 112.6 for October
# 2025 and the NBK-sourced ANNUAL_INFLATION of 12.2% in February 2026 falling
# to 10.2% by August. Core sitting just below headline is the expected
# relationship, since the excluded items are the volatile ones.
# ---------------------------------------------------------------------------
CORE_CPI_EX3_INDEX = "55056856"
CORE_CPI_EX7_INDEX = "55056857"
CORE_CPI_TERM_QOQ = "2695730"      # отчетный период к предыдущему периоду
CORE_CPI_TERM_YOY = "2695732"      # отчетный период к соответствующему периоду прошлого года
CORE_CPI_REGION_TERM = "741880"    # РЕСПУБЛИКА КАЗАХСТАН
CORE_CPI_EX3_BASKET = "77239135"
CORE_CPI_EX7_BASKET = "77239177"
CORE_CPI_EX3_DICS = "67,848,4791"
CORE_CPI_EX7_DICS = "67,848,4792"


def _fetch_core_cpi(index_id: str, basket_term: str, dic_ids: str, comparison_term: str,
                    indicator_id: str, note: str) -> tuple[list[dict], dict]:
    return _fetch_taldau_annual_index(
        index_id, indicator_id, note, measure_id="7",
        terms=f"{CORE_CPI_REGION_TERM},{comparison_term},{basket_term}",
        dic_ids=dic_ids, period_id=TALDAU_PERIOD_MONTHLY)


def fetch_core_cpi_yoy_ex3() -> tuple[list[dict], dict]:
    """Core CPI excluding three components, same month previous year = 100."""
    return _fetch_core_cpi(
        CORE_CPI_EX3_INDEX, CORE_CPI_EX3_BASKET, CORE_CPI_EX3_DICS, CORE_CPI_TERM_YOY,
        "CORE_CPI_YOY_EX3",
        "Index, same month of the previous year = 100. Core inflation excluding fruit and "
        "vegetables, petrol and coal -- 110.7 for August 2026, so 10.7%. MONTHLY (the Taldau "
        "query uses the monthly period; an earlier note here said quarterly, corrected "
        "2026-09-25). Sits just below the headline CPI_YOY, which is the expected relationship "
        "since the excluded items are the volatile ones.")


def fetch_core_cpi_mom_ex3() -> tuple[list[dict], dict]:
    """Core CPI excluding three components, previous month = 100."""
    return _fetch_core_cpi(
        CORE_CPI_EX3_INDEX, CORE_CPI_EX3_BASKET, CORE_CPI_EX3_DICS, CORE_CPI_TERM_QOQ,
        "CORE_CPI_MOM_EX3",
        "Index, previous month = 100 -- 100.8 for August 2026. The momentum reading of "
        "CORE_CPI_YOY_EX3: it turns before the year-on-year series does, which is the point of "
        "carrying both.")


def fetch_core_cpi_yoy_ex7() -> tuple[list[dict], dict]:
    """Core CPI excluding seven components, same month previous year = 100."""
    return _fetch_core_cpi(
        CORE_CPI_EX7_INDEX, CORE_CPI_EX7_BASKET, CORE_CPI_EX7_DICS, CORE_CPI_TERM_YOY,
        "CORE_CPI_YOY_EX7",
        "Index, same month of the previous year = 100. The NARROWER core basket: on top of "
        "fruit, vegetables, petrol and coal it also excludes regulated utilities and rail "
        "transport -- the administered prices. 111.2 for August 2026 (monthly), slightly ABOVE "
        "the three-component measure, which says the administered prices were rising more "
        "slowly than the rest of the basket.")


def fetch_core_cpi_mom_ex7() -> tuple[list[dict], dict]:
    """Core CPI excluding seven components, previous month = 100."""
    return _fetch_core_cpi(
        CORE_CPI_EX7_INDEX, CORE_CPI_EX7_BASKET, CORE_CPI_EX7_DICS, CORE_CPI_TERM_QOQ,
        "CORE_CPI_MOM_EX7",
        "Index, previous month = 100 -- 100.6 for August 2026. Momentum on the narrower core "
        "basket, the companion to CORE_CPI_YOY_EX7.")


# ---------------------------------------------------------------------------
# WAGES BY ECONOMIC ACTIVITY, from the same quarterly publication that already
# supplies AVG_WAGE_QUARTERLY -- sheet 1 carries the 'Всего' row this project
# was reading and twenty more rows below it, one per activity. Another case of
# an already-connected source not being read to the end.
#
# WHY IT MATTERS: the national average of 445,068 KZT hides a spread of nearly
# four to one. Mining and quarrying pays 1,020,632 and agriculture 268,096.
# Finance pays 941,411, education 315,100.
#
# THE REAL WAGE INDEX MATTERS MORE THAN THE LEVEL HERE, and it moves in
# opposite directions across sectors: education 93.3 and arts 93.1 against
# administrative services 111.6 and transport 104.6, with the national figure
# at 99.8. Public-sector real pay was falling while private services rose --
# the national series alone shows neither.
#
# Six activities are taken rather than all twenty-one: they span the wage
# distribution and the public/private divide, which is what the aggregate
# cannot show. The rest are available on the same sheet with the same row
# lookup if they are ever wanted.
#
# Rows are matched EXACTLY, not by prefix: 'Промышленность' is a prefix of
# nothing here, but 'Горнодобывающая промышленность и разработка карьеров' and
# 'Обрабатывающая промышленность' both end in the same word, and an exact match
# removes any question. The column layout is the same eight-value one described
# for AVG_WAGE_QUARTERLY.
# ---------------------------------------------------------------------------
WAGE_SECTOR_ROWS = {
    "MINING": "Горнодобывающая промышленность и разработка карьеров",
    "MANUFACTURING": "Обрабатывающая промышленность",
    "AGRICULTURE": "Сельское, лесное и рыбное хозяйство",
    "CONSTRUCTION": "Строительство",
    "FINANCE": "Финансовая и страховая деятельность",
    "EDUCATION": "Образование",
}
WAGE_COL_LEVEL = 3          # среднемесячная заработная плата, KZT
WAGE_COL_REAL_YOY = 7       # индекс реальной заработной платы к соответствующему кварталу


def _fetch_sector_wage(sector: str, value_index: int, indicator_id: str, note: str,
                       unit: str) -> tuple[list[dict], dict]:
    return _fetch_quarterly_publication_row(
        WAGES_PAGE_URL, "1", WAGES_SHEET_TITLE, WAGE_SECTOR_ROWS[sector],
        value_index, True, indicator_id, note, unit)


def fetch_avg_wage_mining() -> tuple[list[dict], dict]:
    """Average monthly wage in mining and quarrying, KZT, quarterly."""
    return _fetch_sector_wage(
        "MINING", WAGE_COL_LEVEL, "AVG_WAGE_MINING",
        "KZT per month. The highest-paying activity in Kazakhstan -- 1,020,632 in Q1 2026, 2.3 "
        "times the national average and 3.8 times agriculture. This is where oil sector pay sits, "
        "so it moves with commodity earnings rather than with domestic demand.", "KZT")


def fetch_avg_wage_manufacturing() -> tuple[list[dict], dict]:
    """Average monthly wage in manufacturing, KZT, quarterly."""
    return _fetch_sector_wage(
        "MANUFACTURING", WAGE_COL_LEVEL, "AVG_WAGE_MANUFACTURING",
        "KZT per month -- 508,854 in Q1 2026, half what mining pays. Read against AVG_WAGE_MINING "
        "for the pay gap between the resource and processing halves of industry, which is the "
        "same divide MANUFACTURING_OUTPUT and MINING_OUTPUT measure in volume terms.", "KZT")


def fetch_avg_wage_agriculture() -> tuple[list[dict], dict]:
    """Average monthly wage in agriculture, forestry and fishing, KZT, quarterly."""
    return _fetch_sector_wage(
        "AGRICULTURE", WAGE_COL_LEVEL, "AVG_WAGE_AGRICULTURE",
        "KZT per month -- 268,096 in Q1 2026, the LOWEST of the twenty-one activities and 60% of "
        "the national average. Agriculture employs far more people than its wage bill suggests.",
        "KZT")


def fetch_avg_wage_construction() -> tuple[list[dict], dict]:
    """Average monthly wage in construction, KZT, quarterly."""
    return _fetch_sector_wage(
        "CONSTRUCTION", WAGE_COL_LEVEL, "AVG_WAGE_CONSTRUCTION",
        "KZT per month -- 427,282 in Q1 2026, just below the national average despite construction "
        "output growing 15.3% year on year.", "KZT")


def fetch_avg_wage_finance() -> tuple[list[dict], dict]:
    """Average monthly wage in finance and insurance, KZT, quarterly."""
    return _fetch_sector_wage(
        "FINANCE", WAGE_COL_LEVEL, "AVG_WAGE_FINANCE",
        "KZT per month -- 941,411 in Q1 2026, second only to mining and more than twice the "
        "national average.", "KZT")


def fetch_avg_wage_education() -> tuple[list[dict], dict]:
    """Average monthly wage in education, KZT, quarterly."""
    return _fetch_sector_wage(
        "EDUCATION", WAGE_COL_LEVEL, "AVG_WAGE_EDUCATION",
        "KZT per month -- 315,100 in Q1 2026, 71% of the national average. Paired with "
        "REAL_WAGE_INDEX_EDUCATION, which is the sector where real pay fell fastest.", "KZT")


def fetch_real_wage_index_mining() -> tuple[list[dict], dict]:
    """Real wage index in mining, same quarter previous year = 100."""
    return _fetch_sector_wage(
        "MINING", WAGE_COL_REAL_YOY, "REAL_WAGE_INDEX_MINING",
        "Index, same quarter of the previous year = 100 -- 99.1 in Q1 2026. Real pay in the "
        "highest-paying sector was flat to falling even as the national figure held at 99.8.", "index (same quarter previous year = 100)")


def fetch_real_wage_index_manufacturing() -> tuple[list[dict], dict]:
    """Real wage index in manufacturing, same quarter previous year = 100."""
    return _fetch_sector_wage(
        "MANUFACTURING", WAGE_COL_REAL_YOY, "REAL_WAGE_INDEX_MANUFACTURING",
        "Index, same quarter of the previous year = 100 -- 103.2 in Q1 2026, one of the sectors "
        "where real pay rose.", "index (same quarter previous year = 100)")


def fetch_real_wage_index_agriculture() -> tuple[list[dict], dict]:
    """Real wage index in agriculture, same quarter previous year = 100."""
    return _fetch_sector_wage(
        "AGRICULTURE", WAGE_COL_REAL_YOY, "REAL_WAGE_INDEX_AGRICULTURE",
        "Index, same quarter of the previous year = 100 -- 107.5 in Q1 2026, the strongest real "
        "gain of the six sectors carried here, from the lowest base.", "index (same quarter previous year = 100)")


def fetch_real_wage_index_construction() -> tuple[list[dict], dict]:
    """Real wage index in construction, same quarter previous year = 100."""
    return _fetch_sector_wage(
        "CONSTRUCTION", WAGE_COL_REAL_YOY, "REAL_WAGE_INDEX_CONSTRUCTION",
        "Index, same quarter of the previous year = 100 -- 99.3 in Q1 2026. Construction volumes "
        "grew 15.3% year on year while real pay in the sector did not.", "index (same quarter previous year = 100)")


def fetch_real_wage_index_finance() -> tuple[list[dict], dict]:
    """Real wage index in finance and insurance, same quarter previous year = 100."""
    return _fetch_sector_wage(
        "FINANCE", WAGE_COL_REAL_YOY, "REAL_WAGE_INDEX_FINANCE",
        "Index, same quarter of the previous year = 100 -- 104.6 in Q1 2026.", "index (same quarter previous year = 100)")


def fetch_real_wage_index_education() -> tuple[list[dict], dict]:
    """Real wage index in education, same quarter previous year = 100."""
    return _fetch_sector_wage(
        "EDUCATION", WAGE_COL_REAL_YOY, "REAL_WAGE_INDEX_EDUCATION",
        "Index, same quarter of the previous year = 100 -- 93.3 in Q1 2026, the sharpest real "
        "decline of the six sectors carried here and 6.5 points below the national figure of 99.8. "
        "Public-sector real pay was falling while private services rose; neither is visible in the "
        "aggregate REAL_WAGE_INDEX_QUARTERLY.", "index (same quarter previous year = 100)")


# ---------------------------------------------------------------------------
# CPI MOVED FROM THE OPEN-DATA CUBE TO TALDAU, and core inflation moved from
# quarterly to monthly. Both because a staleness review asked why CPI stopped
# at October 2025.
#
# THE ANSWER WAS NOT THAT CPI HAD STOPPED. Open-data element 1549 stops at
# 202510 -- verified by downloading the 6 MB file and reading its own PERIOD
# column, so this is the source and not the fetcher. But Taldau index 703076
# carries the SAME series through 2026-07, nine months further.
#
# THE SWITCH WAS CHECKED BEFORE IT WAS MADE, not after: across all 178
# overlapping months, for all three comparison bases, the cube and Taldau agree
# to within 0.05 index points -- zero discrepancies. Same start (2011-01), same
# values, nine more months. That is a delivery channel that stopped, not a
# discontinued series, and it is the difference between repointing a series and
# replacing one.
#
# periodId=4 IS MONTHLY and periodId=5 IS QUARTERLY on Taldau. The core
# inflation series shipped earlier used periodId=5 and got 14 quarterly points;
# periodId=4 gives 42 monthly ones over the same span. That was a deficiency in
# work already shipped, found by this review rather than by a failure.
#
# CROSS-CHECK on the new data: CPI year-on-year reads 110.2 for July 2026, and
# the independently sourced NBK ANNUAL_INFLATION reads 10.2% for August 2026.
# The three comparison terms all live in dictionary 848, the same one the core
# baskets use.
# ---------------------------------------------------------------------------
CPI_TALDAU_INDEX = "703076"
CPI_TALDAU_DICS = "67,848,2753"
CPI_TALDAU_BASKET = "4772381"          # Товары и услуги
CPI_TERM_MOM = "2695730"               # отчетный период к предыдущему периоду
CPI_TERM_YTD = "2695731"               # отчетный период к декабрю прошлого года
CPI_TERM_YOY = "2695732"               # отчетный период к соответствующему периоду прошлого года
TALDAU_PERIOD_MONTHLY = "4"


def _fetch_cpi_taldau(comparison_term: str, indicator_id: str,
                      note: str) -> tuple[list[dict], dict]:
    return _fetch_taldau_annual_index(
        CPI_TALDAU_INDEX, indicator_id, note, measure_id="7",
        terms=f"{CORE_CPI_REGION_TERM},{comparison_term},{CPI_TALDAU_BASKET}",
        dic_ids=CPI_TALDAU_DICS, period_id=TALDAU_PERIOD_MONTHLY)


def fetch_cpi() -> tuple[list[dict], dict]:
    """Consumer price index, previous month = 100, monthly."""
    return _fetch_cpi_taldau(
        CPI_TERM_MOM, "CPI",
        "Index, previous month = 100 -- 100.6 for July 2026. MOVED FROM open-data element 1549 to "
        "Taldau index 703076 on 2026-09-03: the cube stops at October 2025 (confirmed by reading "
        "its own PERIOD column, so the source and not the fetcher), while Taldau carries the same "
        "series through July 2026. The two agree to within 0.05 index points across all 178 "
        "overlapping months, so this is the same series on a channel that is still updating.")


def fetch_cpi_yoy() -> tuple[list[dict], dict]:
    """Consumer price index, same month previous year = 100, monthly."""
    return _fetch_cpi_taldau(
        CPI_TERM_YOY, "CPI_YOY",
        "Index, same month of the previous year = 100 -- 110.2 for July 2026, so 10.2% headline "
        "inflation. The independently sourced NBK ANNUAL_INFLATION reads 10.2% for August 2026, "
        "which is the cross-check. Same Taldau move as CPI; see that note for the verification.")


def fetch_cpi_ytd() -> tuple[list[dict], dict]:
    """Consumer price index against December of the previous year, monthly."""
    return _fetch_cpi_taldau(
        CPI_TERM_YTD, "CPI_YTD",
        "Index, December of the previous year = 100 -- 105.7 for July 2026, cumulative inflation "
        "so far this year and the form Kazakhstan's own commentary usually quotes. Same Taldau "
        "move as CPI.")


# ---------------------------------------------------------------------------
# MODEL DATA, STEP 1 (2026-09-25): the price and activity blocks a QPM / BVAR needs.
# Every query below was found through Taldau's own endpoints -- getSearchPageGridData
# (search), GetPeriodList (period ids) and GetSegmentList (the dictionary ids and the
# default "Всего" terms of each segment) -- and checked against BNS's own releases
# before being wired in:
#   - CPI groups: December y/y for 2011-2025 equals stat.gov.kz element 1548 for food,
#     non-food and services in all 15 years (Dec 2022: headline 120.3, food 125.3,
#     non-food 119.4, services 114.1); November 2025 m/m 101.0 / 100.9 / 100.3 as in
#     «Социально-экономическое развитие».
#   - PPI: December/December 2011-2025 equals element 1626 in all 15 years (2021 146.1,
#     2022 109.4); October 2025 m/m 101.2, y/y 108.4 as in the BNS release.
#   - Industrial production: October 2025 m/m 99.4, y/y 107.1 as in the BNS release.
# Comparison terms (dictionary 848): 2695730 previous period, 2695731 December of the
# previous year, 2695732 same period of the previous year. Monthly history starts in
# 2011-01 (CPI groups, PPI) and 2014-01 (industrial production); nothing monthly exists
# earlier on Taldau or stat.gov.kz.
# ---------------------------------------------------------------------------
CPI_GROUP_TERMS = {
    "FOOD": "4772574",                  # Продовольственные товары
    "NONFOOD": "4772568",               # Непродовольственные товары
    "SERVICES": "4772555",              # Платные услуги
    "UTILITIES": "4772562",             # Жилищно-коммунальные услуги
    "REGULATED_UTILITIES": "4772564",   # Коммунальные услуги регулируемые
}
CPI_GROUP_NAMES = {
    "FOOD": "food products", "NONFOOD": "non-food products", "SERVICES": "paid services",
    "UTILITIES": "housing and utility services", "REGULATED_UTILITIES": "regulated utility services",
}


def _fetch_cpi_group(group: str, comparison_term: str, indicator_id: str) -> tuple[list[dict], dict]:
    basis = "previous month = 100" if comparison_term == CPI_TERM_MOM else "same month of the previous year = 100"
    records, manifest = _fetch_taldau_annual_index(
        CPI_TALDAU_INDEX, indicator_id,
        f"Index, {basis}: CPI for {CPI_GROUP_NAMES[group]} (Taldau index 703076, term "
        f"{CPI_GROUP_TERMS[group]}), monthly from 2011-01, national. Same index and dictionaries "
        "as the headline CPI; December year-on-year values equal BNS element 1548 for 2011-2025.",
        measure_id="7", terms=f"{NATIONAL_TERM_ID},{comparison_term},{CPI_GROUP_TERMS[group]}",
        dic_ids=CPI_TALDAU_DICS, period_id=TALDAU_PERIOD_MONTHLY)
    return records, manifest


def fetch_cpi_food() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("FOOD", CPI_TERM_MOM, "CPI_FOOD")


def fetch_cpi_food_yoy() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("FOOD", CPI_TERM_YOY, "CPI_FOOD_YOY")


def fetch_cpi_nonfood() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("NONFOOD", CPI_TERM_MOM, "CPI_NONFOOD")


def fetch_cpi_nonfood_yoy() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("NONFOOD", CPI_TERM_YOY, "CPI_NONFOOD_YOY")


def fetch_cpi_services() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("SERVICES", CPI_TERM_MOM, "CPI_SERVICES")


def fetch_cpi_services_yoy() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("SERVICES", CPI_TERM_YOY, "CPI_SERVICES_YOY")


def fetch_cpi_utilities() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("UTILITIES", CPI_TERM_MOM, "CPI_UTILITIES")


def fetch_cpi_utilities_yoy() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("UTILITIES", CPI_TERM_YOY, "CPI_UTILITIES_YOY")


def fetch_cpi_regulated_utilities() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("REGULATED_UTILITIES", CPI_TERM_MOM, "CPI_REGULATED_UTILITIES")


def fetch_cpi_regulated_utilities_yoy() -> tuple[list[dict], dict]:
    return _fetch_cpi_group("REGULATED_UTILITIES", CPI_TERM_YOY, "CPI_REGULATED_UTILITIES_YOY")


PPI_MONTHLY_INDEX = "703039"
PPI_MONTHLY_DICS = "67,848,2513,2854,3068"
PPI_MONTHLY_TOTAL_TERMS = "4150464,15698719,18716910"   # the "Всего" of the three product/activity dictionaries


def _fetch_ppi_monthly(comparison_term: str, indicator_id: str, basis: str) -> tuple[list[dict], dict]:
    return _fetch_taldau_annual_index(
        PPI_MONTHLY_INDEX, indicator_id,
        f"Index, {basis}: producer prices of industrial products, national, monthly from 2011-01 "
        "(Taldau index 703039). December/December values equal BNS element 1626 for 2011-2025. "
        "The annual PPI series is a different figure -- the January-December average.",
        measure_id="7", terms=f"{NATIONAL_TERM_ID},{comparison_term},{PPI_MONTHLY_TOTAL_TERMS}",
        dic_ids=PPI_MONTHLY_DICS, period_id=TALDAU_PERIOD_MONTHLY)


def fetch_ppi_monthly() -> tuple[list[dict], dict]:
    return _fetch_ppi_monthly(CPI_TERM_MOM, "PPI_MONTHLY", "previous month = 100")


def fetch_ppi_yoy_monthly() -> tuple[list[dict], dict]:
    return _fetch_ppi_monthly(CPI_TERM_YOY, "PPI_YOY_MONTHLY", "same month of the previous year = 100")


IND_PROD_MONTHLY_INDEX = "701625"
IND_PROD_MONTHLY_DICS = "68,4303,848"      # region, activity, comparison -- the comparison comes LAST here
IND_PROD_MONTHLY_TOTAL = "3079117"         # Промышленность, всего


def _fetch_ind_prod_monthly(comparison_term: str, indicator_id: str, basis: str) -> tuple[list[dict], dict]:
    return _fetch_taldau_annual_index(
        IND_PROD_MONTHLY_INDEX, indicator_id,
        f"Index, {basis}: industrial production, national, monthly from 2014-01 (Taldau index 701625). "
        "Not seasonally adjusted -- the month-on-month index swings with the calendar (January 2026 "
        "78.5, February 124.5).",
        measure_id="7", terms=f"{NATIONAL_TERM_ID},{IND_PROD_MONTHLY_TOTAL},{comparison_term}",
        dic_ids=IND_PROD_MONTHLY_DICS, period_id=TALDAU_PERIOD_MONTHLY)


def fetch_ind_prod_monthly_yoy() -> tuple[list[dict], dict]:
    return _fetch_ind_prod_monthly(CPI_TERM_YOY, "IND_PROD_MONTHLY_YOY", "same month of the previous year = 100")


def fetch_ind_prod_monthly_mom() -> tuple[list[dict], dict]:
    return _fetch_ind_prod_monthly(CPI_TERM_MOM, "IND_PROD_MONTHLY_MOM", "previous month = 100")


# ---------------------------------------------------------------------------
# LABOUR HISTORY from two stat.gov.kz dynamic tables (2026-09-25).
# «Основные индикаторы рынка труда» (element 5830, sheet «ОИРТ»): one block per
# indicator, each with a year row, a quarter row (I-IV квартал, год) and the
# «Республика Казахстан» row -- unemployment 15+ quarterly from 2001Q1 (12.7) with no
# gap, where the JSON cube the pipeline used before covers only 2023Q1-2025Q2.
# «Среднемесячная заработная плата» (element 5674, sheet «Показатель», form 1-Т):
# quarterly pairs of rows (labels, then values) from 2015. It is NOT the same figure as
# AVG_WAGE_QUARTERLY (445 068 KZT in 2026Q1 with small enterprises; 461 486 here), so it
# goes out as its own series.
# ---------------------------------------------------------------------------
LABOUR_INDICATORS_ELEMENT = 5830
WAGE_1T_ELEMENT = 5674
QUARTER_LABELS = {"I": 1, "II": 2, "III": 3, "IV": 4}
FOOTNOTED_YEAR_RE = re.compile(r"^\s*((?:19|20)\d{2})(?=\D|$|\d\))")


def parse_labour_indicator_block(content: bytes, block_label: str) -> list[dict]:
    """Quarter-end records of the national row of one «ОИРТ» block."""
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows = [list(r) for r in wb["ОИРТ"].iter_rows(values_only=True)]
    start = next((i for i, r in enumerate(rows) if r and isinstance(r[0], str)
                  and r[0].strip().lower() == block_label.lower()), None)
    if start is None:
        raise validation.StructuralChangeError(f"no block {block_label!r} in sheet «ОИРТ»")
    year_i = next(i for i in range(start, start + 6) if any(isinstance(c, int) and 1990 < c < 2100 for c in rows[i]))
    years, quarters = rows[year_i], rows[year_i + 1]
    national = next(r for r in rows[year_i + 2:year_i + 6] if r and isinstance(r[0], str)
                    and r[0].strip() == "Республика Казахстан")
    records, year = [], None
    for col, label in enumerate(quarters):
        # A year cell may carry a footnote digit: 2014 is headed '20142)' (footnote 2).
        m_year = FOOTNOTED_YEAR_RE.match(str(years[col])) if years[col] is not None else None
        if m_year:
            year = int(m_year.group(1))
        m = re.match(r"^\s*(I{1,3}|IV)\s+квартал", str(label or ""))
        if not m or year is None or col >= len(national):
            continue
        value = national[col]
        if isinstance(value, (int, float)):
            q_end = QUARTER_LABELS[m.group(1)] * 3
            records.append({"date": f"{year:04d}-{q_end:02d}-{calendar.monthrange(year, q_end)[1]:02d}",
                            "value": round(float(value), 4)})
    return records


def fetch_unemployment() -> tuple[list[dict], dict]:
    """Unemployment rate (ILO, 15 and older), national, quarterly from 2001Q1."""
    url = f"https://stat.gov.kz/api/iblock/element/{LABOUR_INDICATORS_ELEMENT}/file/ru/"
    content = _download(url)
    _save_raw("UNEMPLOYMENT", content, "xlsx", {"source_url": url, "element_id": LABOUR_INDICATORS_ELEMENT})
    records = parse_labour_indicator_block(content, "Уровень безработицы")
    if len(records) < 90:
        raise validation.StructuralChangeError(
            f"bns/UNEMPLOYMENT: only {len(records)} quarters parsed from element {LABOUR_INDICATORS_ELEMENT}; expected 2001Q1 onward")
    manifest = {"frequency": "quarterly", "source_url": url, "dataset_id": str(LABOUR_INDICATORS_ELEMENT),
                "note": "Percent of the labour force, ILO definition, age 15+, national, quarterly from 2001Q1 "
                        "(stat.gov.kz element 5830 «Основные индикаторы рынка труда», block «Уровень "
                        "безработицы»). Replaced the JSON cube 102790 on 2026-09-25, which stopped at 2025Q2 "
                        "and began in 2023Q1; the two agree on every shared quarter."}
    return records, manifest


def parse_wage_1t_quarterly(content: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows = [list(r) for r in wb["Показатель"].iter_rows(values_only=True)]
    records = []
    for i, r in enumerate(rows[:-1]):
        if not (r and isinstance(r[0], int) and any(isinstance(c, str) and "квартал" in c for c in r[1:])):
            continue
        year, values = r[0], rows[i + 1]
        for col, label in enumerate(r[1:], start=1):
            m = re.match(r"^\s*([1-4])\s+квартал", str(label or ""))
            if m and col < len(values) and isinstance(values[col], (int, float)):
                q_end = int(m.group(1)) * 3
                records.append({"date": f"{year:04d}-{q_end:02d}-{calendar.monthrange(year, q_end)[1]:02d}",
                                "value": float(values[col])})
    return records


def fetch_avg_wage_1t_quarterly() -> tuple[list[dict], dict]:
    """Average monthly nominal wage, form 1-Т, KZT, quarterly from 2015Q1."""
    url = f"https://stat.gov.kz/api/iblock/element/{WAGE_1T_ELEMENT}/file/ru/"
    content = _download(url)
    _save_raw("AVG_WAGE_1T_QUARTERLY", content, "xlsx", {"source_url": url, "element_id": WAGE_1T_ELEMENT})
    records = parse_wage_1t_quarterly(content)
    if len(records) < 40:
        raise validation.StructuralChangeError(
            f"bns/AVG_WAGE_1T_QUARTERLY: only {len(records)} quarters parsed from element {WAGE_1T_ELEMENT}")
    manifest = {"frequency": "quarterly", "source_url": url, "dataset_id": str(WAGE_1T_ELEMENT),
                "note": "KZT per month, statistical form 1-Т «Отчет по труду», national, quarterly from 2015Q1 "
                        "(118 638 KZT) -- stat.gov.kz element 5674, equal to Taldau index 702972. A different "
                        "coverage from AVG_WAGE_QUARTERLY (461 486 here against 445 068 there for 2026Q1)."}
    return records, manifest


# ---------------------------------------------------------------- fixed assets and hours worked
# Added 2026-09-25 for the production function behind potential output and the output gap.
# Taldau, form 11 «Отчет о состоянии основных фондов» (all enterprises), national, annual
# 2000-2025, published in tenge and converted here to billion KZT. The asset dimension
# (dictionary 77) is set to term 455728 «Основные средства» -- TANGIBLE fixed assets. The
# page's default term 741881 «Всего» adds intangibles (2025: 222.8 against 216.9 trn KZT).
# Checked: the 2025 gross and net stock equal BNS's «Основные фонды РК (2025)» (element
# 347772) to the tenge, and wear = 1 - net/gross in every year. These are HISTORICAL-COST
# BOOK VALUES that include revaluations (2024: +22.5 %) -- not a real perpetual-inventory
# stock; deflate, or build K from GFCF and its volume index, before using them as K.
FIXED_ASSETS_DICS = "68,915,90,77,1161"
FIXED_ASSETS_TERMS = "741880,741885,741927,455728,741908"
FIXED_ASSETS_RATIO_DICS = "68,915,90,77"
FIXED_ASSETS_RATIO_TERMS = "741880,741885,741927,455728"
FIXED_ASSETS_INDEX = {
    "FIXED_ASSETS_GROSS": ("703214", "gross stock (original cost) at the end of the year"),
    "FIXED_ASSETS_GROSS_START": ("703203", "gross stock (original cost) at the start of the year"),
    "FIXED_ASSETS_NET": ("703215", "net stock (book value, gross less accumulated depreciation) at the end of the year"),
    "FIXED_ASSETS_COMMISSIONED": ("703205", "new fixed assets put into operation during the year"),
    "FIXED_ASSETS_DEPRECIATION": ("703220", "depreciation charged during the year"),
}
FIXED_ASSETS_RATIO_INDEX = {
    "FIXED_ASSETS_WEAR": ("703216", "degree of wear, % (accumulated depreciation / gross stock)"),
    "FIXED_ASSETS_RENEWAL": ("703217", "renewal ratio, % (new assets put into operation / gross stock at the end of the year)"),
}
FIXED_ASSETS_NOTE = ("Tangible fixed assets («Основные средства», Taldau term 455728, intangibles excluded) of all "
                     "enterprises, form 11, national, from 2000. Historical-cost book values incl. revaluations -- "
                     "not a volume measure.")


def _fixed_assets(indicator_id: str) -> tuple[list[dict], dict]:
    if indicator_id in FIXED_ASSETS_INDEX:
        index_id, what = FIXED_ASSETS_INDEX[indicator_id]
        records, manifest = _fetch_taldau_annual_index(
            index_id, indicator_id, note=f"Billion KZT, {what}. " + FIXED_ASSETS_NOTE + f" Taldau {index_id}.",
            measure_id="1", terms=FIXED_ASSETS_TERMS, dic_ids=FIXED_ASSETS_DICS)
        records = [{**r, "value": round(r["value"] / 1e9, 6)} for r in records]
    else:
        index_id, what = FIXED_ASSETS_RATIO_INDEX[indicator_id]
        records, manifest = _fetch_taldau_annual_index(
            index_id, indicator_id, note=f"Percent, {what}. " + FIXED_ASSETS_NOTE + f" Taldau {index_id}.",
            measure_id="7", terms=FIXED_ASSETS_RATIO_TERMS, dic_ids=FIXED_ASSETS_RATIO_DICS)
    if len(records) < 20:
        raise validation.StructuralChangeError(
            f"bns/{indicator_id}: only {len(records)} years from Taldau {index_id}; expected 2000 onward")
    return records, manifest


def fetch_fixed_assets_gross() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_GROSS")


def fetch_fixed_assets_gross_start() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_GROSS_START")


def fetch_fixed_assets_net() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_NET")


def fetch_fixed_assets_commissioned() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_COMMISSIONED")


def fetch_fixed_assets_depreciation() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_DEPRECIATION")


def fetch_fixed_assets_wear() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_WEAR")


def fetch_fixed_assets_renewal() -> tuple[list[dict], dict]:
    return _fixed_assets("FIXED_ASSETS_RENEWAL")


# Hours actually worked by employees (enterprise survey, Taldau 703017, man-hours; 703018,
# minutes per employee). The annual series sits on two Taldau segments that do not overlap:
# regions x ... (dictionaries 67,1212,2813,576) gives 2000-2012 and 2017 onward, the
# section segment (68,859,2813) only 2013-2016. They are NOT spliced: their coverage
# differs -- the section segment and the quarterly series (period 5, from 2016-Q1, on the
# same section segment) agree with each other (2016: 6 260 annual against 6 297 summed
# over quarters, million man-hours), the regional segment runs about 8 % higher (2017:
# 6 848 against 6 353). A splice would put a false +9 % "growth" into 2017. So HOURS_WORKED
# is the regional segment with 2013-2016 missing, and HOURS_WORKED_QUARTERLY is the
# consistent series from 2016.
HOURS_REGIONAL_SEGMENT = ("67,1212,2813,576", "741880,741885,3629946,741935")
HOURS_SECTION_SEGMENT = ("68,859,2813", "741880,741885,3629946")


def fetch_hours_worked() -> tuple[list[dict], dict]:
    records, manifest = _fetch_taldau_annual_index(
        "703017", "HOURS_WORKED", measure_id="112", terms=HOURS_REGIONAL_SEGMENT[1], dic_ids=HOURS_REGIONAL_SEGMENT[0],
        note="Million man-hours actually worked by employees in the year (enterprise survey, Taldau 703017, "
             "regional segment), national, 2000-2012 and 2017 onward. 2013-2016 exist only on a segment with "
             "about 8 % lower coverage and are deliberately not spliced in; use HOURS_WORKED_QUARTERLY from 2016.")
    records = [{**r, "value": round(r["value"] / 1e6, 6)} for r in records]
    if len(records) < 20:
        raise validation.StructuralChangeError(f"bns/HOURS_WORKED: only {len(records)} years; expected 2000 onward")
    return records, manifest


def fetch_hours_worked_quarterly() -> tuple[list[dict], dict]:
    records, manifest = _fetch_taldau_annual_index(
        "703017", "HOURS_WORKED_QUARTERLY", measure_id="112", terms=HOURS_SECTION_SEGMENT[1],
        dic_ids=HOURS_SECTION_SEGMENT[0], period_id="5",
        note="Million man-hours actually worked by employees in the quarter (Taldau 703017, quarterly), national, "
             "from 2016-Q1, not seasonally adjusted. The quarters do not sum to HOURS_WORKED (different coverage).")
    return [{**r, "value": round(r["value"] / 1e6, 6)} for r in records], manifest


def fetch_hours_per_employee() -> tuple[list[dict], dict]:
    records, manifest = _fetch_taldau_annual_index(
        "703018", "HOURS_PER_EMPLOYEE", measure_id="35", terms=HOURS_SECTION_SEGMENT[1], dic_ids=HOURS_SECTION_SEGMENT[0],
        note="Hours actually worked per employee in the year (Taldau 703018, published in minutes, converted "
             "to hours), national, from 2013.")
    return [{**r, "value": round(r["value"] / 60, 3)} for r in records], manifest


# ---------------------------------------------------------------- annual inequality (added 2026-09-25)
def fetch_gini_coefficient_annual() -> tuple[list[dict], dict]:
    from fetchers import bns_living
    return bns_living.poverty_series(
        "GINI_COEFFICIENT_ANNUAL", "gini10", "annual", "704502",
        "Gini coefficient of money income over decile groups, annual, from 2001 (Taldau 704502; from 2022 "
        "the annual editions of «Основные показатели дифференциации доходов», which equal Taldau). 0.291 in 2025.")


def fetch_decile_income_ratio_annual() -> tuple[list[dict], dict]:
    from fetchers import bns_living
    return bns_living.poverty_series(
        "DECILE_INCOME_RATIO_ANNUAL", "ratio", "annual", "704504",
        "Income of the richest 10% over the poorest 10% (коэффициент фондов), annual: Taldau 704504 for "
        "2011-2021, the annual editions from 2022. 5.98 in 2025.")
