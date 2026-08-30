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
