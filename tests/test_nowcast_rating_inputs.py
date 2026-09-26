"""Nowcasting and rating inputs (2026-09-25): monthly state-budget taxes from every
bulletin layout, the external debt service schedule, IO tables."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import minfin, nbk_dims  # noqa: E402
from lib import validation  # noqa: E402


def _sheet(header, sub, tax_row):
    return [["3-кесте", None], ["(млн.теңге)", None], header, sub, ["1", "2"],
            ["I. КІРІСТЕР"] + [1.0] * (len(header) - 1), tax_row,
            ["  корпоративтік табыс салығы"] + [0.5] * (len(header) - 1)]


def test_current_layout_reads_the_ytd_and_prior_year_columns():
    header = ["Атауы", "2024 ж. есеп/ 2024 г. отчет", "2025 ж. есеп/ 2025 г. отчет", None,
              "2026 ж. қантар-шілде есеп/январь-июль отчет", "Наименование"]
    sub = [None, None, "жылдық/ годовой", "қантар-шілде/январь-июль", None, None]
    got = minfin.parse_bulletin_state_taxes(_sheet(header, sub, ["  Салықтық түсімдер_x000D_\n оның", 19700516.9,
                                                                  23188178.6, 12073505.0, 14111863.6, "Налоговые"]))
    assert got["STATE_TAX_REVENUE_YTD"] == {(2024, 12): 19700516.9, (2025, 12): 23188178.6,
                                            (2025, 7): 12073505.0, (2026, 7): 14111863.6}
    assert set(got["STATE_CIT_YTD"]) == {(2024, 12), (2025, 12), (2025, 7), (2026, 7)}


def test_quarterly_layout_is_cumulated_to_year_to_date():
    header = ["Атауы", "2019 ж. есеп/ 2019 г. отчет", "2020 ж. есеп/ 2020 г. Отчет", None, None, None, "Наименование"]
    sub = [None, None, "1-тоқсан/\n1 квартал", "2-тоқсан/\n2 квартал", "3-тоқсан/\n3 квартал", "4-тоқсан/\n4 квартал", None]
    got = minfin.parse_bulletin_state_taxes(_sheet(header, sub, ["   Салықтық түсiмдері, оның iшiнде:", 9216474.3,
                                                                  2104480.7, 1665565.4, 1992457.9, 2798699.0, None]))
    v = got["STATE_TAX_REVENUE_YTD"]
    assert v[(2019, 12)] == 9216474.3 and v[(2020, 3)] == 2104480.7
    assert v[(2020, 6)] == pytest.approx(2104480.7 + 1665565.4)
    assert v[(2020, 12)] == pytest.approx(8561203.0)


def test_january_only_column():
    header = ["Атауы", "2025 ж. есеп/ 2025 г. отчет", None, "2026 ж. қантар есеп/январь отчет"]
    sub = [None, "жылдық/ годовой", "қантар/январь", None]
    got = minfin.parse_bulletin_state_taxes(_sheet(header, sub, ["Салықтық түсімдер", 5.0, 1.0, 2.0]))
    assert got["STATE_TAX_REVENUE_YTD"] == {(2025, 12): 5.0, (2025, 1): 1.0, (2026, 1): 2.0}


def test_debt_schedule_items_and_unknown_rows():
    rows = [{"report_date": "2026-04-01", "amount": 10.0, "repayment_type": "Principal (forecast)",
             "repayment_period": "within 1-3 months", "economy_sector_type": "General government"},
            {"report_date": "2026-04-01", "amount": 2.0, "repayment_type": "Interests  (forecast)",
             "repayment_period": "after 2 years", "economy_sector_type": "Banks"},
            {"report_date": "2026-04-01", "amount": 3.0, "repayment_period": "on demand",
             "memo_items": "Repayment of external debt in the form of goods (forecast) "}]
    codes = [r["item_code"] for r in nbk_dims.debt_schedule_records(rows)]
    assert codes == ["GG_PRINCIPAL_M01_03", "BANKS_INTEREST_AFTER_2Y", "MEMO_GOODS_ON_DEMAND"]
    with pytest.raises(validation.StructuralChangeError):
        nbk_dims.debt_schedule_records([{**rows[0], "repayment_period": "within 25-27 months"}])


def test_io_reference_tables_exist_with_leontief_check():
    import csv
    path = Path(__file__).resolve().parents[1] / "data" / "reference" / "io" / "editions.csv"
    with path.open(encoding="utf-8") as f:
        eds = list(csv.DictReader(f))
    sym = [e for e in eds if e["kind"] == "io_symmetric"]
    assert {int(e["year"]) for e in sym} >= {2021, 2022, 2023, 2024}
    assert all(e["check"].startswith("max|L-(I-A)^-1|=") and float(e["check"].split("=")[1]) < 1e-8 for e in sym)
