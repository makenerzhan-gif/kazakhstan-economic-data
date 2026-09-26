"""Ministry of Finance RK fetcher.

Confirmed live 2026-08-30 (see config/sources.yaml -> agencies.minfin). Minfin
content is served through the gov.kz unified platform's public content-manager
API, not a dedicated minfin.gov.kz API -- no auth/CAPTCHA, plain requests work.

Both GOV_REVENUE/GOV_EXPENDITURE and GOV_DEBT are discovered dynamically from
the listing API each run (searching for a stable title substring) rather than
hardcoding today's specific document URL -- so a future run picks up whatever
document Minfin publishes next without code changes.
"""
from __future__ import annotations

import calendar
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import requests
import xlrd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
SOURCE = "minfin"
LISTING_URL = "https://www.gov.kz/api/v1/public/content-manager/documents"
GOV_KZ_BASE = "https://www.gov.kz"


_LISTING_CACHE: dict[tuple, list[dict]] = {}


def _list_documents(**params) -> list[dict]:
    """The document listing, once per process per parameter set: 77 indicators ask for the
    same budget-direction listing, and from the CI runner every gov.kz round trip is slow."""
    key = tuple(sorted(params.items()))
    if key not in _LISTING_CACHE:
        resp = requests.get(LISTING_URL, headers=HEADERS,
                             params={"sort-by": "created_date:DESC", "page": "1", "size": "100", **params},
                             timeout=30)
        resp.raise_for_status()
        _LISTING_CACHE[key] = resp.json()
    return _LISTING_CACHE[key]


_DOWNLOAD_CACHE: dict[str, bytes] = {}


def _download(path: str) -> bytes:
    """GET once per process: the same document listing and the same bulletin serve
    many indicators."""
    url = path if path.startswith("http") else GOV_KZ_BASE + path
    if url not in _DOWNLOAD_CACHE:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        _DOWNLOAD_CACHE[url] = resp.content
    return _DOWNLOAD_CACHE[url]


def _open_workbook(content: bytes, filename_hint: str):
    """Returns (kind, workbook) where kind is 'openpyxl' or 'xlrd' -- Minfin
    serves both modern .xlsx and legacy .xls across its document history.
    """
    if filename_hint.lower().endswith(".xls"):
        return "xlrd", xlrd.open_workbook(file_contents=content)
    return "openpyxl", openpyxl.load_workbook(io.BytesIO(content), data_only=True)


def _iter_rows(kind: str, wb, sheet_name: str | None = None):
    if kind == "xlrd":
        ws = wb.sheet_by_index(0) if sheet_name is None else wb.sheet_by_name(sheet_name)
        for r in range(ws.nrows):
            yield [ws.cell_value(r, c) for c in range(ws.ncols)]
    else:
        ws = wb[wb.sheetnames[0]] if sheet_name is None else wb[sheet_name]
        for row in ws.iter_rows(values_only=True):
            yield list(row)


# ---------------------------------------------------------------------------
# GOV_REVENUE / GOV_EXPENDITURE: "Dynamics of execution of the republican
# budget" -- a small, purpose-built annual time-series file (verified live
# 2026-08-30 by download: 97KB, sheets ['Metadata', 'Dynamics 2014-2025']).
# Preferred over pulling a row out of the monthly Statistical Bulletin (which
# is a 50-sheet workbook where the target sheet name/index can shift between
# editions) -- this file is smaller, purpose-built, and its row labels
# ('I. INCOME', 'II.Expences') are stable section headers, not deep in a
# product/classification hierarchy.
# ---------------------------------------------------------------------------
BUDGET_DIRECTION_ID = "448"
DYNAMICS_TITLE_MARKERS = ["Dynamics of execution", "Динамика исполнения"]

YEAR_HEADER_RE = re.compile(r"(\d{4})")


def _find_dynamics_document() -> dict:
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    for d in docs:
        title = d.get("title") or ""
        if any(marker in title for marker in DYNAMICS_TITLE_MARKERS):
            return d
    raise validation.StructuralChangeError(
        "\n".join([
            "STRUCTURAL CHANGE DETECTED in minfin/GOV_REVENUE or GOV_EXPENDITURE",
            f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} matches {DYNAMICS_TITLE_MARKERS}",
            "EXPECTED: a 'Dynamics of execution of the republican budget' document",
            "ACTUAL: not found in the current listing",
            f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
        ])
    )


def _fetch_dynamics_row(row_label_substring: str, indicator_id: str) -> tuple[list[dict], dict]:
    doc = _find_dynamics_document()
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)

    today = date.today()
    ext = "xls" if file_path.lower().endswith(".xls") else "xlsx"
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_document_id": doc["id"], "source_title": doc.get("title"),
        "source_url": GOV_KZ_BASE + file_path,
    })

    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    data_sheet = next((s for s in sheet_names if "Dynamics" in s or "Динамика" in s), None)
    if data_sheet is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: no sheet name contains 'Dynamics' or 'Динамика'",
                f"EXPECTED: one of {sheet_names} to match",
                "ACTUAL: none matched",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path} and update scripts/fetchers/minfin.py",
            ])
        )

    rows = list(_iter_rows(kind, wb, data_sheet))
    header_row = next((r for r in rows if r and str(r[0]).strip().lower() == "name"), None)
    target_row = next((r for r in rows if r and row_label_substring in str(r[0])), None)
    if header_row is None or target_row is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: could not find header row ('Name') or target row ({row_label_substring!r})",
                "EXPECTED: both present in the Dynamics sheet",
                f"ACTUAL: header_row found={header_row is not None}, target_row found={target_row is not None}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path} and update scripts/fetchers/minfin.py",
            ])
        )

    records = []
    for col_idx in range(1, len(header_row)):
        year_cell = header_row[col_idx]
        if not year_cell:
            continue
        m = YEAR_HEADER_RE.search(str(year_cell))
        if not m:
            continue
        year = int(m.group(1))
        value = target_row[col_idx] if col_idx < len(target_row) else None
        if value in (None, ""):
            continue
        records.append({"date": f"{year:04d}-12-31", "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: zero year/value pairs extracted",
                "ACTION REQUIRED: inspect the Dynamics sheet layout and update scripts/fetchers/minfin.py",
            ])
        )
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": GOV_KZ_BASE + file_path,
        "dataset_id": f"gov.kz-doc-{doc['id']}",
        "note": "Annual totals (calendar-year report), stamped at Dec 31 of the reporting year. "
                "Source: 'Dynamics of execution of the republican budget' document, discovered "
                "dynamically each run rather than a hardcoded URL.",
    }
    return records, manifest


def fetch_gov_revenue() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("I. INCOME", "GOV_REVENUE")


def fetch_gov_expenditure() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("II.Expences", "GOV_EXPENDITURE")


# Functional budget-expenditure breakdown rows from the same "Dynamics" file, verified
# live 2026-08-30: row labels 'Education', 'Healthcare', 'Social assistance and social
# security' each appear exactly once in the sheet, under section II (Expenses).
def fetch_gov_health_spending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("Healthcare", "GOV_HEALTH_SPENDING")


def fetch_gov_education_spending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("Education", "GOV_EDUCATION_SPENDING")


def fetch_gov_social_spending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("Social assistance and social security", "GOV_SOCIAL_SPENDING")


# ---------------------------------------------------------------------------
# GOV_DEBT: quarterly point-in-time snapshot documents, one file per quarter
# (no combined "dynamics" file exists for debt, unlike the budget). Verified
# live 2026-08-30 across 3 vintages (Jan 2021 .xls, Jul 2024 .xlsx, Jul 2026
# .xlsx) that the target row's label text -- "Total State and State
# Guaranteed debt, State Guarantees Debt (Subsidiary Liabilities) (I + II +
# III)" -- is stable even though its row POSITION and leading-column offset
# shift between editions (a debt sub-category was added/removed over time).
# We therefore search by label text and take the row's last two numeric
# cells (tenge, usd) rather than a fixed column index.
# ---------------------------------------------------------------------------
DEBT_DIRECTION_ID = "261"
DEBT_ACTIVITY_ID = "14610"
DEBT_TOTAL_LABEL = "Total State and State Guaranteed debt"
AS_OF_RE = re.compile(r"as of\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", re.IGNORECASE)
EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_debt_document(doc: dict) -> dict | None:
    """Returns {"date": iso, "value": float} or None if this document's
    structure doesn't match what we expect (logged by the caller as a skip,
    not a hard failure -- some listed documents are known to use an
    older/different template that doesn't carry the English label we key on).
    """
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)
    kind, wb = _open_workbook(content, file_path)

    rows = list(_iter_rows(kind, wb))
    as_of_date = None
    target_values = None
    for row in rows:
        for cell in row:
            if not cell:
                continue
            m = AS_OF_RE.search(str(cell))
            if m:
                month = EN_MONTHS.get(m.group(1).lower())
                if month:
                    as_of_date = f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"
        if row and any(DEBT_TOTAL_LABEL in str(c) for c in row if c):
            numeric_cells = [c for c in row if isinstance(c, (int, float))]
            if len(numeric_cells) >= 1:
                target_values = numeric_cells  # [..., tenge_ths, usd_ths] typically

    if as_of_date is None or not target_values:
        return None

    tenge_thousands = target_values[-2] if len(target_values) >= 2 else target_values[-1]
    # Source reports "Tenge (ths)" (thousand KZT); converted to million KZT here so
    # GOV_DEBT is unit-consistent with GOV_REVENUE/GOV_EXPENDITURE (both "million KZT"
    # per the Dynamics file's own metadata sheet) in the unified dataset.
    tenge_million = float(tenge_thousands) / 1000.0
    return {
        "date": as_of_date,
        "value": tenge_million,
        "_doc_id": doc["id"],
        "_file_path": file_path,
        "_content": content,
        "_ext": "xls" if file_path.lower().endswith(".xls") else "xlsx",
    }


def fetch_gov_debt() -> tuple[list[dict], dict]:
    docs = _list_documents(directions=DEBT_DIRECTION_ID, activities=DEBT_ACTIVITY_ID)
    today = date.today()

    records: list[dict] = []
    skipped: list[int] = []
    seen_dates: set[str] = set()

    for doc in docs:
        try:
            parsed = _parse_debt_document(doc)
        except Exception:  # noqa: BLE001
            parsed = None
        if parsed is None:
            skipped.append(doc["id"])
            continue
        if parsed["date"] in seen_dates:
            continue  # a later (more recently created) doc for the same as-of date already used
        seen_dates.add(parsed["date"])

        raw_store.save_raw_bytes(SOURCE, f"GOV_DEBT_{parsed['date']}", today, parsed["_ext"], parsed["_content"])
        records.append({"date": parsed["date"], "value": parsed["value"]})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_DEBT",
                "WHAT CHANGED: zero of the listed debt documents could be parsed",
                f"EXPECTED: at least one document with the '{DEBT_TOTAL_LABEL}' row",
                f"ACTUAL: all {len(docs)} documents skipped",
                "ACTION REQUIRED: inspect a recent document and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, "GOV_DEBT", today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(docs), "n_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={DEBT_DIRECTION_ID}&activities={DEBT_ACTIVITY_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{LISTING_URL}?directions={DEBT_DIRECTION_ID}&activities={DEBT_ACTIVITY_ID}",
        "dataset_id": "gov.kz-debt-listing",
        "note": (
            f"Built from {len(records)} of {len(docs)} listed quarterly snapshot documents "
            f"({len(skipped)} skipped, ids: {skipped} -- older/differently-templated files "
            "that didn't match our label-based parser; do not assume continuous quarterly "
            "coverage without checking data/unified for gaps). Values converted from the "
            "source's thousand-KZT unit to million KZT for consistency with GOV_REVENUE/"
            "GOV_EXPENDITURE."
        ),
    }
    return records, manifest


# GOV_DEBT_DOMESTIC / GOV_DEBT_EXTERNAL: same quarterly snapshot documents as GOV_DEBT
# (DEBT_DIRECTION_ID/DEBT_ACTIVITY_ID), but a different, more specific row -- the "1.1.
# internal:" / "1.2. external:" breakdown of row "1. Republic of Kazakhstan Government
# Debt" (itself a sub-item of "I. State Debt"). Verified live 2026-08-30 by printing every
# row and column of a real document: the row label lives in the SECOND column (index 1),
# not the first (which instead holds the "1.1."/"1.2." item number) -- confirmed by summing
# internal (28,471,879,428.3) + external (8,352,366,460.626) = 36,824,245,888.926, matching
# row "1. Republic of Kazakhstan Government Debt" (36,824,245,888.92599) to 5 decimal places.
# IMPORTANT: this internal+external sum is NARROWER than GOV_DEBT itself, which sources from
# "Total State and State Guaranteed debt" (State Debt + State Guarantees + Subsidiary
# Liabilities, i.e. I+II+III) -- GOV_DEBT_DOMESTIC + GOV_DEBT_EXTERNAL will NOT reconcile to
# GOV_DEBT; they reconcile only to the core "Republic of Kazakhstan Government Debt" line.
# Documented here so nobody assumes the three should sum and concludes something's broken.
DOMESTIC_DEBT_LABEL = "internal:"
EXTERNAL_DEBT_LABEL = "external:"


def _parse_debt_component_document(doc: dict, label: str) -> dict | None:
    """Same shape as _parse_debt_document, but matches a row by an EXACT (trimmed)
    match on the row's SECOND cell (index 1) rather than a substring match on the
    first cell -- this document's sub-rows carry their item number ('1.1.', '1.2.')
    in column 0 and their descriptive label in column 1."""
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)
    kind, wb = _open_workbook(content, file_path)

    rows = list(_iter_rows(kind, wb))
    as_of_date = None
    target_values = None
    for row in rows:
        for cell in row:
            if not cell:
                continue
            m = AS_OF_RE.search(str(cell))
            if m:
                month = EN_MONTHS.get(m.group(1).lower())
                if month:
                    as_of_date = f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"
        if row and len(row) > 1 and isinstance(row[1], str) and row[1].strip() == label:
            numeric_cells = [c for c in row if isinstance(c, (int, float))]
            if len(numeric_cells) >= 1:
                target_values = numeric_cells

    if as_of_date is None or not target_values:
        return None

    tenge_thousands = target_values[-2] if len(target_values) >= 2 else target_values[-1]
    tenge_million = float(tenge_thousands) / 1000.0
    return {
        "date": as_of_date,
        "value": tenge_million,
        "_ext": "xls" if file_path.lower().endswith(".xls") else "xlsx",
        "_content": content,
    }


def _fetch_debt_component_series(label: str, indicator_id: str) -> tuple[list[dict], dict]:
    docs = _list_documents(directions=DEBT_DIRECTION_ID, activities=DEBT_ACTIVITY_ID)
    today = date.today()

    records: list[dict] = []
    skipped: list[int] = []
    seen_dates: set[str] = set()

    for doc in docs:
        try:
            parsed = _parse_debt_component_document(doc, label)
        except Exception:  # noqa: BLE001
            parsed = None
        if parsed is None:
            skipped.append(doc["id"])
            continue
        if parsed["date"] in seen_dates:
            continue
        seen_dates.add(parsed["date"])

        raw_store.save_raw_bytes(SOURCE, f"{indicator_id}_{parsed['date']}", today, parsed["_ext"], parsed["_content"])
        records.append({"date": parsed["date"], "value": parsed["value"]})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: zero of the listed debt documents could be parsed for label {label!r}",
                f"ACTION REQUIRED: inspect a recent document and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(docs), "n_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={DEBT_DIRECTION_ID}&activities={DEBT_ACTIVITY_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{LISTING_URL}?directions={DEBT_DIRECTION_ID}&activities={DEBT_ACTIVITY_ID}",
        "dataset_id": f"gov.kz-debt-listing,row={label}",
        "note": (
            f"Built from {len(records)} of {len(docs)} listed quarterly snapshot documents "
            f"({len(skipped)} skipped). Sub-component of 'Republic of Kazakhstan Government "
            "Debt' (row 1 under 'I. State Debt'), NOT of the broader GOV_DEBT total (which "
            "also includes State Guarantees and Subsidiary Liabilities, rows II+III) -- "
            "GOV_DEBT_DOMESTIC + GOV_DEBT_EXTERNAL will not sum to GOV_DEBT. Million KZT."
        ),
    }
    return records, manifest


def fetch_gov_debt_domestic() -> tuple[list[dict], dict]:
    """Domestic (internal) portion of the Republic of Kazakhstan Government Debt,
    million KZT, quarterly. See DOMESTIC_DEBT_LABEL comment above for the row
    location and the important GOV_DEBT scope caveat."""
    return _fetch_debt_component_series(DOMESTIC_DEBT_LABEL, "GOV_DEBT_DOMESTIC")


def fetch_gov_debt_external() -> tuple[list[dict], dict]:
    """External portion of the Republic of Kazakhstan Government Debt, million
    KZT, quarterly. See DOMESTIC_DEBT_LABEL comment above for the row location
    and the important GOV_DEBT scope caveat."""
    return _fetch_debt_component_series(EXTERNAL_DEBT_LABEL, "GOV_DEBT_EXTERNAL")


# More rows from the same "Dynamics" file (see GOV_REVENUE/GOV_EXPENDITURE above), verified
# 2026-08-30 by listing every row label in the sheet and picking substrings that match
# exactly one row each -- 'BUDGET DEFICIT (SURPLUS)' alone would ambiguously match BOTH
# 'V. BUDGET DEFICIT (SURPLUS)' and 'VI. NON-OIL BUDGET DEFICIT (SURPLUS)', so the more
# specific 'V. BUDGET DEFICIT' / 'NON-OIL BUDGET DEFICIT' substrings are used instead.
def fetch_tax_revenue() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("Tax revenues, including:", "TAX_REVENUE")


def fetch_corporate_tax() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("corporate income tax", "CORPORATE_TAX")


def fetch_vat_revenue() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("value added tax", "VAT_REVENUE")


def fetch_excise_tax_revenue() -> tuple[list[dict], dict]:
    """Excise tax revenue -- companion to CORPORATE_TAX/VAT_REVENUE, third and
    last tax-type breakdown row in the same Dynamics file. Verified live
    2026-08-30 by re-listing every row label in the sheet."""
    return _fetch_dynamics_row("excise taxes", "EXCISE_TAX_REVENUE")


def fetch_gov_defense_spending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("2. Defense", "GOV_DEFENSE_SPENDING")


def fetch_gov_general_services_spending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("1. General government services", "GOV_GENERAL_SERVICES_SPENDING")


def fetch_gov_transport_spending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("Transport and communications", "GOV_TRANSPORT_SPENDING")


def fetch_gov_debt_servicing() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("Debt servicing", "GOV_DEBT_SERVICING")


def fetch_net_budget_lending() -> tuple[list[dict], dict]:
    return _fetch_dynamics_row("NET BUDGET LENDING", "NET_BUDGET_LENDING")


def fetch_budget_deficit() -> tuple[list[dict], dict]:
    """Republican budget deficit (surplus). Negative = deficit, matching the source's own sign convention."""
    return _fetch_dynamics_row("V. BUDGET DEFICIT", "BUDGET_DEFICIT")


def fetch_non_oil_budget_deficit() -> tuple[list[dict], dict]:
    """Non-oil budget deficit -- a standard, KZ-specific fiscal indicator given the economy's
    oil-revenue dependence (excludes National Fund transfers from the balance)."""
    return _fetch_dynamics_row("NON-OIL BUDGET DEFICIT", "NON_OIL_BUDGET_DEFICIT")


# ---------------------------------------------------------------------------
# "General government data ... (consolidated budget according to IMF methodology)":
# a genuinely different, BROADER fiscal scope than GOV_REVENUE/GOV_EXPENDITURE/
# TAX_REVENUE/BUDGET_DEFICIT above, which are all republican-budget-only. This is
# IMF GFS-methodology general government (republican + local + social security
# funds), published quarterly. Found 2026-08-30 while researching individual
# income tax / property tax / customs duties (none of which turned out to be
# broken out in this file either -- 'Taxes' here is a single aggregate row, not
# split by type). Discovered under directions=448, title "General government
# data for the {N} quarter of {YYYY} (consolidated budget according to IMF
# methodology)" -- only ONE such document currently exists in the listing
# (unlike GOV_DEBT's 23 quarterly snapshots), but that single document already
# contains all 4 quarters of its year as separate columns (period labels like
# '2025/1'..'2025/4'), not just the one quarter named in its title -- so no
# historical backfill across multiple documents is needed for the current year.
# Values in the source are billions of KZT; converted to million KZT here for
# consistency with GOV_REVENUE/GOV_EXPENDITURE/GOV_DEBT.
# ---------------------------------------------------------------------------
GG_TITLE_RE = re.compile(r"general\s+government|сектору\s+государственного\s+управления", re.IGNORECASE)
GG_QUARTER_HEADER_RE = re.compile(r"^(\d{4})/(\d)$")
GG_QUARTER_END_MONTH_DAY = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _find_gg_documents() -> list[dict]:
    """Every quarterly general-government document Minfin still lists, newest first.

    Matched by pattern, not by one title: Minfin words the title differently almost every
    quarter -- "General Government date 2023/3Q", "General Government Data Q1 2025", "Data
    on the General Government sektor ... for the 2 Q of 2025", "Данные по сектору
    государственного управления ... за 1 квартал 2026", "General government SECTOR data
    for Q2 2026". The old fixed marker "General government data" missed the last two, so
    from 2026-06 the fetcher silently kept reading the Q4 2025 file and GG_* stopped at
    2025Q4 while two newer quarters were online.

    Each file carries only its own year's quarters, so the history is the union of all of
    them (23 documents on 2026-09-26, the oldest from 2020-03 with 2019). The budget
    direction's listing holds only its latest 100 documents, hence the title searches.
    """
    found: dict = {}
    for d in _list_documents(directions=BUDGET_DIRECTION_ID):
        found[d.get("id")] = d
    for title in ("government", "государственного управления"):
        for page in range(1, 6):
            batch = _list_documents(title=title, projects="minfin", page=str(page))
            for d in batch:
                found.setdefault(d.get("id"), d)
            if len(batch) < 100:
                break
    docs = [d for d in found.values()
            if GG_TITLE_RE.search(d.get("title") or "") and d.get("full_text")
            and str(d["full_text"][0].get("document", "")).lower().endswith((".xlsx", ".xls"))]
    if not docs:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GG_* indicators",
                f"WHAT CHANGED: no listed document title matches {GG_TITLE_RE.pattern!r}",
                "EXPECTED: quarterly 'General government ... (consolidated budget according to IMF methodology)' documents",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )
    return sorted(docs, key=lambda d: d.get("created_date") or "", reverse=True)


def _gg_coverage_year(doc: dict) -> int:
    """The year a quarterly GG file covers, from its publication date: Q4 comes out in
    March of the next year, Q1-Q3 from June to December of their own. Each file carries only
    that year's quarters, so a quarter labelled with another year is a header error, not
    data: the Q2 2020 file (id 70842) heads its columns "2019/1", "2019/2", and its first
    column equals the Q1 2020 file's 2020/1 (2,339,6xx mln KZT of taxes). Pre-filled zeros
    for quarters not yet reported (the Q1 2020 file's 2020/3 and 2020/4) are not data either."""
    created = str(doc.get("created_date") or "")
    y, m = int(created[:4]), int(created[5:7])
    return y if m >= 4 else y - 1


def _fetch_gg_row(row_code, indicator_id: str) -> tuple[list[dict], dict]:
    """The union of every listed document, oldest first so a newer edition's figure for a
    quarter replaces an older one's (revisions). Documents that do not parse are skipped;
    the newest must parse, or the layout has changed and that is raised."""
    docs = _find_gg_documents()
    merged: dict[str, float] = {}
    manifest = None
    skipped, dropped = [], []
    for doc in reversed(docs):
        try:
            records, man = _fetch_gg_row_from(doc, row_code, indicator_id)
        except (validation.StructuralChangeError, requests.RequestException):
            # an older edition that fails to parse or to download costs only its own
            # quarters, which keep_unlisted_history retains from earlier runs; the newest
            # edition must succeed
            if doc is docs[0]:
                raise
            skipped.append(str(doc.get("id")))
            continue
        year = _gg_coverage_year(doc)
        for r in records:
            if int(r["date"][:4]) != year or r["value"] == 0:
                dropped.append(f"{doc.get('id')}:{r['date']}={r['value']:g}")
                continue
            merged[r["date"]] = r["value"]
        manifest = man
    manifest = {**manifest, "documents_read": len(docs) - len(skipped),
                "documents_skipped": skipped, "cells_dropped": dropped}
    return [{"date": d, "value": v} for d, v in sorted(merged.items())], manifest


def _fetch_gg_row_from(doc: dict, row_code, indicator_id: str) -> tuple[list[dict], dict]:
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)

    today = date.today()
    ext = "xls" if file_path.lower().endswith(".xls") else "xlsx"
    raw_name = f"{indicator_id}_{doc['id']}"
    raw_store.save_raw_bytes(SOURCE, raw_name, today, ext, content)
    raw_store.write_download_manifest(SOURCE, raw_name, today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_document_id": doc["id"], "source_title": doc.get("title"),
        "source_url": GOV_KZ_BASE + file_path,
    })

    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    rows = list(_iter_rows(kind, wb, sheet_names[0]))

    header_row = next((r for r in rows if r and any(
        isinstance(c, str) and GG_QUARTER_HEADER_RE.match(c.strip()) for c in r if c
    )), None)
    target_row = next((r for r in rows if r and r[0] == row_code), None)
    if header_row is None or target_row is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: could not find header row (quarter labels like '2025/1') or target row (code {row_code!r})",
                "EXPECTED: both present in the sheet",
                f"ACTUAL: header_row found={header_row is not None}, target_row found={target_row is not None}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path} and update scripts/fetchers/minfin.py",
            ])
        )

    records = []
    for col_idx, header_cell in enumerate(header_row):
        if not isinstance(header_cell, str):
            continue
        m = GG_QUARTER_HEADER_RE.match(header_cell.strip())
        if not m:
            continue
        year, quarter = int(m.group(1)), int(m.group(2))
        if quarter not in GG_QUARTER_END_MONTH_DAY:
            continue
        value = target_row[col_idx] if col_idx < len(target_row) else None
        if value in (None, ""):
            continue
        month, day = GG_QUARTER_END_MONTH_DAY[quarter]
        records.append({"date": f"{year:04d}-{month:02d}-{day:02d}", "value": float(value) * 1000.0})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: zero quarter/value pairs extracted",
                "ACTION REQUIRED: inspect the sheet layout and update scripts/fetchers/minfin.py",
            ])
        )
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": GOV_KZ_BASE + file_path,
        "dataset_id": f"gov.kz-doc-{doc['id']}",
        "note": (
            "Million KZT (converted from the source's billion-KZT unit). General government "
            "(IMF GFS methodology: republican + local + social security funds combined), "
            "BROADER scope than GOV_REVENUE/GOV_EXPENDITURE/TAX_REVENUE/BUDGET_DEFICIT above, "
            "which are all republican-budget-only -- do not expect these to reconcile."
        ),
    }
    return records, manifest


def fetch_gg_taxes() -> tuple[list[dict], dict]:
    """General government tax revenue (IMF GFS methodology, all levels of
    government combined), million KZT, quarterly. Row code 11 ('Taxes').
    Verified live 2026-08-30: 4 quarters of 2025, ~5.15-7.02 trillion KZT --
    larger than the republican-budget-only TAX_REVENUE for the same periods,
    as expected since this also includes local and social-security-fund tax
    collections."""
    return _fetch_gg_row(11, "GG_TAXES")


def fetch_gg_social_contributions() -> tuple[list[dict], dict]:
    """General government social contributions received, million KZT,
    quarterly. Row code 12 ('Social contributions'). Verified live
    2026-08-30: 4 quarters of 2025, ~467-572 billion KZT."""
    return _fetch_gg_row(12, "GG_SOCIAL_CONTRIBUTIONS")


def fetch_gg_interest() -> tuple[list[dict], dict]:
    """General government interest expense (IMF GFS, all levels combined), million KZT,
    quarterly. Row code 24 ('Interest'). Added 2026-09-25 for rating models (interest /
    revenue); 2025: 982.0, 687.6, 655.3, 334.5 bn by quarter in the Q4-2025 file."""
    return _fetch_gg_row(24, "GG_INTEREST")


def fetch_gg_cash_surplus_deficit() -> tuple[list[dict], dict]:
    """General government cash surplus/deficit (IMF GFS methodology, all
    levels of government combined), million KZT, quarterly -- a broader
    fiscal balance measure than BUDGET_DEFICIT (republican-budget-only).
    Row code 'CSD' ('Cash surplus / deficit [1-2-31 = 1-2M]'). Verified live
    2026-08-30: 4 quarters of 2025, ranging from -1.94 trillion (Q2 deficit)
    to +2.42 trillion KZT (Q3 surplus) -- plausible quarter-to-quarter
    volatility for a resource-revenue-dependent government's cash position.
    """
    return _fetch_gg_row("CSD", "GG_CASH_SURPLUS_DEFICIT")


# ---------------------------------------------------------------------------
# CUSTOMS_DUTIES: found 2026-08-30 while finally opening the "Statistical bulletin"
# document (49 sheets, 1.5MB -- avoided in earlier sessions as too large/risky, but
# turned out to be perfectly parseable) that was set aside as too complex to attempt.
# Sheet "табл 8 (дох)" ("Table 8, revenues") is the full KBK (budget classification
# code) breakdown of republican-budget revenue by exact tax/fee type, at whatever
# granularity Minfin itself publishes -- and 'Таможенные платежи' (customs payments,
# class 06/subclass 1, "Taxes on international trade and external operations") is a
# genuine, distinct line in it.
#
# IMPORTANT structural finding from the SAME sheet: individual income tax and
# property tax do NOT appear anywhere in this republican-budget table -- the only
# "income tax" row present is explicitly 'Корпоративный подоходный налог' (corporate
# income tax only). This is consistent with Kazakhstan's budget code assigning
# individual income tax and property tax entirely to LOCAL government budgets, not
# the republican budget -- explaining why no republican-level document (this one, the
# Dynamics file, or the General Government IMF-methodology file) ever surfaced them.
# Not pursued further: extracting them would require aggregating 17+ separate local
# budget execution reports, a real methodological undertaking, not a search failure.
#
# CRITICAL discovery about this document series: the document TITLE ("Statistical
# bulletin as of {Month} 1, {YYYY}") is UNRELIABLE -- three documents all titled
# "as of April 1, 2026" turned out, on inspection of their actual sheet content, to
# cover three ENTIRELY DIFFERENT periods (Jan-Feb, Jan-Mar, Jan-May 2026). The only
# trustworthy period indicator is the sheet's own internal header text (e.g.
# "январь-май отчет 2026 г." = "January-May 2026 report"), which is what this
# fetcher actually parses -- never the document title.
#
# The series itself is genuinely YEAR-TO-DATE CUMULATIVE, resetting near zero every
# January and growing through the year (confirmed: 2025 values climb monotonically
# from ~211bn KZT in Feb to ~2,002bn KZT in Nov; 2026 from ~66bn in Jan to ~1,165bn
# in Jun) -- NOT a data error when a naive chart shows a sawtooth pattern year over
# year. No document in the current listing covers a full Jan-Dec year (the latest
# available point for 2025 is Jan-Nov); this is a real gap, not fabricated/
# interpolated into a fake annual figure.
# ---------------------------------------------------------------------------
STATISTICAL_BULLETIN_TITLE_MARKER = "Statistical bulletin"
BULLETIN_REVENUE_SHEET_NAME = "табл 8 (дох)"
BULLETIN_PERIOD_RE = re.compile(r"январь(?:-(\w+))?\s+отчет\s+(\d{4})", re.IGNORECASE)
RU_MONTH_TO_NUM = {
    "январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
    "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
}
# Matched by stem, not by the full word: the January-February 2026 bulletin heads
# табл 3 "январь-феврал отчет" (no soft sign) and the exact lookup dropped that
# edition from six STATE_*_YTD series (audit 2026-09-25). Stems also cover the
# genitive forms ("мая", "августа") a header may use.
RU_MONTH_STEMS = (("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4), ("ма", 5), ("июн", 6),
                  ("июл", 7), ("август", 8), ("сентябр", 9), ("октябр", 10), ("ноябр", 11), ("декабр", 12))


def _ru_month(name: str | None) -> int | None:
    name = (name or "").strip().lower()
    if name in RU_MONTH_TO_NUM:
        return RU_MONTH_TO_NUM[name]
    return next((num for stem, num in RU_MONTH_STEMS if name.startswith(stem) and len(name) <= len(stem) + 3), None)
CUSTOMS_DUTIES_ROW_LABEL = "Таможенные платежи"


def _fetch_bulletin_row(sheet_name: str, row_matcher, indicator_id: str, value_col: int = -2,
                        note_override: str | None = None) -> tuple[list[dict], dict]:
    """Shared fetcher for any single row in one of the "Statistical bulletin"
    document's sheets, across all listed bulletin vintages. `row_matcher` is
    a callable(row) -> bool that identifies the target row within the sheet
    (each sheet's column layout differs, so this is left to the caller
    rather than a fixed column index). See CUSTOMS_DUTIES's module comment
    above for the full explanation of why this needs multi-document
    iteration, why document titles are not trusted, and why the result is
    genuinely year-to-date cumulative with real gaps.
    `value_col` defaults to -2 ("second-to-last column", the convention every
    sheet used so far happens to follow) but is overridable: табл 4's rows
    have a trailing-cell count that genuinely varies between vintages (7, 9,
    or 10 elements for the exact same logical row, depending on how much
    empty trailing range openpyxl picked up from that specific file) --
    confirmed live that -2 silently lands on a None padding cell in 4 of 13
    vintages there, dropping those records. An absolute column index (5, the
    value's real fixed position in that sheet) is used instead for that
    sheet's fetchers.
    """
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )

    today = date.today()
    records: list[dict] = []
    seen_dates: set[str] = set()
    skipped: list[int] = []

    for doc in bulletins:
        file_path = doc["full_text"][0]["document"]
        content = _download(file_path)
        kind, wb = _open_workbook(content, file_path)
        sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        target_sheet = next((s for s in sheet_names if s.strip() == sheet_name), None)
        if target_sheet is None:
            skipped.append(doc["id"])
            continue

        rows = list(_iter_rows(kind, wb, target_sheet))
        header_row = next((r for r in rows if r and any(
            isinstance(c, str) and BULLETIN_PERIOD_RE.search(c) for c in r if c
        )), None)
        period_match = None
        if header_row:
            for cell in header_row:
                if isinstance(cell, str):
                    m = BULLETIN_PERIOD_RE.search(cell)
                    if m:
                        period_match = m
                        break
        target_row = next((r for r in rows if r and row_matcher(r)), None)
        if period_match is None or target_row is None:
            skipped.append(doc["id"])
            continue

        end_month_name = (period_match.group(1) or "январь").lower()
        end_month = _ru_month(end_month_name)
        year = int(period_match.group(2))
        value = target_row[value_col] if -len(target_row) <= value_col < len(target_row) else None
        if end_month is None or value in (None, ""):
            skipped.append(doc["id"])
            continue

        last_day = calendar.monthrange(year, end_month)[1]
        iso_date = f"{year:04d}-{end_month:02d}-{last_day:02d}"
        raw_store.save_raw_bytes(SOURCE, f"{indicator_id}_{iso_date}", today,
                                  "xls" if file_path.lower().endswith(".xls") else "xlsx", content)
        if iso_date in seen_dates:
            continue
        seen_dates.add(iso_date)
        records.append({"date": iso_date, "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: zero of {len(bulletins)} listed bulletin documents could be parsed",
                f"ACTUAL: all skipped, ids: {skipped}",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(bulletins), "n_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "irregular (year-to-date cumulative, roughly monthly)",
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        "dataset_id": f"gov.kz-statistical-bulletin-listing,sheet={sheet_name}",
        "note": (
            f"Built from {len(records)} of {len(bulletins)} listed 'Statistical bulletin' "
            f"documents ({len(skipped)} skipped -- missing sheet or unparseable period/row). "
            "Million KZT, republican budget only. YEAR-TO-DATE CUMULATIVE, resets near zero "
            "each January -- do not read a January value as a sudden collapse from the prior "
            "December's much larger cumulative figure; that is the expected pattern for a "
            "cumulative-since-Jan-1 series, not a data error. No document currently covers a "
            "full Jan-Dec year; real gaps exist and are not fabricated/interpolated. Document "
            "TITLES ('as of {Month} 1') are NOT used to determine period -- they were found "
            "unreliable; only each document's own internal period text is trusted."
        ),
    }
    # The default note says "republican budget only", which is true of every sheet
    # this helper served until "табл 3" (the STATE budget: republican plus local).
    # Callers on a different scope pass their own note rather than shipping a
    # manifest that misstates what the numbers cover.
    if note_override is not None:
        manifest["note"] = (f"Built from {len(records)} of {len(bulletins)} listed 'Statistical "
                            f"bulletin' documents ({len(skipped)} skipped). " + note_override)
    return records, manifest


def fetch_customs_duties() -> tuple[list[dict], dict]:
    """Customs duties (import + export), republican budget, million KZT,
    year-to-date cumulative (resets each January -- see the module comment
    above for why this is a real pattern, not a bug). Verified live
    2026-08-30: 13 documents parsed, values genuinely monotonic within each
    year (2025: ~212bn in Feb to ~2,003bn in Nov; 2026: ~66bn in Jan to
    ~1,165bn in Jun)."""
    return _fetch_bulletin_row(
        BULLETIN_REVENUE_SHEET_NAME,
        lambda r: len(r) > 3 and r[3] == "1" and r[-1] == CUSTOMS_DUTIES_ROW_LABEL,
        "CUSTOMS_DUTIES",
    )


# ---------------------------------------------------------------------------
# Republican budget expenditure by ECONOMIC classification (as opposed to the
# FUNCTIONAL classification already covered by GOV_HEALTH_SPENDING/GOV_EDUCATION_
# SPENDING/etc. from the Dynamics file) -- found 2026-08-30 in the same
# "Statistical bulletin" document's "табл 10" sheet, immediately after resolving
# CUSTOMS_DUTIES in the neighboring "табл 8 (дох)" sheet. Standard GFS-style
# breakdown by TYPE of spending (wages, capital, transfers, subsidies) rather than
# purpose. Confirmed the sheet and target rows are present with exactly one match
# each across all 13 currently-listed bulletin documents, values monotonically
# consistent with the same year-to-date cumulative pattern as CUSTOMS_DUTIES.
# ---------------------------------------------------------------------------
BULLETIN_EXPENDITURE_ECONOMIC_SHEET_NAME = "табл 10"


def fetch_gov_wages_expenditure() -> tuple[list[dict], dict]:
    """Republican budget wages expenditure (compensation category 110,
    'Заработная плата'), million KZT, year-to-date cumulative. Verified live
    2026-08-30: 13 documents parsed, monotonic within each year (2025:
    ~180bn Feb to ~1,015bn Nov; 2026: ~62bn Jan to ~489bn Jun)."""
    return _fetch_bulletin_row(
        BULLETIN_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Заработная плата",
        "GOV_WAGES_EXPENDITURE",
    )


def fetch_gov_capital_expenditure() -> tuple[list[dict], dict]:
    """Republican budget capital expenditure (top-level economic category 2,
    'Капитальные затраты'), million KZT, year-to-date cumulative. Verified
    live 2026-08-30: 13 documents parsed, monotonic within each year (2025:
    ~97bn Feb to ~1,597bn Nov; 2026: ~1bn Jan to ~440bn Jun -- note the very
    low January figure is plausible: capital projects often front-load
    spending later in the fiscal year)."""
    return _fetch_bulletin_row(
        BULLETIN_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Капитальные затраты",
        "GOV_CAPITAL_EXPENDITURE",
    )


def fetch_gov_pensions_expenditure() -> tuple[list[dict], dict]:
    """Republican budget pension expenditure (category 323, 'Пенсии'),
    million KZT, year-to-date cumulative. Verified live 2026-08-30: 13
    documents parsed, monotonic within each year (2025: ~737bn Feb to
    ~3,949bn Nov; 2026: ~431bn Jan to ~2,454bn Jun)."""
    return _fetch_bulletin_row(
        BULLETIN_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Пенсии",
        "GOV_PENSIONS_EXPENDITURE",
    )


def fetch_gov_subsidies_expenditure() -> tuple[list[dict], dict]:
    """Republican budget budgetary subsidies (category 310, 'Бюджетные
    субсидии'), million KZT, year-to-date cumulative -- an economic-
    classification view of subsidies, distinct from BNS's national-accounts
    SUBSIDIES indicator. Verified live 2026-08-30: 13 documents parsed,
    monotonic within each year (2025: ~34bn Feb to ~414bn Nov; 2026: ~6bn
    Jan to ~259bn Jun)."""
    return _fetch_bulletin_row(
        BULLETIN_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Бюджетные субсидии",
        "GOV_SUBSIDIES_EXPENDITURE",
    )


# ---------------------------------------------------------------------------
# SUBVENTIONS_REPUBLICAN: found 2026-08-30 while continuing to explore the
# "Statistical bulletin" document -- sheet "табл 18" ("ТРАНСФЕРТЫ ОБЩЕГО
# ХАРАКТЕРА" / general-character transfers). Unlike CUSTOMS_DUTIES/GOV_*_
# EXPENDITURE above, this sheet uses the SAME multi-year-ANNUAL-column layout
# as the small "Dynamics of execution" file (GOV_REVENUE/TAX_REVENUE/etc.) --
# one document already contains 2023/2024/2025 as separate annual columns, so
# only the single most recent bulletin is needed, not a 13-document backfill.
#
# A companion table, "табл 13" (consolidated-budget execution report, which
# would have given a genuinely new CONSOLIDATED-level budget deficit measure)
# was also investigated and explicitly NOT connected: its column layout and
# row-label conventions (e.g. whether "XV." Roman-numeral prefixes are used)
# vary across bulletin vintages in ways that risk silently landing on the
# wrong column/row in some vintages -- the same category of risk that led to
# abandoning the IMF GFS dataset earlier this session. Not pursued further.
# ---------------------------------------------------------------------------
BULLETIN_TRANSFERS_SHEET_NAME = "табл 18"
SUBVENTIONS_ROW_LABEL = "Республикалық бюджеттен субвенциялар"
ANNUAL_YEAR_HEADER_RE = re.compile(r"^\s*(\d{4})\s*ж\.\s*есеп")


def _fetch_bulletin_annual_row(sheet_name: str, row_matcher, indicator_id: str, note: str,
                                header_re: re.Pattern = ANNUAL_YEAR_HEADER_RE,
                                date_for_year=lambda year: f"{year:04d}-12-31") -> tuple[list[dict], dict]:
    """Shared fetcher for the "single latest document, multi-year-ANNUAL-
    column" layout used by several Statistical Bulletin sheets (as opposed to
    _fetch_bulletin_row's "iterate all 13 vintages, year-to-date cumulative"
    layout) -- one document already contains several full calendar years as
    separate columns (e.g. '2023 ж. есеп', '2024 ж. есеп', '2025 ж. есеп'),
    so only the single most recent bulletin is needed. A same-document
    current-year PARTIAL-period column (e.g. '2026 ж. қаңтар-наурыз') is
    deliberately excluded because its header text doesn't match the default
    'YYYY ж. есеп' pattern -- not via special-casing, just because the regex
    requires the literal word 'есеп' (annual report) right after the year.
    `header_re` is overridable for sheets that use a different annual-column
    header convention (e.g. 'на 1 января YYYY года' point-in-time headers);
    group(1) must always be the 4-digit year. `date_for_year` is overridable
    to match: the default assumes an annual REPORT for year Y (stamped at
    year-end, Dec 31); a Jan-1 point-in-time snapshot header instead needs
    `lambda year: f"{year:04d}-01-01"` -- getting this wrong silently
    mislabels every record by up to a full year, so it must match the
    header's own semantics, not just its year regex.
    """
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )
    doc = bulletins[0]
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)

    today = date.today()
    ext = "xls" if file_path.lower().endswith(".xls") else "xlsx"
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_document_id": doc["id"], "source_title": doc.get("title"),
        "source_url": GOV_KZ_BASE + file_path,
    })

    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    target_sheet = next((s for s in sheet_names if s.strip() == sheet_name), None)
    if target_sheet is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no sheet named {sheet_name!r} in the latest bulletin",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path} and update scripts/fetchers/minfin.py",
            ])
        )

    rows = list(_iter_rows(kind, wb, target_sheet))
    header_row = next((r for r in rows if r and any(
        isinstance(c, str) and header_re.search(c) for c in r if c
    )), None)
    target_row = next((r for r in rows if r and row_matcher(r)), None)
    if header_row is None or target_row is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: could not find header row (annual year labels) or target row",
                f"ACTUAL: header_row found={header_row is not None}, target_row found={target_row is not None}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path} and update scripts/fetchers/minfin.py",
            ])
        )

    records = []
    for col_idx, header_cell in enumerate(header_row):
        if not isinstance(header_cell, str):
            continue
        m = header_re.search(header_cell)
        if not m:
            continue
        year = int(m.group(1))
        value = target_row[col_idx] if col_idx < len(target_row) else None
        if value in (None, ""):
            continue
        records.append({"date": date_for_year(year), "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: zero year/value pairs extracted",
                "ACTION REQUIRED: inspect the sheet layout and update scripts/fetchers/minfin.py",
            ])
        )
    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": GOV_KZ_BASE + file_path,
        "dataset_id": f"gov.kz-doc-{doc['id']},sheet={sheet_name}",
        "note": note,
    }
    return records, manifest


def fetch_subventions_republican() -> tuple[list[dict], dict]:
    """Subventions (unconditional transfers) from the republican budget to
    regional budgets, million KZT, annual. Verified live 2026-08-30: matched
    exactly once in the most recent 'Statistical bulletin' document, 3
    genuine annual columns (2023-2025) -- the same document's Jan-Jun 2026
    partial-year column is deliberately excluded (its header contains a
    month-range, detected and skipped) to avoid mixing a partial year into
    an annual series. Values: 4,995,054.75 (2023) to 5,755,110.61 (2025)
    million KZT.
    """
    return _fetch_bulletin_annual_row(
        BULLETIN_TRANSFERS_SHEET_NAME,
        lambda r: len(r) > 1 and r[1] == SUBVENTIONS_ROW_LABEL,
        "SUBVENTIONS_REPUBLICAN",
        "Million KZT. Annual totals only (calendar-year reports); the same document's "
        "current-year partial-period column is deliberately excluded to avoid mixing a "
        "partial year into an annual series.",
    )


# ---------------------------------------------------------------------------
# LOCAL_GOV_*_EXPENDITURE: local (regional) budget expenditure by ECONOMIC
# classification -- the direct local-budget counterpart to GOV_WAGES_EXPENDITURE/
# GOV_CAPITAL_EXPENDITURE/GOV_SUBSIDIES_EXPENDITURE above, found 2026-08-31 in
# the same "Statistical bulletin" document's local-budget sheet. NOTE: this
# sheet's actual name is "таб 11" (missing the "л") -- confirmed a stable typo,
# not vintage-to-vintage variance, across all 13 currently-listed bulletins.
# Row labels ('Заработная плата', 'Капитальные затраты', 'Бюджетные субсидии')
# each matched exactly once across all 13 vintages. Unlike табл 10 (republican),
# this local-budget sheet has NO 'Пенсии' (pensions) row at all -- pensions are
# not a local-budget expenditure category in Kazakhstan, so no
# LOCAL_GOV_PENSIONS_EXPENDITURE indicator exists. Same year-to-date cumulative
# pattern as CUSTOMS_DUTIES/GOV_*_EXPENDITURE (see CUSTOMS_DUTIES module comment).
# ---------------------------------------------------------------------------
BULLETIN_LOCAL_EXPENDITURE_ECONOMIC_SHEET_NAME = "таб 11"


def fetch_local_gov_wages_expenditure() -> tuple[list[dict], dict]:
    """Local (regional) budget wages expenditure ('Заработная плата'), million
    KZT, year-to-date cumulative. Verified live 2026-08-31: 13 documents
    parsed, exactly one matching row in each."""
    return _fetch_bulletin_row(
        BULLETIN_LOCAL_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Заработная плата",
        "LOCAL_GOV_WAGES_EXPENDITURE",
    )


def fetch_local_gov_capital_expenditure() -> tuple[list[dict], dict]:
    """Local (regional) budget capital expenditure ('Капитальные затраты'),
    million KZT, year-to-date cumulative. Verified live 2026-08-31: 13
    documents parsed, exactly one matching row in each."""
    return _fetch_bulletin_row(
        BULLETIN_LOCAL_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Капитальные затраты",
        "LOCAL_GOV_CAPITAL_EXPENDITURE",
    )


def fetch_local_gov_subsidies_expenditure() -> tuple[list[dict], dict]:
    """Local (regional) budget budgetary subsidies ('Бюджетные субсидии'),
    million KZT, year-to-date cumulative. Verified live 2026-08-31: 13
    documents parsed, exactly one matching row in each."""
    return _fetch_bulletin_row(
        BULLETIN_LOCAL_EXPENDITURE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Бюджетные субсидии",
        "LOCAL_GOV_SUBSIDIES_EXPENDITURE",
    )


# ---------------------------------------------------------------------------
# NATIONAL_FUND_STABILIZATION_PORTFOLIO / _SAVINGS_PORTFOLIO / _SAVINGS_BONDS /
# _EQUITIES / _GOLD: composition breakdown (USD, quarterly point-in-time
# snapshot) of the National Fund of the Republic of Kazakhstan's investment
# portfolio -- found 2026-08-31 in the same "Statistical bulletin" document's
# sheet "табл 17 кв+1мес" ("Composition of the portfolio and asset allocation
# of the National Fund", sourced by Minfin FROM the National Bank RK). NOTE:
# unlike CUSTOMS_DUTIES/GOV_*_EXPENDITURE, this sheet's name varies slightly
# across vintages ("табл 17 кв+1мес" in the 11 most recent, "табл 17 кв" in the
# 2 oldest) -- matched here by prefix ("табл 17") rather than exact string.
#
# IMPORTANT: this sheet also has a grand-total row ("БАРЛЫҒЫ"/"ВСЕГО") that
# was initially built out as its own indicator, "NATIONAL_FUND_ASSETS" -- but
# then REMOVED after discovering it collided with an ALREADY-EXISTING
# indicator of that exact same ID, sourced from NBK formId=34 (see
# fetch_fx_reserves's neighboring notes in config/sources.yaml). The two
# turned out to be, for practical purposes, the same underlying figure (e.g.
# this sheet's 2026-Q1 total of USD 62,395,968,457 vs NBK's 2026-04-01 value
# of USD 62,395,954,208 -- a ~0.00002% difference, almost certainly the same
# valuation one day apart) -- and the NBK series is strictly better anyway
# (monthly vs quarterly, longer history). Only the SUB-PORTFOLIO breakdown
# below (which NBK's formId=34 does not provide) was kept.
#
# Structurally different from every other bulletin-sheet fetcher in this file:
# (a) it's a POINT-IN-TIME snapshot (portfolio value as of quarter-end), not a
# year-to-date cumulative flow -- each of the 13 listed bulletins reports
# whichever quarter was most recently closed as of its publication, so
# iterating across all 13 yields 6 distinct quarters (2024-Q4 through 2026-Q1),
# not 13 growing partial-year figures; (b) values are already in USD (not
# million KZT); (c) the row layout differs (label in column 0, value in
# column 1, NOT the "value in the second-to-last column" convention used by
# _fetch_bulletin_row), so this uses its own inline extraction rather than
# that shared helper. Period parsed from the sheet's own Russian header text
# ('ЗА {N} КВАРТАЛ {YYYY} ГОДА'), never the unreliable document title.
# ---------------------------------------------------------------------------
NF_SHEET_PREFIX = "табл 17"
NF_QUARTER_RE = re.compile(r"ЗА\s+(\d)\s+КВАРТАЛ\s+(\d{4})\s+ГОДА", re.IGNORECASE)
NF_QUARTER_END_MONTH_DAY = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _fetch_nf_row(row_finder, indicator_id: str, description_note: str) -> tuple[list[dict], dict]:
    """Shared fetcher for any single row in the National Fund portfolio sheet
    (see the module comment above for the full structural explanation).
    `row_finder` is a callable(rows: list[list]) -> row | None,
    given the freedom to scope its search by row ORDER (not just label text)
    since some labels repeat in this sheet (e.g. 'Облигации' appears both
    under the stabilization portfolio, where it is consistently 0, and under
    the savings portfolio, where it is the real figure) -- see
    fetch_national_fund_savings_bonds for how that ambiguity is resolved.
    """
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )

    today = date.today()
    records: list[dict] = []
    seen_dates: set[str] = set()
    skipped: list[int] = []

    for doc in bulletins:
        file_path = doc["full_text"][0]["document"]
        content = _download(file_path)
        kind, wb = _open_workbook(content, file_path)
        sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        target_sheet = next((s for s in sheet_names if s.strip().startswith(NF_SHEET_PREFIX)), None)
        if target_sheet is None:
            skipped.append(doc["id"])
            continue

        rows = list(_iter_rows(kind, wb, target_sheet))
        period_match = None
        for row in rows:
            for cell in row:
                if isinstance(cell, str):
                    m = NF_QUARTER_RE.search(cell)
                    if m:
                        period_match = m
                        break
            if period_match:
                break
        target_row = row_finder(rows)
        if period_match is None or target_row is None:
            skipped.append(doc["id"])
            continue

        quarter = int(period_match.group(1))
        year = int(period_match.group(2))
        if quarter not in NF_QUARTER_END_MONTH_DAY:
            skipped.append(doc["id"])
            continue
        value = target_row[1] if len(target_row) > 1 else None
        if value in (None, ""):
            skipped.append(doc["id"])
            continue

        month, day = NF_QUARTER_END_MONTH_DAY[quarter]
        iso_date = f"{year:04d}-{month:02d}-{day:02d}"
        raw_store.save_raw_bytes(SOURCE, f"{indicator_id}_{iso_date}", today,
                                  "xls" if file_path.lower().endswith(".xls") else "xlsx", content)
        if iso_date in seen_dates:
            continue
        seen_dates.add(iso_date)
        records.append({"date": iso_date, "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: zero of {len(bulletins)} listed bulletin documents could be parsed",
                f"ACTUAL: all skipped, ids: {skipped}",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(bulletins), "n_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "quarterly",
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        "dataset_id": f"gov.kz-statistical-bulletin-listing,sheet={NF_SHEET_PREFIX}*",
        "note": (
            f"Built from {len(records)} of {len(bulletins)} listed 'Statistical bulletin' "
            f"documents ({len(skipped)} skipped). USD (not KZT). {description_note} "
            "A POINT-IN-TIME snapshot as of each calendar quarter-end, not a cumulative flow "
            "(unlike most other minfin bulletin-sourced indicators). Originally sourced by "
            "Minfin FROM the National Bank RK, republished here in the Statistical Bulletin. "
            "Document TITLES are NOT used to determine period -- only each document's own "
            "internal 'ЗА N КВАРТАЛ YYYY ГОДА' header text is trusted."
        ),
    }
    return records, manifest


def _nf_row_by_label(rows: list, label: str):
    return next((r for r in rows if r and any(
        isinstance(c, str) and c.strip() == label for c in r if c
    )), None)


# Row order confirmed byte-identical (same 10-row block: Стабилизационный
# портфель / Облигации / Деньги.../ Сберегательный портфель / Облигации /
# Акции / Золото / Альтернативные инструменты / Целевые требования / БАРЛЫҒЫ,
# in that exact sequence) in BOTH the oldest (2024-Q4) and newest (2026-Q1)
# vintages, 13 months apart -- unusually stable for this document family, and
# the basis for the row-order disambiguation in fetch_national_fund_savings_bonds.
NF_STABILIZATION_LABEL = "Стабилизационный портфель"
NF_SAVINGS_LABEL = "Сберегательный портфель"
NF_BONDS_LABEL = "Облигации"
NF_EQUITIES_LABEL = "Акции"
NF_GOLD_LABEL = "Золото"


def fetch_national_fund_stabilization_portfolio() -> tuple[list[dict], dict]:
    """National Fund stabilization portfolio value, USD, quarterly. Verified
    live 2026-08-31: matched exactly once per vintage, 6 quarters recovered."""
    return _fetch_nf_row(
        lambda rows: _nf_row_by_label(rows, NF_STABILIZATION_LABEL),
        "NATIONAL_FUND_STABILIZATION_PORTFOLIO",
        "National Fund 'stabilization portfolio' (Стабилизационный портфель) sub-total -- "
        "the smaller, liquidity-focused portion of the Fund, held mostly in cash and "
        "money-market instruments.",
    )


def fetch_national_fund_savings_portfolio() -> tuple[list[dict], dict]:
    """National Fund savings portfolio value, USD, quarterly -- the much
    larger, diversified (bonds/equities/gold/alternatives) portion of the
    Fund. Verified live 2026-08-31: matched exactly once per vintage, 6
    quarters recovered."""
    return _fetch_nf_row(
        lambda rows: _nf_row_by_label(rows, NF_SAVINGS_LABEL),
        "NATIONAL_FUND_SAVINGS_PORTFOLIO",
        "National Fund 'savings portfolio' (Сберегательный портфель) sub-total -- the larger, "
        "diversified (bonds/equities/gold/alternative instruments) portion of the Fund.",
    )


def fetch_national_fund_savings_bonds() -> tuple[list[dict], dict]:
    """National Fund savings-portfolio bond holdings, USD, quarterly. See the
    module comment above for how this disambiguates from the stabilization
    portfolio's own (always-zero) 'Облигации' row via row order, not label
    text alone. Verified live 2026-08-31: ~52-55% of the savings portfolio in
    every quarter checked."""
    def _finder(rows):
        savings_idx = next((i for i, r in enumerate(rows) if r and any(
            isinstance(c, str) and c.strip() == NF_SAVINGS_LABEL for c in r if c
        )), None)
        if savings_idx is None:
            return None
        return next((r for r in rows[savings_idx + 1:] if r and any(
            isinstance(c, str) and c.strip() == NF_BONDS_LABEL for c in r if c
        )), None)
    return _fetch_nf_row(
        _finder,
        "NATIONAL_FUND_SAVINGS_BONDS",
        "National Fund savings-portfolio bond holdings (Облигации, the savings-portfolio "
        "occurrence specifically -- NOT the stabilization portfolio's own always-zero "
        "'Облигации' row, disambiguated by row order).",
    )


def fetch_national_fund_equities() -> tuple[list[dict], dict]:
    """National Fund savings-portfolio equity holdings, USD, quarterly.
    Verified live 2026-08-31: unambiguous, single match per vintage (only the
    savings portfolio breaks down by equities)."""
    return _fetch_nf_row(
        lambda rows: _nf_row_by_label(rows, NF_EQUITIES_LABEL),
        "NATIONAL_FUND_EQUITIES",
        "National Fund savings-portfolio equity holdings (Акции).",
    )


def fetch_national_fund_gold() -> tuple[list[dict], dict]:
    """National Fund savings-portfolio gold holdings, USD, quarterly.
    Verified live 2026-08-31: unambiguous, single match per vintage."""
    return _fetch_nf_row(
        lambda rows: _nf_row_by_label(rows, NF_GOLD_LABEL),
        "NATIONAL_FUND_GOLD",
        "National Fund savings-portfolio gold holdings (Алтын / Золото).",
    )


# ---------------------------------------------------------------------------
# GOV_ACCOUNTS_PAYABLE / GOV_ACCOUNTS_RECEIVABLE: state budget arrears --
# found 2026-08-31 in sheets "табл 24 кв" (creditor/accounts-payable) and
# "табл 25 кв" (debtor/accounts-receivable) of the Statistical Bulletin.
# Same multi-year-annual-column layout as SUBVENTIONS_REPUBLICAN (uses
# _fetch_bulletin_annual_row), so only the single latest bulletin is needed.
# NOTE: unlike every other sheet used so far, these two are only published in
# 3 of the 13 currently-listed bulletins (the latest, plus two ~1-year-old
# ones) -- confirmed live via a 13-vintage scan -- but since only the latest
# document is ever used, this doesn't affect the fetcher, only documents (for
# anyone re-verifying) that this specific pair of sheets appears to be
# published quarterly rather than monthly, unlike most of this document
# family. Row matched: '3. Задолженность государственного бюджета (1+2)' --
# the STATE BUDGET total (republican + local combined, rows 1+2 above it),
# not either level alone. Verified live: matched exactly once per sheet.
# ---------------------------------------------------------------------------
BULLETIN_ACCOUNTS_PAYABLE_SHEET_NAME = "табл 24 кв"
BULLETIN_ACCOUNTS_RECEIVABLE_SHEET_NAME = "табл 25 кв"
STATE_BUDGET_ARREARS_TOTAL_LABEL = "3. Задолженность государственного бюджета (1+2)"


def fetch_gov_accounts_payable() -> tuple[list[dict], dict]:
    """State budget accounts payable (creditor arrears), republican + local
    combined, million KZT, annual. Verified live 2026-08-31: 2023 (297,690),
    2024 (610,474), 2025 (1,025,433) million KZT -- a striking ~3.4x rise
    over 2 years, consistent with the run-up in local-budget arrears visible
    in the sheet's own regional breakdown (not extracted here)."""
    return _fetch_bulletin_annual_row(
        BULLETIN_ACCOUNTS_PAYABLE_SHEET_NAME,
        lambda r: any(isinstance(c, str) and c.strip() == STATE_BUDGET_ARREARS_TOTAL_LABEL for c in r if c),
        "GOV_ACCOUNTS_PAYABLE",
        "Million KZT. State budget accounts payable (creditor arrears) -- republican + local "
        "budget arrears combined (rows 1+2 in the source). Annual totals only (calendar-year "
        "reports); the same document's current-year partial-period column is deliberately "
        "excluded to avoid mixing a partial year into an annual series.",
    )


def fetch_gov_accounts_receivable() -> tuple[list[dict], dict]:
    """State budget accounts receivable (debtor arrears), republican + local
    combined, million KZT, annual. Verified live 2026-08-31: 2023
    (1,555,238), 2024 (1,868,100), 2025 (1,359,861) million KZT."""
    return _fetch_bulletin_annual_row(
        BULLETIN_ACCOUNTS_RECEIVABLE_SHEET_NAME,
        lambda r: any(isinstance(c, str) and c.strip() == STATE_BUDGET_ARREARS_TOTAL_LABEL for c in r if c),
        "GOV_ACCOUNTS_RECEIVABLE",
        "Million KZT. State budget accounts receivable (debtor arrears) -- republican + local "
        "budget arrears combined (rows 1+2 in the source). Annual totals only (calendar-year "
        "reports); the same document's current-year partial-period column is deliberately "
        "excluded to avoid mixing a partial year into an annual series.",
    )


# ---------------------------------------------------------------------------
# GOV_FINANCIAL_ASSETS_SOLD: proceeds to the state budget from selling state
# financial assets (equity stakes, securities, property), million KZT,
# year-to-date cumulative -- found 2026-08-31 in sheet "табл 16"
# ("Приобретение и продажа финансовых активов государства"). Same
# multi-document-backfill pattern as CUSTOMS_DUTIES (_fetch_bulletin_row
# doesn't fit directly because this sheet's period phrasing and value-column
# position both differ, so this is a bespoke fetcher). Row matched:
# 'II. Общая сумма поступлений в бюджет от продажи финансовых активов
# государства' (row II -- proceeds from SALES; row I, acquisitions, was not
# used since it was consistently blank/None in every vintage checked -- the
# state apparently hasn't recorded any NEW financial-asset acquisitions in
# this reporting window, a real gap not a parsing failure). Value taken from
# column index 1 ("barlygy" / total state-owned, republican + communal
# combined) -- confirmed by column index 2 + index 3 (republican + communal
# sub-columns) summing exactly to index 1 in all 13 vintages checked.
#
# Period phrasing on this sheet is genuinely two DIFFERENT formats across
# vintages: most say "на январь-{end_month} {year} года" (a Jan-anchored
# range), but the single oldest vintage instead says just "на {month} {year}
# года" (a lone month, no range prefix) -- confirmed live and handled by a
# regex that captures 1 or 2 month tokens and uses the LAST one present as
# the end-month, rather than assuming "январь" is always literally present.
# ---------------------------------------------------------------------------
BULLETIN_FINANCIAL_ASSETS_SHEET_NAME = "табл 16"
FINANCIAL_ASSETS_SOLD_LABEL = "II. Общая сумма поступлений в бюджет от продажи финансовых активов государства"
TABL16_PERIOD_RE = re.compile(r"на\s+(\w+)(?:-(\w+))?\s+(\d{4})\s+года", re.IGNORECASE)


def fetch_gov_financial_assets_sold() -> tuple[list[dict], dict]:
    """Proceeds to the state budget from selling state financial assets
    (equity stakes, securities, property), million KZT, year-to-date
    cumulative. Verified live 2026-08-31: 13 documents parsed, monotonic
    within each year (2025: 192.41 Mar to 4,545.42 Nov; 2026: 27.30 Jan to
    3,394.45 Jun)."""
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_FINANCIAL_ASSETS_SOLD",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )

    today = date.today()
    records: list[dict] = []
    seen_dates: set[str] = set()
    skipped: list[int] = []

    for doc in bulletins:
        file_path = doc["full_text"][0]["document"]
        content = _download(file_path)
        kind, wb = _open_workbook(content, file_path)
        sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        target_sheet = next((s for s in sheet_names if s.strip() == BULLETIN_FINANCIAL_ASSETS_SHEET_NAME), None)
        if target_sheet is None:
            skipped.append(doc["id"])
            continue

        rows = list(_iter_rows(kind, wb, target_sheet))
        period_match = None
        for row in rows:
            for cell in row:
                if isinstance(cell, str):
                    m = TABL16_PERIOD_RE.search(cell)
                    if m:
                        period_match = m
                        break
            if period_match:
                break
        target_row = next((r for r in rows if r and any(
            isinstance(c, str) and c.strip() == FINANCIAL_ASSETS_SOLD_LABEL for c in r if c
        )), None)
        if period_match is None or target_row is None:
            skipped.append(doc["id"])
            continue

        end_month_name = (period_match.group(2) or period_match.group(1)).lower()
        end_month = _ru_month(end_month_name)
        year = int(period_match.group(3))
        value = target_row[1] if len(target_row) > 1 else None
        if end_month is None or value in (None, ""):
            skipped.append(doc["id"])
            continue

        last_day = calendar.monthrange(year, end_month)[1]
        iso_date = f"{year:04d}-{end_month:02d}-{last_day:02d}"
        raw_store.save_raw_bytes(SOURCE, f"GOV_FINANCIAL_ASSETS_SOLD_{iso_date}", today,
                                  "xls" if file_path.lower().endswith(".xls") else "xlsx", content)
        if iso_date in seen_dates:
            continue
        seen_dates.add(iso_date)
        records.append({"date": iso_date, "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_FINANCIAL_ASSETS_SOLD",
                f"WHAT CHANGED: zero of {len(bulletins)} listed bulletin documents could be parsed",
                f"ACTUAL: all skipped, ids: {skipped}",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, "GOV_FINANCIAL_ASSETS_SOLD", today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(bulletins), "n_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "irregular (year-to-date cumulative, roughly monthly)",
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        "dataset_id": f"gov.kz-statistical-bulletin-listing,sheet={BULLETIN_FINANCIAL_ASSETS_SHEET_NAME}",
        "note": (
            f"Built from {len(records)} of {len(bulletins)} listed 'Statistical bulletin' "
            f"documents ({len(skipped)} skipped). Million KZT, state property (republican + "
            "communal combined). YEAR-TO-DATE CUMULATIVE, resets near zero each January. "
            "Specifically proceeds from SELLING state financial assets (row II); the "
            "corresponding row I, new ACQUISITIONS, was consistently blank in every vintage "
            "checked -- a real gap in the source, not a parsing omission. Document TITLES are "
            "NOT used to determine period -- only each document's own internal period text is "
            "trusted."
        ),
    }
    return records, manifest


# ---------------------------------------------------------------------------
# GOV_AUDIT_VIOLATIONS_AMOUNT: total amount of financial violations detected
# by the Committee for Internal State Audit (Ministry of Finance), million
# KZT, year-to-date cumulative -- found 2026-08-31 in sheet "28 табл" (note
# the reversed numbering -- "28 табл" not "табл 28" -- confirmed a stable
# quirk of this specific sheet's name, present in all 13 vintages). A
# compliance/anti-corruption metric, structurally unlike any other minfin
# indicator so far. Row matched: 'сумма выявленных нарушений, всего' (total
# amount of detected violations); value at a FIXED column index (2), unlike
# _fetch_bulletin_row's "second-to-last column" convention -- confirmed
# stable in all 13 vintages checked.
#
# Period parsed from the sheet's own Kazakh header text, which uses an
# "as of {month} 1, {year}" convention (e.g. "2026 жылдың 1 шілдесіне" = "as
# of July 1, 2026") DIFFERENT from every other sheet in this file. Confirmed
# via a 13-vintage value scan that this is genuinely YTD CUMULATIVE (2025:
# 18,398 as of Mar 1 (=Jan-Feb) climbing monotonically to 395,858 as of Dec 1
# (=Jan-Nov); resets for 2026: 19,655 as of Feb 1 climbing to 455,695 as of
# Jul 1) -- so "as of month N" is read as covering through the END of month
# N-1. Kazakh month names only mapped for the 10 forms actually observed live
# (қаңтарына/January and мамырына/May never appeared in the current 13-
# document listing) -- an unobserved month name simply causes that one
# document to be skipped (logged, not a hard failure), consistent with this
# file's "never guess a text pattern we haven't verified" discipline.
# ---------------------------------------------------------------------------
BULLETIN_AUDIT_SHEET_NAME = "28 табл"
AUDIT_VIOLATIONS_LABEL = "сумма выявленных нарушений, всего"
AUDIT_AS_OF_RE = re.compile(r"(\d{4})\s*жылдың\s+1\s+([a-zа-яәғқңөұүһі]+)", re.IGNORECASE)
KZ_ASOF_MONTH_TO_NUM = {
    "ақпанына": 2, "наурызына": 3, "сәуіріне": 4, "маусымына": 6, "шілдесіне": 7,
    "тамызына": 8, "қыркүйегіне": 9, "қазанына": 10, "қарашасына": 11, "желтоқсанына": 12,
}


def fetch_gov_audit_violations_amount() -> tuple[list[dict], dict]:
    """Total amount of financial violations detected by Minfin's Committee
    for Internal State Audit, million KZT, year-to-date cumulative. Verified
    live 2026-08-31: 13 documents parsed, monotonic within each year (2025:
    18,398 Feb to 395,858 Nov; 2026: 19,655 Jan to 455,695 Jun)."""
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_AUDIT_VIOLATIONS_AMOUNT",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )

    today = date.today()
    records: list[dict] = []
    seen_dates: set[str] = set()
    skipped: list[int] = []

    for doc in bulletins:
        file_path = doc["full_text"][0]["document"]
        content = _download(file_path)
        kind, wb = _open_workbook(content, file_path)
        sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        target_sheet = next((s for s in sheet_names if s.strip() == BULLETIN_AUDIT_SHEET_NAME), None)
        if target_sheet is None:
            skipped.append(doc["id"])
            continue

        rows = list(_iter_rows(kind, wb, target_sheet))
        period_match = None
        for row in rows:
            for cell in row:
                if isinstance(cell, str):
                    m = AUDIT_AS_OF_RE.search(cell)
                    if m:
                        period_match = m
                        break
            if period_match:
                break
        target_row = next((r for r in rows if r and any(
            isinstance(c, str) and c.strip() == AUDIT_VIOLATIONS_LABEL for c in r if c
        )), None)
        if period_match is None or target_row is None:
            skipped.append(doc["id"])
            continue

        as_of_month = KZ_ASOF_MONTH_TO_NUM.get(period_match.group(2).lower())
        year = int(period_match.group(1))
        value = target_row[2] if len(target_row) > 2 else None
        if as_of_month is None or value in (None, ""):
            skipped.append(doc["id"])
            continue

        covered_month = as_of_month - 1
        covered_year = year
        if covered_month == 0:
            covered_month = 12
            covered_year -= 1
        last_day = calendar.monthrange(covered_year, covered_month)[1]
        iso_date = f"{covered_year:04d}-{covered_month:02d}-{last_day:02d}"
        raw_store.save_raw_bytes(SOURCE, f"GOV_AUDIT_VIOLATIONS_AMOUNT_{iso_date}", today,
                                  "xls" if file_path.lower().endswith(".xls") else "xlsx", content)
        if iso_date in seen_dates:
            continue
        seen_dates.add(iso_date)
        records.append({"date": iso_date, "value": float(value)})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_AUDIT_VIOLATIONS_AMOUNT",
                f"WHAT CHANGED: zero of {len(bulletins)} listed bulletin documents could be parsed",
                f"ACTUAL: all skipped, ids: {skipped}",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, "GOV_AUDIT_VIOLATIONS_AMOUNT", today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(bulletins), "n_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "irregular (year-to-date cumulative, roughly monthly)",
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        "dataset_id": f"gov.kz-statistical-bulletin-listing,sheet={BULLETIN_AUDIT_SHEET_NAME}",
        "note": (
            f"Built from {len(records)} of {len(bulletins)} listed 'Statistical bulletin' "
            f"documents ({len(skipped)} skipped). Million KZT. Total amount of financial "
            "violations detected by Minfin's Committee for Internal State Audit through on-site "
            "audits, YEAR-TO-DATE CUMULATIVE, resets near zero each January. Source header reads "
            "'as of {month} 1' (e.g. 'as of July 1' for a document covering January-June); "
            "stamped here at the END of the month BEFORE the stated 'as of' month. Document "
            "TITLES are NOT used to determine period -- only each document's own internal period "
            "text is trusted."
        ),
    }
    return records, manifest


# ---------------------------------------------------------------------------
# TAX_ARREARS_TOTAL: total overdue tax and payment debt owed TO the republican
# budget ("недоимка"), million KZT, annual point-in-time (as of Jan 1) --
# found 2026-08-31 in sheet "табл 26 пг". Genuinely NEW: distinct from
# GOV_ACCOUNTS_RECEIVABLE (money the budget itself owes/is owed in settlement
# terms) -- this is specifically unpaid tax and fee debt from taxpayers.
# Two-column "as of Jan 1 {prior year}" / "as of Jan 1 {current year}" layout
# (plus a deviation column, correctly excluded since it has no year in its
# header), present in ALL 13 vintages with a stable row structure, though
# only the latest document is used (_fetch_bulletin_annual_row pattern) since
# each vintage's "current year" column is simply more up to date than the
# last. Row matched by an EXACT (not substring) match on 'БАРЛЫҒЫ' to avoid
# the sheet's several SUBTOTAL rows that also contain 'БАРЛЫҒЫ' as part of a
# longer compound label (e.g. 'Салықтық түсімдер, БАРЛЫҒЫ' = tax-revenue
# subtotal) -- confirmed the grand-total row is the only row where the WHOLE
# first cell, after stripping, equals just 'БАРЛЫҒЫ'.
# ---------------------------------------------------------------------------
BULLETIN_TAX_ARREARS_SHEET_NAME = "табл 26 пг"
TAX_ARREARS_TOTAL_LABEL = "БАРЛЫҒЫ"
AS_OF_JAN1_HEADER_RE = re.compile(r"на\s+1\s+января\s+(\d{4})\s+года", re.IGNORECASE)


def fetch_tax_arrears_total() -> tuple[list[dict], dict]:
    """Total overdue tax/payment debt owed to the republican budget
    ('недоимка'), million KZT, as of January 1 each year. Verified live
    2026-08-31: 434,785 (as of 2025-01-01) to 522,067 (as of 2026-01-01)
    million KZT."""
    return _fetch_bulletin_annual_row(
        BULLETIN_TAX_ARREARS_SHEET_NAME,
        lambda r: isinstance(r[0], str) and r[0].strip() == TAX_ARREARS_TOTAL_LABEL,
        "TAX_ARREARS_TOTAL",
        "Million KZT. Total overdue tax and payment debt ('недоимка') owed to the republican "
        "budget by taxpayers, as of January 1 of the stated year -- distinct from "
        "GOV_ACCOUNTS_RECEIVABLE (which covers the budget's own settlement-level arrears, not "
        "unpaid taxpayer debt). Point-in-time snapshot, not a flow.",
        header_re=AS_OF_JAN1_HEADER_RE,
        date_for_year=lambda year: f"{year:04d}-01-01",
    )


# ---------------------------------------------------------------------------
# PENSION_CONTRIBUTIONS_RECEIVED / PENSION_CONTRIBUTIONS_ARREARS: found
# 2026-08-31 in sheet "табл 27 пг" ("Receipts and arrears on mandatory
# pension contributions to the accumulative pension fund"), a national-total
# summary row ('Жиыны'/'Итого') sitting above the sheet's own by-region
# breakdown. Genuinely NEW pension-system indicators, present in all 13
# vintages (only the latest is used).
#
# IMPORTANT structural wrinkle NOT shared by any other annual-column sheet in
# this file: the same two years (e.g. 2025, 2026) appear TWICE in the header
# row -- once for the "Поступления" (receipts) column pair, once for the
# "Задолженность" (arrears) column pair -- because both concepts share the
# same as-of-Jan-1 dating. A naive single-pass "match every year cell" loop
# (as used by _fetch_bulletin_annual_row) would silently produce TWO records
# with the same date but different values for the same indicator, corrupting
# the series -- so this uses bespoke logic instead: collect ALL (col_idx,
# year) matches in the header row IN ORDER, then take the FIRST half for
# receipts and the SECOND half for arrears (confirmed live: matches always
# come as [receipts_year1, receipts_year2, arrears_year1, arrears_year2], in
# that left-to-right column order, matching the sheet's own header layout).
# ---------------------------------------------------------------------------
BULLETIN_PENSION_SHEET_NAME = "табл 27 пг"
PENSION_TOTAL_LABEL = "Жиыны"


AS_OF_FIRST_OF_MONTH_RE = re.compile(r"на\s+1\s+([а-яё]+)\s+(\d{4})\s+года", re.IGNORECASE)
PENSION_MAX_EDITIONS = 8


def _pension_table(content: bytes, file_path: str, indicator_id: str) -> tuple[list, list] | None:
    """(header_row, total_row) of sheet 'табл 27 пг', or None when the workbook has no such
    sheet. The header carries the two as-of dates the table is built for."""
    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    target_sheet = next((s for s in sheet_names if s.strip() == BULLETIN_PENSION_SHEET_NAME), None)
    if target_sheet is None:
        return None
    rows = list(_iter_rows(kind, wb, target_sheet))
    header_row = next((r for r in rows if r and any(isinstance(c, str) and AS_OF_FIRST_OF_MONTH_RE.search(c) for c in r if c)), None)
    total_row = next((r for r in rows if r and isinstance(r[0], str) and r[0].strip() == PENSION_TOTAL_LABEL), None)
    if header_row is None or total_row is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: could not find header row (as-of-1st-of-month year labels) or the total row",
                f"ACTUAL: header_row found={header_row is not None}, total_row found={total_row is not None}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path} and update scripts/fetchers/minfin.py",
            ])
        )
    return header_row, total_row


def _pension_records(header_row: list, total_row: list, column_half: str, indicator_id: str) -> tuple[list[dict], set[str]]:
    """Records for one column pair of the table and the set of months its header names."""
    year_matches = [(i, AS_OF_FIRST_OF_MONTH_RE.search(c)) for i, c in enumerate(header_row)
                    if isinstance(c, str) and AS_OF_FIRST_OF_MONTH_RE.search(c)]
    if len(year_matches) != 4:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: expected exactly 4 as-of-date header cells (2 for receipts, 2 for "
                f"arrears), found {len(year_matches)}: {[(i, m.group(0)) for i, m in year_matches]}",
                "ACTION REQUIRED: inspect the sheet layout and update scripts/fetchers/minfin.py",
            ])
        )
    months = {m.group(1).lower() for _, m in year_matches}
    half = year_matches[:2] if column_half == "first" else year_matches[2:]
    records = []
    for col_idx, m in half:
        value = total_row[col_idx] if col_idx < len(total_row) else None
        if value in (None, ""):
            continue
        records.append({"date": f"{int(m.group(2)):04d}-01-01", "value": float(value)})
    records.sort(key=lambda r: r["date"])
    return records, months


def _fetch_pension_row(column_half: str, indicator_id: str, note: str) -> tuple[list[dict], dict]:
    """Table 27 is rebuilt twice a year, not with every bulletin: the editions published
    from about February to July carry the figures as of 1 JANUARY (the annual series these
    indicators are), the editions from August on carry the figures as of 1 JULY (half-year
    receipts, mid-year arrears). Seen 2026-09-04: the 'as of August 1, 2026' bulletin
    switched the table to 1 July while the 'as of July 1, 2026' one still had 1 January.
    The bulletin title says nothing about which; so the editions are opened newest-first
    and the first whose table 27 is dated 1 January is used -- the 1-July figures are not
    stored (a half-year variant would be a separate indicator, not this one)."""
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )
    seen: list[tuple[str, str]] = []
    for doc in bulletins[:PENSION_MAX_EDITIONS]:
        file_path = doc["full_text"][0]["document"]
        content = _download(file_path)
        table = _pension_table(content, file_path, indicator_id)
        if table is None:
            seen.append((str(doc.get("title"))[:40], "no table 27"))
            continue
        records, months = _pension_records(*table, column_half, indicator_id)
        if months == {"января"}:
            today = date.today()
            ext = "xls" if file_path.lower().endswith(".xls") else "xlsx"
            raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
            raw_store.write_download_manifest(SOURCE, indicator_id, today, {
                "downloaded_at": datetime.now().isoformat(),
                "source_document_id": doc["id"], "source_title": doc.get("title"),
                "source_url": GOV_KZ_BASE + file_path,
                "editions_skipped": seen,
            })
            manifest = {
                "frequency": "annual",
                "source_url": GOV_KZ_BASE + file_path,
                "dataset_id": f"gov.kz-doc-{doc['id']},sheet={BULLETIN_PENSION_SHEET_NAME}",
                "note": note + (f" Newer editions skipped because their table 27 is dated mid-year: {seen}." if seen else ""),
            }
            return records, manifest
        seen.append((str(doc.get("title"))[:40], "/".join(sorted(months))))
    raise validation.StructuralChangeError(
        "\n".join([
            f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
            f"WHAT CHANGED: none of the {len(seen)} newest bulletins carries table 27 dated 1 January",
            f"ACTUAL: {seen}",
            "EXPECTED: the February–July editions carry the 1-January figures; if the table's dating "
            "convention changed, decide whether the indicator becomes semi-annual",
            "ACTION REQUIRED: inspect the bulletins and update scripts/fetchers/minfin.py",
        ])
    )


def fetch_pension_contributions_received() -> tuple[list[dict], dict]:
    """National total mandatory pension contributions (ОПВ/МЗА) received by
    the accumulative pension fund, million KZT, as of January 1 each year.
    Verified live 2026-08-31: 2,448,612.87 (2025) to 2,548,511.48 (2026)
    million KZT."""
    return _fetch_pension_row(
        "first", "PENSION_CONTRIBUTIONS_RECEIVED",
        "Million KZT. National total mandatory pension contributions (ОПВ/МЗА) received by the "
        "accumulative pension fund, as of January 1 of the stated year (cumulative receipts to "
        "that date). Sum across all regions.",
    )


def fetch_pension_contributions_arrears() -> tuple[list[dict], dict]:
    """National total arrears (unpaid mandatory pension contributions) owed
    to the accumulative pension fund, million KZT, as of January 1 each year.
    Verified live 2026-08-31: 3,287,315.70 (2025) to 4,486,885.77 (2026)
    million KZT."""
    return _fetch_pension_row(
        "second", "PENSION_CONTRIBUTIONS_ARREARS",
        "Million KZT. National total arrears (unpaid mandatory pension contributions, ОПВ/МЗА) "
        "owed to the accumulative pension fund, as of January 1 of the stated year. Sum across "
        "all regions.",
    )


# ---------------------------------------------------------------------------
# GOV_PROCUREMENT_TOTAL_VALUE: total value of concluded state procurement
# contracts, million KZT, annual -- found 2026-08-31 in sheet "табл 29 пг"
# ("Information on state procurement for {year}"). Structurally different
# from every other sheet used so far: it's published only once a FULL
# calendar year has closed (present in just 3 of the 13 currently-listed
# bulletins, covering only 2 distinct years -- 2024 and 2025 -- confirmed via
# a 13-vintage scan; the other 10 bulletins simply lack this sheet). Uses the
# CUSTOMS_DUTIES-style multi-document iteration (not the single-latest-
# document annual pattern) because the target YEAR itself changes between
# vintages, unlike SUBVENTIONS_REPUBLICAN-style sheets where one document
# already contains all needed years as separate columns. Row matched: 'ВСЕГО'
# (grand total across all procurement methods). Value taken from the
# "Сумма заключенных договоров" (concluded contracts sum) column, which the
# sheet's own header states is in raw ТЕҢГЕ, not million tenge like every
# other sheet in this file -- converted /1,000,000 here for unit consistency
# with the rest of the dataset. A separate "economy/savings" column exists in
# the same row but was NOT extracted: its header states it's in million tenge
# (a different unit than the value columns in the same row), and mixing that
# ambiguity into this indicator risked a units error -- left for a future,
# more careful pass rather than guessed at now.
# ---------------------------------------------------------------------------
BULLETIN_PROCUREMENT_SHEET_NAME = "табл 29 пг"
PROCUREMENT_YEAR_RE = re.compile(r"закупках\s+за\s+(\d{4})\s+год", re.IGNORECASE)
PROCUREMENT_TOTAL_LABEL = "ВСЕГО"


def fetch_gov_procurement_total_value() -> tuple[list[dict], dict]:
    """Total value of concluded state procurement contracts, million KZT,
    annual. Verified live 2026-08-31: only 2 distinct years available across
    the 13 listed bulletins (this sheet is published once per closed year,
    not monthly) -- 2024: 7,296,933.87; 2025: 8,141,829.16 million KZT."""
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_PROCUREMENT_TOTAL_VALUE",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "EXPECTED: at least one 'Statistical bulletin as of ...' document",
                "ACTUAL: not found in the current listing",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
            ])
        )

    today = date.today()
    records_by_year: dict[int, dict] = {}
    skipped: list[int] = []

    for doc in bulletins:
        file_path = doc["full_text"][0]["document"]
        content = _download(file_path)
        kind, wb = _open_workbook(content, file_path)
        sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        target_sheet = next((s for s in sheet_names if s.strip() == BULLETIN_PROCUREMENT_SHEET_NAME), None)
        if target_sheet is None:
            skipped.append(doc["id"])
            continue

        rows = list(_iter_rows(kind, wb, target_sheet))
        year_match = None
        for row in rows:
            for cell in row:
                if isinstance(cell, str):
                    m = PROCUREMENT_YEAR_RE.search(cell)
                    if m:
                        year_match = m
                        break
            if year_match:
                break
        target_row = next((r for r in rows if r and isinstance(r[0], str) and r[0].strip() == PROCUREMENT_TOTAL_LABEL), None)
        if year_match is None or target_row is None:
            skipped.append(doc["id"])
            continue

        year = int(year_match.group(1))
        value = target_row[5] if len(target_row) > 5 else None
        if value in (None, ""):
            skipped.append(doc["id"])
            continue

        iso_date = f"{year:04d}-12-31"
        raw_store.save_raw_bytes(SOURCE, f"GOV_PROCUREMENT_TOTAL_VALUE_{iso_date}", today,
                                  "xls" if file_path.lower().endswith(".xls") else "xlsx", content)
        if iso_date not in records_by_year:
            records_by_year[iso_date] = {"date": iso_date, "value": float(value) / 1_000_000.0}

    records = list(records_by_year.values())
    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                "STRUCTURAL CHANGE DETECTED in minfin/GOV_PROCUREMENT_TOTAL_VALUE",
                f"WHAT CHANGED: zero of {len(bulletins)} listed bulletin documents could be parsed",
                f"ACTUAL: all skipped, ids: {skipped}",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    raw_store.write_download_manifest(SOURCE, "GOV_PROCUREMENT_TOTAL_VALUE", today, {
        "downloaded_at": datetime.now().isoformat(),
        "n_documents_listed": len(bulletins), "n_years_parsed": len(records), "skipped_document_ids": skipped,
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
    })

    records.sort(key=lambda r: r["date"])
    manifest = {
        "frequency": "annual",
        "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        "dataset_id": f"gov.kz-statistical-bulletin-listing,sheet={BULLETIN_PROCUREMENT_SHEET_NAME}",
        "note": (
            f"Built from {len(records)} distinct year(s) found across {len(bulletins)} listed "
            f"'Statistical bulletin' documents ({len(skipped)} skipped -- missing sheet, most "
            "commonly because this sheet is only published once a full calendar year has "
            "closed, not monthly like most other sheets). Million KZT (converted from the "
            "source's raw-tenge unit -- this sheet's value columns are NOT in million tenge "
            "like the rest of this document, per its own header text). Total value of concluded "
            "state procurement contracts across all procurement methods (tender, auction, price "
            "quotes, single-source, electronic marketplace). Annual totals only."
        ),
    }
    return records, manifest


# ---------------------------------------------------------------------------
# INDIVIDUAL_INCOME_TAX: found 2026-08-31 in sheet "табл 3" ("Исполнение
# государственного бюджета" -- execution of the STATE budget, i.e. republican
# + local combined) -- and it MATTERS: individual income tax was investigated
# repeatedly earlier this session (see CUSTOMS_DUTIES's and SUBVENTIONS_
# REPUBLICAN's module comments) and consistently found ABSENT from every
# republican-level document (the Dynamics file, табл 8 (дох)) and even the
# broadest CONSOLIDATED-government document checked (табл 13, ultimately not
# connected for unrelated structural reasons) -- correctly concluded to be a
# genuinely local-budget-only tax under Kazakhstan's budget code. табл 3 does
# NOT contradict that: it operates at the STATE budget level specifically
# (republican + local combined, matching the same "state" framing already
# used for GOV_ACCOUNTS_PAYABLE/RECEIVABLE and TAX_ARREARS_TOTAL above), so
# individual income tax legitimately appears here as a real, non-zero,
# distinct line -- consistent with it being collected AT the local level but
# rolled up INTO the state-level aggregate. Cross-checked against табл 7
# ("Исполнение РЕСПУБЛИКАНСКОГО бюджета" specifically): no individual-income-
# tax row appears there at all, confirming republican-level absence still
# holds and табл 3's figure is genuinely state-level, not a contradiction.
# Property tax was searched for in the same табл 3 tax breakdown and was NOT
# found itemized here either -- that specific question remains open.
#
# Same multi-year-annual-column layout as SUBVENTIONS_REPUBLICAN/
# GOV_ACCOUNTS_PAYABLE (uses _fetch_bulletin_annual_row with its default
# 'YYYY ж. есеп' header and Dec-31 dating), so only the single latest
# bulletin is needed.
# ---------------------------------------------------------------------------
BULLETIN_STATE_BUDGET_SHEET_NAME = "табл 3"
INDIVIDUAL_INCOME_TAX_LABEL = "индивидуальный подоходный налог"
STATE_BUDGET_REVENUE_LABEL = "I. ДОХОДЫ"
STATE_BUDGET_EXPENDITURE_LABEL = "II. ЗАТРАТЫ"
STATE_BUDGET_DEFICIT_LABEL = "V. ДЕФИЦИТ (ПРОФИЦИТ) БЮДЖЕТА"
STATE_NON_OIL_DEFICIT_LABEL = "VI. НЕНЕФТЯНОЙ ДЕФИЦИТ (ПРОФИЦИТ) БЮДЖЕТА"


def _state_budget_row_matcher(label: str):
    return lambda r: any(isinstance(c, str) and c.strip() == label for c in r if c)


def fetch_individual_income_tax() -> tuple[list[dict], dict]:
    """Individual income tax revenue, STATE budget (republican + local
    combined), million KZT, annual. Verified live 2026-08-31: 1,992,384.85
    (2023) to 2,859,192.36 (2025) million KZT -- resolves a question left
    open earlier this session: this tax IS collectible at the state level,
    just not the republican level, where every prior document searched
    (Dynamics file, табл 8 (дох), the broader табл 13) correctly found it
    absent."""
    return _fetch_bulletin_annual_row(
        BULLETIN_STATE_BUDGET_SHEET_NAME,
        _state_budget_row_matcher(INDIVIDUAL_INCOME_TAX_LABEL),
        "INDIVIDUAL_INCOME_TAX",
        "Million KZT. Individual (personal) income tax revenue, STATE budget (republican + "
        "local government combined) -- NOT available at the republican-budget-only level "
        "(confirmed absent from GOV_REVENUE/TAX_REVENUE's source and табл 7's republican-only "
        "breakdown); this is the local-government-collected portion rolled up into the state "
        "total, per Kazakhstan's budget code assigning this tax to local budgets.",
    )


def fetch_state_budget_revenue() -> tuple[list[dict], dict]:
    """Total revenue, STATE budget (republican + local combined), million
    KZT, annual -- broader in scope than GOV_REVENUE (republican-budget-only,
    from the separate 'Dynamics of execution' file). Verified live
    2026-08-31: 24,917,246.14 (2023) to 29,871,047.82 (2025) million KZT."""
    return _fetch_bulletin_annual_row(
        BULLETIN_STATE_BUDGET_SHEET_NAME,
        _state_budget_row_matcher(STATE_BUDGET_REVENUE_LABEL),
        "STATE_BUDGET_REVENUE",
        "Million KZT. Total revenue, STATE budget (republican + local government budgets "
        "combined) -- broader scope than GOV_REVENUE, which is republican-budget-only.",
    )


def fetch_state_budget_expenditure() -> tuple[list[dict], dict]:
    """Total expenditure, STATE budget (republican + local combined), million
    KZT, annual -- broader in scope than GOV_EXPENDITURE. Verified live
    2026-08-31: 26,760,000.29 (2023) to 33,442,828.77 (2025) million KZT."""
    return _fetch_bulletin_annual_row(
        BULLETIN_STATE_BUDGET_SHEET_NAME,
        _state_budget_row_matcher(STATE_BUDGET_EXPENDITURE_LABEL),
        "STATE_BUDGET_EXPENDITURE",
        "Million KZT. Total expenditure, STATE budget (republican + local government budgets "
        "combined) -- broader scope than GOV_EXPENDITURE, which is republican-budget-only.",
    )


def fetch_state_budget_deficit() -> tuple[list[dict], dict]:
    """State budget deficit (surplus), STATE budget (republican + local
    combined), million KZT, annual. Negative = deficit, matching the
    source's own sign convention. Broader in scope than BUDGET_DEFICIT
    (republican-only). Verified live 2026-08-31: -2,811,100.59 (2023) to
    -4,383,871.07 (2025) million KZT."""
    return _fetch_bulletin_annual_row(
        BULLETIN_STATE_BUDGET_SHEET_NAME,
        _state_budget_row_matcher(STATE_BUDGET_DEFICIT_LABEL),
        "STATE_BUDGET_DEFICIT",
        "Million KZT. State budget deficit (surplus), STATE budget (republican + local "
        "government budgets combined) -- broader scope than BUDGET_DEFICIT, which is "
        "republican-budget-only. Negative values indicate a deficit.",
    )


def fetch_state_non_oil_deficit() -> tuple[list[dict], dict]:
    """State non-oil budget deficit (surplus), STATE budget (republican +
    local combined), million KZT, annual -- broader in scope than
    NON_OIL_BUDGET_DEFICIT (republican-only). Verified live 2026-08-31:
    -8,454,245.45 (2023) to -11,393,479.39 (2025) million KZT."""
    return _fetch_bulletin_annual_row(
        BULLETIN_STATE_BUDGET_SHEET_NAME,
        _state_budget_row_matcher(STATE_NON_OIL_DEFICIT_LABEL),
        "STATE_NON_OIL_DEFICIT",
        "Million KZT. State non-oil budget deficit (surplus), STATE budget (republican + local "
        "government budgets combined) -- broader scope than NON_OIL_BUDGET_DEFICIT, which is "
        "republican-budget-only. Negative values indicate a deficit.",
    )


# ---------------------------------------------------------------------------
# PROPERTY_TAX / LAND_TAX: found 2026-08-31 in sheet "табл 4" ("Поступления в
# ГОСУДАРСТВЕННЫЙ бюджет" -- receipts to the STATE budget, republican + local
# combined, the same "state" scope as табл 3's INDIVIDUAL_INCOME_TAX above).
# This resolves the property-tax half of the question left open by
# INDIVIDUAL_INCOME_TAX's discovery -- табл 3's simplified tax breakdown
# didn't itemize property tax, but табл 4's full KBK-code-level classification
# (the state-budget counterpart to табл 8 (дох), which is republican-only)
# does.
#
# IMPORTANT data-quality finding: the RUSSIAN label for property tax
# ('Налоги на имущество') is UNRELIABLE for matching across vintages --
# confirmed live that in several older documents (e.g. doc 928644, "as of
# November 1, 2025") the source spreadsheet itself renders this word as
# 'Hалоги на имущество', using a LATIN 'H' instead of the correct Cyrillic
# 'Н' -- a genuine copy-paste artifact in Minfin's own template, not a
# rendering issue on this end (confirmed by inspecting the raw string).
# Matching this label directly returned 0/13 matches in most vintages. Fixed
# by matching on the KAZAKH label ('Мүлiкке салынатын салықтар') at its
# fixed column position (index 4) instead, which is byte-identical across
# all 13 vintages and gives exactly 1 match each -- confirmed live values
# form a genuine year-to-date cumulative series (monotonic within each year,
# resetting each January), the same pattern as CUSTOMS_DUTIES. LAND_TAX uses
# the same Kazakh-label strategy for consistency, even though its Russian
# label ('Земельный налог') did NOT show the H/Н issue -- matched twice per
# vintage (a category-aggregate row and its single specific sub-item row,
# confirmed to always carry an IDENTICAL value in every vintage checked, so
# matching either is safe; the Kazakh-label-at-fixed-index approach picks the
# first, the aggregate row, deterministically).
# ---------------------------------------------------------------------------
BULLETIN_STATE_REVENUE_SHEET_NAME = "табл 4"
PROPERTY_TAX_KZ_LABEL = "Мүлiкке салынатын салықтар"
LAND_TAX_KZ_LABEL = "Жер салығы"


def fetch_property_tax() -> tuple[list[dict], dict]:
    """Property tax revenue, STATE budget (republican + local combined),
    million KZT, year-to-date cumulative. Verified live 2026-08-31: 13
    documents parsed, monotonic within each year (2025: 152,083.55 Feb to
    658,288.76 Nov; 2026: 3,311.46 Jan to 263,237.87 Jun)."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_REVENUE_SHEET_NAME,
        lambda r: len(r) > 4 and isinstance(r[4], str) and r[4].strip() == PROPERTY_TAX_KZ_LABEL,
        "PROPERTY_TAX",
        value_col=5,
    )


def fetch_land_tax() -> tuple[list[dict], dict]:
    """Land tax revenue, STATE budget (republican + local combined), million
    KZT, year-to-date cumulative. Verified live 2026-08-31: 13 documents
    parsed, monotonic within each year (2025: 3,867.96 Feb to 16,702.83 Nov;
    2026: 274.37 Jan to 5,038.71 Jun)."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_REVENUE_SHEET_NAME,
        lambda r: len(r) > 4 and isinstance(r[4], str) and r[4].strip() == LAND_TAX_KZ_LABEL,
        "LAND_TAX",
        value_col=5,
    )


# ---------------------------------------------------------------------------
# STATE_GOV_WAGES_EXPENDITURE / _CAPITAL_EXPENDITURE / _SUBSIDIES_EXPENDITURE:
# found 2026-08-31 in sheet "табл 6" ("Исполнение ГОСУДАРСТВЕННОГО бюджета по
# экономической классификации расходов" -- STATE budget expenditure by
# economic classification), the STATE-level (republican + local combined)
# counterpart to both GOV_*_EXPENDITURE (табл 10, republican-only) and
# LOCAL_GOV_*_EXPENDITURE (таб 11, local-only). Same three row labels
# ('Заработная плата', 'Капитальные затраты', 'Бюджетные субсидии'), each
# matched exactly once across all 13 vintages. Unlike табл 10, no separate
# 'Пенсии' row exists in this sheet either (like the local-budget sheet), so
# no STATE_GOV_PENSIONS_EXPENDITURE was added.
# ---------------------------------------------------------------------------
BULLETIN_STATE_ECONOMIC_SHEET_NAME = "табл 6"


def fetch_state_gov_wages_expenditure() -> tuple[list[dict], dict]:
    """State budget wages expenditure ('Заработная плата'), million KZT,
    year-to-date cumulative. Verified live 2026-08-31: 13 documents parsed,
    exactly one matching row in each."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Заработная плата",
        "STATE_GOV_WAGES_EXPENDITURE",
    )


def fetch_state_gov_capital_expenditure() -> tuple[list[dict], dict]:
    """State budget capital expenditure ('Капитальные затраты'), million
    KZT, year-to-date cumulative. Verified live 2026-08-31: 13 documents
    parsed, exactly one matching row in each."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Капитальные затраты",
        "STATE_GOV_CAPITAL_EXPENDITURE",
    )


def fetch_state_gov_subsidies_expenditure() -> tuple[list[dict], dict]:
    """State budget budgetary subsidies ('Бюджетные субсидии'), million KZT,
    year-to-date cumulative. Verified live 2026-08-31: 13 documents parsed,
    exactly one matching row in each."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_ECONOMIC_SHEET_NAME,
        lambda r: r[-1] == "Бюджетные субсидии",
        "STATE_GOV_SUBSIDIES_EXPENDITURE",
    )


# ---------------------------------------------------------------------------
# Government debt STRUCTURE: Statistical Bulletin sheet "табл 22 кв"
# ("Государственный и гарантированный государством долг Республики Казахстан,
# долг по поручительствам государства"), found 2026-09-01 by enumerating all 49
# sheets of the latest bulletin and diffing them against the sheets this module
# already mines.
#
# Layout differs from every other bulletin sheet used here: it is a WIDE
# point-in-time time series -- one column PAIR per reporting date (млн тенге,
# then млн долл. США), 22 dates from 2020-01-01 to 2026-07-01 in the current
# vintage -- rather than a year-to-date column per bulletin edition.
#
# Row codes ARE NOT UNIQUE across the sheet: "1" and "2" appear both under
# section I (government / National Bank debt) and again under sections II and
# III as their internal/external split. Matching on the code alone would
# silently pick the wrong row, so every lookup here is anchored to its section
# ("I.", "II.", "III.") and additionally verified against an expected Russian
# label before use.
#
# The sheet's own arithmetic was verified against it at 2026-07-01 before
# connecting anything:
#   1.1 + 1.2 = 28,471,879.43 + 8,352,366.46 = 36,824,245.89 = row "1"
#   I. + II. + III. = 38,495,061.56 + 2,414,476.28 + 6,000 = 40,915,537.84,
#   which equals the sheet's own "Всего" row AND the already-connected GOV_DEBT
#   series exactly -- so these are components of GOV_DEBT, not a duplicate of it.
# Note I. is NOT simply 1+2+3: the sheet's footnote 1 states it excludes mutual
# claims, and subtracting row 3.1 (local-government debt owed to the Government,
# 1,101,375.43) from 1+2+3 reproduces I. exactly.
# ---------------------------------------------------------------------------
DEBT_STRUCTURE_SHEET_PREFIX = "табл 22"
DEBT_DATE_RE = re.compile(r"на\s+1\s+(\w+)\s+(\d{4})", re.IGNORECASE)
DEBT_MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
               "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
DEBT_SECTIONS = ("I.", "II.", "III.")


def _fetch_debt_structure_row(section: str, row_code: str, russian_marker: str,
                              indicator_id: str, note: str,
                              currency: str = "KZT") -> tuple[list[dict], dict]:
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no bulletin document under directions={BUDGET_DIRECTION_ID}",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
            ])
        )
    doc = bulletins[0]
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)

    today = date.today()
    ext = "xls" if file_path.lower().endswith(".xls") else "xlsx"
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_document_id": doc["id"], "source_title": doc.get("title"),
        "source_url": GOV_KZ_BASE + file_path,
    })

    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    target_sheet = next((s for s in sheet_names if s.strip().startswith(DEBT_STRUCTURE_SHEET_PREFIX)), None)
    if target_sheet is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no sheet starting with {DEBT_STRUCTURE_SHEET_PREFIX!r}",
                f"ACTUAL sheets: {sheet_names}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    rows = list(_iter_rows(kind, wb, target_sheet))

    # Date header: the row carrying the most "на 1 <month> <year>" cells.
    date_row_idx, date_cols = -1, {}
    for i, r in enumerate(rows[:20]):
        found = {}
        for j, c in enumerate(r):
            if isinstance(c, str):
                m = DEBT_DATE_RE.search(c)
                if m and m.group(1).lower() in DEBT_MONTHS:
                    found[j] = (int(m.group(2)), DEBT_MONTHS[m.group(1).lower()])
        if len(found) > len(date_cols):
            date_row_idx, date_cols = i, found
    if len(date_cols) < 4:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: fewer than 4 date columns in sheet {target_sheet!r}",
                f"ACTUAL: {len(date_cols)} found",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    # Unit row sits directly under the dates; each date has a KZT column then a USD column.
    unit_row = rows[date_row_idx + 1] if date_row_idx + 1 < len(rows) else []

    def unit_at(idx):
        cell = unit_row[idx] if idx < len(unit_row) else None
        return cell.lower() if isinstance(cell, str) else ""

    # Locate the requested row: anchored inside its section, never by code alone.
    section_start = next((i for i, r in enumerate(rows)
                          if r and str(r[0]).strip() == section), None)
    if section_start is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: section anchor {section!r} not found in column 0",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )
    later = [i for i, r in enumerate(rows)
             if i > section_start and r and str(r[0]).strip() in DEBT_SECTIONS]
    section_end = later[0] if later else len(rows)

    target_row, target_idx = None, None
    scan = [section_start] if row_code == section else range(section_start, section_end)
    for i in scan:
        if rows[i] and str(rows[i][0]).strip() == row_code:
            target_row, target_idx = rows[i], i
            break
    if target_row is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: row code {row_code!r} not found inside section {section!r} "
                f"(rows {section_start}..{section_end})",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    # Structural guard: the row must still carry its expected Russian label.
    russian_text = " ".join(str(c) for c in target_row if isinstance(c, str))
    if russian_marker.lower() not in russian_text.lower():
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: row {row_code!r} in section {section!r} (sheet row {target_idx}) no longer "
                f"contains the expected label {russian_marker!r}",
                f"ACTUAL text: {russian_text[:200]!r}",
                "EXPECTED: row codes may have been re-ordered -- the code alone is not trusted",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    want_usd = currency.upper() == "USD"
    records = []
    for col, (year, month) in sorted(date_cols.items()):
        idx = col + 1 if want_usd else col
        u = unit_at(idx)
        if want_usd and "долл" not in u:
            continue
        if not want_usd and ("теңге" not in u and "тенге" not in u):
            continue
        value = target_row[idx] if idx < len(target_row) else None
        if value in (None, ""):
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        records.append({"date": f"{year:04d}-{month:02d}-01", "value": v})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no {currency} values parsed for row {row_code!r} in section {section!r}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    records.sort(key=lambda r: r["date"])
    return records, {
        "frequency": "quarterly",
        "source_url": GOV_KZ_BASE + file_path,
        "dataset_id": f"statistical-bulletin/{target_sheet}/section={section},row={row_code},currency={currency}",
        "note": note,
    }


def fetch_state_debt_total() -> tuple[list[dict], dict]:
    """State Debt (million KZT, quarterly)."""
    return _fetch_debt_structure_row(
        "I.", "I.", "Государственный долг",
        "STATE_DEBT_TOTAL",
        "Million KZT. Section I of the bulletin's debt table: state debt (government + National Bank + local executive bodies, net of mutual claims). A COMPONENT of the existing GOV_DEBT, which is I + II + III -- verified: 38,495,061.56 + 2,414,476.28 + 6,000 = 40,915,537.84, exactly GOV_DEBT.",
        currency="KZT",
    )


def fetch_gov_debt_external_usd() -> tuple[list[dict], dict]:
    """Government Debt, External (USD) (USD million, quarterly)."""
    return _fetch_debt_structure_row(
        "I.", "1.2", "внешний",
        "GOV_DEBT_EXTERNAL_USD",
        "USD million. The same external government debt series as GOV_DEBT_EXTERNAL, in the source's own USD column. Consistency checked against the sheet's stated rate: 8,352,366.46 / 485.82 = 17,192.4 against the published 17,192.31.",
        currency="USD",
    )


def fetch_local_gov_debt() -> tuple[list[dict], dict]:
    """Local Government Debt (million KZT, quarterly)."""
    return _fetch_debt_structure_row(
        "I.", "3", "местных исполнительных",
        "LOCAL_GOV_DEBT",
        "Million KZT. Debt of local executive bodies (regional and city administrations), including what they owe the central Government.",
        currency="KZT",
    )


def fetch_state_guaranteed_debt() -> tuple[list[dict], dict]:
    """State-Guaranteed Debt (million KZT, quarterly)."""
    return _fetch_debt_structure_row(
        "II.", "II.", "Гарантированный государством",
        "STATE_GUARANTEED_DEBT",
        "Million KZT. Section II: debt guaranteed by the state -- the sovereign's contingent liabilities, outside state debt proper.",
        currency="KZT",
    )


def fetch_gov_debt_eurobonds() -> tuple[list[dict], dict]:
    """Government Eurobonds (million KZT, quarterly)."""
    return _fetch_debt_structure_row(
        "I.", "1.2.10.", "Еврооблигации",
        "GOV_DEBT_EUROBONDS",
        "Million KZT. Eurobonds within the Government's external debt -- the market-issued portion, as opposed to loans from international financial institutions.",
        currency="KZT",
    )


# ---------------------------------------------------------------------------
# LOCAL budget execution: Statistical Bulletin sheet "табл 12" ("Исполнение
# местных бюджетов"), found 2026-09-01 in the same 49-sheet enumeration that
# produced the debt-structure series. The dataset already covered the
# REPUBLICAN budget in detail but had no measure of the LOCAL budgets, which
# carry most of Kazakhstan's education, housing/utilities and health spending.
#
# Layout is the ordinary "several annual columns in one document" shape, so the
# existing _fetch_bulletin_annual_row is reused unchanged. Its default header
# regex also does the right thing here without special-casing: the sheet's
# current-period column is headed "2026 ж. қантар-маусым есеп" and is skipped
# because 'есеп' is not immediately after the year, while 2025's merged
# "2025 ж. есеп" header sits over the ANNUAL sub-column, so the annual figure
# (17,039,798.7) is taken rather than the January-June one (8,223,337.6) --
# verified live rather than assumed.
#
# Row-matching hazard handled here: a naive substring match for "Налоговые
# поступления" would also match "Неналоговые поступления" if case were ignored,
# and matching "Образование" alone would collide with other rows. Matchers below
# therefore require the numbered/section prefix and can exclude a substring.
#
# Verified identity at 2025: tax 8,725,097.5 + non-tax 425,962.4 + capital sales
# 172,470.9 + special 0 + transfers 7,716,267.9 = 17,039,798.7, exactly the
# sheet's own "I. ДОХОДЫ" row.
# ---------------------------------------------------------------------------
LOCAL_BUDGET_SHEET = "табл 12"


def _row_has(row, must: str, exclude: str | None = None) -> bool:
    for cell in row:
        if isinstance(cell, str) and must in cell:
            if exclude is not None and exclude in cell:
                continue
            return True
    return False


def fetch_local_budget_revenue() -> tuple[list[dict], dict]:
    """Local budgets: total revenue (million KZT, annual)."""
    return _fetch_bulletin_annual_row(
        LOCAL_BUDGET_SHEET,
        lambda r: _row_has(r, "I. ДОХОДЫ"),
        "LOCAL_BUDGET_REVENUE",
        "Million KZT. Total revenue of Kazakhstan's LOCAL budgets (regions and cities), "
        "distinct from the republican budget series. Equals the sum of its own components: "
        "tax + non-tax + capital sales + special + transfers.",
    )


def fetch_local_budget_expenditure() -> tuple[list[dict], dict]:
    """Local budgets: total expenditure (million KZT, annual)."""
    return _fetch_bulletin_annual_row(
        LOCAL_BUDGET_SHEET,
        lambda r: _row_has(r, "II. ЗАТРАТЫ"),
        "LOCAL_BUDGET_EXPENDITURE",
        "Million KZT. Total expenditure of Kazakhstan's LOCAL budgets.",
    )


def fetch_local_budget_tax_revenue() -> tuple[list[dict], dict]:
    """Local budgets: tax revenue (million KZT, annual)."""
    return _fetch_bulletin_annual_row(
        LOCAL_BUDGET_SHEET,
        lambda r: _row_has(r, "Налоговые поступления", exclude="Неналоговые"),
        "LOCAL_BUDGET_TAX_REVENUE",
        "Million KZT. TAX revenue of local budgets. The matcher explicitly excludes the "
        "neighbouring 'Неналоговые поступления' (non-tax) row, which contains the same "
        "substring.",
    )


def fetch_local_budget_transfers() -> tuple[list[dict], dict]:
    """Local budgets: transfers received (million KZT, annual)."""
    return _fetch_bulletin_annual_row(
        LOCAL_BUDGET_SHEET,
        lambda r: _row_has(r, "Поступления трансфертов"),
        "LOCAL_BUDGET_TRANSFERS",
        "Million KZT. Transfers received by local budgets from the republican budget -- "
        "read against LOCAL_BUDGET_REVENUE this is the fiscal-dependence ratio of Kazakhstan's "
        "regions (45% of local revenue in 2025).",
    )


def fetch_local_education_expenditure() -> tuple[list[dict], dict]:
    """Local budgets: education spending (million KZT, annual)."""
    return _fetch_bulletin_annual_row(
        LOCAL_BUDGET_SHEET,
        lambda r: _row_has(r, "4. Образование"),
        "LOCAL_EDUCATION_EXPENDITURE",
        "Million KZT. Education spending from local budgets -- the largest single functional "
        "category of local expenditure (6.31 trillion KZT in 2025, 38% of the total). Matched on "
        "the numbered prefix '4. Образование' so it cannot collide with other rows mentioning "
        "education.",
    )


def fetch_local_housing_utilities_expenditure() -> tuple[list[dict], dict]:
    """Local budgets: housing and utilities spending (million KZT, annual)."""
    return _fetch_bulletin_annual_row(
        LOCAL_BUDGET_SHEET,
        lambda r: _row_has(r, "7. Жилищно-коммунальное хозяйство"),
        "LOCAL_HOUSING_UTILITIES_EXPENDITURE",
        "Million KZT. Housing and communal services spending from local budgets.",
    )


# ---------------------------------------------------------------------------
# BUDGET FINANCING flows: Statistical Bulletin sheets "табл 20 кв" (by sector
# and residency of the counterparty) and "табл 21 кв" (by financial
# instrument), the last two substantive unmined sheets from the 49-sheet
# enumeration.
#
# Layout has two hazards, both handled explicitly:
#
# 1. TWO COLUMN GROUPS side by side. Columns 1..19 are the STATE budget
#    (Мемлекеттік бюджет / Государственный бюджет) and columns 20..38 repeat
#    the identical period layout for the REPUBLICAN budget. Reading a column
#    index without establishing which group it belongs to would silently mix
#    two different budgets. The group boundary is located from the header row
#    rather than hardcoded.
#
# 2. The quarterly columns are PER-QUARTER FLOWS, NOT year-to-date cumulative.
#    This was established, not assumed -- and the obvious "the magnitudes look
#    like the annual columns, so Q4 must be the year total" reading is WRONG.
#    Summing the four quarters of each year reproduces the already-connected
#    STATE_BUDGET_DEFICIT exactly:
#       2023: 382,189.3 + 1,249,185.9 + 592,247.6 + 587,477.9 = 2,811,100.7
#             vs published deficit -2,811,100.59
#       2024: 271,312.9 + 694,701.5 + 1,091,941.7 + 1,528,085.9 = 3,586,042.0
#             vs published deficit -3,586,041.85
#       2025: -77,995.2 + 1,075,781.4 + 1,002,304.0 + 2,383,780.8 = 4,383,871.0
#             vs published deficit -4,383,871.07
#    i.e. financing exactly covers the deficit, three years running.
#
# Only the QUARTERLY columns (2023Q1 onward) are published. The sheets also
# carry annual columns for 2018-2022, but those are a different frequency and
# are deliberately not spliced onto the quarterly series.
# ---------------------------------------------------------------------------
FINANCING_ANNUAL_RE = re.compile(r"(\d{4})\s*ж\.\s*есеп")
FINANCING_QUARTER_RE = re.compile(r"(\d{4})\s*ж\..*?(\d)\s*тоқсан", re.DOTALL)
FINANCING_QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
STATE_BUDGET_MARKER = "Мемлекеттік бюджет"
REPUBLICAN_BUDGET_MARKER = "Республикалық бюджет"


def _fetch_budget_financing_row(sheet_prefix: str, kazakh_label: str, russian_marker: str,
                                 indicator_id: str, note: str) -> tuple[list[dict], dict]:
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no bulletin document under directions={BUDGET_DIRECTION_ID}",
                f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
            ])
        )
    doc = bulletins[0]
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)

    today = date.today()
    ext = "xls" if file_path.lower().endswith(".xls") else "xlsx"
    raw_store.save_raw_bytes(SOURCE, indicator_id, today, ext, content)
    raw_store.write_download_manifest(SOURCE, indicator_id, today, {
        "downloaded_at": datetime.now().isoformat(),
        "source_document_id": doc["id"], "source_title": doc.get("title"),
        "source_url": GOV_KZ_BASE + file_path,
    })

    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    # NB: one of these sheets is named with a TRAILING SPACE ('табл 21 кв '),
    # so match on a stripped prefix rather than equality.
    target_sheet = next((s for s in sheet_names if s.strip().startswith(sheet_prefix)), None)
    if target_sheet is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no sheet whose stripped name starts with {sheet_prefix!r}",
                f"ACTUAL sheets: {sheet_names}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    rows = list(_iter_rows(kind, wb, target_sheet))

    # Establish the STATE-budget column range from the group header row.
    state_col = rep_col = None
    for r in rows[:12]:
        for j, c in enumerate(r):
            if isinstance(c, str):
                if state_col is None and STATE_BUDGET_MARKER in c:
                    state_col = j
                if rep_col is None and REPUBLICAN_BUDGET_MARKER in c:
                    rep_col = j
        if state_col is not None and rep_col is not None:
            break
    if state_col is None or rep_col is None or rep_col <= state_col:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                "WHAT CHANGED: could not locate the two budget column groups "
                f"({STATE_BUDGET_MARKER!r} then {REPUBLICAN_BUDGET_MARKER!r}) in sheet {target_sheet!r}",
                f"ACTUAL: state_col={state_col}, republican_col={rep_col}",
                "EXPECTED: state budget group starts left of the republican group; without this "
                "boundary the two budgets would be silently mixed",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    # Period header row: the one with the most quarter labels.
    period_row, quarters = None, {}
    for r in rows[:14]:
        found = {}
        for j, c in enumerate(r):
            if not isinstance(c, str):
                continue
            m = FINANCING_QUARTER_RE.search(c)
            if m and state_col <= j < rep_col:
                q = int(m.group(2))
                if q in FINANCING_QUARTER_END:
                    found[j] = (int(m.group(1)), q)
        if len(found) > len(quarters):
            period_row, quarters = r, found
    if len(quarters) < 4:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: fewer than 4 quarterly columns inside the state-budget group "
                f"(cols {state_col}..{rep_col - 1}) of sheet {target_sheet!r}",
                f"ACTUAL: {len(quarters)}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    target_row = next((r for r in rows
                       if r and isinstance(r[0], str) and r[0].strip().startswith(kazakh_label)), None)
    if target_row is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no row whose first cell starts with {kazakh_label!r} in {target_sheet!r}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    russian_text = " ".join(str(c) for c in target_row if isinstance(c, str))
    if russian_marker.lower() not in russian_text.lower():
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: the row starting {kazakh_label!r} no longer carries its expected "
                f"Russian label {russian_marker!r}",
                f"ACTUAL text: {russian_text[:200]!r}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    records = []
    for col, (year, q) in sorted(quarters.items()):
        value = target_row[col] if col < len(target_row) else None
        if value in (None, ""):
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        records.append({"date": f"{year:04d}-{FINANCING_QUARTER_END[q]}", "value": v})

    if not records:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no quarterly values parsed for row {kazakh_label!r}",
                f"ACTION REQUIRED: inspect {GOV_KZ_BASE + file_path}",
            ])
        )

    records.sort(key=lambda r: r["date"])
    return records, {
        "frequency": "quarterly",
        "source_url": GOV_KZ_BASE + file_path,
        "dataset_id": f"statistical-bulletin/{target_sheet}/state-budget/{kazakh_label}",
        "note": note,
    }


def fetch_budget_financing_total() -> tuple[list[dict], dict]:
    """State budget financing, total (million KZT, per quarter)."""
    return _fetch_budget_financing_row(
        "табл 21", "МІНДЕТТЕМЕЛЕР", "ОБЯЗАТЕЛЬСТВА",
        "BUDGET_FINANCING_TOTAL",
        "Million KZT, flow during the quarter (NOT year-to-date). Total financing of the STATE "
        "budget through incurring liabilities. The four quarters of a year sum to that year's "
        "STATE_BUDGET_DEFICIT -- verified for 2023, 2024 and 2025.",
    )


def fetch_budget_financing_domestic() -> tuple[list[dict], dict]:
    """State budget financing from domestic sources (million KZT, per quarter)."""
    return _fetch_budget_financing_row(
        "табл 21", "Ішкі", "нутренние",
        "BUDGET_FINANCING_DOMESTIC",
        "Million KZT, flow during the quarter. DOMESTIC financing of the state budget. With "
        "BUDGET_FINANCING_EXTERNAL this sums to BUDGET_FINANCING_TOTAL.",
    )


def fetch_budget_financing_external() -> tuple[list[dict], dict]:
    """State budget financing from external sources (million KZT, per quarter)."""
    return _fetch_budget_financing_row(
        "табл 21", "Сыртқы", "нешние",
        "BUDGET_FINANCING_EXTERNAL",
        "Million KZT, flow during the quarter. EXTERNAL financing of the state budget -- "
        "frequently negative, i.e. net repayment to foreign creditors.",
    )


def fetch_budget_financing_long_term_bonds() -> tuple[list[dict], dict]:
    """State budget financing via long-term bonds (million KZT, per quarter)."""
    return _fetch_budget_financing_row(
        "табл 21", "Ұзақ мерзімді облигациялар", "Долгосрочные облигации",
        "BUDGET_FINANCING_LONG_TERM_BONDS",
        "Million KZT, flow during the quarter. Financing raised through LONG-TERM bonds -- the "
        "dominant domestic instrument.",
    )


def fetch_budget_financing_banks() -> tuple[list[dict], dict]:
    """State budget financing from deposit corporations (million KZT, per quarter)."""
    return _fetch_budget_financing_row(
        "табл 20", "Депозиттік корпорациялар", "Депозитные корпорации",
        "BUDGET_FINANCING_BANKS",
        "Million KZT, flow during the quarter. Financing provided by DEPOSIT CORPORATIONS "
        "(banks) -- who is actually funding the deficit, from the counterparty-sector table.",
    )


def fetch_budget_financing_intl_organizations() -> tuple[list[dict], dict]:
    """State budget financing from international organizations (million KZT, per quarter)."""
    return _fetch_budget_financing_row(
        "табл 20", "Халықаралық ұйымдар", "еждународные организации",
        "BUDGET_FINANCING_INTL_ORGANIZATIONS",
        "Million KZT, flow during the quarter. Financing from INTERNATIONAL ORGANIZATIONS "
        "(IBRD, ADB and similar) -- the main external counterparty group.",
    )


# ---------------------------------------------------------------------------
# OIL_EXPORT_DUTY / OIL_PRODUCTS_EXPORT_DUTY: found 2026-09-01 in sheet "табл 4"
# by scanning every sheet of the bulletin for rows mentioning oil. Kazakhstan is
# an oil exporter and the dataset carried no oil-linked budget revenue at all.
#
# What the scan actually showed matters for how these are named. Almost every
# oil-mentioning row in the budget classification is a NON-oil variant -- "Мұнай
# секторы ұйымдарынан түсетін түсімдерді қоспағанда", i.e. "excluding receipts
# from oil sector organisations". The source does not publish a single
# "oil revenue of the budget" total line. These two rows are the exception:
# unambiguous, directly oil-linked revenue items. They are therefore named for
# exactly what they are -- export customs duties -- and NOT presented as total
# oil revenue, which would overstate what the source provides.
#
# Same column layout as LAND_TAX in this sheet: Kazakh label in column 4, value
# in column 5, Russian label in column 6. Matched on the Kazakh label because
# this sheet's row padding varies between vintages and its Russian labels have
# been seen with Latin/Cyrillic letter substitutions.
# ---------------------------------------------------------------------------
OIL_EXPORT_DUTY_KZ_LABEL = "Мұнайға салынатын кедендік әкету бажы"
OIL_PRODUCTS_EXPORT_DUTY_KZ_LABEL = "Мұнайдан өндірілген тауарларға салынатын кедендік әкету бажы"


def fetch_oil_export_duty() -> tuple[list[dict], dict]:
    """Export customs duty on CRUDE OIL, state budget, million KZT,
    year-to-date cumulative."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_REVENUE_SHEET_NAME,
        lambda r: len(r) > 4 and isinstance(r[4], str) and r[4].strip() == OIL_EXPORT_DUTY_KZ_LABEL,
        "OIL_EXPORT_DUTY",
        value_col=5,
    )


def fetch_oil_products_export_duty() -> tuple[list[dict], dict]:
    """Export customs duty on goods produced from oil, state budget, million
    KZT, year-to-date cumulative."""
    return _fetch_bulletin_row(
        BULLETIN_STATE_REVENUE_SHEET_NAME,
        lambda r: len(r) > 4 and isinstance(r[4], str) and r[4].strip() == OIL_PRODUCTS_EXPORT_DUTY_KZ_LABEL,
        "OIL_PRODUCTS_EXPORT_DUTY",
        value_col=5,
    )


# ---------------------------------------------------------------------------
# STATE BUDGET EXECUTION, YEAR-TO-DATE -- the audit's "monthly budget
# execution" item, from sheet "табл 3" of the Statistical Bulletin.
#
# The dataset already held STATE_BUDGET_REVENUE / _EXPENDITURE / _DEFICIT and
# STATE_NON_OIL_DEFICIT from this same sheet, but read from its ANNUAL column
# -- three points each, the last being 2025. Fiscal position could not be
# tracked within a year at all.
#
# The sheet's column layout is [Kazakh label, 2023 annual, 2024 annual, 2025
# annual, 2025 Jan-to-month, 2026 Jan-to-month, Russian label]. The existing
# annual series read column 3. Column 5 is the CURRENT year-to-date figure, and
# across the thirteen bulletin vintages that gives thirteen in-year points.
#
# Two consequences of the layout worth stating:
#
# 1. The default value_col of -2 lands on the RUSSIAN LABEL here, not a number,
#    because this sheet puts its labels in the last columns. An absolute index
#    is used, the same fix "табл 4" needed.
# 2. Rows are matched on the RUSSIAN label at index 6, not the Kazakh one at
#    index 0, and on the full section text -- 'I. ДОХОДЫ' rather than a prefix,
#    since 'III. ЧИСТОЕ БЮДЖЕТНОЕ КРЕДИТОВАНИЕ' and 'VI. НЕНЕФТЯНОЙ ДЕФИЦИТ'
#    would collide with looser matching.
#
# THE BUDGET IDENTITY IS CHECKED against the latest bulletin on every fetch of
# the deficit series: revenue - expenditure - net lending - financial assets
# balance = deficit. All four components and the deficit are published
# independently on this sheet, so this tests the row lookups rather than
# restating one number. For Jan-June 2026: 15,036,307.107 - 16,677,640.518 -
# 255,161.716 - 379,454.476 = -2,275,949.603, exactly the stated line V.
#
# These are YEAR-TO-DATE CUMULATIVE and reset each January, like every other
# bulletin-sourced series here. A January value is not a collapse from the
# previous December.
# ---------------------------------------------------------------------------
BULLETIN_STATE_BUDGET_YTD_COL = 5
BULLETIN_STATE_BUDGET_LABEL_COL = 6
STATE_BUDGET_LINES = {
    "revenue": "I. ДОХОДЫ",
    "expenditure": "II. ЗАТРАТЫ",
    "net_lending": "III. ЧИСТОЕ БЮДЖЕТНОЕ КРЕДИТОВАНИЕ",
    "financial_assets": "IV. САЛЬДО ПО ОПЕРАЦИЯМ С ФИНАНСОВЫМИ АКТИВАМИ",
    "deficit": "V. ДЕФИЦИТ (ПРОФИЦИТ) БЮДЖЕТА",
    "non_oil_deficit": "VI. НЕНЕФТЯНОЙ ДЕФИЦИТ (ПРОФИЦИТ) БЮДЖЕТА",
}
STATE_BUDGET_IDENTITY_TOLERANCE = 1.0  # million KZT


def _state_budget_row_matcher(label: str):
    def matcher(row) -> bool:
        if len(row) <= BULLETIN_STATE_BUDGET_LABEL_COL:
            return False
        cell = row[BULLETIN_STATE_BUDGET_LABEL_COL]
        return isinstance(cell, str) and cell.strip().startswith(label)
    return matcher


def _verify_state_budget_identity(indicator_id: str) -> str:
    """revenue - expenditure - net lending - financial assets == deficit.

    Checked against the most recent bulletin only, which costs one download
    rather than one per component. Returns the period checked.
    """
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    bulletins = [d for d in docs if STATISTICAL_BULLETIN_TITLE_MARKER in (d.get("title") or "")]
    if not bulletins:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains "
                f"{STATISTICAL_BULLETIN_TITLE_MARKER!r}",
                "ACTION REQUIRED: inspect the listing and update scripts/fetchers/minfin.py",
            ])
        )

    doc = bulletins[0]
    file_path = doc["full_text"][0]["document"]
    content = _download(file_path)
    kind, wb = _open_workbook(content, file_path)
    sheet_names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
    target_sheet = next((s for s in sheet_names if s.strip() == BULLETIN_STATE_BUDGET_SHEET_NAME), None)
    if target_sheet is None:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: the latest bulletin has no sheet {BULLETIN_STATE_BUDGET_SHEET_NAME!r}",
                f"ACTUAL sheets: {sheet_names[:12]}",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    rows = list(_iter_rows(kind, wb, target_sheet))
    values = {}
    for key, label in STATE_BUDGET_LINES.items():
        matcher = _state_budget_row_matcher(label)
        row = next((r for r in rows if r and matcher(r)), None)
        if row is None or len(row) <= BULLETIN_STATE_BUDGET_YTD_COL:
            continue
        cell = row[BULLETIN_STATE_BUDGET_YTD_COL]
        if isinstance(cell, (int, float)):
            values[key] = float(cell)

    needed = ("revenue", "expenditure", "net_lending", "financial_assets", "deficit")
    missing = [k for k in needed if k not in values]
    if missing:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: sheet {BULLETIN_STATE_BUDGET_SHEET_NAME!r} of the latest bulletin "
                f"no longer carries a numeric column {BULLETIN_STATE_BUDGET_YTD_COL} for: "
                f"{[STATE_BUDGET_LINES[k] for k in missing]}",
                "EXPECTED: all budget sections present with a year-to-date figure",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )

    computed = (values["revenue"] - values["expenditure"]
                - values["net_lending"] - values["financial_assets"])
    if abs(computed - values["deficit"]) > STATE_BUDGET_IDENTITY_TOLERANCE:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
                f"WHAT CHANGED: the state budget identity no longer holds -- revenue "
                f"{values['revenue']:.3f} - expenditure {values['expenditure']:.3f} - net lending "
                f"{values['net_lending']:.3f} - financial assets {values['financial_assets']:.3f} "
                f"= {computed:.3f}, against a stated deficit of {values['deficit']:.3f}",
                "EXPECTED: all five lines are published independently on this sheet and must "
                "reconcile; a mismatch means a row lookup has drifted or a section was respecified",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/minfin.py",
            ])
        )
    return str(doc.get("title") or "")[:80]


def _fetch_state_budget_ytd(line: str, indicator_id: str, note: str,
                            check_identity: bool = False) -> tuple[list[dict], dict]:
    records, manifest = _fetch_bulletin_row(
        BULLETIN_STATE_BUDGET_SHEET_NAME,
        _state_budget_row_matcher(STATE_BUDGET_LINES[line]),
        indicator_id,
        value_col=BULLETIN_STATE_BUDGET_YTD_COL,
        note_override=note)
    if check_identity:
        manifest["identity_checked_against"] = _verify_state_budget_identity(indicator_id)
    return records, manifest


_STATE_BUDGET_YTD_COMMON = (
    "Million KZT, STATE budget (republican plus local), YEAR-TO-DATE CUMULATIVE -- resets each "
    "January, so a January value is not a collapse from the previous December. Read from column 5 "
    "of sheet 'табл 3'; the existing annual series of the same name reads column 3 of the same "
    "sheet. ")


def fetch_state_budget_revenue_ytd() -> tuple[list[dict], dict]:
    """State budget revenue, million KZT, year-to-date."""
    return _fetch_state_budget_ytd(
        "revenue", "STATE_BUDGET_REVENUE_YTD",
        _STATE_BUDGET_YTD_COMMON +
        "Total revenue. 15,036,307 mln KZT for January-June 2026 against 14,516,486 for the same "
        "period of 2025, both printed side by side on the sheet.")


def fetch_state_budget_expenditure_ytd() -> tuple[list[dict], dict]:
    """State budget expenditure, million KZT, year-to-date."""
    return _fetch_state_budget_ytd(
        "expenditure", "STATE_BUDGET_EXPENDITURE_YTD",
        _STATE_BUDGET_YTD_COMMON +
        "Total expenditure ('затраты'). 16,677,641 mln KZT for January-June 2026 -- spending ran "
        "ahead of revenue by 1.64 trillion before net lending and financial-asset operations.")


def fetch_state_budget_deficit_ytd() -> tuple[list[dict], dict]:
    """State budget deficit, million KZT, year-to-date."""
    return _fetch_state_budget_ytd(
        "deficit", "STATE_BUDGET_DEFICIT_YTD",
        _STATE_BUDGET_YTD_COMMON +
        "Deficit (negative) or surplus (positive), -2,275,950 mln KZT for January-June 2026. Every "
        "fetch re-checks the budget identity against the latest bulletin: revenue - expenditure - "
        "net lending - balance on financial-asset operations must equal this line, and all five "
        "are published independently on the sheet.",
        check_identity=True)


def fetch_state_non_oil_deficit_ytd() -> tuple[list[dict], dict]:
    """State budget non-oil deficit, million KZT, year-to-date."""
    return _fetch_state_budget_ytd(
        "non_oil_deficit", "STATE_NON_OIL_DEFICIT_YTD",
        _STATE_BUDGET_YTD_COMMON +
        "The deficit excluding oil revenue -- -5,037,288 mln KZT for January-June 2026 against a "
        "headline deficit of -2,275,950. The gap between the two is what oil contributed to the "
        "budget, and it is the number that shows the underlying fiscal position.")


def fetch_state_net_budget_lending_ytd() -> tuple[list[dict], dict]:
    """Net budget lending, million KZT, year-to-date."""
    return _fetch_state_budget_ytd(
        "net_lending", "STATE_NET_BUDGET_LENDING_YTD",
        _STATE_BUDGET_YTD_COMMON +
        "Budget loans issued minus repaid (255,162 mln KZT for January-June 2026). One of the two "
        "lines between the revenue-expenditure gap and the headline deficit; not previously in the "
        "dataset at any frequency.")


def fetch_state_financial_assets_balance_ytd() -> tuple[list[dict], dict]:
    """Balance on operations with financial assets, million KZT, year-to-date."""
    return _fetch_state_budget_ytd(
        "financial_assets", "STATE_FINANCIAL_ASSETS_BALANCE_YTD",
        _STATE_BUDGET_YTD_COMMON +
        "Acquisition minus disposal of financial assets (379,454 mln KZT for January-June 2026). "
        "The second of the two lines between the revenue-expenditure gap and the headline deficit; "
        "not previously in the dataset at any frequency.")


# ---------------------------------------------------------------------------
# Monthly state-budget TAX receipts for nowcasting (added 2026-09-25), 2020 onward.
#
# The bulletin series above read only the first page of the listing (100 newest
# documents), which reaches back to 2025. The listing has more pages (X-Has-Next /
# X-Next-Pages headers); older bulletins are titled "Statistical Bulletin" with a capital
# B, which the case-sensitive marker above does not match either. Here every page is read
# and every bulletin's 'табл 3' (STATE budget, million KZT) parsed.
#
# 'табл 3' has had three layouts, so the period of each column is read from its header
# text, never from its position:
#   2020-mid 2021  annual 'YYYY ж. есеп' columns, then four '1-тоқсан … 4-тоқсан' columns
#                  under the current year -- DISCRETE quarters, cumulated here to Mar, Jun,
#                  Sep, Dec year-to-date;
#   some editions  annual columns only (the December edition): the last one is Jan-Dec;
#   mid 2021 on    annual columns; the prior year split into 'жылдық/годовой' and
#                  'қантар-шілде/январь-июль' (the prior-year same period), then
#                  'YYYY ж. қантар-шілде есеп/январь-июль отчет' (the current year to date).
# Where editions disagree on a (year, month) the most recent edition wins (revisions);
# the number of revised points is reported in the note. Checked 2026-09-25: December
# year-to-date equals the annual column of the next editions for 2022-2025 (e.g. tax
# 2024: 19 700 516.9 -- equal to KGD's 19 700 516 947 thousand to the thousand).
# ---------------------------------------------------------------------------
BULLETIN_TITLE_RE = re.compile(r"statistical\s+bulletin|бюллетен", re.IGNORECASE)
YEAR_IN_HEADER_RE = re.compile(r"(\d{4})\s*ж\.")
QUARTER_IN_HEADER_RE = re.compile(r"(\d)\s*-\s*тоқсан")
RU_RANGE_RE = re.compile(r"январ[ьяе]?\s*(?:-\s*([а-яё]+))?", re.IGNORECASE)
STATE_TAX_ROWS = {
    # Kazakh label in column 0 of 'табл 3'; the first matching row after «I. КІРІСТЕР».
    "STATE_TAX_REVENUE_YTD": lambda s: s.startswith("салықтық түс"),
    "STATE_CIT_YTD": lambda s: "табыс салығы" in s and ("корпорат" in s or "корпорац" in s),
    "STATE_PIT_YTD": lambda s: s.startswith("жеке табыс салығы"),
    "STATE_SOCIAL_TAX_YTD": lambda s: s.startswith("әлеуметт") and "салық" in s,
    "STATE_VAT_YTD": lambda s: s.startswith("қосылған құн салығы"),
    "STATE_EXCISE_YTD": lambda s: s.startswith("акциз"),
}


def _list_all_documents(**params) -> list[dict]:
    """Every page of the listing (the first-page helper above stops at 100 documents)."""
    key = ("ALL",) + tuple(sorted(params.items()))
    if key not in _LISTING_CACHE:
        docs, page = [], 1
        while page <= 50:
            resp = requests.get(LISTING_URL, headers=HEADERS, timeout=60,
                                params={"sort-by": "created_date:DESC", "page": str(page), "size": "100", **params})
            resp.raise_for_status()
            docs += resp.json()
            if resp.headers.get("X-Has-Next", "false").lower() != "true":
                break
            page += 1
        _LISTING_CACHE[key] = docs
    return _LISTING_CACHE[key]


def bulletin_state_budget_columns(header: list, subheader: list) -> dict[int, tuple[int, int, str]]:
    """{column: (year, last month covered, kind)} for 'табл 3'. kind: 'ytd' (January to
    that month), 'annual', or 'quarter' (a DISCRETE quarter; month = its last month)."""
    out: dict[int, tuple[int, int, str]] = {}
    parent = None
    for j in range(1, max(len(header), len(subheader))):
        top = str(header[j]) if j < len(header) and header[j] not in (None, "") else None
        sub = str(subheader[j]) if j < len(subheader) and subheader[j] not in (None, "") else None
        if top is not None:
            if not YEAR_IN_HEADER_RE.search(top):
                parent = None                               # «Наименование»: the Russian label column
                continue
            parent = top
        if parent is None:
            continue
        year = int(YEAR_IN_HEADER_RE.search(parent).group(1))
        text = sub if sub is not None else (parent if top is not None else None)
        if text is None:
            continue
        q = QUARTER_IN_HEADER_RE.search(text)
        if q:
            out[j] = (year, 3 * int(q.group(1)), "quarter")
            continue
        if "жылдық" in text or "годов" in text:
            out[j] = (year, 12, "annual")
            continue
        ru = text.split("/", 1)[-1]
        m = RU_RANGE_RE.search(ru) if "қантар" in text.lower() or "январ" in ru.lower() else None
        if m:
            month = _ru_month(m.group(1)) if m.group(1) else 1
            if month:
                out[j] = (year, month, "ytd")
            continue
        if sub is None:
            out[j] = (year, 12, "annual")
    return out


def parse_bulletin_state_taxes(rows: list[list]) -> dict[str, dict[tuple[int, int], float]]:
    """{indicator: {(year, month): year-to-date million KZT}} from one bulletin's 'табл 3'."""
    hi = next((i for i, r in enumerate(rows) if r and isinstance(r[0], str) and r[0].strip().startswith("Атауы")), None)
    if hi is None:
        return {}
    columns = bulletin_state_budget_columns(rows[hi], rows[hi + 1] if hi + 1 < len(rows) else [])
    start = next((i for i, r in enumerate(rows) if r and isinstance(r[0], str) and r[0].strip().startswith("I. К")), hi)
    out: dict[str, dict[tuple[int, int], float]] = {}
    for ind, matches in STATE_TAX_ROWS.items():
        row = next((r for r in rows[start:] if r and isinstance(r[0], str)
                    and matches(" ".join(r[0].replace("_x000D_", " ").split()).lower())), None)
        if row is None:
            continue
        vals: dict[tuple[int, int], float] = {}
        quarters: dict[int, dict[int, float]] = {}
        for j, (year, month, kind) in columns.items():
            cell = row[j] if j < len(row) else None
            try:
                v = float(cell)
            except (TypeError, ValueError):
                continue
            if kind == "quarter":
                quarters.setdefault(year, {})[month] = v
            else:
                vals[(year, month)] = v
        for year, qs in quarters.items():                   # discrete quarters -> year to date
            running = 0.0
            for month in (3, 6, 9, 12):
                if month not in qs:
                    break
                running += qs[month]
                vals.setdefault((year, month), running)
        out[ind] = vals
    return out


_STATE_TAX_CACHE: dict = {}


def _state_tax_history() -> tuple[dict[str, dict[tuple[int, int], float]], dict]:
    if _STATE_TAX_CACHE:
        return _STATE_TAX_CACHE["data"], _STATE_TAX_CACHE["info"]
    docs = [d for d in _list_all_documents(directions=BUDGET_DIRECTION_ID)
            if BULLETIN_TITLE_RE.search(d.get("title") or "")
            and d.get("full_text") and str(d["full_text"][0].get("document", "")).lower().endswith((".xlsx", ".xls"))]
    docs.sort(key=lambda d: d.get("created_date") or "")          # oldest first: later editions overwrite
    data: dict[str, dict[tuple[int, int], float]] = {k: {} for k in STATE_TAX_ROWS}
    revised = 0
    parsed, skipped = [], []
    today = date.today()
    for doc in docs:
        path = doc["full_text"][0]["document"]
        try:
            content = _download(path)
            kind, wb = _open_workbook(content, path)
        except Exception:  # noqa: BLE001 -- one unreadable edition must not sink the history
            skipped.append(doc.get("id"))
            continue
        names = wb.sheet_names() if kind == "xlrd" else wb.sheetnames
        sheet = next((s for s in names if s.strip() == BULLETIN_STATE_BUDGET_SHEET_NAME), None)
        if sheet is None:
            skipped.append(doc.get("id"))
            continue
        rows = list(_iter_rows(kind, wb, sheet))
        got = parse_bulletin_state_taxes(rows)
        if not got.get("STATE_TAX_REVENUE_YTD"):
            skipped.append(doc.get("id"))
            continue
        parsed.append(doc.get("id"))
        # The sheet read, not the 0.5-2 MB workbook: 40-odd editions would add ~70 MB to the
        # archive for one table. Identical bytes are stored once (raw_store dedups).
        sheet_json = json.dumps({"document": path, "created_date": doc.get("created_date"), "title": doc.get("title"),
                                 "sheet": sheet, "rows": rows}, ensure_ascii=False, default=str).encode("utf-8")
        raw_store.save_raw_bytes(SOURCE, f"BULLETIN_TABLE3_{str(doc.get('created_date', ''))[:10]}_{doc.get('id')}", today, "json",
                                 sheet_json)
        for ind, vals in got.items():
            for k, v in vals.items():
                old = data[ind].get(k)
                if old is not None and abs(old - v) > 0.5:
                    revised += 1
                data[ind][k] = v
    info = {"n_bulletins": len(docs), "parsed": len(parsed), "skipped": skipped, "revised_points": revised}
    raw_store.write_download_manifest(SOURCE, "STATE_TAX_BULLETINS", today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        **info})
    _STATE_TAX_CACHE.update(data=data, info=info)
    return data, info


STATE_TAX_NAMES = {
    "STATE_TAX_REVENUE_YTD": "tax receipts, total", "STATE_CIT_YTD": "corporate income tax",
    "STATE_PIT_YTD": "individual income tax", "STATE_SOCIAL_TAX_YTD": "social tax",
    "STATE_VAT_YTD": "value added tax", "STATE_EXCISE_YTD": "excise duties",
}


def _fetch_state_tax(indicator_id: str) -> tuple[list[dict], dict]:
    data, info = _state_tax_history()
    vals = data[indicator_id]
    if len(vals) < 40:
        raise validation.StructuralChangeError("\n".join([
            f"STRUCTURAL CHANGE DETECTED in minfin/{indicator_id}",
            f"WHAT CHANGED: only {len(vals)} months parsed from {info['parsed']} of {info['n_bulletins']} bulletins",
            f"ACTION REQUIRED: inspect 'табл 3' of a recent bulletin ({LISTING_URL}?directions={BUDGET_DIRECTION_ID})"]))
    records = [{"date": f"{y:04d}-{m:02d}-01", "value": v} for (y, m), v in sorted(vals.items())]
    return records, {
        "frequency": "monthly", "source_url": f"{LISTING_URL}?directions={BUDGET_DIRECTION_ID}",
        "dataset_id": "gov.kz-statistical-bulletin,sheet=табл 3,all pages",
        "note": (f"Million KZT, STATE budget (republican plus local) {STATE_TAX_NAMES[indicator_id]}, YEAR-TO-DATE "
                 "cumulative (January to the month dated), from every Statistical Bulletin on every page of the "
                 f"listing ({info['parsed']} of {info['n_bulletins']} parsed). The latest edition wins where editions "
                 f"differ ({info['revised_points']} revised points across the six series). Where an edition gave "
                 "discrete quarters (2020 - mid 2021) they are cumulated to March/June/September/December. Months "
                 "no edition covers are missing, not interpolated."),
    }


def fetch_state_tax_revenue_ytd() -> tuple[list[dict], dict]:
    return _fetch_state_tax("STATE_TAX_REVENUE_YTD")


def fetch_state_cit_ytd() -> tuple[list[dict], dict]:
    return _fetch_state_tax("STATE_CIT_YTD")


def fetch_state_pit_ytd() -> tuple[list[dict], dict]:
    return _fetch_state_tax("STATE_PIT_YTD")


def fetch_state_social_tax_ytd() -> tuple[list[dict], dict]:
    return _fetch_state_tax("STATE_SOCIAL_TAX_YTD")


def fetch_state_vat_ytd() -> tuple[list[dict], dict]:
    return _fetch_state_tax("STATE_VAT_YTD")


def fetch_state_excise_ytd() -> tuple[list[dict], dict]:
    return _fetch_state_tax("STATE_EXCISE_YTD")
