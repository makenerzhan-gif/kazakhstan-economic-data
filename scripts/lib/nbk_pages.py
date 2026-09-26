"""Canonical archive form of a paginated NBK open-data form download.

`fetchers.nbk._fetch_nbk_form_paginated` walks data.nationalbank.kz/api/v1/data?formId=N
page by page. The API does not answer the same data with the same bytes: the per-page
`columns` block labels a column differently from one page to the next, at random
(formId=132, insurance: `residency` is labelled "Residency of institutional units" on
some pages and "residency" -- before 2026-09-15 null -- on the others, in a different
mix on every call), and nothing guarantees the order of the rows either. Archived as
returned, the 13.7 MB insurance form and the 11 MB balance-of-payments form were
stored again on nearly every run from 2026-08-31 to 2026-09-26, often several times a
day, although the rows were the same (see data/raw/dedup_2026-09-26.json).

The canonical form keeps everything the pages carry and only fixes its arrangement:
  - every row of every page, none dropped, merged or edited (a row the API repeats is
    kept as many times as it was served), in one list sorted by report_date and then
    by the row's full content (`json.dumps(row, sort_keys=True)`, i.e. every dimension
    field and the amount), so the order no longer depends on the API;
  - the page envelope fields that are the same on every page (formId, locale,
    pageSize, totalRows, the filters) once, and `n_pages`; a field that differs
    between pages (other than `page` itself) under `envelope_varying`, all values;
  - `columns`: every distinct column entry seen on any page, sorted -- a column whose
    label the API varies appears once per label;
  - the whole document serialised with sorted keys.
Equal data therefore gives equal bytes, and lib/raw_store's byte-level dedup
(`identical_twin`) recognises an unchanged form. No field is treated as volatile and
dropped: `row_id` (added 2026-09-15) was checked to be stable for unchanged data.
"""
from __future__ import annotations

import json

CANONICAL_FORMAT = "nbk-open-data-form/canonical-v1"
NORMALISATION = ("all rows of all pages, unchanged and none dropped, sorted by report_date then full row content; "
                 "page envelope fields common to all pages kept once; distinct column entries of all pages, sorted; "
                 "keys sorted. Page boundaries and the API's row order are not kept (they vary between identical downloads).")
_SKIP = ("rows", "page", "columns")


def is_form_pages(obj) -> bool:
    """Is this the as-returned list of pages of an NBK open-data form (the format archived
    until 2026-09-26)?"""
    return (isinstance(obj, list) and bool(obj)
            and all(isinstance(p, dict) and "rows" in p and "formId" in p for p in obj))


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def row_sort_key(row: dict) -> tuple[str, str]:
    return (str(row.get("report_date", "")), _dump(row))


def canonical_form_document(pages: list[dict]) -> dict:
    rows = sorted((r for p in pages for r in (p.get("rows") or [])), key=row_sort_key)
    columns = {_dump(c): c for p in pages for c in (p.get("columns") or [])}
    envelope: dict = {}
    varying: dict = {}
    for key in sorted({k for p in pages for k in p if k not in _SKIP}):
        values = {_dump(p.get(key)): p.get(key) for p in pages}
        if len(values) == 1:
            envelope[key] = next(iter(values.values()))
        else:
            varying[key] = [values[v] for v in sorted(values)]
    doc = {"format": CANONICAL_FORMAT, "normalisation": NORMALISATION, **envelope,
           "n_pages": len(pages),
           "columns": [columns[k] for k in sorted(columns, key=lambda k: (str(columns[k].get("key")), k))],
           "rows": rows}
    if varying:
        doc["envelope_varying"] = varying
    return doc


def canonical_form_bytes(pages: list[dict]) -> bytes:
    """The bytes archived for a paginated form download: equal data -> equal bytes."""
    return _dump(canonical_form_document(pages)).encode("utf-8")


def canonical_bytes_of_archived(content: bytes) -> bytes | None:
    """Canonical bytes of an archived NBK form file, in either format (as-returned pages
    or already canonical); None when the file is not a paginated form download."""
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict) and obj.get("format") == CANONICAL_FORMAT:
        return _dump(obj).encode("utf-8")
    if is_form_pages(obj):
        return canonical_form_bytes(obj)
    return None
