"""World Bank (Pink Sheet, CMO forecasts) and EIA (STEO) fetchers — parsed from grids
shaped like the live files of 2026-09-14/15; no network."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import dims, validation  # noqa: E402
from fetchers import eia, wb  # noqa: E402
import update_dims  # noqa: E402
import update_wb  # noqa: E402

PRICES = {"id": "T", "sheet": "Annual Prices (Nominal)", "dictionary": "wb_commodities", "region": "world"}
INDICES = {"id": "T", "sheet": "Annual Indices (Nominal)", "dictionary": "wb_commodity_indices", "region": "world"}


def test_english_normaliser_keeps_latin_letters_and_drops_footnotes():
    assert dims.normalise_label_en("Non-energy **") == "non-energy"
    assert dims.normalise_label_en("Base Metals 4/") == "base metals"
    assert dims.normalise_label_en("World Bank \nCommodity \nPrice Index") == "world bank commodity price index"
    assert dims.normalise_label("Energy") != "energy"          # the Cyrillic normaliser is the wrong tool here


@pytest.mark.parametrize("label, code", [
    ("Coal, Australian", "COAL_AUS"), ("Coal, Australia", "COAL_AUS"), ("Coal, South African **", "COAL_SAFRICA"),
    ("Crude oil, Brent", "CRUDE_BRENT"), ("Natural gas, US", "NGAS_US"), ("Natural gas, U.S.", "NGAS_US"),
    ("Liquefied natural gas, Japan", "NGAS_JP"), ("Tea, avg 3 auctions", "TEA_AVG"), ("Tea, average", "TEA_AVG"),
    ("Rice, Thai 5%", "RICE_05"), ("Rice, Thailand, 5%", "RICE_05"), ("Rice, Thai 25%", "RICE_25"),
    ("Wheat, US HRW", "WHEAT_US_HRW"), ("Wheat, U.S., HRW", "WHEAT_US_HRW"), ("Banana, US", "BANANA_US"), ("Bananas, U.S.", "BANANA_US"),
    ("Orange", "ORANGE"), ("Oranges", "ORANGE"), ("Shrimps, Mexican", "SHRIMP_MEX"), ("Shrimp", "SHRIMP_MEX"),
    ("Sugar, world", "SUGAR_WLD"), ("Sugar, World", "SUGAR_WLD"), ("Sugar, US", "SUGAR_US"), ("Sugar, EU", "SUGAR_EU"),
    ("Tobacco, US import u.v.", "TOBAC_US"), ("Tobacco", "TOBAC_US"), ("Logs, Cameroon", "LOGS_CMR"), ("Logs, Africa", "LOGS_CMR"),
    ("Logs, Malaysian", "LOGS_MYS"), ("Logs, S.E. Asia", "LOGS_MYS"), ("Sawnwood, Malaysian", "SAWNWD_MYS"), ("Sawnwood, S.E. Asia", "SAWNWD_MYS"),
    ("Cotton, A Index", "COTTON_A_INDX"), ("Cotton", "COTTON_A_INDX"), ("Rubber, TSR20 **", "RUBBER_TSR20"), ("Rubber, RSS3", "RUBBER1_MYSG"),
    ("Urea", "UREA_EE_BULK"), ("Urea, E. Europe", "UREA_EE_BULK"), ("Iron ore, cfr spot", "IRON_ORE"), ("Iron ore", "IRON_ORE"),
    ("Aluminum ", "ALUMINUM"), ("Tin", "TIN"), ("Lead", "LEAD"), ("Rapeseed oil", "RAPESEED_OIL"), ("Palm kernel oil", "PLMKRNL_OIL"),
    ("Palm oil", "PALM_OIL"), ("Soybeans", "SOYBEANS"), ("Soybean oil", "SOYBEAN_OIL"), ("Groundnuts", "GRNUT"), ("Groundnut oil **", "GRNUT_OIL"),
    ("Something new", None),
])
def test_pink_sheet_and_cmo_labels_resolve_to_one_code(label, code):
    got = dims.match_item(label, dims.load_dictionary("wb_commodities"), dims.normalise_label_en)
    assert (got[0] if got else None) == code


@pytest.mark.parametrize("label, code", [
    ("World Bank \nCommodity \nPrice Index", "TOTAL"), ("Total Index", "TOTAL"), ("Total 1/", "TOTAL"),
    ("Energy", "ENERGY"), ("Energy 2/", "ENERGY"), ("Non-energy **", "NON_ENERGY"), ("Non-Energy", "NON_ENERGY"),
    ("Oils & Meals", "OILS_MEALS"), ("Oils and Meals", "OILS_MEALS"), ("Other Raw Mat.", "OTHER_RAW_MATERIALS"), ("Other Raw Materials", "OTHER_RAW_MATERIALS"),
    ("Metals  & Minerals", "METALS_MINERALS"), ("Metals and Minerals", "METALS_MINERALS"),
    ("Base Metals (ex. iron ore)", "BASE_METALS"), ("Base Metals 4/", "BASE_METALS"), ("Precious Metals 5/", "PRECIOUS_METALS"), ("Food **", "FOOD"),
])
def test_index_labels_of_both_files_resolve(label, code):
    assert dims.match_item(label, dims.load_dictionary("wb_commodity_indices"), dims.normalise_label_en)[0] == code


def test_wb_dictionaries_are_unambiguous_on_their_own_names():
    for name in ("wb_commodities", "wb_commodity_indices"):
        d = dims.load_dictionary(name)
        assert len({e["code"] for e in d}) == len(d)
        for e in d:
            assert dims.match_item(e["name_en"], d, dims.normalise_label_en) == (e["code"], e["name_ru"]), e["code"]


def test_parse_prices_reads_names_units_and_year_rows():
    grid = [
        ["World Bank Commodity Price Data", None, None, None],
        ["Updated on September 02, 2026", None, None, None],
        [None, "Crude oil, Brent", "Coal, Australian", "Gold"],
        [None, "($/bbl)", "($/mt)", "($/troy oz)"],
        [2024, 80.7, 136.1, 2388],
        [2025, 69.0, "…", 3442],
    ]
    recs = wb.parse_prices(grid, PRICES)
    assert {(r["date"], r["item_code"], r["value"], r["region"]) for r in recs} == {
        ("2024-12-31", "CRUDE_BRENT", 80.7, "world"), ("2025-12-31", "CRUDE_BRENT", 69.0, "world"),
        ("2024-12-31", "COAL_AUS", 136.1, "world"), ("2024-12-31", "GOLD", 2388.0, "world"), ("2025-12-31", "GOLD", 3442.0, "world")}
    assert wb.release_note(grid) == "September 02, 2026"


def test_parse_prices_monthly_rows_are_dated_the_first_of_the_month():
    grid = [[None, "Crude oil, Brent"], [None, "($/bbl)"], ["2026M07", 86.4], ["2026M08", 90.9]]
    assert [(r["date"], r["value"]) for r in wb.parse_prices(grid, {**PRICES, "sheet": "Monthly Prices"})] == [("2026-07-01", 86.4), ("2026-08-01", 90.9)]


def test_parse_prices_stops_on_a_new_series_or_a_changed_unit():
    base = [[None, "Crude oil, Brent", "Helium"], [None, "($/bbl)", "($/mt)"], [2025, 69.0, 1.0]]
    with pytest.raises(validation.StructuralChangeError) as exc:
        wb.parse_prices(base, PRICES)
    assert "Helium" in str(exc.value)
    changed = [[None, "Crude oil, Brent"], [None, "($/mt)"], [2025, 69.0]]
    with pytest.raises(validation.StructuralChangeError) as exc:
        wb.parse_prices(changed, PRICES)
    assert "unit of CRUDE_BRENT" in str(exc.value)


def test_parse_indices_takes_each_column_name_from_its_header_row():
    grid = [
        ["Updated on September 02, 2026", None, None, None, None],
        [None, "World Bank \nCommodity \nPrice Index", "Energy", "Non-energy", None],
        [None, None, None, None, "Agriculture"],
        [None, None, None, " ", " "],
        [2025, 98.4, 90.0, 115.4, 115.7],
    ]
    recs = wb.parse_indices(grid, INDICES)
    assert {(r["item_code"], r["value"]) for r in recs} == {("TOTAL", 98.4), ("ENERGY", 90.0), ("NON_ENERGY", 115.4), ("AGRICULTURE", 115.7)}


FORECAST = [
    ["TABLE 1. World Bank Commodity Price Forecasts", None, None, None, None, None, None, None, None, None],
    [None] * 10,
    [None] * 6 + [None, None, "Percent change", None],
    ["Commodity", None, "Unit", "2024", "2025", "2026f", "2027f", None, "2026f", "2027f"],
    [None] * 10,
    ["INDEXES (in nominal US dollars, 2010=100)"] + [None] * 9,
    ["Total 1/", None, None, 105.1, 98.4, 113.7, 99.8, None, 15.5, -12.3],
    ["Energy 2/", None, None, 101.5, 90.0, 111.3, 92.1, None, 23.6, -17.2],
    [None, "Agriculture", None, 115.0, 115.7, 109.3, 110.0, None, -5.6, 0.6],       # sub-groups are indented into column B
    ["PRICES (in nominal US dollars)"] + [None] * 9,
    ["Energy"] + [None] * 9,
    ["Crude oil, Brent", None, "$/bbl", 80.7, 69.0, 86.0, 70.0, None, 24.6, -18.6],
    [None, "Barley", "$/mt", "…", "…", 172.0, 174.0, None, "...", 1.2],
    ["Notes: 1/ The World Bank …"] + [None] * 9,
]


def test_parse_forecasts_takes_only_the_f_columns_of_the_requested_section():
    prices = wb.parse_forecasts(FORECAST, {**PRICES, "section": "prices"})
    assert {(r["date"], r["item_code"], r["value"], r["transformation"]) for r in prices} == {
        ("2026-12-31", "CRUDE_BRENT", 86.0, "forecast"), ("2027-12-31", "CRUDE_BRENT", 70.0, "forecast"),
        ("2026-12-31", "BARLEY", 172.0, "forecast"), ("2027-12-31", "BARLEY", 174.0, "forecast")}
    indices = wb.parse_forecasts(FORECAST, {**INDICES, "section": "indices"})
    assert {(r["item_code"], r["value"]) for r in indices} == {("TOTAL", 113.7), ("TOTAL", 99.8), ("ENERGY", 111.3), ("ENERGY", 92.1),
                                                               ("AGRICULTURE", 109.3), ("AGRICULTURE", 110.0)}


def test_parse_forecasts_stops_on_an_unknown_price_row():
    grid = [row[:] for row in FORECAST]
    grid.insert(12, ["Lithium carbonate", None, "$/mt", 10.0, 11.0, 12.0, 13.0, None, 1.0, 1.0])
    with pytest.raises(validation.StructuralChangeError) as exc:
        wb.parse_forecasts(grid, {**PRICES, "section": "prices"})
    assert "Lithium carbonate" in str(exc.value)


def test_cmo_page_links_are_discovered_and_the_forecast_xlsx_sits_beside_the_pdf():
    html = ('<a href="https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Annual.xlsx">Annual</a>'
            '<a href="https://thedocs.worldbank.org/en/doc/f3138644a1e8e2bb631399ae11d6c408-0050012026/related/CMO-April-2026-Forecasts.pdf">Forecasts</a>'
            '<a href="https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Pink-Sheet-September-2026.pdf">Pink</a>')
    links = wb.discover_links(html)
    assert set(links) == {"CMO-Historical-Data-Annual.xlsx", "CMO-April-2026-Forecasts.pdf", "CMO-Pink-Sheet-September-2026.pdf"}
    pdf = next(u for n, u in links.items() if wb.FORECAST_PDF.match(n))
    assert pdf.endswith("/related/CMO-April-2026-Forecasts.pdf")


def test_current_url_falls_back_when_the_page_cannot_be_read(monkeypatch):
    monkeypatch.setattr(wb.bns, "_download", lambda url: (_ for _ in ()).throw(ConnectionError("offline")))
    assert wb.current_url("annual", "https://example.org/fallback.xlsx") == ("https://example.org/fallback.xlsx", False)


STEO_DATES = [["Forecast Month -", None, None, "September 2026"], ["Modeling and analysis completion - ", "2026-09-03"],
              ["Table Beginning Year--- ", 2022], [], ["Last Historical Month--- ", None, None, 202608.0]]
STEO_TABLE = [
    ["Table of Contents", "Table 2.  Energy Prices"] + [None] * 24,
    [None] * 26,
    ["Forecast date:", None, 2026] + [None] * 11 + [2027] + [None] * 11,
    ["Thursday, September 3, 2026", None] + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] * 2,
    [None, "Crude Oil (dollars per barrel)"] + [None] * 24,
    ["WTIPUUS", "West Texas Intermediate Spot Average"] + [60.0] * 24,
    ["BREPUUS", "Brent Spot Average"] + [80.0] * 8 + [90.0] * 4 + [70.0] * 12,
]
EIA_DS = {"id": "EIA_STEO_PRICES", "sheet": "2tab", "items": {"BREPUUS": "Brent", "WTIPUUS": "WTI"}, "region": "world"}


def test_eia_dates_and_table_mark_months_after_the_last_historical_month_as_forecast():
    release, last = eia.read_dates(STEO_DATES, EIA_DS)
    assert (release, last) == ("September 2026", 202608)
    recs = eia.parse_table(STEO_TABLE, EIA_DS, last)
    brent = [r for r in recs if r["item_code"] == "BREPUUS"]
    assert len(brent) == 24 and brent[0]["date"] == "2026-01-01" and brent[-1]["date"] == "2027-12-01"
    assert {r["transformation"] for r in brent if r["date"] <= "2026-08-01"} == {"level"}
    assert {r["transformation"] for r in brent if r["date"] > "2026-08-01"} == {"forecast"}
    assert sum(r["value"] for r in brent if r["date"][:4] == "2026") / 12 == pytest.approx((80 * 8 + 90 * 4) / 12)


def test_eia_missing_series_id_is_a_structural_change():
    with pytest.raises(validation.StructuralChangeError) as exc:
        eia.parse_table(STEO_TABLE, {**EIA_DS, "items": {"BREPUUS": "Brent", "NGHHUUS": "Henry Hub"}}, 202608)
    assert "NGHHUUS" in str(exc.value)


def test_processed_writer_keeps_a_record_level_transformation(tmp_path, monkeypatch):
    monkeypatch.setattr(dims, "PROCESSED_ROOT", tmp_path)
    recs = [{"date": "2026-08-01", "region": "world", "item_code": "BREPUUS", "item_name": "Brent", "value": 90.9},
            {"date": "2026-09-01", "region": "world", "item_code": "BREPUUS", "item_name": "Brent", "value": 87.0, "transformation": "forecast"}]
    dims.write_processed("T", recs)
    assert [(r["transformation"], r["region"]) for r in dims.load_processed("T")] == [("level", "world"), ("forecast", "world")]


def test_world_datasets_are_registered_with_their_agencies():
    for ds_id, agency in (("WB_COMMODITY_PRICES_ANNUAL", "wb"), ("WB_COMMODITY_PRICE_FORECASTS", "wb"), ("EIA_STEO_PRICES", "eia")):
        assert update_dims.DATASETS[ds_id]["agency"] == agency and update_dims.DATASETS[ds_id]["country"] == "WLD"
    assert set(update_wb.FETCHERS) == set(update_wb.INDICATOR_IDS) == {"OIL_PRICE_BRENT"}
