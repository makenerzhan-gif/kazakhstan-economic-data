"""Minfin bulletin table 22 (state debt structure): the section-anchored row lookup
picks row '1' / '2' of section I (Government / National Bank), never the identically
coded internal/external split of sections II-III, skips blank cells, and refuses a row
whose Russian label no longer matches. Also the табл 3 row '14. Обслуживание долга'."""
import io
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import minfin  # noqa: E402
from lib import validation  # noqa: E402


DATES = ["на 1 января 2021 года", "на 1 января 2022 года", "на 1 октября 2025 года",
         "на 1 января 2026 года"]


def _table22(nbk_label: str = "Долг Национального Банка Республики Казахстан") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "табл 22 кв"
    ws.append(["Таблица 22"])
    header = [None, "Наименование"]
    units = [None, None]
    for d in DATES:
        header += [d, None]
        units += ["млн.тенге", "млн.долл. США"]
    ws.append(header)
    ws.append(units)
    # Section I = 1 + 2 + 3 - 3.1 (the sheet nets out local debt owed to the Government).
    # Its first column carries both currencies at the sheet's rate 20,642,523 / 49,000.
    ws.append(["I.", "Государственный долг", 20642523.0, 49000.0, 21975570.0, 51000.0,
               35503740.0, 66000.0, 36444160.0, 70000.0])
    ws.append(["1", "Долг Правительства Республики Казахстан", 16658003.2, 39500.0, 18730000.0,
               43400.0, 33950000.0, 63100.0, 34850000.0, 67000.0])
    ws.append(["1.1", "внутренний:", 9760912.1, 23100.0, 11330000.0, 26200.0, 25220000.0,
               46900.0, 26150000.0, 50300.0])
    ws.append(["1.2", "внешний:", 6897091.1, 16400.0, 7400000.0, 17200.0, 8730000.0, 16200.0,
               8700000.0, 16700.0])
    # National Bank: first-column tenge cell BLANK with the USD cell filled (as in the real
    # 2020-01-01 column), zero for the third date, blank in both currencies for the last.
    ws.append(["2", nbk_label, None, 6949.0, 2100000.0, 4900.0, 0, 0, None, None])
    ws.append(["3", "Долг местных исполнительных органов", 1741971.7, 4140.6, 1874498.0,
               4300.0, 2543483.0, 4700.0, 2678711.0, 5100.0])
    ws.append(["3.1", "перед Правительством Республики Казахстан", 684728.9, 1627.6, 728928.0,
               1700.0, 989743.0, 1800.0, 1084551.0, 2100.0])
    ws.append(["3.2", "перед прочими кредиторами", 1057242.8, 2513.0, 1145570.0, 2600.0,
               1553740.0, 2900.0, 1594160.0, 3000.0])
    ws.append(["II.", "Гарантированный государством долг", 877205.6, 2085.1, 1172589.0,
               2700.0, 2424397.0, 4500.0, 2292984.0, 4400.0])
    ws.append(["1", "внутренний", 188910.9, 449.0, 300000.0, 700.0, 900000.0, 1700.0,
               800000.0, 1500.0])
    ws.append(["2", "внешний", 688294.7, 1636.0, 872589.0, 2000.0, 1524397.0, 2800.0,
               1492984.0, 2900.0])
    ws.append(["III.", "Долг по поручительствам государства", 28608.4, 68.0, 27000.0, 60.0,
               6000.0, 11.0, 6000.0, 12.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _patch(monkeypatch, content: bytes):
    docs = [{"id": 7, "title": "Statistical bulletin as of August 1, 2026",
             "full_text": [{"document": "/b.xlsx"}]}]
    monkeypatch.setattr(minfin, "_list_documents", lambda **kw: docs)
    monkeypatch.setattr(minfin, "_download", lambda path: content)
    monkeypatch.setattr(minfin.raw_store, "save_raw_bytes", lambda *a, **k: None)
    monkeypatch.setattr(minfin.raw_store, "write_download_manifest", lambda *a, **k: None)


def test_central_gov_debt_is_row_1_of_section_I_not_the_guarantee_split(monkeypatch):
    _patch(monkeypatch, _table22())
    recs, man = minfin.fetch_central_gov_debt()
    assert [r["date"] for r in recs] == ["2021-01-01", "2022-01-01", "2025-10-01", "2026-01-01"]
    assert recs[0]["value"] == 16658003.2 and recs[-1]["value"] == 34850000.0
    assert man["frequency"] == "quarterly" and "section=I.,row=1," in man["dataset_id"]
    # 1.1 + 1.2 = row 1 on the synthetic sheet, as on the real one
    assert abs(9760912.1 + 6897091.1 - recs[0]["value"]) < 0.01


def test_nbk_debt_converts_blank_tenge_cell_from_usd_skips_double_blank_keeps_zero(monkeypatch):
    _patch(monkeypatch, _table22())
    recs, man = minfin.fetch_nbk_debt()
    assert [r["date"] for r in recs] == ["2021-01-01", "2022-01-01", "2025-10-01"]
    # blank tenge, filled USD -> USD x (section I KZT / USD) = 6949 x 20642523 / 49000
    assert abs(recs[0]["value"] - 6949.0 * 20642523.0 / 49000.0) < 1e-6
    assert recs[1]["value"] == 2100000.0 and recs[2]["value"] == 0.0
    assert "2021-01-01" in man["note"] and "implied rate" in man["note"]
    # a row with every tenge cell filled gets no conversion note
    _, man_gov = minfin.fetch_central_gov_debt()
    assert "implied rate" not in man_gov["note"]


def test_central_gov_debt_external_is_row_1_2_in_tenge(monkeypatch):
    _patch(monkeypatch, _table22())
    recs, man = minfin.fetch_central_gov_debt_external()
    assert [(r["date"], r["value"]) for r in recs][:2] == [("2021-01-01", 6897091.1), ("2022-01-01", 7400000.0)]
    assert "row=1.2,currency=KZT" in man["dataset_id"]


def test_nbk_row_with_changed_label_raises(monkeypatch):
    _patch(monkeypatch, _table22(nbk_label="Прочие обязательства"))
    with pytest.raises(validation.StructuralChangeError) as exc:
        minfin.fetch_nbk_debt()
    assert "Национального Банка" in str(exc.value)


def test_section_identity_I_equals_gov_plus_nbk_plus_local_minus_3_1(monkeypatch):
    """Section I = Government + National Bank + local bodies - row 3.1 (local debt owed to
    the Government), i.e. section I is already consolidated -- the fetchers read the rows
    they claim to read, including the USD-converted NBK cell of the first column."""
    _patch(monkeypatch, _table22())
    total = minfin.fetch_state_debt_total()[0][0]["value"]
    gov = minfin.fetch_central_gov_debt()[0][0]["value"]
    nbk = minfin.fetch_nbk_debt()[0][0]["value"]
    loc = minfin.fetch_local_gov_debt()[0][0]["value"]
    owed_to_gov = 684728.9
    # NBK converted from USD: 6949 x 20642523 / 49000 = 2,927,529.7 (fixture rounding)
    assert abs(gov + nbk + loc - owed_to_gov - total) < 300.0
    # and exactly with the rounding-free tenge values of the second column
    second = lambda fn: fn()[0][1]["value"]  # noqa: E731
    assert abs(second(minfin.fetch_central_gov_debt) + second(minfin.fetch_nbk_debt)
               + second(minfin.fetch_local_gov_debt) - 728928.0
               - second(minfin.fetch_state_debt_total)) < 1e-3


def _table3() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "табл 3"
    ws.append(["Таблица 3"])
    ws.append(["Атауы", "2023 ж. есеп/ 2023 г. отчет", "2024 ж. есеп/ 2024 г. отчет",
               "2025 ж. есеп/ 2025 г. отчет", "2026 ж. қантар-шілде есеп/январь-июль отчет 2026 г.",
               None, "Наименование"])
    ws.append(["I. КІРІСТЕР", 24917246.14, 27132164.97, 29871047.82, 16361107.76, 17125393.59, "I. ДОХОДЫ"])
    ws.append(["   14. Борышқа  қызмет көрсету", 1865648.998, 2232329.183, 2660521.406, 2035215.45,
               2461812.69, "   14. Обслуживание долга"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_state_budget_debt_servicing_takes_only_the_annual_report_columns(monkeypatch):
    _patch(monkeypatch, _table3())
    recs, man = minfin.fetch_state_budget_debt_servicing()
    assert [(r["date"], round(r["value"], 3)) for r in recs] == [
        ("2023-12-31", 1865648.998), ("2024-12-31", 2232329.183), ("2025-12-31", 2660521.406)]
    assert man["frequency"] == "annual"
