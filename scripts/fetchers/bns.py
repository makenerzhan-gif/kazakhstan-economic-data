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
import sys
from datetime import date, datetime
from pathlib import Path

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
