"""Bureau of National Statistics (stat.gov.kz) fetcher.

Confirmed live 2026-08-30 (see config/sources.yaml -> agencies.bns). Download
pattern: GET https://stat.gov.kz/api/iblock/element/{elementId}/{json|csv}/file/ru/
-> 302 redirect -> static file, no auth/CAPTCHA. Field layout for each indicator
below was determined by actually downloading and inspecting the live file this
session (not guessed) -- see the per-function docstring for what was verified.
"""
from __future__ import annotations

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


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    return resp.content


def _save_raw(indicator_id: str, content: bytes, ext: str, extra_manifest: dict) -> None:
    today = date.today()
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        **extra_manifest,
    })


def _dd_mm_yyyy_to_iso(s: str) -> str:
    return datetime.strptime(s, "%d.%m.%Y").date().isoformat()


def fetch_cpi() -> tuple[list[dict], dict]:
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


def fetch_unemployment() -> tuple[list[dict], dict]:
    """Unemployment rate, national, both sexes, all localities, all ages, all education levels.

    Verified live 2026-08-30: file is a JSON list of "cube slices", each with its own
    terms/termNames/periods (NOT a single terms/periods object). Dimension order is
    [region, locality, sex, education, age_group]. Confirmed the fully-aggregated
    national row exists with termNames == ['РЕСПУБЛИКА КАЗАХСТАН', 'Всего', 'Всего',
    'Всего', 'Всего']. periods[].date is DD.MM.YYYY, .value is the unemployment rate (%).
    """
    element_id = 102790
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw("UNEMPLOYMENT", content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    TARGET = ["РЕСПУБЛИКА КАЗАХСТАН", "Всего", "Всего", "Всего", "Всего"]
    match = next((entry for entry in data if entry.get("termNames") == TARGET), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/UNEMPLOYMENT",
                "WHAT CHANGED: no cube slice matched the expected fully-aggregated national combo",
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
    manifest = {"frequency": "quarterly", "source_url": url, "dataset_id": str(element_id)}
    return records, manifest


def fetch_gdp_nominal() -> tuple[list[dict], dict]:
    """Nominal GDP, national, production method -- published as YEAR-TO-DATE
    CUMULATIVE totals at each quarter-end (Jan-Mar, Jan-Jun, Jan-Sep, Jan-Dec), not
    as discrete quarterly increments. We store it exactly as published (cumulative);
    turning it into non-cumulative quarterly GDP would require a decumulation
    transformation not yet implemented -- flagged in metadata rather than silently done.

    Verified live 2026-08-30: file is a JSON list of 22 per-region cube slices, each
    with a single-element termNames (just the region name). Confirmed a
    ['РЕСПУБЛИКА КАЗАХСТАН'] entry exists with 66 periods. Values are in KZT (whole tenge).
    """
    element_id = 4439
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw("GDP_NOMINAL", content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    match = next((entry for entry in data if entry.get("termNames") == ["РЕСПУБЛИКА КАЗАХСТАН"]), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/GDP_NOMINAL",
                "WHAT CHANGED: no cube slice matched the expected national-total combo",
                "EXPECTED termNames: ['РЕСПУБЛИКА КАЗАХСТАН']",
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
        "frequency": "quarterly",
        "source_url": url,
        "dataset_id": str(element_id),
        "transformation": "level (year-to-date cumulative, as published -- not decumulated to discrete quarters)",
    }
    return records, manifest


def fetch_ind_prod() -> tuple[list[dict], dict]:
    """Industrial production index, national, whole-industry aggregate, annual.

    Verified live 2026-08-30: SAME list-of-cube-slices JSON format as GDP_NOMINAL/
    UNEMPLOYMENT (terms/termNames/periods per entry) -- not a merged-cell pivot
    table. 3 dimensions: [region, industry/activity, comparison_type]. The
    comparison_type dimension has exactly one value in this file
    ('отчетный период к предыдущему периоду'), and all periods are ANNUAL only
    (2009-2023) -- there is no monthly granularity in this particular file,
    correcting our earlier unverified guess that it might contain monthly points.
    Filtered to region='РЕСПУБЛИКА КАЗАХСТАН', industry='Промышленность' (the
    whole-industry aggregate, as opposed to sub-sectors like manufacturing).
    """
    element_id = 5809
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw("IND_PROD", content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    TARGET = ["РЕСПУБЛИКА КАЗАХСТАН", "Промышленность", "отчетный период к предыдущему периоду"]
    match = next((entry for entry in data if entry.get("termNames") == TARGET), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/IND_PROD",
                "WHAT CHANGED: no cube slice matched the expected national/whole-industry combo",
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
        "note": "file contains only annual points, not monthly, despite the indicator being conceptually a monthly release",
    }
    return records, manifest


def fetch_investment() -> tuple[list[dict], dict]:
    """Investment in fixed capital, national, all enterprise sizes/localities, total, annual.

    Verified live 2026-08-30: SAME list-of-cube-slices JSON format again. 4
    dimensions: [region, locality, enterprise_size, cost_type]. Filtered to
    region='РЕСПУБЛИКА КАЗАХСТАН', locality='Всего', enterprise_size='Всего',
    cost_type='Всего' (the fully-aggregated national total).

    IMPORTANT caveat found this session: there are TWO cube entries with this
    exact same termNames combo -- one covering 2016-2018, another covering
    2019-2022, with no overlapping years. This looks like a classification/
    methodology break (BNS re-published under what appears to be a revised
    structure starting 2019) rather than a data error. We concatenate both
    since their periods don't overlap, but flag it in the manifest note rather
    than silently presenting it as one continuous, unbroken methodology. Also
    note: this file's actual coverage (2016-2022) is narrower than the
    "2003-2025" range advertised on the human-facing page -- that longer
    history may live in a different, not-yet-identified file.
    """
    element_id = 5546
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw("INVESTMENT", content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    TARGET = ["РЕСПУБЛИКА КАЗАХСТАН", "Всего", "Всего", "Всего"]
    matches = [entry for entry in data if entry.get("termNames") == TARGET]
    if not matches:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/INVESTMENT",
                "WHAT CHANGED: no cube slice matched the expected fully-aggregated national combo",
                f"EXPECTED termNames: {TARGET}",
                "ACTUAL: no matching entry in the downloaded file",
                f"ACTION REQUIRED: inspect {url} and update scripts/fetchers/bns.py",
            ])
        )

    records = []
    for match in matches:
        for p in match["periods"]:
            try:
                records.append({"date": _dd_mm_yyyy_to_iso(p["date"]), "value": float(p["value"])})
            except (ValueError, KeyError):
                continue
    records.sort(key=lambda r: r["date"])

    dates = [r["date"] for r in records]
    if len(dates) != len(set(dates)):
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in bns/INVESTMENT",
                "WHAT CHANGED: multiple cube slices for the national total now overlap on the same date(s)",
                "EXPECTED: the known methodology-break slices (2016-2018 / 2019-2022) to cover disjoint years",
                f"ACTUAL: duplicate dates found across {len(matches)} matching slices",
                "ACTION REQUIRED: inspect the raw file and decide how to reconcile overlapping values "
                "before trusting this series -- do not silently pick one.",
            ])
        )

    manifest = {
        "frequency": "annual",
        "source_url": url,
        "dataset_id": str(element_id),
        "note": (
            f"{len(matches)} cube slices concatenated for the national total (methodology break "
            "observed between them, exact years found: " + ", ".join(sorted({r['date'][:4] for r in records})) +
            "). Coverage is narrower than the 2003-2025 advertised on the source page -- "
            "the older history was not located in this file."
        ),
    }
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


def fetch_exports() -> tuple[list[dict], dict]:
    """Exports, national total, monthly, thousand USD. XLSX-only (no CSV/JSON
    variant found for trade indicators). See _parse_trade_workbook docstring
    for the structure this relies on.
    """
    element_id = 446905
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/file/ru/"
    content = _download(url)
    _save_raw("EXPORTS", content, "xlsx", {"source_url": url, "element_id": element_id})
    records = _parse_trade_workbook(content, "EXPORTS", url)
    manifest = {"frequency": "monthly", "source_url": url, "dataset_id": str(element_id)}
    return records, manifest


def fetch_imports() -> tuple[list[dict], dict]:
    """Imports, national total, monthly, thousand USD. Same format as fetch_exports."""
    element_id = 446906
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/file/ru/"
    content = _download(url)
    _save_raw("IMPORTS", content, "xlsx", {"source_url": url, "element_id": element_id})
    records = _parse_trade_workbook(content, "IMPORTS", url)
    manifest = {"frequency": "monthly", "source_url": url, "dataset_id": str(element_id)}
    return records, manifest


TALDAU_TREE_DATA_URL = "https://taldau.stat.gov.kz/ru/NewIndex/GetIndexTreeData"
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
                                dic_ids: str = REGIONS_DIC_ID) -> tuple[list[dict], dict]:
    """Shared fetcher for any Taldau "NewIndex" indicator following the pattern
    discovered for GDP_REAL: national annual series, root term id 741880. See
    fetch_gdp_real's docstring for how this mechanism was cracked. Each new
    index_id used here was verified live this session (real HTTP 200, at least
    one parsed year) before being wired into update_bns.py -- not assumed to
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
    """
    body = {
        "p_parent_id": "", "p_index_id": index_id, "p_keyword": "",
        "p_period_id": "7", "p_measure_id": measure_id, "p_term_id": NATIONAL_TERM_ID,
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
        if not (isinstance(key, str) and key.startswith("y") and key[1:].isdigit()):
            continue
        year_str = key[-4:]
        try:
            year = int(year_str)
            v = float(value)
        except (TypeError, ValueError):
            continue
        records.append({"date": f"{year:04d}-12-31", "value": v})

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
        "frequency": "annual",
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
