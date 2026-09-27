"""BNS external trade by commodity group -- the dimensional view of the export and import
workbooks (elements 446905 and 446906; the scalar EXPORTS, OIL_EXPORTS_* are derived from
the export datasets, IMPORTS reads the import file's national row in fetchers/bns.py). See
the module comment above `_parse_trade_workbook` in fetchers/bns.py for the file's layout:
one sheet per year, row 4 the national total, then 21 regional blocks -- a heading row with
the region's total, then its flat 6-digit HS lines; each month spans [tonnes, additional
unit, thousand USD].

Groups are HS (ТН ВЭД ЕАЭС) prefixes listed in a dictionary: dictionaries/hs_export_groups.csv
(the GDP model's commodity groups: a 4-digit heading, a chapter, a 6-digit line or several),
hs_chapters.csv (the 96 chapters present, 01-97 and 99 «прочие товары»), hs_sections.csv (the
21 sections). A group is the sum of its 6-digit lines, legitimate only while the lines
reproduce the published totals, re-checked every month: all lines against the national row
(else the month keeps TOTAL only; a broad failure stops the dataset) and, for the regional
datasets (`by_region: true`), each region's lines against its heading row (else that region
keeps TOTAL only for the month). TOTAL is always a published row, never a sum.

Each workbook is read once per process for every dictionary its datasets use (the import
file is ~140 MB); the raw file is archived once per day under EXPORTS / IMPORTS, the names
the files have always had in data/raw/bns.

Region: the region of the exporting/importing company's registration, as BNS compiles it --
not necessarily where the good was produced or consumed (crude oil leaves under Atyrau and
Astana-registered companies).
"""
from __future__ import annotations

import io
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, raw_store, validation  # noqa: E402
from fetchers import bns  # noqa: E402

FLOWS = {"exports": {"element": 446905, "raw_id": "EXPORTS"},
         "imports": {"element": 446906, "raw_id": "IMPORTS"}}
UNIT_OFFSET = {"tonnes": 0, "usd": 2}      # each month spans [tonnes, additional unit, thousand USD]
# How close the 6-digit lines must come to a published total. Exact in almost every month;
# the import file's г. Алматы block falls short of its heading by up to 66 thousand USD
# (0.003 %) in Feb, Mar, Nov and Dec 2023 -- a few suppressed lines, not a layout change.
TOLERANCE = 1e-4
_SCANS: dict[str, "Scan"] = {}


def _url(flow: str) -> str:
    return f"https://stat.gov.kz/api/iblock/element/{FLOWS[flow]['element']}/file/ru/"


def _structural(ds: dict, what: str, expected, actual) -> None:
    element = FLOWS[ds.get("flow", "exports")]["element"]
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in bns/{ds['id']} (element {element})",
        f"WHAT CHANGED: {what}", f"EXPECTED: {expected}", f"ACTUAL: {actual}",
        "ACTION REQUIRED: open the trade workbook, compare with the layout described in "
        "scripts/fetchers/bns_trade.py and fetchers/bns.py, update the parser or "
        "the dictionary, then re-run.",
    ]))


def load_groups(name: str) -> list[dict]:
    """Dictionary entries with their HS prefix lists ('7208|7209' -> ['7208', '7209'])."""
    out = []
    for e in dims.load_dictionary(name):
        out.append({**e, "prefixes": [p.strip() for p in (e.get("hs") or "").split("|") if p.strip()]})
    return out


def _content(flow: str, today: date) -> tuple[bytes, str]:
    """(workbook bytes, the raw file holding them). bns._download caches per process (the
    scalar IMPORTS reads the same import workbook), raw_store stores identical bytes once per day."""
    url = _url(flow)
    content = bns._download(url)
    raw_id = FLOWS[flow]["raw_id"]
    path = raw_store.save_raw_bytes("bns", raw_id, today, "xlsx", content)
    raw_store.write_download_manifest("bns", raw_id, today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": url, "element_id": FLOWS[flow]["element"],
        "raw_file": path.name, "note": f"read by the {flow.upper()}_*_BY_* datasets of config/dims.yaml (fetcher bns_trade)"})
    return content, path.name


class Scan:
    """One pass over a trade workbook for several dictionaries at once (the import file is
    ~140 MB; each pass takes a minute or two).

    Per unit ('tonnes', 'usd') and month (ISO date):
      national[iso]                    the published national row (row 4)
      region_total[iso][region]        the published region heading row
      sums[iso][(dict, region, code)]  the dictionary group's 6-digit lines within the region
      national_sums[iso][(dict, code)] … over all regions, summed in file order
      verified_national / verified_region: the months whose lines reproduce the published
        national total / the region's heading row (a national / regional group sum is kept only then).
    """

    def __init__(self):
        self.national: dict[str, dict[str, float]] = {"tonnes": {}, "usd": {}}
        self.region_total: dict[str, dict[str, dict[str, float]]] = {"tonnes": {}, "usd": {}}
        self.sums: dict[str, dict[str, dict[tuple, float]]] = {"tonnes": {}, "usd": {}}
        self.national_sums: dict[str, dict[str, dict[tuple, float]]] = {"tonnes": {}, "usd": {}}
        self.verified_national: dict[str, set[str]] = {"tonnes": set(), "usd": set()}
        self.verified_region: dict[str, set[tuple[str, str]]] = {"tonnes": set(), "usd": set()}
        self.skipped: list[tuple] = []


def scan(content: bytes, dictionaries: dict[str, list[dict]], ds: dict) -> Scan:
    """Read every data sheet once. A month whose 6-digit lines do not add up to the published
    national total is left unverified (the group sums are withheld, the published row stays);
    likewise a region whose lines miss its heading row. Region headings are matched to
    dictionaries/regions.csv -- an unknown one is a structural change."""
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    out = Scan()
    checked = 0
    by_prefix = [(name, p, g["code"]) for name, groups in dictionaries.items() for g in groups for p in g["prefixes"]]
    target_cache: dict[str, list[tuple[str, str]]] = {}
    data_sheets = [s for s in wb.sheetnames if s not in ("Метаданные", "Показатель")]
    if not data_sheets:
        # Seen on the CI runner 2026-09-15: a 23 KB workbook with only the two description
        # sheets and a per-region annual summary -- BNS was serving a stub while the 65 MB
        # export was being regenerated. Stop loudly; the previous processed data stays.
        _structural(ds, f"the workbook has no data sheets ({len(content) // 1024} KB, sheets {wb.sheetnames})",
                    "one sheet per year ('2019', …) plus the current partial year", "only description sheets -- a stub served during regeneration? retry later")
    for sheet_name in data_sheets:
        ws = wb[sheet_name]
        header_row = national_row = None
        region = None
        sums: dict[tuple, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        nat_sums: dict[tuple, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        region_heads: dict[str, tuple] = {}
        region_sums: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        all_sums: dict[int, float] = defaultdict(float)
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 1:
                header_row = row
                continue
            if i == 3:
                national_row = row
                label = (row[0] or "").strip() if row and row[0] else ""
                if label != bns.TRADE_TOTAL_ROW_LABEL:
                    _structural(ds, f"row 4 of sheet {sheet_name!r} is not the national total", bns.TRADE_TOTAL_ROW_LABEL, label)
                continue
            if i < 4 or not row or row[0] is None:
                continue
            code = str(row[0]).strip()
            if not code.isdigit():
                hit = dims.match_region(code)
                if hit is None and not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in row[1:]):
                    continue                              # a footnote («*Предварительные данные.»)
                if hit is None or hit[0] == dims.NATIONAL:
                    _structural(ds, f"sheet {sheet_name!r} row {i + 1}: {code!r} is neither a 6-digit code nor a region",
                                "a region heading from dictionaries/regions.csv", code)
                region = hit[0]
                region_heads[region] = row
                continue
            if len(code) != 6:
                _structural(ds, f"sheet {sheet_name!r} row {i + 1} has a {len(code)}-digit code {code!r}",
                            "a flat 6-digit breakdown (mixed lengths would double-count)", code)
            if region is None:
                _structural(ds, f"sheet {sheet_name!r} row {i + 1}: a product line before any region heading", "a region heading first", code)
            if code not in target_cache:
                target_cache[code] = [(name, g) for name, p, g in by_prefix if code.startswith(p)]
            targets = target_cache[code]
            rs = region_sums[region]
            for col, value in enumerate(row):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                all_sums[col] += value
                rs[col] += value
                for name, g in targets:
                    sums[(name, region, g)][col] += value
                    nat_sums[(name, g)][col] += value        # in file order, as before the regional split
        if header_row is None or national_row is None:
            _structural(ds, f"sheet {sheet_name!r} has no header/national rows", "header at row 2, national total at row 4", sheet_name)
        for col_idx, cell in enumerate(header_row):
            m = bns.MONTH_HEADER_RE.match(str(cell).strip()) if cell else None
            month = bns.RU_MONTHS.get(m.group(1).lower()) if m else None
            if not month:
                continue
            iso = f"{int(m.group(2)):04d}-{month:02d}-01"
            for unit, offset in UNIT_OFFSET.items():
                col = col_idx + offset
                national = national_row[col] if col < len(national_row) else None
                if not isinstance(national, (int, float)) or not national:
                    continue
                checked += 1
                out.national[unit][iso] = float(national)
                out.region_total[unit][iso] = {}
                for reg, head in region_heads.items():
                    v = head[col] if col < len(head) else None
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        out.region_total[unit][iso][reg] = float(v)
                        if abs(region_sums[reg].get(col, 0.0) - v) <= max(abs(v) * TOLERANCE, 1e-6):
                            out.verified_region[unit].add((iso, reg))
                    elif not region_sums[reg].get(col):
                        out.verified_region[unit].add((iso, reg))       # a region with no trade that month
                out.sums[unit][iso] = {k: v[col] for k, v in sums.items() if col in v}
                out.national_sums[unit][iso] = {k: v[col] for k, v in nat_sums.items() if col in v}
                if abs(all_sums.get(col, 0.0) - national) > abs(national) * TOLERANCE:
                    out.skipped.append((sheet_name, m.group(0), unit, round((all_sums.get(col, 0.0) / national - 1) * 100, 4)))
                    continue
                out.verified_national[unit].add(iso)
    if checked and len(out.skipped) > checked * 0.1:
        _structural(ds, f"regional product rows failed to sum to the national total in {len(out.skipped)} of {checked} month/unit checks",
                    "at most a couple of isolated months (2 of 180 as of 2026-09-01)", out.skipped[:8])
    if out.skipped:
        print(f"bns/{ds['id']}: skipped {len(out.skipped)} unverifiable month(s): {out.skipped}", file=sys.stderr)
    if not out.verified_national["usd"]:
        _structural(ds, "no month passed the partition check", "monthly national totals matched by the regional rows", data_sheets)
    return out


def national_groups(sc: Scan, name: str, groups: list[dict], unit: str) -> dict[str, dict[str, float]]:
    """{iso month: {group code: value}}: the group summed over the regions, and TOTAL the
    published national row; an unverified month keeps TOTAL only."""
    out = {}
    for iso, national in sc.national[unit].items():
        vals = {}
        if iso in sc.verified_national[unit]:
            summed = sc.national_sums[unit].get(iso, {})
            for g in groups:
                if g["prefixes"]:
                    vals[g["code"]] = summed.get((name, g["code"]), 0.0)
        vals["TOTAL"] = national
        out[iso] = vals
    return out


def regional_groups(sc: Scan, name: str, groups: list[dict], unit: str) -> dict[str, dict[tuple[str, str], float]]:
    """{iso month: {(region, group code): value}}: the national rows of national_groups plus,
    per region, TOTAL = its published heading row and each group's lines within the region
    (kept when the region's lines reproduce its heading row, even in a month whose national
    row is off -- September 2022, config/source_issues.yaml trade_national_row_2022_09)."""
    out = {}
    nat = national_groups(sc, name, groups, unit)
    for iso, vals in nat.items():
        month: dict[tuple[str, str], float] = {(dims.NATIONAL, c): v for c, v in vals.items()}
        sums = sc.sums[unit].get(iso, {})
        for reg, total in sc.region_total[unit].get(iso, {}).items():
            month[(reg, "TOTAL")] = total
            if (iso, reg) not in sc.verified_region[unit]:
                continue
            for g in groups:
                if g["prefixes"]:
                    month[(reg, g["code"])] = sums.get((name, reg, g["code"]), 0.0)
        out[iso] = month
    return out


def parse_groups(content: bytes, groups: list[dict], ds: dict) -> dict[str, dict[str, dict[str, float]]]:
    """{unit: {iso month: {group code: value}}} for 'tonnes' and 'usd', every sheet of the
    workbook; months whose regional rows do not reproduce the national total keep TOTAL only."""
    sc = scan(content, {"_": groups}, ds)
    return {unit: national_groups(sc, "_", groups, unit) for unit in UNIT_OFFSET}


def _flow_dictionaries(flow: str) -> dict[str, list[dict]]:
    """Every dictionary a bns_trade dataset of this flow uses, so the workbook is read once."""
    names = {d["dictionary"] for d in dims.load_config()["datasets"]
             if d.get("fetcher") == "bns_trade" and d.get("flow", "exports") == flow}
    return {n: load_groups(n) for n in sorted(names)}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    """ds['flow'] is 'exports' (default) or 'imports', ds['measure'] 'usd' (thousand USD) or
    'tonnes'; ds['by_region'] adds the regions (national rows included)."""
    today = date.today()
    flow = ds.get("flow", "exports")
    content, origin = _content(flow, today)
    if flow not in _SCANS:
        dictionaries = _flow_dictionaries(flow)
        dictionaries.setdefault(ds["dictionary"], load_groups(ds["dictionary"]))
        _SCANS[flow] = scan(content, dictionaries, ds)
    sc = _SCANS[flow]
    groups = load_groups(ds["dictionary"])
    names = {g["code"]: g["name_ru"] for g in groups}
    if ds.get("by_region"):
        by_month = regional_groups(sc, ds["dictionary"], groups, ds["measure"])
        records = [{"date": iso, "region": reg, "item_code": code, "item_name": names[code], "value": v}
                   for iso in sorted(by_month) for (reg, code), v in by_month[iso].items()]
    else:
        by_month = national_groups(sc, ds["dictionary"], groups, ds["measure"])
        records = [{"date": iso, "region": dims.NATIONAL, "item_code": code, "item_name": names[code], "value": v}
                   for iso in sorted(by_month) for code, v in by_month[iso].items()]
    element = FLOWS[flow]["element"]
    return records, {"frequency": "monthly", "source_url": _url(flow), "dataset_id": f"{element},measure={ds['measure']}",
                     "note": ds.get("note", "") + f" Raw file: {origin}.", "warnings": [], "raw_file": origin}
