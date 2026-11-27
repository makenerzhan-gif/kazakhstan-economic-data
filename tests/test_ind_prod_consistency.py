"""The cumulative industrial production index against the monthly one (both Taldau 701625).

January-to-month growth is a weighted mean of the months' own year-on-year indices, so
(1) January of the two series is the same number and (2) the cumulative index cannot sit far
from the plain mean of the months so far (the weights -- last year's monthly volumes -- move
little). Where it does, one of the two is a figure the source has not brought into line:
config/source_issues.yaml, ind_prod_mom_not_revised and ind_prod_ytd_2017. Marked
cross_source: reported by the run, never blocks it."""
import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 0.5      # index points
# Months where the two disagree by more than TOLERANCE as served by Taldau on 2026-11-27 (the
# difference cumulative - mean of months): recorded in config/source_issues.yaml.
KNOWN = {"2017-04-01": 4.27, "2017-05-01": -0.76, "2017-06-01": -0.58, "2017-07-01": -0.54, "2017-08-01": -0.51,
         "2026-02-01": -1.40, "2026-03-01": -1.00, "2026-04-01": -0.72, "2026-05-01": -0.54}


def _series(name):
    with open(ROOT / "data" / "processed" / "bns" / f"{name}.csv", encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f)}


def differences(ytd: dict, monthly: dict) -> dict:
    """cumulative - mean of the year's monthly indices up to that month, where every month is there."""
    out = {}
    for d, v in ytd.items():
        months = [monthly.get(f"{d[:4]}-{m:02d}-01") for m in range(1, int(d[5:7]) + 1)]
        if None not in months:
            out[d] = v - sum(months) / len(months)
    return out


def test_differences_on_a_made_up_year():
    monthly = {"2030-01-01": 102.0, "2030-02-01": 104.0, "2030-03-01": 106.0}
    ytd = {"2030-01-01": 102.0, "2030-02-01": 103.0, "2030-03-01": 105.5, "2030-04-01": 105.0}
    d = differences(ytd, monthly)
    assert d == {"2030-01-01": 0.0, "2030-02-01": 0.0, "2030-03-01": 1.5}      # April: no monthly value, no verdict


@pytest.mark.cross_source
def test_january_is_the_same_number_in_both_series():
    ytd, monthly = _series("ind_prod_ytd_yoy"), _series("ind_prod_monthly_yoy")
    bad = {d: (v, monthly[d]) for d, v in ytd.items() if d[5:7] == "01" and d in monthly and abs(v - monthly[d]) > 0.05}
    assert not bad, f"January cumulative != January monthly y/y: {bad}"


@pytest.mark.cross_source
def test_cumulative_index_stays_near_the_mean_of_the_months():
    d = differences(_series("ind_prod_ytd_yoy"), _series("ind_prod_monthly_yoy"))
    assert len(d) >= 150
    new = {k: round(v, 2) for k, v in d.items() if abs(v) > TOLERANCE and k not in KNOWN}
    assert not new, (f"cumulative industrial production index more than {TOLERANCE} pt from the mean of the monthly "
                     f"y/y indices in months not yet recorded in config/source_issues.yaml: {new}")
