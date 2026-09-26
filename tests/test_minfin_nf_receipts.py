"""National Fund receipts by tax (2026-09-26): the Minfin report parsed by row label, the
four identities, the period from the heading, the document fixes (period override, line
exclusion, values against the wrong labels), the latest posting winning, the archived
reports read from disk, December = the year, and the KGD history (its own identity, and
the December overlap rule)."""
import csv
import io
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import minfin  # noqa: E402
import load_nf_receipts_history as kgd  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "minfin"
TAXES = [("corporate income tax", 1300317125.0), ("excess profits tax", 34645454.0), ("bonuses ", 1236374.0),
         ("tax on production of useful minerals ", 899223359.0), ("rent tax on export", 356851131.0),
         ("portion of  the Republic of Kazakhstan under the production sharing", 1045387278.0),
         ("additional payment made by mineral resource user carrying on activity under a production sharing contract",
          87575369.0)]
HEADING = "STATEMENT OF RECEIPTS AND APPLICATION OF THE NATIONAL FUND \nOF THE REPUBLIC OF KAZAKHSTAN AS OF 1  JANUARY  2026"


def _report(heading=HEADING, direct=3725236090.0, extra_rows=(), taxes=TAXES, cit_delta=0.0, privatization=1284415.0,
            investment_line=None):
    """A sheet in the 2025-2026 layout whose four identities hold (unless `direct` is set off)."""
    taxes = [(label, v + (cit_delta if i == 0 else 0.0)) for i, (label, v) in enumerate(taxes)]
    direct = direct + cit_delta
    other = [1745189.0, 4704710.0, 10484017.0, 2527877.0]
    first_level = [direct, sum(other), 1131821.0, privatization, 23000000.0, 182913.0] + \
        ([investment_line] if investment_line is not None else [])
    rows = [[heading], ["№ ", "Name", "Sum, thousands of Tenge"], [1.0, 2.0, 3.0],
            ["1.", "National Fund's Means as of the Beginning of the Reporting Period, total:", 34730106884.0],
            ["2.", "Receipts, total:", sum(first_level)], [None, "including:"],
            [None, "       - direct taxes levied on oil sector enterprises (except for taxes to the local budgets)", direct],
            [None, "including:"]]
    rows += [[None, label, v] for label, v in taxes]
    rows += list(extra_rows)
    rows += [[None, "       -  оther receipts from operations carried out by  the oil sector organizations", sum(other)],
             [None, "administrative fines, sanctions, penalties imposed by central state bodies", other[0]],
             [None, "other fines and penalties levied on oil sector enterprises", other[1]],
             [None, "received from users of natural resourses under  compensatary action", other[2]],
             [None, "other nontax receipts from oil sector organizations", other[3]],
             [None, "       - proceeds from the sale of agricultural land plots", 1131821.0],
             [None, "proceeds from the privatization of republican property", privatization],
             [None, "     - proceeds from the privatization of republican property", " "],
             [None, "     - proceeds from the sale of assets by an organization specializing in improving loan portfolios",
              23000000.0],
             [None, "proceeds from the repayment of budget loans allocated from the republican budget", 182913.0]]
    if investment_line is not None:
        rows.append([None, "investment income from Fund management *", investment_line])
    rows += [[None, "return of the guaranteed transfer from the republican budget"],
             ["3.", "Application, total:", 5778483949.0], [None, "including:"],
             [None, "     - guaranteed transfers  ", 2000000000.0], [None, "     - targeted transfers", 3250000000.0],
             [None, "     - expenditures connected with the National Fund management", 54389753.0],
             [None, "     -expenses for the payment of target claims", 474094196.0],
             ["4.", "Investment income, TOTAL:     ", 4614369396.0],
             [None, " - profit/(loss) based on management results, calculated in tenge", 6016890188.0],
             [None, " - exchange rate difference on recalculation", -1402520792.0],
             ["8.", "Fund's assets at the end of the reporting period, total:", 37335632220.0]]
    return rows


def _archived(doc_id):
    files = sorted(RAW.glob(f"minfin_nf_report_{doc_id}_*.xls*"))
    if not files:
        pytest.skip(f"archived report {doc_id} not in data/raw/minfin")
    content = files[-1].read_bytes()
    kind, wb = minfin._open_workbook(content, ".xls" if content.startswith(b"\xd0\xcf") else ".xlsx")
    return list(minfin._iter_rows(kind, wb))


def test_lines_are_found_by_label_and_the_identities_hold():
    got = minfin.parse_nf_report(_report())
    assert got["NF_OIL_CIT_YTD"] == 1300317125.0 and got["NF_MET_YTD"] == 899223359.0
    assert got["NF_PSA_SHARE_YTD"] == 1045387278.0
    assert got["NF_OIL_OTHER_RECEIPTS_YTD"] == 19461793.0            # «оther» with a Cyrillic «о»
    assert got["NF_PRIVATIZATION_YTD"] == 1284415.0                   # a second, blank privatization line
    assert got["NF_TRANSFERS_YTD"] == 5250000000.0
    assert got["NF_OIL_RECEIPTS_YTD"] == 3725236090.0 + 19461793.0
    assert got["NF_GUARANTEED_TRANSFER_YTD"] == 2000000000.0
    assert minfin.nf_identity_errors(got) == []


def test_investment_income_is_the_receipts_line_never_the_total_item():
    # the approved annual layout: item «4. Investment income, TOTAL» and no receipts line -> no value
    assert "NF_INVESTMENT_INCOME_YTD" not in minfin.parse_nf_report(_report())
    # the receipts line where there is one (the report as of 1 January 2023 has both)
    got = minfin.parse_nf_report(_report(investment_line=30299038.0))
    assert got["NF_INVESTMENT_INCOME_YTD"] == 30299038.0 and minfin.nf_identity_errors(got) == []
    # the item present and the receipts line blank (approved report for 2023) -> no value either
    rows = _report()
    rows.insert(-12, [None, "- investment income from the National Fund management*"])
    assert "NF_INVESTMENT_INCOME_YTD" not in minfin.parse_nf_report(rows)


def test_parsing_does_not_depend_on_row_positions():
    moved = _report(extra_rows=[[None, "- repayment of budget loans issued from the republican budget", None]],
                    taxes=list(reversed(TAXES)))
    moved = [[None], [None]] + moved                                   # two blank rows on top
    assert minfin.parse_nf_report(moved) == minfin.parse_nf_report(_report())


def test_russian_sheet_and_a_blank_line_is_zero():
    rows = [["ОТЧЕТ О ПОСТУПЛЕНИЯХ И ИСПОЛЬЗОВАНИИ НАЦИОНАЛЬНОГО ФОНДА РЕСПУБЛИКИ КАЗАХСТАН НА 1 НОЯБРЯ 2023 ГОДА "],
            ["2.", "Поступления, всего:", 67.0], [None, "в том числе:"],
            [None, " - прямые налоги от организации нефтяного сектора", 60.0],
            [None, "корпоративный подоходный налог", 10.0], [None, "налог на сверхприбыль", 10.0], [None, "бонусы "],
            [None, "налог на добычу полезных ископаемых ", 10.0], [None, "рентный налог на экспорт", 10.0],
            [None, "доля Республики Казахстан по разделу продукции по  заключенным контрактам", 10.0],
            [None, "Дополнительный платеж недропользователя, осуществляющего деятельность", 10.0],
            [None, " - инвестиционные доходы от управления Фондом *", 7.0],
            ["3.", "Использование, всего:", 5.0], [None, "в том числе:"], [None, " - гарантированные трансферты", 5.0],
            [None, " - целевые трансферты"]]
    got = minfin.parse_nf_report(rows)
    assert minfin.nf_report_period(rows) == (2023, 10)
    assert got["NF_BONUSES_YTD"] == 0.0 and got["NF_TARGETED_TRANSFERS_YTD"] == 0.0
    assert got["NF_INVESTMENT_INCOME_YTD"] == 7.0
    assert minfin.nf_identity_errors(got) == []


def test_each_identity_failure_is_reported():
    assert "seven taxes" in minfin.nf_identity_errors(minfin.parse_nf_report(_report(direct=3725236090.0 + 5000.0)))[0]
    rows = _report()
    rows[4][2] += 1000.0                                                 # «Receipts, total»
    assert any("Receipts, total" in e for e in minfin.nf_identity_errors(minfin.parse_nf_report(rows)))
    rows = _report()
    next(r for r in rows if len(r) > 1 and r[1] == "     - targeted transfers")[2] = 3250001000.0
    assert any("Application, total" in e for e in minfin.nf_identity_errors(minfin.parse_nf_report(rows)))
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


def test_866029_values_one_row_too_high_are_moved_back():
    rows = _archived("866029")
    raw_errors = minfin.nf_identity_errors(minfin.parse_nf_report(rows))
    assert any("Receipts, total" in e for e in raw_errors) and any("Application, total" in e for e in raw_errors)
    fixed, done = minfin.apply_nf_doc_fixes("866029", rows)
    got = minfin.parse_nf_report(fixed)
    assert done and minfin.nf_identity_errors(got) == []
    assert minfin.nf_report_period(fixed) == (2025, 6)
    assert got["NF_GUARANTEED_TRANSFER_YTD"] == 2000000000.0 and got["NF_TARGETED_TRANSFERS_YTD"] == 1120000000.0
    assert got["NF_PRIVATIZATION_YTD"] == 608178.5 and got["NF_INVESTMENT_INCOME_YTD"] == 2480802213.0
    assert got["NF_OIL_CIT_YTD"] == 496679562.1                         # rows above the defect untouched
    assert minfin.apply_nf_doc_fixes("851283", rows) == (rows, [])      # other documents: nothing done


def test_946754_bank_asset_sale_is_not_privatization():
    rows = _archived("946754")
    assert minfin.parse_nf_report(rows)["NF_PRIVATIZATION_YTD"] == 24284415.0
    fixed, done = minfin.apply_nf_doc_fixes("946754", rows)
    got = minfin.parse_nf_report(fixed)
    assert done and got["NF_PRIVATIZATION_YTD"] == 1284415.0            # Decree No. 1328, p. 4: 2.4 = 1 284 415
    assert minfin.nf_identity_errors(got) == []


def test_a_fix_is_not_applied_when_the_labels_do_not_match():
    rows = _report()
    assert minfin.apply_nf_doc_fixes("866029", rows) == (rows, [])
    assert minfin.apply_nf_doc_fixes("946754", rows)[1] == []


def test_december_of_the_ytd_series_is_the_calendar_year():
    """The report as of 1 January is the year: its seven taxes equal KGD's January-December
    column of that year (an independent annual figure), and the approved report for 2024
    equals it too. The report as of 1 February is January alone (KGD's «январь»)."""
    history = minfin.load_nf_history()
    if not history:
        pytest.skip("data/reference/nf_receipts_kgd_history.csv missing")
    for doc_id, year in (("580102", 2023), ("866047", 2024)):
        rows = _archived(doc_id)
        assert minfin.nf_report_period(rows) == (year, 12)
        got = minfin.parse_nf_report(rows)
        for ind in minfin.NF_TAX_ITEMS:
            assert got[ind] == pytest.approx(history[ind][(year, 12)], abs=minfin.NF_IDENTITY_TOLERANCE), (doc_id, ind)
    feb = next(iter(sorted(RAW.glob("minfin_nf_report_599434_*.xls*"))), None)   # as of 1 February 2024
    if feb is not None:
        rows = _archived("599434")
        assert minfin.nf_report_period(rows) == (2024, 1)
        got = minfin.parse_nf_report(rows)
        assert got["NF_PSA_SHARE_YTD"] == pytest.approx(history["NF_PSA_SHARE_YTD"][(2024, 1)], abs=2.0)


def _xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append([c for c in r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reports_override_exclusion_latest_posting_and_identity(monkeypatch):
    heading = "STATEMENT ... NATIONAL FUND OF THE REPUBLIC OF KAZAKHSTAN AS OF 1 {}"
    sheets = {
        "580102": ("2024-01-05", _report(heading.format("JANUARY 2024"), privatization=1236124.0)),
        "677412": ("2024-06-14", _report(heading.format("JANUARY 2024"), cit_delta=100.0, privatization=1289473.0)),
        "621022": ("2024-03-04", _report(heading.format("MARCH 2024"))),
        "638881": ("2024-04-03", _report(heading.format("MARCH 2024"), cit_delta=500.0)),     # really 1 April
        "999": ("2024-05-04", _report(heading.format("MAY 2024"), direct=1.0)),                # fails the identity
    }
    docs = [{"id": int(i), "created_date": c, "title": "Statement of receipts and application of the National fund",
             "full_text": [{"document": f"/uploads/{i}_original.1.xlsx"}]} for i, (c, _) in sheets.items()]
    files = {f"/uploads/{i}_original.1.xlsx": _xlsx(rows) for i, (_, rows) in sheets.items()}
    monkeypatch.setattr(minfin, "_list_all_documents", lambda **kw: docs)
    monkeypatch.setattr(minfin, "_download", lambda path: files[path])
    monkeypatch.setattr(minfin, "_nf_cached_report", lambda doc_id, path: None)
    monkeypatch.setattr(minfin.raw_store, "save_raw_bytes", lambda *a, **k: None)
    monkeypatch.setattr(minfin.raw_store, "write_download_manifest", lambda *a, **k: None)
    monkeypatch.setattr(minfin, "_NF_CACHE", {})
    data, info = minfin._nf_reports()
    cit = data["NF_OIL_CIT_YTD"]
    assert cit[(2023, 12)] == 1300317125.0 + 100.0                        # the later posting (677412) wins
    assert data["NF_PRIVATIZATION_YTD"][(2023, 12)] == 1236124.0          # ... except its excluded line
    assert cit[(2024, 2)] == 1300317125.0 and cit[(2024, 3)] == 1300317125.0 + 500.0   # 638881 -> March
    assert (2024, 4) not in cit and info["parsed"] == 4
    assert len(info["identity_failed"]) == 1 and info["identity_failed"][0].startswith("999:")
    assert info["revised_points"] >= 1 and info["downloaded"] == 5


def test_archived_report_is_read_from_disk(monkeypatch, tmp_path):
    folder = tmp_path / "minfin"
    folder.mkdir()
    content = b"\xd0\xcf\x11\xe0" + b"x" * 12
    (folder / "minfin_nf_report_5_2026-09-26.xls").write_bytes(content)
    (folder / "minfin_nf_report_6_2026-09-26.xls").write_bytes(b"<html>" + b"x" * 10)
    monkeypatch.setattr(minfin.raw_store, "RAW_ROOT", tmp_path)
    assert minfin._nf_cached_report(5, "/uploads/2026/1/6/abc_original.16.xls") == content
    assert minfin._nf_cached_report(5, "/uploads/2026/1/6/abc_original.17.xls") is None     # re-uploaded
    assert minfin._nf_cached_report(5, "/uploads/2026/1/6/abc.xls") is None                 # no size in the path
    assert minfin._nf_cached_report(6, "/uploads/x_original.16.xls") is None                # not a workbook
    assert minfin._nf_cached_report(7, "/uploads/x_original.16.xls") is None                # not archived


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
