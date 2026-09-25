"""The sources added for the QPM / BVAR data (2026-09-25): KASE (TONIA, government
securities yield curve) and the long NBK histories (official rates from 1999, money from
1994, base-rate decisions from 2015, deposit and loan rates from 1996-97)."""
import csv
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import kase, nbk  # noqa: E402

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


def _series(agency: str, indicator_id: str) -> dict[str, float]:
    with (PROCESSED / agency / f"{indicator_id.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f)}


def test_tradingview_history_is_dated_by_utc_trade_date():
    payload = {"s": "ok", "t": [1735948800, 1736035200], "c": [14.43, 14.3]}   # 2025-01-04, 2025-01-05 (a working Sunday)
    assert kase.parse_tv_history(payload, "TONIA") == [{"date": "2025-01-04", "value": 14.43},
                                                       {"date": "2025-01-05", "value": 14.3}]
    with pytest.raises(Exception):
        kase.parse_tv_history({"s": "no_data"}, "TONIA")


def test_nelson_siegel_spot_matches_kase_on_2026_09_25():
    """Parameters of the 2026-09-25 curve; KASE's own API plots 14.463 at 1.003 years and
    12.853 at 10.003 years."""
    p = dict(b0=0.12300057583821004, b1=0.026539491431365, b2=0.010474227322786526, tau=1.5000000000003257)
    assert math.isclose(100 * kase.ns_spot(1.003, **p), 14.463, abs_tol=0.001)
    assert math.isclose(100 * kase.ns_spot(10.003, **p), 12.853, abs_tol=0.001)


def test_monthly_tenor_average_is_the_mean_of_the_daily_curves():
    flat = lambda d, level: {"date": d, "B0": level, "B1": 0.0, "B2": 0.0, "TAU": 1.5}
    out = kase.monthly_tenor_averages([flat("2026-08-28", 0.12), flat("2026-08-31", 0.14), flat("2026-09-01", 0.10)])
    assert out["10Y"] == [{"date": "2026-08-01", "value": 13.0}, {"date": "2026-09-01", "value": 10.0}]


REPORT = """<table><thead><tr><th></th><th>Числовое значение</th><th>ДОЛЛАР США</th>
<th>Числовое значение</th><th>РОССИЙСКИЙ РУБЛЬ</th></tr></thead><tbody>
<tr><td>2015-08-20</td><td>1</td><td>188.38</td><td>1</td><td>2.87</td></tr>
<tr><td>2015-08-21</td><td>1</td><td>255.26</td><td>10</td><td>37.9</td></tr>
<tr><td>bad</td><td>1</td></tr>
</tbody></table>"""


def test_official_rates_report_is_read_by_column_header_and_per_unit():
    out = nbk.parse_official_rates_report(REPORT)
    assert out["USD"] == {"2015-08-20": 188.38, "2015-08-21": 255.26}
    assert out["RUB"]["2015-08-21"] == 3.79       # quantity 10
    assert "EUR" not in out


def test_money_stock_is_dated_as_at_the_first_of_the_next_month():
    assert nbk.money_as_at("2026-08-31 22:00:00") == "2026-09-01"
    assert nbk.money_as_at("2021-12-14 00:00:00") == "2022-01-01"


def test_long_histories_hold_known_points():
    base = _series("nbk", "BASE_RATE")
    assert min(base) == "2015-09-02" and base["2015-09-02"] == 12.0 and base["2022-02-24"] == 13.5
    usd = _series("nbk", "EXCHANGE_RATE")
    assert min(usd) <= "1999-12-31"
    assert usd["2010-01-04"] == 148.46 and usd["2015-08-20"] == 188.38 and usd["2015-08-21"] == 255.26
    assert usd["2021-05-07"] == 426.99          # get_rates.cfm had substituted 464.77
    m3 = _series("nbk", "M3")
    assert min(m3) <= "1995-01-01"
    # Form 51 carried 4.50 trn for this date; the stock at the end of November 2021 was 28.70 trn.
    assert m3["2021-12-01"] > 25_000_000
    tonia = _series("kase", "TONIA")
    assert min(tonia) == "2001-09-02" and "2025-01-05" in tonia
    assert min(_series("kase", "GS_YIELD_10Y")) == "2019-11-01"
    assert min(_series("nbk", "DEPOSIT_RATE")) == "1996-12-01"
    assert min(_series("nbk", "LOAN_RATE_ISSUED_LEGAL_KZT")) == "1997-01-01"
