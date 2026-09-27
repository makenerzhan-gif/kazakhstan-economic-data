#!/usr/bin/env python3
"""One-off: read every monthly Statistical Bulletin Minfin keeps online (January 2019 on,
91 xlsx on 2026-09-27) into the bulletin series' processed history.

    python scripts/backfill_minfin_bulletins.py [--cache DIR] [--only ID ...]

The daily run sees only the budget direction's latest ~14 bulletins and lays them over the
processed history (fetchers/minfin._with_history); this script supplies that history. It sets
minfin.BULLETIN_ARCHIVE, so the documents come from title searches too, and runs update_minfin
for every series read from the bulletin — the January-to-month ones (_fetch_bulletin_row, state
budget table 3) and the annual ones (_fetch_bulletin_annual_row), then the quarterly state
budget built from them. The archive's workbooks are not copied into data/raw.

--cache DIR: a folder with the bulletins already downloaded, named <document id>.xlsx/.xls
(downloaded there when missing). Each workbook is read once, in openpyxl's read-only mode, and
its sheets kept in memory for every series (the full-mode load the daily fetcher does would
take over an hour for 91 workbooks x 25 series).
"""
from __future__ import annotations

import argparse
import inspect
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_minfin  # noqa: E402
from fetchers import minfin  # noqa: E402
from lib import pipeline_logging  # noqa: E402

BULLETIN_READERS = ("_fetch_bulletin_row", "_fetch_state_budget_ytd", "_fetch_bulletin_annual_row")


def bulletin_series() -> list[str]:
    ids = [i for i, f in update_minfin.FETCHERS.items()
           if any(r in inspect.getsource(f) for r in BULLETIN_READERS)]
    return [i for i in update_minfin.INDICATOR_IDS if i in ids] + list(minfin.STATE_BUDGET_QUARTERLY)


class _Sheets:
    def __init__(self, sheets: dict[str, list[list]]):
        self.sheets = sheets
        self.sheetnames = list(sheets)

    def sheet_names(self):
        return self.sheetnames


def install_cache(cache: Path) -> None:
    """Downloads go to `cache`; every workbook is parsed once, read-only, for all series."""
    import openpyxl
    import xlrd
    by_path: dict[str, str] = {}
    parsed: dict[str, _Sheets] = {}
    download = minfin._download

    def cached_download(path: str) -> bytes:
        name = by_path.get(path) or path.rstrip("/").split("/")[-1]
        f = cache / name
        if not f.exists():
            f.write_bytes(download(path))
        return f.name.encode()

    def cached_open(content: bytes, hint: str):
        name = content.decode()
        if name not in parsed:
            f = cache / name
            sheets: dict[str, list[list]] = {}
            if f.suffix.lower() == ".xls":
                book = xlrd.open_workbook(str(f))
                for sh in book.sheets():
                    sheets[sh.name] = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
            else:
                wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
                for ws in wb.worksheets:
                    sheets[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
                wb.close()
            parsed[name] = _Sheets(sheets)
        return "sheets", parsed[name]

    def cached_rows(kind, wb, sheet_name=None):
        if kind != "sheets":
            return original_rows(kind, wb, sheet_name)
        return iter(wb.sheets[wb.sheetnames[0] if sheet_name is None else sheet_name])

    for d in minfin._bulletin_documents():
        p = str(d["full_text"][0]["document"])
        by_path[p] = f"{d['id']}{os.path.splitext(p)[1].lower()}"
    original_rows = minfin._iter_rows
    minfin._download = cached_download
    minfin._open_workbook = cached_open
    minfin._iter_rows = cached_rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "minfin_bulletins")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    minfin.BULLETIN_ARCHIVE = True
    docs = minfin._bulletin_documents()
    print(f"{len(docs)} bulletins, {docs[-1].get('created_date', '')[:10]} … {docs[0].get('created_date', '')[:10]}")
    install_cache(args.cache)

    update_minfin.INDICATOR_IDS = args.only or bulletin_series()
    log = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    update_minfin.run(log)
    for e in log.entries:
        print(f"{e.dataset:40} {e.status:8} {e.records_processed or 0:4}", (e.errors or [""])[0][:120])


if __name__ == "__main__":
    main()
