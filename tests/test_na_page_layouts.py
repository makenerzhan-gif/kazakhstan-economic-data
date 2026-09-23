"""The layouts added for the rest of the national-accounts page: one sheet per year, year
blocks (three orientations), month rows, year-over-month columns, region blocks with month
columns, sector columns; and the month-label helpers."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import dims, validation  # noqa: E402
from fetchers import bns_dims  # noqa: E402
import update_dims  # noqa: E402

OKV = "okved_sections"


def test_month_helpers():
    assert [bns_dims.month_of(s) for s in ("Январь", "мая", "Декабрь", "год", None)] == [1, 5, 12, None, None]
    assert [bns_dims.month_ytd_of(s) for s in ("Январь", "Январь-февраль", "Январь- май", "Январь-декабрь", "Февраль", "год")] == [1, 2, 5, 12, None, None]
    assert bns_dims.month_period_of("ИФО, январь-март 2021 г. к январю-марту 2020 г.") == (2021, 3)
    assert bns_dims.month_period_of("ИФО, января 2022г. к январю 2021г.") == (2022, 1)
    assert bns_dims.month_period_of("ИФО, январь-декабрь 2025г. к январю-декабрю 2024г.") == (2025, 12)
    assert bns_dims.month_period_of("период к соответствующему периоду") is None
    assert bns_dims.YEAR_CELL.match("2010 год") and bns_dims.YEAR_CELL.match("2024г.") and not bns_dims.YEAR_CELL.match("2024 год =100")


def test_year_sheets_take_every_year_sheet_and_the_regions_below_the_header():
    sheets = {
        "Метаданные": [["x"]],
        "2024 год": [[111201, "Выпуск"], [None, None, None, "млн. тенге"],
                     ["код КАТО", None, "Всего", "Сельское, лесное и рыбное хозяйство", "Промышленность"],
                     [0, "Республика Казахстан", 300.0, 100.0, 200.0], [11, "Акмолинская", 30.0, 10.0, 20.0]],
        "2025 год ": [[111201, "Выпуск"], [None],
                      ["код КАТО", None, "Всего", "Сельское, лесное и рыбное хозяйство", "Промышленность"],
                      [0, "Республика Казахстан", 330.0, 110.0, 220.0], [11, "Акмолинская", "-", 11.0, 22.0]],
    }
    ds = {"id": "T", "element_id": 0, "layout": "year_sheets", "dictionary": OKV, "label_overrides": {"всего": "TOTAL"}, "regions": "all"}
    recs = bns_dims.parse_year_sheets(list(sheets.items()), dims.load_dictionary(OKV), ds)
    by = {(r["region"], r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("national", "TOTAL", "2024-12-31")] == 300.0 and by[("AKM", "A", "2025-12-31")] == 11.0 and by[("national", "IND", "2025-12-31")] == 220.0
    assert ("AKM", "TOTAL", "2025-12-31") not in by and len(recs) == 11


def test_year_blocks_regions_items_stop_at_the_next_year_marker():
    grid = [["код КАТО", None, "Всего", "Сельское, лесное и рыбное хозяйство"],
            ["2020 год"], [0.0, "Республика Казахстан", 20.0, 2.0], [11.0, "Акмолинская", 0.5, 0.1],
            ["2021 год"], [0.0, "Республика Казахстан", 19.0, 1.9], [11.0, "Акмолинская", 0.4, 0.1]]
    ds = {"id": "T", "element_id": 0, "layout": "year_blocks_regions_items", "dictionary": OKV, "label_overrides": {"всего": "TOTAL"}, "regions": "all"}
    recs = bns_dims.parse_year_blocks_regions_items(grid, dims.load_dictionary(OKV), ds)
    assert {(r["date"], r["region"], r["item_code"], r["value"]) for r in recs if r["item_code"] == "TOTAL"} == {
        ("2020-12-31", "national", "TOTAL", 20.0), ("2020-12-31", "AKM", "TOTAL", 0.5), ("2021-12-31", "national", "TOTAL", 19.0), ("2021-12-31", "AKM", "TOTAL", 0.4)}


def test_year_blocks_items_regions_read_the_year_from_the_block_title():
    grid = [["111219", "ВДС квазигосударственного сектора … за 2018 год"], [None, None, None, None, "млн. теңге"],
            ["ОКЭД", "Наименование", "Республика Казахстан", "город Нур-Султан", "Акмолинская область"],
            [None, "Производство товаров", 100.0, 10.0, 5.0], ["Секция А (01-03)", "Сельское, лесное и рыбное хозяйство", 20.0, 0.0, 3.0],
            [None], ["111219", "ВДС квазигосударственного сектора … за 2019 год"], [None],
            ["ОКЭД", "Наименование", "Республика Казахстан", "город Нур-Султан", "Акмолинская область"],
            [None, "Производство товаров", 110.0, 11.0, 6.0]]
    ds = {"id": "T", "element_id": 0, "layout": "year_blocks_items_regions", "year_in_title": "111219", "dictionary": OKV, "regions": "all"}
    recs = bns_dims.parse_year_blocks_items_regions(grid, dims.load_dictionary(OKV), ds)
    by = {(r["date"], r["region"], r["item_code"]): r["value"] for r in recs}
    assert by[("2018-12-31", "AST", "GOODS")] == 10.0 and by[("2018-12-31", "AKM", "A")] == 3.0 and by[("2019-12-31", "national", "GOODS")] == 110.0
    assert len(recs) == 9


def test_year_blocks_items_regions_ytd_and_a_last_block_that_stops_early():
    def block(year, subs):
        return [[year], [None, "Акмолинская", None, None, None, "Карагандиская"], ["ОКЭД (ГК РК 03-2007)"] + subs + subs,
                ["Итого по отраслям", 1.0, 2.0, 3.0, 4.0, 10.0, 20.0, 30.0, 40.0], ["Сельское, лесное и рыбное хозяйство", 0.1, 0.2, 0.3, 0.4, 1.0, 2.0, 3.0, 4.0]]
    full = ["1 квартал", "1 полугодие", "9 месяцев", "год"]
    grid = block(2024, full) + [[None]] + block(2025, ["1 квартал", "1 квартал", "1 квартал", "1 квартал"])
    ds = {"id": "T", "element_id": 0, "layout": "year_blocks_items_regions_ytd", "dictionary": OKV, "regions": "all"}
    recs = bns_dims.parse_year_blocks_items_regions_ytd(grid, dims.load_dictionary(OKV), ds)
    by = {(r["date"], r["region"], r["item_code"]): r["value"] for r in recs}
    assert by[("2024-01-01", "AKM", "TOTAL")] == 1.0 and by[("2024-10-01", "KRG", "A")] == 4.0 and by[("2025-01-01", "KRG", "TOTAL")] == 10.0
    assert ("2025-04-01", "AKM", "TOTAL") not in by and len(recs) == 16 + 4
    grid2 = block(2024, ["1 квартал", "1 квартал", "1 квартал", "1 квартал"]) + [[None]] + block(2025, full)
    with pytest.raises(validation.StructuralChangeError):
        bns_dims.parse_year_blocks_items_regions_ytd(grid2, dims.load_dictionary(OKV), ds)


def test_month_rows_take_the_year_from_the_marker_row():
    grid = [[None, "Период", "за месяц", "нарастающим", "ИФО"], [None, None, "2021 г."], [None, "Январь", 10.0, 10.0, 94.2], [None, "Февраль", 11.0, 21.0, 96.0],
            [None, "2022г."], [None, "Январь", 12.0, 12.0, 103.0]]
    ds = {"id": "T", "element_id": 0, "layout": "month_rows", "columns": {"TOTAL": 3}, "item_names": {"TOTAL": "КЭИ"}}
    recs = bns_dims.parse_month_rows(grid, ds)
    assert [(r["date"], r["value"]) for r in recs] == [("2021-01-01", 10.0), ("2021-02-01", 21.0), ("2022-01-01", 12.0)]
    assert recs[0]["item_name"] == "КЭИ" and recs[0]["region"] == "national"


def test_year_months_read_twelve_year_to_date_sub_columns_per_year():
    subs = ["Январь", "Январь-февраль", "Январь-март", "Январь-апрель", "Январь-май", "Январь-июнь", "Январь-июль", "Январь-август", "Январь-сентябрь", "Январь-октябрь", "Январь-ноябрь", "Январь-декабрь"]
    grid = [["код КАТО", None, "2021 г."] + [None] * 11 + ["2022 г."], [None, None] + subs + ["Январь", "Январь-февраль"],
            [0, "Республика Казахстан"] + [100.0 + i for i in range(12)] + [200.0, 201.0], [11, "Акмолинская"] + [50.0 + i for i in range(12)] + [None, 61.0]]
    ds = {"id": "T", "element_id": 0, "layout": "year_months", "label_col": 1, "row_dimension": "region", "fixed_item": "TOTAL", "regions": "all"}
    recs = bns_dims.parse_year_quarters(grid, None, ds)
    by = {(r["date"], r["region"]): r["value"] for r in recs}
    assert by[("2021-01-01", "national")] == 100.0 and by[("2021-12-01", "national")] == 111.0 and by[("2022-02-01", "AKM")] == 61.0
    assert ("2022-01-01", "AKM") not in by and len(recs) == 12 + 2 + 12 + 1


def test_region_blocks_months_take_the_period_from_each_column_label():
    grid = [[None, 111201021], [None, None, "Индекс"], [0, "Республика Казахстан"], [None],
            [None, "период к соответствующему периоду", "ИФО, январь 2021 г. к январю 2020г.", "ИФО, январь-февраль 2021 г. к январю-февралю 2020 г.", "ИФО, январь 2022г. к январю 2021г."] + ["x"] * 0,
            [None, "Сельское, лесное и рыбное хозяйство", 102.5, 103.1, 99.0], [None, "Связь", 110.0, 111.0, 112.0], [None, "Индекс краткосрочного экономического индикатора", 94.2, 96.0, 103.0],
            [None], [10, "область Абай"], [None], [None, "период к соответствующему периоду", "ИФО, январь 2021 г. к январю 2020г.", "ИФО, январь-февраль 2021 г. к январю-февралю 2020 г.", "ИФО, январь 2022г. к январю 2021г."],
            [None, "Индекс краткосрочного экономического индикатора", "-", "-", 104.0]]
    ds = {"id": "T", "element_id": 0, "layout": "region_blocks_months", "dictionary": "kei_activities", "regions": "all"}
    # the header needs at least six period labels in the real file; the fixture lowers nothing, so pad the header rows
    for row in (grid[4], grid[11]):
        row += ["ИФО, январь-март 2022 г. к январю-марту 2021 г.", "ИФО, январь-апрель 2022 г. к январю-апрелю 2021 г.", "ИФО, январь-май 2022 г. к январю-маю 2021 г."]
    grid[5] += [98.0, 97.0, 96.0]
    recs = bns_dims.parse_region_blocks_months(grid, dims.load_dictionary("kei_activities"), ds)
    by = {(r["date"], r["region"], r["item_code"]): r["value"] for r in recs}
    assert by[("2021-02-01", "national", "A")] == 103.1 and by[("2022-01-01", "national", "COMMUNICATIONS")] == 112.0 and by[("2022-05-01", "national", "A")] == 96.0
    assert by[("2022-01-01", "ABY", "TOTAL")] == 104.0 and ("2021-01-01", "ABY", "TOTAL") not in by


def test_sector_columns_pick_one_measure_under_every_sector():
    grid = [[None, "Производство и образование доходов"], [None, None, "S11", None, None, None, None, None, None, "S1"],
            [None, None, "Сектор нефинансовых корпораций", None, None, None, None, None, None, "Экономика в целом"],
            [None, None, "Выпуск в основных ценах", "Промежуточное потребление", "Валовая добавленная стоимость", "в том числе:", None, None, None, "Выпуск в основных ценах", "Промежуточное потребление", "Валовая добавленная стоимость", "в том числе:"],
            [None, None, None, None, None, "оплата труда", "другие налоги на производство", "потребление основного капитала", "чистая прибыль", None, None, None, "оплата труда", "другие налоги", "потребление основного капитала", "чистая прибыль"],
            [None, "Сельское, лесное и рыбное хозяйство"], [None, 2010, 648.0, 315.0, 333.0, 80.0, 0.4, 30.0, 221.0, 1964.0, 980.0, 983.0, 229.0, 1.0, 110.0, 643.0],
            [None, 2011, 748.0, 332.0, 415.0, 92.0, 0.4, 59.0, 263.0, 2100.0, 1000.0, 1100.0, 240.0, 1.1, 120.0, 700.0],
            [None, "Валовой внутренний продукт"], [None, 2010, None, None, None, None, None, None, None, 21815.0, None, None, None, None, None, None],
            [None, "Ответственный исполнители: кто-то, тел: 1"]]
    d = dims.load_dictionary(OKV)
    out = bns_dims.parse_sector_columns(grid, d, {"id": "T", "element_id": 0, "layout": "sector_columns", "measure": "OUTPUT", "dictionary": OKV})
    comp = bns_dims.parse_sector_columns(grid, d, {"id": "T", "element_id": 0, "layout": "sector_columns", "measure": "COMPENSATION", "dictionary": OKV})
    assert {(r["item_code"], r["date"], r["value"]) for r in out} == {("A_S11", "2010-12-31", 648.0), ("A_S11", "2011-12-31", 748.0), ("A_S1", "2010-12-31", 1964.0), ("A_S1", "2011-12-31", 2100.0), ("GDP_S1", "2010-12-31", 21815.0)}
    assert {(r["item_code"], r["date"], r["value"]) for r in comp if r["date"] == "2010-12-31"} == {("A_S11", "2010-12-31", 80.0), ("A_S1", "2010-12-31", 229.0)}
    assert out[0]["item_name"].endswith("— S11") or "S11" in out[0]["item_name"]


def test_every_second_batch_dataset_names_its_source_table():
    ids = [d["id"] for d in update_dims.DATASETS.values() if d.get("element_id") in (81477, 81478, 286855, 4449, 4450, 5933, 5934, 4445, 5941, 5942, 5943, 5923, 410224, 5932, 75044)]
    assert len(ids) == 35
    for d in (update_dims.DATASETS[i] for i in ids):
        assert d["note"] and d["unit"] and d["frequency"] in ("annual", "quarterly", "monthly"), d["id"]
        if "year-to-date" in d["unit"] or d.get("cumulation"):
            assert d.get("transformation"), d["id"]
