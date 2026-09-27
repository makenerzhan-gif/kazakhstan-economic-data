"""The seven gaps of 2026-09-27: quasi-fiscal lending (NBK forms 445/470/50, Damu, development
institutions' IFRS statements), inflation expectations (NBK household survey, analysts' survey,
enterprise expectations by sector), import prices by HS section, the import-weighted NEER,
monthly wage-bill proxies (ГФСС 5-СО, UAPF contributions) and local budgets by region.
Parser tests on built fixtures; data tests on the processed files against published figures."""
import csv
import io
import math
import sys
from pathlib import Path

import openpyxl
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import (comtrade, damu, gfss, kase_ifrs, minfin_regions, nbk_dims,  # noqa: E402
                      nbk_expectations, nbk_fx, neer_import)
from lib import validation  # noqa: E402

DIMS = REPO_ROOT / "data" / "processed" / "dims"


def _dims(name: str) -> dict[tuple[str, str, str], float]:
    with (DIMS / f"{name.lower()}.csv").open(encoding="utf-8") as f:
        return {(r["date"], r["region"], r["item_code"]): float(r["value"]) for r in csv.DictReader(f)}


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


# ---------------------------------------------------------------- NBK classified forms

LOANS_DS = {"id": "T", "filters": {"type": "mln", "period": "Month"},
            "item_fields": [{"field": "creditors", "codes": {"other public sector": "OPS", "Banking sector": "BANKS"}},
                            {"field": "subject_type", "codes": {"Business": "BUS"}}]}


def test_classified_rows_ignore_case_and_outer_spaces():
    rows = [{"report_date": "2026-08-01", "amount": 5.0, "type": "mln", "period": "month",
             "creditors": "other public sector ", "subject_type": "Business"},
            {"report_date": "2026-08-01", "amount": 7.0, "type": "other", "period": "Month",
             "creditors": "Banking sector", "subject_type": "Business"}]
    out = nbk_dims.classified_records(rows, LOANS_DS)
    assert [(r["item_code"], r["value"]) for r in out] == [("OPS.BUS", 5.0)]


def test_classified_rows_stop_on_an_unknown_value_or_a_conflict():
    row = {"report_date": "2026-08-01", "amount": 5.0, "type": "mln", "period": "Month", "subject_type": "Business"}
    with pytest.raises(validation.StructuralChangeError, match="Leasing"):
        nbk_dims.classified_records([{**row, "creditors": "Leasing"}], LOANS_DS)
    with pytest.raises(validation.StructuralChangeError, match="two different values"):
        nbk_dims.classified_records([{**row, "creditors": "Banking sector"},
                                     {**row, "creditors": "Banking sector", "amount": 6.0}], LOANS_DS)


def test_other_industries_is_the_pooled_nrs_slot():
    assert nbk_dims.SURVEY_SECTORS["Other industries"] == nbk_dims.SURVEY_SECTORS["N.R.S"] == "NRS"


def test_loans_by_creditor_banks_equal_the_scalar_business_loans():
    loans = _dims("LOANS_BY_CREDITOR_TYPE")
    with (REPO_ROOT / "data" / "processed" / "nbk" / "loans_business_kzt.csv").open(encoding="utf-8") as f:
        scalar = {r["date"]: float(r["value"]) for r in csv.DictReader(f)}
    common = [d for (d, _, i) in loans if i == "BANKS.KZT.BUS" and d in scalar]
    assert len(common) >= 30
    assert all(abs(loans[(d, "national", "BANKS.KZT.BUS")] - scalar[d]) < 1.0 for d in common)
    # «other public sector» business lending: 1 486 bn KZT in January 2022, over 4 trn by 2026
    assert loans[("2022-01-01", "national", "OPS.KZT.BUS")] == pytest.approx(1485756.0, abs=1)
    assert loans[("2026-08-01", "national", "OPS.KZT.BUS")] > 4.0e6


def test_nbk_monetary_survey_identities_hold():
    ms = _dims("NBK_MONETARY_SURVEY")
    dates = {d for d, _, _ in ms}
    for d in dates:
        if all((d, "national", k) in ms for k in ("1", "2", "3")):
            assert ms[(d, "national", "1")] + ms[(d, "national", "2")] == pytest.approx(ms[(d, "national", "3")], abs=5)


# ---------------------------------------------------------------- Damu

def test_damu_link_is_the_latest_edition():
    html = ('<a href="/upload/iblock/a/Отчет по проектам субсидирования на 01.08.2026г.xlsx">'
            '<a href="/upload/iblock/b/Отчет по проектам субсидирования на 01.09.2026г.xlsx">')
    url, as_of = damu._latest_link(html)
    assert as_of == "2026-09-01" and "/b/" in url and "%20" in url


def test_damu_aggregates_by_region_programme_and_month():
    projects = [{"region": "AKM", "year": 2024, "month": 3, "programme": "PS", "section": "C", "size": "SMALL", "amount": 2e9},
                {"region": "AST", "year": 2024, "month": None, "programme": "DKB", "section": "G", "size": "MICRO", "amount": 1e9}]
    annual = {(r["date"], r["region"], r["item_code"]): r["value"] for r in damu.aggregate(projects, monthly=False)}
    assert annual[("2024-01-01", "national", "TOTAL")] == 3.0
    assert annual[("2024-01-01", "AKM", "SEC.C")] == 2.0 and annual[("2024-01-01", "national", "COUNT.TOTAL")] == 2
    monthly = {(r["date"], r["region"], r["item_code"]): r["value"] for r in damu.aggregate(projects, monthly=True)}
    assert monthly == {k: v for k, v in monthly.items() if k[0] == "2024-03-01"} and monthly[("2024-03-01", "national", "PROG.PS")] == 2.0


# ---------------------------------------------------------------- IFRS statements on KASE

def _statement(current_header="31 марта 2026 г.", comparative="31 декабря 2025 г.", liabilities=60.0) -> bytes:
    return _xlsx({"Ф1": [
        ["Консолидированный отчет о финансовом положении"],
        ["АО «Холдинг» по состоянию на 31 марта 2026 года"],
        [None, "тыс. тенге"],
        [None, None, current_header, comparative],
        ["Кредиты, выданные клиентам", 4, "70.000.000", "(1.000)"],
        ["Итого активов", None, 100_000_000, 90_000_000],
        ["Займы от Правительства Республики Казахстан", 9, 5_000_000, 5_000_000],
        ["Итого обязательств", None, liabilities * 1e6, 50_000_000],
        ["Итого собственного капитала", None, 40_000_000, 40_000_000]]})


def test_ifrs_balance_sheet_in_billions_with_the_identity_enforced():
    sheet, note = kase_ifrs.parse_balance_sheet(_statement())
    assert note == ""
    assert sheet["2026-03-31"]["TOTAL_ASSETS"] == 100.0 and sheet["2026-03-31"]["LOANS_CUSTOMERS"] == 70.0
    assert sheet["2025-12-31"]["LOANS_CUSTOMERS"] == -0.001 and sheet["2025-12-31"]["GOV_LOANS"] == 5.0
    broken, note = kase_ifrs.parse_balance_sheet(_statement(liabilities=61.0))
    assert "2026-03-31" not in broken and "failing" in note


def test_ifrs_title_date_overrides_a_mistyped_header():
    sheet, note = kase_ifrs.parse_balance_sheet(_statement(current_header="30 июня 2026 г."))
    assert "2026-03-31" in sheet and "read as the title" in note
    sheet, note = kase_ifrs.parse_balance_sheet(_statement(comparative="31 марта 2025 г."))
    assert list(sheet) == ["2026-03-31"] and "not a year end" in note


def test_statement_order_prefers_later_reports():
    assert kase_ifrs._order("/x/btrkfm3_2025_cons_rus.xlsx") > kase_ifrs._order("/x/btrkf_2024_cons_rus.xlsx") \
        > kase_ifrs._order("/x/btrkfm1_2024_cons_rus.xlsx")


def test_baiterek_balance_sheet_from_kase():
    bs = _dims("DEVELOPMENT_INSTITUTIONS_BALANCE_SHEETS")
    # «Байтерек» consolidated, 31 March 2026 (btrkfm1_2026): assets 19 417.3, loans to customers 8 150.1 bn KZT
    assert bs[("2026-03-31", "national", "BTRK.TOTAL_ASSETS")] == pytest.approx(19417.264678, abs=1e-3)
    assert bs[("2026-03-31", "national", "BTRK.LOANS_CUSTOMERS")] == pytest.approx(8150.147808, abs=1e-3)
    for (d, reg, item), v in bs.items():
        if item.endswith(".TOTAL_ASSETS"):
            issuer = item.split(".")[0]
            assert v == pytest.approx(bs[(d, reg, f"{issuer}.TOTAL_LIABILITIES")] + bs[(d, reg, f"{issuer}.EQUITY")], rel=0.005)


# ---------------------------------------------------------------- expectations

def test_household_survey_blocks_and_medians():
    content = _xlsx({"Данные": [
        ["Источник данных"],
        ["Вопрос №5", "Как изменятся цены?"], [None, "в % от всех"],
        [None, "Варианты ответов", openpyxl.utils.datetime.from_excel(44562), openpyxl.utils.datetime.from_excel(44593)],
        [None, "Будут расти быстрее", 30.0, 14.4], [None, "Будут снижаться", 1.0, None], [None],
        ["Вопрос №6", "На сколько вырастут цены?"], [None, "в % от ожидающих"],
        [None, "Варианты ответов", openpyxl.utils.datetime.from_excel(44562)], [None, "1-5%", 5.0], [None],
        ["Вопрос №6", "На сколько вырастут цены (новые интервалы)?"],
        [None, "Варианты ответов", openpyxl.utils.datetime.from_excel(45658)], [None, "1-3%", 2.0]],
        "Медианные оценки": [["Медианы"], [None, "Воспринимаемая (за прошедшие 12 месяцев)", "Ожидаемая (в следующие 12 месяцев)"],
                             [openpyxl.utils.datetime.from_excel(44593), 18.2, 9.6]]})
    out = {(r["date"], r["item_code"]): r["value"] for r in nbk_expectations.household_records(content)}
    assert out[("2022-02-01", "Q5.1")] == 14.4 and ("2022-02-01", "Q5.2") not in out
    assert out[("2022-01-01", "Q6.1")] == 5.0 and out[("2025-01-01", "Q6.v2.1")] == 2.0
    assert out[("2022-02-01", "MEDIAN.EXPECTED_12M")] == 9.6 and out[("2022-02-01", "MEDIAN.PERCEIVED_12M")] == 18.2


def test_forecaster_chronology_items_and_unknown_variables():
    d = openpyxl.utils.datetime.from_excel
    rows = [[None, None, "Период"], [None, None, "Опросный", d(45505), d(45536), d(45566)],
            [None, "Инфляция\n%, декабрь к декабрю", 2026, 8.0, 8.5, 9.0], [None, None, 2027, 7.0, None, 7.5],
            [None, "Нейтральная базовая ставка*\n% годовых", None, 9.0, 9.0, 9.5], [None, "*Уровень базовой ставки …"]]
    out = {(r["date"], r["item_code"]): r["value"] for r in nbk_expectations.forecaster_records(_xlsx({"Август": rows}))}
    assert out[("2024-09-01", "CPI_DEC.2026")] == 8.5 and ("2024-09-01", "CPI_DEC.2027") not in out
    assert out[("2024-10-01", "NEUTRAL_RATE")] == 9.5
    with pytest.raises(validation.StructuralChangeError, match="unknown variables"):
        nbk_expectations.forecaster_records(_xlsx({"x": rows[:2] + [[None, "Цена на золото", 2026, 1.0, 2.0, 3.0]]}))


def test_survey_file_copies_q5_into_q6_in_february_2022_only():
    """The registered source issue inflation_expectations_survey_2022_02_q6."""
    s = _dims("INFLATION_EXPECTATIONS_SURVEY")
    q = lambda d, c: tuple(s.get((d, "national", f"{c}.{i}")) for i in range(1, 6))  # noqa: E731
    assert q("2022-02-01", "Q6") == q("2022-02-01", "Q5") == (14.4, 26.5, 16.8, 9.6, 7.5)
    assert q("2022-03-01", "Q6") != q("2022-03-01", "Q5")
    with (REPO_ROOT / "data" / "processed" / "nbk" / "inflation_expectations.csv").open(encoding="utf-8") as f:
        scalar = {r["date"]: float(r["value"]) for r in csv.DictReader(f)}
    medians = {d: v for (d, _, i), v in s.items() if i == "MEDIAN.EXPECTED_12M"}
    common = sorted(set(scalar) & set(medians))
    assert len(common) > 100 and all(abs(scalar[d] - medians[d]) < 0.051 for d in common)


# ---------------------------------------------------------------- exchange rates, weights, NEER

REPORT = """<table><tr><th></th><th>Числовое значение</th><th>БЕЛОРУССКИЙ РУБЛЬ</th></tr>
<tr><td>2016-06-29</td><td>1</td><td>0.02</td></tr><tr><td>2016-06-30</td><td>100</td><td>1.72</td></tr>
<tr><td>2016-07-02</td><td>1</td><td>170.0</td></tr><tr><td>2016-07-04</td><td>1</td><td>168.0</td></tr></table>"""


def test_official_rates_per_unit_weekdays_and_precision():
    daily = nbk_fx.parse_single(REPORT)
    assert daily == {"2016-06-30": 0.0172, "2016-07-04": 168.0}      # 0.02 too coarse, 2016-07-02 is a Saturday
    restated = nbk_fx.redenominate("BYN", daily)
    assert restated["2016-06-30"] == pytest.approx(172.0) and nbk_fx.monthly_means(restated)["2016-07-01"] == 168.0


def test_comtrade_basket_sums_partners_over_codes():
    answers = [{"data": [{"flowCode": "M", "partner2Code": 0, "partnerCode": 0, "primaryValue": 10.0},
                         {"flowCode": "M", "partner2Code": 0, "partnerCode": 643, "primaryValue": 6.0}]},
               {"data": [{"flowCode": "M", "partner2Code": 0, "partnerCode": 643, "primaryValue": 1.0},
                         {"flowCode": "X", "partner2Code": 0, "partnerCode": 156, "primaryValue": 99.0}]}]
    assert comtrade.basket_values(answers) == {0: 10.0, 643: 7.0}


def test_neer_weights_follow_euro_adoption_and_renormalise():
    imports = {("CONSUMER", 0, 2014): 100.0, ("CONSUMER", 643, 2014): 50.0, ("CONSUMER", 440, 2014): 10.0,
               ("CONSUMER", 440, 2015): 10.0, ("CONSUMER", 0, 2015): 10.0, ("CONSUMER", 4, 2014): 40.0}
    shares, coverage = neer_import.weights(imports)
    assert shares[("CONSUMER", 2014)] == {"RUB": 1.0}                 # Lithuania adopts the euro in 2015
    assert shares[("CONSUMER", 2015)] == {"EUR": 1.0} and coverage[("CONSUMER", 2014)] == 50.0


def test_neer_chain_is_a_weighted_geometric_mean_up_is_appreciation():
    months = [f"2020-{m:02d}-01" for m in range(1, 13)] + ["2021-01-01"]
    rates = {"USD": {m: 400.0 for m in months}, "RUB": {m: 5.0 for m in months}}
    rates["RUB"]["2021-01-01"] = 5.5                                   # the rouble gains 10% against the tenge
    w = {2019: {"USD": 0.5, "RUB": 0.5}, 2020: {"USD": 0.5, "RUB": 0.5}}
    index = neer_import.chain(rates, w)
    assert index["2020-06-01"] == pytest.approx(100.0)
    assert index["2021-01-01"] == pytest.approx(100 * math.exp(0.5 * math.log(5.0 / 5.5)))


def test_neer_tracks_the_nbk_neer():
    ours = {d[:7]: v for (d, _, i), v in _dims("NEER_IMPORT_WEIGHTED").items() if i == "NEER_TOTAL"}
    with (REPO_ROOT / "data" / "processed" / "nbk" / "neer.csv").open(encoding="utf-8") as f:
        nbk = {r["date"][:7]: float(r["value"]) for r in csv.DictReader(f)}
    ks = sorted(set(ours) & set(nbk))
    a = [math.log(ours[k2] / ours[k1]) for k1, k2 in zip(ks, ks[1:])]
    b = [math.log(nbk[k2] / nbk[k1]) for k1, k2 in zip(ks, ks[1:])]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    corr = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    assert len(ks) > 150 and corr > 0.7


# ---------------------------------------------------------------- ГФСС 5-СО

def test_gfss_recognises_the_form_by_content_and_checks_the_total():
    rows = [["Приложение 1"], [], ["Сведения о суммах социальных отчислений и пени … в июне 2021 года"], [],
            ["Области, города", "Сумма", "Пеня", "Число участников"]]
    regions = ["Акмолинская", "Актюбинская", "Алматинская", "Атырауская", "Восточно-Казахстанская", "Жамбылская",
               "Западно-Казахстанская", "Карагандинская", "Кызылординская", "Костанайская", "Мангистауская",
               "Павлодарская", "Северо-Казахстанская", "Туркестанская", "г. Алматы", "г.Астана", "г. Шымкент"]
    rows += [[r, 1000.0, 1.0, 10.0] for r in regions] + [["Регион не определен", 500.0, 0.5, 5.0], ["Итого:", 17500.0, 17.5, 175.0]]
    d, recs = gfss.parse(_xlsx({"5-СО рус. ": rows}))
    out = {(r["region"], r["item_code"]): r["value"] for r in recs}
    assert d == "2021-06-01" and out[("national", "CONTRIBUTIONS")] == 17.5 and out[("AKM", "PARTICIPANTS")] == 10.0
    assert out[("national", "CONTRIBUTIONS_UNALLOCATED")] == 0.5
    rows[-1] = ["Итого:", 18000.0, 17.5, 175.0]
    with pytest.raises(validation.StructuralChangeError, match="regions sum"):
        gfss.parse(_xlsx({"5-СО рус. ": rows}))


def test_gfss_candidate_file_names():
    html = "".join(f'<a href="/documents/{i}/{n}">' for i, n in enumerate([
        "6january2016_x.xls", "7january2016_y.xls", "5-%D1%81%D0%BE_-_%D0%98%D1%8E%D0%BD%D1%8C_2022%D0%B3.xls",
        "5-%D1%81%D0%BE_-_1_%D0%BA%D0%B2._2026%D0%B3.xls", "6year2016_z.xlsx"]))
    assert [ym for _, ym in gfss.candidates(html)] == [(2016, 1), (2022, 6)]


def test_social_contributions_published_totals():
    s = _dims("SOCIAL_CONTRIBUTIONS_BY_REGION")
    assert s[("2026-08-01", "national", "CONTRIBUTIONS")] == pytest.approx(85112.25, abs=0.01)   # 85.11 bn KZT
    assert s[("2026-08-01", "national", "PARTICIPANTS")] == pytest.approx(5254.319)
    assert s[("2016-01-01", "national", "PARTICIPANTS")] == pytest.approx(2959.81)


# ---------------------------------------------------------------- local budgets by region

@pytest.mark.parametrize("title, code", [
    ("ИСПОЛНЕНИЕ БЮДЖЕТА АКМОЛИНСКОЙ ОБЛАСТИ", "AKM"), ("ВОСТ-КАЗАХСТАНСКАЯ ОБЛАСТЬ", "VKO"),
    ("ЗАП-КАЗАХСТАНСКАЯ ОБЛАСТЬ", "ZKO"), ("ГОРОДА АСТАНЫ", "AST"), ("ГОРОД АЛМАТЫ", "ALA"), ("ОБЛАСТЬ АБАЙ", "ABY"),
    ("МАНГИСТАУСКОЙ ОБЛАСТИ", "MNG")])
def test_region_titles(title, code):
    assert minfin_regions._region_of([[title]])[0] == code


def test_budget_and_transfer_lines():
    rows = [["I. КІРІСТЕР", 10.0, "I. ДОХОДЫ"], ["", 2.0, "  индивидуальный подоходный налог"],
            ["", 4.0, "Поступления трансфертов"], ["", 9.0, "II. ЗАТРАТЫ"], ["", 3.0, "   4. Образование"],
            ["", 1.0, "   6. Социальная помощь и социальное обеспечение"], ["", "-", "III. ЧИСТОЕ БЮДЖЕТНОЕ КРЕДИТОВАНИЕ"]]
    lines = minfin_regions.budget_lines(rows, 1)
    assert lines["REV"][1] == 10.0 and lines["REV.PIT"][1] == 2.0 and lines["EXP.04"] == ("Образование", 3.0)
    assert lines["EXP.06"][1] == 1.0 and lines["NET_LENDING"][1] == 0.0
    t = [["", 5.0, "Бюджетные изъятия из местных бюджетов"], ["", 3.0, "Бюджетное изъятие из бюджета города Алматы"],
         ["", 2.0, "Бюджетное изъятие из областного бюджета Атырауской области"],
         ["", 7.0, "Субвенции из республиканского бюджета"], ["", 7.0, "Туркестанская область"], ["", 1.0, "Итого"]]
    assert minfin_regions.transfer_lines(t, 1) == [("national", "WITHDRAWALS", 5.0), ("ALA", "WITHDRAWALS", 3.0),
                                                   ("ATY", "WITHDRAWALS", 2.0), ("national", "SUBVENTIONS", 7.0),
                                                   ("TRK", "SUBVENTIONS", 7.0)]


def test_regional_budgets_add_up_and_match_the_bulletin():
    b = _dims("REGIONAL_BUDGETS_YTD")
    # Jan-Jul 2026: subventions 3 246.1 bn KZT, of which Turkestan 656.4; Almaty city withdrawal 319.3
    assert b[("2026-07-01", "national", "SUBVENTIONS")] == pytest.approx(3246064.9664, abs=0.01)
    assert b[("2026-07-01", "TRK", "SUBVENTIONS")] == pytest.approx(656378.063, abs=0.01)
    assert b[("2026-07-01", "ALA", "WITHDRAWALS")] == pytest.approx(319312.21, abs=0.01)
    known = {"2020-02-01", "2021-02-01", "2021-03-01"}          # source_issues regional_budgets_*
    checked = 0
    for d in {d for d, r, i in b if r == "national" and i == "REV"} - known:
        regions = {r for (dd, r, i) in b if dd == d and i == "REV" and r != "national"}
        # 2022-09 … 2024-07: three new regions not printed (source_issues regional_budgets_new_regions_2022_2024)
        if not "2022-09-01" <= d <= "2024-07-01" and len(regions) >= 16:
            parts = sum(b[(d, r, "REV")] for r in regions)
            assert parts == pytest.approx(b[(d, "national", "REV")], rel=0.005), d
            checked += 1
    assert checked > 100


def test_edition_period_is_the_latest_and_december_uses_the_report_column():
    body = [["I. КІРІСТЕР", 1.0, 2.0, "I. ДОХОДЫ"]]
    july = {"табл 12.1": [["АКМОЛИНСКАЯ ОБЛАСТЬ"], ["Атауы", "қантар-шілде/январь-июль отчет 2025", "январь-июль отчет 2026", "Наименование"]] + body}
    d, recs, _ = minfin_regions.edition_records(july)
    assert d == "2026-07-01" and recs[0]["value"] == 2.0
    december = {"табл 12.1": [["АКМОЛИНСКАЯ ОБЛАСТЬ"], ["Атауы", "2022 ж. есеп/ 2022 г. отчет", "2\xa0023 ж. есеп/ 2018 г. отчет", "Наименование"]] + body,
                "табл 18": [["Атауы", "январь - декабрь 2\xa0023 г. отчет", "x", "Наименование"],
                            ["", 5.0, None, "Субвенции из республиканского бюджета"], ["", 5.0, None, "Акмолинская область"]]}
    d, recs, _ = minfin_regions.edition_records(december)
    out = {(r["region"], r["item_code"]): r["value"] for r in recs}
    assert d == "2023-12-01" and out[("AKM", "REV")] == 2.0 and out[("AKM", "SUBVENTIONS")] == 5.0
