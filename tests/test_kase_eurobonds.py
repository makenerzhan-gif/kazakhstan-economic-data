"""Sovereign Eurobond yields and spreads from KASE valuations (fetchers/kase_eurobonds.py)."""
import io
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import kase_eurobonds as K  # noqa: E402


def _xlsx(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=name, header=False, index=False)
    return buf.getvalue()


def test_ytm_reproduces_kase():
    # KASE 25.09.2026: 2045 bond clean 104.002 -> 6.14 %, 2044 bond clean 87.666 -> 6.00 %
    assert K.ytm_from_clean(104.002, date(2026, 9, 29), date(2045, 7, 21), 6.5) == pytest.approx(6.14, abs=0.01)
    assert K.ytm_from_clean(87.666, date(2026, 9, 29), date(2044, 10, 14), 4.875) == pytest.approx(6.00, abs=0.01)


def test_parse_current_layout():
    head = ["№ п/п", "Торговый код", "ISIN", "Вид ценной бумаги", "Краткое наименование эмитента", "Расчетная цена",
            "Расчетная грязная", "Доходность до погашения, % годовых", "Дней до погашения", "Единица измерения цены"]
    rows = [["Дата оценки"], [None], [None], head,
            [658, "KZ_06_4410", "XS1120709826", "Облигации", "Министерство финансов РК", 87.666, "89,8462", "6", 6499, "Чистая цена в %"],
            [1, "KZTK", "KZ1C00000876", "Акции", "Казахтелеком", 30000, None, None, None, "тенге"],
            [1062, "QA_02_3004", "XS2155352664", "Облигации", "Катар", 94.673, 96.33, 5.42, 1281, "Чистая цена в %"]]
    got = K.parse_workbook(_xlsx({"Расчетные цены_ФР": rows}))
    assert set(got) == {"XS1120709826"}
    assert got["XS1120709826"] == {"code": "KZ_06_4410", "clean": 87.666, "dirty": 89.8462, "ytm": 6.0, "days": 6499.0, "kind": ""}


def test_parse_2020_layout_with_blank_yield_and_market_over_indicative():
    head = ["№ п/п", "НИН", "Торговый код", "Дней до погашения", "Доходность до погашения, % годовых",
            "Рыночная цена, в % к номинальной стоимости", None, None, "Цена прошлого периода", "Ставка купона, %"]
    sub = [None, None, None, None, None, 'без дисконта, "чистая"', 'без дисконта, "грязная"', None, None, None]
    rows = [["2020-03-31"], ["Еврооблигации МФ РК"], head, sub,
            [2, "XS1120709826", "KZ_06_4410", 8834, None, 113.56, 115.8079, 110.0175, 115.61, 4.875]]
    got = K.parse_workbook(_xlsx({"Еврооблигации МФ РК": rows}))["XS1120709826"]
    assert (got["clean"], got["dirty"], got["ytm"]) == (113.56, 115.8079, None)


def test_treasury_interpolation():
    curve = {10: {"2026-09-25": 4.0}, 20: {"2026-09-25": 4.5}, 30: {"2026-09-25": 4.6}}
    assert K.treasury_yield(date(2026, 9, 27), 15, curve) == pytest.approx(4.25)      # weekend -> Friday
    assert K.treasury_yield(date(2026, 9, 25), 35, curve) == 4.6
    assert K.treasury_yield(date(2026, 9, 25), 8, curve) == 4.0


def test_benchmark_windows_leave_the_low_quality_period_out():
    assert K._benchmark("2020-10-01") == "XS1120709826"
    assert K._benchmark("2021-06-01") is None and K._benchmark("2022-07-01") is None
    assert K._benchmark("2022-08-01") == "XS1263139856"
