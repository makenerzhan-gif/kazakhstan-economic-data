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
