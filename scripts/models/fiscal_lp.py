"""Fiscal impulse and inflation in Kazakhstan: local projections on National Fund transfers.

    python scripts/models/fiscal_lp.py         # writes models/fiscal_lp/

Why transfers: there is no monthly or quarterly budget-execution series long enough (the
state-budget execution in the repository starts in 2025-02; Taldau has none). The National
Fund transfers to the republican budget are monthly from 2018-01 (MinFin, year-to-date) and
finance most of the non-oil deficit. Two parts:
  * guaranteed transfer -- fixed in the NF law / 3-year budget, known in advance;
  * targeted transfers  -- ad hoc decisions (2019, 2021-2025), the discretionary part.
Shock = targeted transfers in month t, % of trailing-12-month nominal GDP, and (robustness)
total transfers net of their predictable part (regression on 12 own lags + month dummies).

Local projections (Jorda 2005), h = 0..18 months:
    100 [ln X_{t+h} - ln X_{t-1}] = a_h + b_h shock_t + controls_t + e_{t+h}
X = CPI (STL SA) or industrial production (SA); controls: 3 lags of the dependent monthly change,
of USD/KZT, Brent and TONIA changes, and 3 lags of the shock. Newey-West s.e. with h+1 lags.
Sample 2018-05..2026-06 (~98 months, fewer at long h). Everything here is small-sample.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT = common.MODELS / "fiscal_lp"
H = 18


def load_transfers() -> pd.DataFrame:
    d = pd.read_csv(common.UNIFIED / "macro_long.csv", parse_dates=["date"],
                    usecols=["date", "variable", "value"])
    s = lambda v: d[d.variable == v].set_index("date").value.sort_index()  # noqa: E731
    ytd = pd.DataFrame({"total": s("NF_TRANSFERS_YTD"), "targeted": s("NF_TARGETED_TRANSFERS_YTD"),
                        "guaranteed": s("NF_GUARANTEED_TRANSFER_YTD")})
    idx = pd.date_range(ytd.index.min(), ytd.index.max(), freq="MS")
    ytd = ytd.reindex(idx)
    # missing months (2018-05, 2018-11, 2026-04, 2026-05): interpolate the year-to-date level
    # within the year, so the flow is spread over the gap instead of lost
    ytd = ytd.groupby(ytd.index.year, group_keys=False).apply(lambda g: g.interpolate(limit_area="inside"))
    flow = ytd.groupby(ytd.index.year).diff()
    jan = flow.index.month == 1
    flow.loc[jan] = ytd.loc[jan]
    gdp = s("GDP_NOMINAL")  # quarterly, year-to-date
    g = pd.DataFrame({"ytd": gdp})
    q = g.groupby(g.index.year).ytd.diff()
    q[g.index.month == 1] = g.ytd[g.index.month == 1]
    gm = (q / 3).reindex(pd.date_range(q.index.min(), q.index.max() + pd.offsets.MonthBegin(2), freq="MS")).ffill()
    gdp12 = gm.rolling(12).sum()
    out = flow.div(gdp12.reindex(flow.index) / 1e6, axis=0) * 100  # % of trailing-12m GDP
    out.index = out.index.to_period("M")
    return out


def lp(y_level: pd.Series, shock: pd.Series, ctrl: pd.DataFrame, H: int = H) -> pd.DataFrame:
    ly = 100 * np.log(y_level)
    dy = ly.diff()
    rows = []
    for h in range(H + 1):
        lhs = ly.shift(-h) - ly.shift(1)
        X = pd.concat([shock.rename("shock")] +
                      [dy.shift(k).rename(f"dy_l{k}") for k in (1, 2, 3)] +
                      [shock.shift(k).rename(f"sh_l{k}") for k in (1, 2, 3)] +
                      [ctrl[c].shift(k).rename(f"{c}_l{k}") for c in ctrl for k in (1, 2, 3)], axis=1)
        df = pd.concat([lhs.rename("y"), X], axis=1).dropna()
        m = sm.OLS(df.y, sm.add_constant(df.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": h + 1})
        b, se = m.params["shock"], m.bse["shock"]
        rows.append({"h": h, "b": b, "se": se, "lo68": b - se, "hi68": b + se, "lo90": b - 1.645 * se,
                     "hi90": b + 1.645 * se, "n": int(m.nobs)})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    m = common.load_monthly()
    tr = load_transfers()
    ctrl = pd.DataFrame({"fx": 100 * np.log(m.usdkzt).diff(), "oil": 100 * np.log(m.brent).diff(),
                         "rate": m.tonia.diff()})
    # predictable part of total transfers: 12 own lags + month dummies
    t = tr.total.dropna()
    Z = pd.concat([t.shift(k).rename(f"l{k}") for k in range(1, 13)], axis=1)
    Z = pd.concat([Z, pd.get_dummies(t.index.month, prefix="m", drop_first=True, dtype=float).set_index(t.index)], axis=1)
    df = pd.concat([t.rename("y"), Z], axis=1).dropna()
    surprise = (df.y - sm.OLS(df.y, sm.add_constant(df.drop(columns="y"))).fit().fittedvalues).reindex(t.index)
    shocks = {"targeted": tr.targeted, "total_surprise": surprise}
    res = []
    for sname, sh in shocks.items():
        for yname, y in {"cpi": m.cpi_sa, "ip": m.ip_sa}.items():
            sub = pd.concat([y.rename("y"), sh.rename("s"), ctrl], axis=1).loc["2018-01":"2026-06"]
            r = lp(sub.y, sub.s, sub[list(ctrl)])
            r["shock"], r["outcome"] = sname, yname
            res.append(r)
    res = pd.concat(res)
    res.to_csv(OUT / "lp.csv", index=False, float_format="%.4f")
    tr.to_csv(OUT / "nf_transfers_pct_gdp.csv", float_format="%.4f")
    # scale: targeted transfers of 1 % of GDP in one month
    show = res[res.h.isin([0, 3, 6, 9, 12, 18])]
    print(show.round(3).to_string(index=False))
    chart(res, OUT / "lp_fiscal.png")


def chart(res: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharex=True)
    common.style(fig, *axes)
    for ax, (y, lab) in zip(axes, [("cpi", "Уровень цен (ИПЦ SA), %"), ("ip", "Промпроизводство (SA), %")]):
        r = res[(res.shock == "targeted") & (res.outcome == y)]
        ax.fill_between(r.h, r.lo90, r.hi90, color=common.SERIES[0], alpha=0.12, linewidth=0)
        ax.fill_between(r.h, r.lo68, r.hi68, color=common.SERIES[0], alpha=0.25, linewidth=0)
        ax.plot(r.h, r.b, color=common.SERIES[0], lw=2)
        common.zero_line(ax)
        ax.set_title(lab, loc="left", fontsize=10, color=common.INK)
        ax.set_xlabel("месяцы после трансферта", fontsize=8.5, color=common.INK_2)
    fig.suptitle("Отклик на целевой трансферт Нацфонда 1 % ВВП (локальные проекции, 68 % и 90 %)",
                 x=0.01, ha="left", fontsize=11.5, fontweight="bold", color=common.INK)
    fig.tight_layout()
    common.save(fig, path)


if __name__ == "__main__":
    main()
