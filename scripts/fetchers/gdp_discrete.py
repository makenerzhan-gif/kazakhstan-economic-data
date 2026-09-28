"""Discrete-quarter GDP volume indices derived from BNS's year-to-date quarterly tables
(added 2026-09-27; derived, no download).

BNS publishes the discrete-quarter GDP (QNA_*, «ВВП методом производства (на квартальной
основе)», elements 283160-283162) about four months after the quarter -- on 2026-09-27 they
end at 2026 Q1 -- while the year-to-date tables 4439/4440 already carry January-June 2026
(GVA_*_BY_SECTION_QUARTERLY). In previous-year prices the year-to-date index is a
weighted mean of the quarters, so the quarter k index is

    I_k = (I_ytd,k · N_ytd,k,t−1 − I_ytd,k−1 · N_ytd,k−1,t−1) / (N_ytd,k,t−1 − N_ytd,k−1,t−1)

with N the nominal year-to-date values of the previous year (I_1 = I_ytd,1). Both indices are
published with one decimal, so the GDP Q2 value carries about ±0.15 pp of rounding. Caveats:
this is the 4439/4440 (operational/reported) basis, not the QNA basis, and must not be spliced
with QNA_* without a note; Q4 = year − 9 months carries the annual-survey residual of table
4439 (flag it); Q2 and Q3 are clean. 2026 Q2: GDP 105.18 (band 105.04-105.33).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

QUARTER_OF = {"01": 1, "04": 2, "07": 3, "10": 4}
START = {1: "01", 2: "04", 3: "07", 4: "10"}


def discrete(index_ytd: dict[tuple[str, str], float], nominal_ytd: dict[tuple[str, str], float]) -> list[dict]:
    """{(date, item): YTD index}, {(date, item): YTD nominal} -> discrete-quarter indices."""
    out = []
    for (d, item), i_k in sorted(index_ytd.items()):
        year, k = int(d[:4]), QUARTER_OF[d[5:7]]
        if k == 1:
            out.append((d, item, i_k))
            continue
        prev_d = f"{year}-{START[k - 1]}-01"
        n_k = nominal_ytd.get((f"{year - 1}-{START[k]}-01", item))
        n_km1 = nominal_ytd.get((f"{year - 1}-{START[k - 1]}-01", item))
        i_km1 = index_ytd.get((prev_d, item))
        if None in (n_k, n_km1, i_km1) or n_k - n_km1 <= 0:
            continue
        out.append((d, item, (i_k * n_k - i_km1 * n_km1) / (n_k - n_km1)))
    return [{"date": d, "region": dims.NATIONAL, "item_code": item, "item_name": item, "value": round(v, 3)} for d, item, v in out]


def fetch(ds: dict) -> tuple[list[dict], dict]:
    index = {}
    names = {}
    for r in dims.load_processed("GVA_VOLUME_INDEX_BY_SECTION_QUARTERLY"):
        if r["region"] == dims.NATIONAL:
            index[(r["date"], r["item_code"])] = float(r["value"])
            names[r["item_code"]] = r["item_name"]
    nominal = {(r["date"], r["item_code"]): float(r["value"]) for r in dims.load_processed("GVA_NOMINAL_BY_SECTION_QUARTERLY")
               if r["region"] == dims.NATIONAL}
    if not index or not nominal:
        raise validation.StructuralChangeError("gdp_discrete: run GVA_VOLUME_INDEX_BY_SECTION_QUARTERLY and GVA_NOMINAL_BY_SECTION_QUARTERLY first")
    records = discrete(index, nominal)
    for r in records:
        q = QUARTER_OF[r["date"][5:7]]
        r["item_name"] = f"{names.get(r['item_code'], r['item_code'])} — {q} квартал к {q} кварталу прошлого года" + (
            " (IV квартал = год − 9 месяцев, с годовой досчётной поправкой)" if q == 4 else "")
    return records, {"frequency": "quarterly", "source_url": "", "dataset_id": "derived", "note": ds.get("note", "")}
