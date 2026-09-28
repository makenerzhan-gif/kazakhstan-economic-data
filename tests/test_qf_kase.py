"""KASE statements of the quasi-fiscal holdings (scripts/fetchers/kase_ifrs.py): the Problem
Loans Fund (FPKR), KazAgro (KZAG), Samruk-Kazyna consolidated (SKKZ) and separate (SKKZ_SEP).
Fixture-based parser tests, no network; the data test runs once the dataset holds FPKR."""
import csv
import io
import json
import sys
import types
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from fetchers import kase_ifrs  # noqa: E402
from lib import validation  # noqa: E402

DATA = REPO_ROOT / "data" / "processed" / "dims" / "development_institutions_balance_sheets.csv"


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- Minfin Form 1 (SKKZ_SEP, *_nb_*)

def _form1(title=" за период с 01.01.2015 по 30.09.2015 года") -> bytes:
    return _xlsx({"Баланс": [
        ["Приложение 2"], ["к приказу Министра финансов Республики Казахстан"], ["от 20 августа 2010 года № 422"],
        ["Форма 1"], ["Бухгалтерский баланс"], [title], [None],
        ["", "", "", "", "тыс. тенге", ""],
        ["Наименование статьи", None, "Код строки", "На конец отчетного периода", "На конец отчетного периода ",
         "На начало отчетного периода"],
        ["Прочие долгосрочные финансовые активы", None, 114, None, 1_000_000_000, 900_000_000],
        ["Баланс (строка 100 +строка 101+ строка 200)", None, "", 0, 5_000_000_000, 4_000_000_000],
        ["Займы", None, 210, None, 100_000_000, 400_000_000],
        ["Итого краткосрочных обязательств (сумма строк с 210 по 217)", None, 300, 0, 150_000_000, 450_000_000],
        ["Займы", None, 310, None, 600_000_000, 1_300_000_000],
        ["Итого долгосрочных обязательств (сумма строк с 310 по 316)", None, 400, 0, 650_000_000, 1_350_000_000],
        ["Итого капитал, относимый на собственников материнской организации", None, 420, 0, 4_200_000_000, None],
        ["Всего капитал (строка 420 +/- строка 421)", None, 500, 0, 4_200_000_000, 2_200_000_000],
        ["Баланс (строка 300+строка 301+строка 400 + строка 500)", None, "", 0, 5_000_000_000, 4_000_000_000],
        ["Займы", None, 999, None, 7, 7]]})  # below the balance sheet: not summed


def test_minfin_form_dates_from_the_title_and_liabilities_from_the_two_totals():
    sheet, note = kase_ifrs.parse_balance_sheet(_form1())
    assert sorted(sheet) == ["2014-12-31", "2015-09-30"] and note == ""
    cur = sheet["2015-09-30"]  # the empty first «На конец» column is passed over
    assert cur["TOTAL_ASSETS"] == 5000.0 and cur["EQUITY"] == 4200.0
    assert cur["TOTAL_LIABILITIES"] == 800.0 and cur["BORROWINGS"] == 700.0  # 210 + 310
    assert sheet["2014-12-31"]["BORROWINGS"] == 1700.0 and sheet["2014-12-31"]["TOTAL_LIABILITIES"] == 1800.0
    assert not any(k.startswith("_") for v in sheet.values() for k in v)


def test_minfin_form_title_on_the_first_of_the_month_and_quarter_words():
    sheet, _ = kase_ifrs.parse_balance_sheet(_form1('по состоянию на "01" октября 2015 года'))
    assert sorted(sheet) == ["2014-12-31", "2015-09-30"]
    # «за первый квартал 2014 года» names no date: the file name's period is used
    assert kase_ifrs.parse_balance_sheet(_form1("за первый квартал 2014 года"))[0] == {}
    sheet, _ = kase_ifrs.parse_balance_sheet(_form1("за первый квартал 2014 года"), expected="2014-03-31")
    assert sorted(sheet) == ["2013-12-31", "2014-03-31"]


def test_labels_lose_form_suffixes():
    assert kase_ifrs._label("Всего обязательств (сумма строк 16-24)") == "всего обязательств"
    assert kase_ifrs._label("Итого капитал (сумма строк 26-33):") == "итого капитал"
    assert kase_ifrs._label("Баланс (строка 100 +строка 101+ строка 200)") == "итого активов"
    assert kase_ifrs._line(kase_ifrs._label("Всего обязательств (сумма строк 16-24)")) == "TOTAL_LIABILITIES"


# ---------------------------------------------------------------- KazAgro / Samruk-Kazyna / FPK layouts

def _kazagro(title="На 30 июня 2014 года", unit="В тысячах тенге") -> bytes:
    return _xlsx({"Лист1": [
        ["промежуточный сокращенный КОНСОЛИДИРОВАННЫЙ отчёт о финансовом положении"], [title], [unit], [None],
        [None, "Прим.", "30 сентября", "31 декабря"],
        [None, None, "2014 года", "2013 года"],
        ["Займы клиентам", 6, "205.037.326", "199.326.232"],
        ["Средства Правительства Республики Казахстан", 11, "70.655.213", "15.855.139"],
        ["Средства кредитных учреждений", 12, "117.003.875", "64.577.132"],
        ["Выпущенные долговые ценные бумаги", 13, "134.760.860", "117.254.491"],
        ["Выпущенные еврооблигации", 14, "323.614.755", "153.676.011"],
        ["Итого обязательства", None, "680.522.049", "379.853.033"],
        ["Резерв по условному распределению", 16, "(20.484.314)", "(17.028.754)"],
        ["Итого капитал", None, "332.541.187", "314.974.517"],
        ["Итого обязательства и капитал", None, "1.013.063.236", "694.827.550"],
        ["Процентные доходы", 19, "32.579.796", "22.035.177"]]})


def test_kazagro_layout_two_row_headers_summed_bonds_and_assets_from_the_grand_total():
    sheet, note = kase_ifrs.parse_balance_sheet(_kazagro(), expected="2014-09-30")
    assert sorted(sheet) == ["2013-12-31", "2014-09-30"]
    assert "total assets from" in note
    q3 = sheet["2014-09-30"]  # the title's «30 июня» typo loses to the header and the file name
    assert q3["TOTAL_ASSETS"] == pytest.approx(1013.063236)
    assert q3["DEBT_SECURITIES"] == pytest.approx(134.760860 + 323.614755)  # tenge bonds + Eurobonds
    assert q3["GOV_LOANS"] == pytest.approx(70.655213) and q3["BORROWINGS"] == pytest.approx(117.003875)
    assert q3["DISTRIBUTION_RESERVE"] == pytest.approx(-20.484314)
    assert q3["LOANS_CUSTOMERS"] == pytest.approx(205.037326)
    # without the file name the title wins (as before), which here would be the typo
    assert "2014-06-30" in kase_ifrs.parse_balance_sheet(_kazagro())[0]


def test_file_name_date_rejects_a_statement_of_another_year():
    sheet, note = kase_ifrs.parse_balance_sheet(_kazagro(), expected="2016-09-30")
    assert sheet == {} and "file name's year" in note


def test_units_millions_and_missing_unit_line():
    sheet, note = kase_ifrs.parse_balance_sheet(_kazagro(unit="В миллионах тенге"), expected="2014-09-30")
    assert sheet["2014-09-30"]["TOTAL_ASSETS"] == pytest.approx(1013063.236) and "thousands" not in note
    sheet, note = kase_ifrs.parse_balance_sheet(_kazagro(unit=None), expected="2014-09-30")
    assert sheet["2014-09-30"]["TOTAL_ASSETS"] == pytest.approx(1013.063236) and "thousands assumed" in note


def test_samruk_consolidated_long_and_current_lines_are_summed():
    content = _xlsx({"ОФП": [
        ["АО «Фонд Национального Благосостояния «Самрук-Қазына»"],
        ["В миллионах тенге", "Прим.", "30 июня 2026 года (неаудировано)", "31 декабря 2025 года (аудировано)"],
        ["Займы выданные и чистые инвестиции в финансовую аренду", 11, 328278, 323035],
        ["Займы выданные и чистые инвестиции в финансовую аренду", 11, 517499, 41647],
        ["Итого активы", None, 46665321, 44242913],
        ["Итого капитал", None, 27809599, 27180282],
        ["Займы", 17, 7539966, 6716384],
        ["Займы Правительства Республики Казахстан", 18, 1125107, 1085386],
        ["Займы", 17, 1404808, 1370737],
        ["Займы Правительства Республики Казахстан", 18, 21088, 115690],
        ["Итого обязательства", None, 18855722, 17062631],
        ["Итого капитал и обязательства", None, 46665321, 44242913]]})
    sheet, note = kase_ifrs.parse_balance_sheet(content, expected="2026-06-30")
    h1 = sheet["2026-06-30"]
    assert note == "" and h1["TOTAL_ASSETS"] == pytest.approx(46665.321)
    assert h1["BORROWINGS"] == pytest.approx(8944.774) and h1["GOV_LOANS"] == pytest.approx(1146.195)
    assert h1["LOANS_ISSUED"] == pytest.approx(845.777) and "LOANS_CUSTOMERS" not in h1


def test_fpk_single_date_column_claims_and_subsidies_receivable():
    content = _xlsx({"BS_PL": [
        ["АО ФОНД ПРОБЛЕМНЫХ КРЕДИТОВ"], ["Консолидированный о финансовом положении"], [None],
        [None, "Примечание", "30 сентября 2018 года"],
        ["Права требования", 12, 155_101_456],
        ["Государственные субсидии к получению", None, 5_000_000],
        ["Итого активы", None, 1_004_011_272],
        ["Выпущенные долговые ценные бумаги", 16, 450_675_000],
        ["Государственные субсидии", None, 1_000_000],
        ["Итого обязательства", "Total liabilities", 703_616_625],
        ["Резерв по условному распределению", 19, -2_744_474_119],
        ["Итого капитал", "Total equity", 300_394_647],
        ["ИТОГО ОБЯЗАТЕЛЬСТВА И КАПИТАЛ", None, 1_004_011_272]]})
    sheet, note = kase_ifrs.parse_balance_sheet(content, expected="2018-09-30")
    assert list(sheet) == ["2018-09-30"] and "thousands assumed" in note
    q = sheet["2018-09-30"]
    assert q["ACQUIRED_CLAIMS"] == pytest.approx(155.101456) and q["DEBT_SECURITIES"] == pytest.approx(450.675)
    assert q["DISTRIBUTION_RESERVE"] == pytest.approx(-2744.474119) and q["EQUITY"] == pytest.approx(300.394647)
    assert q["GOV_SUBSIDIES"] == 1.0  # the deferred income, not the receivable


def test_first_of_month_headers_are_the_previous_close():
    content = _xlsx({"ОФП": [["тыс. тенге"], [None, "на 01.04.2021", "на 01.01.2021"],
                             ["Итого активов", 100, 90], ["Итого обязательств", 60, 50], ["Итого капитала", 40, 40]]})
    sheet, _ = kase_ifrs.parse_balance_sheet(content)
    assert sorted(sheet) == ["2020-12-31", "2021-03-31"]
    assert kase_ifrs._as_date("31.06.2022") is None  # malformed header dates do not raise


def test_xls_is_read_with_xlrd(monkeypatch):
    class Cell:
        def __init__(self, ctype, value):
            self.ctype, self.value = ctype, value

    grid = [[Cell(1, "тыс. тенге")],
            [Cell(0, ""), Cell(3, 45382.0), Cell(3, 45291.0)],
            [Cell(1, "Итого активов"), Cell(2, 100.0), Cell(2, 90.0)],
            [Cell(1, "Итого обязательств"), Cell(2, 60.0), Cell(6, "")],
            [Cell(1, "Итого капитала"), Cell(2, 40.0), Cell(2, 40.0)]]

    class Sheet:
        name, nrows, ncols = "Баланс", len(grid), 3

        def cell(self, i, j):
            return grid[i][j] if j < len(grid[i]) else Cell(0, "")

    fake = types.SimpleNamespace(
        XL_CELL_EMPTY=0, XL_CELL_BLANK=6, XL_CELL_DATE=3, xldate=types.SimpleNamespace(XLDateError=ValueError),
        open_workbook=lambda file_contents: types.SimpleNamespace(sheets=lambda: [Sheet()], datemode=0),
        xldate_as_tuple=lambda v, mode: (openpyxl.utils.datetime.from_excel(v).timetuple()[:6]))
    monkeypatch.setitem(sys.modules, "xlrd", fake)
    (name, rows), = kase_ifrs._sheets(kase_ifrs.OLE_MAGIC + b"rest")
    assert name == "Баланс" and rows[1][1] == datetime(2024, 3, 31) and rows[3][2] is None
    sheet, _ = kase_ifrs.parse_balance_sheet(kase_ifrs.OLE_MAGIC + b"rest")
    assert sheet == {"2024-03-31": {"TOTAL_ASSETS": 0.0001, "TOTAL_LIABILITIES": 0.00006, "EQUITY": 0.00004}}


# ---------------------------------------------------------------- discovery, key indicators, fetch

def test_file_names_give_the_period_and_the_static_lists_are_complete():
    assert kase_ifrs._period_end("/f/kzagfm3_2014_cons_rus.xlsx") == "2014-09-30"
    assert kase_ifrs._period_end("/f/kzagfm4_2014_cons_rus.xlsx") == "2014-12-31"
    assert kase_ifrs._period_end("/f/fpkrf_2019_cons_rus.xlsx") == "2019-12-31"
    assert kase_ifrs._period_end("/f/kfusfm1_2021_rus_2.xlsx") == "2021-03-31"
    assert len(kase_ifrs.STATIC_DOCS["FPKR"]) == 11 and len(kase_ifrs.STATIC_DOCS["KZAG"]) == 23
    assert kase_ifrs.STATIC_DOCS["FPKR"][0][1] == "/files/emitters/FPKR/fpkrfm3_2018_cons_rus.xlsx"


def test_document_filter():
    keep = kase_ifrs.keep_document
    q = "Финансовая отчетность за январь–сентябрь 2025 года "
    nb = "Неполная финансовая отчетность за январь–март 2016 года для размещения на интернет-ресурсе ДФО и KASE"
    assert keep("SKKZ", q, "/files/emitters/SKKZ/skkzfm3_2025_rus.xlsx")  # consolidated without «cons»
    assert not keep("SKKZ", nb, "/files/emitters/SKKZ/skkzfm1_2016_nb_rus.xlsx")
    assert keep("SKKZ_SEP", nb, "/files/emitters/SKKZ/skkzfm1_2016_nb_rus.xlsx")
    assert not keep("SKKZ_SEP", q, "/files/emitters/SKKZ/skkzfm3_2025_rus.xlsx")
    assert keep("AGKK", q, "/files/emitters/AGKK/agkkfm1_2016_rus.xls")
    assert not keep("AGKK", q, "/files/emitters/AGKK/agkkfm1_2019_rus.xlsb") and not keep("AGKK", q, "/x/a.pdf")
    assert not keep("BTRK", q, "/files/emitters/BTRK/btrkfm3_2025_rus.xlsx")
    assert keep("BTRK", q + "(консолидированная)", "/files/emitters/BTRK/btrkfm3_2025_cons_rus.xlsx")


def test_documents_fall_back_to_the_static_list(monkeypatch):
    api = {"FPKR": b"[]", "SKKZ": json.dumps([
        {"name": "Неполная финансовая отчетность за январь–март 2016 года", "link": "/files/emitters/SKKZ/skkzfm1_2016_nb_rus.xlsx"},
        {"name": "Финансовая отчетность за январь–март 2026 года (консолидированная)",
         "link": "/files/emitters/SKKZ/skkzfm1_2026_cons_rus.xlsx"}]).encode(), "XXXX": b"[]", "BAD": b'{"language": []}'}
    monkeypatch.setattr(kase_ifrs, "_get", lambda url, missing_ok=False: api[url.rsplit("=", 1)[1]])
    assert kase_ifrs.documents("FPKR") == sorted(kase_ifrs.STATIC_DOCS["FPKR"], key=lambda x: x[1])
    assert [link for _, link in kase_ifrs.documents("SKKZ_SEP")] == ["/files/emitters/SKKZ/skkzfm1_2016_nb_rus.xlsx"]
    assert [link for _, link in kase_ifrs.documents("SKKZ")] == ["/files/emitters/SKKZ/skkzfm1_2026_cons_rus.xlsx"]
    with pytest.raises(validation.StructuralChangeError, match="no financial statements"):
        kase_ifrs.documents("XXXX")
    with pytest.raises(validation.StructuralChangeError, match="documents API"):
        kase_ifrs.documents("BAD")


def test_fin_data_dates_units_and_nulls():
    rows = [{"change_date": "2026-07-01", "units": "mln", "aggregate_assets": 46665321.0,
             "total_liabilities": 18855722.0, "own_capital": 27809599.0},
            {"change_date": "2011-01-01", "units": "thnd", "aggregate_assets": 12_815_300_000.0,
             "total_liabilities": None, "own_capital": 5_422_400_000.0}]
    fd = kase_ifrs.parse_fin_data(rows)
    assert fd["2026-06-30"] == {"FD_TOTAL_ASSETS": 46665.321, "FD_TOTAL_LIABILITIES": 18855.722, "FD_EQUITY": 27809.599}
    assert fd["2010-12-31"] == {"FD_TOTAL_ASSETS": 12815.3, "FD_EQUITY": 5422.4}
    with pytest.raises(validation.StructuralChangeError):
        kase_ifrs.parse_fin_data({"detail": "Not found"})
    with pytest.raises(validation.StructuralChangeError, match="units"):
        kase_ifrs.parse_fin_data([{**rows[0], "units": "bln"}])


def _simple(year: int) -> bytes:
    return _xlsx({"ОФП": [["тыс. тенге"], [None, f"31 марта {year} г.", f"31 декабря {year - 1} г."],
                         ["Итого активов", 100_000_000, 90_000_000], ["Итого обязательств", 60_000_000, 50_000_000],
                         ["Итого капитала", 40_000_000, 40_000_000]]})


def _offline_fetch(monkeypatch, fd_assets: float):
    statement = _simple(2026)
    responses = {
        kase_ifrs.DOCS_URL.format(code="BTRK"): json.dumps([{"name": "Финансовая отчетность за январь–март 2026 года (консолидированная)",
                                                             "link": "/files/emitters/BTRK/btrkfm1_2026_cons_rus.xlsx"}]).encode(),
        kase_ifrs.DOCS_URL.format(code="FPKR"): b"[]",
        kase_ifrs.FILE_BASE + "/files/emitters/BTRK/btrkfm1_2026_cons_rus.xlsx": statement,
        kase_ifrs.FIN_DATA_URL.format(code="BTRK"): json.dumps([
            {"change_date": "2026-04-01", "units": "thnd", "aggregate_assets": fd_assets, "total_liabilities": 60e6, "own_capital": 40e6},
            {"change_date": "2016-01-01", "units": "thnd", "aggregate_assets": 3_460_325_554.0, "total_liabilities": 2_597_327_281.0,
             "own_capital": 862_998_273.0}]).encode()}
    for _, link in kase_ifrs.STATIC_DOCS["FPKR"]:
        responses[kase_ifrs.FILE_BASE + link] = _simple(2021) if "fm1_2021" in link else _simple(2026) if "fm2_2021" in link else None
    monkeypatch.setattr(kase_ifrs, "_get", lambda url, missing_ok=False: responses[url])
    monkeypatch.setattr(kase_ifrs.raw_store, "save_raw_bytes", lambda *a, **k: None)
    monkeypatch.setattr(kase_ifrs.raw_store, "write_download_manifest", lambda *a, **k: None)
    monkeypatch.setattr(kase_ifrs.imf_dims, "stored_if_fresh", lambda *a, **k: None)
    ds = {"id": "T", "issuers": {"BTRK": "Байтерек", "FPKR": "ФПК"}, "fin_data": ["BTRK"], "frequency": "quarterly"}
    return kase_ifrs.fetch(ds)


def test_fetch_uses_the_static_list_and_adds_key_indicators(monkeypatch):
    records, meta = _offline_fetch(monkeypatch, 100_000_000.0)
    out = {(r["item_code"], r["date"]): r["value"] for r in records}
    assert out[("BTRK.TOTAL_ASSETS", "2026-03-31")] == 100.0 and out[("BTRK.FD_TOTAL_ASSETS", "2015-12-31")] == 3460.325554
    assert out[("FPKR.TOTAL_ASSETS", "2021-03-31")] == 100.0 and out[("FPKR.EQUITY", "2020-12-31")] == 40.0
    assert not any(d > "2021-12-31" for (c, d) in out if c.startswith("FPKR."))  # fpkrfm2_2021 headed 2026: dropped
    assert sum(w.endswith(": 404") for w in meta["warnings"]) == 9
    assert any("fpkrfm2_2021" in w and "file name's year" in w for w in meta["warnings"])
    names = {r["item_code"]: r["item_name"] for r in records}
    assert names["BTRK.FD_EQUITY"] == "Байтерек: Итого капитала (ключевые показатели KASE), млрд тенге"


def test_fetch_stops_on_a_unit_mismatch_with_the_key_indicators(monkeypatch):
    with pytest.raises(validation.StructuralChangeError, match="unit misread"):
        _offline_fetch(monkeypatch, 100_000_000_000.0)


# ---------------------------------------------------------------- data (after the integrator's run)

def _data():
    with DATA.open(encoding="utf-8") as f:
        return {(r["date"], r["item_code"]): float(r["value"]) for r in csv.DictReader(f)}


@pytest.mark.skipif(not DATA.exists() or "FPKR." not in DATA.read_text(encoding="utf-8"),
                    reason="DEVELOPMENT_INSTITUTIONS_BALANCE_SHEETS not yet refreshed with FPKR/KZAG/SKKZ")
def test_quasi_fiscal_issuers_in_the_dataset():
    bs = _data()
    # ФПК, 31.12.2019 (fpkrf_2019_cons_rus.xlsx): assets 454.7, bonds 1 165.6, equity -716.3 bn KZT
    assert bs[("2019-12-31", "FPKR.TOTAL_ASSETS")] == pytest.approx(454.681784, abs=1e-3)
    assert bs[("2019-12-31", "FPKR.DEBT_SECURITIES")] == pytest.approx(1165.561731, abs=1e-3)
    assert bs[("2019-12-31", "FPKR.EQUITY")] == pytest.approx(-716.288213, abs=1e-3)
    # КазАгро: 548.1 bn at 2012-12-31, 1 474.3 bn at 2020-09-30
    assert bs[("2012-12-31", "KZAG.TOTAL_ASSETS")] == pytest.approx(548.1, abs=0.1)
    assert bs[("2020-09-30", "KZAG.TOTAL_ASSETS")] == pytest.approx(1474.3, abs=0.1)
    # Самрук-Казына: consolidated 46 665.3 bn at 2026-06-30; separate borrowings 628.5 bn at 2015-09-30
    assert bs[("2026-06-30", "SKKZ.TOTAL_ASSETS")] == pytest.approx(46665.321, abs=1e-3)
    assert bs[("2015-09-30", "SKKZ_SEP.BORROWINGS")] == pytest.approx(628.459050, abs=1e-3)
    assert bs[("2015-12-31", "BTRK.FD_TOTAL_ASSETS")] == pytest.approx(3460.325554, abs=1e-3)
    assert not any(d > "2020-12-31" for d, i in bs if i.startswith("KZAG."))


def test_stored_records_are_reused_only_when_they_cover_every_issuer(monkeypatch):
    old = [{"date": "2026-03-31", "region": "national", "item_code": "BTRK.TOTAL_ASSETS", "item_name": "x", "value": 1.0}]
    monkeypatch.setattr(kase_ifrs.imf_dims, "stored_if_fresh", lambda *a, **k: (old, {"warnings": ["not re-downloaded"]}))
    ds = {"id": "T", "issuers": {"BTRK": "Байтерек"}, "frequency": "quarterly"}
    assert kase_ifrs.fetch(ds)[0] == old
    monkeypatch.setattr(kase_ifrs, "_get", lambda url, missing_ok=False: (_ for _ in ()).throw(RuntimeError("download")))
    with pytest.raises(RuntimeError, match="download"):
        kase_ifrs.fetch({**ds, "issuers": {"BTRK": "Байтерек", "FPKR": "ФПК"}})
    with pytest.raises(RuntimeError, match="download"):
        kase_ifrs.fetch({**ds, "fin_data": ["BTRK"]})
