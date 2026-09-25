import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_minfin


def test_fetchers_registered_for_every_indicator():
    """See tests/test_bns.py for why this doesn't call the fetchers themselves."""
    assert set(update_minfin.FETCHERS.keys()) == set(update_minfin.INDICATOR_IDS)
    for indicator_id, fn in update_minfin.FETCHERS.items():
        assert callable(fn), f"{indicator_id}'s fetcher is not callable"


def test_bulletin_month_names_match_by_stem():
    """The Jan-Feb 2026 bulletin heads табл 3 "январь-феврал отчет"; the exact
    lookup dropped it from six STATE_*_YTD series (audit 2026-09-25)."""
    from fetchers import minfin
    assert minfin._ru_month("феврал") == 2
    assert minfin._ru_month("февраль") == 2
    assert minfin._ru_month("мая") == 5
    assert minfin._ru_month("марта") == 3
    assert minfin._ru_month("ноябрь") == 11
    assert minfin._ru_month("отчет") is None


def test_points_the_listing_no_longer_serves_are_kept():
    fresh = [{"date": "2026-07-31", "value": 3.0}, {"date": "2026-06-30", "value": 2.5}]
    old = [{"date": "2025-02-28", "value": "1.0"}, {"date": "2026-06-30", "value": "2.0"}]
    merged, kept = update_minfin.keep_unlisted_history(fresh, old, "irregular (year-to-date cumulative, roughly monthly)")
    assert kept == 1
    # The period the source still serves is taken fresh, never from the old file.
    assert merged == [{"date": "2025-02-28", "value": 1.0}, {"date": "2026-06-30", "value": 2.5},
                      {"date": "2026-07-31", "value": 3.0}]


def test_kept_history_never_duplicates_a_period_under_another_date():
    fresh = [{"date": "2026-06-30", "value": 2.0}]
    old = [{"date": "2026-04-01", "value": "1.9"}, {"date": "2026-01-01", "value": "1.5"}]
    merged, kept = update_minfin.keep_unlisted_history(fresh, old, "quarterly")
    assert [r["date"] for r in merged] == ["2026-01-01", "2026-06-30"] and kept == 1
