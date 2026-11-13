"""Quarterly and monthly inputs for svar_v2.py (the September 2026 re-estimation).

New relative to bvar_sign_ext.py:
  * nonoil_def   : non-oil deficit of the STATE budget, % of GDP, discrete quarter, X-13 SA.
                   Positive = deficit (fiscal expansion). Minfin bulletin, табл 3, YTD -> quarters.
  * nonoil_ma4   : 4-quarter moving average of the unadjusted non-oil deficit, % GDP -- the annual
                   fiscal stance; the quarterly cash deficit is dominated by payment timing.
  * quasi_def    : budget loans + equity injections into development institutions and national
                   holdings (Minfin табл 8, LOAN.DI + EQUITY.DI), % of GDP, X-13 SA. These flows are
                   INSIDE the Kazakh deficit definition (net lending and financial-asset operations
                   are below the line of revenue - expenditure), so nonoil_core = nonoil_def - quasi_def.
  * tariff_step  : regulated-utility CPI m/m in months with an identified administrative tariff step
                   (BNS item-level jumps, TARIFF_CHANGE_MONTHS), zero otherwise; cumulated into an
                   index so that 400 dln gives quarterly SAAR step inflation. Drift between steps
                   stays in the other shocks.
  * gdp_sa 2026Q2: extended with the BNS discrete-quarter volume index (105.184 y/y) applied to
                   the SA level of 2025Q2 -- assumes an unchanged seasonal factor.
Nominal GDP for 2026Q2 (denominator only) is extrapolated with the 2026Q1 q/q SA growth.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import common  # noqa: E402
import x13  # noqa: E402

R = common.REPO_ROOT / "data" / "processed"


def ytd_to_quarter(s: pd.Series) -> pd.Series:
    """Year-to-date cumulative (dated at month ends) -> discrete quarters (PeriodIndex Q)."""
    s = s.copy()
    s.index = pd.to_datetime(s.index)
    qe = s[s.index.month.isin([3, 6, 9, 12])]
    qe.index = pd.PeriodIndex(qe.index, freq="Q")
    out = {}
    for p, v in qe.items():
        if p.quarter == 1:
            out[p] = v
        else:
            prev = p - 1
            if prev in qe.index:
                out[p] = v - qe[prev]
    return pd.Series(out).sort_index()


def sa_additive(s: pd.Series, name: str) -> pd.Series:
    x = s.copy()
    x.index = x.index.to_timestamp()
    r = x13.adjust(x, 4, transform="none", calendar="none", title=name)
    out = r.sa if hasattr(r, "sa") else r.adjusted
    out.index = pd.PeriodIndex(out.index, freq="Q")
    return out


def nominal_gdp(q: pd.DataFrame) -> pd.Series:
    g = q["gdp_nominal"].dropna()
    gsa = q["gdp_nominal_sa"].dropna()
    last = g.index[-1]
    nxt = last + 1
    growth = gsa.iloc[-1] / gsa.iloc[-2]
    # NSA extrapolation: same quarter a year earlier times the y/y implied by SA growth
    yoy = gsa.iloc[-1] * growth / gsa.loc[nxt - 4]
    g.loc[nxt] = g.loc[nxt - 4] * yoy
    return g


def bank_rescue_2017() -> float:
    """One-off July 2017 transfer to the Problem Loans Fund (Kazkommertsbank / Halyk deal), booked
    as state-budget expenditure and financed by the National Fund: July expenditure minus the
    average monthly expenditure of August-September 2017. A balance-sheet operation in the
    financial sector, not a demand impulse, so it is removed from the non-oil deficit."""
    e = pd.read_csv(R / "minfin" / "state_budget_expenditure_ytd.csv", index_col=0)["value"]
    jul = e["2017-07-31"] - e["2017-06-30"]
    normal = (e["2017-09-30"] - e["2017-07-31"]) / 2
    return float(jul - normal)


def fiscal(q: pd.DataFrame) -> pd.DataFrame:
    nod = pd.read_csv(R / "minfin" / "state_non_oil_deficit_ytd.csv", index_col=0)["value"]
    nod_q = -ytd_to_quarter(nod)  # deficit positive
    nod_q.loc[pd.Period("2017Q3")] -= bank_rescue_2017()
    qf = pd.read_csv(R / "dims" / "rb_quasifiscal_ytd.csv")
    qf = qf[qf.item_code.isin(["LOAN.DI", "EQUITY.DI"])].pivot_table(index="date", columns="item_code", values="value")
    qf.index = pd.to_datetime(qf.index) + pd.offsets.MonthEnd(0)
    quasi_q = ytd_to_quarter(qf.sum(axis=1, min_count=2))
    gdp = nominal_gdp(q)
    df = pd.DataFrame({"nonoil_def_nsa": 100 * nod_q / gdp, "quasi_def_nsa": 100 * quasi_q / gdp}).dropna(how="all")
    df = df.loc[:gdp.index[-1]]
    df["nonoil_core_nsa"] = df.nonoil_def_nsa - df.quasi_def_nsa
    for c in ["nonoil_def", "quasi_def", "nonoil_core"]:
        s = df[f"{c}_nsa"].dropna()
        df[c] = sa_additive(s, c)
    # annual fiscal stance: 4-quarter mean of the unadjusted ratio (no seasonal adjustment needed)
    df["nonoil_ma4"] = df["nonoil_def_nsa"].rolling(4).mean()
    return df


def tariff_steps(m: pd.DataFrame) -> pd.DataFrame:
    reg = m["cpi_regulated"].dropna()
    mm = 100 * np.log(reg).diff()
    t = pd.read_csv(R / "dims" / "tariff_change_months.csv", parse_dates=["date"])
    flagged = pd.PeriodIndex(t.date, freq="M").unique()
    step = mm.where(mm.index.isin(flagged), 0.0)
    drift = mm - step
    idx = np.exp(step.fillna(0).cumsum() / 100) * 100
    out = pd.DataFrame({"reg_mm": mm, "step_mm": step, "drift_mm": drift, "tariff_step_idx": idx,
                        "flagged": mm.index.isin(flagged)})
    return out


def decision_match(window: int = 1) -> dict:
    """Share of CPI tariff-jump months (2019+) that have a KREM/ДКРЕМ decision for the same kind of
    service taking effect in the same month or up to `window` months earlier."""
    t = pd.read_csv(R / "dims" / "tariff_change_months.csv", parse_dates=["date"])
    d = pd.read_csv(R / "dims" / "tariff_decisions.csv", parse_dates=["date"])
    d["svc"] = d.item_name.str.split(" \\| ").str[0]
    kind = {"COLD_WATER": ["водоснабжение", "подача воды"], "SEWERAGE": ["водоотведение"],
            "HOT_WATER": ["горячее водоснабжение", "теплоснабжение"], "HEATING": ["теплоснабжение"],
            "ELECTRICITY": ["электро"], "NETWORK_GAS": ["газ"]}
    t = t[(t.date >= "2019-01-01") & t.item_code.isin(kind)]
    hits = 0
    for _, r in t.iterrows():
        ok = d.svc.apply(lambda s: any(k in s for k in kind[r.item_code]))
        lo = r.date - pd.DateOffset(months=window)
        hits += bool(((d.date >= lo) & (d.date <= r.date) & ok).any())
    return {"jump_months_2019plus": len(t), "with_decision": hits, "share": hits / max(len(t), 1)}


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    q = common.load_quarterly()
    m = common.load_monthly()
    # GDP SA 2026Q2 from the discrete y/y volume index
    gv = pd.read_csv(R / "dims" / "gva_volume_index_by_section_discrete.csv", parse_dates=["date"])
    gv = gv[(gv.region == "national") & (gv.item_code == "GDP")].set_index("date")["value"]
    gv.index = pd.PeriodIndex(gv.index, freq="Q")
    last = q["gdp_sa"].dropna().index[-1]
    for p in gv.index[gv.index > last]:
        q.loc[p, "gdp_sa"] = q.loc[p - 4, "gdp_sa"] * gv[p] / 100
    f = fiscal(q)
    for c in f.columns:
        q[c] = f[c]
    ts = tariff_steps(m)
    idx = ts["tariff_step_idx"].copy()
    idx.index = idx.index.to_timestamp()
    qi = idx.resample("QS").mean()[idx.resample("QS").count() == 3]
    qi.index = pd.PeriodIndex(qi.index, freq="Q")
    q["tariff_step_idx"] = qi
    return q, ts


if __name__ == "__main__":
    q, ts = build()
    print(q[["nonoil_def_nsa", "nonoil_def", "quasi_def", "nonoil_core", "tariff_step_idx", "gdp_sa"]].loc["2011Q3":].round(2).to_string())
    print(decision_match())
    print("flagged share of regulated m/m variance:", (ts.step_mm ** 2).sum() / (ts.reg_mm.dropna() ** 2).sum())
