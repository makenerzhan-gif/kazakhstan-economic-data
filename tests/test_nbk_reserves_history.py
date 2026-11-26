"""Reserves and National Fund history 1995-2017 from NBK's site table (added 2026-11-26),
spliced in front of the open-data form 34 that starts at 2018-01-01."""
import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import nbk  # noqa: E402
from lib import validation  # noqa: E402
import load_nbk_reserves_history as loader  # noqa: E402


def _hist(tmp_path, rows):
    p = tmp_path / "h.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "fx_reserves", "national_fund_assets", "reporting_date"])
        w.writeheader()
        w.writerows(rows)
    return p


def test_page_record_is_dated_on_the_first_day_of_the_next_month():
    assert loader.next_month_start("2017-12-12 00:00:00") == "2018-01-01"
    assert loader.next_month_start("2026-10-31 08:00:00") == "2026-11-01"


def test_loader_refuses_a_gap_or_two_records_in_one_month():
    rec = lambda d, v: {"reporting_date": d, loader.GROSS: v, loader.NF: None}  # noqa: E731
    assert [r["date"] for r in loader.rows_from_records([rec("1995-01-04", 1), rec("1995-02-13", 2)])] == ["1995-02-01", "1995-03-01"]
    with pytest.raises(ValueError):
        loader.rows_from_records([rec("1995-01-04", 1), rec("1995-03-13", 2)])
    with pytest.raises(ValueError):
        loader.rows_from_records([rec("1995-01-04", 1), rec("1995-01-20", 2)])


def test_splice_prepends_only_months_before_the_api_and_checks_the_overlap(tmp_path):
    p = _hist(tmp_path, [
        {"date": "2017-11-01", "fx_reserves": "31073", "national_fund_assets": "", "reporting_date": ""},
        {"date": "2017-12-01", "fx_reserves": "30997", "national_fund_assets": "", "reporting_date": ""},
        {"date": "2018-01-01", "fx_reserves": "30997", "national_fund_assets": "", "reporting_date": ""},
    ])
    api = [{"date": "2018-01-01", "value": 30996.649}]
    out = nbk.splice_reserves_history("FX_RESERVES", "fx_reserves", api, path=p)
    assert [(r["date"], r["value"]) for r in out] == [("2017-11-01", 31073.0), ("2017-12-01", 30997.0), ("2018-01-01", 30996.649)]
    with pytest.raises(validation.StructuralChangeError):
        nbk.splice_reserves_history("FX_RESERVES", "fx_reserves", [{"date": "2018-01-01", "value": 31500.0}], path=p)


def test_stored_history_equals_the_api_on_every_shared_month():
    hist = {r["date"]: r for r in csv.DictReader(nbk.RESERVES_HISTORY_PATH.open(encoding="utf-8"))}
    for ind, col in (("fx_reserves", "fx_reserves"), ("national_fund_assets", "national_fund_assets")):
        with (REPO_ROOT / "data" / "processed" / "nbk" / f"{ind}.csv").open(encoding="utf-8") as f:
            api = {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["date"] >= "2018-01-01"}
        shared = [d for d in api if d in hist and hist[d][col]]
        assert len(shared) >= 100
        assert all(abs(round(api[d]) - float(hist[d][col])) <= 0.5 for d in shared), ind
