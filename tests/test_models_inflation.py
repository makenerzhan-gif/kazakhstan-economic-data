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
    params["y1"], params["y2"], params["usd3"] = 0.4, 0.2, 0.05                       # AR(2) and a second lag coefficient
    c = []
    for h in range(N.L + 1):
        c.append((0.1 if h == 0 else 0.05 if h == 3 else 0.0) + (0.4 * c[-1] if h >= 1 else 0.0) + (0.2 * c[-2] if h >= 2 else 0.0))
    assert N.cumulative(params, cols) == pytest.approx(sum(c))
    params["y1"], params["y2"], params["usd3"] = 0.0, 0.0, 0.0
    assert N.cumulative(params, cols) == pytest.approx(0.1)                            # no AR terms: the lag sum itself
    t = pd.read_csv(M / "erpt_neer" / "erpt_usd_vs_neer.csv")
    food = t[t["раздел"].str.startswith("Продукты питания")].iloc[0]
    assert food["USD: перенос 12м"] > 2 * food["USD: сумма b"] > 0                   # food: AR sum about 0.75


def test_border_pass_through_is_within_reason():
    """Read as month-on-month, the «December = 100» import price index gave pass-through of 2.6 and 1.9."""
    t = pd.read_csv(M / "erpt_neer" / "erpt_border.csv")
    assert t[["граница←usd", "граница←neer"]].abs().max().max() < 1.2
    import erpt_border as B
    idx = pd.period_range("2024-11", "2025-03", freq="M")
    ip = pd.DataFrame({"IV": [110.0, 112.0, 101.0, 103.0, np.nan]}, index=idx)
    mm = B.monthly_change(ip)["IV"]
    assert mm["2024-12"] == pytest.approx(100 * np.log(112 / 110)) and mm["2025-01"] == pytest.approx(100 * np.log(1.01))   # January against 100
    assert mm["2025-02"] == pytest.approx(100 * np.log(103 / 101)) and np.isnan(mm["2025-03"]) and np.isnan(mm["2024-11"])


def test_shapiro_contributions_and_official_weights():
    c = pd.read_csv(M / "shapiro_goods" / "contributions.csv", index_col=0)
    assert (c.goods_demand + c.goods_supply + c.goods_ambiguous - c.goods_total).abs().max() < 0.005
    months = pd.PeriodIndex(c.index, freq="M")
    assert len(c) >= 100 and len(pd.period_range(months[0], months[-1], freq="M")) == len(c)   # no hole: 2018, 2021 weights are interpolated
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


def test_bank_rescue_of_2017_is_read_from_the_budget_line():
    import svar_v2_data as V
    assert V.bank_rescue_2017() == pytest.approx(2_100_398.2, abs=1.0)        # million tenge: specific 169, July 2017


def test_market_core_is_consistent_with_headline_inflation():
    """No builder script exists for the index; this is what can be checked: headline m/m = a weighted sum of the
    market core and what it leaves out, year by year, within rounding."""
    mk = pd.read_csv(M / "cpi_components" / "market_core_index.csv", index_col=0, parse_dates=True)
    mm = pd.read_csv(REPO / "model_data" / "monthly.csv", index_col=0, parse_dates=True)
    d = pd.read_csv(REPO / "data" / "processed" / "dims" / "cpi_detail_mom.csv", parse_dates=["date"])
    p = d.pivot_table(index="date", columns="item_code", values="value")
    g = lambda s: 100 * np.log(s).diff()                                       # noqa: E731
    x = pd.DataFrame({"y": g(mm.cpi), "mkt": g(mk.mkt_base), "reg": g(mm.cpi_regulated),
                      "fv": 100 * np.log(p["frukty_i_ovoshchi"] / 100), "petrol": 100 * np.log(p["benzin"] / 100),
                      "diesel": 100 * np.log(p["dizelnoe_toplivo"] / 100)}).dropna()
    for year in range(2012, 2026):
        s = x[x.index.year == year]
        b = np.linalg.lstsq(s.drop(columns="y").values, s.y.values, rcond=None)[0]
        assert np.abs(s.drop(columns="y").values @ b - s.y.values).max() < 0.12, year
        assert 0.75 < b[0] < 0.97 and 0.9 < b.sum() < 1.25, (year, b.round(3))
