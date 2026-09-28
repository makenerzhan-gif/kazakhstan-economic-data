"""Demand vs supply decomposition of Kazakhstan's CPI inflation: the BVAR of bvar.py with the
domestic block identified by sign restrictions (plus one zero restriction).

    python scripts/models/bvar_sign.py        # writes models/bvar_sign/

Reduced form: identical to bvar.py (same variables, sample, Minnesota prior, lambda/mu/s chosen
by marginal likelihood, block exogeneity, crisis-quarter variance scaling).

Identification. External shocks (Brent, Fed, RUB/USD) stay recursive and first, as in bvar.py.
The domestic 4x4 block [GDP, USD/KZT, inflation, TONIA] is rotated: impact = chol(Sigma) @
blockdiag(I3, Q), Q orthonormal drawn uniformly (Rubio-Ramirez, Waggoner & Zha 2010), with
signs on impact (h = 0; robustness: h = 0..1):

    shock          GDP   USD/KZT  inflation  TONIA
    demand          +       .        +         +
    supply          -       .        +         .
    monetary        -       .        -         +
    tenge (risk)    0       +        +         .

The tenge shock has zero impact on GDP within the quarter (as in bvar.py's recursive order,
where GDP precedes the exchange rate); that zero is what separates it from the supply shock.
Demand vs monetary: same comovement of GDP and prices, opposite sign of the rate.
Uncertainty: every accepted (draw, rotation) pair; contributions reported as medians and
16-84 percentiles; the stacked chart uses the Fry-Pagan median-target pair so bars add up.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bvar  # noqa: E402
import common  # noqa: E402

OUT = common.MODELS / "bvar_sign"
N_EXT = 3
GDP, FX, INFL, RATE = 3, 4, 5, 6
LABELS = ["demand", "supply", "monetary"]
# sign patterns over domestic vars (GDP, FX, INFL, RATE); None = unrestricted
SIGNS = {
    "demand": (+1, None, +1, +1),
    "supply": (-1, None, +1, None),
    "monetary": (-1, None, -1, +1),
}
NAMES = {"external": "Внешние шоки", "demand": "Спрос (внутренний)", "supply": "Предложение (внутреннее)",
         "monetary": "ДКП (шок ставки)", "tenge": "Курс тенге (риск-премия)"}
TRIES = 3000
N_ROT_PER_DRAW = 1


def ma_coefs(B: np.ndarray, n: int, p: int, H: int) -> np.ndarray:
    A = bvar.companion(B, n, p)
    out = np.zeros((H + 1, n, n))
    Ah = np.eye(n * p)
    for h in range(H + 1):
        out[h] = Ah[:n, :n]
        Ah = Ah @ A
    return out


def ok(resp: np.ndarray, pattern) -> bool:
    """resp: [h, 4] domestic responses of one shock over the restricted horizons."""
    for v, s in enumerate(pattern):
        if s is None:
            continue
        if np.any(resp[:, v] * s <= 0):
            return False
    return True


def rotate(P: np.ndarray, C: np.ndarray, rng: np.random.Generator, hmax: int) -> np.ndarray | None:
    """Return the 7x7 structural impact matrix, columns ordered
    [ext0, ext1, ext2, demand, supply, monetary, tenge], or None."""
    n = P.shape[0]
    Pd = P
    for _ in range(TRIES):
        z = rng.standard_normal(3)
        qfx = np.concatenate([[0.0], z / np.linalg.norm(z)])
        M = rng.standard_normal((4, 3))
        M -= np.outer(qfx, qfx @ M)
        Qc, _ = np.linalg.qr(M)
        Qd = np.column_stack([Qc, qfx])
        Q = np.eye(n)
        Q[N_EXT:, N_EXT:] = Qd
        A0 = Pd @ Q
        R = np.einsum("hij,jk->hik", C[:hmax + 1], A0)[:, N_EXT:, :]  # [h, dom var, shock]
        # tenge column: normalise to depreciation, check inflation
        if R[0, 1, 6] < 0:
            A0[:, 6] *= -1
            R[:, :, 6] *= -1
        if np.any(R[:, 2, 6] <= 0) or np.any(R[:, 1, 6] <= 0):
            continue
        # the three other columns: find a sign + label assignment
        cand = []
        for j in (3, 4, 5):
            opts = []
            for sgn in (1, -1):
                for lab in LABELS:
                    if ok(sgn * R[:, :, j], SIGNS[lab]):
                        opts.append((lab, sgn))
            cand.append(opts)
        found = None
        for a in cand[0]:
            for b in cand[1]:
                for c in cand[2]:
                    if len({a[0], b[0], c[0]}) == 3:
                        found = (a, b, c)
                        break
                if found:
                    break
            if found:
                break
        if not found:
            continue
        out = A0[:, :3].copy()
        cols = {}
        for j, (lab, sgn) in zip((3, 4, 5), found):
            cols[lab] = sgn * A0[:, j]
        return np.column_stack([out, cols["demand"], cols["supply"], cols["monetary"], A0[:, 6]])
    return None


def identify(res: dict, rng: np.random.Generator, hmax: int = 0, H: int = 20) -> dict:
    post = res["post"]
    n = res["data"].shape[1]
    Y, X = post["Y"], post["X"]
    T = Y.shape[0]
    keep_irf, keep_hd, keep_base, keep_fevd = [], [], [], []
    tried = 0
    for B, S in zip(post["B"], post["Sigma"]):
        tried += 1
        P = np.linalg.cholesky(S)
        C = ma_coefs(B, n, bvar.LAGS, max(H, T))
        A0 = rotate(P, C, rng, hmax)
        if A0 is None:
            continue
        Phi = np.einsum("hij,jk->hik", C, A0)  # [h, var, shock]
        E = Y - X @ B
        U = np.linalg.solve(A0, E.T).T
        contrib = np.zeros((T, n, n))
        for t in range(T):
            contrib[t] = np.einsum("hvs,hs->vs", Phi[:t + 1], U[t::-1])
        keep_irf.append(Phi[:H + 1])
        keep_hd.append(contrib[:, INFL, :])
        keep_base.append(Y[:, INFL] - contrib[:, INFL, :].sum(axis=1))
        c2 = np.cumsum(Phi[:H + 1] ** 2, axis=0)
        keep_fevd.append(c2 / c2.sum(axis=2, keepdims=True))
    return {"irf": np.array(keep_irf), "hd": np.array(keep_hd), "base": np.array(keep_base),
            "fevd": np.array(keep_fevd), "accepted": len(keep_irf), "tried": tried,
            "index": res["data"].index[bvar.LAGS:], "Y": Y[:, INFL]}


AGG = {"Σ Спрос + ДКП": ["demand", "monetary"], "Σ Предложение + курс": ["supply", "tenge"]}
CHANGES = [("2024Q4", "2025Q4"), ("2025Q3", "2026Q1"), ("2021Q4", "2022Q4"), ("2022Q4", "2024Q4")]
GROUPS = {"external": [0, 1, 2], "demand": [3], "supply": [4], "monetary": [5], "tenge": [6]}


def yoy(a: np.ndarray) -> np.ndarray:
    """mean of four quarterly SAAR rates ~ y/y log inflation; works on last axis=time? no: axis 0."""
    s = pd.DataFrame(a)
    return s.rolling(4).mean().values


def hd_table(idn: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Median-target frame (adds up) and a band frame (median, p16, p84 per group)."""
    idx = idn["index"]
    D = idn["hd"].shape[0]
    grp = {g: idn["hd"][:, :, s].sum(axis=2) for g, s in GROUPS.items()}  # [draw, t]
    grp_y = {g: np.array([pd.Series(v[d]).rolling(4).mean().values for d in range(D)]) for g, v in grp.items()}
    base_y = np.array([pd.Series(idn["base"][d]).rolling(4).mean().values for d in range(D)])
    actual_y = pd.Series(idn["Y"]).rolling(4).mean().values
    # median target on the decomposition itself: the pair whose y/y contributions (and baseline)
    # are closest to the pointwise medians, so the bars add up AND look like the medians.
    # (The Fry-Pagan target on IRFs picked pairs whose baseline swung by 3 pp between runs.)
    stack = np.stack([grp_y[g] for g in GROUPS] + [base_y], axis=2)[:, 3:]  # [draw, t, k]
    med, sd = np.median(stack, axis=0), stack.std(axis=0) + 1e-12
    d = int(np.argmin((((stack - med) / sd) ** 2).sum(axis=(1, 2))))
    mt = pd.DataFrame({"actual": actual_y, "baseline": base_y[d]}, index=idx)
    for g in GROUPS:
        mt[NAMES[g]] = grp_y[g][d]
    rows = []
    for g in GROUPS:
        lo, me, hi = np.nanpercentile(grp_y[g], [16, 50, 84], axis=0)
        for t, q in enumerate(idx):
            rows.append({"quarter": str(q), "group": NAMES[g], "p16": lo[t], "median": me[t], "p84": hi[t]})
    for g, parts in AGG.items():
        v = sum(grp_y[x] for x in parts)
        lo, me, hi = np.nanpercentile(v, [16, 50, 84], axis=0)
        for t, q in enumerate(idx):
            rows.append({"quarter": str(q), "group": g, "p16": lo[t], "median": me[t], "p84": hi[t]})
    # changes between quarters (what drove the rise / the fall), per draw then percentiles
    pos = {str(q): i for i, q in enumerate(idx)}
    for a, b in CHANGES:
        if a not in pos or b not in pos:
            continue
        ia, ib = pos[a], pos[b]
        items = {NAMES[g]: grp_y[g] for g in GROUPS} | {g: sum(grp_y[x] for x in parts) for g, parts in AGG.items()}
        items["Базовая траектория"] = base_y
        for g, v in items.items():
            dv = v[:, ib] - v[:, ia]
            lo, me, hi = np.percentile(dv, [16, 50, 84])
            rows.append({"quarter": f"{a}->{b}", "group": g, "p16": lo, "median": me, "p84": hi,
                         "p_positive": float((dv > 0).mean())})
        rows.append({"quarter": f"{a}->{b}", "group": "Факт", "median": actual_y[ib] - actual_y[ia]})
    lo, me, hi = np.nanpercentile(base_y, [16, 50, 84], axis=0)
    for t, q in enumerate(idx):
        rows.append({"quarter": str(q), "group": "Базовая траектория", "p16": lo[t], "median": me[t], "p84": hi[t]})
    mt.index = mt.index.astype(str)
    mt.index.name = "quarter"
    return mt.dropna(), pd.DataFrame(rows).dropna(subset=["median"])


def fevd_infl(idn: dict) -> pd.DataFrame:
    f = np.median(idn["fevd"], axis=0)
    rows = []
    for h in (0, 4, 8, 20):
        r = {"h": h}
        for g, s in GROUPS.items():
            r[NAMES[g]] = 100 * f[h, INFL, s].sum()
        rows.append(r)
    return pd.DataFrame(rows)


def irf_summary(idn: dict) -> pd.DataFrame:
    """Responses to one-s.d. shocks, median [16;84], for GDP (%), price level (%), TONIA (pp)."""
    irf = idn["irf"]
    rows = []
    for g, s in [("demand", 3), ("supply", 4), ("monetary", 5), ("tenge", 6)]:
        for h in (0, 4, 8):
            gd = np.percentile(irf[:, h, GDP, s], [16, 50, 84])
            pl = np.percentile(np.cumsum(irf[:, :, INFL, s], axis=1)[:, h] / 4, [16, 50, 84])
            tn = np.percentile(irf[:, h, RATE, s], [16, 50, 84])
            fx = np.percentile(irf[:, h, FX, s], [16, 50, 84])
            f = lambda a: f"{a[1]:+.2f} [{a[0]:+.2f}; {a[2]:+.2f}]"  # noqa: E731
            rows.append({"Шок": NAMES[g], "h": h, "ВВП, %": f(gd), "Уровень цен, %": f(pl),
                         "TONIA, п.п.": f(tn), "USD/KZT, %": f(fx)})
    return pd.DataFrame(rows)


def chart(mt: pd.DataFrame, path: Path, title: str, sub: str) -> None:
    import matplotlib.pyplot as plt

    d = mt.loc["2018Q1":]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7.2), sharex=True, gridspec_kw={"height_ratios": [1, 2.2]})
    common.style(fig, *axes)
    x = np.arange(len(d))
    ax = axes[0]
    ax.plot(x, d.actual, color=common.INK, lw=1.8, label="Инфляция, г/г (модельная мера)")
    ax.plot(x, d.baseline, color=common.MUTED, lw=1.4, ls="--", label="Базовая траектория")
    ax.set_ylabel("%", color=common.INK_2, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=common.INK)
    ax = axes[1]
    colors = {"Внешние шоки": "#898781", "Спрос (внутренний)": "#eb6834", "Предложение (внутреннее)": "#2a78d6",
              "ДКП (шок ставки)": "#1baf7a", "Курс тенге (риск-премия)": "#eda100"}
    pos, neg = np.zeros(len(d)), np.zeros(len(d))
    for g, c in colors.items():
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
    ax.set_title(sub, loc="left", fontsize=9.5, color=common.INK_2)
    ax.legend(frameon=False, fontsize=8.3, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()
    common.save(fig, path)


def chart_changes(bands: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    periods = [("2024Q4->2025Q4", "Разгон: IV кв. 2024 → IV кв. 2025"),
               ("2025Q3->2026Q1", "Разворот: III кв. 2025 → I кв. 2026")]
    order = ["Внешние шоки", "Спрос (внутренний)", "ДКП (шок ставки)", "Предложение (внутреннее)",
             "Курс тенге (риск-премия)", "Σ Спрос + ДКП", "Σ Предложение + курс"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    common.style(fig, *axes)
    for ax, (key, head) in zip(axes, periods):
        b = bands[bands.quarter == key].set_index("group")
        y = np.arange(len(order))[::-1]
        for yi, g in zip(y, order):
            r = b.loc[g]
            col = "#0b0b0b" if g.startswith("Σ") else "#2a78d6"
            ax.plot([r.p16, r.p84], [yi, yi], color=col, lw=2.2, alpha=0.45, solid_capstyle="round")
            ax.plot(r["median"], yi, "o", color=col, ms=7)
            ax.text(r.p84 + 0.12, yi, f"{r['median']:+.1f}  (P>0 = {r.p_positive:.0%})", va="center",
                    fontsize=8.3, color=common.INK_2)
        ax.axvline(0, color=common.BASELINE, lw=1)
        ax.axhline(1.5, color=common.GRID, lw=0.8)
        ax.set_yticks(y)
        ax.set_yticklabels(order, fontsize=9)
        fact = b.loc["Факт", "median"]
        ax.set_title(f"{head}\nфакт: {fact:+.1f} п.п.", loc="left", fontsize=10.5, color=common.INK,
                     fontweight="bold")
        ax.set_xlabel("изменение вклада, п.п. (медиана и 68 % интервал)", fontsize=8.5, color=common.INK_2)
        ax.grid(True, axis="x", color=common.GRID, linewidth=0.6)
        lo = min(b.loc[order, "p16"].min(), 0) - 0.3
        hi = b.loc[order, "p84"].max() + 1.9
        ax.set_xlim(lo, hi)
    fig.tight_layout()
    common.save(fig, path)


def run_variant(q, rng, hmax=0, gdp_col=None, start=bvar.START):
    if gdp_col:
        old = bvar.VARIABLES[GDP]
        bvar.VARIABLES[GDP] = (gdp_col, "Потребление", "log")
    try:
        res = bvar.estimate(q, start, rng)
    finally:
        if gdp_col:
            bvar.VARIABLES[GDP] = old
    idn = identify(res, rng, hmax=hmax)
    return res, idn


def main() -> None:
    rng = np.random.default_rng(20260927)
    q = common.load_quarterly()
    OUT.mkdir(parents=True, exist_ok=True)
    variants = {
        "base": dict(),
        "h01": dict(hmax=1),
        "cons": dict(gdp_col="consumption_hh_sa"),
    }
    summary = {}
    for name, kw in variants.items():
        res, idn = run_variant(q, rng, **kw)
        mt, bands = hd_table(idn)
        mt.to_csv(OUT / f"hd_median_target_{name}.csv", float_format="%.3f")
        bands.to_csv(OUT / f"hd_bands_{name}.csv", index=False, float_format="%.3f")
        fevd_infl(idn).to_csv(OUT / f"fevd_infl_{name}.csv", index=False, float_format="%.1f")
        irf_summary(idn).to_csv(OUT / f"irf_summary_{name}.csv", index=False)
        # additivity check on median target
        resid = (mt.actual - mt.baseline - mt[[NAMES[g] for g in GROUPS]].sum(axis=1)).abs().max()
        print(f"[{name}] lambda={res['lambda']} mu={res['mu']} s={res['scale']} "
              f"accepted {idn['accepted']}/{idn['tried']}  max additivity error {resid:.2e}")
        summary[name] = (res, idn, mt, bands)
    chart(summary["base"][2], OUT / "hd_cpi_sign.png",
          "Инфляция в Казахстане: вклады шоков спроса и предложения",
          "Вклады в отклонение инфляции г/г от базовой траектории, п.п. (SVAR, знаковые ограничения)")
    chart_changes(summary["base"][3], OUT / "changes_sign.png")
    return summary


if __name__ == "__main__":
    main()
