"""Sources added 2026-11-09 (the second batch): NBK rates by purpose and the securities market
(nbk_cube "" codes and distinct datasets), Taldau vacancies / registered unemployed / investment by
source, KASE indices and bond volumes, the KMG databook, FAO and UN WPP, freight by mode, the
consumer sentiment index derived from the NBK survey. No network."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import validation  # noqa: E402
from fetchers import bns_dims, kase_dims, kmg, nbk_cube, nbk_expectations, world_misc  # noqa: E402
import update_dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- nbk_cube: "" codes, distinct

RATES = {"id": "T", "form_id": "0", "filters": {"type": "rate"}, "distinct": True, "sum_check": False,
         "levels": [["currency", "subject", "purpose"]],
         "codes": {"currency": {"KZT": "KZT"}, "subject": {"": "ALL", "Business": "BUS", "Individuals": "HH"},
                   "purpose": {"": "", "Undefined": "", "Mortgage": "MORTGAGE"}}}


def _r(subject, purpose, amount, when="2026-09-01"):
    return {"report_date": when, "amount": amount, "type": "rate", "currency": "KZT", "subject": subject, "purpose": purpose}


def test_empty_codes_make_items_of_different_lengths():
    rows = [_r(None, None, 20.9), _r("Business", None, 21.2), _r("Individuals", "Mortgage", 10.7), _r("Individuals", "Undefined", 20.6)]
    assert {r["item_code"]: r["value"] for r in nbk_cube.cube_records(rows, RATES)} == {
        "KZT.ALL": 20.9, "KZT.BUS": 21.2, "KZT.HH.MORTGAGE": 10.7, "KZT.HH": 20.6}


def test_distinct_tolerates_a_repeated_row_and_stops_on_a_conflict():
    rows = [_r("Business", None, 21.2), _r("Business", None, 21.2)]
    assert [r["value"] for r in nbk_cube.cube_records(rows, RATES)] == [21.2]
    with pytest.raises(validation.StructuralChangeError, match="two different values"):
        nbk_cube.cube_records([_r("Business", None, 21.2), _r("Business", None, 19.0)], RATES)


def test_field_aliases_read_one_row_field_through_two_maps():
    ds = {**RATES, "levels": [["currency", "subject"], ["currency", "hh", "purpose"]], "field_aliases": {"hh": "subject"},
          "codes": {**RATES["codes"], "subject": {"": "ALL", "Business": "BUS", "Individuals": None},
                    "hh": {"": None, "Business": None, "Individuals": "HH"}}}
    rows = [_r(None, None, 20.9), _r("Business", None, 21.2), _r("Individuals", "Mortgage", 10.7)]
    assert {r["item_code"] for r in nbk_cube.cube_records(rows, ds)} == {"KZT.ALL", "KZT.BUS", "KZT.HH.MORTGAGE"}


def test_second_batch_datasets_are_configured():
    by = {d["id"]: d for d in update_dims.DATASETS.values()}
    for i in ("LOAN_RATES_BY_PURPOSE", "LOAN_RATES_BY_MATURITY", "GOV_SECURITIES_PRIMARY_AUCTIONS", "GOV_SECURITIES_SECONDARY_MARKET",
              "VACANCIES_BY_REGION_QUARTERLY", "EMPLOYEE_SEPARATIONS_BY_REGION_QUARTERLY", "REGISTERED_UNEMPLOYED_SHARE", "REGISTERED_UNEMPLOYED",
              "INVESTMENT_BY_SOURCE_BY_REGION_YTD", "INVESTMENT_BY_SOURCE_BY_REGION", "KASE_INDICES", "KASE_CORPORATE_BOND_VOLUMES",
              "KMG_OIL_PRODUCTION_AND_TRANSPORT", "FAO_FOOD_PRICE_INDEX", "UN_WPP_POPULATION", "FREIGHT_BY_MODE_MONTHLY",
              "FREIGHT_TURNOVER_BY_MODE_MONTHLY"):
        assert i in by, i
    assert by["LOAN_RATES_BY_PURPOSE"]["distinct"] and by["LOAN_RATES_BY_PURPOSE"]["sum_check"] is False
    assert by["GOV_SECURITIES_PRIMARY_AUCTIONS"]["codes"]["month_period"][""] is None     # no term: not an item of the by-term level
    assert by["INVESTMENT_BY_SOURCE_BY_REGION_YTD"]["cumulation"] == "year_to_date"
    assert {i["code"] for i in by["INVESTMENT_BY_SOURCE_BY_REGION"]["items"]} >= {"TOTAL", "OWN", "REP_BUDGET", "LOCAL_BUDGET", "BANK_LOANS", "OTHER_BORROWED"}
    assert by["FAO_FOOD_PRICE_INDEX"]["region"] == "world"


# ---------------------------------------------------------------- BNS year rows x month columns

def test_year_rows_months_reads_discrete_months_and_preliminary_years():
    months = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    grid = [[181103, "Перевезено грузов", None], [None] * 3, [None, *months, None],
            [2024, *[float(i) for i in range(1, 13)], None], ["2025*", 27423.3, 26331.9, "…", None, None, None, None, None, None, None, None, None, None],
            ["*По грузовому железнодорожному транспорту …", None]]
    ds = {"id": "T", "element_id": 0, "layout": "year_rows_months", "sheet_items": {"Железнодорожный": "RAIL"}, "item_names": {"RAIL": "Ж/д"}}
    recs = bns_dims.parse_year_rows_months(grid, ds, "Железнодорожный")
    by = {r["date"]: r["value"] for r in recs}
    assert by["2024-01-01"] == 1.0 and by["2024-12-01"] == 12.0 and by["2025-02-01"] == 26331.9 and "2025-03-01" not in by
    assert all(r["item_code"] == "RAIL" and r["item_name"] == "Ж/д" and r["region"] == "national" for r in recs)
    ytd = [[None, "январь", "январь-февраль", "январь-март", *months[3:], None]]
    with pytest.raises(validation.StructuralChangeError, match="twelve month names"):
        bns_dims.parse_year_rows_months(ytd + grid[3:], ds, "Железнодорожный")


# ---------------------------------------------------------------- KASE

def test_bond_table_rows_and_monthly_from_daily():
    body = ("<p>…</p><pre>Год,       Первичный Вторичный\n2026, VII    1 197,8     103,2 1 301,1\n2026, X        800,5     100,8   901,3\n"
            "Всего        5 338,5   1 082,0 6 420,5\n2025, I-X    3 576,7     870,1 4 446,8</pre>")
    assert kase_dims.bond_rows(body) == {"2026-07-01": (1197.8, 103.2, 1301.1), "2026-10-01": (800.5, 100.8, 901.3)}
    daily = [{"date": "2026-10-01", "value": 7900.0}, {"date": "2026-10-30", "value": 7916.32}, {"date": "2026-11-03", "value": 7850.0}]
    by = {r["item_code"]: r["value"] for r in kase_dims.monthly_from_daily(daily, "INDEX_KASE", "Индекс KASE") if r["date"] == "2026-10-01"}
    assert by == {"INDEX_KASE.AVG": 7908.16, "INDEX_KASE.EOM": 7916.32}


# ---------------------------------------------------------------- KMG databook

def _databook(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "стр. 6"
    ws.append([None, None, None, "1кв 2025", "2кв. 2025", 2025])
    ws.append([None, "ДОБЫЧА НЕФТИ", None, "1кв 2025", "2кв. 2025", 2025])
    ws.append([None, 'АО "Озенмунайгаз" ', "тыс. тонн", 1300.0, 1310.0, 2610.0])
    ws.append([None, "Итого операционные активы", "тыс. тонн", 1300.0, 1310.0, 2610.0])
    ws.append([None, 'ТОО "Тенгизшевройл" (20%)', "тыс. тонн", 1873.66, 2018.78, 3892.44])
    ws.append([None, '"Норт Каспиан Оперейтинг Компани н.в." (8,44%; 16,88% после 15.09.22)', "тыс. тонн", 760.7, 700.0, 1460.7])
    ws.append([None, '"Карачаганак Петролеум Оперейтинг б.в." (10%)', "тыс. тонн", 280.0, "275,5", 555.5])
    ws.append([None, "Всего с учетом операционной доли ", "тыс. тонн", 4214.36, 4304.28, 8518.64])
    ws7 = wb.create_sheet("стр. 7")
    ws7.append([None, "Транспортировка нефти по магистральным нефтепроводам", None, "1кв 2025", "2кв. 2025", 2025])
    ws7.append([None, 'АО "КазТрансОйл"', "млн тонн", 11.0, 11.2, 22.2])
    ws7.append([None, "Каспийский трубопроводный консорциум", "млн тонн", 4.0, 4.1, 8.1])
    ws7.append([None, "Транспортировка нефти по магистральным нефтепроводам", None, "1кв 2025", "2кв. 2025", 2025])
    ws7.append([None, 'АО "КазТрансОйл"', "млн барр.*", 80.0, 81.0, 161.0])
    ws7.append([None, "Транспортировка нефти по магистральным нефтепроводам", None, "1кв 2025", "2кв. 2025", 2025])
    ws7.append([None, "Экспорт", "%", 0.45, 0.46, 0.455])
    ws7.append([None, "Внутренний рынок (НПЗ РК)", "%", 0.23, 0.22, 0.225])
    p = tmp_path / "book.xlsx"
    wb.save(p)
    return p.read_bytes()


def test_kmg_databook_production_gross_and_transport(tmp_path):
    recs = kmg.parse_databook(_databook(tmp_path), {"id": "T"})
    by = {(r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("TCO", "2025-01-01")] == 1873.66 and by[("TCO_GROSS", "2025-04-01")] == pytest.approx(10093.9)
    assert by[("NCOC_GROSS", "2025-01-01")] == pytest.approx(760.7 / 0.1688, abs=0.01) and by[("KPO", "2025-04-01")] == 275.5
    assert by[("TRANSPORT_KTO", "2025-04-01")] == 11.2 and by[("TRANSPORT_CPC", "2025-01-01")] == 4.0
    assert by[("SHARE_EXPORT", "2025-04-01")] == 46.0 and by[("SHARE_DOMESTIC", "2025-01-01")] == 23.0
    assert ("TRANSPORT_KTO", "2025-12-31") not in by                      # annual columns are not kept
    assert kmg.latest_file('<a href="/upload/iblock/x/Справочник_1кв2026_rus.xlsx">a</a><a href="/upload/iblock/y/Справочник_2кв2026_rus.xlsx">b</a>'
                           '<a href="/upload/iblock/z/Справочник_4кв2025_ru.xlsx">c</a>') == ("https://www.kmg.kz/upload/iblock/y/Справочник_2кв2026_rus.xlsx", 2026, 2)


# ---------------------------------------------------------------- FAO, UN WPP

def test_fao_csv_rows():
    content = ("﻿FAO Food Price Index,,,,,,,\n2014-2016=100,,,,,,,\nDate,Food Price Index,Meat,Dairy,Cereals,Oils,Sugar,,\n,,,,,,,,\n"
               "1990-01,64.4,74.3,53.5,64.1,44.59,87.9,,\n2026-09,135.6,127.1,119.1,122.3,198.6,113.7,,\n").encode()
    by = {(r["item_code"], r["date"]): r["value"] for r in world_misc.fao_records(content, {"id": "T", "agency": "fao"})}
    assert by[("FFPI", "1990-01-01")] == 64.4 and by[("OILS", "2026-09-01")] == 198.6 and len(by) == 12
    assert all(r["region"] == "world" for r in world_misc.fao_records(content, {"id": "T", "agency": "fao"}))


def test_wpp_records_variants_ages_and_indicators():
    total = [{"Variant": "Medium", "Time": "2024", "PopTotal": "20592.571", "PopMale": "10100", "PopFemale": "10492.571"},
             {"Variant": "High", "Time": "2050", "PopTotal": "28447.199", "PopMale": "1", "PopFemale": "2"},
             {"Variant": "Low", "Time": "2050", "PopTotal": "24000", "PopMale": "1", "PopFemale": "2"},
             {"Variant": "Upper 80 PI", "Time": "2050", "PopTotal": "27000", "PopMale": "1", "PopFemale": "2"}]
    age = [{"Time": "2024", "AgeGrpStart": "0", "PopTotal": "2000"}, {"Time": "2024", "AgeGrpStart": "10", "PopTotal": "2048.714"},
           {"Time": "2024", "AgeGrpStart": "15", "PopTotal": "12761.932"}, {"Time": "2024", "AgeGrpStart": "65", "PopTotal": "1000"},
           {"Time": "2024", "AgeGrpStart": "100", "PopTotal": "1.5"}]
    ind = [{"Time": "2024", "TFR": "2.9", "LEx": "75.1", "NetMigrations": "-12.3", "TPopulation1Jan": "20464.208"}]
    by = {(r["item_code"], r["date"]): r["value"] for r in world_misc.wpp_records(total, age, ind, {"id": "T", "agency": "un"})}
    assert by[("TOTAL.MEDIUM", "2024-12-31")] == 20592.571 and by[("TOTAL.UPPER_80_PI", "2050-12-31")] == 27000
    assert by[("AGE_0_14", "2024-12-31")] == 4048.714 and by[("AGE_15_64", "2024-12-31")] == 12761.932 and by[("AGE_65", "2024-12-31")] == 1001.5
    assert by[("TFR", "2024-12-31")] == 2.9 and by[("NET_MIGRATION", "2024-12-31")] == -12.3 and by[("POP_1JAN", "2024-12-31")] == 20464.208
    with pytest.raises(validation.StructuralChangeError, match="variants"):
        world_misc.wpp_records(total[:1], age, ind, {"id": "T", "agency": "un"})


# ---------------------------------------------------------------- consumer sentiment from the NBK survey

def test_consumer_sentiment_index_from_answer_shares():
    shares = {"Q9.1": 30, "Q9.3": 20, "Q10.1": 40, "Q10.3": 10, "Q23.1": 10, "Q23.2": 20, "Q23.4": 15, "Q23.5": 5,
              "Q24.1": 35, "Q24.3": 15, "Q25.1": 25, "Q25.3": 30}
    recs = [{"date": "2025-10-01", "region": "national", "item_code": k, "item_name": k, "value": float(v)} for k, v in shares.items()]
    by = {r["item_code"]: r["value"] for r in nbk_expectations.sentiment_records(recs)}
    assert by["CSI.Q9"] == 110 and by["CSI.Q23"] == 110 and by["CSI.Q25"] == 95
    assert by["CSI.CURRENT"] == 102.5 and by["CSI.EXPECTATIONS"] == 120.0 and by["CSI"] == 113.0
    partial = [r for r in recs if not r["item_code"].startswith("Q25")]          # a quarterly question missing that month
    codes = {r["item_code"] for r in nbk_expectations.sentiment_records(partial)}
    assert "CSI.EXPECTATIONS" in codes and "CSI" not in codes and "CSI.CURRENT" not in codes


@pytest.mark.cross_source
def test_derived_sentiment_index_matches_the_values_the_nbk_published():
    """«Индекс потребительских настроений» in the NBK's reports: May 2022 104.1, December 2023 115.7, October 2025 99.1."""
    with (REPO_ROOT / "data" / "processed" / "dims" / "inflation_expectations_survey.csv").open(encoding="utf-8") as f:
        by = {(r["item_code"], r["date"]): float(r["value"]) for r in csv.DictReader(f) if r["item_code"] == "CSI"}
    for d, published in (("2022-05-01", 104.1), ("2023-12-01", 115.7), ("2025-10-01", 99.1)):
        assert abs(by[("CSI", d)] - published) < 0.06, (d, by.get(("CSI", d)), published)
