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


def fetch_population_bns() -> tuple[list[dict], dict]:
    """Average annual population, persons. Taldau indexId 703834 (code 611104,
    "Среднегодовая численность населения"), found under Taldau's demographic
    statistics via keyword search ("численность населения") -- picked over
    the "at start of period" variant (703831) as the more standard annual
    figure. Classified across 4 dictionaries; params recovered via the live
    ExtJS component tree, same technique as RETAIL_TRADE/CONSTRUCTION.
    Verified live 2026-08-30 and cross-checked: 2025 value (20,391,610.5)
    matches the already-confirmed IMF_POPULATION series (2025: 20,380,366) to
    within 0.06% -- strong independent confirmation, two different agencies'
    figures agreeing almost exactly.
    """
    return _fetch_taldau_annual_index(
        "703834", "POPULATION_BNS",
        note="Average annual population, persons. Taldau indexId 703834.",
        measure_id="23", dic_ids="67,749,576,1433",
        terms="741880,741917,741935,3699122",
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


def fetch_employed_total() -> tuple[list[dict], dict]:
    """Total employed population, persons. Taldau indexId 702840 (code 251201,
    "Занятое население") -- companion to UNEMPLOYMENT (a rate, not a count).
    Found via keyword search ("занятое население"), picked over the many
    narrower breakdowns (by sector, by additional-work status, etc.) returned
    by the same search as the clean headline total. Classified across 6
    dictionaries; params recovered via the live ExtJS component tree.
    Verified live 2026-08-30: ~9.3 million (2025), a plausible employed-
    population figure for Kazakhstan given its ~20.4 million total population.
    """
    return _fetch_taldau_annual_index(
        "702840", "EMPLOYED_TOTAL",
        note="Total employed population, persons. Taldau indexId 702840.",
        measure_id="23", dic_ids="67,749,576,1773,1793,3028",
        terms="741880,741917,741935,3805694,4197331,741885",
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


def fetch_electricity_production() -> tuple[list[dict], dict]:
    """Electricity production, kWh, annual. Taldau indexId 19197226 (code
    304132, "Производство электроэнергии в натуральном выражении"), found
    via keyword search ("производство электроэнергии") after the energy
    category page itself didn't list it among its two RK-total indicators.
    Standard single-dimension mechanism worked directly. Verified live
    2026-08-30: ~113.6 billion kWh (2022) to ~118.7 billion kWh (2024), a
    plausible scale matching Kazakhstan's known annual generation.
    """
    return _fetch_taldau_annual_index(
        "19197226", "ELECTRICITY_PRODUCTION",
        note="Electricity production, kWh. Taldau indexId 19197226.",
    )


def _fetch_ind_prod_sub_sector(industry_name: str, indicator_id: str) -> tuple[list[dict], dict]:
    """Shared fetcher for industrial-production sub-sector indices -- the SAME
    stat.gov.kz open-data file (element_id=5809) used by fetch_ind_prod for the
    whole-industry aggregate ('Промышленность') turns out to also carry sub-
    sector cube slices for the same region/comparison_type, discovered by
    enumerating every distinct `industry` (termNames[1]) value in the file
    rather than searching for a separate indicator. This resolves the mining/
    manufacturing/electricity sub-sector gap noted in earlier sessions as "not
    found" -- it was never a separate indicator to find, just an unexplored
    dimension of one already-connected file.
    """
    element_id = 5809
    url = f"https://stat.gov.kz/api/iblock/element/{element_id}/json/file/ru/"
    content = _download(url)
    _save_raw(indicator_id, content, "json", {"source_url": url, "element_id": element_id})

    import json
    data = json.loads(content)

    TARGET = ["РЕСПУБЛИКА КАЗАХСТАН", industry_name, "отчетный период к предыдущему периоду"]
    match = next((entry for entry in data if entry.get("termNames") == TARGET), None)
    if match is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in bns/{indicator_id}",
                "WHAT CHANGED: no cube slice matched the expected national/sub-sector combo",
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
        "note": f"Sub-sector ({industry_name!r}) slice of the same file used by IND_PROD. "
                "Physical volume index, % of prior period.",
    }
    return records, manifest


def fetch_ind_prod_mining() -> tuple[list[dict], dict]:
    """Industrial production index, mining and quarrying sub-sector, % of
    prior period, annual. Same source file as IND_PROD (element_id=5809),
    industry='Горнодобывающая промышленность и разработка карьеров'.
    Verified live 2026-08-30: 15 periods (2009-2023), values ~99-106% range,
    consistent with the whole-industry aggregate's own range."""
    return _fetch_ind_prod_sub_sector("Горнодобывающая промышленность и разработка карьеров", "IND_PROD_MINING")


def fetch_ind_prod_manufacturing() -> tuple[list[dict], dict]:
    """Industrial production index, manufacturing sub-sector, % of prior
    period, annual. Same source file as IND_PROD (element_id=5809),
    industry='Обрабатывающая промышленность'. Verified live 2026-08-30: 15
    periods (2009-2023), values ~100-105% range."""
    return _fetch_ind_prod_sub_sector("Обрабатывающая промышленность", "IND_PROD_MANUFACTURING")


def fetch_ind_prod_electricity() -> tuple[list[dict], dict]:
    """Industrial production index, electricity/gas/steam/air-conditioning
    supply sub-sector, % of prior period, annual. Same source file as
    IND_PROD (element_id=5809), industry='Снабжение электроэнергией, газом,
    паром, горячей водой и кондиционированным воздухом'. Verified live
    2026-08-30: 15 periods (2009-2023), values ~100-106% range."""
    return _fetch_ind_prod_sub_sector(
        "Снабжение электроэнергией, газом, паром, горячей водой и кондиционированным воздухом",
        "IND_PROD_ELECTRICITY",
    )


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
