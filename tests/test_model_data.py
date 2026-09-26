"""model_data builder (scripts/build_model_data.py)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_model_data as B  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def _m(values, start="2020-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"))


def test_chain_and_decumulate():
    s = _m([101.0, 102.0, 100.0])
    assert list(B.chain(s).round(4)) == [100.0, 102.0, 102.0]
    ytd = _m([10.0, 25.0, 45.0], start="2021-01-01")
    assert list(B.decumulate_ytd(ytd, 12)) == [10.0, 15.0, 20.0]
    gap = pd.Series([10.0, 45.0], index=pd.to_datetime(["2021-01-01", "2021-03-01"]))
    assert list(B.decumulate_ytd(gap, 12).index) == [pd.Timestamp("2021-01-01")]      # never across a gap


def test_asat_to_eop_and_event_months():
    s = _m([1.0, 2.0], start="2026-01-01")
    assert list(B.asat_to_eop(s, 12).index) == list(pd.to_datetime(["2025-12-01", "2026-01-01"]))
    ev = pd.Series([10.0, 12.0], index=pd.to_datetime(["2024-01-01", "2024-01-16"]))
    m = B.to_monthly(ev, "mean", event=True)
    assert m.iloc[0] == pytest.approx((15 * 10 + 16 * 12) / 31)
    assert m.loc["2024-02-01"] == 12.0


def test_seasonal_adjust_removes_a_pure_seasonal():
    idx = pd.date_range("2015-01-01", periods=96, freq="MS")
    trend = np.linspace(100, 200, 96)
    s = pd.Series(trend * (1 + 0.1 * np.sin(2 * np.pi * np.arange(96) / 12)), index=idx)
    sa = B.seasonal_adjust(s, 12, "log", True)
    assert (sa / trend - 1).abs().max() < 0.02


def test_built_panels_are_consistent():
    m = pd.read_csv(REPO / "model_data" / "monthly.csv", index_col=0, parse_dates=True)
    q = pd.read_csv(REPO / "model_data" / "quarterly.csv", index_col=0, parse_dates=True)
    assert m.index.min() >= pd.Timestamp("1994-01-01") and m.index.is_unique and q.index.is_unique
    assert (m.index.day == 1).all() and set(q.index.month) <= {1, 4, 7, 10}
    for col in ("cpi", "cpi_sa", "cpi_yoy", "base_rate", "m2", "usdkzt", "eurobond_spread"):
        assert col in m
    for col in ("gdp", "gdp_saar", "employment_sa", "capital", "tfp_log", "cpi_yoy"):
        assert col in q
    assert q["capital"].dropna().is_monotonic_increasing          # net investment has stayed positive
    assert 0.25 < q["labour_share"].dropna().mean() < 0.45
