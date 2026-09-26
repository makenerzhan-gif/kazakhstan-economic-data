"""Natural rate of interest (r*) and the output gap for Kazakhstan.

    python scripts/models/rstar.py          # writes models/rstar/

Semi-structural model in the spirit of Holston, Laubach & Williams (2017, 2023), quarterly,
estimated at the posterior mode (Kalman-filter likelihood + normal priors, PRIORS):

  IS:        gap_t = a1 gap_{t-1} + a2 gap_{t-2} + a_r/2 sum_{j=1,2} (r_{t-j} - r*_{t-j})
                     + a_o oil_{t-1} + e_gap
  Phillips:  pi_t  = b_pi pi_{t-1} + (1 - b_pi) mean(pi_{t-2..t-4}) + b_y gap_{t-1}
                     + b_e de_{t-1} + e_pi
  potential: y*_t = y*_{t-1} + g_{t-1} / 4 + e_y*      g_t = g_{t-1} + e_g
  r*_t = g_t + z_t,                                  z_t = z_{t-1} + e_z

  y   = 100 ln real GDP (BNS SA), gap = y - y*, g = trend growth, % a year
  pi  = CPI inflation, q/q SAAR;  r = TONIA - mean(pi_t..pi_{t-3}) (HLW's backward proxy)
  oil = 100 (ln Brent_t - ln Brent_{t-4}); de = 400 dln USD/KZT (depreciation, SAAR)

Kazakhstan-specific choices:
- the oil term: the business cycle here is partly the oil-price cycle;
- the exchange-rate term in the Phillips curve: pass-through is a first-order driver of
  inflation (2014-2016, 2022);
- the turbulent quarters (the same list as the BVAR: 2014 and 2015 devaluations, the 2015-16
  liquidity squeeze with TONIA up to 37 %, the 2020 lockdown) get their IS and Phillips
  shock s.d. multiplied by kappa, estimated -- the Lenza & Primiceri (2022) idea in a state
  space.

Why priors: by maximum likelihood the gap has almost no persistence (a1 + a2 ~ 0.13) and the
real rate almost no effect (a_r ~ -0.05), so r* is not identified and sits at its initial
value; the posterior mode costs under 3 log-likelihood points. The report shows both.

The signal-to-noise ratios are not estimated. With 57 quarters, maximum likelihood drives
the trend-growth and z variances to zero (the pile-up problem HLW solve with Stock-Watson
median-unbiased estimators, which need far longer samples). They are set to HLW-like values,
lambda_g = sigma_g / (4 sigma_y*) = 0.06 and lambda_z = |a_r| sigma_z / sigma_gap = 0.04, and
the report shows how r* moves over a grid of both.

Cross-checks on the gap: a production-function gap (the Solow residual and employment
against their HP trends, alpha from model_data) and an HP filter on GDP. Cross-checks on r*:
the HP trend of the ex-ante real rate, and an interest-parity floor -- the US real 10-year
rate (HP trend) plus the sovereign Eurobond spread.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from statsmodels.tsa.filters.hp_filter import hpfilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from bvar import TURBULENT  # noqa: E402

OUT = common.MODELS / "rstar"
START = "2012Q1"  # first quarter with a real rate and two lags of the gap
LAMBDA_G, LAMBDA_Z = 0.06, 0.04
GRID_G = [0.03, 0.06, 0.12]
GRID_Z = [0.02, 0.04, 0.08]
HP_LAMBDA = 1600
PARAMS = ["a1", "a2", "a_r", "a_o", "b_pi", "b_y", "b_e", "ln_s_gap", "ln_s_pi", "ln_s_ystar", "ln_kappa"]
BOUNDS = {
    "a1": (0.0, 1.6), "a2": (-0.9, 0.6), "a_r": (-1.0, -0.0025), "a_o": (-0.2, 0.2),
    "b_pi": (0.0, 1.0), "b_y": (0.025, 2.0), "b_e": (0.0, 0.5),
    "ln_s_gap": (np.log(0.05), np.log(5)), "ln_s_pi": (np.log(0.2), np.log(20)),
    "ln_s_ystar": (np.log(0.05), np.log(5)), "ln_kappa": (0.0, np.log(10)),
}
X0 = {"a1": 0.8, "a2": -0.1, "a_r": -0.05, "a_o": 0.01, "b_pi": 0.6, "b_y": 0.2, "b_e": 0.05,
      "ln_s_gap": np.log(0.8), "ln_s_pi": np.log(3.0), "ln_s_ystar": np.log(0.6), "ln_kappa": np.log(3)}
# Priors (normal; on logs for the s.d.s), in the spirit of the QPM-type models emerging-market
# central banks estimate: a persistent gap (a1 + a2 ~ 0.8), a real-rate effect of -0.1 a
# quarter (a year of r 1 pp above r* costs ~0.5 % of output once persistence plays out), a
# Phillips slope of 0.3 on annualised inflation, potential shocks smaller than gap shocks.
PRIORS = {
    "a1": (0.8, 0.2), "a2": (0.0, 0.15), "a_r": (-0.10, 0.05), "a_o": (0.01, 0.02),
    "b_pi": (0.6, 0.2), "b_y": (0.3, 0.15), "b_e": (0.05, 0.05),
    "ln_s_gap": (np.log(0.8), 0.5), "ln_s_pi": (np.log(3.0), 0.5), "ln_s_ystar": (np.log(0.3), 0.5),
    "ln_kappa": (np.log(3.0), 0.5),
}
NSTATE = 9  # y*_t, y*_{t-1}, y*_{t-2}, g_t, g_{t-1}, g_{t-2}, z_t, z_{t-1}, z_{t-2}


# ---------------------------------------------------------------- data
def build_data(q: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=q.index)
    d["y"] = 100 * np.log(q.gdp_sa)
    d["pi"] = 400 * np.log(q.cpi_sa).diff()
    d["pi_e"] = d.pi.rolling(4).mean()
    d["r"] = q.tonia - d.pi_e
    d["pi_lag_avg"] = d.pi.shift(2).rolling(3).mean()  # mean(pi_{t-2..t-4})
    d["oil"] = 100 * (np.log(q.brent) - np.log(q.brent).shift(4))
    d["de"] = 400 * np.log(q.usdkzt).diff()
    d["tonia"] = q.tonia
    d["infl_expect"] = q.infl_expect
    d["turbulent"] = [str(t) in TURBULENT for t in d.index]
    return d


def sample(d: pd.DataFrame, start: str = START) -> pd.DataFrame:
    s = d.loc[start:].copy()
    s["y_l1"], s["y_l2"] = d.y.shift(1), d.y.shift(2)
    s["r_l1"], s["r_l2"] = d.r.shift(1), d.r.shift(2)
    s["pi_l1"] = d.pi.shift(1)
    s["oil_l1"], s["de_l1"] = d.oil.shift(1), d.de.shift(1)
    s = s.dropna(subset=["y", "pi", "y_l1", "y_l2", "r_l1", "r_l2", "pi_l1", "pi_lag_avg", "oil_l1", "de_l1"])
    idx = s.index
    if len(idx) != (idx[-1] - idx[0]).n + 1:
        raise SystemExit("rstar: the sample has internal gaps")
    return s


# ---------------------------------------------------------------- state space
def unpack(theta: np.ndarray) -> dict:
    return dict(zip(PARAMS, theta))


def system(p: dict, lam_g: float, lam_z: float):
    s_gap, s_pi, s_ys = np.exp(p["ln_s_gap"]), np.exp(p["ln_s_pi"]), np.exp(p["ln_s_ystar"])
    s_g = lam_g * 4 * s_ys
    s_z = lam_z * s_gap / abs(p["a_r"])
    F = np.zeros((NSTATE, NSTATE))
    F[0, 0], F[0, 3] = 1.0, 0.25  # y*_t = y*_{t-1} + g_{t-1}/4; g_{t-1} is slot 3 of xi_{t-1}
    F[1, 0], F[2, 1] = 1.0, 1.0
    F[3, 3], F[4, 3], F[5, 4] = 1.0, 1.0, 1.0
    F[6, 6], F[7, 6], F[8, 7] = 1.0, 1.0, 1.0
    Q = np.zeros((NSTATE, NSTATE))
    Q[0, 0], Q[3, 3], Q[6, 6] = s_ys ** 2, s_g ** 2, s_z ** 2
    H = np.zeros((2, NSTATE))
    ar = p["a_r"] / 2
    H[0, [0, 1, 2]] = [1.0, -p["a1"], -p["a2"]]
    H[0, [4, 5, 7, 8]] = -ar
    H[1, 1] = -p["b_y"]
    return F, Q, H, s_gap, s_pi


def exog(p: dict, s: pd.DataFrame) -> np.ndarray:
    ar = p["a_r"] / 2
    m_y = p["a1"] * s.y_l1 + p["a2"] * s.y_l2 + ar * (s.r_l1 + s.r_l2) + p["a_o"] * s.oil_l1
    m_pi = p["b_pi"] * s.pi_l1 + (1 - p["b_pi"]) * s.pi_lag_avg + p["b_y"] * s.y_l1 + p["b_e"] * s.de_l1
    return np.column_stack([m_y, m_pi])


def initial_state(s: pd.DataFrame, d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """y* lags from an HP trend of the pre-sample GDP, g from its slope, z from the mean real
    rate less g; loose variances so the first years are data-driven."""
    y = d.y.dropna()
    trend = pd.Series(hpfilter(y, lamb=HP_LAMBDA)[1], index=y.index)
    t0 = s.index[0]
    ys = [trend[t0 - 1], trend[t0 - 2], trend[t0 - 3]]
    g0 = trend[t0 - 1] - trend[t0 - 5]  # % a year
    z0 = float(s.r.mean()) - g0  # centred on the sample's mean real rate, loosely
    x0 = np.array([ys[0], ys[1], ys[2], g0, g0, g0, z0, z0, z0])
    P0 = np.diag([1.0, 1.0, 1.0, 4.0, 4.0, 4.0, 16.0, 16.0, 16.0])
    return x0, P0


def kalman(p: dict, s: pd.DataFrame, x0: np.ndarray, P0: np.ndarray, lam_g: float, lam_z: float,
           smooth: bool = False) -> dict:
    F, Q, H, s_gap, s_pi = system(p, lam_g, lam_z)
    Y = s[["y", "pi"]].values
    A = exog(p, s)
    kappa = np.exp(p["ln_kappa"])
    T = len(Y)
    xp, Pp, xf, Pf = np.zeros((T, NSTATE)), np.zeros((T, NSTATE, NSTATE)), np.zeros((T, NSTATE)), \
        np.zeros((T, NSTATE, NSTATE))
    x, P, ll = x0, P0, 0.0
    for t in range(T):
        x = F @ x
        P = F @ P @ F.T + Q
        xp[t], Pp[t] = x, P
        k = kappa if s.turbulent.iloc[t] else 1.0
        R = np.diag([(k * s_gap) ** 2, (k * s_pi) ** 2])
        v = Y[t] - A[t] - H @ x
        S = H @ P @ H.T + R
        Si = np.linalg.inv(S)
        K = P @ H.T @ Si
        x = x + K @ v
        P = (np.eye(NSTATE) - K @ H) @ P
        P = (P + P.T) / 2
        xf[t], Pf[t] = x, P
        ll += -0.5 * (2 * np.log(2 * np.pi) + np.linalg.slogdet(S)[1] + v @ Si @ v)
    out = {"ll": ll, "xf": xf, "Pf": Pf}
    if smooth:
        xs, Ps = xf.copy(), Pf.copy()
        for t in range(T - 2, -1, -1):
            J = Pf[t] @ F.T @ np.linalg.pinv(Pp[t + 1])
            xs[t] = xf[t] + J @ (xs[t + 1] - xp[t + 1])
            Ps[t] = Pf[t] + J @ (Ps[t + 1] - Pp[t + 1]) @ J.T
        out.update(xs=xs, Ps=Ps)
    return out


def log_prior(p: dict) -> float:
    return float(sum(-0.5 * ((p[k] - m) / sd) ** 2 for k, (m, sd) in PRIORS.items()))


def fit(s: pd.DataFrame, d: pd.DataFrame, lam_g: float = LAMBDA_G, lam_z: float = LAMBDA_Z,
        start: dict | None = None, restarts: tuple = (0.0, 0.1, -0.1), use_prior: bool = True) -> dict:
    """Posterior mode: Kalman log likelihood + log prior (maximum likelihood if not use_prior)."""
    x0, P0 = initial_state(s, d)
    theta0 = np.array([(start or X0)[k] for k in PARAMS])
    bounds = [BOUNDS[k] for k in PARAMS]

    def nll(theta):
        p = unpack(theta)
        if p["a1"] + p["a2"] >= 0.98:  # stationary gap
            return 1e10
        try:
            return -kalman(p, s, x0, P0, lam_g, lam_z)["ll"] - (log_prior(p) if use_prior else 0.0)
        except np.linalg.LinAlgError:
            return 1e10

    best = None
    for jitter in restarts:
        th = np.clip(theta0 * (1 + jitter), [b[0] for b in bounds], [b[1] for b in bounds])
        r = minimize(nll, th, method="L-BFGS-B", bounds=bounds, options={"maxiter": 3000})
        if best is None or r.fun < best.fun:
            best = r
    p = unpack(best.x)
    kf = kalman(p, s, x0, P0, lam_g, lam_z, smooth=True)
    return {"params": p, "ll": kf["ll"], "lpost": -best.fun, "kf": kf, "lam_g": lam_g, "lam_z": lam_z, "converged": bool(best.success)}


def states(res: dict, s: pd.DataFrame) -> pd.DataFrame:
    kf = res["kf"]
    out = pd.DataFrame(index=s.index)
    for kind in ("f", "s"):
        x, P = kf["x" + kind], kf["P" + kind]
        rstar = x[:, 3] + x[:, 6]
        rstar_sd = np.sqrt(P[:, 3, 3] + P[:, 6, 6] + 2 * P[:, 3, 6])
        tag = "filtered" if kind == "f" else "smoothed"
        out[f"ystar_{tag}"] = x[:, 0]
        out[f"gap_{tag}"] = s.y.values - x[:, 0]
        out[f"gap_sd_{tag}"] = np.sqrt(P[:, 0, 0])
        out[f"g_{tag}"] = x[:, 3]
        out[f"z_{tag}"] = x[:, 6]
        out[f"rstar_{tag}"] = rstar
        out[f"rstar_sd_{tag}"] = rstar_sd
    out["r"] = s.r
    out["tonia"] = s.tonia
    out["pi_e"] = s.pi_e
    return out


# ---------------------------------------------------------------- cross-checks
def pf_gap(q: pd.DataFrame, index: pd.PeriodIndex) -> pd.Series:
    """(tfp - trend tfp) + (1 - alpha)(ln L - trend ln L), in % of potential."""
    alpha = 1 - float(q.labour_share.mean())
    tfp = q.tfp_log.dropna()
    lnl = 100 * np.log(q.employment_sa.dropna())
    common_idx = tfp.index.intersection(lnl.index)
    tfp, lnl = tfp[common_idx], lnl[common_idx]
    tfp_c = hpfilter(tfp, lamb=HP_LAMBDA)[0]
    l_c = hpfilter(lnl, lamb=HP_LAMBDA)[0]
    return (tfp_c + (1 - alpha) * l_c).reindex(index)


def hp_gap(q: pd.DataFrame, index: pd.PeriodIndex) -> pd.Series:
    y = 100 * np.log(q.gdp_sa.dropna())
    return hpfilter(y, lamb=HP_LAMBDA)[0].reindex(index)


def parity_floor(q: pd.DataFrame, m: pd.DataFrame, index: pd.PeriodIndex) -> pd.DataFrame:
    """US real 10-year rate (HP trend of UST10 less US CPI y/y) + the Eurobond spread."""
    us = (m.ust_10y - m.us_cpi_yoy).dropna()
    usq = us.groupby(us.index.asfreq("Q")).mean()
    us_trend = hpfilter(usq, lamb=HP_LAMBDA)[1]
    spread = q.eurobond_spread / 100
    out = pd.DataFrame({"us_real_trend": us_trend, "eurobond_spread_pp": spread})
    out["parity_floor"] = out.us_real_trend + out.eurobond_spread_pp
    return out.reindex(index)


# ---------------------------------------------------------------- outputs
def chart_rstar(st: pd.DataFrame, extra: pd.DataFrame, path: Path) -> None:
    fig, ax = common.figure(9, 4.6)
    x = st.index.to_timestamp()
    lo = st.rstar_smoothed - st.rstar_sd_smoothed
    hi = st.rstar_smoothed + st.rstar_sd_smoothed
    ax.fill_between(x, lo, hi, color=common.SERIES[0], alpha=0.16, linewidth=0)
    ax.plot(x, st.rstar_smoothed, color=common.SERIES[0], linewidth=2.2, label="r* (сглаженная, ±1 s.d.)")
    ax.plot(x, st.r, color=common.SERIES[1], linewidth=1.6, label="Реальная ставка: TONIA − инфляция г/г")
    ax.plot(x, extra.parity_floor, color=common.SERIES[2], linewidth=1.6,
            label="Паритет: реальная UST10 (тренд) + спред еврооблигаций")
    common.zero_line(ax)
    lim = np.nanpercentile(np.r_[st.r.values, hi.values, lo.values], [1, 99])
    ylo, yhi = min(lim[0], -12) - 1, max(lim[1], 12) + 1
    ax.set_ylim(ylo, yhi)
    for t, v in st.r[(st.r > yhi) | (st.r < ylo)].items():  # clipped spikes, labelled
        ax.annotate(f"{t}: {v:.0f} %", (t.to_timestamp(), yhi if v > yhi else ylo), xytext=(6, -10),
                    textcoords="offset points", fontsize=8, color=common.INK_2)
    ax.set_ylabel("%", color=common.INK_2, fontsize=9)
    common.title(ax, "Нейтральная реальная ставка r* и фактическая реальная ставка",
                 "HLW-подобная модель, 2012–2026; ставка выше r* — ДКП жёсткая")
    common.legend(ax, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=8.5)
    common.save(fig, path)


def chart_gaps(gaps: pd.DataFrame, path: Path) -> None:
    fig, ax = common.figure(9, 4.4)
    x = gaps.index.to_timestamp()
    for i, (col, label) in enumerate([("gap_hlw", "Полуструктурная модель (HLW)"),
                                      ("gap_pf", "Производственная функция"),
                                      ("gap_hp", "HP-фильтр ВВП")]):
        ax.plot(x, gaps[col], color=common.SERIES[i], linewidth=2 if i == 0 else 1.6, label=label)
    common.zero_line(ax)
    ax.set_ylabel("% от потенциала", color=common.INK_2, fontsize=9)
    common.title(ax, "Разрыв выпуска: три оценки", "100·(ln Y − ln Y*); сглаженные оценки")
    common.legend(ax, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, fontsize=8.5)
    common.save(fig, path)


def report(res: dict, mle: dict, st: pd.DataFrame, gaps: pd.DataFrame, extra: pd.DataFrame,
           sens: pd.DataFrame, s: pd.DataFrame) -> str:
    p, pm = res["params"], mle["params"]
    last = st.index[-1]
    names = {"a1": "a1 (инерция разрыва)", "a2": "a2", "a_r": "a_r (r − r* → разрыв)",
             "a_o": "a_o (нефть → разрыв)", "b_pi": "b_π (вес π_(t−1))", "b_y": "b_y (разрыв → π)",
             "b_e": "b_e (Δкурс → π)", "ln_s_gap": "σ шока разрыва", "ln_s_pi": "σ шока инфляции",
             "ln_s_ystar": "σ шока потенциала", "ln_kappa": "κ (множитель σ в кризис)"}

    def show(k, v):
        return f"{np.exp(v):.2f}" if k.startswith("ln_") else f"{v:.3f}"

    def prior(k):
        m, sd = PRIORS[k]
        return f"{np.exp(m):.2f} (±{sd:g} в лог.)" if k.startswith("ln_") else f"{m:g} ± {sd:g}"

    par = pd.DataFrame([[names[k], prior(k), show(k, p[k]), show(k, pm[k])] for k in PARAMS],
                       columns=["Параметр", "Приор: среднее ± s.d.", "Мода апостериорного", "ММП без приоров"])
    x_m = mle["kf"]["xs"][-1]
    z_m = mle["kf"]["xs"][:, 6]
    z_p = res["kf"]["xs"][:, 6]
    from scipy.stats import norm
    r_trend = hpfilter(s.r, lamb=HP_LAMBDA)[1]
    yearly = st.groupby(st.index.year).agg(
        r=("r", "mean"), rstar=("rstar_smoothed", "mean"), rstar_f=("rstar_filtered", "mean"),
        g=("g_smoothed", "mean"), z=("z_smoothed", "mean"))
    yearly = yearly.join(gaps.groupby(gaps.index.year).mean()).join(
        extra.groupby(extra.index.year).parity_floor.mean())
    ytab = pd.DataFrame({
        "Год": yearly.index,
        "Реальная ставка": yearly.r.map(lambda v: common.fmt(v, 1)),
        "r* (сглаж.)": yearly.rstar.map(lambda v: common.fmt(v, 1)),
        "r* (фильтр)": yearly.rstar_f.map(lambda v: common.fmt(v, 1)),
        "Тренд роста g": yearly.g.map(lambda v: common.fmt(v, 1)),
        "z": yearly.z.map(lambda v: common.fmt(v, 1)),
        "Паритет": yearly.parity_floor.map(lambda v: common.fmt(v, 1)),
        "Разрыв HLW": yearly.gap_hlw.map(lambda v: common.fmt(v, 1)),
        "Разрыв ПФ": yearly.gap_pf.map(lambda v: common.fmt(v, 1)),
        "Разрыв HP": yearly.gap_hp.map(lambda v: common.fmt(v, 1)),
    })
    corr = gaps.corr().round(2)
    sens_tab = sens.pivot(index="lambda_g", columns="lambda_z", values="rstar_last").round(1)
    sens_tab.columns = [f"λ_z={c:g}" for c in sens_tab.columns]
    sens_tab = sens_tab.reset_index().rename(columns={"lambda_g": "λ_g"})
    ll_tab = sens.pivot(index="lambda_g", columns="lambda_z", values="ll").round(1)
    ll_tab.columns = [f"λ_z={c:g}" for c in ll_tab.columns]
    ll_tab = ll_tab.reset_index().rename(columns={"lambda_g": "λ_g"})
    cur = st.loc[last]
    stance = cur.r - cur.rstar_smoothed
    survey = st.tonia - s.infl_expect
    return f"""# r* и разрыв выпуска

Производный результат, не официальная статистика. Скрипт: `scripts/models/rstar.py`;
ряды: `states.csv` (r*, g, z, потенциал, разрывы с s.d., фильтр и сглаживание), `gaps.csv`,
`parameters.csv`, `sensitivity.csv`.

## Модель

Полуструктурная модель в духе Holston, Laubach & Williams (2017, 2023), квартальная,
{s.index[0]}–{s.index[-1]} ({len(s)} кварталов); фильтр Калмана, оценка — мода апостериорного
распределения (правдоподобие + нормальные приоры):

- IS: разрыв_t = a1·разрыв_(t−1) + a2·разрыв_(t−2) + a_r/2·Σ(r − r*)_(t−1,t−2) + a_o·нефть_(t−1) + ε
- Филлипс: π_t = b_π·π_(t−1) + (1 − b_π)·ср.(π_(t−2..t−4)) + b_y·разрыв_(t−1) + b_e·Δкурс_(t−1) + ε
- Потенциал: y*_t = y*_(t−1) + g_(t−1)/4 + ε; g и z — случайные блуждания; **r* = g + z**.
- y — 100·ln ВВП (SA), π — инфляция кв/кв SAAR, r = TONIA − инфляция за 4 кв. (ожидания по
  прошлой инфляции, как у HLW), нефть — изменение Brent за 4 кв., Δкурс — ослабление тенге SAAR.
- Особенности Казахстана: нефтяной член в IS, курсовой член в кривой Филлипса, и кризисные
  кварталы ({", ".join(TURBULENT)}) с σ шоков, умноженной на κ (оценивается).
- λ_g и λ_z (отношения сигнал/шум для тренда роста и z) откалиброваны, а не оценены: на 57
  кварталах ММП «прижимает» их дисперсии к нулю (pile-up; HLW решают это медианно-несмещёнными
  оценками Stock–Watson, которым нужна гораздо более длинная выборка). Чувствительность — ниже.

## Оценки

{common.md_table(par)}

λ_g = {res['lam_g']:g}, λ_z = {res['lam_z']:g} (калибровка). Лог-правдоподобие: {res['ll']:.1f} в моде
апостериорного против {mle['ll']:.1f} в ММП без приоров. Данные почти не различают варианты
(разница {mle['ll'] - res['ll']:.1f}), но ММП даёт вырожденную модель: инерция разрыва
a1 + a2 = {pm['a1'] + pm['a2']:.2f}, влияние ставки a_r = {pm['a_r']:.3f}. При таком a_r r* не
идентифицирована: z за всю выборку меняется лишь от {z_m.min():.2f} до {z_m.max():.2f} при начальном
значении {res['kf']['xs'][0, 6]:.2f} (ММП: r* на {last} = {x_m[3] + x_m[6]:.1f} %).
Поэтому оценка — мода апостериорного распределения с приорами, как в QPM-моделях ЦБ
развивающихся стран; приор и результат стоят рядом, чтобы было видно, что сдвинули данные.

## Итог на {last}

- **r* = {cur.rstar_smoothed:.1f} %** (сглаженная); фильтрованная (только прошлые данные) —
  {cur.rstar_filtered:.1f} %. ±1 s.d. = {cur.rstar_sd_smoothed:.1f} п.п. (только неопределённость
  состояния): данные почти не информативны об **уровне** r*.
- Уровень r* в модели задаёт в основном средняя реальная ставка за выборку
  ({s.r.mean():.1f} %): z в моде апостериорного меняется лишь от {z_p.min():.1f} до {z_p.max():.1f} п.п.
  **Динамику** r* даёт тренд роста g. Сверка: HP-тренд самой реальной ставки на {last} —
  {r_trend.iloc[-1]:.1f} %.
- Реальная ставка (TONIA − инфляция за 4 кв.) = {cur.r:.1f} %, т. е. **{stance:+.1f} п.п. к r***:
  {"ДКП жёстче нейтральной" if stance > 0 else "ДКП мягче нейтральной"}; вероятность того, что
  ставка выше r* (по распределению состояния), — {norm.cdf(stance / cur.rstar_sd_smoothed) * 100:.0f} %.
- С опросными ожиданиями НБК (TONIA − ожидаемая инфляция) реальная ставка {common.fmt(survey.iloc[-1], 1)} %.
- Тренд роста g = {cur.g_smoothed:.1f} %, z = {cur.z_smoothed:.1f} п.п. (всё, что сдвигает r* помимо
  роста: премия за риск, глобальная ставка, спрос на тенговые активы).
- Разрыв выпуска: HLW {gaps.gap_hlw.iloc[-1]:+.1f} %, производственная функция {common.fmt(gaps.gap_pf.dropna().iloc[-1], 1)} %,
  HP {common.fmt(gaps.gap_hp.dropna().iloc[-1], 1)} %.

![r*](rstar.png)

![Разрыв выпуска](output_gap.png)

## По годам (средние за год, %)

{common.md_table(ytab)}

Корреляции трёх разрывов:

{common.md_table(corr.reset_index().rename(columns={'index': ''}))}

## Чувствительность r* на {last} к λ_g и λ_z

{common.md_table(sens_tab)}

Лог-правдоподобие по той же сетке (оно почти плоское — данные сами λ не выбирают):

{common.md_table(ll_tab)}

## Как читать и ограничения

1. r* здесь — «нейтральная» реальная ставка денежного рынка: уровень TONIA минус ожидаемая
   инфляция, при котором разрыв выпуска закрывается, а инфляция стабильна. Неопределённость
   велика: ±1 s.d. — только неопределённость состояния; с параметрической она шире.
2. Реальная ставка через прошлую инфляцию завышает жёсткость на выходе из инфляционных
   всплесков (2016, 2023): прошлая инфляция выше ожидаемой. Опросные ожидания НБК есть с 2016 г.
3. Паритетная линия (реальная доходность UST10 + спред суверенных еврооблигаций) — нижняя
   граница для тенговой r*: к ней надо добавить валютную премию (средний избыточный доход
   carry-trade в тенге за 2016–2026 гг. ~7 % годовых, `model_data` `carry_excess`, s.e. ~3).
4. Разрыв по производственной функции опирается на ряд капитала (PIM) и TFP как остаток,
   тренды — HP с проблемой конца выборки; HP-разрыв ВВП — чисто статистический ориентир.
5. Выборка короткая (с 2012 г.) и включает смену режима (2015: переход к таргетированию
   инфляции и плавающему курсу) — модель это не моделирует явно, кроме κ для кризисных кварталов.
"""


def main() -> None:
    q = common.load_quarterly()
    m = common.load_monthly()
    d = build_data(q)
    s = sample(d)
    res = fit(s, d)
    mle = fit(s, d, restarts=(0.0,), use_prior=False)
    st = states(res, s)
    gaps = pd.DataFrame({"gap_hlw": st.gap_smoothed, "gap_pf": pf_gap(q, s.index), "gap_hp": hp_gap(q, s.index)})
    extra = parity_floor(q, m, s.index)
    sens = []
    for lg in GRID_G:
        for lz in GRID_Z:
            r = res if (lg, lz) == (LAMBDA_G, LAMBDA_Z) else fit(s, d, lg, lz, start=res["params"], restarts=(0.0,))
            x = r["kf"]["xs"][-1]
            sens.append({"lambda_g": lg, "lambda_z": lz, "rstar_last": x[3] + x[6], "ll": r["ll"],
                         "gap_last": s.y.iloc[-1] - x[0]})
    sens = pd.DataFrame(sens)
    OUT.mkdir(parents=True, exist_ok=True)
    st.join(extra).to_csv(OUT / "states.csv", index_label="quarter", float_format="%.4f")
    gaps.to_csv(OUT / "gaps.csv", index_label="quarter", float_format="%.4f")
    pd.Series(res["params"]).to_csv(OUT / "parameters.csv", header=["value"], index_label="parameter",
                                    float_format="%.5f")
    sens.to_csv(OUT / "sensitivity.csv", index=False, float_format="%.4f")
    chart_rstar(st, extra, OUT / "rstar.png")
    chart_gaps(gaps, OUT / "output_gap.png")
    (OUT / "REPORT.md").write_text(report(res, mle, st, gaps, extra, sens, s), encoding="utf-8")
    print({k: round(float(v), 4) for k, v in res["params"].items()}, "ll", round(res["ll"], 2),
          "converged", res["converged"])
    print(st[["r", "rstar_smoothed", "rstar_filtered", "g_smoothed", "z_smoothed", "gap_smoothed"]]
          .iloc[::4].round(2).to_string())
    print(sens.round(2).to_string())


if __name__ == "__main__":
    main()
