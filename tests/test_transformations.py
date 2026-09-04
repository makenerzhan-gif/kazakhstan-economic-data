import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import transformations as t


def test_level_is_identity():
    s = [("2026-01", 10.0), ("2026-02", 20.0)]
    assert t.level(s) == s


def test_log():
    s = [("2026-01", math.e), ("2026-02", -1.0), ("2026-03", None)]
    out = t.log(s)
    assert math.isclose(out[0][1], 1.0)
    assert out[1][1] is None  # negative -> undefined
    assert out[2][1] is None  # None -> None


def test_difference():
    s = [("2026-01", 10.0), ("2026-02", 15.0), ("2026-03", 12.0)]
    out = t.difference(s, periods=1)
    assert out[0][1] is None
    assert out[1][1] == 5.0
    assert out[2][1] == -3.0


def test_growth_rate():
    s = [("2026-01", 100.0), ("2026-02", 110.0)]
    out = t.growth_rate(s, periods=1)
    assert out[0][1] is None
    assert math.isclose(out[1][1], 10.0)


def test_yoy_monthly():
    s = [(f"2025-{m:02d}", 100.0) for m in range(1, 13)] + [("2026-01", 105.0)]
    out = t.yoy(s, obs_per_year=12)
    assert math.isclose(out[-1][1], 5.0)


def test_deflate():
    nominal = [("2026-01", 200.0)]
    price_index = [("2026-01", 200.0)]
    out = t.deflate(nominal, price_index, base_value=100.0)
    assert math.isclose(out[0][1], 100.0)


def test_rebase_index():
    s = [("2026-01", 50.0), ("2026-02", 100.0)]
    out = t.rebase_index(s, new_base_date="2026-02", new_base_value=100.0)
    assert math.isclose(dict(out)["2026-01"], 50.0)
    assert math.isclose(dict(out)["2026-02"], 100.0)


def test_seasonal_adjust_placeholder_is_passthrough():
    s = [("2026-01", 10.0)]
    assert t.seasonal_adjust_placeholder(s) == s


def test_decumulate_ytd_matches_validate_outliers_own_period_contribution():
    # Same fixture as test_schema.py::test_validate_outliers_year_to_date_ignores_the_january_reset
    s = [
        ("2026-01-01", 100.0),
        ("2026-04-01", 210.0),
        ("2026-07-01", 320.0),
        ("2026-10-01", 430.0),
        ("2027-01-01", 105.0),  # January reset -- own-period contribution, not a diff across years
    ]
    out = t.decumulate_ytd(s)
    assert [v for _, v in out] == [100.0, 110.0, 110.0, 110.0, 105.0]


def test_decumulate_ytd_flags_real_spike_within_year():
    # Same fixture as test_schema.py::test_validate_outliers_year_to_date_still_catches_a_real_anomaly
    s = [
        ("2026-01-01", 100.0),
        ("2026-04-01", 210.0),
        ("2026-07-01", 900.0),
        ("2026-10-01", 1010.0),
    ]
    out = t.decumulate_ytd(s)
    assert [v for _, v in out] == [100.0, 110.0, 690.0, 110.0]


def test_decumulate_ytd_propagates_none_and_does_not_fake_a_delta_across_a_gap():
    s = [("2026-01-01", 100.0), ("2026-04-01", None), ("2026-07-01", 320.0)]
    out = t.decumulate_ytd(s)
    assert out[0][1] == 100.0
    assert out[1][1] is None
    assert out[2][1] == 320.0  # treated as a fresh run's first value, not 320-None


def test_decumulate_ytd_single_observation_is_unchanged():
    s = [("2026-01-01", 42.0)]
    assert t.decumulate_ytd(s) == s
