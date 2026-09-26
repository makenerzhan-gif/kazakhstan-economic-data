"""National Fund receipts by tax (2026-09-26): the Minfin report parsed by row label, the
identities, the period from the heading, the year-to-date -> annual convention, and the
KGD history (its own identity, and the December overlap rule)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import minfin  # noqa: E402
import load_nf_receipts_history as kgd  # noqa: E402

TAXES = [("corporate income tax", 1300317125.0), ("excess profits tax", 34645454.0), ("bonuses ", 1236374.0),
         ("tax on production of useful minerals ", 899223359.0), ("rent tax on export", 356851131.0),
         ("portion of  the Republic of Kazakhstan under the production sharing", 1045387278.0),
         ("additional payment made by mineral resource user carrying on activity under a production sharing contract",
          87575369.0)]


def _report(heading="STATEMENT OF RECEIPTS AND APPLICATION OF THE NATIONAL FUND \nOF THE REPUBLIC OF KAZAKHSTAN AS OF 1  JANUARY  2026",
            direct=3725236090.0, extra_rows=(), taxes=TAXES):
    rows = [[heading], ["№ ", "Name", "Sum, thousands of Tenge"], [1.0, 2.0, 3.0],
            ["1.", "National Fund's Means as of the Beginning of the Reporting Period, total:", 34730106884.0],
            ["2.", "Receipts, total:", 3770297032.0], [None, "including:"],
            [None, "       - direct taxes levied on oil sector enterprises (except for taxes to the local budgets)", direct],
            [None, "including:"]]
    rows += [[None, label, v] for label, v in taxes]
    rows += list(extra_rows)
    rows += [[None, "       -  оther receipts from operations carried out by  the oil sector organizations", 19461793.0],
             [None, "administrative fines, sanctions, penalties imposed by central state bodies", 1745189.0],
             [None, "other fines and penalties levied on oil sector enterprises", 4704710.0],
             [None, "received from users of natural resourses under  compensatary action", 10484017.0],
             [None, "other nontax receipts from oil sector organizations", 2527877.0],
             [None, "       - proceeds from the sale of agricultural land plots", 1131821.0],
             [None, "proceeds from the privatization of republican property", 1284415.0],
             [None, "     - proceeds from the privatization of republican property", " "],
             [None, "     - receipts from the transfer to the competitive environment of assets of national holdings", 23000000.0],
             [None, "return of the guaranteed transfer from the republican budget"],
             ["3.", "Application, total:", 5778483949.0], [None, "including:"],
             [None, "     - guaranteed transfers  ", 2000000000.0], [None, "     - targeted transfers", 3250000000.0],
             ["4.", "Investment income, TOTAL:     ", 4614369396.0],
             ["8.", "Fund's assets at the end of the reporting period, total:", 37335632220.0]]
    return rows


def test_lines_are_found_by_label_and_the_identities_hold():
    got = minfin.parse_nf_report(_report())
    assert got["NF_OIL_CIT_YTD"] == 1300317125.0 and got["NF_MET_YTD"] == 899223359.0
    assert got["NF_PSA_SHARE_YTD"] == 1045387278.0
    assert got["NF_OIL_OTHER_RECEIPTS_YTD"] == 19461793.0            # «оther» with a Cyrillic «о»
    assert got["NF_PRIVATIZATION_YTD"] == 1284415.0 + 23000000.0      # two lines, a blank duplicate
    assert got["NF_INVESTMENT_INCOME_YTD"] == 4614369396.0            # item 4 of the annual layout
    assert got["NF_TRANSFERS_YTD"] == 5250000000.0
    assert got["NF_OIL_RECEIPTS_YTD"] == 3725236090.0 + 19461793.0
    assert "NF_GUARANTEED_TRANSFER_YTD" in got and got["NF_GUARANTEED_TRANSFER_YTD"] == 2000000000.0
    assert minfin.nf_identity_errors(got) == []


def test_parsing_does_not_depend_on_row_positions():
    moved = _report(extra_rows=[[None, "- repayment of budget loans issued from the republican budget", 182913.0]],
                    taxes=list(reversed(TAXES)))
    moved = [[None], [None]] + moved                                   # two blank rows on top
    assert {k: v for k, v in minfin.parse_nf_report(moved).items() if k != "_OTHER_OIL_ITEMS_SUM"} == \
        {k: v for k, v in minfin.parse_nf_report(_report()).items() if k != "_OTHER_OIL_ITEMS_SUM"}


def test_russian_sheet_and_a_blank_line_is_zero():
    rows = [["ОТЧЕТ О ПОСТУПЛЕНИЯХ И ИСПОЛЬЗОВАНИИ НАЦИОНАЛЬНОГО ФОНДА РЕСПУБЛИКИ КАЗАХСТАН НА 1 НОЯБРЯ 2023 ГОДА "],
            ["2.", "Поступления, всего:", 100.0],
            [None, " - прямые налоги от организации нефтяного сектора", 60.0],
            [None, "корпоративный подоходный налог", 10.0], [None, "налог на сверхприбыль", 10.0], [None, "бонусы "],
            [None, "налог на добычу полезных ископаемых ", 10.0], [None, "рентный налог на экспорт", 10.0],
            [None, "доля Республики Казахстан по разделу продукции по  заключенным контрактам", 10.0],
            [None, "Дополнительный платеж недропользователя, осуществляющего деятельность", 10.0],
            [None, " - инвестиционные доходы от управления Фондом *", 7.0],
            ["3.", "Использование, всего:", 5.0], [None, " - гарантированные трансферты", 5.0],
            [None, " - целевые трансферты"]]
    got = minfin.parse_nf_report(rows)
    assert minfin.nf_report_period(rows) == (2023, 10)
    assert got["NF_BONUSES_YTD"] == 0.0 and got["NF_TARGETED_TRANSFERS_YTD"] == 0.0
    assert got["NF_INVESTMENT_INCOME_YTD"] == 7.0
    assert minfin.nf_identity_errors(got) == []


def test_identity_failure_is_reported():
    got = minfin.parse_nf_report(_report(direct=3725236090.0 + 5000.0))
    assert minfin.nf_identity_errors(got) and "seven taxes" in minfin.nf_identity_errors(got)[0]
    rows = _report()
    del rows[8]                                                          # corporate income tax line gone
    assert "missing lines" in minfin.nf_identity_errors(minfin.parse_nf_report(rows))[0]


@pytest.mark.parametrize("heading,period", [
    ("... AS OF 1 MARCH 2018", (2018, 2)), ("... AS OF 1 JANUARY 2026", (2025, 12)),
    ("... AS OF 1 OKTOBER 2019", (2019, 9)), ("... AS OF 1 JULE 2022", (2022, 6)), ("... AS OF 1MARCH 2021", (2021, 2)),
    ("... AS OF 1 FEB 2018", (2018, 1)), ("... AS OF 2018", (2018, 12)), ("... as of March 1, 2025", (2025, 2)),
    ("... НА 1 ЯНВАРЯ 2020 ГОДА", (2019, 12)), ("... НА 1 МАЯ 2019 ГОДА", (2019, 4)), ("... НА 1 МАРТА 2024 ГОДА", (2024, 2)),
])
def test_period_is_the_month_before_the_as_of_date(heading, period):
    assert minfin.nf_report_period([["STATEMENT ... NATIONAL FUND " + heading]]) == period


def test_ytd_december_is_the_annual_value(monkeypatch):
    """Series are dated by the last month covered: the report as of 1 January is December, i.e.
    the calendar-year total; the report as of 1 February is January alone."""
    reports = {"as of 1 January 2026": (2025, 12), "as of 1 February 2026": (2026, 1)}
    for text, period in reports.items():
        assert minfin.nf_report_period([[f"STATEMENT ... NATIONAL FUND {text}"]]) == period
    ytd = {(2025, m): 100.0 * m for m in range(1, 13)}
    discrete = {m: ytd[(2025, m)] - ytd.get((2025, m - 1), 0.0) for m in range(1, 13)}
    assert sum(discrete.values()) == ytd[(2025, 12)]


def test_history_is_added_only_when_decembers_agree():
    recent = {(2018, 1): 90.0, (2018, 12): 3200.0, (2019, 12): 2800.0}
    history = {(2017, 11): 700.0, (2017, 12): 780.0, (2018, 1): 80.0, (2018, 12): 3200.0, (2019, 12): 2800.0}
    add, note = minfin.nf_merge_history(recent, history)
    assert add == {(2017, 11): 700.0, (2017, 12): 780.0}
    assert "2 shared Decembers" in note and "0 of 1 shared months are equal" in note
    history[(2019, 12)] = 2810.0
    add, note = minfin.nf_merge_history(recent, history)
    assert add == {} and "December 2019" in note


def test_kgd_workbook_identity_and_label_rows():
    rows = [["Поступление налогов и платежей в Национальный фонд"], [None, "тыс.тенге"],
            [None, None, "январь", "январь-февраль", "январь-декабрь"],
            [None, "Налоговые поступления"],
            [101105, "Корпоративный подоходный налог с юридических лиц-организаций нефт. сектора", 10.0, 20.0, 100.0],
            [101106, "Корпоративный подоходный налог с юридических лиц-резидентов", 1.0, 2.0, 10.0],
            [None, "Роялти от организаций сырьевого сектора", 5.0, 5.0, 5.0],
            [105328, "Доля РК по разделу прод. по закл. контр. от организаций", None, 3.0, 30.0],
            [None, "ИТОГО по налоговым поступлениям", 16.0, 30.0, 145.0]]
    got, bad = kgd.parse_kgd_sheet(rows)
    assert bad == []
    assert got["NF_OIL_CIT_YTD"] == {1: 11.0, 2: 22.0, 12: 110.0}
    assert got["NF_PSA_SHARE_YTD"] == {1: 0.0, 2: 3.0, 12: 30.0}
    assert "NF_MET_YTD" not in got                                          # no such line that year: missing, not zero
    rows[-1][4] = 999.0                                                     # December fails the identity
    got, bad = kgd.parse_kgd_sheet(rows)
    assert bad == [12] and all(v == {} for v in got.values())               # the whole workbook is dropped


def test_kgd_year_of_each_workbook_comes_from_the_page_text():
    page = ("<h3>2024 год</h3><a href='x'>x</a><p>2024</p><a href=\"/sites/default/files/nalogi_rus__12.xlsx\">"
            "Поступление налогов и платежей в Нацфонд по видам налогов и платежей</a>"
            "<a href=\"/sites/default/files/regiony_rus__10.xlsx\">в разрезе регионов</a>"
            "<p>2023</p><a href=\"https://kgd.gov.kz/sites/default/files/nalogi_rus_okt_1.xlsx\">"
            "Поступление налогов и платежей в Нацфонд по видам налогов и платежей</a>")
    assert kgd.list_workbooks(page) == {2024: "https://kgd.gov.kz/sites/default/files/nalogi_rus__12.xlsx",
                                        2023: "https://kgd.gov.kz/sites/default/files/nalogi_rus_okt_1.xlsx"}
