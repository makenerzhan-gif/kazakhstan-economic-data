"""Scalar indicators derived from the item-level layer, and the two de-duplication
mechanisms that came with them: one download per process, one raw copy per day."""
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import raw_store  # noqa: E402
from fetchers import bns, nbk  # noqa: E402
import update_bns  # noqa: E402
import update_derived  # noqa: E402
import update_dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

DIMS_ROWS = [
    {"date": "2024-12-31", "region": "national", "item_code": "TOTAL", "item_name": "всего", "value": "9214.184", "transformation": "level"},
    {"date": "2025-12-31", "region": "national", "item_code": "TOTAL", "item_name": "всего", "value": "9320.639", "transformation": "level"},
    {"date": "2025-12-31", "region": "AKM", "item_code": "TOTAL", "item_name": "всего", "value": "400.0", "transformation": "level"},
    {"date": "2025-12-31", "region": "national", "item_code": "MEN", "item_name": "мужчины", "value": "4800.0", "transformation": "level"},
    {"date": "2023-12-31", "region": "national", "item_code": "TOTAL", "item_name": "всего", "value": "", "transformation": "level"},
]


def test_derive_filters_item_and_region_and_scales_units():
    ind = {"id": "EMPLOYED_TOTAL", "frequency": "annual", "derived_from": {"dataset": "X", "item": "TOTAL", "region": "national", "scale": 1000}}
    assert [(r["date"], r["value"]) for r in update_derived.derive(ind, DIMS_ROWS)] == [("2024-12-31", 9214184.0), ("2025-12-31", 9320639.0)]


def test_every_derived_indicator_points_at_a_real_dataset_and_has_no_fetcher_of_its_own():
    dims_ids = set(update_dims.DATASETS)
    derived = update_derived.derived_indicators()
    assert {i["id"] for i in derived} == {"IND_PROD", "IND_PROD_MINING", "IND_PROD_MANUFACTURING", "IND_PROD_ELECTRICITY", "INVESTMENT",
                                          "EXPORTS", "OIL_EXPORTS_VALUE", "OIL_EXPORTS_VOLUME", "POPULATION_BNS", "EMPLOYED_TOTAL", "ELECTRICITY_PRODUCTION",
                                          "GDP_NOMINAL"}
    for i in derived:
        spec = i["derived_from"]
        assert spec["dataset"] in dims_ids, i["id"]
        assert i["id"] not in update_bns.FETCHERS and i["id"] not in update_bns.INDICATOR_IDS, f"{i['id']} is derived AND fetched"
        assert not i.get("lifecycle"), f"{i['id']}: a derived series is live, the lifecycle flag belonged to the retired fetcher"


def test_scalar_ids_are_either_fetched_or_derived_never_both_and_never_neither():
    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    import update_ardfm, update_imf, update_kase, update_minfin, update_nbk, update_wb
    fetched = set()
    for m in (update_bns, update_nbk, update_minfin, update_imf, update_ardfm, update_wb, update_kase):
        fetched |= set(m.FETCHERS)
    derived = {i["id"] for i in indicators if i.get("derived_from")}
    assert not fetched & derived
    for i in indicators:
        assert i["id"] in fetched or i["id"] in derived, f"{i['id']} has neither a fetcher nor a derivation"


def test_raw_store_keeps_identical_bytes_once_across_indicators_and_days(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_store, "RAW_ROOT", tmp_path)
    today, tomorrow = date(2026, 9, 15), date(2026, 9, 16)
    first = raw_store.save_raw_bytes("bns", "EXPORTS", today, "xlsx", b"same bytes")
    twin = raw_store.save_raw_bytes("bns", "OIL_EXPORTS_VALUE", today, "xlsx", b"same bytes")
    other = raw_store.save_raw_bytes("bns", "IMPORTS", today, "xlsx", b"different bytes")
    next_day = raw_store.save_raw_bytes("bns", "EXPORTS", tomorrow, "xlsx", b"same bytes")        # source unchanged overnight
    revised = raw_store.save_raw_bytes("bns", "EXPORTS", tomorrow, "xlsx", b"revised bytes")      # source republished
    assert twin == first and next_day == first and other != first and revised.name == "bns_exports_2026-09-16.xlsx"
    assert sorted(p.name for p in (tmp_path / "bns").iterdir()) == ["bns_exports_2026-09-15.xlsx", "bns_exports_2026-09-16.xlsx", "bns_imports_2026-09-15.xlsx"]
    again = raw_store.save_raw_bytes("bns", "EXPORTS", today, "xlsx", b"same bytes")      # idempotent re-run
    assert again == first and len(list((tmp_path / "bns").iterdir())) == 3


def test_downloads_are_made_once_per_process(monkeypatch):
    calls = []

    class Resp:
        content = b"payload"
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    # both modules share the one `requests` module, so one recorder serves both
    monkeypatch.setattr(bns.requests, "get", lambda url, **kw: calls.append((url, kw.get("params"))) or Resp())
    bns._DOWNLOAD_CACHE.clear()
    nbk._DOWNLOAD_CACHE.clear()
    assert bns._download("https://example.org/a") == b"payload" and bns._download("https://example.org/a") == b"payload"
    nbk._download("https://example.org/form", {"formId": 51})
    nbk._download("https://example.org/form", {"formId": 51})
    nbk._download("https://example.org/form", {"formId": 34})
    assert calls == [("https://example.org/a", None), ("https://example.org/form", {"formId": 51}), ("https://example.org/form", {"formId": 34})]
    bns._DOWNLOAD_CACHE.clear()
    nbk._DOWNLOAD_CACHE.clear()


def test_gaps_are_filled_only_from_a_series_that_agrees_on_every_shared_year():
    ind = {"id": "GFCF", "gaps_filled_from": {"dataset": "GDP_EXPENDITURE_NOMINAL", "item": "GFCF", "region": "national", "scale": 1000000}}
    dims_rows = [{"date": f"{y}-12-31", "region": "national", "item_code": "GFCF", "item_name": "", "value": str(v), "transformation": "level"}
                 for y, v in ((2009, 4726718.7), (2010, 5307136.6), (2014, 8552487.1))]
    own = [{"date": "2009-12-31", "value": "4726718700000.0"}, {"date": "2014-12-31", "value": "8552487100000.0"}]
    merged, added = update_derived.fill_gaps(ind, own, dims_rows)
    assert added == 1 and [r["date"] for r in merged] == ["2009-12-31", "2010-12-31", "2014-12-31"]
    own[0]["value"] = "4700000000000.0"
    with pytest.raises(Exception):
        update_derived.fill_gaps(ind, own, dims_rows)


def test_expenditure_components_cover_2010_to_2013():
    for ind in update_derived.gap_filled_indicators():
        path = REPO_ROOT / "data" / "processed" / ind["agency"] / f"{ind['id'].lower()}.csv"
        years = {line.split(",")[0][:4] for line in path.read_text(encoding="utf-8").splitlines()[1:]}
        assert {"2010", "2011", "2012", "2013"} <= years, ind["id"]
