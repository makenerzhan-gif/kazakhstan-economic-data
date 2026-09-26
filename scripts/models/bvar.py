"""Bayesian VAR for Kazakhstan with an exogenous external block.

    python scripts/models/bvar.py           # writes models/bvar/

Variables (quarterly, model_data/quarterly.csv; x100 logs, so responses are in %):
  external: 100 ln Brent (USD), Fed funds rate, 100 ln RUB/USD
  domestic: 100 ln real GDP (BNS SA), CPI inflation (400 dln CPI SA, % SAAR), TONIA,
            100 ln USD/KZT
Inflation, not the CPI level: over 2011-2026 the log price level behaves close to I(2) and a
levels VAR rejected most draws as explosive. Sample: 2011Q2 (the chained CPI starts 2011-01) to the last quarter with every variable;
robustness sample from 2016Q1 (inflation targeting and the free float).

Prior: Minnesota through dummy observations (Banbura, Giannone & Reichlin 2010): random-walk
prior means for every variable, overall tightness lambda, lag decay 1/l, a sum-of-coefficients
prior with tightness mu, a diffuse constant, and scales sigma_i from AR(1) residuals.
lambda and mu are the values that maximise the closed-form marginal likelihood of the
conjugate Normal-inverse-Wishart model on a grid (Giannone, Lenza & Primiceri 2015 pick
hyperparameters the same way).

Small open economy: Kazakhstan does not move oil prices, the Fed or the rouble, so domestic
lags are excluded from the external equations (block exogeneity). With that restriction the
model is a SUR, so the posterior is drawn by Gibbs sampling -- beta | Sigma is GLS on the
data augmented with the same dummy observations, Sigma | beta is inverse Wishart -- and
explosive draws (companion root above MAX_ROOT) are discarded. The turbulent quarters get
their shock variance scaled by s^2 (Lenza & Primiceri 2022), with s picked jointly with
lambda and mu by marginal likelihood; the rows are divided by s, and the marginal likelihood
carries the Jacobian -n sum(ln s_t).

Identification: recursive, in the order listed. External shocks come first; the exchange
rate passes into prices within the quarter; the policy rate reacts to everything in the same
quarter, so the policy shock is TONIA's move beyond that reaction. With the exchange rate
ordered last instead (FX_LAST, reported as a robustness column) the 2015 devaluation cannot
reach prices within the quarter, and the pass-through estimate collapses to ~5 %. Shocks reported: oil (+10 % Brent), policy (+1 pp TONIA), tenge (+10 % USD/KZT,
i.e. depreciation). Bands are the posterior 16th-84th percentiles. The historical
decomposition uses the Fry & Pagan (2011) median-target draw so the contributions add up.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import multigammaln

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT = common.MODELS / "bvar"
VARIABLES = [  # (column, label, transform: log = 100 ln, infl = 400 dln (% SAAR), level)
    ("brent", "Brent", "log"),
    ("fed_funds", "Ставка ФРС", "level"),
    ("rubusd", "RUB/USD", "log"),
    ("gdp_sa", "ВВП", "log"),
    ("usdkzt", "USD/KZT", "log"),
    ("cpi_sa", "Инфляция (кв/кв, SAAR)", "infl"),
    ("tonia", "TONIA", "level"),
]
GDP, FX, INFL, RATE = 3, 4, 5, 6
FX_LAST = [0, 1, 2, GDP, INFL, RATE, FX]  # robustness ordering: the exchange rate last
N_EXTERNAL = 3
LAGS = 2
START = "2011Q2"
ROBUST_START = "2016Q1"
LAMBDAS = [0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5]
MUS = [0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 100.0]
# Lenza & Primiceri (2022): quarters whose shock variance is scaled up by a factor s chosen by
# marginal likelihood -- the 2014 devaluation, the 2015 float and liquidity squeeze (TONIA
# 15-37 %), and the pandemic -- so they inform the model without dominating it.
TURBULENT = ["2014Q1", "2014Q4", "2015Q3", "2015Q4", "2016Q1", "2020Q2", "2020Q3"]
SCALES = [1.0, 2.0, 3.0, 5.0, 8.0]
CONST_EPS = 1e-3
HORIZON = 20
DRAWS, BURN, THIN = 1000, 1000, 3
MAX_ROOT = 1.01
SEED = 20260926
SHOCKS = {  # name: (shock index, variable index normalised, size)
    "oil": (0, 0, 10.0),
    "policy": (RATE, RATE, 1.0),
    "tenge": (FX, FX, 10.0),
}
GROUPS = {"Внешние шоки": [0, 1, 2], "Прочие внутренние": [GDP, INFL], "Ставка (ДКП)": [RATE],
          "Курс тенге": [FX]}


# ---------------------------------------------------------------- data
def load_data(q: pd.DataFrame, start: str) -> pd.DataFrame:
    cols = [c for c, _, _ in VARIABLES]
    d = q.loc[(pd.Period(start, "Q") - 1):, cols].copy()
    for c, _, tr in VARIABLES:
        if tr == "log":
            d[c] = 100 * np.log(d[c])
        elif tr == "infl":
            d[c] = 400 * np.log(d[c]).diff()
    d = d.loc[start:].dropna()
    idx = d.index
    if len(idx) != (idx[-1] - idx[0]).n + 1:
        raise SystemExit("bvar: the sample has internal gaps")
    return d


def lagmat(Y: np.ndarray, p: int) -> tuple[np.ndarray, np.ndarray]:
    T = Y.shape[0]
    X = np.hstack([Y[p - j:T - j] for j in range(1, p + 1)] + [np.ones((T - p, 1))])
    return Y[p:], X


# ---------------------------------------------------------------- prior
def ar1_scale(Y: np.ndarray) -> np.ndarray:
    s = []
    for i in range(Y.shape[1]):
        y, x = Y[1:, i], np.column_stack([np.ones(len(Y) - 1), Y[:-1, i]])
        b = np.linalg.lstsq(x, y, rcond=None)[0]
        s.append(np.std(y - x @ b, ddof=2))
    return np.array(s)


def dummies(Y: np.ndarray, p: int, lam: float, mu: float) -> tuple[np.ndarray, np.ndarray]:
    n = Y.shape[1]
    sig = ar1_scale(Y)
    delta = np.ones(n)
    k = n * p + 1
    # Minnesota: coefficients
    Yd1 = np.vstack([np.diag(delta * sig) / lam, np.zeros((n * (p - 1), n))])
    Xd1 = np.hstack([np.kron(np.diag(np.arange(1, p + 1)), np.diag(sig) / lam), np.zeros((n * p, 1))])
    # covariance
    Yd2, Xd2 = np.diag(sig), np.zeros((n, k))
    # sum of coefficients
    ybar = Y[:p].mean(axis=0)
    Yd3 = np.diag(delta * ybar) / mu
    Xd3 = np.hstack([np.kron(np.ones((1, p)), np.diag(delta * ybar) / mu), np.zeros((n, 1))])
    # constant
    Yd4 = np.zeros((1, n))
    Xd4 = np.hstack([np.zeros((1, n * p)), np.full((1, 1), CONST_EPS)])
    return np.vstack([Yd1, Yd2, Yd3, Yd4]), np.vstack([Xd1, Xd2, Xd3, Xd4])


def _niw_terms(Y: np.ndarray, X: np.ndarray) -> tuple[float, float, int]:
    XtX = X.T @ X
    B = np.linalg.solve(XtX, X.T @ Y)
    E = Y - X @ B
    return np.linalg.slogdet(XtX)[1], np.linalg.slogdet(E.T @ E)[1], Y.shape[0]


def log_ml(Y: np.ndarray, X: np.ndarray, Yd: np.ndarray, Xd: np.ndarray) -> float:
    """log p(Y | dummies) for the conjugate NIW model with the dummy-observation prior."""
    n, k, T = Y.shape[1], X.shape[1], Y.shape[0]
    ldx_d, lds_d, Td = _niw_terms(Yd, Xd)
    ldx_s, lds_s, Ts = _niw_terms(np.vstack([Yd, Y]), np.vstack([Xd, X]))
    return (-n * T / 2 * np.log(np.pi)
            + multigammaln((Ts - k) / 2, n) - multigammaln((Td - k) / 2, n)
            + n / 2 * (ldx_d - ldx_s)
            + (Td - k) / 2 * lds_d - (Ts - k) / 2 * lds_s)


def row_weights(index: pd.PeriodIndex, scale: float) -> np.ndarray:
    """1/s for the turbulent quarters, 1 elsewhere (rows of Y after the lags)."""
    turbulent = {pd.Period(t, "Q") for t in TURBULENT}
    return np.array([1.0 / scale if t in turbulent else 1.0 for t in index])


def select_hyper(Ylev: np.ndarray, p: int, index: pd.PeriodIndex,
                 scales: list[float] = SCALES) -> tuple[float, float, float, pd.DataFrame]:
    Y, X = lagmat(Ylev, p)
    n = Y.shape[1]
    grid = []
    for scale in scales:
        w = row_weights(index[p:], scale)
        Yw, Xw = Y * w[:, None], X * w[:, None]
        jac = n * np.log(w).sum()  # density of Y, not of Y / s
        for lam in LAMBDAS:
            for mu in MUS:
                Yd, Xd = dummies(Ylev, p, lam, mu)
                grid.append({"scale": scale, "lambda": lam, "mu": mu, "log_ml": log_ml(Yw, Xw, Yd, Xd) + jac})
    g = pd.DataFrame(grid)
    best = g.loc[g.log_ml.idxmax()]
    return float(best["lambda"]), float(best["mu"]), float(best["scale"]), g


# ---------------------------------------------------------------- posterior
def regressor_sets(n: int, p: int, n_ext: int) -> list[np.ndarray]:
    """Columns of X each equation uses: external equations see only external lags."""
    k = n * p + 1
    ext_cols = [lag * n + j for lag in range(p) for j in range(n_ext)] + [k - 1]
    return [np.array(ext_cols) if i < n_ext else np.arange(k) for i in range(n)]


def gibbs(Ylev: np.ndarray, p: int, lam: float, mu: float, n_ext: int, rng: np.random.Generator,
          draws: int = DRAWS, burn: int = BURN, thin: int = THIN, weights: np.ndarray | None = None) -> dict:
    Y, X = lagmat(Ylev, p)
    Yd, Xd = dummies(Ylev, p, lam, mu)
    w = np.ones(len(Y)) if weights is None else weights
    Ys, Xs = np.vstack([Yd, Y * w[:, None]]), np.vstack([Xd, X * w[:, None]])
    T, n = Ys.shape
    k = X.shape[1]
    sets = regressor_sets(n, p, n_ext)
    sizes = [len(s) for s in sets]
    offs = np.concatenate([[0], np.cumsum(sizes)])
    XtX = Xs.T @ Xs
    XtY = Xs.T @ Ys
    B = np.linalg.solve(XtX, XtY)
    Sigma = (Ys - Xs @ B).T @ (Ys - Xs @ B) / T
    out_B, out_S, rejected, kept, it = [], [], 0, 0, 0
    while kept < draws:
        it += 1
        Si = np.linalg.inv(Sigma)
        P = np.zeros((offs[-1], offs[-1]))
        r = np.zeros(offs[-1])
        for i in range(n):
            for j in range(n):
                P[offs[i]:offs[i + 1], offs[j]:offs[j + 1]] = Si[i, j] * XtX[np.ix_(sets[i], sets[j])]
            r[offs[i]:offs[i + 1]] = sum(Si[i, j] * XtY[sets[i], j] for j in range(n))
        L = np.linalg.cholesky(P)
        mean = np.linalg.solve(P, r)
        beta = mean + np.linalg.solve(L.T, rng.standard_normal(offs[-1]))
        B = np.zeros((k, n))
        for i in range(n):
            B[sets[i], i] = beta[offs[i]:offs[i + 1]]
        E = Ys - Xs @ B
        Sigma = inv_wishart(E.T @ E, T, rng)
        if it <= burn or (it - burn) % thin:
            continue
        if max_root(B, n, p) > MAX_ROOT:
            rejected += 1
            continue
        out_B.append(B.copy())
        out_S.append(Sigma.copy())
        kept += 1
    return {"B": np.array(out_B), "Sigma": np.array(out_S), "rejected": rejected, "Y": Y, "X": X}


def inv_wishart(S: np.ndarray, df: int, rng: np.random.Generator) -> np.ndarray:
    n = S.shape[0]
    C = np.linalg.cholesky(np.linalg.inv(S))
    Z = rng.standard_normal((df, n)) @ C.T
    return np.linalg.inv(Z.T @ Z)


def companion(B: np.ndarray, n: int, p: int) -> np.ndarray:
    A = np.zeros((n * p, n * p))
    A[:n] = B[:n * p].T
    A[n:, :-n] = np.eye(n * (p - 1))
    return A


def max_root(B: np.ndarray, n: int, p: int) -> float:
    return float(np.abs(np.linalg.eigvals(companion(B, n, p))).max())


def impact(Sigma: np.ndarray, order: list[int] | None = None) -> np.ndarray:
    """Recursive impact matrix; column j is the shock of variable j's equation. `order` is the
    recursive ordering (default: the order of VARIABLES)."""
    if order is None:
        return np.linalg.cholesky(Sigma)
    o = np.array(order)
    Pp = np.linalg.cholesky(Sigma[np.ix_(o, o)])
    P = np.zeros_like(Sigma)
    P[np.ix_(o, o)] = Pp
    return P


def irf(B: np.ndarray, Sigma: np.ndarray, n: int, p: int, H: int, order: list[int] | None = None) -> np.ndarray:
    """Responses [h, variable, shock] to one-s.d. recursive shocks."""
    A = companion(B, n, p)
    P = impact(Sigma, order)
    out = np.zeros((H + 1, n, n))
    Ah = np.eye(n * p)
    for h in range(H + 1):
        out[h] = Ah[:n, :n] @ P
        Ah = Ah @ A
    return out


def posterior_irfs(post: dict, n: int, p: int, H: int, order: list[int] | None = None) -> np.ndarray:
    return np.array([irf(B, S, n, p, H, order) for B, S in zip(post["B"], post["Sigma"])])


def scaled(irfs: np.ndarray, shock: int, var: int, size: float) -> np.ndarray:
    """[draw, h, variable] responses to a shock normalised to `size` on impact of `var`."""
    return irfs[:, :, :, shock] / irfs[:, 0, var, shock][:, None, None] * size


def fevd(irfs: np.ndarray) -> np.ndarray:
    """[draw, h, variable, shock] forecast-error-variance shares."""
    c = np.cumsum(irfs ** 2, axis=1)
    return c / c.sum(axis=3, keepdims=True)


def median_target(irfs: np.ndarray) -> int:
    med, sd = np.median(irfs, axis=0), irfs.std(axis=0) + 1e-12
    return int(np.argmin((((irfs - med) / sd) ** 2).sum(axis=(1, 2, 3))))


def historical_decomposition(B: np.ndarray, Sigma: np.ndarray, Y: np.ndarray, X: np.ndarray,
                             n: int, p: int) -> tuple[np.ndarray, np.ndarray]:
    """Contributions [t, variable, shock] of each structural shock and the baseline
    [t, variable] (constant + initial conditions); they sum to Y."""
    E = Y - X @ B
    P = np.linalg.cholesky(Sigma)
    U = np.linalg.solve(P, E.T).T
    T = Y.shape[0]
    Phi = irf(B, Sigma, n, p, T - 1)  # includes P
    contrib = np.zeros((T, n, n))
    for t in range(T):
        contrib[t] = np.einsum("hvs,hs->vs", Phi[:t + 1], U[t::-1])
    base = Y - contrib.sum(axis=2)
    return contrib, base


def forecast(post: dict, Ylev: np.ndarray, n: int, p: int, H: int, rng: np.random.Generator) -> np.ndarray:
    """Predictive paths [draw, h, variable] with shocks drawn from each Sigma."""
    out = np.zeros((len(post["B"]), H, n))
    for d, (B, S) in enumerate(zip(post["B"], post["Sigma"])):
        hist = list(Ylev[-p:])
        C = np.linalg.cholesky(S)
        for h in range(H):
            x = np.concatenate([hist[-j] for j in range(1, p + 1)] + [[1.0]])
            y = x @ B + C @ rng.standard_normal(n)
            hist.append(y)
            out[d, h] = y
    return out


# ---------------------------------------------------------------- run
def estimate(q: pd.DataFrame, start: str, rng: np.random.Generator, scales: list[float] = SCALES) -> dict:
    data = load_data(q, start)
    Ylev = data.values
    n = Ylev.shape[1]
    lam, mu, scale, grid = select_hyper(Ylev, LAGS, data.index, scales)
    post = gibbs(Ylev, LAGS, lam, mu, N_EXTERNAL, rng, weights=row_weights(data.index[LAGS:], scale))
    irfs = posterior_irfs(post, n, LAGS, HORIZON)
    return {"data": data, "lambda": lam, "mu": mu, "scale": scale, "grid": grid, "post": post, "irfs": irfs,
            "irfs_fx_last": posterior_irfs(post, n, LAGS, HORIZON, FX_LAST)}


def price_level(resp: np.ndarray) -> np.ndarray:
    """Cumulative price-level response, %, from quarterly SAAR inflation responses [draw, h]."""
    return np.cumsum(resp, axis=1) / 4


def summary_numbers(res: dict, key: str = "irfs") -> dict:
    irfs = res[key]
    oil = scaled(irfs, *SHOCKS["oil"])
    pol = scaled(irfs, *SHOCKS["policy"])
    fx = scaled(irfs, *SHOCKS["tenge"])
    q = lambda a: np.percentile(a, [16, 50, 84])  # noqa: E731
    return {
        "oil_gdp_4": q(oil[:, 4, GDP]), "oil_cpi_8": q(price_level(oil[:, :, INFL])[:, 8]),
        "oil_fx_1": q(oil[:, 1, FX]),
        "pol_cpi_8": q(price_level(pol[:, :, INFL])[:, 8]), "pol_gdp_4": q(pol[:, 4, GDP]),
        "pol_fx_1": q(pol[:, 1, FX]),
        "erpt_1": q(price_level(fx[:, :, INFL])[:, 1] / fx[:, 1, FX]),
        "erpt_4": q(price_level(fx[:, :, INFL])[:, 4] / fx[:, 4, FX]),
        "erpt_8": q(price_level(fx[:, :, INFL])[:, 8] / fx[:, 8, FX]),
        "fx_gdp_4": q(fx[:, 4, GDP]),
    }


def irf_table(res: dict) -> pd.DataFrame:
    rows = []
    for name, (s, v, size) in SHOCKS.items():
        r = scaled(res["irfs"], s, v, size)
        for vi, (col, label, _) in enumerate(VARIABLES):
            for h in range(HORIZON + 1):
                lo, med, hi = np.percentile(r[:, h, vi], [16, 50, 84])
                rows.append({"shock": name, "variable": col, "h": h, "p16": lo, "median": med, "p84": hi})
    return pd.DataFrame(rows)


def fevd_table(res: dict) -> pd.DataFrame:
    f = np.median(fevd(res["irfs"]), axis=0)
    rows = []
    for vi, (col, _, _) in enumerate(VARIABLES):
        for h in (0, 4, 8, 20):
            row = {"variable": col, "h": h}
            for g, idx in GROUPS.items():
                row[g] = f[h, vi, idx].sum() * 100
            rows.append(row)
    return pd.DataFrame(rows)


def hd_frame(res: dict) -> pd.DataFrame:
    post = res["post"]
    n = len(VARIABLES)
    d = median_target(res["irfs"])
    contrib, base = historical_decomposition(post["B"][d], post["Sigma"][d], post["Y"], post["X"], n, LAGS)
    idx = res["data"].index[LAGS:]
    rows = []
    for vi in (GDP, INFL):  # GDP: four-quarter log growth; CPI: mean of four SAAR rates ~ y/y
        col = VARIABLES[vi][0]
        if VARIABLES[vi][2] == "infl":
            diff = lambda a: pd.Series(a, index=idx).rolling(4).mean()  # noqa: E731
        else:
            diff = lambda a: pd.Series(a, index=idx).diff(4)  # noqa: E731
        frame = pd.DataFrame({"actual": diff(post["Y"][:, vi]), "baseline": diff(base[:, vi])})
        for g, sh in GROUPS.items():
            frame[g] = diff(contrib[:, vi, sh].sum(axis=1))
        frame["variable"] = col
        rows.append(frame.dropna())
    out = pd.concat(rows)
    out.index.name = "quarter"
    return out.reset_index()


# ---------------------------------------------------------------- charts
def chart_irfs(res: dict, path: Path) -> None:
    import matplotlib.pyplot as plt

    panels = [("oil", [GDP, INFL, RATE, FX], "Нефтяной шок: Brent +10 %"),
              ("policy", [GDP, INFL, FX], "Шок ДКП: TONIA +1 п.п."),
              ("tenge", [GDP, INFL, RATE], "Ослабление тенге: USD/KZT +10 %")]
    fig, axes = plt.subplots(3, 4, figsize=(12, 8.2), sharex=True)
    common.style(fig, *axes.ravel())
    h = np.arange(HORIZON + 1)
    for r, (name, vars_, head) in enumerate(panels):
        s, v, size = SHOCKS[name]
        resp = scaled(res["irfs"], s, v, size)
        for c in range(4):
            ax = axes[r, c]
            if c >= len(vars_):
                ax.axis("off")
                continue
            vi = vars_[c]
            lo, med, hi = np.percentile(resp[:, :, vi], [16, 50, 84], axis=0)
            ax.fill_between(h, lo, hi, color=common.SERIES[0], alpha=0.18, linewidth=0)
            ax.plot(h, med, color=common.SERIES[0], linewidth=2)
            common.zero_line(ax)
            unit = "%" if VARIABLES[vi][2] == "log" else "п.п."
            ax.set_title(f"{VARIABLES[vi][1]}, {unit}", loc="left", fontsize=9.5, color=common.INK)
            if c == 0:
                ax.text(0, 1.22, head, transform=ax.transAxes, fontsize=10.5, color=common.INK,
                        fontweight="bold")
            if r == 2:
                ax.set_xlabel("кварталы", color=common.INK_2, fontsize=8.5)
    fig.suptitle("BVAR: импульсные отклики (медиана и 68 % апостериорный интервал)", x=0.01, ha="left",
                 fontsize=12, color=common.INK, fontweight="bold", y=1.01)
    fig.tight_layout(h_pad=2.2)
    common.save(fig, path)


def chart_hd(hd: pd.DataFrame, variable: str, title: str, path: Path) -> None:
    import matplotlib.pyplot as plt  # noqa: F401

    d = hd[hd.variable == variable].set_index("quarter")
    fig, ax = common.figure(9, 4.6)
    x = np.arange(len(d))
    colors = common.SERIES + ["#eda100"]
    pos, neg = np.zeros(len(d)), np.zeros(len(d))
    for i, g in enumerate(GROUPS):
        v = d[g].values
        bottom = np.where(v >= 0, pos, neg)
        ax.bar(x, v, bottom=bottom, width=0.8, color=colors[i], label=g, edgecolor=common.SURFACE, linewidth=0.8)
        pos += np.where(v >= 0, v, 0)
        neg += np.where(v < 0, v, 0)
    ax.plot(x, (d.actual - d.baseline).values, color=common.INK, linewidth=1.6,
            label="Факт минус базовая траектория")
    common.zero_line(ax)
    ticks = [i for i, qq in enumerate(d.index) if str(qq).endswith("Q1")]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(d.index[i])[:4] for i in ticks])
    ax.set_ylabel("п.п.", color=common.INK_2, fontsize=9)
    common.title(ax, title, "Вклады шоков в отклонение от базовой траектории (константа и начальные условия), г/г, п.п.")
    common.legend(ax, loc="upper center", bbox_to_anchor=(0.5, -0.07), ncol=5, fontsize=8.5)
    common.save(fig, path)


# ---------------------------------------------------------------- report
def report(main: dict, robust: dict, flat: dict, fev: pd.DataFrame, fc: pd.DataFrame) -> str:
    s, x, r = summary_numbers(main), summary_numbers(main, "irfs_fx_last"), summary_numbers(robust)
    u = summary_numbers(flat)
    g = main["grid"]
    ml_best, ml_flat = g.log_ml.max(), g[g.scale == 1.0].log_ml.max()
    band = lambda a, nd=2: f"{a[1]:.{nd}f} [{a[0]:.{nd}f}; {a[2]:.{nd}f}]"  # noqa: E731
    d = main["data"]
    post = main["post"]
    fev_show = fev[fev.variable.isin(["gdp_sa", "cpi_sa", "tonia", "usdkzt"]) & fev.h.isin([4, 8, 20])].copy()
    fev_show["variable"] = fev_show.variable.map({c: label for c, label, _ in VARIABLES})
    for g in GROUPS:
        fev_show[g] = fev_show[g].map(lambda v: f"{v:.0f}")
    fev_show = fev_show.rename(columns={"variable": "Переменная", "h": "Горизонт, кв."})
    rows = [
        ("ВВП через 4 кв., % — нефть +10 %", "oil_gdp_4"),
        ("Уровень цен через 8 кв., % — нефть +10 %", "oil_cpi_8"),
        ("USD/KZT через 1 кв., % — нефть +10 %", "oil_fx_1"),
        ("ВВП через 4 кв., % — TONIA +1 п.п.", "pol_gdp_4"),
        ("Уровень цен через 8 кв., % — TONIA +1 п.п.", "pol_cpi_8"),
        ("USD/KZT через 1 кв., % — TONIA +1 п.п.", "pol_fx_1"),
        ("Перенос курса в цены за 1 кв.", "erpt_1"),
        ("Перенос курса в цены за 4 кв.", "erpt_4"),
        ("Перенос курса в цены за 8 кв.", "erpt_8"),
        ("ВВП через 4 кв., % — USD/KZT +10 %", "fx_gdp_4"),
    ]
    key = common.md_table(pd.DataFrame(
        [[label, band(s[k]), band(x[k]), band(u[k]), band(r[k])] for label, k in rows],
        columns=["Показатель", f"Базовая, {d.index[0]}–{d.index[-1]}", "Курс последним",
                 "Без масштаба (s = 1)", f"С {robust['data'].index[0]}"]))
    grid = main["grid"][main["grid"].scale == main["scale"]].pivot(index="lambda", columns="mu",
                                                                  values="log_ml").round(1)
    grid.columns = [f"μ={c:g}" for c in grid.columns]
    grid = grid.reset_index().rename(columns={"lambda": "λ"})
    return f"""# BVAR с внешним блоком

Производный результат, не официальная статистика. Скрипт: `scripts/models/bvar.py`;
числа: `irf.csv` (все отклики с интервалами), `fevd.csv`, `historical_decomposition.csv`,
`forecast.csv`, `hyperparameters.csv`.

## Спецификация

- Переменные (квартальные, `model_data/quarterly.csv`): внешний блок — 100·ln Brent, ставка ФРС,
  100·ln RUB/USD; внутренний — 100·ln ВВП (SA, БНС), инфляция кв/кв в годовом выражении
  (400·Δln ИПЦ SA), TONIA, 100·ln USD/KZT. Инфляция, а не уровень ИПЦ: в 2011–2026 гг. логарифм
  уровня цен ведёт себя почти как I(2), и VAR в уровнях давал 84 % взрывных выборок.
- Выборка: {d.index[0]}–{d.index[-1]} ({len(d)} кварталов; цепной ИПЦ начинается в 2011-01).
  Проверка устойчивости: с {robust['data'].index[0]} (инфляционное таргетирование, плавающий курс).
- VAR({LAGS}) в уровнях; приор Миннесоты через фиктивные наблюдения (Bańbura, Giannone &
  Reichlin 2010): случайное блуждание, общая жёсткость λ, затухание по лагам 1/l, приор суммы
  коэффициентов μ. λ и μ выбраны по максимуму предельного правдоподобия на сетке (как у
  Giannone, Lenza & Primiceri 2015): **λ = {main['lambda']:g}, μ = {main['mu']:g}**
  (устойчивость: λ = {robust['lambda']:g}, μ = {robust['mu']:g}).
- Кризисные кварталы ({", ".join(TURBULENT)}) входят с дисперсией шоков, умноженной на s²
  (Lenza & Primiceri 2022); s выбран вместе с λ и μ: **s = {main['scale']:g}**, выигрыш
  лог-правдоподобия против s = 1: {ml_best - ml_flat:.1f}. Без этого TONIA 2015–2016 гг. (15–37 %)
  делает ставку почти неперсистентной, и прогноз TONIA падает на 5 п.п. за квартал.
- Блочная экзогенность: лаги казахстанских переменных исключены из уравнений внешнего блока
  (малая открытая экономика). Апостериорное распределение — Гиббс (SUR), {len(post['B'])} сохранённых
  выборок; отброшено взрывных выборок: {post['rejected']}.
- Идентификация — рекурсивная в указанном порядке: внешний блок → ВВП → курс → инфляция →
  TONIA. Внешние шоки первыми; курс переносится в цены уже внутри квартала (высокая доля
  импорта в потреблении); ставка реагирует на всё в том же квартале (как в 2014–2015 и 2022 гг.),
  а шок ДКП — это движение TONIA сверх этой реакции. Проверка: порядок «… инфляция → TONIA →
  курс» (курс реагирует на всё, но в цены попадает лишь с лагом) — столбец «Курс последним».
  Интервалы — 16–84 перцентили.

## Ключевые отклики (медиана [16 %; 84 %])

{key}

Уровень цен — накопленный отклик инфляции (сумма кв/кв SAAR / 4). Перенос курса = отклик
уровня цен / отклик USD/KZT на шок курса на том же горизонте.

Главное (базовая спецификация):

- **Перенос курса** за 4 кв. — {s['erpt_4'][1]:.2f}, за 8 кв. — {s['erpt_8'][1]:.2f}. Без
  масштабирования кризисных кварталов он {u['erpt_4'][1] / s['erpt_4'][1]:.1f} раза выше: высокий
  перенос — свойство крупных девальваций 2014–2015 гг., а не «обычных» колебаний курса.
- **Шок ДКП** +1 п.п. TONIA: уровень цен через 8 кв. {s['pol_cpi_8'][1]:+.2f} %, ВВП через 4 кв.
  {s['pol_gdp_4'][1]:+.2f} %. Эффект на цены значим на уровне 68 %, но мал (вероятные причины —
  долларизация и льготное кредитование; модель их не проверяет).
- **Нефть** +10 %: ВВП через 4 кв. {s['oil_gdp_4'][1]:+.2f} %, уровень цен через 8 кв.
  {s['oil_cpi_8'][1]:+.2f} %, тенге укрепляется на {-s['oil_fx_1'][1]:.2f} % через квартал. Без
  масштабирования эффект нефти на курс и ВВП завышается — его «делают» 2014–2015 гг.

![Импульсные отклики](irf.png)

## Декомпозиция дисперсии ошибки прогноза, % (медиана)

{common.md_table(fev_show)}

«Прочие внутренние» — шоки уравнений ВВП и ИПЦ (спрос/предложение без разделения).

## Историческая декомпозиция

Вклады групп шоков в темп роста г/г (Fry–Pagan: выборка, ближайшая к медианным откликам,
чтобы вклады складывались точно).

![ИПЦ](hd_cpi.png)

![ВВП](hd_gdp.png)

## Безусловный прогноз (медиана [16 %; 84 %])

{common.md_table(fc)}

## Как читать и чего модель не умеет

1. Рекурсивная идентификация — предположение, а не факт: шок ДКП — это движение TONIA,
   не объяснённое внешним блоком, ВВП и ИПЦ текущего квартала. До 2015 г. TONIA отражает
   ликвидность при фиксированном курсе, а не решения по базовой ставке; поэтому отклики на
   шок ДКП в полной выборке смешивают два режима — сравнивайте со столбцом «с 2016Q1».
2. Шок курса включает всё, что двигает тенге помимо нефти, ФРС и рубля (в т. ч. ожидания и
   операции Нацфонда); перенос — средний по выборке, он зависит от режима и размера шока.
3. 60 кварталов на 7 переменных — это данные, в которых приор играет большую роль: λ выбран
   по данным, но отклики на горизонте > 8 кварталов опираются на приор случайного блуждания.
4. Рекурсивная схема даёт «курсовую загадку»: после повышения ставки тенге в медиане слабеет
   (68 % интервал включает ноль на первых кварталах), а TONIA на ударе снижается при
   ослаблении тенге. Типично для рекурсивной идентификации в малой открытой экономике
   (Kim & Roubini 2000); следующий шаг — знаковые ограничения.
5. Масштабирование кризисных кварталов — один общий множитель на заранее выбранный список
   кварталов; полноценная стохастическая волатильность — следующий шаг.
6. Выборка с 2016Q1 (41 квартал) даёт «ценовую загадку» (цены растут после повышения ставки)
   и положительный отклик ВВП на ослабление тенге — признак того, что данных мало для 7
   переменных; поэтому основной вариант — полная выборка с масштабированием кризисов.

## Предельное правдоподобие по сетке гиперпараметров

{common.md_table(grid)}
"""


def forecast_table(res: dict, rng: np.random.Generator, H: int = 6) -> pd.DataFrame:
    Ylev = res["data"].values
    paths = forecast(res["post"], Ylev, len(VARIABLES), LAGS, H, rng)
    last = res["data"].index[-1]
    hist = np.repeat(Ylev[None, -4:], paths.shape[0], axis=0)
    full = np.concatenate([hist, paths], axis=1)
    rows = []
    for h in range(H):
        qq = last + h + 1
        g = np.percentile(full[:, h + 4, GDP] - full[:, h, GDP], [16, 50, 84])
        c = np.percentile(full[:, h + 1:h + 5, INFL].mean(axis=1), [16, 50, 84])
        t = np.percentile(paths[:, h, RATE], [16, 50, 84])
        k = np.percentile(np.exp(paths[:, h, FX] / 100), [16, 50, 84])
        f = lambda a, nd=1: f"{a[1]:.{nd}f} [{a[0]:.{nd}f}; {a[2]:.{nd}f}]"  # noqa: E731
        rows.append({"Квартал": str(qq), "ВВП, г/г, % (лог.)": f(g), "ИПЦ, г/г, % (лог.)": f(c),
                     "TONIA, %": f(t), "USD/KZT": f(k, 0)})
    return pd.DataFrame(rows)


def main() -> None:
    rng = np.random.default_rng(SEED)
    q = common.load_quarterly()
    main_res = estimate(q, START, rng)
    robust = estimate(q, ROBUST_START, rng)
    flat = estimate(q, START, rng, scales=[1.0])
    OUT.mkdir(parents=True, exist_ok=True)
    irf_table(main_res).to_csv(OUT / "irf.csv", index=False, float_format="%.4f")
    fev = fevd_table(main_res)
    fev.to_csv(OUT / "fevd.csv", index=False, float_format="%.2f")
    hd = hd_frame(main_res)
    hd.to_csv(OUT / "historical_decomposition.csv", index=False, float_format="%.4f")
    grid = pd.concat([main_res["grid"].assign(sample=START), robust["grid"].assign(sample=ROBUST_START)])
    grid.to_csv(OUT / "hyperparameters.csv", index=False, float_format="%.3f")
    fc = forecast_table(main_res, rng)
    fc.to_csv(OUT / "forecast.csv", index=False)
    chart_irfs(main_res, OUT / "irf.png")
    chart_hd(hd, "cpi_sa", "Инфляция: что её двигало", OUT / "hd_cpi.png")
    chart_hd(hd, "gdp_sa", "Рост ВВП: что его двигало", OUT / "hd_gdp.png")
    (OUT / "REPORT.md").write_text(report(main_res, robust, flat, fev, fc), encoding="utf-8")
    for k, v in summary_numbers(main_res).items():
        print(f"{k:10s} {v.round(3)}")
    print("lambda", main_res["lambda"], "mu", main_res["mu"], "scale", main_res["scale"],
          "rejected", main_res["post"]["rejected"])
    print("robust lambda", robust["lambda"], "mu", robust["mu"], "scale", robust["scale"])


if __name__ == "__main__":
    main()
