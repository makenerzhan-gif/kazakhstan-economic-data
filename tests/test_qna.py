"""The quarterly national accounts (discrete quarters): the year_quarters layout of the
tables 283162/283161/283160/471384 and the QNA_* dataset configuration."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import dims, validation  # noqa: E402
from fetchers import bns_dims  # noqa: E402
import update_dims  # noqa: E402

DS = {"id": "TEST", "element_id": 0, "layout": "year_quarters", "dictionary": "okved_sections", "label_col": 1}


def test_year_cells_and_year_to_date_labels_are_recognised():
    assert [bool(bns_dims.YEAR_CELL.match(s)) for s in ("2010", " 2025 ", "20253)", "2025 3)", "2010.0", "2146592.05", "год", "")] == \
        [True, True, True, True, True, False, False, False]
    assert [bns_dims.ytd_of(s) for s in ("I квартал", "1 квартал", "I кв.", "I полугодие", "9 месяцев", "год", "Январь - Март ", "Январь - Июнь", "Январь - Сентябрь", "II квартал", None)] == \
        [1, 1, 1, 2, 3, 4, 1, 2, 3, None, None]
    assert [bns_dims.quarter_of(s) for s in ("I кв.", "IV кв", "II квартал", "I полугодие")] == [1, 4, 2, None]


def _grid(sub_labels):
    return [
        ["Валовая добавленная стоимость по отраслям экономики в текущих ценах, млн. тенге", None, None, None, None, None, None, None, None, None],
        ["ОКЭД", "наименование ОКЭД", 2024, None, None, None, "20253)", None, None, None],
        [None, None, *sub_labels, *sub_labels],
        [None, "Производство товаров", 10.0, 20.0, 30.0, 40.0, 11.0, "-", None, None],
        ["Секция А (01-03)", "Сельское, лесное и рыбное хозяйство", 1.0, 2.0, 3.0, 4.0, 1.5, 2.5, None, None],
        [None, "Валовой внутренний продукт", 100.0, 200.0, 300.0, 400.0, 110.0, 210.0, None, None],
        ["1) Расчет предварительный", None, None, None, None, None, None, None, None, None],
    ]


def test_year_quarters_reads_discrete_quarters_dated_at_quarter_start():
    d = dims.load_dictionary("okved_sections")
    recs = bns_dims.parse_year_quarters(_grid(["I квартал", "II квартал", "III квартал", "IV квартал"]), d, DS)
    by = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("GOODS", "2024-01-01")] == 10.0 and by[("GOODS", "2024-10-01")] == 40.0 and by[("GOODS", "2025-01-01")] == 11.0
    assert ("GOODS", "2025-04-01") not in by                       # "-" is a missing value, not zero
    assert by[("A", "2025-04-01")] == 2.5 and by[("GDP", "2024-07-01")] == 300.0
    assert len(recs) == 5 + 6 + 6 and all(r["region"] == "national" for r in recs)


def test_year_quarters_cumulative_sheets_use_the_year_to_date_labels():
    d = dims.load_dictionary("okved_sections")
    recs = bns_dims.parse_year_quarters(_grid(["I квартал", "I полугодие", "9 месяцев", "год"]), d, {**DS, "cumulative": True})
    assert {(r["item_code"], r["date"], r["value"]) for r in recs if r["item_code"] == "GDP"} == {
        ("GDP", "2024-01-01", 100.0), ("GDP", "2024-04-01", 200.0), ("GDP", "2024-07-01", 300.0), ("GDP", "2024-10-01", 400.0),
        ("GDP", "2025-01-01", 110.0), ("GDP", "2025-04-01", 210.0)}
    with pytest.raises(validation.StructuralChangeError):                # a discrete sheet read as cumulative is a structural mismatch
        bns_dims.parse_year_quarters(_grid(["I квартал", "II квартал", "III квартал", "IV квартал"]), d, {**DS, "cumulative": True})


def test_year_quarters_stops_on_a_mislabelled_sub_column_and_on_an_unknown_row():
    d = dims.load_dictionary("okved_sections")
    with pytest.raises(validation.StructuralChangeError) as exc:
        bns_dims.parse_year_quarters(_grid(["I квартал", "II квартал", "9 месяцев", "IV квартал"]), d, DS)
    assert "sub-column 3" in str(exc.value)
    grid = _grid(["I квартал", "II квартал", "III квартал", "IV квартал"])
    grid[4][1] = "Новая строка БНС"
    with pytest.raises(validation.StructuralChangeError) as exc:
        bns_dims.parse_year_quarters(grid, d, DS)
    assert "Новая строка БНС" in str(exc.value)


def test_year_quarters_region_blocks_start_on_a_data_row_and_fold_city_names():
    grid = [
        ["КАТО", "ОКЭД", "Наименование ОКЭД", 2024, None, None, None],
        [None, None, None, "I квартал", "II квартал", "III квартал", "IV квартал"],
        ["Республика Казахстан", "Секция А (01-03)", "Сельское, лесное и рыбное хозяйство", 1.0, 2.0, 3.0, 4.0],
        [None, None, "Валовой внутренний продукт", 10.0, 20.0, 30.0, 40.0],
        ["город Астана", "Секция А (01-03)", "Сельское, лесное и рыбное хозяйство", 0.1, 0.2, 0.3, 0.4],
        [None, None, "Валовой региональный продукт", 5.0, 6.0, 7.0, 8.0],
        ["Область Абай", "Секция А (01-03)", "Сельское, лесное и рыбное хозяйство", 0.5, 0.6, 0.7, 0.8],
    ]
    ds = {**DS, "label_col": 2, "region_col": 0, "regions": "all"}
    recs = bns_dims.parse_year_quarters(grid, dims.load_dictionary("okved_sections"), ds)
    by = {(r["region"], r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("national", "A", "2024-01-01")] == 1.0 and by[("national", "GDP", "2024-10-01")] == 40.0
    assert by[("AST", "GDP", "2024-04-01")] == 6.0 and by[("ABY", "A", "2024-10-01")] == 0.8
    assert {r["region"] for r in recs} == {"national", "AST", "ABY"}
    national_only = bns_dims.parse_year_quarters(grid, dims.load_dictionary("okved_sections"), {**ds, "regions": "national"})
    assert {r["region"] for r in national_only} == {"national"}
    grid[4][0] = "город Неизвестный"
    with pytest.raises(validation.StructuralChangeError):
        bns_dims.parse_year_quarters(grid, dims.load_dictionary("okved_sections"), ds)


def test_year_quarters_components_take_one_component_row_under_each_activity():
    grid = [
        ["Образование доходов по видам экономической деятельности", None, None, None, None],
        [None, 2024, None, None, None],
        [None, "I квартал", "II квартал", "III квартал", "IV квартал"],
        ["Производство товаров", None, None, None, None],
        ["Валовая добавленная стоимость", 100.0, 110.0, 120.0, 130.0],
        ["Оплата труда", 40.0, 41.0, 42.0, 43.0],
        ["Другие чистые налоги на производство", 1.0, 1.1, 1.2, 1.3],
        ["Валовая прибыль/валовой смешанный доход", 59.0, 67.9, 76.8, 85.7],
        ["Итого по видам экономической деятельности", None, None, None, None],
        ["Валовая добавленная стоимость", 100.0, 110.0, 120.0, 130.0],
        ["Оплата труда", 40.0, 41.0, 42.0, 43.0],
        ["Чистые налоги на продукты", 5.0, 5.0, 5.0, 5.0],
        ["Валовой внутренний продукт", 105.0, 115.0, 125.0, 135.0],
    ]
    ds = {**DS, "label_col": 0, "components": {"GVA": "^валовая добавленная стоимость", "COMPENSATION": "^оплата труда",
                                                "OTHER_NET_TAXES": "^другие чистые налоги", "GROSS_PROFIT": "^валовая прибыль"},
          "component": "COMPENSATION", "skip_rows": ["^чистые налоги на продукты", "^валовой внутренний продукт"]}
    recs = bns_dims.parse_year_quarters(grid, dims.load_dictionary("okved_sections"), ds)
    assert {(r["item_code"], r["date"], r["value"]) for r in recs} == {
        ("GOODS", "2024-01-01", 40.0), ("GOODS", "2024-04-01", 41.0), ("GOODS", "2024-07-01", 42.0), ("GOODS", "2024-10-01", 43.0),
        ("TOTAL", "2024-01-01", 40.0), ("TOTAL", "2024-04-01", 41.0), ("TOTAL", "2024-07-01", 42.0), ("TOTAL", "2024-10-01", 43.0)}
    assert [r["item_name"] for r in recs][0] == "Производство товаров"
    grid[11][0] = "Неизвестная компонента"
    with pytest.raises(validation.StructuralChangeError) as exc:
        bns_dims.parse_year_quarters(grid, dims.load_dictionary("okved_sections"), ds)
    assert "Неизвестная компонента" in str(exc.value)


def test_expenditure_dictionary_tells_gdp_by_production_from_gdp():
    d = dims.load_dictionary("expenditure_items")
    assert dims.match_item("Валовой внутренний продукт2)", d)[0] == "GDP"
    assert dims.match_item("Валовой внутренний продукт методом конечного использования", d)[0] == "GDP"
    assert dims.match_item("Валовой внутренний продукт методом производства", d)[0] == "GDP_PRODUCTION"


def test_every_qna_dataset_is_configured_consistently():
    qna = [d for d in update_dims.DATASETS.values() if d["id"].startswith("QNA_")]
    assert len(qna) == 19
    for d in qna:
        assert d["layout"] == "year_quarters" and d["frequency"] == "quarterly" and d["agency"] == "bns", d["id"]
        assert d["element_id"] in (283162, 283161, 283160, 471384) and len(d["sheets"]) == 1, d["id"]
        assert "2010-2022" in d["vintage"] and "vintage" in d["transformation"], d["id"]
        assert d["id"].endswith("_YTD") == bool(d.get("cumulative")), d["id"]
        if d.get("component"):
            assert d["component"] in d["components"] and d["skip_rows"], d["id"]
        if d.get("region_col") is not None:
            assert d["regions"] == "all" and d["min_regions"] >= 20, d["id"]
