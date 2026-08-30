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


def _list_documents(**params) -> list[dict]:
    resp = requests.get(LISTING_URL, headers=HEADERS,
                         params={"sort-by": "created_date:DESC", "page": "1", "size": "100", **params},
                         timeout=30)
    resp.raise_for_status()
    return resp.json()


def _download(path: str) -> bytes:
    url = path if path.startswith("http") else GOV_KZ_BASE + path
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return resp.content


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
GG_TITLE_MARKER = "General government data"
GG_QUARTER_HEADER_RE = re.compile(r"^(\d{4})/(\d)$")
GG_QUARTER_END_MONTH_DAY = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _find_gg_document() -> dict:
    docs = _list_documents(directions=BUDGET_DIRECTION_ID)
    for d in docs:
        title = d.get("title") or ""
        if GG_TITLE_MARKER in title:
            return d
    raise validation.StructuralChangeError(
        "\n".join([
            "STRUCTURAL CHANGE DETECTED in minfin/GG_* indicators",
            f"WHAT CHANGED: no document title under directions={BUDGET_DIRECTION_ID} contains {GG_TITLE_MARKER!r}",
            "EXPECTED: a 'General government data ... (consolidated budget according to IMF methodology)' document",
            "ACTUAL: not found in the current listing",
            f"ACTION REQUIRED: inspect {LISTING_URL}?directions={BUDGET_DIRECTION_ID} and update scripts/fetchers/minfin.py",
        ])
    )


def _fetch_gg_row(row_code, indicator_id: str) -> tuple[list[dict], dict]:
    doc = _find_gg_document()
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
