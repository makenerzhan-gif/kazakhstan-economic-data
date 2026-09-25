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


def test_cbr_key_rate_and_usd_rub_parsers():
    from fetchers import foreign
    soap = b"""<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>
    <KeyRateXMLResponse xmlns="http://web.cbr.ru/"><KeyRateXMLResult><KeyRate xmlns="">
    <KR><DT>2023-12-18T00:00:00+03:00</DT><Rate>16.00</Rate></KR><KR><DT>2023-12-15T00:00:00+03:00</DT><Rate>15.00</Rate></KR>
    </KeyRate></KeyRateXMLResult></KeyRateXMLResponse></soap:Body></soap:Envelope>"""
    assert foreign.parse_cbr_key_rate(soap) == {"2023-12-18": 16.0, "2023-12-15": 15.0}
    xml = ('<?xml version="1.0" encoding="windows-1251"?><ValCurs><Record Date="11.03.2022" Id="R01235">'
           '<Nominal>1</Nominal><Value>120,3785</Value></Record></ValCurs>').encode("cp1251")
    assert foreign.parse_cbr_xml_dynamic(xml) == {"2022-03-11": 120.3785}


def test_qnea_takes_real_nsa_national_currency_gdp_from_the_first_quarter_given():
    from fetchers import foreign
    rows = ("STRUCTURE[;],COUNTRY,INDICATOR,PRICE_TYPE,S_ADJUSTMENT,TYPE_OF_TRANSFORMATION,FREQUENCY,TIME_PERIOD,OBS_VALUE\n"
            "dataflow,RUS,B1GQ,Q,NSA,XDC,Q,2013-Q4,23.75\n"
            "dataflow,RUS,B1GQ,Q,NSA,XDC,Q,2014-Q1,28.17\n"
            "dataflow,RUS,B1GQ,V,NSA,XDC,Q,2014-Q1,99\n"
            "dataflow,RUS,B1GQ,Q,NSA,USD,Q,2014-Q1,1\n").encode()
    assert foreign.parse_qnea_real_gdp(rows, "2014-Q1") == {"2014-01-01": 28.17}


def test_fred_csv_skips_missing_observations():
    from fetchers import foreign
    content = b"observation_date,GS10\n2023-10-01,4.80\n2023-11-01,.\n2023-12-01,\n"
    assert foreign.parse_fred_csv(content, "GS10") == {"2023-10-01": 4.8}


def test_external_block_holds_known_points():
    key = _series("cbr", "RU_KEY_RATE")
    assert key["2013-09-17"] == 5.5 and key["2022-02-28"] == 20.0 and key["2023-12-18"] == 16.0
    assert _series("cbr", "RUB_USD")["2022-03-11"] == 120.3785
    assert min(_series("cbr", "RUB_USD")) == "1998-01-01"
    assert _series("eec", "RU_CPI_YOY")["2024-12-01"] == 109.5
    assert min(_series("imf", "RU_GDP_REAL")) == "2014-01-01"
    assert _series("fred", "US_FED_FUNDS")["2023-08-01"] == 5.33


def test_nbs_quarter_codes_and_ecb_periods():
    from fetchers import foreign
    payload = {"data": [{"code": "202001SS", "values": [{"_id": "X", "value": "93.2"}, {"_id": "Y", "value": "1"}]},
                        {"code": "202602SS", "values": [{"_id": "X", "value": ""}]}]}
    assert foreign.parse_nbs_quarterly(payload, "X") == {"2020-01-01": 93.2}
    ecb = b"KEY,TIME_PERIOD,OBS_VALUE\nA,2022-10,10.6\nA,2020-Q2,1.5\nA,2019-09-18,-0.5\nA,2023-01,\n"
    assert foreign.parse_ecb_csv(ecb) == {"2022-10-01": 10.6, "2020-04-01": 1.5, "2019-09-18": -0.5}


def test_foreign_demand_weights_partner_growth_on_common_quarters():
    from fetchers import foreign
    levels = {"2024-01-01": 100.0, "2025-01-01": 102.0, "2025-04-01": 50.0}
    assert foreign.yoy_index(levels, "level") == {"2025-01-01": 102.0}
    growth = {"A": {"2025-01-01": 102.0, "2025-04-01": 101.0}, "B": {"2025-01-01": 110.0}}
    assert foreign.foreign_demand(growth, {"A": 3.0, "B": 1.0}) == {"2025-01-01": 104.0}


def test_foreign_demand_weights_are_documented_and_the_index_exists():
    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "foreign_demand.yaml").read_text(encoding="utf-8"))
    assert {p["name"] for p in cfg["partners"]} == {"euro area", "China", "Russia"} and cfg["reviewed"]
    fd = _series("derived", "FOREIGN_DEMAND_YOY")
    assert min(fd) == "2015-01-01" and 88 < fd["2020-04-01"] < 95     # the 2020-Q2 collapse
