"""Extension of bvar_sign.py: government consumption and administered (regulated-utility) prices
get their own shocks, so "demand" and "tenge" no longer have to absorb them.

    python scripts/models/bvar_sign_ext.py     # writes models/bvar_sign_ext/

Variables (quarterly, 2011Q2-2026Q1), in this order:
  external : 100 ln Brent, Fed funds, 100 ln RUB/USD                        (recursive, first)
  fiscal   : 100 ln real government final consumption (BNS SA, 2010 prices)  (recursive)
  tariffs  : 400 dln CPI "regulated utility services" (STL SA, quarterly mean) (recursive)
  rotated  : 100 ln GDP, 100 ln USD/KZT, CPI inflation SAAR, TONIA           (signs as bvar_sign)

Why recursive for the first two domestic shocks:
  * Blanchard & Perotti (2002): discretionary government consumption does not react to GDP,
    prices or rates within the quarter (budget laws, appropriations); the G shock is the part
    of G not explained by lags and by external news.
  * Regulated tariffs are approved in advance by the regulator (КРЕМ), so within the quarter
    they do not respond to GDP, the exchange rate or the rate; they may respond to G and to
    external shocks. The tariff shock hits headline CPI directly and mechanically.
Everything else as in bvar_sign.py (priors, lambda/mu/s by marginal likelihood, block
exogeneity for the external block, zero + sign restrictions on the last four).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bvar  # noqa: E402
import common  # noqa: E402

OUT = common.MODELS / "bvar_sign_ext"
N_EXT = 3

SIGNS = {"demand": (+1, None, +1, +1), "supply": (-1, None, +1, None), "monetary": (-1, None, -1, +1)}
LABELS = list(SIGNS)
TRIES = 3000
NAMES = {"external": "Внешние шоки", "fiscal": "Бюджет (госпотребление)", "tariff": "Регулируемые тарифы",
         "demand": "Спрос (прочий внутренний)", "supply": "Предложение (внутреннее)",
         "monetary": "ДКП (шок ставки)", "tenge": "Курс тенге (риск-премия)"}


def build_quarterly() -> pd.DataFrame:
    q = common.load_quarterly()
    m = common.load_monthly()
    reg = m["cpi_regulated_sa"].copy()
    reg.index = reg.index.to_timestamp()
    rq = reg.resample("QS").mean()
    rq = rq[reg.resample("QS").count() == 3]
    rq.index = pd.PeriodIndex(rq.index, freq="Q")
    q["cpi_regulated_sa"] = rq
    return q


def spec(fiscal: str | None, tariff: bool) -> list[tuple[str, str, str]]:
    v = [("brent", "Brent", "log"), ("fed_funds", "Ставка ФРС", "level"), ("rubusd", "RUB/USD", "log")]
    if fiscal:
        v.append((fiscal, "Госпотребление", "log"))
    if tariff:
        v.append(("cpi_regulated_sa", "Регулируемые тарифы", "infl"))
    v += [("gdp_sa", "ВВП", "log"), ("usdkzt", "USD/KZT", "log"),
          ("cpi_sa", "Инфляция (кв/кв, SAAR)", "infl"), ("tonia", "TONIA", "level")]
    return v


def ma_coefs(B, n, p, H):
    A = bvar.companion(B, n, p)
    out = np.zeros((H + 1, n, n))
    Ah = np.eye(n * p)
    for h in range(H + 1):
        out[h] = Ah[:n, :n]
        Ah = Ah @ A
    return out


def ok(resp, pattern):
    for v, s in enumerate(pattern):
        if s is not None and np.any(resp[:, v] * s <= 0):
            return False
    return True


def rotate(P, C, rng, n_fixed, hmax):
    """Columns 0..n_fixed-1 recursive; the last four rotated. Returns impact matrix with the
    rotated columns ordered demand, supply, monetary, tenge."""
    n = P.shape[0]
    r0 = n_fixed  # first rotated variable = GDP
    for _ in range(TRIES):
        z = rng.standard_normal(3)
        qfx = np.concatenate([[0.0], z / np.linalg.norm(z)])
        M = rng.standard_normal((4, 3))
        M -= np.outer(qfx, qfx @ M)
        Qc, _ = np.linalg.qr(M)
        Q = np.eye(n)
        Q[r0:, r0:] = np.column_stack([Qc, qfx])
        A0 = P @ Q
        R = np.einsum("hij,jk->hik", C[:hmax + 1], A0)[:, r0:, :]
        t = n - 1
        if R[0, 1, t] < 0:
            A0[:, t] *= -1
            R[:, :, t] *= -1
        if np.any(R[:, 2, t] <= 0) or np.any(R[:, 1, t] <= 0):
            continue
        cand = []
        for j in (r0, r0 + 1, r0 + 2):
            cand.append([(lab, s) for s in (1, -1) for lab in LABELS if ok(s * R[:, :, j], SIGNS[lab])])
        found = next(((a, b, c) for a in cand[0] for b in cand[1] for c in cand[2]
                      if len({a[0], b[0], c[0]}) == 3), None)
        if not found:
            continue
        cols = {lab: s * A0[:, j] for j, (lab, s) in zip((r0, r0 + 1, r0 + 2), found)}
        return np.column_stack([A0[:, :r0], cols["demand"], cols["supply"], cols["monetary"], A0[:, t]])
    return None


def run(q, rng, fiscal="consumption_gov_sa", tariff=True, hmax=0, start=bvar.START):
    variables = spec(fiscal, tariff)
    n = len(variables)
    old = (bvar.VARIABLES, bvar.FX_LAST)
    bvar.VARIABLES = variables
    bvar.FX_LAST = list(range(n))  # the robustness ordering of bvar.py is not used here
    try:
        res = bvar.estimate(q, start, rng)
    finally:
        bvar.VARIABLES, bvar.FX_LAST = old
    n_fixed = n - 4
    INFL = n - 2
    groups = {"external": [0, 1, 2]}
    k = 3
    if fiscal:
        groups["fiscal"] = [k]; k += 1
    if tariff:
        groups["tariff"] = [k]; k += 1
    groups.update({"demand": [k], "supply": [k + 1], "monetary": [k + 2], "tenge": [k + 3]})
    post = res["post"]
    Y, X = post["Y"], post["X"]
    T = Y.shape[0]
    hd, base, irfs = [], [], []
    for B, S in zip(post["B"], post["Sigma"]):
        P = np.linalg.cholesky(S)
        C = ma_coefs(B, n, bvar.LAGS, T)
        A0 = rotate(P, C, rng, n_fixed, hmax)
        if A0 is None:
            continue
        Phi = np.einsum("hij,jk->hik", C, A0)
        U = np.linalg.solve(A0, (Y - X @ B).T).T
        contrib = np.array([np.einsum("hs,hs->s", Phi[:t + 1, INFL, :], U[t::-1]) for t in range(T)])
        hd.append(contrib)
        base.append(Y[:, INFL] - contrib.sum(axis=1))
        irfs.append(Phi[:21])
    hd, base, irfs = np.array(hd), np.array(base), np.array(irfs)
    roll = lambda a: pd.DataFrame(a.T).rolling(4).mean().values.T  # [draw, t]  # noqa: E731
    grp_y = {g: roll(hd[:, :, s].sum(axis=2)) for g, s in groups.items()}
    base_y = roll(base)
    idx = res["data"].index[bvar.LAGS:]
    return {"res": res, "groups": groups, "grp_y": grp_y, "base_y": base_y, "irfs": irfs, "idx": idx,
            "actual": pd.Series(Y[:, INFL]).rolling(4).mean().values, "accepted": len(hd),
            "n": n, "INFL": INFL, "variables": variables}


def bands(o, agg=None):
    rows = []
    items = {NAMES[g]: v for g, v in o["grp_y"].items()}
    for name, parts in (agg or {}).items():
        items[name] = sum(o["grp_y"][p] for p in parts if p in o["grp_y"])
    items["Базовая траектория"] = o["base_y"]
    for g, v in items.items():
        lo, me, hi = np.nanpercentile(v, [16, 50, 84], axis=0)
        for t, q in enumerate(o["idx"]):
            if not np.isnan(me[t]):
                rows.append({"quarter": str(q), "group": g, "p16": lo[t], "median": me[t], "p84": hi[t]})
    pos = {str(q): i for i, q in enumerate(o["idx"])}
    for a, b in CHANGES:
        for g, v in items.items():
            dv = v[:, pos[b]] - v[:, pos[a]]
            lo, me, hi = np.percentile(dv, [16, 50, 84])
            rows.append({"quarter": f"{a}->{b}", "group": g, "p16": lo, "median": me, "p84": hi,
                         "p_positive": float((dv > 0).mean())})
        rows.append({"quarter": f"{a}->{b}", "group": "Факт", "median": o["actual"][pos[b]] - o["actual"][pos[a]]})
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


def fiscal_irf(o):
    """Responses to a G shock normalised to +1 % of government consumption."""
    if "fiscal" not in o["groups"]:
        return None
    s = o["groups"]["fiscal"][0]
    irf = o["irfs"]
    sc = irf[:, :, :, s] / irf[:, 0, s, s][:, None, None]
    gdp, infl = o["n"] - 4, o["INFL"]
    rows = []
    for h in (0, 2, 4, 8):
        f = lambda a: f"{np.percentile(a, 50):+.3f} [{np.percentile(a, 16):+.3f}; {np.percentile(a, 84):+.3f}]"  # noqa: E731
        rows.append({"h": h, "Госпотребление, %": f(sc[:, h, s]), "ВВП, %": f(sc[:, h, gdp]),
                     "Уровень цен, %": f(np.cumsum(sc[:, :, infl], axis=1)[:, h] / 4),
                     "TONIA, п.п.": f(sc[:, h, o["n"] - 1])})
    return pd.DataFrame(rows)


CHANGES = [("2024Q4", "2025Q4"), ("2025Q3", "2026Q1"), ("2021Q4", "2022Q4"), ("2022Q4", "2024Q4")]
AGG = {"Σ Спрос + бюджет + ДКП": ["fiscal", "demand", "monetary"],
       "Σ Предложение + курс + тарифы": ["supply", "tenge", "tariff"]}


def chart(mt, path, title):
    import matplotlib.pyplot as plt

    d = mt.loc["2018Q1":]
    fig, ax = common.figure(10.5, 5.4)
    x = np.arange(len(d))
    colors = {"Внешние шоки": "#898781", "Бюджет (госпотребление)": "#9b5de5", "Спрос (прочий внутренний)": "#eb6834",
              "ДКП (шок ставки)": "#1baf7a", "Регулируемые тарифы": "#d62839",
              "Предложение (внутреннее)": "#2a78d6", "Курс тенге (риск-премия)": "#eda100"}
    pos, neg = np.zeros(len(d)), np.zeros(len(d))
    for g, c in colors.items():
        if g not in d:
            continue
        v = d[g].values
        bottom = np.where(v >= 0, pos, neg)
        ax.bar(x, v, bottom=bottom, width=0.82, color=c, label=g, edgecolor=common.SURFACE, linewidth=0.6)
        pos += np.where(v >= 0, v, 0)
        neg += np.where(v < 0, v, 0)
    ax.plot(x, (d.actual - d.baseline).values, color=common.INK, lw=1.5, label="Факт − базовая")
    common.zero_line(ax)
    ticks = [i for i, q in enumerate(d.index) if q.endswith("Q1")]
    ax.set_xticks(ticks)
    ax.set_xticklabels([d.index[i][:4] for i in ticks])
    ax.set_ylabel("п.п.", color=common.INK_2, fontsize=9)
    common.title(ax, title, "Вклады в отклонение инфляции г/г от базовой траектории, п.п.")
    ax.legend(frameon=False, fontsize=8.3, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()
    common.save(fig, path)


def main():
    rng = np.random.default_rng(20260928)
    q = build_quarterly()
    OUT.mkdir(parents=True, exist_ok=True)
    variants = {"full": dict(), "full_h01": dict(hmax=1), "fiscal_only": dict(tariff=False),
                "tariff_only": dict(fiscal=None)}
    out = {}
    for name, kw in variants.items():
        o = run(q, rng, **kw)
        b = bands(o, AGG)
        b.to_csv(OUT / f"bands_{name}.csv", index=False, float_format="%.3f")
        mt = median_target(o)
        mt.to_csv(OUT / f"median_target_{name}.csv", float_format="%.3f")
        fi = fiscal_irf(o)
        if fi is not None:
            fi.to_csv(OUT / f"fiscal_irf_{name}.csv", index=False)
        r = o["res"]
        err = (mt.actual - mt.baseline - mt.drop(columns=["actual", "baseline"]).sum(axis=1)).abs().max()
        print(f"[{name}] n={o['n']} lambda={r['lambda']} mu={r['mu']} s={r['scale']} "
              f"rejected={r['post']['rejected']} accepted={o['accepted']} additivity={err:.1e}")
        out[name] = (o, b, mt)
    chart(out["full"][2], OUT / "hd_cpi_ext.png", "Инфляция: вклады спроса, бюджета, тарифов и курса")
    return out


if __name__ == "__main__":
    main()
