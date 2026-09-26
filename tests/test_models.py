"""Model scripts (scripts/models/): gravity PPML, BVAR, r*. Synthetic data only -- each test
checks a property the estimator must have, not the numbers of the current vintage."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "models"))
import bvar  # noqa: E402
import gravity  # noqa: E402
import rstar  # noqa: E402


# ---------------------------------------------------------------- gravity
def _dims(rows):
    return pd.DataFrame(rows, columns=["date", "region", "variable", "item_code", "value"])


def _geo(iso):
    return pd.DataFrame({"iso3": iso, "contig": [1, 0, 0], "comlang_off": [1, 0, 0],
                         "distw": [2000.0, 5000.0, 9000.0]})


def _cepii(iso):
    rows = []
    for y in range(2000, 2022):
        for c, d in zip(iso, [1900.0, 4800.0, 8800.0]):
            rows.append({"year": y, "iso3": c, "distw_harmonic": d, "fta_wto": 1.0 if c == "RUS" else 0.0,
                         "wto_d": 1.0, "eu_d": 1.0 if c == "DEU" else 0.0})
    return pd.DataFrame(rows)


def test_gravity_panel_splices_wits_then_bns_and_keeps_zeros():
    iso = ["RUS", "DEU", "CHL"]
    rows = []
    for y in (2018, 2019, 2020, 2021):
        for c in iso:
            rows.append([f"{y}-12-31", "world", "WDI_GDP_USD", c, 1e12])
        rows.append([f"{y}-12-31", "national", "WITS_KZ_EXPORTS_BY_PARTNER", "RUS", 1000.0])  # thousand USD
        rows.append([f"{y}-12-31", "national", "KZ_EXPORTS_BY_PARTNER", "RUS", 5000.0])
        rows.append([f"{y}-12-31", "national", "WITS_KZ_EXPORTS_BY_PARTNER", "DEU", 700.0])
    panel = gravity.build_panel(_dims(rows), _cepii(iso), _geo(iso)).set_index(["iso3", "year"])
    assert panel.loc[("RUS", 2019), "exports"] == pytest.approx(1.0)   # WITS up to 2019, million USD
    assert panel.loc[("RUS", 2020), "exports"] == pytest.approx(5.0)   # BNS from 2020
    assert panel.loc[("DEU", 2020), "exports"] == 0.0                  # WITS ignored after 2019, no BNS -> zero
    assert panel.loc[("CHL", 2018), "exports"] == 0.0                  # no flow at all -> zero, not missing
    assert panel.loc[("RUS", 2021), "eaeu"] == 1.0 and panel.loc[("DEU", 2021), "eaeu"] == 0.0
    assert panel.loc[("RUS", 2021), "rta"] == 1.0                      # EAEU members count as covered
    assert panel.loc[("RUS", 2021), "ln_dist"] == pytest.approx(np.log(1900.0))


def test_gravity_panel_drops_the_2010_customs_union_gap():
    rows = [["2010-12-31", "world", "WDI_GDP_USD", c, 1e12] for c in ("RUS", "DEU", "CHL")]
    rows.append(["2010-12-31", "national", "WITS_KZ_IMPORTS_BY_PARTNER", "RUS", 10.0])
    panel = gravity.build_panel(_dims(rows), _cepii(["RUS", "DEU", "CHL"]), _geo(["RUS", "DEU", "CHL"]))
    assert panel.set_index("iso3").loc["RUS", "imports"] != panel.set_index("iso3").loc["RUS", "imports"]  # NaN


def test_ppml_recovers_known_elasticities_with_zeros():
    rng = np.random.default_rng(0)
    n_p, years = 120, range(2000, 2012)
    iso = [f"P{i:03d}" for i in range(n_p)]
    ln_gdp = rng.normal(24, 1.5, n_p)
    ln_dist = rng.normal(8, 0.6, n_p)
    rows = []
    for y in years:
        for i, c in enumerate(iso):
            g = ln_gdp[i] + 0.03 * (y - 2000) + rng.normal(0, 0.05)
            eaeu = float(i < 10 and y >= 2006)
            mu = np.exp(-18 + 0.9 * g - 1.1 * ln_dist[i] + 0.4 * eaeu + 0.02 * (y - 2000))
            rows.append({"iso3": c, "year": y, "exports": rng.poisson(mu * 2000) / 2000, "ln_gdp": g,
                         "ln_dist": ln_dist[i], "eaeu": eaeu})
    df = pd.DataFrame(rows)
    assert (df.exports == 0).mean() > 0.02
    res, _, _ = gravity.ppml(df, "exports", ["ln_gdp", "ln_dist", "eaeu"])
    assert res.params["ln_gdp"] == pytest.approx(0.9, abs=0.1)
    assert res.params["ln_dist"] == pytest.approx(-1.1, abs=0.15)
    assert res.params["eaeu"] == pytest.approx(0.4, abs=0.15)


# ---------------------------------------------------------------- BVAR
def test_marginal_likelihood_matches_student_t_predictive_chain():
    """log p(y1..yT) must equal the sum of one-step Student-t predictive densities -- the
    closed form's normalising constants are right only if this holds."""
    rng = np.random.default_rng(1)
    Y = np.cumsum(rng.normal(0, 1, (30, 1)), axis=0)
    Ydat, X = bvar.lagmat(Y, 1)
    Yd, Xd = bvar.dummies(Y, 1, 0.3, 2.0)
    total = bvar.log_ml(Ydat, X, Yd, Xd)
    chain, Ya, Xa = 0.0, Yd, Xd
    k = X.shape[1]
    for t in range(len(Ydat)):
        B = np.linalg.solve(Xa.T @ Xa, Xa.T @ Ya)
        e = Ya - Xa @ B
        nu = Ya.shape[0] - k
        x = X[t]
        scale2 = (e.T @ e).item() * (1 + x @ np.linalg.solve(Xa.T @ Xa, x)) / nu
        chain += stats.t.logpdf(Ydat[t, 0], df=nu, loc=(x @ B).item(), scale=np.sqrt(scale2))
        Ya, Xa = np.vstack([Ya, Ydat[t:t + 1]]), np.vstack([Xa, X[t:t + 1]])
    assert total == pytest.approx(chain, abs=1e-6)


def _var_data(T=90, seed=2):
    rng = np.random.default_rng(seed)
    n = 3
    A = np.array([[0.7, 0.0, 0.0], [0.3, 0.5, 0.1], [0.2, 0.2, 0.6]])
    Y = np.zeros((T, n))
    for t in range(1, T):
        Y[t] = A @ Y[t - 1] + rng.normal(0, 1, n)
    return Y


def test_gibbs_imposes_block_exogeneity_exactly():
    Y = _var_data()
    post = bvar.gibbs(Y, 2, 0.3, 5.0, 1, np.random.default_rng(3), draws=50, burn=50, thin=1)
    n = Y.shape[1]
    for B in post["B"]:
        for lag in range(2):
            assert np.all(B[lag * n + 1:lag * n + n, 0] == 0.0)  # domestic lags in the external equation
    assert np.any(post["B"][:, 1, 1] != 0.0)


def test_impact_with_reordering_is_a_valid_factorisation():
    rng = np.random.default_rng(4)
    M = rng.normal(size=(4, 4))
    S = M @ M.T + 4 * np.eye(4)
    P = bvar.impact(S, [0, 1, 3, 2])
    assert np.allclose(P @ P.T, S)
    assert P[3, 2] == 0.0 and P[2, 3] != 0.0  # 3 now before 2: 2 reacts to 3's shock on impact, not vice versa


def test_historical_decomposition_adds_up():
    Y = _var_data()
    post = bvar.gibbs(Y, 2, 0.3, 5.0, 1, np.random.default_rng(5), draws=5, burn=20, thin=1)
    contrib, base = bvar.historical_decomposition(post["B"][0], post["Sigma"][0], post["Y"], post["X"], 3, 2)
    assert np.allclose(contrib.sum(axis=2) + base, post["Y"])
    # without shocks the baseline is the deterministic path from the initial conditions
    B = post["B"][0]
    x = post["X"][0].copy()
    path = []
    for _ in range(len(base)):
        y = x @ B
        path.append(y)
        x = np.concatenate([y, x[:3], [1.0]])
    assert np.allclose(np.array(path), base, atol=1e-8)


def test_row_weights_scale_only_the_turbulent_quarters():
    idx = pd.period_range("2015Q2", "2016Q2", freq="Q")
    w = bvar.row_weights(idx, 4.0)
    assert list(w) == [1.0, 0.25, 0.25, 0.25, 1.0]


# ---------------------------------------------------------------- r*
def test_kalman_tracks_simulated_potential_and_rstar():
    rng = np.random.default_rng(6)
    p = {"a1": 0.8, "a2": -0.05, "a_r": -0.15, "a_o": 0.0, "b_pi": 0.6, "b_y": 0.3, "b_e": 0.0,
         "ln_s_gap": np.log(0.5), "ln_s_pi": np.log(1.0), "ln_s_ystar": np.log(0.3), "ln_kappa": 0.0}
    T = 160
    g = 4 + np.cumsum(rng.normal(0, 0.05, T))
    z = -1 + np.cumsum(rng.normal(0, 0.05, T))
    ystar = 1000 + np.cumsum(np.r_[0, g[:-1] / 4]) + np.cumsum(rng.normal(0, 0.3, T))
    r = 3 + np.cumsum(rng.normal(0, 0.4, T)) * 0.3
    gap, pi = np.zeros(T), np.full(T, 5.0)
    for t in range(4, T):
        rg = (r[t - 1] - g[t - 1] - z[t - 1] + r[t - 2] - g[t - 2] - z[t - 2]) / 2
        gap[t] = p["a1"] * gap[t - 1] + p["a2"] * gap[t - 2] + p["a_r"] * rg + rng.normal(0, 0.5)
        pi[t] = 0.6 * pi[t - 1] + 0.4 * pi[t - 4:t - 1].mean() + 0.3 * gap[t - 1] + rng.normal(0, 1)
    y = ystar + gap
    idx = pd.period_range("1980Q1", periods=T, freq="Q")
    s = pd.DataFrame({"y": y, "pi": pi, "r": r, "turbulent": False}, index=idx)
    s["y_l1"], s["y_l2"] = s.y.shift(1), s.y.shift(2)
    s["r_l1"], s["r_l2"] = s.r.shift(1), s.r.shift(2)
    s["pi_l1"] = s.pi.shift(1)
    s["pi_lag_avg"] = s.pi.shift(2).rolling(3).mean()
    s["oil_l1"] = s["de_l1"] = 0.0
    s = s.iloc[5:]
    lam_g = 0.05 / (4 * 0.3)
    lam_z = 0.05 * abs(p["a_r"]) / 0.5
    x0 = np.array([ystar[4], ystar[3], ystar[2], g[4], g[3], g[2], z[4], z[3], z[2]])
    kf = rstar.kalman(p, s, x0, np.eye(9) * 0.5, lam_g, lam_z, smooth=True)
    est_gap = s.y.values - kf["xs"][:, 0]
    assert np.corrcoef(est_gap, gap[5:])[0, 1] > 0.8
    assert np.abs(kf["xs"][:, 3] - g[5:]).mean() < 1.0
    assert np.isfinite(kf["ll"])
