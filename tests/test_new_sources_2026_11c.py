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


# ---------------------------------------------------------------- BNS block B (Taldau extensions, sector accounts, social standards)

def test_fetch_regional_segment_national_term_item_pos_and_item_measure(monkeypatch):
    from fetchers import taldau_dims
    calls = []

    def fake_post(ds, terms, parent="", pos="0", term="741880"):
        calls.append((ds["dic_ids"], terms, term, ds["measure_id"]))
        if ds["dic_ids"].startswith("4843"):
            return [{"id": "77397431", "text": "РК", "leaf": "true", "y012025": "51548"}]
        return [{"id": "741880", "text": "РК", "leaf": "true", "y122024": "50293"}]

    monkeypatch.setattr(taldau_dims, "_post", fake_post)
    monkeypatch.setattr(taldau_dims.raw_store, "save_raw_bytes", lambda *a, **k: Path("x"))
    monkeypatch.setattr(taldau_dims.raw_store, "write_download_manifest", lambda *a, **k: None)
    ds = {"id": "T", "index_id": "704492", "measure_id": "1", "frequency": "monthly", "item_pos": 2,
          "segments": [{"dic_ids": "67,576,1450", "terms": "741880,741935,3768282"},
                       {"dic_ids": "4843,576,1450", "terms": "77397431,741935,3768282", "national_term": "77397431"},
                       {"dic_ids": "67,1450", "terms": "741880,3768282", "item_pos": 1, "items": ["EXTRA"]}],
          "items": [{"code": "TOTAL", "term": "3768282", "name": "Все"}, {"code": "EXTRA", "term": "9", "name": "x", "measure_id": "7"}]}
    recs, _ = taldau_dims.fetch_regional(ds)
    by = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("TOTAL", "2024-12-01")] == 50293 and by[("TOTAL", "2025-01-01")] == 51548
    assert ("67,576,1450", "741880,741935,9", "741880", "7") in calls            # EXTRA under its own measure
    assert ("4843,576,1450", "77397431,741935,3768282", "77397431", "1") in calls
    assert ("67,1450", "741880,9", "741880", "7") in calls and not any(c[1] == "741880,3768282" for c in calls)


def test_sector_accounts_parser():
    from fetchers import bns_dims
    head = ["S11", "S12", "S13", "S14", "S15", "S1", "S2", None, None, None] + ["S11", "S12", "S13", "S14", "S15", "S1", "S2", None]

    def row(code, label, uses=None, res=None):
        return list(uses or [None] * 8) + [code, label] + list(res or [None] * 8)
    grid = [["title"] + [None] * 17, head,
            row("B6g", "Валовой располагаемый доход", [10, 2, 5, 100, 1, 118, None, 118]),
            row("B5g", "Валовой располагаемый доход", res=[10, 2, 5, 100, 1, 118, None, 118]),   # mislabelled opening line
            row("B5g", "Валовой национальный доход", res=[9, 9, 9, 9, 9, 45, None, 45]),
            row("B5g", "Валовой национальный доход", [11, 3, 6, 90, 1, 111, None, 111]),
            row("D8", "Корректировка", [None, 4, None, None, None, 4, None, 4], [None, None, None, 4, None, 4, None, 4]),
            row("B8g", "Валовое сбережение", [10, 1, 1, -10.4, 0, 1.6, None, 1.6])]
    ds = {"id": "SA", "element_id": 1, "min_years": 1,
          "accounts": [{"code": "B5g", "side": "uses", "label": "национальный", "name": "ВНД"},
                       {"code": "B6g", "side": "uses", "name": "РД"},
                       {"code": "D8", "side": "resources", "item": "D8_RECEIVED", "name": "D8"},
                       {"code": "B8g", "side": "uses", "name": "Сб"}]}
    recs = bns_dims.parse_sector_accounts({"Обложка": [[None]], "2024": grid}, ds)
    by = {r["item_code"]: r["value"] for r in recs}
    assert by["B5g.S14"] == 90 and by["B6g.S14"] == 100 and by["D8_RECEIVED.S14"] == 4 and "D8_RECEIVED.S12" not in by
    assert by["HH_SAVING_RATE"] == pytest.approx(-10.0) and recs[0]["date"] == "2024-12-31"


def test_social_standards_step_series():
    doc = yaml.safe_load((REPO / "config" / "social_standards.yaml").read_text(encoding="utf-8"))
    recs = manual_vintages.step_records(doc, {"id": "S", "file": "x"}, today="2026-11-10")
    v = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert v[("MZP", "2018-12-01")] == 28284 and v[("MZP", "2019-01-01")] == 42500 and v[("MZP", "2021-12-01")] == 42500
    assert v[("MRP", "2022-03-01")] == 3063 and v[("MRP", "2022-04-01")] == 3180 and v[("MRP", "2026-11-01")] == 4325
    assert ("MIN_PENSION", "2010-12-01") not in v and ("MRP", "2026-12-01") not in v
    for item in doc["items"]:
        keys = list(item["values"])
        assert keys == sorted(keys), item["code"]


def test_block_b_bns_datasets_configured():
    import update_dims
    for ds_id in ("SUBSISTENCE_MINIMUM_BY_REGION", "SOCIAL_STANDARDS", "ENTERPRISE_PROFIT_LOSS_QUARTERLY", "ENTERPRISE_LOSS_MAKING_SHARE_QUARTERLY",
                  "INFORMAL_EMPLOYMENT_SHARE", "UNPRODUCTIVE_SELF_EMPLOYED_SHARE", "NET_LENDING_BY_SECTOR", "SECTOR_ACCOUNTS",
                  "LIVESTOCK_STOCK_MONTHLY", "LIVESTOCK_PRODUCTION_MONTHLY", "FUEL_PRICES_BY_CITY", "SOVEREIGN_RATINGS", "QUASI_STATE_DEBT_ANNUAL"):
        ds = update_dims.DATASETS[ds_id]
        assert ds.get("fetcher", ds["agency"]) in update_dims.AGENCY_FETCHERS, ds_id
        assert ds["agency"] in update_dims.METHODOLOGY or ds["agency"] == "bns", ds_id
