"""Quarterly siblings of the annual item-level datasets: the year-to-date columns and rows
of the national-accounts tables (`periods: quarterly_ytd`) and the discrete quarter
sub-columns of the employment table 5831 (`periods: quarterly_subcolumns`)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import dims, validation  # noqa: E402
from fetchers import bns_dims  # noqa: E402
import update_dims  # noqa: E402

DS = {"id": "TEST", "element_id": 0, "dictionary": "okved_sections", "periods": "quarterly_ytd"}


@pytest.mark.parametrize("label, expected", [
    ("1 квартал 2010г.", (2010, 1)), ("I квартал     2012 года", (2012, 1)), ("1 квартал 2026г.7)", (2026, 1)),
    ("І квартал 2019 года", (2019, 1)),                                   # a Cyrillic І, not a Latin I
    ("1 полугодие 2010г.", (2010, 2)), ("1 полугодие 2026г.*", (2026, 2)), ("I полугодие 2018 года", (2018, 2)),
    ("1 полугодие 2023 года 2)", (2023, 2)),
    ("9 месяцев 2010г.", (2010, 3)), ("9 месяц 2012г.", (2012, 3)), ("9 месяцев 2019 года**", (2019, 3)),
    ("2010 год", (2010, 4)), (" 2025 год7)8)", (2025, 4)), ("2021 год 2)", (2021, 4)),
    ("Республика Казахстан", None), ("Акмолинская", None), ("ОКЭД", None), ("2024", None), (2024.0, None), (None, None),
])
def test_period_of_reads_every_label_shape_seen_in_the_bns_files(label, expected):
    assert bns_dims.period_of(label) == expected


def test_quarter_of_reads_bare_roman_quarters():
    assert [bns_dims.quarter_of(s) for s in ("I  квартал ", "II квартал", "III квартал", "IV квартал ", "год", None)] == [1, 2, 3, 4, None, None]


def test_periods_across_quarterly_ytd_dates_periods_at_quarter_start_and_keeps_the_year_as_q4():
    grid = [
        ["ОКЭД", "9 месяцев 2023г.", "2023 год", "1 квартал 2024г.", "1 полугодие 2024г.", "9 месяцев 2024г.", "2024 год", "1 квартал 2025г.", "1 полугодие 2025г.*"],
        ["Сельское, лесное и рыбное хозяйство", 900.0, 950.0, 100.0, 250.0, 700.0, 1000.0, 110.0, "-"],
        ["1) Расчет предварительный", None, None, None, None, None, None, None, None],
    ]
    d = dims.load_dictionary("okved_sections")
    recs = bns_dims.parse_periods_across(grid, d, 0, DS)
    assert [(r["date"], r["value"]) for r in recs] == [
        ("2023-07-01", 900.0), ("2023-10-01", 950.0),
        ("2024-01-01", 100.0), ("2024-04-01", 250.0), ("2024-07-01", 700.0), ("2024-10-01", 1000.0), ("2025-01-01", 110.0)]
    annual = bns_dims.parse_periods_across(grid, d, 0, {**DS, "periods": None})
    assert [(r["date"], r["value"]) for r in annual] == [("2023-12-31", 950.0), ("2024-12-31", 1000.0)]


def test_years_from_drops_the_earlier_columns():
    grid = [["код КАТО", "Наименование", "2010 год", "9 месяцев 2011 года", "2011 год", "I квартал 2012 года"],
            ["0", "Республика Казахстан", 107.3, 107.0, 107.4, 105.6]]
    ds = {**DS, "dictionary": None, "row_dimension": "region", "fixed_item": "GDP", "years_from": 2011}
    recs = bns_dims.parse_periods_across(grid, None, 1, ds)
    assert [(r["date"], r["region"], r["value"]) for r in recs] == [
        ("2011-07-01", "national", 107.0), ("2011-10-01", "national", 107.4), ("2012-01-01", "national", 105.6)]


def test_region_blocks_quarterly_ytd_reads_every_period_row():
    grid = [
        ["код КАТО", "Наименование регионов", "Промышленность- всего", "Горнодобывающая промышленность", "Добыча угля"],
        [None, None, None, "B", 5],
        ["0", "Республика Казахстан", None, None, None],
        [None, "9 месяцев 2024 года", 100.0, 60.0, 5.0],
        [None, "2024 год", 130.0, 80.0, 7.5],
        [None, "I квартал 2025 года", 30.0, 20.0, 2.0],
        ["11", "Акмолинская", None, None, None],
        [None, "2024 год", 9.0, 5.0, 1.0],
    ]
    recs = bns_dims.parse_region_blocks(grid, {**DS, "dictionary": "from_table"})
    assert {(r["date"], r["item_code"], r["value"]) for r in recs} == {
        ("2024-07-01", "IND", 100.0), ("2024-07-01", "B", 60.0), ("2024-07-01", "05", 5.0),
        ("2024-10-01", "IND", 130.0), ("2024-10-01", "B", 80.0), ("2024-10-01", "05", 7.5),
        ("2025-01-01", "IND", 30.0), ("2025-01-01", "B", 20.0), ("2025-01-01", "05", 2.0)}
    assert all(r["region"] == "national" for r in recs)


def test_year_subcolumns_quarterly_subcolumns_reads_four_discrete_quarters_and_checks_their_labels():
    grid = [
        [None, "2024 год", None, None, None, None, "2025 год", None, None, None, None],
        [None, "I  квартал ", "II квартал ", "III квартал", "IV квартал ", "год", "I квартал", "II квартал", "III квартал", "IV квартал", "год"],
        ["Строительство", 600.0, 640.0, 660.0, 620.0, 630.0, 610.0, 650.0, None, None, None],
    ]
    d = dims.load_dictionary("okved_sections")
    ds = {**DS, "periods": "quarterly_subcolumns"}
    recs = bns_dims.parse_year_subcolumns(grid, d, 0, 0, ds)
    assert [(r["date"], r["value"]) for r in recs] == [
        ("2024-01-01", 600.0), ("2024-04-01", 640.0), ("2024-07-01", 660.0), ("2024-10-01", 620.0), ("2025-01-01", 610.0), ("2025-04-01", 650.0)]
    annual = bns_dims.parse_year_subcolumns(grid, d, 0, 4, {**DS, "periods": None})
    assert [(r["date"], r["value"]) for r in annual] == [("2024-12-31", 630.0)]
    grid[1][3] = "9 месяцев"
    with pytest.raises(validation.StructuralChangeError) as exc:
        bns_dims.parse_year_subcolumns(grid, d, 0, 0, ds)
    assert "III квартал" in str(exc.value)


def test_validate_with_year_to_date_cumulation_compares_own_period_contributions():
    rows = [{"date": d, "region": "national", "item_code": "A", "item_name": "a", "value": v} for d, v in
            [("2024-01-01", 100.0), ("2024-04-01", 200.0), ("2024-07-01", 300.0), ("2024-10-01", 400.0), ("2025-01-01", 105.0)]]
    assert dims.validate(rows, "T", "quarterly", cumulation="year_to_date").warnings == []
    assert any("jump" in w for w in dims.validate(rows, "T", "quarterly").warnings)   # the January reset, read as a level


def test_every_quarterly_dataset_mirrors_its_annual_sibling():
    quarterly = [d for d in update_dims.DATASETS.values() if d["id"].endswith("_QUARTERLY")]
    assert len(quarterly) == 14
    for q in quarterly:
        a = update_dims.DATASETS[q["id"][:-len("_QUARTERLY")]]
        assert q["frequency"] == "quarterly" and a["frequency"] == "annual", q["id"]
        assert q["periods"] in ("quarterly_ytd", "quarterly_subcolumns") and "periods" not in a, q["id"]
        for key in ("element_id", "layout", "dictionary", "sheets", "sheet_match", "label_col", "row_dimension", "fixed_item",
                    "label_overrides", "regions", "region", "min_items", "min_regions"):
            assert q.get(key) == a.get(key), (q["id"], key)
        assert q["transformation"] and q["unit"], q["id"]
        assert (q.get("cumulation") == "year_to_date") == ("year-to-date cumulative" in q["unit"]), q["id"]
