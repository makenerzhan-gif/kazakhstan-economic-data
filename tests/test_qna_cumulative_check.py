"""The quarterly national-accounts files carry a cumulative twin of every discrete sheet;
the twin is re-read on every run and any point where it is not the running sum of the
stored discrete quarters is reported as a warning (the discrete values are kept)."""
import io
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import bns_dims  # noqa: E402

DS = {"id": "QNA_TEST", "element_id": 0, "layout": "year_quarters", "dictionary": "okved_sections", "label_col": 1,
      "sheets": ["1"], "cumulative_check": "1.1"}


def _workbook(cumulative_gdp_year):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "1"
    ws.append(["Валовая добавленная стоимость, млн. тенге"])
    ws.append(["ОКЭД", "наименование ОКЭД", 2024, None, None, None, 2025])
    ws.append([None, None, "I квартал", "II квартал", "III квартал", "IV квартал", "I квартал"])
    ws.append([None, "Производство товаров", 10.0, 20.0, 30.0, 40.0, 11.0])
    ws.append([None, "Валовой внутренний продукт", 100.0, 200.0, 300.0, 400.0, 110.0])
    ws2 = wb.create_sheet("1.1")
    ws2.append(["Валовая добавленная стоимость, млн. тенге"])
    ws2.append(["ОКЭД", "наименование ОКЭД", 2024, None, None, None, 2025])
    ws2.append([None, None, "I квартал", "I полугодие", "9 месяцев", "год", "I квартал"])
    ws2.append([None, "Производство товаров", 10.0, 30.0, 60.0, 100.0, 11.0])
    ws2.append([None, "Валовой внутренний продукт", 100.0, 300.0, 600.0, cumulative_gdp_year, 110.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_a_consistent_twin_gives_no_warning():
    content = _workbook(1000.0)
    records = bns_dims.parse(content, DS)
    assert len(records) == 10
    assert bns_dims.cumulative_check(content, DS, records) == []


def test_an_unreadable_twin_is_a_warning_not_a_stop():
    content = _workbook(1000.0)
    records = bns_dims.parse(content, DS)
    warnings = bns_dims.cumulative_check(content, {**DS, "cumulative_check": "1"}, records)   # the discrete sheet read as cumulative
    assert len(warnings) == 1 and "could not be read" in warnings[0] and "no year row" in warnings[0]


def test_a_twin_that_is_not_the_running_sum_is_reported_and_the_discrete_values_are_kept():
    content = _workbook(950.0)
    records = bns_dims.parse(content, DS)
    warnings = bns_dims.cumulative_check(content, DS, records)
    assert len(warnings) == 1 and "1 of 10 points" in warnings[0] and "GDP@national 2024-10-01" in warnings[0]
    assert "950.0" in warnings[0] and "1000.0" in warnings[0]
    assert {r["value"] for r in records if r["item_code"] == "GDP"} == {100.0, 200.0, 300.0, 400.0, 110.0}
