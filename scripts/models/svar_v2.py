"""SVAR re-estimation, September 2026: the fiscal block measured by the NON-OIL DEFICIT (and its
quasi-fiscal part), tariffs by identified administrative steps, X-13 seasonal adjustment
(model_data is X-13 since 2026-09-28), sample to 2026Q2.

    python scripts/models/svar_v2.py        # writes models/svar_v2/

Same identification as bvar_sign_ext.py: external block (Brent, Fed funds, RUB/USD) recursive and
block-exogenous; fiscal and tariff variables recursive (Blanchard-Perotti: no within-quarter
reaction of discretionary fiscal policy and of regulator-approved tariffs); GDP, USD/KZT,
inflation, TONIA rotated with zero (tenge: no GDP impact) and sign restrictions.

Variants
  old_2011  : bvar_sign_ext spec (real G, regulated CPI) on today's X-13 data, 2011Q2-2026Q1
  old_2013  : the same spec from 2013Q1 (isolates the sample change)
  v2        : non-oil deficit % GDP + tariff steps, 2013Q1-2026Q2                      <- main
  v2_split  : v2 with the deficit split into quasi-fiscal (budget loans + equity to development
              institutions) and the rest, two recursive fiscal shocks
  v2_ma4    : v2 with the annual fiscal stance (4-quarter mean of the non-oil deficit, % GDP)
  v2_market, v2_ma4_market : v2 / v2_ma4 on the market core (headline without fruit & veg, fuel, coal, regulated
              utilities), X-13 re-adjusted
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import bvar  # noqa: E402
import bvar_sign_ext as E  # noqa: E402
import common  # noqa: E402
import svar_v2_data as V  # noqa: E402

OUT = common.MODELS / "svar_v2"
EXT = [("brent", "Brent", "log"), ("fed_funds", "Ставка ФРС", "level"), ("rubusd", "RUB/USD", "log")]
ROT = [("gdp_sa", "ВВП", "log"), ("usdkzt", "USD/KZT", "log"), ("cpi_sa", "Инфляция (кв/кв, SAAR)", "infl"),
       ("tonia", "TONIA", "level")]
NAMES = dict(E.NAMES)
NAMES.update({"fiscal": "Бюджет (ненефтяной дефицит)", "quasi": "Квазифискальный (институты развития)",
              "fiscal_core": "Бюджет без квазифискальных операций", "fiscal_g": "Бюджет (госпотребление)"})
CHANGES = [("2024Q4", "2025Q4"), ("2025Q3", "2026Q1"), ("2025Q4", "2026Q2"), ("2021Q4", "2022Q4"),
           ("2022Q4", "2024Q4")]
AGG = {"Σ Спрос + бюджет + ДКП": ["fiscal", "fiscal_g", "quasi", "fiscal_core", "demand", "monetary"],
       "Σ Предложение + курс + тарифы": ["supply", "tenge", "tariff"]}


def run(q, rng, domestic: list[tuple[str, str, str, str]], start: str, end: str | None = None):
    """domestic: recursive domestic variables as (column, label, transform, group)."""
    variables = EXT + [(c, lab, tr) for c, lab, tr, _ in domestic] + ROT
    n = len(variables)
    qq = q.loc[:end] if end else q
    old = (bvar.VARIABLES, bvar.FX_LAST)
    bvar.VARIABLES, bvar.FX_LAST = variables, list(range(n))
    try:
        res = bvar.estimate(qq, start, rng)
    finally:
        bvar.VARIABLES, bvar.FX_LAST = old
    n_fixed = n - 4
    INFL = n - 2
    groups = {"external": [0, 1, 2]}
    for k, (_, _, _, g) in enumerate(domestic):
        groups[g] = [3 + k]
    groups.update({"demand": [n_fixed], "supply": [n_fixed + 1], "monetary": [n_fixed + 2], "tenge": [n_fixed + 3]})
    post = res["post"]
    Y, X = post["Y"], post["X"]
    T = Y.shape[0]
    hd, base, irfs = [], [], []
    for B, S in zip(post["B"], post["Sigma"]):
        P = np.linalg.cholesky(S)
        C = E.ma_coefs(B, n, bvar.LAGS, T)
        A0 = E.rotate(P, C, rng, n_fixed, 0)
        if A0 is None:
            continue
        Phi = np.einsum("hij,jk->hik", C, A0)
        U = np.linalg.solve(A0, (Y - X @ B).T).T
        contrib = np.array([np.einsum("hs,hs->s", Phi[:t + 1, INFL, :], U[t::-1]) for t in range(T)])
        hd.append(contrib)
        base.append(Y[:, INFL] - contrib.sum(axis=1))
        irfs.append(Phi[:21])
    hd, base, irfs = np.array(hd), np.array(base), np.array(irfs)
    roll = lambda a: pd.DataFrame(a.T).rolling(4).mean().values.T  # noqa: E731
    grp_y = {g: roll(hd[:, :, s].sum(axis=2)) for g, s in groups.items()}
    idx = res["data"].index[bvar.LAGS:]
    return {"res": res, "groups": groups, "grp_y": grp_y, "base_y": roll(base), "irfs": irfs, "idx": idx,
            "actual": pd.Series(Y[:, INFL]).rolling(4).mean().values, "accepted": len(hd), "n": n,
            "INFL": INFL, "variables": variables}


def bands(o):
    rows = []
    items = {NAMES[g]: v for g, v in o["grp_y"].items()}
    for name, parts in AGG.items():
        items[name] = sum(o["grp_y"][p] for p in parts if p in o["grp_y"])
    items["Базовая траектория"] = o["base_y"]
    pos = {str(q): i for i, q in enumerate(o["idx"])}
    for a, b in CHANGES:
        if a not in pos or b not in pos:
            continue
        for g, v in items.items():
            dv = v[:, pos[b]] - v[:, pos[a]]
            lo, me, hi = np.nanpercentile(dv, [16, 50, 84])
            rows.append({"change": f"{a}->{b}", "group": g, "p16": lo, "median": me, "p84": hi,
                         "p_positive": float((dv > 0).mean())})
        rows.append({"change": f"{a}->{b}", "group": "Факт", "median": o["actual"][pos[b]] - o["actual"][pos[a]]})
    return pd.DataFrame(rows)


def levels(o):
    rows = []
    for g, v in o["grp_y"].items():
        lo, me, hi = np.nanpercentile(v, [16, 50, 84], axis=0)
        for t, q in enumerate(o["idx"]):
            if not np.isnan(me[t]):
                rows.append({"quarter": str(q), "group": NAMES[g], "p16": lo[t], "median": me[t], "p84": hi[t]})
    return pd.DataFrame(rows)


def median_target(o):
    keys = list(o["grp_y"])
    stack = np.stack([o["grp_y"][g] for g in keys] + [o["base_y"]], axis=2)[:, 3:]
    med, sd = np.median(stack, axis=0), stack.std(axis=0) + 1e-12
    d = int(np.argmin((((stack - med) / sd) ** 2).sum(axis=(1, 2))))
    mt = pd.DataFrame({"actual": o["actual"], "baseline": o["base_y"][d]}, index=[str(q) for q in o["idx"]])
    for g in keys:
        mt[NAMES[g]] = o["grp_y"][g][d]
    mt.index.name = "quarter"
    return mt.dropna()


def fiscal_irf(o, group):
    """Responses to a +1 pp of GDP shock to the fiscal variable of `group`."""
    s = o["groups"][group][0]
    irf = o["irfs"]
    sc = irf[:, :, :, s] / irf[:, 0, s, s][:, None, None]
    gdp, infl = o["n"] - 4, o["INFL"]
    rows = []
    for h in (0, 2, 4, 6, 8, 12):
        f = lambda a: f"{np.percentile(a, 50):+.3f} [{np.percentile(a, 16):+.3f}; {np.percentile(a, 84):+.3f}]"  # noqa: E731
        rows.append({"h": h, "fiscal var": f(sc[:, h, s]), "ВВП, %": f(sc[:, h, gdp]),
                     "Уровень цен, %": f(np.cumsum(sc[:, :, infl], axis=1)[:, h] / 4),
                     "Инфляция SAAR, п.п.": f(sc[:, h, infl]), "USD/KZT, %": f(sc[:, h, o["n"] - 3]),
                     "TONIA, п.п.": f(sc[:, h, o["n"] - 1])})
    return pd.DataFrame(rows)


def fevd_share(o, h=8):
    """Share of the h-quarter-ahead forecast-error variance of inflation by shock group (median)."""
    irf = o["irfs"][:, :h + 1, o["INFL"], :] ** 2
    tot = irf.sum(axis=(1, 2))
    return {NAMES[g]: float(np.median(irf[:, :, s].sum(axis=(1, 2)) / tot)) for g, s in o["groups"].items()}


def market_core_quarterly() -> pd.Series:
    """Market-core index (see bvar_market.py), X-13 re-adjusted, quarterly mean."""
    import x13
    m = pd.read_csv(common.MODELS / "cpi_components" / "market_core_index.csv", index_col=0, parse_dates=True)
    s = m["mkt_base"].loc["2012-01-01":].copy()  # from 2011-02 the automatic ARIMA does not converge
    sa = None
    for kw in (dict(calendar="kz"), dict(calendar="none"), dict(calendar="none", outliers=("ao", "ls"))):
        try:
            sa = x13.adjust(s, 12, transform="log", title="market_core", **kw).sa
            print("market core X-13:", kw)
            break
        except x13.X13Error as e:
            print("market core X-13 retry:", str(e)[:80])
    if sa is None:
        raise SystemExit("market core: X-13 did not converge")
    q = sa.resample("QS").mean()[sa.resample("QS").count() == 3]
    q.index = pd.PeriodIndex(q.index, freq="Q")
    return q


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    q, ts = V.build()
    q = q.copy()
    q["cpi_regulated_q"] = E.build_quarterly()["cpi_regulated_sa"]
    ts.to_csv(OUT / "tariff_steps_monthly.csv", float_format="%.4f")
    q[["nonoil_def_nsa", "nonoil_def", "nonoil_ma4", "quasi_def", "nonoil_core", "tariff_step_idx", "gdp_sa"]].loc["2011Q1":].to_csv(
        OUT / "inputs_quarterly.csv", float_format="%.4f")
    G = ("consumption_gov_sa", "Госпотребление", "log", "fiscal_g")
    TR_OLD = ("cpi_regulated_q", "Регулируемые тарифы", "infl", "tariff")
    TR = ("tariff_step_idx", "Тарифы (шаги)", "infl", "tariff")
    F = ("nonoil_def", "Ненефтяной дефицит, % ВВП", "level", "fiscal")
    F4 = ("nonoil_ma4", "Ненефтяной дефицит, 4 кв., % ВВП", "level", "fiscal")
    variants = {
        "old_2011": dict(domestic=[G, TR_OLD], start="2011Q2", end="2026Q1"),
        "old_2013": dict(domestic=[G, TR_OLD], start="2013Q1", end="2026Q1"),
        "v2": dict(domestic=[F, TR], start="2013Q1"),
        "v2_split": dict(domestic=[("quasi_def", "Квазифискальные, % ВВП", "level", "quasi"),
                                   ("nonoil_core", "Дефицит без квазифиск., % ВВП", "level", "fiscal_core"), TR],
                         start="2013Q1"),
    }
    qm = q.copy()
    qm["cpi_sa"] = market_core_quarterly()
    rng = np.random.default_rng(20260928)
    summary = []
    variants["v2_ma4"] = dict(domestic=[F4, TR], start="2013Q4")
    market = {"v2_market": dict(domestic=[F, TR], start="2013Q1"), "v2_ma4_market": dict(domestic=[F4, TR], start="2013Q4")}
    for name, kw in list(variants.items()) + list(market.items()):
        data = qm if name in market else q
        o = run(data, rng, **kw)
        b = bands(o)
        b.to_csv(OUT / f"changes_{name}.csv", index=False, float_format="%.3f")
        levels(o).to_csv(OUT / f"levels_{name}.csv", index=False, float_format="%.3f")
        mt = median_target(o)
        mt.to_csv(OUT / f"median_target_{name}.csv", float_format="%.3f")
        for g in ("fiscal", "quasi", "fiscal_core", "fiscal_g"):
            if g in o["groups"]:
                fiscal_irf(o, g).to_csv(OUT / f"irf_{g}_{name}.csv", index=False)
        fe = fevd_share(o)
        r = o["res"]
        print(f"[{name}] n={o['n']} T={len(o['idx'])} {o['idx'][0]}..{o['idx'][-1]} lambda={r['lambda']} "
              f"mu={r['mu']} s={r['scale']} accepted={o['accepted']}")
        summary.append({"variant": name, "sample": f"{o['idx'][0]}-{o['idx'][-1]}", "T": len(o["idx"]),
                        "lambda": r["lambda"], "accepted": o["accepted"], **{f"FEVD8 {k}": v for k, v in fe.items()}})
        if name == "v2":
            E.chart(mt.rename(columns={NAMES["fiscal"]: "Бюджет (госпотребление)"}), OUT / "hd_v2.png",
                    "Инфляция: вклады шоков, модель 2026-09")
    pd.DataFrame(summary).to_csv(OUT / "summary.csv", index=False, float_format="%.3f")


if __name__ == "__main__":
    main()
