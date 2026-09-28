"""Months in which the CPI shows a utility-tariff change (TARIFF_CHANGE_MONTHS), derived from
the BNS item-level CPI already in the pipeline -- no download.

WHAT IT MEASURES: the month in which a change of a regulated utility price reached the prices
BNS registers for the CPI (month-on-month index of the item), NOT the date a regulator decided
it. Decisions (TARIFF_DECISIONS, scripts/fetchers/krem_tariffs.py) usually take effect on the 1st
of a month and are registered in that month's CPI; a decision taking effect mid-month, or one
for a single city, shows up as a smaller move spread over two months. The CPI item is a national
average of the regional capitals' tariffs weighted by population, so a large change in Almaty
alone moves the national «Холодная вода» by a fraction of its size.

Input: data/processed/dims/cpi_detail_mom.csv (CPI_DETAIL_MOM, BNS Т-15-02-М, national rows;
index, previous month = 100). The regional rows of that file carry only TOTAL, FOOD, NONFOOD and
SERVICES -- no utility items -- so the detector is national only.

Series (national item slugs of CPI_DETAIL_MOM, chained where BNS renamed the item when it
re-based the basket; verified 2026-09-27, 2004-07 to 2026-08, 266 months each unless noted):
    ELECTRICITY   elektroenergiya (-2025-12), elektroenergiya_obshchiy (2026-01-)
    HOT_WATER     goryachaya_voda (-2026-01), goryachaya_voda_za_1_kub_metr (2026-02-)
    COLD_WATER    kholodnaya_voda (-2026-01), kholodnaya_voda_za_1_kub_metr (2026-02-)
    HEATING       otoplenie_tsentralnoe (-2026-01), otoplenie_tsentralnoe_za_1_gkal (2026-02-)
    SEWERAGE      kanalizatsiya (-2020-12), vodootvedenie (2021-01 to 2026-01),
                  vodootvedenie_za_1_kub_metr (2026-02-)
    NETWORK_GAS   gaz (-2008-02), gazosnabzhenie (2008-01 to 2020-12),
                  gaz_transportiruemyy_po_raspredelitelnym_setyam (2021-01-)
    LPG           gaz_szhizhennyy_v_ballonakh (2021-01 to 2025-12), szhizhennyy_gaz (2026-01-)
    GARBAGE       sbor_musora (-2020-12), vyvoz_musora (2021-01-)
Where two slugs cover the same month (gaz and gazosnabzhenie in 2008-01/02) the later one in
the list wins.

A month is flagged when |index - 100| >= `threshold_pct` (default 3.0) or, for smaller moves,
when the robust z-score (x - median) / (1.4826 * MAD) over the item's whole history is at least
`z_threshold` (default 5.0) and |index - 100| >= `min_pct` (default 1.5). Both directions are
kept (cuts: 2019-01/02 after the tariff reductions of January 2019, 2020-04/05 COVID relief).
value = the month-on-month change in % (index - 100). Verified examples (national m/m, %):
ELECTRICITY 2023-08 +6.7, 2024-03 +5.9; COLD_WATER 2023-08 +13.1, 2025-02 +29.2;
HEATING 2023-11 +16.1; NETWORK_GAS 2025-08 +24.1, 2026-08 +29.5; HOT_WATER 2019-02 -6.6.
"""
from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

CPI_FILE = dims.PROCESSED_ROOT / "cpi_detail_mom.csv"
CHAINS = {
    "ELECTRICITY": ("Электроэнергия", ["elektroenergiya", "elektroenergiya_obshchiy"]),
    "HOT_WATER": ("Горячая вода", ["goryachaya_voda", "goryachaya_voda_za_1_kub_metr"]),
    "COLD_WATER": ("Холодная вода", ["kholodnaya_voda", "kholodnaya_voda_za_1_kub_metr"]),
    "HEATING": ("Отопление центральное", ["otoplenie_tsentralnoe", "otoplenie_tsentralnoe_za_1_gkal"]),
    "SEWERAGE": ("Водоотведение (канализация)", ["kanalizatsiya", "vodootvedenie", "vodootvedenie_za_1_kub_metr"]),
    "NETWORK_GAS": ("Газ сетевой", ["gaz", "gazosnabzhenie", "gaz_transportiruemyy_po_raspredelitelnym_setyam"]),
    "LPG": ("Газ сжиженный", ["gaz_szhizhennyy_v_ballonakh", "szhizhennyy_gaz"]),
    "GARBAGE": ("Вывоз мусора", ["sbor_musora", "vyvoz_musora"]),
}


def load_cpi(path: Path = CPI_FILE) -> dict[str, dict[str, float]]:
    """{item_code: {date: index}} of the national rows."""
    if not path.exists():
        raise validation.StructuralChangeError(
            f"tariff_jumps: {path} is missing -- run update_dims --only CPI_DETAIL_MOM first")
    out: dict[str, dict[str, float]] = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("region") or dims.NATIONAL) != dims.NATIONAL or r["value"] in ("", "nan"):
                continue
            out.setdefault(r["item_code"], {})[r["date"]] = float(r["value"])
    return out


def chain(cpi: dict[str, dict[str, float]], slugs: list[str]) -> dict[str, tuple[float, str]]:
    """{date: (index, slug)}, later slugs overriding earlier ones on shared months."""
    out: dict[str, tuple[float, str]] = {}
    for slug in slugs:
        for d, v in cpi.get(slug, {}).items():
            out[d] = (v, slug)
    return out


def detect(series: dict[str, tuple[float, str]], threshold_pct: float = 3.0, z_threshold: float = 5.0,
           min_pct: float = 1.5) -> list[tuple[str, float, float | None, str, str]]:
    """[(date, change %, robust z or None, rule, slug)] of the flagged months."""
    changes = {d: v - 100.0 for d, (v, _) in series.items()}
    if not changes:
        return []
    vals = list(changes.values())
    med = statistics.median(vals)
    mad = statistics.median(abs(x - med) for x in vals) * 1.4826
    out = []
    for d in sorted(changes):
        x = changes[d]
        z = (x - med) / mad if mad > 0 else None
        if abs(x) >= threshold_pct:
            rule = f"|м/м| >= {threshold_pct:g}%"
        elif z is not None and abs(z) >= z_threshold and abs(x) >= min_pct:
            rule = f"робастный z >= {z_threshold:g} и |м/м| >= {min_pct:g}%"
        else:
            continue
        out.append((d, round(x, 2), None if z is None else round(z, 1), rule, series[d][1]))
    return out


def fetch(ds: dict) -> tuple[list[dict], dict]:
    cpi = load_cpi()
    latest = max(d for s in cpi.values() for d in s)
    threshold = float(ds.get("threshold_pct", 3.0))
    z_thr = float(ds.get("z_threshold", 5.0))
    min_pct = float(ds.get("min_pct", 1.5))
    records, warnings, stale = [], [], []
    for code, (name, slugs) in CHAINS.items():
        series = chain(cpi, slugs)
        if not series:
            raise validation.StructuralChangeError(
                f"STRUCTURAL CHANGE DETECTED in tariff_jumps: none of {slugs} is in CPI_DETAIL_MOM\n"
                f"ACTION REQUIRED: find the renamed item in {CPI_FILE} and extend CHAINS in scripts/fetchers/tariff_jumps.py")
        if max(series) < latest:
            stale.append(f"{code} ends {max(series)} (CPI to {latest}): BNS may have renamed the item")
        for d, x, z, rule, slug in detect(series, threshold, z_thr, min_pct):
            records.append({
                "date": d, "region": dims.NATIONAL, "item_code": code,
                "item_name": f"{name}: изменение цены в ИПЦ м/м {x:+.1f}% ({rule}"
                             + (f"; z={z:+.1f}" if z is not None else "") + f"; ряд {slug}) -- "
                             "наблюдаемое в ИПЦ изменение тарифа, не дата решения",
                "value": x})
    if stale:
        warnings.append("; ".join(stale))
    if not records:
        raise validation.StructuralChangeError("tariff_jumps: no month flagged in any utility series -- check CPI_DETAIL_MOM")
    records.sort(key=lambda r: (r["item_code"], r["date"]))
    return records, {"frequency": ds["frequency"], "source_url": str(CPI_FILE.relative_to(dims.REPO_ROOT)),
                     "dataset_id": "derived from CPI_DETAIL_MOM", "note": ds.get("note", ""),
                     "transformation": "percent change, month on month", "warnings": warnings}
