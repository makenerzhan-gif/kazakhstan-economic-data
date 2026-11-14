#!/usr/bin/env python3
"""One-off: read every monthly Statistical Bulletin Minfin keeps online (January 2019 on,
91 xlsx on 2026-09-27) into the bulletin series' processed history.

    python scripts/backfill_minfin_bulletins.py [--cache DIR] [--only ID ...] [--yearly 2005-2018] [--dims ID ...] [--offline]

The daily run sees only the budget direction's latest ~14 bulletins and lays them over the
processed history (fetchers/minfin._with_history); this script supplies that history. It sets
minfin.BULLETIN_ARCHIVE, so the documents come from title searches too, and runs update_minfin
for every series read from the bulletin — the January-to-month ones (_fetch_bulletin_row, state
budget table 3) and the annual ones (_fetch_bulletin_annual_row), then the quarterly state
budget built from them. The archive's workbooks are not copied into data/raw.

--yearly FIRST-LAST: also the years before 2019. Minfin keeps them as one RAR per year («Статистический
бюллетень за 2017 год (12 месяцев)», 12 monthly editions inside; the tables are those of the 2019
editions, same sheet names and labels). Each archive is downloaded into the cache, unpacked with
7z, unar or unrar (the 2012 archive is RAR5) and its editions are read like the monthly documents. 2013-2018
are spreadsheets. 2005-2012 are PDF with a few spreadsheets among them: a PDF is turned into sheets by
fetchers/minfin_pdf.py (needs pdftotext), which maps only the tables the --dims datasets read -- the scalar
series find nothing in it. 2002-2004 follow the pre-2005 budget classification and are not read.

--offline: do not ask gov.kz for the list of documents; read only the yearly archives already unpacked in the
cache (folders yearly_<year>). For reading the old years where the listing API does not answer.

--dims ID ...: run these item-level datasets of config/dims.yaml instead (the bulletin readers of
fetchers/minfin_regions.py), then rebuild data/unified/macro_dims_long.csv.gz.

--cache DIR: a folder with the bulletins already downloaded, named <document id>.xlsx/.xls
(downloaded there when missing). Each workbook is read once, in openpyxl's read-only mode, and
its sheets kept in memory for every series (the full-mode load the daily fetcher does would
take over an hour for 91 workbooks x 25 series).
"""
from __future__ import annotations

import argparse
import inspect
import os
import re
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


YEARLY_TITLE = "Статистический бюллетень за {year} год"


def _unpack(rar: Path, folder: Path) -> None:
    """7z crashes on the 2011 archive and, without its rar codec, writes empty files; unar does not read RAR5."""
    import shutil
    import subprocess
    for command in (["7z", "x", "-y", f"-o{folder}", str(rar)], ["unar", "-q", "-f", "-o", str(folder), str(rar)],
                    ["unrar", "x", "-o+", "-inul", str(rar), str(folder) + "/"]):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
        try:
            subprocess.run(command, check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        if any(f.is_file() and f.stat().st_size > 0 for f in folder.rglob("*")):
            return
    raise RuntimeError(f"{rar.name}: none of 7z, unar, unrar unpacked it")


def yearly_editions(years: range, cache: Path, offline: bool = False) -> list[dict]:
    """Pseudo-documents for the editions inside the yearly RAR archives; the local path stands in for the
    gov.kz file path (install_cache reads it back)."""
    import glob
    docs = []
    for year in years:
        folder = cache / f"yearly_{year}"
        source = "the cache"
        if not folder.exists():
            if offline:
                print(f"{year}: not in the cache")
                continue
            found = [d for d in minfin._list_documents(title=YEARLY_TITLE.format(year=year), projects="minfin")
                     if d.get("full_text") and str(d["full_text"][0].get("document", "")).lower().endswith(".rar")
                     and str(year) in (d.get("title") or "")]
            if not found:
                print(f"{year}: no yearly archive found")
                continue
            rar = cache / f"yearly_{year}.rar"
            if not rar.exists():
                rar.write_bytes(minfin._download(found[0]["full_text"][0]["document"]))
            _unpack(rar, folder)
            source = f"document {found[0]['id']}"
        files = sorted((f for f in glob.glob(str(folder / "**" / "*"), recursive=True) if f.lower().endswith((".xls", ".xlsx", ".pdf"))),
                       key=lambda f: (f.lower().endswith(".pdf"), f))        # a month printed both ways is taken from the spreadsheet
        print(f"{year}: {len(files)} editions from {source}")
        docs += [{"id": f"yearly:{year}:{Path(f).name}", "title": f"yearly {year} {Path(f).name}", "created_date": f"{year}-12-31",
                  "full_text": [{"document": f}]} for f in files]
    return docs


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
        if path.startswith(str(cache)):                   # an edition unpacked from a yearly archive
            return str(Path(path).relative_to(cache)).encode()
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
            if f.suffix.lower() == ".pdf":
                from fetchers import minfin_pdf
                year = re.search(r"yearly_(\d{4})", str(f))
                sheets = minfin_pdf.sheets(f.read_bytes(), int(year.group(1)) if year else None)
            elif f.suffix.lower() == ".xls" and f.read_bytes()[:4] != b"PK\x03\x04":
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
    ap.add_argument("--yearly", help="also the yearly archives, e.g. 2005-2018")
    ap.add_argument("--offline", action="store_true", help="only the yearly archives already unpacked in the cache")
    ap.add_argument("--dims", nargs="*", help="item-level datasets read from the bulletins (config/dims.yaml), e.g. REGIONAL_BUDGETS_YTD; "
                    "only these are run")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    minfin.BULLETIN_ARCHIVE = True
    if args.offline and not args.yearly:
        ap.error("--offline reads the yearly archives of the cache: give --yearly")
    if args.yearly:
        first, last = (int(y) for y in args.yearly.split("-"))
        extra = yearly_editions(range(first, last + 1), args.cache, args.offline)
        listed = (lambda: []) if args.offline else minfin._bulletin_documents
        minfin._bulletin_documents = lambda: listed() + extra      # the monthly documents first (newer editions win)
    docs = minfin._bulletin_documents()
    print(f"{len(docs)} bulletins, {docs[-1].get('created_date', '')[:10]} … {docs[0].get('created_date', '')[:10]}")
    install_cache(args.cache)

    log = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    if args.dims:
        import update_dims
        update_dims.run(log, set(args.dims))
        update_dims.build_unified()
    else:
        update_minfin.INDICATOR_IDS = args.only or bulletin_series()
        update_minfin.run(log)
    for e in log.entries:
        print(f"{e.dataset:40} {e.status:8} {e.records_processed or 0:4}", (e.errors or [""])[0][:120])
    if args.dims:                      # what each edition gave: the older layouts are diagnosed from this
        report = Path("reports") / "backfill_minfin_bulletins.md"
        lines = [f"# Bulletin backfill, item-level datasets -- {datetime.now():%Y-%m-%d %H:%M}", "",
                 f"{len(docs)} editions listed, {docs[-1].get('created_date', '')[:10]} … {docs[0].get('created_date', '')[:10]}.", ""]
        for e in log.entries:
            lines += [f"## {e.dataset}: {e.status}, {e.records_processed or 0} rows", ""]
            from fetchers import minfin_classification
            notes = minfin_classification.EDITION_NOTES.get(e.dataset)      # in full; the log entry keeps only the first few
            if notes is None:
                notes = [w for w in (e.warnings or []) if not w.startswith("[")]
            lines += [f"- ERROR: {x}" for x in (e.errors or [])] + [w if w.startswith("    ") else f"- {w}" for w in notes] + [""]
        report.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines)[:60000])


if __name__ == "__main__":
    main()
