#!/usr/bin/env python3
"""Market core CPI of Kazakhstan: headline CPI excluding (a) fruit and vegetables, (b) petrol and
diesel, (c) solid fuel (coal), (d) regulated utility services.

    python scripts/models/build_market_core.py [--out DIR] [--refresh-taldau] [--sa auto|x13|filter]

Writes models/cpi_components/market_core_index.csv (read by bvar_market.py and svar_v2.py) and, in
models/cpi_components/market_core/, the weights, the components, the sensitivity and the comparison with
the index used until November 2026 (market_core_index_until_2026-11.csv, which had no builder).

Method (details and limits: models/cpi_components/market_core/README.md)
-------------------------------------------
BNS compiles the CPI as a Laspeyres index on December of the previous year with weights fixed for
the calendar year, so within a year  H_ytd = sum_i w_i * I_i,ytd  (all indices December = 100).
The index excluding a set E is therefore exactly

    core_ytd(t) = (H_ytd(t) - sum_{i in E} w_i * I_i,ytd(t)) / (1 - sum_{i in E} w_i)

and core m/m(t) = core_ytd(t) / core_ytd(t-1); years are chained through December. This is the
formula  pi_core = (pi_headline - sum w_i pi_i) / (1 - sum w_i)  on month-on-month changes with the
weights price-updated inside the year (w_i,t = w_i * I_i,ytd(t-1) / H_ytd(t-1)); in January the two
coincide. The version with the annual weights applied to every month-on-month change unchanged is
also written (column mkt_base_fixedw) so that the difference can be seen.

Data
----
* Index series (headline, the five excluded components, the COICOP sub-indices used to estimate
  weights): BNS, Taldau index 703076 «Индекс потребительских цен», national, monthly, previous
  month = 100 and December of the previous year = 100. They are kept in taldau_cpi_cache.csv next
  to this script, with the term names in taldau_cpi_cache_terms.csv (no network at run time);
  --refresh-taldau downloads them again (16 POST requests to taldau.stat.gov.kz, standard library
  only) and is needed whenever a new month is to be added. The same numbers are in the repository
  (data/processed/dims/cpi_detail_*.csv, data/processed/bns/cpi_regulated_utilities.csv); the
  script checks that they agree and stops if they do not.
* From REPO_ROOT: official division weights (data/processed/dims/cpi_weights.csv), BNS
  contributions to CPI growth (cpi_contribution_ytd.csv) with the item indices they refer to
  (cpi_detail_ytd.csv), division weights estimated from contributions for 2024+
  (cpi_weights_estimated.csv), BNS core inflation (data/processed/bns/core_cpi_*), and the old
  models/cpi_components/market_core_index.csv for the comparison.

Weights (percent of the CPI basket, one set per calendar year; source recorded per cell)
-----------------------------------------------------------------------------------------
official   BNS brochure «Индекс потребительских цен: вопросы и ответы» (fruit and vegetables:
           2017, 2019-2023; divisions 04 and 07 for 2020, 2021, 2023), IMF/BNS division weights.
implied    BNS contribution of the item to CPI growth since December divided by the item's
           growth: w = 100 * sum(c*d) / sum(d*d), d = I_ytd - 100. Used when its rounding error
           is below 10 % of the weight (contributions exist from 2020).
regression non-negative least squares of a published aggregate on its complete set of published
           children (shares sum to one), December = 100 indices, twelve months of the year;
           the share is multiplied by the official weight of the COICOP division.
ratio      diesel only: the 2026 implied diesel/petrol ratio applied to the petrol weight.

Only pandas and numpy are needed (the X-13 seasonal adjustment of the *_sa columns uses the
repository's scripts/lib/x13.py when it is there; otherwise a moving seasonal filter).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "models" / "cpi_components" / "market_core"
INDEX = REPO / "models" / "cpi_components" / "market_core_index.csv"
CACHE = HERE / "taldau_cpi_cache.csv"                    # term_id, base (mom / ytd), date, value
TERMS = HERE / "taldau_cpi_cache_terms.csv"              # term_id, parent_id, name

# ----------------------------------------------------------------------------- Taldau terms
TALDAU_URL = "https://taldau.stat.gov.kz/ru/NewIndex/GetIndexTreeData"
TALDAU_INDEX = "703076"                    # Индекс потребительских цен
TALDAU_DICS = "67,848,2753"                # region, comparison base, goods and services
BASES = {"mom": "2695730", "ytd": "2695731"}
TOP = "7358"                               # root of the goods-and-services dictionary
T = dict(
    H="4772381",          # Товары и услуги
    EXFV="4772554",       # Все товары и услуги без фруктов и овощей
    FV="5259928",         # Фрукты и овощи
    REG="4772564",        # Коммунальные услуги регулируемые
    CP04="5259273",       # Жилищные услуги, вода, электроэнергия, газ и другие виды топлива
    RENT="5259274", MAINT="5259285", WATERGRP="5259306", ENERGY="5259336",
    WATER="5259307", SEWER="5259325", GARBAGE_OLD="5259320", GARBAGE="54965293", HOUSING_OTHER="5259330",
    SOLID="5259362",      # Твердое топливо
    CP07="5259642", OPER="5259662", FUELS="5259668",
    PETROL="5259669",     # Бензин
    DIESEL="5259681",     # Дизельное топливо
)
PARENTS = [TOP, T["H"], T["CP04"], T["WATERGRP"], T["ENERGY"], T["CP07"], T["OPER"], T["FUELS"]]
COMPONENTS = ["fv", "petrol", "diesel", "solid", "reg"]           # the excluded set, in this order
TERM_OF = {"fv": T["FV"], "petrol": T["PETROL"], "diesel": T["DIESEL"], "solid": T["SOLID"], "reg": T["REG"]}
LABEL = {"fv": "fruit and vegetables", "petrol": "petrol", "diesel": "diesel", "solid": "solid fuel (coal)",
         "reg": "regulated utilities"}

# ----------------------------------------------------------------------------- official weights
# BNS brochure «Индекс потребительских цен: вопросы и ответы», table «Схема взвешивания для расчета
# ИПЦ, используемая в … году» (stat.gov.kz/upload/medialibrary/…, editions for 2019, 2020, 2021,
# 2023 and one headed «2016г.» whose numbers are the IMF/BNS weights of 2017: food 35.14, housing
# 15.90). 2022: the same table, already in data/reference/bns_cpi_weights.csv.
OFFICIAL_FV = {2017: 5.94, 2019: 6.18, 2020: 6.00, 2021: 5.84, 2022: 6.14, 2023: 5.74}
OFFICIAL_DIV = {2020: {"CP04": 14.58, "CP07": 9.54}, 2021: {"CP04": 14.61, "CP07": 9.57},
                2023: {"CP04": 13.95, "CP07": 7.09}}

# contribution rows (cpi_contribution_ytd.csv) and the index they refer to
CONTRIB = {"fv": (["frukty_i_ovoshchi"], "taldau"), "petrol": (["benzin"], "taldau"),
           "diesel": (["dizelnoe_toplivo"], "taldau"), "solid": (["tverdoe_toplivo"], "taldau")}
# regulated utilities = electricity, gas through the network, cold and hot water, central heating,
# sewerage (the composition that reproduces BNS's own index, see models/cpi_components/market_core/README.md); each logical
# item: contribution codes, then codes of its index in cpi_detail_ytd.csv
REG_ITEMS = {
    "electricity": (["elektroenergiya", "elektroenergiya_obshchiy"], ["elektroenergiya", "elektroenergiya_obshchiy"]),
    "network gas": (["gaz_transportiruemyy_po_raspredelitelnym_setyam"], ["gaz_transportiruemyy_po_raspredelitelnym_setyam"]),
    "cold water": (["kholodnaya_voda", "kholodnaya_voda_za_1_kub_metr"], ["kholodnaya_voda", "kholodnaya_voda_za_1_kub_metr"]),
    "hot water": (["goryachaya_voda", "goryachaya_voda_za_1_kub_metr"], ["goryachaya_voda", "goryachaya_voda_za_1_kub_metr"]),
    "central heating": (["otoplenie_tsentralnoe", "otoplenie_tsentralnoe_za_1_gkal"],
                        ["otoplenie_tsentralnoe", "otoplenie_tsentralnoe_za_1_gkal"]),
    "sewerage": (["vodootvedenie", "vodootvedenie_za_1_kub_metr", "kanalizatsiya"],
                 ["vodootvedenie", "vodootvedenie_za_1_kub_metr", "kanalizatsiya"]),
}
REG_ITEMS_2020_GAS = (["gaz"], ["gazosnabzhenie"])       # 2020: one gas item
SIGMA_C, SIGMA_I = 0.0003, 0.029                         # rounding s.d. of a contribution (3 dp) and an index (1 dp)
MAX_REL_SE = 0.10
UTIL_BAND = 0.30                                         # low / high: regulated-utilities weight -/+ 30 %
FIRST_YEAR = 2011


# ============================================================================= Taldau cache
def _taldau_children(parent: str, base: str) -> list[dict]:
    import ssl
    import urllib.parse
    import urllib.request
    body = {"p_parent_id": parent, "p_index_id": TALDAU_INDEX, "p_keyword": "", "p_period_id": "4",
            "p_measure_id": "7", "p_term_id": parent, "p_terms": f"741880,{BASES[base]},{parent}",
            "p_dicIds": TALDAU_DICS, "idx": "2", "filter": '[{"property":null,"value":null}]', "id": parent}
    req = urllib.request.Request(TALDAU_URL, data=urllib.parse.urlencode(body).encode(),
                                 headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180, context=ssl.create_default_context()) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                                   # noqa: BLE001
            if attempt == 3:
                raise SystemExit(f"Taldau request failed for term {parent} ({base}): {e}")
            time.sleep(3 * (attempt + 1))
    return []


def refresh_taldau() -> None:
    rows = []
    for base in BASES:
        for parent in PARENTS:
            for node in _taldau_children(parent, base):
                for k, v in node.items():
                    if len(k) == 7 and k[0] == "y" and k[1:].isdigit() and v not in ("", None, "x"):
                        rows.append((str(node["id"]), str(node["text"]).strip(), parent, base, f"{k[3:]}-{k[1:3]}", float(v)))
    df = pd.DataFrame(rows, columns=["term_id", "name", "parent_id", "base", "date", "value"])
    df = df.drop_duplicates(["term_id", "base", "date"]).sort_values(["base", "parent_id", "term_id", "date"])
    if df.term_id.nunique() < 40 or df[df.term_id == T["H"]].shape[0] < 300:
        raise SystemExit("Taldau refresh returned too little; the cache was left as it was")
    df[["term_id", "base", "date", "value"]].to_csv(CACHE, index=False)
    df.drop_duplicates("term_id")[["term_id", "parent_id", "name"]].to_csv(TERMS, index=False)
    print(f"taldau cache refreshed: {len(df)} rows, {df.term_id.nunique()} series, to {df.date.max()}")


def load_taldau() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    if not CACHE.exists() or not TERMS.exists():
        raise SystemExit(f"{CACHE} is missing: run with --refresh-taldau once (network needed)")
    df = pd.read_csv(CACHE, dtype={"term_id": str})
    df["date"] = pd.to_datetime(df.date + "-01")
    wide = {b: df[df.base == b].pivot(index="date", columns="term_id", values="value").sort_index() for b in BASES}
    meta = pd.read_csv(TERMS, dtype={"term_id": str, "parent_id": str}).set_index("term_id")
    return wide["mom"], wide["ytd"], meta["name"].to_dict(), meta["parent_id"].to_dict()


# ============================================================================= small numerics
def nnls_shares(y: np.ndarray, X: np.ndarray, sum_to_one: bool = True) -> tuple[np.ndarray, float]:
    """min |y - X b|, b >= 0 (and sum b = 1): exact, by enumeration of the active set (k <= 10)."""
    k = X.shape[1]
    best, best_sse = np.zeros(k), np.inf
    for r in range(1, k + 1):
        for idx in itertools.combinations(range(k), r):
            A = X[:, idx]
            if sum_to_one:
                if r == 1:
                    b = np.array([1.0])
                else:                                            # substitute the last coefficient
                    Z = A[:, :-1] - A[:, [-1]]
                    g = np.linalg.lstsq(Z, y - A[:, -1], rcond=None)[0]
                    b = np.append(g, 1 - g.sum())
            else:
                b = np.linalg.lstsq(A, y, rcond=None)[0]
            if (b < -1e-12).any():
                continue
            sse = float(((y - A @ b) ** 2).sum())
            if sse < best_sse - 1e-14:
                best_sse = sse
                best = np.zeros(k)
                best[list(idx)] = np.clip(b, 0, None)
    return best, best_sse


def regress(ytd: pd.DataFrame, year: int, parent: str, kids: list[str], sum_to_one: bool = True) -> tuple[dict, float, int]:
    """Shares of `kids` in `parent` from the December = 100 indices of one year; max |residual|."""
    s = ytd.loc[str(year), [parent] + kids].dropna() - 100
    if len(s) < max(4, len(kids)):
        return {}, np.nan, len(s)
    b, _ = nnls_shares(s[parent].values, s[kids].values, sum_to_one)
    return dict(zip(kids, b)), float(np.abs(s[kids].values @ b - s[parent].values).max()), len(s)


def children(parent_of: dict, ytd: pd.DataFrame, parent: str, year: int) -> list[str]:
    n = int(ytd.loc[str(year), parent].notna().sum())
    return sorted(t for t, p in parent_of.items() if p == parent and t in ytd and ytd.loc[str(year), t].notna().sum() >= n)


def implied_weight(c: pd.Series, i_ytd: pd.Series) -> tuple[float, float, int]:
    """Weight (percent) implied by contributions c (pp, since December) and the index (Dec = 100)."""
    df = pd.concat([c.rename("c"), (i_ytd - 100).rename("d")], axis=1).dropna()
    df = df[df.d.abs() >= 0.05]
    if df.empty:
        return np.nan, np.nan, 0
    sdd = float((df.d ** 2).sum())
    w = 100 * float((df.c * df.d).sum()) / sdd
    se = 100 * np.sqrt(SIGMA_C ** 2 + (w / 100 * SIGMA_I) ** 2) / np.sqrt(sdd)
    return w, se, len(df)


def first_valid(frame: pd.DataFrame, codes: list[str]) -> pd.Series:
    out = pd.Series(np.nan, index=frame.index)
    for code in codes:
        if code in frame:
            out = out.combine_first(frame[code])
    return out


# ============================================================================= repository data
def load_repo(root: Path) -> dict:
    d = root / "data" / "processed" / "dims"

    def wide(name: str) -> pd.DataFrame:
        x = pd.read_csv(d / name, parse_dates=["date"])
        x = x[x.region == "national"]
        return x.pivot_table(index="date", columns="item_code", values="value")

    def annual(name: str) -> pd.DataFrame:
        x = pd.read_csv(d / name)
        x["year"] = x.date.str[:4].astype(int)
        return x.pivot_table(index="year", columns="item_code", values="value")

    def scalar(name: str) -> pd.Series:
        p = root / "data" / "processed" / "bns" / name
        return pd.read_csv(p, index_col=0, parse_dates=True)["value"] if p.exists() else pd.Series(dtype=float)

    out = {"mom": wide("cpi_detail_mom.csv"), "ytd": wide("cpi_detail_ytd.csv"), "yoy": wide("cpi_detail_yoy.csv"),
           "contrib": wide("cpi_contribution_ytd.csv"), "w_off": annual("cpi_weights.csv"),
           "w_est": annual("cpi_weights_estimated.csv"),
           "reg_mom": scalar("cpi_regulated_utilities.csv"), "ex3_mom": scalar("core_cpi_mom_ex3.csv"),
           "ex3_yoy": scalar("core_cpi_yoy_ex3.csv"), "ex7_mom": scalar("core_cpi_mom_ex7.csv"),
           "ex7_yoy": scalar("core_cpi_yoy_ex7.csv"), "cpi_yoy": scalar("cpi_yoy.csv")}
    old = root / "models" / "cpi_components" / "market_core" / "market_core_index_until_2026-11.csv"
    out["old"] = pd.read_csv(old, index_col=0, parse_dates=True) if old.exists() else None
    return out


def check_cache_against_repo(mom: pd.DataFrame, ytd: pd.DataFrame, repo: dict) -> list[str]:
    """The cache must carry the numbers the pipeline already has."""
    pairs = [("TOTAL", T["H"]), ("frukty_i_ovoshchi", T["FV"]), ("benzin", T["PETROL"]), ("dizelnoe_toplivo", T["DIESEL"]),
             ("dizelnoe_toplivo_obshchiy", T["DIESEL"]), ("tverdoe_toplivo", T["SOLID"]), ("CP04", T["CP04"]), ("CP07", T["CP07"])]
    lines, worst = [], 0.0
    for code, term in pairs:
        for name, a, b in (("mom", repo["mom"], mom), ("ytd", repo["ytd"], ytd)):
            if code not in a:
                continue
            diff = (a[code] - b[term]).dropna().abs()
            worst = max(worst, float(diff.max()))
            lines.append(f"  {code:28s} {name}: {len(diff):3d} common months, max |repo - Taldau| = {diff.max():.3f}")
    diff = (repo["reg_mom"] - mom[T["REG"]]).dropna().abs()
    worst = max(worst, float(diff.max()))
    lines.append(f"  {'cpi_regulated_utilities':28s} mom: {len(diff):3d} common months, max |repo - Taldau| = {diff.max():.3f}")
    if worst > 0.051:
        raise SystemExit("the Taldau cache and the repository disagree:\n" + "\n".join(lines))
    return lines


# ============================================================================= weights
def division_weight(repo: dict, year: int, code: str) -> tuple[float, str]:
    if year in OFFICIAL_DIV:
        return OFFICIAL_DIV[year][code], "official (BNS brochure)"
    if year in repo["w_off"].index and pd.notna(repo["w_off"].loc[year].get(code)):
        return float(repo["w_off"].loc[year, code]), "official (BNS via IMF)" if year < 2020 else "official (BNS brochure)"
    if year in repo["w_est"].index and pd.notna(repo["w_est"].loc[year].get(code)):
        return float(repo["w_est"].loc[year, code]), "estimated from contributions (repo CPI_WEIGHTS_ESTIMATED)"
    raise SystemExit(f"no weight for {code} in {year}")


def build_weights(mom: pd.DataFrame, ytd: pd.DataFrame, parent_of: dict, repo: dict, years: list[int]) -> pd.DataFrame:
    """One row per year and component: the weight used, its source, and every alternative estimate."""
    rows = []
    C, D = repo["contrib"], repo["ytd"]
    for y in years:
        yy = str(y)
        w04, s04 = division_weight(repo, y, "CP04")
        w07, s07 = division_weight(repo, y, "CP07")
        alt: dict[str, dict] = {c: {} for c in COMPONENTS}

        # ---- implied by BNS contributions
        if yy in C.index.year.astype(str):
            for comp, (codes, _) in CONTRIB.items():
                w, se, n = implied_weight(first_valid(C.loc[yy], codes), ytd.loc[yy, TERM_OF[comp]])
                alt[comp]["implied"], alt[comp]["implied_se"], alt[comp]["implied_n"] = w, se, n
            tot, var, nmin, parts = 0.0, 0.0, 99, {}
            for name, (ccodes, icodes) in REG_ITEMS.items():
                if y == 2020 and name == "network gas":
                    ccodes, icodes = REG_ITEMS_2020_GAS
                w, se, n = implied_weight(first_valid(C.loc[yy], ccodes), first_valid(D.loc[yy], icodes))
                parts[name] = w
                tot, var, nmin = tot + (w if pd.notna(w) else np.nan), var + (se ** 2 if pd.notna(se) else np.nan), min(nmin, n)
            alt["reg"]["implied"], alt["reg"]["implied_se"], alt["reg"]["implied_n"] = tot, np.sqrt(var), nmin
            alt["reg"]["implied_parts"] = "; ".join(f"{k} {v:.2f}" for k, v in parts.items() if pd.notna(v))

        # ---- regressions in the COICOP tree
        fvb, fvres, _ = regress(ytd, y, T["H"], [T["EXFV"], T["FV"]])
        alt["fv"]["regression"], alt["fv"]["regression_res"] = 100 * fvb.get(T["FV"], np.nan), fvres

        a, r1, _ = regress(ytd, y, T["CP04"], [T["RENT"], T["MAINT"], T["WATERGRP"], T["ENERGY"]])
        e, r2, _ = regress(ytd, y, T["ENERGY"], children(parent_of, ytd, T["ENERGY"], y))
        wt, r3, _ = regress(ytd, y, T["WATERGRP"], children(parent_of, ytd, T["WATERGRP"], y))
        alt["solid"]["regression"] = w04 * a[T["ENERGY"]] * e[T["SOLID"]]
        alt["solid"]["regression_res"] = max(r1, r2)
        alt["reg"]["regression_tree"] = w04 * (a[T["ENERGY"]] * (1 - e[T["SOLID"]]) + a[T["WATERGRP"]] * (wt[T["WATER"]] + wt[T["SEWER"]]))
        alt["reg"]["regression_tree_res"] = max(r1, r2, r3)
        garbage = T["GARBAGE_OLD"] if ytd.loc[yy, T["GARBAGE_OLD"]].notna().any() else T["GARBAGE"]
        dk = [T["REG"], T["SOLID"], T["RENT"], T["MAINT"], garbage, T["HOUSING_OTHER"]]
        dcoef, dres, _ = regress(ytd, y, T["CP04"], dk, sum_to_one=False)
        alt["reg"]["regression_direct"], alt["reg"]["regression_direct_res"] = w04 * dcoef[T["REG"]], dres
        ok_direct = dres <= 0.15
        alt["reg"]["regression"] = (alt["reg"]["regression_tree"] + alt["reg"]["regression_direct"]) / 2 if ok_direct \
            else alt["reg"]["regression_tree"]
        alt["reg"]["regression_res"] = max(r1, r2, r3)

        a7, q1, _ = regress(ytd, y, T["CP07"], children(parent_of, ytd, T["CP07"], y))
        b7, q2, _ = regress(ytd, y, T["OPER"], children(parent_of, ytd, T["OPER"], y))
        c7, q3, _ = regress(ytd, y, T["FUELS"], children(parent_of, ytd, T["FUELS"], y))
        fuels = w07 * a7[T["OPER"]] * b7[T["FUELS"]]
        alt["petrol"]["regression"], alt["petrol"]["regression_res"] = fuels * c7[T["PETROL"]], max(q1, q2, q3)
        alt["diesel"]["regression"], alt["diesel"]["regression_res"] = fuels * c7[T["DIESEL"]], max(q1, q2, q3)

        # ---- choice
        for comp in COMPONENTS:
            x = alt[comp]
            identified = pd.notna(x.get("implied")) and x.get("implied_n", 0) >= 1 and x["implied"] > 0 \
                and x["implied_se"] / x["implied"] <= MAX_REL_SE
            if comp == "fv" and y in OFFICIAL_FV:
                used, src = OFFICIAL_FV[y], "official (BNS brochure)"
            elif comp == "diesel":
                used, src = np.nan, ""                                    # filled below
                if identified:
                    used, src = x["implied"], "implied by BNS contributions"
            elif identified:
                used, src = x["implied"], "implied by BNS contributions"
            else:
                used = x["regression"]
                if comp == "fv":
                    src = "regression: CPI on CPI-ex-F&V and F&V"
                elif comp == "petrol":
                    src = f"regression in division 07 x division weight ({s07})"
                else:
                    src = f"regression in division 04 x division weight ({s04})"
                if comp == "reg" and not ok_direct:
                    src += "; tree estimate only"
            rows.append({"year": y, "component": comp, "weight": used, "source": src, "w_div04": w04, "w_div07": w07,
                         **{k: v for k, v in x.items()}})
    W = pd.DataFrame(rows)
    # diesel: the implied diesel/petrol ratio of the years where diesel is identified, applied to petrol
    pet = W[W.component == "petrol"].set_index("year").weight
    dsl = W[W.component == "diesel"].set_index("year").weight
    ratio = float((dsl / pet).dropna().mean()) if dsl.notna().any() else 0.035
    for i in W.index[(W.component == "diesel") & W.weight.isna()]:
        W.loc[i, "weight"] = ratio * pet[W.loc[i, "year"]]
        W.loc[i, "source"] = f"ratio: {ratio:.3f} x petrol weight (implied diesel/petrol ratio of {', '.join(map(str, dsl.dropna().index))})"
    return W


# ============================================================================= the index
def exclusion_index(ytd: pd.DataFrame, weights: pd.DataFrame, comps: list[str], scale: dict | None = None) -> pd.Series:
    """Chained index (first December before the sample = 100) of the CPI without `comps`."""
    scale = scale or {}
    level, prev, out = {}, 100.0, {}
    for y, g in ytd.groupby(ytd.index.year):
        w = {c: float(weights.loc[(y, c), "weight"]) / 100 * scale.get(c, 1.0) for c in comps}
        num = g[T["H"]] - sum(w[c] * g[TERM_OF[c]] for c in comps)
        core = num / (1 - sum(w.values()))
        if core.isna().any():
            raise SystemExit(f"missing index values in {y}: {core[core.isna()].index.strftime('%Y-%m').tolist()}")
        for t, v in core.items():
            out[t] = prev * v / 100
        prev = out[g.index[-1]] if g.index[-1].month == 12 else prev
        level[y] = prev
    return pd.Series(out).sort_index()


def fixed_weight_index(mom: pd.DataFrame, weights: pd.DataFrame, comps: list[str]) -> pd.Series:
    """The same exclusion with the annual weights applied to every m/m change unchanged."""
    out, lvl = {}, 100.0
    for t in mom.index:
        w = {c: float(weights.loc[(t.year, c), "weight"]) / 100 for c in comps}
        pi = (mom.loc[t, T["H"]] - 100 - sum(w[c] * (mom.loc[t, TERM_OF[c]] - 100) for c in comps)) / (1 - sum(w.values()))
        lvl *= 1 + pi / 100
        out[t] = lvl
    return pd.Series(out)


def seasonal_filter(s: pd.Series) -> pd.Series:
    """Fallback seasonal adjustment (numpy only): log-additive, 2x12 trend, 3x3 moving seasonal
    averages per calendar month, factors centred over each 12 months. Not X-13."""
    x = np.log(s.astype(float))
    n = len(x)
    k = np.r_[0.5, np.ones(11), 0.5] / 12
    trend = pd.Series(np.convolve(x.values, k, mode="same"), index=x.index)
    trend.iloc[:6] = np.nan
    trend.iloc[n - 6:] = np.nan
    si = x - trend
    seas = pd.Series(np.nan, index=x.index)
    w33 = np.array([1, 2, 3, 2, 1]) / 9
    for m in range(1, 13):
        v = si[si.index.month == m].dropna()
        if v.empty:
            continue
        pad = np.r_[[v.iloc[:2].mean()] * 2, v.values, [v.iloc[-2:].mean()] * 2]
        sm = pd.Series(np.convolve(pad, w33, mode="valid"), index=v.index)
        full = sm.reindex(x.index[x.index.month == m])
        seas[full.index] = full.ffill().bfill().values
    seas = seas - seas.rolling(12, center=True, min_periods=12).mean().ffill().bfill()
    return np.exp(x - seas)


def seasonally_adjust(s: pd.Series, root: Path, how: str, title: str) -> tuple[pd.Series, str]:
    if how in ("auto", "x13"):
        try:
            sys.path.insert(0, str(root / "scripts" / "lib"))
            import x13                                              # noqa: PLC0415
            for kw in (dict(calendar="kz"), dict(calendar="none"), dict(calendar="none", outliers=("ao", "ls"))):
                try:
                    return x13.adjust(s, 12, transform="log", title=title, **kw).sa.reindex(s.index), f"X-13 ({kw})"
                except x13.X13Error:
                    continue
        except Exception as e:                                       # noqa: BLE001
            if how == "x13":
                raise SystemExit(f"X-13 is not available: {e}")
        if how == "x13":
            raise SystemExit("X-13 did not converge")
    return seasonal_filter(s), "moving seasonal filter (numpy)"


def pct12(s: pd.Series) -> pd.Series:
    return 100 * (s / s.shift(12) - 1)


# ============================================================================= main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repo_root", type=Path, nargs="?", default=REPO)
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--refresh-taldau", action="store_true", help="download the index series again (network)")
    ap.add_argument("--sa", choices=["auto", "x13", "filter"], default="auto")
    args = ap.parse_args()
    if args.refresh_taldau:
        refresh_taldau()
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_rows", 400)
    mom, ytd, names, parent_of = load_taldau()
    repo = load_repo(args.repo_root)
    args.out.mkdir(parents=True, exist_ok=True)
    rep: list[str] = []

    def say(*a) -> None:
        line = " ".join(str(x) for x in a)
        print(line)
        rep.append(line)

    # the sample: every month for which headline and the five components exist on both bases
    need = [T["H"]] + list(TERM_OF.values())
    ok = mom[need].notna().all(axis=1) & ytd[need].notna().all(axis=1)
    last = ok[ok].index.max()
    mom, ytd = mom.loc[f"{FIRST_YEAR}-01-01":last], ytd.loc[f"{FIRST_YEAR}-01-01":last]
    if not ok.loc[mom.index].all():
        raise SystemExit(f"gaps in the component series: {ok.loc[mom.index][~ok.loc[mom.index]].index.tolist()}")
    years = sorted(set(mom.index.year))
    say(f"sample {mom.index[0]:%Y-%m} .. {last:%Y-%m} ({len(mom)} months)")
    say("\n== cache against the repository")
    for line in check_cache_against_repo(mom, ytd, repo):
        say(line)

    # ------------------------------------------------------------------ weights
    W = build_weights(mom, ytd, parent_of, repo, years)
    W.to_csv(args.out / "market_core_weights_detail.csv", index=False, float_format="%.4f")
    Wi = W.set_index(["year", "component"])
    table = Wi.weight.unstack()[COMPONENTS]
    table["excluded"] = table.sum(axis=1)
    table["market core"] = 100 - table.excluded
    src = Wi.source.unstack()[COMPONENTS]
    short = {"official": "O", "implied": "C", "regression": "R", "ratio": "D"}
    table["source"] = ["".join(short[next(k for k in short if s.startswith(k))] for s in src.loc[y]) for y in table.index]
    table.round(3).to_csv(args.out / "market_core_weights.csv")
    say("\n== weights, percent of the CPI basket (source letters in the order fv, petrol, diesel, solid, reg:"
        " O official, C implied by BNS contributions, R regression, D diesel/petrol ratio)")
    say(table.round(2).to_string())
    say("\n== alternative estimates (percent)")
    alt = pd.DataFrame({
        "fv used": Wi.weight.unstack()["fv"], "fv regr": Wi.regression.unstack()["fv"], "fv contrib": Wi.implied.unstack()["fv"],
        "petrol used": Wi.weight.unstack()["petrol"], "petrol regr": Wi.regression.unstack()["petrol"],
        "petrol contrib": Wi.implied.unstack()["petrol"], "solid used": Wi.weight.unstack()["solid"],
        "solid regr": Wi.regression.unstack()["solid"], "solid contrib": Wi.implied.unstack()["solid"],
        "reg used": Wi.weight.unstack()["reg"], "reg tree": Wi.regression_tree.unstack()["reg"],
        "reg direct": Wi.regression_direct.unstack()["reg"], "reg contrib": Wi.implied.unstack()["reg"],
        "reg contrib se": Wi.implied_se.unstack()["reg"], "diesel contrib": Wi.implied.unstack()["diesel"],
        "diesel regr": Wi.regression.unstack()["diesel"]})
    say(alt.round(2).to_string())
    say("\n   max |residual| of the regressions used, index points (rounding of the data is 0.05):")
    say(pd.DataFrame({c: Wi.regression_res.unstack()[c] for c in ["fv", "petrol", "solid", "reg"]}).round(2).T.to_string())

    # ------------------------------------------------------------------ index
    idx = pd.DataFrame({
        "mkt_base": exclusion_index(ytd, Wi, COMPONENTS),
        "mkt_low": exclusion_index(ytd, Wi, COMPONENTS, {"reg": 1 - UTIL_BAND}),
        "mkt_high": exclusion_index(ytd, Wi, COMPONENTS, {"reg": 1 + UTIL_BAND})})
    jan = idx.iloc[0].copy()
    idx = idx / jan * 100                                         # January 2011 = 100, as the old file
    out = pd.DataFrame(index=idx.index)
    sa_method = ""
    for c in ["mkt_base", "mkt_low", "mkt_high"]:
        out[c] = idx[c]
        out[c + "_sa"], sa_method = seasonally_adjust(idx[c], args.repo_root, args.sa, c)
    out.index.name = None
    out.to_csv(INDEX if args.out == HERE else args.out / "market_core_index.csv", float_format="%.5f")
    say(f"\nseasonal adjustment of the *_sa columns: {sa_method}")

    # components file: everything needed to re-do the arithmetic by hand
    hl, prev = {}, 100.0
    for y, g in ytd.groupby(ytd.index.year):
        for t, v in g[T["H"]].items():
            hl[t] = prev * v / 100
        prev = hl[g.index[-1]] if g.index[-1].month == 12 else prev
    headline = pd.Series(hl)
    comp = pd.DataFrame({"cpi_mom": mom[T["H"]], "cpi_ytd": ytd[T["H"]]})
    for c in COMPONENTS:
        comp[f"{c}_mom"], comp[f"{c}_ytd"] = mom[TERM_OF[c]], ytd[TERM_OF[c]]
        comp[f"w_{c}"] = [Wi.loc[(t.year, c), "weight"] for t in comp.index]
    comp["mkt_base_mom"] = 100 * idx.mkt_base / idx.mkt_base.shift(1)
    comp.loc[comp.index[0], "mkt_base_mom"] = exclusion_index(ytd, Wi, COMPONENTS).iloc[0]
    fixed = fixed_weight_index(mom, Wi, COMPONENTS)
    comp["mkt_base_fixedw"] = fixed / fixed.iloc[0] * 100
    ex3like = exclusion_index(ytd, Wi, ["fv", "petrol", "solid"])
    comp["ex_fv_petrol_solid"] = ex3like / ex3like.iloc[0] * 100
    comp.to_csv(args.out / "market_core_components.csv", float_format="%.5f")

    # ------------------------------------------------------------------ validation
    say("\n== validation (i): the identity")
    worst_ytd, worst_mom = 0.0, 0.0
    core_raw = exclusion_index(ytd, Wi, COMPONENTS)
    resid = {}
    for y, g in ytd.groupby(ytd.index.year):
        w = {c: Wi.loc[(y, c), "weight"] / 100 for c in COMPONENTS}
        base = core_raw[pd.Timestamp(y - 1, 12, 1)] if pd.Timestamp(y - 1, 12, 1) in core_raw.index else 100.0
        core_ytd = core_raw[g.index] / base * 100
        recon = (1 - sum(w.values())) * core_ytd + sum(w[c] * g[TERM_OF[c]] for c in COMPONENTS)
        worst_ytd = max(worst_ytd, float((recon - g[T["H"]]).abs().max()))
        # month-on-month form: price-updated weights, published m/m indices of the components
        prev_core = core_ytd.shift(1).fillna(100.0)
        prev_h = g[T["H"]].shift(1).fillna(100.0)
        core_mom = core_ytd / prev_core * 100 - 100
        h_implied = (1 - sum(w.values())) * prev_core / prev_h * core_mom
        for c in COMPONENTS:
            h_implied = h_implied + w[c] * g[TERM_OF[c]].shift(1).fillna(100.0) / prev_h * (mom.loc[g.index, TERM_OF[c]] - 100)
        r = h_implied - (mom.loc[g.index, T["H"]] - 100)
        resid[y] = float(r.abs().max())
        worst_mom = max(worst_mom, resid[y])
    say(f"  December = 100 form, headline - [(1-W) core + sum w_i I_i]: max |.| = {worst_ytd:.1e} index points (exact)")
    say(f"  month-on-month form with the published m/m of headline and components (all rounded to 0.1):"
        f" max |.| = {worst_mom:.3f} pp")
    say("  by year: " + ", ".join(f"{y} {v:.2f}" for y, v in resid.items()))
    d_fixed = (pct12(comp.mkt_base_fixedw) - pct12(idx.mkt_base)).dropna()
    say(f"  annual weights applied to m/m changes unchanged instead: 12-month inflation differs by"
        f" mean {d_fixed.mean():+.3f}, max |.| {d_fixed.abs().max():.3f} pp")

    say("\n== validation (ii): weights")
    say("  fruit and vegetables, regression against the official weight (percent):")
    for y in sorted(OFFICIAL_FV):
        say(f"    {y}: official {OFFICIAL_FV[y]:.2f}  regression {Wi.loc[(y, 'fv'), 'regression']:.2f}"
            f"  contributions {Wi.loc[(y, 'fv'), 'implied']:.2f}")
    say("  regression against the weights implied by BNS contributions, years where the latter are identified:")
    for c, col in (("petrol", "regression"), ("solid", "regression"), ("reg", "regression_tree"), ("reg", "regression_direct"), ("reg", "regression")):
        x = W[(W.component == c) & W.source.str.startswith("implied")]
        if len(x):
            e = x[col] - x.implied
            say(f"    {c:7s} {col:18s}: {len(x)} years, mean error {e.mean():+.2f}, mean |error| {e.abs().mean():.2f}, max |error| {e.abs().max():.2f} pp of the basket")
    say("  shares of the divisions (official division weights; the excluded part must be below them):")
    chk = pd.DataFrame({"div 04": Wi.w_div04.unstack()["reg"], "solid+reg": table.solid + table.reg,
                        "div 07": Wi.w_div07.unstack()["petrol"], "petrol+diesel": table.petrol + table.diesel})
    chk["share of 04"], chk["share of 07"] = chk["solid+reg"] / chk["div 04"], chk["petrol+diesel"] / chk["div 07"]
    say(chk.round(2).to_string())
    # BNS's own measures as a test of the weights
    exfv = exclusion_index(ytd, Wi, ["fv"])
    d = (100 * exfv / exfv.shift(1) - mom[T["EXFV"]]).dropna()
    say(f"  CPI without fruit and vegetables: mine against BNS (Taldau {T['EXFV']}), m/m: mean {d.mean():+.3f},"
        f" mean |.| {d.abs().mean():.3f}, max |.| {d.abs().max():.2f} pp")
    ex3 = repo["ex3_mom"]
    d = (100 * ex3like / ex3like.shift(1) - ex3).dropna()
    say(f"  CPI without fruit and vegetables, petrol and solid fuel: mine against BNS core (ex F&V, petrol, coal), m/m,"
        f" {d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m}: mean {d.mean():+.3f}, mean |.| {d.abs().mean():.3f}, max |.| {d.abs().max():.2f} pp")
    say("    by year, mean |.|: " + ", ".join(f"{y} {v:.3f}" for y, v in d.abs().groupby(d.index.year).mean().items()))
    d12 = (pct12(ex3like) - (repo["ex3_yoy"] - 100)).dropna()
    if len(d12):
        say(f"    12-month rates against BNS's published year-on-year core: mean {d12.mean():+.2f}, mean |.| {d12.abs().mean():.2f},"
            f" max |.| {d12.abs().max():.2f} pp ({d12.index[0]:%Y-%m}..{d12.index[-1]:%Y-%m})")

    say("\n== validation (iii): 12-month market core inflation when one excluded weight is changed by -/+ 30 %, pp")
    dates = [t for t in idx.index if t.month == 12 and t.year >= 2012] + ([last] if last.month != 12 else [])
    base12 = pct12(idx.mkt_base)
    sens = pd.DataFrame({"market core": base12[dates]})
    full = {}
    for c in COMPONENTS:
        for f, tag in ((0.7, "-30%"), (1.3, "+30%")):
            alt12 = pct12(exclusion_index(ytd, Wi, COMPONENTS, {c: f})) - base12
            sens[f"{c} {tag}"] = alt12[dates]
            full[f"{c} {tag}"] = alt12
    sens.index = sens.index.strftime("%Y-%m")
    say(sens.round(2).to_string())
    full = pd.DataFrame(full).dropna()
    say("  all months: mean |change| / max |change|: " + "; ".join(
        f"{c} {full[[c + ' -30%', c + ' +30%']].abs().mean().mean():.2f}/{full[[c + ' -30%', c + ' +30%']].abs().max().max():.2f}"
        for c in COMPONENTS))
    sens.to_csv(args.out / "market_core_sensitivity.csv", float_format="%.3f")

    # ------------------------------------------------------------------ comparison with the old file
    old = repo["old"]
    if old is not None:
        say("\n== comparison with models/cpi_components/market_core_index.csv (old)")
        ex3m, regm = repo["ex3_mom"] - 100, repo["reg_mom"] - 100
        om = 100 * (old.mkt_base / old.mkt_base.shift(1) - 1)
        u = ((ex3m - om) / (regm - om)).replace([np.inf, -np.inf], np.nan)
        u = u[(regm - om).abs() > 0.5].dropna()
        say("  the old base reproduces as (BNS core ex F&V, petrol, coal - u * regulated utilities) / (1 - u), m/m;")
        say("  u (share of the BNS core basket), median by year: " + ", ".join(f"{y} {v:.4f}" for y, v in u.groupby(u.index.year).median().items()))
        uy = u.groupby(u.index.year).median()
        both = pd.concat([ex3m.rename("c"), regm.rename("r")], axis=1).dropna()
        uu = both.index.year.map(uy).values
        rebuilt = (both.c - uu * both.r) / (1 - uu)
        say(f"  max |old m/m - that formula| = {(rebuilt - om).abs().max():.3f} pp over {(rebuilt - om).notna().sum()} months")
        nm = 100 * (idx.mkt_base / idx.mkt_base.shift(1) - 1)
        d = (om - nm).dropna()
        say(f"  m/m, old - new, {d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m}: mean {d.mean():+.3f}, mean |.| {d.abs().mean():.3f},"
            f" max |.| {d.abs().max():.2f} pp ({d.abs().idxmax():%Y-%m})")
        by = pd.DataFrame({"mean": d.groupby(d.index.year).mean(), "mean abs": d.abs().groupby(d.index.year).mean(),
                           "max abs": d.abs().groupby(d.index.year).max(),
                           "month of max": d.abs().groupby(d.index.year).idxmax().dt.strftime("%Y-%m")})
        say(by.round(3).to_string())
        by.to_csv(args.out / "market_core_old_vs_new_mom_by_year.csv", float_format="%.4f")
        ex7y = repo["ex7_yoy"].combine_first(repo["yoy"]["CORE_EX7"] if "CORE_EX7" in repo["yoy"] else pd.Series(dtype=float)) - 100
        ex3y = repo["ex3_yoy"].combine_first(repo["yoy"]["CORE_EX3"] if "CORE_EX3" in repo["yoy"] else pd.Series(dtype=float)) - 100
        cmp12 = pd.DataFrame({"headline": pct12(headline), "old mkt_base": pct12(old.mkt_base), "new mkt_base": pct12(idx.mkt_base),
                              "new low": pct12(idx.mkt_low), "new high": pct12(idx.mkt_high),
                              "old low": pct12(old.mkt_low), "old high": pct12(old.mkt_high),
                              "BNS CORE_EX3": ex3y, "BNS CORE_EX7": ex7y,
                              "regulated": pct12((mom[T["REG"]] / 100).cumprod())})
        cmp12 = cmp12.reindex(idx.index)
        cmp12["old - new"] = cmp12["old mkt_base"] - cmp12["new mkt_base"]
        cmp12.to_csv(args.out / "market_core_old_vs_new_12m.csv", float_format="%.3f")
        sel = [t for t in cmp12.index if (t.month == 12 and 2015 <= t.year <= 2025)] + [old.index.max(), last]
        sel = sorted(set(sel))
        show = cmp12.loc[sel]
        show.index = show.index.strftime("%Y-%m")
        say("  12-month inflation, percent:")
        say(show.round(2).to_string())
        d12 = cmp12["old - new"].dropna()
        say(f"  12-month rates, old - new, all months: mean {d12.mean():+.2f}, mean |.| {d12.abs().mean():.2f},"
            f" max |.| {d12.abs().max():.2f} pp ({d12.abs().idxmax():%Y-%m})")
        # where the difference comes from: (1) the starting index -- the old file chains BNS's core
        # (m/m rounded to 0.1), the new one removes the three components itself; (2) the weight of
        # regulated utilities; (3) diesel
        Wold = Wi[["weight"]].copy()
        for y in years:
            rest = 1 - sum(Wi.loc[(y, c), "weight"] for c in ("fv", "petrol", "solid")) / 100
            Wold.loc[(y, "reg"), "weight"] = float(uy.get(y, uy.iloc[-1])) * rest * 100
        step1 = pct12(exclusion_index(ytd, Wold, ["fv", "petrol", "solid", "reg"]))
        step2 = pct12(exclusion_index(ytd, Wi, ["fv", "petrol", "solid", "reg"]))
        dec = pd.DataFrame({"old": cmp12["old mkt_base"], "(1) starting index": cmp12["old mkt_base"] - step1,
                            "(2) utilities weight": step1 - step2, "(3) diesel": step2 - cmp12["new mkt_base"],
                            "new": cmp12["new mkt_base"]})
        dec["old utilities weight, % of CPI"] = [Wold.loc[(t.year, "reg"), "weight"] for t in dec.index]
        dec["new utilities weight, % of CPI"] = [Wi.loc[(t.year, "reg"), "weight"] for t in dec.index]
        dec.to_csv(args.out / "market_core_old_vs_new_decomposition.csv", float_format="%.3f")
        show = dec.loc[[t for t in sel if t in dec.index and pd.notna(dec.loc[t, "old"])]]
        show.index = show.index.strftime("%Y-%m")
        say("  old - new in 12-month inflation = (1) + (2) + (3), pp:")
        say(show.round(2).to_string())
        dd = dec.dropna()
        say("  all months, mean |.|: " + ", ".join(f"{c} {dd[c].abs().mean():.2f} (max {dd[c].abs().max():.2f})"
                                                     for c in ["(1) starting index", "(2) utilities weight", "(3) diesel"]))
        chained = pct12((repo["ex3_mom"] / 100).cumprod())
        drift = (chained - ex3y).dropna()
        say(f"  BNS core (ex F&V, petrol, coal): twelve chained m/m (0.1 rounding) minus BNS's own year-on-year,"
            f" {drift.index[0]:%Y-%m}..{drift.index[-1]:%Y-%m}: mean {drift.mean():+.2f}, mean |.| {drift.abs().mean():.2f},"
            f" max |.| {drift.abs().max():.2f} pp ({drift.abs().idxmax():%Y-%m}); Decembers: "
            + ", ".join(f"{t.year} {v:+.2f}" for t, v in drift.items() if t.month == 12 and t.year >= 2015))
        lv = (old.mkt_base / old.mkt_base.loc["2011-02-01"]) / (idx.mkt_base / idx.mkt_base.loc["2011-02-01"])
        say(f"  level, old / new (both = 1 in 2011-02): {lv.dropna().iloc[-1]:.4f} in {lv.dropna().index[-1]:%Y-%m}")

    (args.out / "market_core_report.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
