"""Derived analytics (scripts/fetchers/analytics.py, added 2026-11-10)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import analytics  # noqa: E402
from lib import dims  # noqa: E402


def test_weighted_quantile_mean():
    x, w = np.array([5.0, 1.0, 3.0, 2.0]), np.array([1.0, 1.0, 1.0, 1.0])
    assert analytics.weighted_quantile_mean(x, w, 0.5, 0.5) == 2.0          # the change at half the weight
    assert analytics.weighted_quantile_mean(x, w, 0.25, 0.75) == pytest.approx(2.5)   # drops 1 and 5
    assert analytics.weighted_quantile_mean(x, w, 0.0, 1.0) == pytest.approx(x.mean())
    # partial weights at the cut: weights 0.5/0.3/0.2, trimming 10 % each side
    v = analytics.weighted_quantile_mean(np.array([1.0, 2.0, 3.0]), np.array([5.0, 3.0, 2.0]), 0.1, 0.9)
    assert v == pytest.approx((1 * 0.4 + 2 * 0.3 + 3 * 0.1) / 0.8)


def test_hp_filter_matches_statsmodels():
    from statsmodels.tsa.filters.hp_filter import hpfilter
    y = np.cumsum(np.random.default_rng(0).normal(size=80))
    _, trend = hpfilter(y, 1600)
    assert np.allclose(analytics.hp_filter(y, 1600), trend)
    one = analytics.hp_onesided(y, 1600)
    assert np.isnan(one[10]) and one[-1] == pytest.approx(trend[-1])


def test_hamilton_gap_recovers_a_linear_series():
    y = pd.Series(np.arange(40, dtype=float) * 0.5, index=pd.date_range("2010-01-01", periods=40, freq="QS"))
    gap = analytics.hamilton_gap(y)
    assert gap.index[0] == y.index[11] and np.allclose(gap.values, 0, atol=1e-9)


def test_monthly_step_mean():
    ev = pd.Series([10.0, 12.0], index=pd.to_datetime(["2020-01-01", "2020-01-17"]))
    m = analytics.monthly_step_mean(ev, pd.Timestamp("2020-02-29"))
    assert m["2020-01-01"] == pytest.approx((16 * 10 + 15 * 12) / 31) and m["2020-02-01"] == 12.0


def test_config_and_registration():
    import update_dims
    ids = [d["id"] for d in dims.load_config()["datasets"]]
    for ds_id in ("CORE_INFLATION_MEASURES", "MONETARY_CONDITIONS", "OUTPUT_GAP", "CREDIT_GAP", "FISCAL_STANCE"):
        ds = update_dims.DATASETS[ds_id]
        assert ds["fetcher"] == "analytics" and ds["agency"] == "derived" and ds["measure"] in analytics.MEASURES
        # every input is fetched earlier in the same run
        assert ids.index(ds_id) > ids.index("CPI_DETAIL_MOM") and ids.index(ds_id) > ids.index("QNA_GDP_EXPENDITURE_SA_CONSTANT_2010")
    assert "analytics" in update_dims.AGENCY_FETCHERS and "derived" in update_dims.METHODOLOGY
    assert set(analytics.CORE_COMPONENTS) <= {"CP011_bread", "CP011_meat", "CP011_fish", "CP011_milk", "CP011_eggs", "CP011_oils",
                                              "CP011_fruitveg", "CP011_sugar", "CP012", "CP021", "CP022"} | {f"CP{i:02d}" for i in range(3, 13)}


@pytest.mark.skipif(not (dims.PROCESSED_ROOT / "core_inflation_measures.csv").exists(), reason="processed file absent")
def test_core_inflation_tracks_published_cpi():
    rows = dims.load_processed("CORE_INFLATION_MEASURES")
    s = pd.Series({r["date"]: float(r["value"]) for r in rows if r["item_code"] == "COMPONENTS_MEAN.YOY"})
    y = analytics.scalar("bns", "CPI_YOY") - 100
    y.index = y.index.strftime("%Y-%m-%d")
    j = pd.concat([s, y], axis=1).dropna()
    assert len(j) > 200 and j.corr().iloc[0, 1] > 0.98


def test_no_jump_check_skips_gap_series():
    rows = [{"date": f"2020-{m:02d}-01", "region": "national", "item_code": c, "item_name": c, "value": v}
            for c in ("GAP", "LEVEL") for m, v in ((1, 0.1), (4, -0.9), (7, 0.5))]
    plain = dims.validate(rows, "T", "quarterly")
    skipped = dims.validate(rows, "T", "quarterly", no_jump_check=["GAP"])
    assert any("[GAP]" in w for w in plain.warnings) and not any("[GAP]" in w for w in skipped.warnings)
    assert any("[LEVEL]" in w for w in skipped.warnings)
