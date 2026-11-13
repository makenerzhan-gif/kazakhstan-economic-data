"""Inflation models (scripts/models/svar_v2.py, erpt_*.py, shapiro_goods.py): the properties whose absence
were the errors found on 2026-11-13 -- shares that did not add up, a level index read as a monthly change,
a sum of lag coefficients sold as a 12-month pass-through."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "models"))
M = REPO / "models"


def test_fevd_shares_add_up_to_one():
    s = pd.read_csv(M / "svar_v2" / "summary.csv")
    shares = s[[c for c in s.columns if c.startswith("FEVD8")]]
    assert len(s) == 7 and (shares.sum(axis=1) - 1).abs().max() < 0.002          # three-decimal rounding of up to eight shares
    for name in ("base", "cons", "h01"):
        f = pd.read_csv(M / "bvar_sign" / f"fevd_infl_{name}.csv")
        assert (f.drop(columns="h").sum(axis=1) - 100).abs().max() < 0.3


def test_posterior_mean_decomposition_reproduces_inflation():
    for path in sorted((M / "svar_v2").glob("mean_*.csv")):
        t = pd.read_csv(path, index_col=0)
        parts = t.drop(columns=["actual", "baseline"]).sum(axis=1) + t["baseline"]
        assert (parts - t["actual"]).abs().max() < 0.005, path.name
    assert len(list((M / "svar_v2").glob("mean_*.csv"))) == 7


def test_cumulative_pass_through_includes_the_autoregressive_terms():
    import erpt_neer as N
    cols = [f"usd{k}" for k in range(N.L + 1)]
    params = pd.Series({**{c: 0.0 for c in cols}, "y1": 0.5, "y2": 0.0})
    params["usd0"] = 0.1
    assert N.cumulative(params, cols) == pytest.approx(0.1 * (1 - 0.5 ** 13) / 0.5)   # 0.2 against a lag sum of 0.1
    params["y1"] = 0.0
    assert N.cumulative(params, cols) == pytest.approx(0.1)                            # no AR terms: the lag sum itself
    t = pd.read_csv(M / "erpt_neer" / "erpt_usd_vs_neer.csv")
    food = t[t["раздел"].str.startswith("Продукты питания")].iloc[0]
    assert food["USD: перенос 12м"] > 2 * food["USD: сумма b"] > 0                   # food: AR sum about 0.75


def test_border_pass_through_is_within_reason():
    """Read as month-on-month, the «December = 100» import price index gave pass-through of 2.6 and 1.9."""
    t = pd.read_csv(M / "erpt_neer" / "erpt_border.csv")
    assert t[["граница←usd", "граница←neer"]].abs().max().max() < 1.2
    src = (REPO / "scripts" / "models" / "erpt_border.py").read_text(encoding="utf-8")
    assert "ip / prev" in src and "month == 1" in src


def test_shapiro_contributions_and_official_weights():
    c = pd.read_csv(M / "shapiro_goods" / "contributions.csv", index_col=0)
    assert (c.goods_demand + c.goods_supply + c.goods_ambiguous - c.goods_total).abs().max() < 0.005
    w = pd.read_csv(M / "shapiro_goods" / "cpi_group_weights_official.csv", index_col=0)
    assert (w.sum(axis=1) - 1).abs().max() < 1e-3 and abs(w.loc[2019, "nonfood"] - 0.298) < 0.005
    lab = pd.read_csv(M / "shapiro_goods" / "labels.csv", index_col=0)
    assert (lab == "ambiguous").mean().max() < 0.40                                  # was 0.46 with the y/y residuals


def test_shapiro_price_innovation_is_monthly():
    import shapiro_goods as S
    rng = np.random.default_rng(0)
    idx = pd.period_range("2010-01", periods=180, freq="M")
    shock = pd.Series(rng.normal(size=180), index=idx)
    season = pd.Series(np.tile(np.arange(12) - 5.5, 15), index=idx)
    price = 0.3 * shock.shift(1).fillna(0) + shock + season                         # m/m with a seasonal and an MA term
    qty = pd.Series(rng.normal(size=180), index=idx).rolling(12).sum()              # a y/y-type series
    res = S.innovations(price, qty, 13)
    assert np.corrcoef(res["p"], shock.loc[res.index])[0, 1] > 0.85                 # the residual is the month's own shock
