"""The PDF editions of the Minfin Statistical Bulletin (2005-2012): fetchers/minfin_pdf.py turns words with their
place on the page into the sheets the spreadsheet readers expect. Synthetic pages, then the loaded history."""
import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from fetchers import minfin, minfin_classification as mc, minfin_pdf as mp  # noqa: E402
from lib import dims  # noqa: E402

CENTRES = [50, 70, 92, 115, 220, 338, 460]          # the numbering row «1 … 7»: four code columns, name, value, name
EDGE, NAME = 360.0, 365.0


def _word(text, left, top, width=None):
    width = 4.45 * len(text) if width is None else width
    return (left, left + width, top, text)


def _centred(text, centre, top):
    return _word(text, centre - 2.2 * len(text), top)


def _number(text, top, edge=EDGE):
    """Digit groups right-aligned at the edge, as pdftotext gives them: one word per group."""
    out, right = [], edge
    for group in reversed(text.split()):
        out.insert(0, (right - 4.45 * len(group), right, top, group))
        right -= 4.45 * len(group) + 2.2
    return out


def _row(top, codes, value, name, kazakh="Атау"):
    line = [_centred(c, CENTRES[i], top) for i, c in enumerate(codes) if c]
    line.append(_word(kazakh, 127.8, top))
    if value is not None:
        line += _number(value, top)
    x = NAME
    for w in name.split():
        line.append(_word(w, x, top))
        x += 4.45 * len(w) + 2.2
    return line


def _page(rows, first=True):
    words = []
    if first:
        words += [_word("Таблица", 480, 30), _word("4", 520, 30)]
        for i, w in enumerate("ПОСТУПЛЕНИЯ В ГОСУДАРСТВЕННЫЙ БЮДЖЕТ".split()):
            words.append(_word(w, 200 + 70 * i, 55))
        words += [_word("(млн.", 515, 71), _word("тенге)", 534, 71), _word("Специфика", 104, 84),
                  _word("2008ж.", 325, 97), _word("январь-", 324, 124), _word("октябрь", 323, 133), _word("отчет", 339, 142)]
    words += [_centred(str(i + 1), c, 168) for i, c in enumerate(CENTRES)]
    for line in rows:
        words += line
    return words


def _table():
    y = iter(range(178, 800, 10))
    return [
        _row(next(y), [None] * 4, "1 300", "ПОСТУПЛЕНИЯ"),
        _row(next(y), [None] * 4, None, "в том числе:"),
        _row(next(y), [None] * 4, "1 300", "ДОХОДЫ"),
        _row(next(y), ["1", None, None, None], "1 300", "Налоговые поступления"),
        _row(next(y), [None, "01", None, None], "1 300", "Подоходный налог"),
        _row(next(y), [None, None, "1", None], "1 300", "Корпоративный подоходный налог"),
        _row(next(y), [None, None, None, "01"], "1 000", "Корпоративный подоходный налог с юридических"),
        _row(next(y), [None] * 4, None, "лиц-резидентов"),
        # a number inside the Kazakh name («2005 жылға дейін») is neither a code nor the value
        [*_row(next(y), [None, None, None, "02"], "300", "Налог до 2005 года"), _word("2005", 276.5, 258, 17.8)],
    ]


def test_a_page_of_words_becomes_the_receipts_sheet_and_adds_up():
    found = mp.tables([_page(_table())])
    assert list(found) == ["4"]
    pages = found["4"]
    assert mp.classify(mp._title(pages), mp._header(pages)) == "табл 4"
    assert mp.period_of(mp._report_cell(pages)) == (2008, 10)
    sheet = mp.receipt_sheet(pages, "2008 ж. есеп / январь-октябрь отчет 2008 г.")
    body = [r for r in sheet[2:]]
    assert [r[5] for r in body] == [1300.0, 1300.0, 1300.0, 1300.0, 1300.0, 1000.0, 300.0]
    assert body[0][6] == "ПОСТУПЛЕНИЯ" and body[5][6] == "Корпоративный подоходный налог с юридических лиц-резидентов"
    assert body[5][:4] == [None, "01", "1", "01"] or body[5][3] == "01"       # the specific carries its class and subclass
    minfin.BULLETIN_ARCHIVE = True
    try:
        d, records, notes = mc.receipts_edition({"табл 4": sheet}, {"id": "BUDGET_RECEIPTS_BY_CODE_YTD"})
    finally:
        minfin.BULLETIN_ARCHIVE = False
    by = {r["item_code"]: r["value"] for r in records}
    assert d == "2008-10-01" and by["STATE.TOTAL"] == 1300.0 and by["STATE.101101"] == 1000.0 and by["STATE.101102"] == 300.0, notes


def test_a_misread_value_is_caught_by_the_sums_and_not_excused_as_incomplete():
    rows = _table()
    rows[6] = _row(238, [None, None, None, "01"], "900", "Корпоративный подоходный налог с юридических")
    pages = mp.tables([_page(rows)])["4"]
    sheet = mp.receipt_sheet(pages, "2008 ж. есеп / январь-октябрь отчет 2008 г.")
    minfin.BULLETIN_ARCHIVE = True
    try:
        _, records, notes = mc.receipts_edition({"табл 4": sheet}, {"id": "BUDGET_RECEIPTS_BY_CODE_YTD"})
    finally:
        minfin.BULLETIN_ARCHIVE = False
    # the spreadsheet editions of 2015-2018 may keep such a subclass as «INCOMPLETE»; a table of whole millions may not
    assert not [r for r in records if r["item_code"].startswith("STATE.")] and any(n.startswith("SKIPPED STATE") for n in notes)


def test_rounding_of_whole_millions_is_allowed_for_but_not_more():
    lines = [("TOTAL", "", 10.0), ("REVENUE", "", 10.0), ("1", "", 10.0), ("101", "", 10.0), ("1011", "", 10.0),
             ("101101", "", 3.0), ("101102", "", 3.0), ("101103", "", 3.0)]             # 3.4 + 3.4 + 3.4 = 10.2 printed as 3, 3, 3 and 10
    assert mc.check_receipts(lines) == []
    assert mc.check_receipts(lines[:-1] + [("101103", "", 0.0)])                        # three short: not rounding
    decimals = [(c, n, 10.5) for c, n, _ in lines[:5]] + lines[5:]                      # printed with decimals: no allowance (1.5 off)
    assert mc.check_receipts(decimals)


def test_small_reading_rules():
    assert mp._join("Поступления от продажи финансовых акти-", "вов государства") == "Поступления от продажи финансовых активов государства"
    assert mp._join("на развитие инженерно-", "коммуникационной инфраструктуры") == "на развитие инженерно-коммуникационной инфраструктуры"
    assert mp.period_of("2008ж. қантар есеп/январь 2008г. отчет") == (2008, 1)
    assert mp.period_of("2011ж. есеп/ 2011г. отчет") == (2011, 12)
    assert mp.repair_encoding("Òàáëèöà 4 ÏÎÑÒÓÏËÅÍÈß") == "Таблица 4 ПОСТУПЛЕНИЯ"
    assert mp.classify("ИСПОЛНЕНИЕ РЕСПУБЛИКАНСКОГО БЮДЖЕТА ПО ВЕДОМСТВЕННОЙ КЛАССИФИКАЦИИ РАСХОДОВ (млн. тенге)", "Подкласс") is None
    assert mp.classify("ИСПОЛНЕНИЕ РЕСПУБЛИКАНСКОГО БЮДЖЕТА ПО ЭКОНОМИЧЕСКОЙ КЛАССИФИКАЦИИ РАСХОДОВ", "") == "табл 10"


def _scalar(name):
    path = REPO / "data" / "processed" / "minfin" / f"{name}.csv"
    return {r["date"][:7]: float(r["value"]) for r in csv.DictReader(path.open(encoding="utf-8")) if r.get("value")} if path.exists() else {}


def test_loaded_history_2005_2012_agrees_with_the_independent_series():
    rows = [r for r in dims.load_processed("BUDGET_RECEIPTS_BY_CODE_YTD") if r["date"] < mc.OLD_CLASSIFICATION_BEFORE]
    if not rows:
        pytest.skip("history before 2013 not loaded")
    revenue = {r["date"][:7]: float(r["value"]) for r in rows if r["item_code"] == "STATE.REVENUE"}
    assert len(revenue) >= 80 and min(revenue) == "2005-01"
    checked = 0
    for name in ("state_budget_revenue", "state_budget_revenue_ytd"):               # annual from 2008, year-to-date from 2011-08
        for month, value in _scalar(name).items():
            if month in revenue:
                assert revenue[month] == pytest.approx(value, abs=1.0), (name, month)
                checked += 1
    assert checked >= 8
    # the subsoil lines of RESOURCE_PAYMENTS_YTD are rows of the same table
    met = {r["date"]: float(r["value"]) for r in dims.load_processed("RESOURCE_PAYMENTS_YTD")
           if r["item_code"] == "MET_NON_OIL" and r["date"] < mc.OLD_CLASSIFICATION_BEFORE}
    code = {r["date"]: float(r["value"]) for r in rows if r["item_code"] == "STATE.105306"}
    assert len(met) >= 15 and all(code[d] == v for d, v in met.items())


def test_the_old_economic_classification_is_a_dataset_of_its_own():
    old = dims.load_processed("BUDGET_EXPENDITURE_ECONOMIC_2005_2012_YTD")
    new = dims.load_processed("BUDGET_EXPENDITURE_ECONOMIC_YTD")
    if not old or not new:
        pytest.skip("processed files absent")
    assert max(r["date"] for r in old) < mc.OLD_CLASSIFICATION_BEFORE <= min(r["date"] for r in new)
    assert not any("GFS" in r["item_code"] for r in old)                      # the bridge is written for the codes of 2013 on
    names = {r["item_code"]: r["item_name"] for r in old if r["date"] == "2012-12-01"}
    assert "Приобретение товаров" in names["STATE.130"]                       # from 2013 the code 130 is wages of certain categories
    for budget in ("STATE", "REP"):
        by_date: dict = {}
        for r in old:
            if r["item_code"].startswith(budget + "."):
                by_date.setdefault(r["date"], {})[r["item_code"].split(".", 1)[1]] = float(r["value"])
        assert len(by_date) >= 85
        for date, v in by_date.items():
            cats = [x for c, x in v.items() if c.startswith("CAT")]
            assert abs(sum(cats) - v["TOTAL"]) <= 0.5 * len(cats) + 1, (budget, date)
