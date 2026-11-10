"""Block B sources added 2026-11-10: FRED financial conditions, IMF PCPS metals, sovereign ratings,
quasi-state debt, the Minfin debt listing fix."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import foreign, manual_vintages, minfin  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def test_fred_monthly_mean_drops_the_current_month(monkeypatch):
    monkeypatch.setattr(foreign, "_get", lambda *a, **k: b"")
    monkeypatch.setattr(foreign, "_save_raw", lambda *a, **k: None)

    class D:
        @staticmethod
        def today():
            import datetime
            return datetime.date(2021, 1, 20)
    monkeypatch.setattr(foreign, "date", D)
    monkeypatch.setitem(foreign.FRED_SERIES, "VIX", ("VIXCLS", "monthly_mean", "x"))
    monkeypatch.setattr(foreign, "parse_fred_csv", lambda content, series: {
        **{f"2020-{m:02d}-02": 10.0 for m in range(1, 13)}, **{f"2020-{m:02d}-15": 20.0 for m in range(1, 13)},
        **{f"2019-{m:02d}-{d:02d}": 1.0 for m in range(1, 13) for d in range(1, 10)}, "2021-01-05": 5.0})
    records, meta = foreign._fetch_fred("VIX")
    by = {r["date"]: r["value"] for r in records}
    assert by["2020-06-01"] == 15.0 and "2021-01-01" not in by and meta["frequency"] == "monthly"


def test_new_fred_and_imf_ids_are_wired():
    import update_foreign
    import update_imf
    ind = {i["id"]: i for i in yaml.safe_load((REPO / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]}
    for i in ("VIX", "USD_BROAD_INDEX", "USD_EME_INDEX", "US_BAA_SPREAD", "US_NFCI"):
        assert i in update_foreign.FETCHERS and ind[i]["agency"] == "fred" and ind[i]["frequency"] == "monthly"
        assert foreign.FRED_SERIES[i][1] == "monthly_mean"
    for i in ("URANIUM_PRICE", "CHROMIUM_PRICE", "MANGANESE_PRICE"):
        assert i in update_imf.FETCHERS and i in update_imf.INDICATOR_IDS and ind[i]["agency"] == "imf"
    import update_nbk
    for i in ("EXTERNAL_DEBT_STATE_CONTROLLED", "EXTERNAL_DEBT_STATE_CONTROLLED_GUARANTEED"):
        assert i in update_nbk.FETCHERS and i in update_nbk.INDICATOR_IDS and ind[i]["agency"] == "nbk"


def test_rating_scale():
    assert manual_vintages.rating_notch("SP", "BBB-") == 12 == manual_vintages.rating_notch("MOODYS", "Baa3")
    assert manual_vintages.rating_notch("FITCH", "AAA") == 21 == manual_vintages.rating_notch("MOODYS", "Aaa")
    assert manual_vintages.rating_notch("MOODYS", "Ba1") == 11 and manual_vintages.rating_notch("SP", "D") == 0
    with pytest.raises(ValueError):
        manual_vintages.rating_notch("SP", "Baa1")


def test_rating_records_step_series():
    doc = {"actions": {"SP": [{"date": "2020-03-15", "rating": "BBB-", "outlook": "stable"},
                              {"date": "2020-06-01", "rating": "BBB", "outlook": "positive"}],
                       "MOODYS": [{"date": "2020-01-10", "rating": "Baa2", "outlook": "negative"}],
                       "FITCH": [{"date": "2020-01-10", "rating": "BBB", "outlook": "stable"}]}}
    recs = manual_vintages.rating_records(doc, {"id": "T", "file": "x"}, today="2020-07-10")
    v = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert v[("SP.RATING", "2020-03-01")] == 12 and v[("SP.RATING", "2020-05-01")] == 12 and v[("SP.RATING", "2020-06-01")] == 13
    assert v[("SP.OUTLOOK", "2020-07-01")] == 1 and ("SP.RATING", "2020-08-01") not in v
    assert ("AVG.RATING_OUTLOOK", "2020-02-01") not in v          # S&P not yet rated
    assert v[("AVG.RATING_OUTLOOK", "2020-06-01")] == pytest.approx((13 + 1 / 3 + 13 - 1 / 3 + 13) / 3)


def test_sovereign_ratings_yaml_is_valid():
    doc = yaml.safe_load((REPO / "config" / "sovereign_ratings.yaml").read_text(encoding="utf-8"))
    recs = manual_vintages.rating_records(doc, {"id": "SOVEREIGN_RATINGS", "file": "config/sovereign_ratings.yaml"}, today="2026-11-10")
    v = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert v[("SP.RATING", "2026-09-01")] == 13 and v[("SP.RATING", "2026-07-01")] == 12     # BBB from 2026-08-21
    assert v[("MOODYS.RATING", "2026-11-01")] == 14 and v[("FITCH.RATING", "2026-11-01")] == 13
    for agency, actions in doc["actions"].items():
        dates = [str(a["date"]) for a in actions]
        assert dates == sorted(dates) and all(a["conf"] in ("H", "M") for a in actions), agency


def test_quasi_state_table():
    doc = yaml.safe_load((REPO / "config" / "quasi_state_debt.yaml").read_text(encoding="utf-8"))
    recs = manual_vintages.table_records(doc, {"id": "Q", "file": "x"})
    v = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert v[("TOTAL_VAP", "2025-12-31")] == v[("TOTAL_VAP_EXTERNAL", "2025-12-31")] + v[("TOTAL_VAP_INTERNAL", "2025-12-31")]
    assert v[("SK_BORROWINGS", "2025-12-31")] == 8087121


def test_debt_listing_unions_activities(monkeypatch):
    minfin._LISTING_CACHE.clear() if hasattr(minfin, "_LISTING_CACHE") else None
    listings = {"14610": [{"id": 2, "title": "State and State Guaranteed Debt (as of July 1, 2026)", "created_date": "2026-07-30"}],
                "565": [{"id": 3, "title": "State and State Guaranteed Debt, State Guarantees Debt (as of October 1, 2026)", "created_date": "2026-10-30"},
                        {"id": 4, "title": "Order on a state securities issue by the Almaty city local executive body", "created_date": "2026-10-01"},
                        {"id": 2, "title": "State and State Guaranteed Debt (as of July 1, 2026)", "created_date": "2026-07-30"}]}
    monkeypatch.setattr(minfin, "_list_documents", lambda **kw: listings[kw["activities"]])
    assert [d["id"] for d in minfin._debt_documents()] == [3, 2]
