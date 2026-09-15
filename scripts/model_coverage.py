#!/usr/bin/env python3
"""Where does every number in the GDP model come from?

Walks the workbook's year columns and classifies every literal number (a cell that is
not a formula) as
  pipeline   — a cell some model_map.yaml mapping checks (ok / diff / control / missing:
               the pipeline is its source of truth, whatever the current status)
  manual     — a cell inside a config/manual_inputs.yaml entry: an assumption or a
               hand-loaded block with its provenance and vintage written down
  unaccounted — a number nobody has claimed: the phase-6 target is zero of these

    python scripts/model_coverage.py                 # summary per sheet + top unaccounted rows
    python scripts/model_coverage.py --csv out.csv   # every unaccounted (sheet, row, year)
    python scripts/model_coverage.py --sheet "Экспорт" --verbose

manual_inputs.yaml entries name a sheet, rows (a [first, last] range or a list) and
optionally years or columns; see the file for the fields. Sheets with a text header
(no calendar years in row 1) are scanned by column letter instead.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml
from openpyxl.utils import column_index_from_string, get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_sync as ms  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANUAL = REPO_ROOT / "config" / "manual_inputs.yaml"
SKIP_SHEETS = {"Контроль", "Журнал_правок"}


@dataclass
class Cell:
    sheet: str
    row: int
    col: int
    year: int | None
    value: float
    label: str
    status: str            # pipeline | manual | unaccounted
    claim: str = ""        # mapping id or manual input id


def _rows_of(spec, wb: ms.Workbook, sheet: str) -> set[int]:
    """Rows named by a manual entry: [first, last], a list, or a label regex."""
    rows: set[int] = set()
    if spec is None:
        return set(range(1, wb.max_row(sheet) + 1))
    if isinstance(spec, list) and len(spec) == 2 and all(isinstance(x, int) for x in spec):
        return set(range(int(spec[0]), int(spec[1]) + 1))
    for x in spec:
        if isinstance(x, int):
            rows.add(x)
        elif isinstance(x, list) and len(x) == 2:
            rows.update(range(int(x[0]), int(x[1]) + 1))
    return rows


def pipeline_claims(cfg: dict, wb: ms.Workbook) -> dict[tuple[str, int, int], str]:
    """(sheet, row, col) -> mapping id for every cell model_sync would check."""
    claims: dict[tuple[str, int, int], str] = {}
    header_row = int(cfg["model"].get("year_header_row", 1))
    default_years = [int(y) for y in cfg["model"]["default_years"]]
    cache: dict = {}
    for m in cfg["mappings"]:
        years = [int(y) for y in m.get("years", default_years)]
        if "dims_variable" in m:
            sheet = m["sheet"]
            cols = ms._year_cols(m, wb, sheet, header_row, cache)
            for _code, _region, row in ms._dims_targets(m, wb):
                for y in years:
                    if y in cols:
                        claims.setdefault((sheet, row, cols[y] + int(m.get("col_offset", 0))), m["id"])
        else:
            for t in m["targets"]:
                sheet = t["sheet"]
                cols = ms._year_cols(m, wb, sheet, header_row, cache)
                for y in years:
                    if y in cols:
                        claims.setdefault((sheet, int(t["row"]), cols[y] + int(t.get("col_offset", 0))), m["id"])
    return claims


def manual_claims(manual: dict, wb: ms.Workbook, year_cols: dict[str, dict[int, int]]) -> dict[tuple[str, int, int], str]:
    claims: dict[tuple[str, int, int], str] = {}
    for e in manual.get("inputs", []):
        sheet = e["sheet"]
        if sheet not in wb.sheetnames:
            continue
        rows = _rows_of(e.get("rows"), wb, sheet)
        if e.get("columns"):
            first, last = (column_index_from_string(c) for c in e["columns"])
            cols = set(range(first, last + 1))
        elif e.get("years"):
            y0, y1 = (int(y) for y in e["years"])
            cols = {c for y, c in year_cols.get(sheet, {}).items() if y0 <= y <= y1}
        else:
            cols = set(year_cols.get(sheet, {}).values())
        for r in rows:
            for c in cols:
                claims.setdefault((sheet, r, c), e["id"])
    return claims


def scan(model_path: Path, cfg: dict, manual: dict, only_sheet: str | None = None) -> list[Cell]:
    wb = ms.Workbook(model_path)
    header_row = int(cfg["model"].get("year_header_row", 1))
    sheets = [s for s in wb.sheetnames if s not in SKIP_SHEETS and not s.endswith("=>>>") and (only_sheet is None or s == only_sheet)]
    year_cols: dict[str, dict[int, int]] = {}
    for sheet in wb.sheetnames:
        _, hdr = wb.row(sheet, header_row)
        year_cols[sheet] = ms.year_columns(hdr, set(range(1990, 2101)))
    pipe = pipeline_claims(cfg, wb)
    man = manual_claims(manual, wb, year_cols)
    cells: list[Cell] = []
    for sheet in sheets:
        wb.load_sheet(sheet)
        ycols = year_cols[sheet]
        col_year = {c: y for y, c in ycols.items()}
        scan_cols = sorted(col_year) if ycols else list(range(2, ms.Workbook.MAX_COL + 1))
        for r in range(1, wb.max_row(sheet) + 1):
            if (sheet, r) not in wb._rows:
                break
            frow, vrow = wb.row(sheet, r)
            if r == header_row and ycols:
                continue
            label = str(vrow[0])[:60] if vrow and vrow[0] is not None else ""
            for c in scan_cols:
                if c - 1 >= len(frow):
                    break
                f, v = frow[c - 1], vrow[c - 1]
                if isinstance(f, str) and f.startswith("="):
                    continue
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                if col_year.get(c) is not None and v == col_year[c]:
                    continue                                   # a repeated year header inside the sheet
                key = (sheet, r, c)
                if key in pipe:
                    status, claim = "pipeline", pipe[key]
                elif key in man:
                    status, claim = "manual", man[key]
                else:
                    status, claim = "unaccounted", ""
                cells.append(Cell(sheet, r, c, col_year.get(c), float(v), label, status, claim))
    return cells


def report(cells: list[Cell], top: int = 40, verbose: bool = False) -> str:
    lines = [f"{'sheet':<34} {'numbers':>8} {'pipeline':>9} {'manual':>8} {'unaccounted':>12}"]
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in cells:
        per[c.sheet][c.status] += 1
        per[c.sheet]["all"] += 1
    tot = defaultdict(int)
    for sheet, d in per.items():
        lines.append(f"{sheet[:34]:<34} {d['all']:>8} {d['pipeline']:>9} {d['manual']:>8} {d['unaccounted']:>12}")
        for k, v in d.items():
            tot[k] += v
    lines.append(f"{'TOTAL':<34} {tot['all']:>8} {tot['pipeline']:>9} {tot['manual']:>8} {tot['unaccounted']:>12}")
    rows: dict[tuple[str, int], list[Cell]] = defaultdict(list)
    for c in cells:
        if c.status == "unaccounted":
            rows[(c.sheet, c.row)].append(c)
    if rows:
        lines.append("")
        lines.append(f"unaccounted rows: {len(rows)} (top {top} by cells)")
        for (sheet, row), cs in sorted(rows.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:top]:
            years = sorted(c.year for c in cs if c.year)
            span = f"{years[0]}–{years[-1]}" if years else f"cols {get_column_letter(min(c.col for c in cs))}–{get_column_letter(max(c.col for c in cs))}"
            lines.append(f"  {sheet[:28]:<28} r{row:<5} {len(cs):>3} cells  {span:<11} {cs[0].label[:50]}")
    if verbose:
        lines.append("")
        for c in cells:
            if c.status == "unaccounted":
                lines.append(f"  {c.sheet}!{get_column_letter(c.col)}{c.row} {c.year} {c.value} {c.label[:40]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", type=Path)
    ap.add_argument("--map", type=Path, default=ms.DEFAULT_MAP)
    ap.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    ap.add_argument("--sheet")
    ap.add_argument("--csv", type=Path, help="write every unaccounted cell here")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any number is unaccounted")
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(args.map.read_text(encoding="utf-8"))
    manual = yaml.safe_load(args.manual.read_text(encoding="utf-8")) if args.manual.exists() else {"inputs": []}
    model_path = args.model or Path(cfg["model"]["default_file"])
    cells = scan(model_path, cfg, manual, args.sheet)
    print(report(cells, args.top, args.verbose))
    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sheet", "cell", "row", "year", "value", "label", "status", "claim"])
            for c in cells:
                if c.status == "unaccounted":
                    w.writerow([c.sheet, f"{get_column_letter(c.col)}{c.row}", c.row, c.year, c.value, c.label, c.status, c.claim])
        print(f"written {args.csv}")
    return 1 if args.strict and any(c.status == "unaccounted" for c in cells) else 0


if __name__ == "__main__":
    sys.exit(main())
