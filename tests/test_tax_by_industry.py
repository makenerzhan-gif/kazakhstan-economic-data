"""Taxes by economic activity (scripts/fetchers/tax_by_industry.py, added 2026-11-13)."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import tax_by_industry  # noqa: E402
from lib import dims, validation  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DS = {"id": "ENVIRONMENTAL_TAXES_BY_OKED", "agency": "bns"}
YEARS = ["Виды экономической деятельности", "2016", "2017", "2018", "2019", "2020"]


def _sheet(mining, manufacturing, other, total):
    return [[None] * 6, [None, "title"], YEARS,
            ["Горнодобывающая промышленность и разработка карьеров"] + mining,
            ["Обрабатывающая промышленность"] + manufacturing,
            ["Прочие плательщики налогов"] + other, ["Всего"] + total]


def _grids(total_sheet=None):
    one = _sheet(["10", "10", "10", "10", "10"], ["5", "5", "5", "5", "-"], [1, 1, 1, 1, 1], ["16", "16", "16", "16", "11"])
    zero = _sheet([0] * 5, [0] * 5, [0] * 5, [0] * 5)
    return {"Метаданные": [["x"]], "Налоги на энергоносители": one, "Транспортные налоги": zero, "Налоги на загрязнение окр среды": zero,
            "Налоги на исп-е ресурсов": zero, "Экологические налоги (всего)": total_sheet or one}


def test_env_taxes_sections_add_up_to_the_total():
    recs = tax_by_industry.env_tax_records(_grids(), DS)
    by = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("TOTAL.B", "2016-12-31")] == 0.01 and by[("ENERGY.ALL", "2020-12-31")] == 0.011       # thousand -> million KZT
    assert by[("ENERGY.C", "2020-12-31")] == 0.0 and ("TOTAL.OTHER_PAYERS", "2018-12-31") in by       # «-» = none
    for year in ("2016", "2020"):
        parts = sum(v for (c, d), v in by.items() if c.startswith("TOTAL.") and c != "TOTAL.ALL" and d.startswith(year))
        assert parts == pytest.approx(by[("TOTAL.ALL", f"{year}-12-31")], rel=1e-3)


def test_env_taxes_identity_violations_stop_the_dataset():
    bad = _sheet(["10"] * 5, ["5"] * 5, [1] * 5, ["16", "16", "16", "16", "20"])           # sections 16, «Всего» 20
    with pytest.raises(validation.StructuralChangeError, match="sum to"):
        tax_by_industry.env_tax_records({**_grids(), "Налоги на энергоносители": bad}, DS)
    other_total = _sheet(["12"] * 5, ["5"] * 5, [1] * 5, ["18"] * 5)                      # consistent sheet, but not the groups' sum
    with pytest.raises(validation.StructuralChangeError, match="four tax groups"):
        tax_by_industry.env_tax_records(_grids(total_sheet=other_total), DS)
    unknown = _sheet(["10"] * 5, ["5"] * 5, [1] * 5, ["16"] * 5)
    unknown[3][0] = "Добыча сырой нефти"                                                  # a division, not a section
    with pytest.raises(validation.StructuralChangeError, match="not an ОКЭД section"):
        tax_by_industry.env_tax_records({**_grids(), "Транспортные налоги": unknown}, DS)
    grids = _grids()
    del grids["Налоги на исп-е ресурсов"]
    with pytest.raises(validation.StructuralChangeError, match="RESOURCE"):
        tax_by_industry.env_tax_records(grids, DS)


def test_industry_structure_records_and_checks():
    ds = {"id": "TAX_STRUCTURE_BY_INDUSTRY", "agency": "vap"}
    doc = {"shares": {2024: {"MINING": 34.2, "MANUFACTURING": 10.7, "CONSTRUCTION": 5.2, "TRADE": 18.2, "TRANSPORT": 5.1, "OTHER": 26.6},
                      2017: {"MINING": 40.9, "MANUFACTURING": 10.7, "CONSTRUCTION": 6.3, "TRADE": 13.5, "TRANSPORT": 3.5, "OTHER": 25.1}},
           "published_total_bn": {2024: 23509.5}}
    recs = tax_by_industry.structure_records(doc, ds, {2024: 19700516.9}, {2024: 3808971.5})
    by = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("CONSOLIDATED_TAX", "2024-12-31")] == pytest.approx(23509.488) and by[("MINING.SHARE", "2017-12-31")] == 40.9
    assert by[("MINING.RECEIPTS", "2024-12-31")] == pytest.approx(0.342 * 23509.488, abs=0.06)
    assert ("MINING.RECEIPTS", "2017-12-31") not in by                       # no National Fund series before 2018
    with pytest.raises(validation.StructuralChangeError, match="Chamber prints"):
        tax_by_industry.structure_records(doc, ds, {2024: 19000000.0}, {2024: 3808971.5})
    doc["shares"][2024]["OTHER"] = 30.0
    with pytest.raises(validation.StructuralChangeError, match="shares sum"):
        tax_by_industry.structure_records(doc, ds, {}, {})


def test_structure_yaml_and_registration():
    import update_dims
    doc = yaml.safe_load((REPO / "config" / "tax_structure_by_industry.yaml").read_text(encoding="utf-8"))
    assert sorted(doc["shares"]) == list(range(2017, 2026))
    for year, shares in doc["shares"].items():
        assert set(shares) == set(tax_by_industry.GROUPS) and abs(sum(shares.values()) - 100) <= 0.11, year
    for ds_id, fetcher in (("ENVIRONMENTAL_TAXES_BY_OKED", "bns_env_taxes"), ("TAX_STRUCTURE_BY_INDUSTRY", "tax_industry_structure")):
        assert update_dims.DATASETS[ds_id]["fetcher"] == fetcher and fetcher in update_dims.AGENCY_FETCHERS
    sources = (REPO / "config" / "sources.yaml").read_text(encoding="utf-8")
    assert "TAX_RECEIPTS_BY_OKED (scope note):" in sources                   # the negative result is on record


def test_processed_env_taxes_sections_equal_the_total():
    """The identity on the stored data: 19 sections + other payers = «Всего» within 0.1 %, every group and year."""
    rows = dims.load_processed("ENVIRONMENTAL_TAXES_BY_OKED")
    if not rows:
        pytest.skip("processed file absent")
    by = {}
    for r in rows:
        group, code = r["item_code"].split(".", 1)
        by.setdefault((group, r["date"]), {})[code] = float(r["value"])
    assert len(by) >= 5 * 10
    for (group, when), vals in by.items():
        parts = sum(v for c, v in vals.items() if c != "ALL")
        assert parts == pytest.approx(vals["ALL"], rel=1e-3, abs=0.01), (group, when)
        assert "B" in vals and len(vals) == 21, (group, when)


@pytest.mark.cross_source
def test_consolidated_tax_equals_the_chamber_totals():
    rows = dims.load_processed("TAX_STRUCTURE_BY_INDUSTRY")
    if not rows:
        pytest.skip("processed file absent")
    by = {(r["item_code"], r["date"]): float(r["value"]) for r in rows}
    published = {d: v for (c, d), v in by.items() if c == "CONSOLIDATED_TAX.PUBLISHED"}
    assert len(published) >= 3
    for when, value in published.items():
        assert by[("CONSOLIDATED_TAX", when)] == pytest.approx(value, abs=0.5), when


# ---------------------------------------------------------------- statutory rates (TAX_RATES)

def test_tax_rates_step_series_and_gaps():
    import yaml
    from fetchers import manual_vintages
    root = Path(__file__).resolve().parents[1]
    doc = yaml.safe_load((root / "config" / "tax_rates.yaml").read_text(encoding="utf-8"))
    records = manual_vintages.step_records(doc, {"id": "TAX_RATES"}, today="2026-11-13")
    by = {(r["item_code"], r["date"][:7]): r["value"] for r in records}
    assert by[("VAT", "2008-12")] == 13 and by[("VAT", "2009-01")] == 12 and by[("VAT", "2025-12")] == 12 and by[("VAT", "2026-01")] == 16
    assert by[("SOCIAL_TAX", "2017-12")] == 11 and by[("SOCIAL_TAX", "2018-01")] == 9.5 and by[("SOCIAL_TAX", "2026-11")] == 6
    assert by[("PENSION_EMPLOYER", "2026-03")] == 3.5 and by[("HEALTH_EMPLOYER", "2021-12")] == 2 and by[("SOCIAL_CONTRIBUTIONS", "2024-12")] == 3.5
    assert by[("CIT", "2008-12")] == 30 and by[("CIT", "2009-06")] == 20 and by[("VAT", "1995-07")] == 20
    assert by[("SOCIAL_TAX", "2003-12")] == 21 and by[("SOCIAL_TAX", "2005-01")] == 20 and by[("SOCIAL_TAX", "2008-06")] == 13
    assert by[("PIT_TOP", "2003-12")] == 30 and by[("PIT_DIVIDENDS", "2019-01")] == 5 and by[("MET_COPPER", "2020-01")] == 5.7
    assert by[("MET_COAL", "2020-12")] == 0 and by[("MET_COAL", "2021-01")] == 2.7 and by[("EXCISE_PETROL", "2015-12")] == 10500
    assert by[("OIL_EXPORT_DUTY_RATE", "2009-02")] == 0 and by[("OIL_EXPORT_DUTY_RATE", "2011-01")] == 40
    for gap in (("MET_URANIUM", "2026-01"), ("MET_GOLD", "2026-01"), ("OIL_EXPORT_DUTY_RATE", "2016-03"), ("EXCISE_DIESEL", "2020-01")):
        assert gap not in by                                   # no single rate in these months: absent, not carried
    assert all(v is not None for v in by.values())
    import update_dims
    ds = update_dims.DATASETS["TAX_RATES"]
    assert ds["fetcher"] == "manual_table" and ds["step"] == "monthly" and len(doc["items"]) >= ds["min_items"]
