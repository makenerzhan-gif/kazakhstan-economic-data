#!/usr/bin/env python3
"""Check (and, with --apply, load) the GDP model workbook against the unified dataset.

The contract lives in config/model_map.yaml. Kinds of entry:

  variable:       a scalar pipeline series (macro_long.csv) and the workbook cells that
                  should carry its annual value — `targets: [{sheet, row, col_offset?}]`
  dims_variable:  an item-level series (macro_dims_long.csv); one sheet, and one of
                    rows_by_item: {item_code: row}            explicit rows
                    item_column + row_range                   item codes read from a column of the
                                                              sheet (`item_aliases` maps a code to
                                                              the label the sheet uses, GVA -> ВДС)
                    blocks: {item_code: [first, last]} +      rows of REGIONS under each item; the
                    region_column                             region names are read from the sheet and
                                                              resolved through dictionaries/regions.csv
                  `region` (default national) picks the region for the first two forms.

Year columns come from the sheet's header row (row 1 by default) unless the entry
gives `year_columns: {2024: E, …}` explicitly — for sheets whose header is text.

The script annualises the series, reads the workbook once as formulas and once as
cached values, and reports one line per (cell, year):

  ok        the model already holds the pipeline value (within `tolerance`, or within
            `rel_tolerance` × the pipeline value — for series spanning several orders
            of magnitude, such as world prices from $0.3/kg to $30 000/t)
  diff      values differ; an INPUT cell would be rewritten by --apply
  control   values differ, but the cell is a formula — reported, never overwritten
  missing   the pipeline has no observation for that year, or the sheet has no such year

--apply writes only the `diff` INPUT cells, through a private Excel instance
(scripts/lib/excel_apply.ps1: full recalculation, save-as to --out), adds a cell
comment naming the variable and its source, and appends the change to the model's
own «Журнал_правок» sheet. The source workbook is never modified in place; --out is
required. Windows only, because the writer is Excel itself.

This is a local step, deliberately outside update_all.py: the model is a hand-run
Excel file on the analyst's disk, not a pipeline artefact.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import dims as dimslib  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = REPO_ROOT / "config" / "model_map.yaml"
DEFAULT_UNIFIED = REPO_ROOT / "data" / "unified" / "macro_long.csv"
DEFAULT_DIMS = REPO_ROOT / "data" / "unified" / "macro_dims_long.csv"
APPLIER = REPO_ROOT / "scripts" / "lib" / "excel_apply.ps1"
ANNUAL_RULES = ("last", "mean", "december", "sum")
NATIONAL = dimslib.NATIONAL


@dataclass
class Observation:
    date: str
    value: float
    source: str
    last_updated: str


@dataclass
class Check:
    mapping_id: str
    variable: str
    sheet: str
    cell: str
    year: int
    model: float | None
    pipeline: float | None
    is_formula: bool
    tolerance: float
    note: str = ""
    source: str = ""
    replace_formula: bool = False   # the author decided these cells are inputs: a formula there is stale, not logic
    rel_tolerance: float = 0.0      # share of the pipeline value; the wider of the two tolerances applies

    @property
    def status(self) -> str:
        if self.pipeline is None:
            return "missing"                        # nothing to compare against — never invent a value
        allowed = max(self.tolerance, self.rel_tolerance * abs(self.pipeline))
        if self.model is not None and abs(self.model - self.pipeline) <= allowed:
            return "ok"
        if self.is_formula and not self.replace_formula:
            return "control"
        return "diff"                               # an input (or an empty cell) --apply may write


# ---------------------------------------------------------------- unified dataset

def load_unified(path: Path) -> dict[str, list[Observation]]:
    """variable -> observations, sorted by date. Rows with a non-numeric value are skipped."""
    series: dict[str, list[Observation]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue
            series[row["variable"]].append(Observation(row["date"], value, row.get("source", ""), row.get("last_updated", "")))
    for obs in series.values():
        obs.sort(key=lambda o: o.date)
    return series


def load_unified_dims(path: Path) -> dict[tuple[str, str, str], list[Observation]]:
    """(variable, item_code, region) -> observations, sorted by date. Empty when the file is absent."""
    series: dict[tuple[str, str, str], list[Observation]] = defaultdict(list)
    if not path.exists():
        return series
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue
            series[(row["variable"], row["item_code"], row.get("region") or NATIONAL)].append(
                Observation(row["date"], value, row.get("source", ""), row.get("last_updated", "")))
    for obs in series.values():
        obs.sort(key=lambda o: o.date)
    return series


def annual_value(observations: list[Observation], year: int, rule: str) -> float | None:
    """One number for `year` from the observations dated inside it, or None when there are none."""
    if rule not in ANNUAL_RULES:
        raise ValueError(f"unknown annual rule {rule!r}; expected one of {ANNUAL_RULES}")
    inside = [o for o in observations if o.date[:4] == f"{year:04d}"]
    if rule == "december":
        inside = [o for o in inside if o.date[5:7] == "12"]
    if not inside:
        return None
    values = [o.value for o in inside]
    if rule == "mean":
        return sum(values) / len(values)
    if rule == "sum":
        return sum(values)
    return values[-1]           # last, december


def transform(value: float | None, scale: float = 1.0, offset: float = 0.0) -> float | None:
    return None if value is None else value * scale + offset


def year_columns(header_cells: list, wanted: set[int]) -> dict[int, int]:
    """{year: 1-based column} for the calendar years found in a header row's cached values."""
    found: dict[int, int] = {}
    for idx, cell in enumerate(header_cells, start=1):
        if isinstance(cell, (int, float)) and not isinstance(cell, bool) and float(cell).is_integer():
            year = int(cell)
            if year in wanted and year not in found:
                found[year] = idx
    return found


def normalise_code(cell) -> str | None:
    """An item code as it sits in a workbook column: numbers become two-digit strings."""
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return f"{int(cell):02d}"
    s = str(cell).strip()
    return s or None


def item_rows(column_cells: list, first_row: int, aliases: dict[str, str]) -> dict[str, int]:
    """{item_code: row} from a column of codes; `aliases` maps a code to the label the sheet uses."""
    by_label = {str(v).strip(): k for k, v in aliases.items()}
    rows: dict[str, int] = {}
    for offset, cell in enumerate(column_cells):
        code = normalise_code(cell)
        if code is None:
            continue
        code = by_label.get(code, code)
        rows.setdefault(code, first_row + offset)
    return rows


def region_rows(column_cells: list, first_row: int) -> dict[str, int]:
    """{region_code: row} from a column of region names (dictionaries/regions.csv); first hit wins."""
    rows: dict[str, int] = {}
    for offset, cell in enumerate(column_cells):
        if cell is None or not str(cell).strip():
            continue
        hit = dimslib.match_region(cell)
        if hit is not None:
            rows.setdefault(hit[0], first_row + offset)
    return rows


# ---------------------------------------------------------------- workbook

class Workbook:
    """The model opened twice: formulas (to tell inputs from controls) and cached values."""

    MAX_COL = 250

    def __init__(self, path: Path):
        self.path = path
        self.formulas = load_workbook(path, read_only=True)
        self.values = load_workbook(path, read_only=True, data_only=True)
        self._rows: dict[tuple[str, int], tuple[list, list]] = {}

    def row(self, sheet: str, row: int, max_col: int = MAX_COL) -> tuple[list, list]:
        """Formulas and cached values of one row (first MAX_COL columns), read once:
        a read-only worksheet scans from the top on every iter_rows call."""
        key = (sheet, row)
        if key not in self._rows:
            f = next(self.formulas[sheet].iter_rows(min_row=row, max_row=row, min_col=1, max_col=self.MAX_COL, values_only=True), ())
            v = next(self.values[sheet].iter_rows(min_row=row, max_row=row, min_col=1, max_col=self.MAX_COL, values_only=True), ())
            self._rows[key] = (list(f), list(v))          # an empty sheet gives ([], [])
        return self._rows[key]

    def column(self, sheet: str, col: int, first_row: int, last_row: int) -> list:
        return [r[0] for r in self.values[sheet].iter_rows(min_row=first_row, max_row=last_row, min_col=col, max_col=col, values_only=True)]

    def max_row(self, sheet: str) -> int:
        return self.values[sheet].max_row

    @property
    def sheetnames(self) -> list[str]:
        return list(self.values.sheetnames)

    def load_sheet(self, sheet: str) -> None:
        """Fill the row cache for a whole sheet in one pass (a whole-sheet scan through
        row() would re-read the sheet from the top for every row)."""
        fi = self.formulas[sheet].iter_rows(min_row=1, min_col=1, max_col=self.MAX_COL, values_only=True)
        vi = self.values[sheet].iter_rows(min_row=1, min_col=1, max_col=self.MAX_COL, values_only=True)
        for r, (f, v) in enumerate(zip(fi, vi), 1):
            self._rows.setdefault((sheet, r), (list(f), list(v)))


def _year_cols(m: dict, wb: Workbook, sheet: str, header_row: int, cache: dict) -> dict[int, int]:
    if "year_columns" in m:
        return {int(y): column_index_from_string(str(c)) for y, c in m["year_columns"].items()}
    if sheet not in cache:
        _, hdr = wb.row(sheet, header_row, 200)
        cache[sheet] = year_columns(hdr, set(range(1990, 2101)))
    return cache[sheet]


def _check_cell(wb: Workbook, m: dict, sheet: str, row: int, col: int, year: int, obs: list[Observation],
                scale: float, offset: float, tolerance: float, label: str, note: str) -> Check:
    frow, vrow = wb.row(sheet, row, col)
    formula, cached = frow[col - 1], vrow[col - 1]
    is_formula = isinstance(formula, str) and formula.startswith("=")
    model_val = float(cached) if isinstance(cached, (int, float)) and not isinstance(cached, bool) else None
    pipe_val = transform(annual_value(obs, year, m.get("annual", "last")), scale, offset)
    src = next((f"{o.source}, обновлено {o.last_updated}" for o in obs if o.date[:4] == f"{year:04d}"), "пайплайн")
    return Check(m["id"], label, sheet, f"{get_column_letter(col)}{row}", year, model_val, pipe_val, is_formula, tolerance, note, src,
                 bool(m.get("replace_formulas", False)), float(m.get("rel_tolerance", 0.0)))


def _dims_targets(m: dict, wb: Workbook) -> list[tuple[str, str, int]]:
    """[(item_code, region, row)] for a dims mapping, from whichever row form it uses."""
    sheet = m["sheet"]
    out: list[tuple[str, str, int]] = []
    if "blocks" in m:
        col = column_index_from_string(m["region_column"])
        for item, (first, last) in m["blocks"].items():
            cells = wb.column(sheet, col, int(first), int(last))
            out += [(str(item), region, row) for region, row in region_rows(cells, int(first)).items()]
        return out
    region = m.get("region", NATIONAL)
    rows = {str(k): int(v) for k, v in m.get("rows_by_item", {}).items()}
    if "item_column" in m:
        first, last = (int(x) for x in m["row_range"])
        col_cells = wb.column(sheet, column_index_from_string(m["item_column"]), first, last)
        for code, row in item_rows(col_cells, first, m.get("item_aliases", {})).items():
            rows.setdefault(code, row)
    return [(code, region, row) for code, row in rows.items()]


def run_checks(cfg: dict, series: dict[str, list[Observation]], wb: Workbook,
               dims_series: dict[tuple[str, str, str], list[Observation]] | None = None,
               only: set[str] | None = None) -> list[Check]:
    model_cfg = cfg["model"]
    header_row = int(model_cfg.get("year_header_row", 1))
    default_years = [int(y) for y in model_cfg["default_years"]]
    dims_series = dims_series or {}
    checks: list[Check] = []
    header_cache: dict[str, dict[int, int]] = {}
    for m in cfg["mappings"]:
        if only and m["id"] not in only:
            continue
        years = [int(y) for y in m.get("years", default_years)]
        scale, offset, tol = float(m.get("scale", 1.0)), float(m.get("offset", 0.0)), float(m.get("tolerance", 0.0))
        if "dims_variable" in m:
            sheet, var = m["sheet"], m["dims_variable"]
            cols = _year_cols(m, wb, sheet, header_row, header_cache)
            for code, region, row in sorted(_dims_targets(m, wb), key=lambda t: t[2]):
                obs = dims_series.get((var, code, region), [])
                if not obs:
                    continue                                  # sheet row with no pipeline series — not a check
                label = f"{var}[{code}]" if region == NATIONAL else f"{var}[{code}@{region}]"
                for year in years:
                    col = cols.get(year)
                    if col is None:
                        checks.append(Check(m["id"], label, sheet, f"?{row}", year, None, None, False, tol, "нет столбца года"))
                        continue
                    checks.append(_check_cell(wb, m, sheet, row, col + int(m.get("col_offset", 0)), year, obs, scale, offset, tol, label, m.get("note", "")))
        else:
            obs = series.get(m["variable"], [])
            for t in m["targets"]:
                sheet = t["sheet"]
                cols = _year_cols(m, wb, sheet, header_row, header_cache)
                t_scale, t_offset = float(t.get("scale", scale)), float(t.get("offset", offset))
                t_tol = float(t.get("tolerance", tol))
                for year in years:
                    col = cols.get(year)
                    if col is None:
                        checks.append(Check(m["id"], m["variable"], sheet, f"?{t['row']}", year, None, None, False, t_tol, "нет столбца года"))
                        continue
                    checks.append(_check_cell(wb, m, sheet, int(t["row"]), col + int(t.get("col_offset", 0)), year, obs, t_scale, t_offset, t_tol, m["variable"], t.get("note", "")))
    return checks


def format_report(checks: list[Check], verbose: bool = False) -> str:
    fmt = lambda v: "—" if v is None else f"{v:,.3f}"
    lines = [f"{'status':<8} {'variable':<44} {'sheet!cell':<36} {'year':>4} {'model':>18} {'pipeline':>18} {'diff':>12}"]
    for c in checks:
        if not verbose and c.status == "ok":
            continue
        diff = "" if c.model is None or c.pipeline is None else f"{c.model - c.pipeline:+,.3f}"
        lines.append(f"{c.status:<8} {c.variable[:44]:<44} {(c.sheet + '!' + c.cell)[:36]:<36} {c.year:>4} {fmt(c.model):>18} {fmt(c.pipeline):>18} {diff:>12}")
    per_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in checks:
        per_map[c.mapping_id][c.status] += 1
    lines.append("")
    lines.append(f"{'mapping':<34} {'ok':>5} {'diff':>5} {'ctrl':>5} {'miss':>5}")
    for mid, counts in per_map.items():
        lines.append(f"{mid:<34} {counts['ok']:>5} {counts['diff']:>5} {counts['control']:>5} {counts['missing']:>5}")
    totals = defaultdict(int)
    for c in checks:
        totals[c.status] += 1
    lines.append("summary: " + ", ".join(f"{k}={totals[k]}" for k in ("ok", "diff", "control", "missing")))
    return "\n".join(lines)


# ---------------------------------------------------------------- apply

def build_ops(checks: list[Check], series: dict, cfg: dict, journal_next_row: int, today: str) -> list[dict]:
    """JSON ops for excel_apply.ps1: rewrite `diff` inputs, comment them, append journal rows."""
    ops, journal = [], []
    for c in checks:
        if c.status != "diff":
            continue
        src = c.source or next((f"{o.source}, обновлено {o.last_updated}" for o in series.get(c.variable, []) if o.date[:4] == f"{c.year:04d}"), "пайплайн")
        ops.append({"op": "value", "sheet": c.sheet, "cell": c.cell, "value": c.pipeline})
        was = "пусто" if c.model is None else f"{c.model:,.3f}"
        how = " Формула заменена значением по решению автора модели (replace_formulas в model_map.yaml)." if c.is_formula else ""
        ops.append({"op": "comment", "sheet": c.sheet, "cell": c.cell,
                    "text": f"Синхронизация {today}: {c.variable} из пайплайна kazakhstan-economic-data ({src}). Было {was}.{how}"})
        journal.append([c.sheet, c.cell, c.model, c.pipeline, f"пайплайн: {c.variable} ({src})" + (" — формула заменена фактом" if c.is_formula else "")])
    if journal:
        header = [[f"— Синхронизация с пайплайном {today}: {len(journal)} ячеек —", None, None, None, None]]
        ops.append({"op": "table", "sheet": cfg["model"]["journal_sheet"], "cell": f"A{journal_next_row}", "rows": header + journal, "header": False})
    return ops


def apply_ops(ops: list[dict], src: Path, out: Path) -> str:
    if sys.platform != "win32":
        raise SystemExit("--apply needs Excel (Windows); run the check on any platform, apply on the analyst's machine")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(ops, f, ensure_ascii=False)
        edits = f.name
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(APPLIER),
           "-Src", str(src), "-Dst", str(out), "-Edits", edits]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"excel_apply.ps1 failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


# ---------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", type=Path, help="model workbook (default: model.default_file from the map)")
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--unified", type=Path, default=DEFAULT_UNIFIED)
    ap.add_argument("--dims", type=Path, default=DEFAULT_DIMS)
    ap.add_argument("--only", nargs="*", help="mapping ids to check (default: all)")
    ap.add_argument("--verbose", action="store_true", help="print the ok lines too")
    ap.add_argument("--apply", action="store_true", help="write differing INPUT cells to --out")
    ap.add_argument("--out", type=Path, help="where --apply saves the updated workbook (never the source)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any diff or control mismatch remains")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(args.map.read_text(encoding="utf-8"))
    model_path = args.model or Path(cfg["model"]["default_file"])
    if not model_path.exists():
        raise SystemExit(f"model workbook not found: {model_path}")
    if args.apply and (args.out is None or args.out.resolve() == model_path.resolve()):
        raise SystemExit("--apply requires --out, and it must differ from the source workbook")

    series = load_unified(args.unified)
    dims_series = load_unified_dims(args.dims)
    wb = Workbook(model_path)
    checks = run_checks(cfg, series, wb, dims_series, set(args.only) if args.only else None)
    print(format_report(checks, verbose=args.verbose))

    if args.apply:
        ops = build_ops(checks, series, cfg, wb.max_row(cfg["model"]["journal_sheet"]) + 1, date.today().strftime("%d.%m.%Y"))
        if not ops:
            print("nothing to apply")
        else:
            print(apply_ops(ops, model_path, args.out))
            print(f"saved {args.out}")
    if args.strict and any(c.status in ("diff", "control") for c in checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
