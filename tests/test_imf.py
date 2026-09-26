import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_imf


def test_fetchers_registered_for_every_indicator():
    """See tests/test_bns.py for why this doesn't call the fetchers themselves."""
    assert set(update_imf.FETCHERS.keys()) == set(update_imf.INDICATOR_IDS)
    for indicator_id, fn in update_imf.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"


WEO_CSV = (
    "STRUCTURE[;],INDICATOR,FREQUENCY,TIME_PERIOD,OBS_VALUE,COUNTRY_UPDATE_DATE\n"
    "dataflow,NGDP_RPCH,A,2024,5.0,9/29/2025\n"
    "dataflow,NGDP_RPCH,A,2025,6.49,9/29/2025\n"
    "dataflow,NGDP_RPCH,A,2030,3.6,9/29/2025\n"
).encode()


def test_weo_years_are_stamped_at_year_end_like_bns():
    from fetchers import imf
    recs = imf._parse_annual_csv(WEO_CSV, "IMF_GDP_GROWTH", "test")
    assert [r["date"] for r in recs] == ["2024-12-31", "2025-12-31", "2030-12-31"]


def test_weo_years_from_the_vintage_year_on_are_labelled_projections():
    """The WEO mixes outturns and projections in one column; the year of the
    country update is the first that cannot be an outturn (audit 2026-09-25)."""
    from fetchers import imf
    recs = {r["date"][:4]: r for r in imf._parse_annual_csv(WEO_CSV, "IMF_GDP_GROWTH", "test")}
    assert "transformation" not in recs["2024"]
    assert recs["2025"]["transformation"].startswith(imf.WEO_PROJECTION)
    assert recs["2030"]["transformation"].startswith(imf.WEO_PROJECTION)


def test_processed_weo_series_carry_the_projection_label():
    import csv
    path = Path(__file__).resolve().parents[1] / "data" / "processed" / "imf" / "imf_gdp_growth.csv"
    rows = {r["date"][:4]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
    assert rows["2024"]["transformation"] == "level"
    assert "projection" in rows["2027"]["transformation"]
    assert all(d.endswith("-12-31") for d in (r["date"] for r in rows.values()))
