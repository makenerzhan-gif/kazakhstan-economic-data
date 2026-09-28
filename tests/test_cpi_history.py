"""National CPI and its food / non-food / paid-services groups before Taldau (1991-01 ..
2010-12): the loader's parsers on small fixtures shaped like the three BNS sources, the checks
on the committed reference file, and the splice into CPI / CPI_YTD / CPI_YOY and CPI_FOOD /
CPI_NONFOOD / CPI_SERVICES (+ _YOY). No network.

Tolerances. Each published index is rounded to 0.1, so a product of k of them can miss a
published index I by up to I * sum(0.05 / v_i) + 0.05 (load_cpi_history.rounding_bound):
0.3-0.7 index points in a year of 5-20% inflation, 14 points on 1992's 3060.8. That bound
is the test. The gaps actually seen, for the record:
  - chain of mom vs December ytd: at most 0.37 pp in 1995-2010 (2005: 107.87 vs 107.5), the
    same size as on Taldau itself (2023: 110.14 vs 109.8) -- 0.1-0.2 pp is typical, not a limit;
    1991-1994 at most 0.24% of the index (1993: 2269.8 vs 2265.0).
  - product of twelve mom vs yoy: at most 0.40 pp in 1996-2010, 5.4 points on 1994's 2000+.
  - February 1993: BNS prints mom 131.9 in both publications while its own ytd implies 131.7;
    KNOWN_SLACK allows those 0.2 points and nothing else.
  - the groups: chain of mom vs December ytd at most 0.38 pp in 1995-2010 (FOOD 1999), 0.26% of
    the index in 1991-1994 (NONFOOD 1993); twelve mom vs yoy at most 0.40 pp from 1996 (FOOD
    2000-02), 0.30% in 1994-1995 (NONFOOD 1994-02). No group needs a KNOWN_SLACK.
"""
import csv
import io
import math
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import load_cpi_history as L  # noqa: E402
from fetchers import bns  # noqa: E402
from lib import validation  # noqa: E402

REFERENCE = REPO_ROOT / "data" / "reference" / "bns_cpi_history.csv"


# ---------------------------------------------------------------- fixtures: the docx

def _docx(parts: list) -> bytes:
    """A minimal docx: strings are paragraphs, lists of rows are tables."""
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = []
    for p in parts:
        if isinstance(p, str):
            body.append(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>")
        else:
            rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r)
                           + "</w:tr>" for r in p)
            body.append(f"<w:tbl>{rows}</w:tbl>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document {w}><w:body>{''.join(body)}</w:body></w:document>")
    return buf.getvalue()


ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
TITLE = "Тұтыну тауарлары мен қызметтердің бағасы және тарифтерінің индексіИндекс цен и тарифов на потребительские товары и услуги"


MOM_LABEL = "өткен айға пайызбенв процентах к предыдущему месяцу"
TABLE_1_1 = [["", "Барлық тауарлар мен қызметтерВсе товары и услуги", "Азық-түлік тауарларыПродовольственные товары",
              "Азық-түлік емес тауарларНепродовольственные товары", "Ақылы қызметтерПлатные услуги"],
             ["1991", "247,1", "204,7", "301,6", "200,9"], ["1992", "3 060,8", "2 108,3", "3 897,8", "3 019,7"]]


def _collection(table_1_1=TABLE_1_1, groups=True) -> bytes:
    """The 1991-2021 docx in miniature: contents, 1.1 (Dec/Dec by item), 1.2 (a December 1995
    base, not read), 1.3 (all, m/m), 1.4-1.6 (food, non-food, services, m/m), 1.7 (Dec/Dec by
    division, not read)."""
    parts = [
        "Содержание", [["1.1 Индекс цен ... 3", ""], ["1.3 Индекс цен ... 5", ""]],
        "1. Тұтыну нарығындағы бағалар индексі және орташа бағалар Индекс цен и средние цены на потребительском рынке",
        f"1.1 {TITLE}", "кезең соңына, өткен жылғы желтоқсанға пайызбенна конец периода, в процентах к декабрю предыдущего года",
        table_1_1,
        "1.2 ... Индекс цен и тарифов на потребительские товары и платные услуги",
        "на конец периода, в процентах, декабрь 1995г.=100",
        [["", "Все товары и услуги"], ["1996", "128,7"]],
        f"1.3 {TITLE}", MOM_LABEL,
        [[""] + ROMAN, ["1992", "312,3", "121,0"] + ["100,0"] * 10, ["2021", "100,6"] + ["100,5"] * 11],
    ]
    if groups:
        parts += [
            "1.4 Азық-түлік тауарлары бағасының индексіИндекс цен на продовольственные товары", MOM_LABEL,
            [[""] + ROMAN, ["1992", "356,4"] + ["101,0"] * 11],
            "1.5 Азық-түлік емес тауарлар бағасының индексіИндекс цен на непродовольственные товары", MOM_LABEL,
            [[""] + ROMAN, ["1992", "264,0"] + ["102,0"] * 11],
            "1.6 Ақылы қызметтердің бағасының индексіИндекс цен на платные услуги", MOM_LABEL,
            [[""] + ROMAN, ["1992", "286,9"] + ["103,0"] * 11],
        ]
    parts += [
        f"1.7 {TITLE}", "кезең соңына, өткен жылғы желтоқсанға пайызбенна конец периода, в процентах к декабрю предыдущего года",
        [["", "2000", "2001"], ["Барлық тауарлар мен қызметтер", "109,8", "106,4"]],
    ]
    return _docx(parts)


def test_docx_tables_1_1_and_1_3_to_1_6_found_by_title():
    got = L.parse_docx(_collection())
    assert got["TOTAL"]["decdec"] == {"1991-12-01": 247.1, "1992-12-01": 3060.8}
    assert got["FOOD"]["decdec"] == {"1991-12-01": 204.7, "1992-12-01": 2108.3}
    assert got["NONFOOD"]["decdec"]["1992-12-01"] == 3897.8 and got["SERVICES"]["decdec"]["1991-12-01"] == 200.9
    tot = got["TOTAL"]["mom"]
    assert tot["1992-01-01"] == 312.3 and tot["1992-02-01"] == 121.0
    assert tot["2021-01-01"] == 100.6 and len(tot) == 24                  # not the food table 1.4
    assert got["FOOD"]["mom"]["1992-01-01"] == 356.4 and len(got["FOOD"]["mom"]) == 12
    assert got["NONFOOD"]["mom"]["1992-01-01"] == 264.0 and got["NONFOOD"]["mom"]["1992-12-01"] == 102.0
    assert got["SERVICES"]["mom"]["1992-01-01"] == 286.9 and got["SERVICES"]["mom"]["1992-06-01"] == 103.0


def test_docx_without_the_tables_is_an_error():
    with pytest.raises(L.SourceError):
        L.parse_docx(_docx(["Содержание", [["a", "b"]]]))
    with pytest.raises(L.SourceError, match="FOOD mom"):              # no group tables 1.4-1.6
        L.parse_docx(_collection(groups=False))
    with pytest.raises(L.SourceError, match="table 1.1"):             # a group column missing from 1.1
        L.parse_docx(_collection(table_1_1=[r[:4] for r in TABLE_1_1]))


# ---------------------------------------------------------------- fixtures: the 1991-2000 pdf

# The pdf's text layer as pypdf gives it: Cyrillic labels in a broken font encoding, numbers
# clean except that a leading «1» may be split off («1 13,3»).
MOM, YTD, YOY = "Œ ïðåäßäóøåìó ìåæÿöó", "Œ äåŒàÆðþ ïðåäßäóøåªî ªîäà", "Œ æîîòâåòæòâóþøåìó ìåæÿöó ïðåäßäóøåªî ªîäà"
MONTHS = ["ßíâàðü", "Ôåâðàºü", "Ìàðò", "Àïðåºü", "ÌàØ", "¨þíü", "¨þºü", "Àâªóæò", "ÑåíòÿÆðü", "˛ŒòÿÆðü", "˝îÿÆðü", "˜åŒàÆðü"]
PAGE_BREAK = ["41", "Öåíß â ˚àçàıæòàíå â 1991-2000 ªª.", "ïðîäîºæåíŁå", "´æå òîâàðß Ł óæºóªŁ ˇðîäîâîºüæòâåí-",
              "íßå òîâàðß", "ˇºàòíßå óæºóªŁ"]


def _fmt(v: float) -> str:
    s = f"{v:.1f}".replace(".", ",")
    return "1 " + s[1:] if s.startswith("11") else s         # 112,7 comes out as «1 12,7»


def _pdf_lines(break_inside: int = 1995) -> tuple[list[str], dict]:
    """Ten years of the table built from a constant 1% (1991-1993) / 0.5% monthly rise."""
    lines = ["¨íäåŒæß öåí Ł òàðŁôîâ íà ïðîäîâîºüæòâåííßå,", "â ïðîöåíòàı"]
    expect = {"mom": {}, "ytd": {}, "yoy": {}}
    for y in range(1991, 2001):
        lines.append(str(y))
        r = 101.0 if y < 1994 else 100.5
        blocks = [(MOM, [r] * 12), (YTD, [round(100 * (r / 100) ** m, 1) for m in range(1, 13)])]
        if y >= 1994:
            blocks.append((YOY, [round(100 * (r / 100) ** 12, 1)] * 11 + [blocks[1][1][-1]]))
        for (label, vals), ms in zip(blocks, ("mom", "ytd", "yoy")):
            lines.append(label)
            for m, v in enumerate(vals, 1):
                if y == break_inside and ms == "ytd" and m == 8:
                    lines += PAGE_BREAK
                lines.append(f"{MONTHS[m - 1]} {_fmt(v)} {_fmt(v + 1)} {_fmt(v - 1)} 100,0")
                expect[ms][f"{y}-{m:02d}-01"] = v
    lines += ["¨íäåŒæß öåí Ł òàðŁôîâ íà ïîòðåÆŁòåºüæŒŁå òîâàðß Ł óæºóªŁ â 1992-2000ªª.", "1000", "1500", "2000"]
    return lines, expect


def test_pdf_row_values_join_split_numbers():
    assert L.row_values("Ôåâðàºü 1 13,3 109,0 120,1 105,7") == [113.3, 109.0, 120.1, 105.7]
    assert L.row_values("Àïðåºü 579,1 507,8 588,1 1 133,1") == [579.1, 507.8, 588.1, 1133.1]
    assert L.row_values("˜åŒàÆðü 3060,8 2108,3 3897,8 3019,7") == [3060.8, 2108.3, 3897.8, 3019.7]
    assert L.row_values("1992 1993 1994") is None and L.row_values("41") is None


def test_pdf_table_read_by_structure_across_a_page_break():
    lines, expect = _pdf_lines()
    got = L.parse_pdf_table(lines)
    assert got["TOTAL"] == expect
    assert min(got["TOTAL"]["yoy"]) == "1994-01-01" and len(got["TOTAL"]["mom"]) == len(got["TOTAL"]["ytd"]) == 120
    # the other three columns: food, non-food, paid services (the fixture prints v+1, v-1, 100.0)
    for ms in L.MEASURES:
        assert got["FOOD"][ms] == {d: round(v + 1, 1) for d, v in expect[ms].items()}
        assert got["NONFOOD"][ms] == {d: round(v - 1, 1) for d, v in expect[ms].items()}
        assert set(got["SERVICES"][ms].values()) == {100.0} and got["SERVICES"][ms].keys() == expect[ms].keys()


def test_pdf_table_missing_row_is_an_error():
    lines, _ = _pdf_lines()
    i = lines.index("1996") + 5                         # a mom row of 1996
    with pytest.raises(L.SourceError):
        L.parse_pdf_table(lines[:i] + lines[i + 1:])


def test_pdf_table_unlabelled_block_is_an_error():
    lines, _ = _pdf_lines()
    j = lines.index(YTD, lines.index("1997"))
    with pytest.raises(L.SourceError):
        L.parse_pdf_table(lines[:j] + lines[j + 1:])


# ---------------------------------------------------------------- fixtures: 1999-2004 editions

LAYOUT_A = """##### FILE 168457/in/1051562/ipc5.txt
                            Индекс потребительских цен
                  по Республике Казахстан за  май   1999 года
----------------------------------------------------------------------------------------------------
                      :                 Май 1999 года в процентах к декабрю 1998 года
                      :-----------------------------------------------------------------------------
                      :  Все   :Продукты:Hепродо-:Плат- :Одежда,:Товары
                      : товары :питания,:вольст- :ные   :обувь  : для
-----------------------------------------------------------------------------------------------------
Республика Казахстан      106.6    107.8    106.9  103.7   104.3  111.3
Акмолинская               103.5    103.7    103.2  103.3    98.3  109.8
##### FILE 168457/in/1051562/ipc6.txt
----------------------------------------------------------------------------------------------------
                      :                 Май 1999 года в процентах к апрелю 1999 года
                      :-----------------------------------------------------------------------------
                      :  Все   :Продукты:Hепродо-:Плат- :Одежда,:Товары
                      : товары :питания,:вольст- :ные   :обувь  : для
-----------------------------------------------------------------------------------------------------
Республика Казахстан      101.4    101.7    101.2  101.2   100.6  101.7
----------------------------------------------------------------------------------------------------
                      :                 Май 1999 года в процентах к маю 1998 года
                      :-----------------------------------------------------------------------------
                      :  Все   :Продукты:Hепродо-:Плат- :Одежда,:Товары
                      : товары :питания,:вольст- :ные   :обувь  : для
-----------------------------------------------------------------------------------------------------
Республика Казахстан      103.9    101.1    106.6  107.7   105.5  111.2
"""

LAYOUT_B = ("##### FILE osi/1055761.html\n    Таблица \n  Индекс    потребительских цен по Республике Казахстан \n"
            "     В марте 2001г.  \t  \n   (в процентах) \t      \n \t       Март    2001г. к \t       Январь-март    2001г.\n"
            "    к январю-марту \n    2000г. \t       I    квартал 2001г. к \n    IV кварталу 2000г. \t  \n"
            "          февралю    2001г. \t       декабрю    2000г. \t       марту    2000г. \t  \n"
            "          Все товары и услуги \t       100.7 \t       102.5 \t       109.6 \t       108.9 \t       103.1 \t  \n"
            "            Продукты    питания, напитки и табачные изделия \t       101.3 \t       104.0 \t       113.1 \n"
            "            Одежда, обувь и    ткани \t       100.6 \t       101.4 \t       107.0 \t       106.7 \t       101.7 \t  \n"
            "            Hепродовольственные    товары \t       100.2 \t       100.6 \t       106.5 \t       106.3 \t       101.2 \t  \n"
            "            Платные услуги \t       100.2 \t       101.4 \t       105.6 \t       105.6 \t       101.7 \t  \n"
            "  Лист 2\n           Индекс    потребительских цен по Республике Казахстан  \t  \n"
            "          Продукты питания \t       101.5 \t       104.5 \t       114.4 \t       112.7 \t       105.3 \t  \n")

# December 2002 heads its December/December column «декабрю 2002г.» (a typo for 2001)
LAYOUT_B_DEC_2002 = ("##### FILE osi/1051443.html\n   \xa0 \xa0 в процентах       Агентство Республики Казахстан по статистике   \n"
                     "           Индекс    потребительских цен в Республике Казахстан \t  \n         \xa0 \t   \xa0в процентах \t\n \t\n"
                     "      \xa0\t       Декабрь    2002г. к \t       Январь-\n    декабрь 2002г.\n    к январю-\n    декабрю 2001г. \t"
                     "       IV    квартал 2002г. к III кварталу \n    2001г \t       IV    квартал к 2002г. к\n     IV кварталу\n"
                     "    2000г \t  \n          ноябрю\n     2002г. \t       декабрю\n     2002г. \t  \n"
                     "    Все товары и услуги \t     101,4 \t     106,6 \t     105,9 \t     101,7 \t     106,2 \t\n")


def test_edition_layout_a_1999():
    text = L.edition_text([("a/ipc5.txt", LAYOUT_A.encode("cp1251"))])
    assert L.parse_html_edition(text, 1999, 5) == {
        "TOTAL": {"mom": 101.4, "ytd": 106.6, "yoy": 103.9}, "FOOD": {"mom": 101.7, "ytd": 107.8, "yoy": 101.1},
        "NONFOOD": {"mom": 101.2, "ytd": 106.9, "yoy": 106.6}, "SERVICES": {"mom": 101.2, "ytd": 103.7, "yoy": 107.7}}


def test_edition_layout_a_checks_the_column_order():
    swapped = LAYOUT_A.replace(":Продукты:Hепродо-:", ":Hепродо-:Продукты:", 1)
    with pytest.raises(L.SourceError, match="layout A header"):
        L.parse_html_edition(L.edition_text([("a/ipc5.txt", swapped.encode("cp1251"))]), 1999, 5)


def test_edition_layout_b_2001_skips_the_average_and_quarter_columns():
    text = L.edition_text([("osi/1055761.html", LAYOUT_B.encode("cp1251"))])
    assert L.parse_html_edition(text, 2001, 3) == {
        "TOTAL": {"mom": 100.7, "ytd": 102.5, "yoy": 109.6}, "FOOD": {"mom": 101.3, "ytd": 104.0, "yoy": 113.1},
        "NONFOOD": {"mom": 100.2, "ytd": 100.6, "yoy": 106.5}, "SERVICES": {"mom": 100.2, "ytd": 101.4, "yoy": 105.6}}


def test_edition_layout_b_december_2002_header_typo():
    text = L.edition_text([("osi/1051443.html", LAYOUT_B_DEC_2002.encode("cp1251"))])
    assert L.parse_html_edition(text, 2002, 12) == {"TOTAL": {"mom": 101.4, "ytd": 106.6, "yoy": 106.6}}


def test_edition_text_decodes_cp866_and_joins_hyphenated_months():
    raw = "<html><td>Май 1999 года в процентах к де-\n   кабрю 1998 года</td></html>".encode("cp866")
    text = L.edition_text([("x.htm", raw)])
    assert "к декабрю 1998 года" in text


# ---------------------------------------------------------------- assembling

def _sources():
    docx = {"TOTAL": {"mom": {"1992-01-01": 312.3, "2011-01-01": 101.7}, "decdec": {"1992-12-01": 3060.8, "1991-12-01": 247.1}},
            "FOOD": {"mom": {"1992-01-01": 356.4}, "decdec": {"1995-12-01": 158.7}}}
    pdf = {"TOTAL": {"mom": {"1992-01-01": 312.3}, "ytd": {"1992-01-01": 312.3, "1992-12-01": 3060.8}, "yoy": {"1994-01-01": 2430.3}},
           "FOOD": {"mom": {"1992-01-01": 356.4}, "ytd": {"1995-12-01": 158.7}, "yoy": {"1995-12-01": 158.7}}}
    eds = {(2005, 3): ("168380", {"TOTAL": {"mom": 100.6, "ytd": 101.9, "yoy": 107.3}, "FOOD": {"mom": 100.4}})}
    return docx, pdf, eds


def test_assemble_prefers_the_docx_names_the_other_sources_and_marks_the_overlap():
    rows = {(r["item"], r["date"], r["measure"]): r for r in L.assemble(*_sources())}
    r = rows[("TOTAL", "1992-01-01", "mom")]
    assert r["value"] == 312.3 and "17216" in r["source_url"] and "element 21933" in r["source_note"]
    assert r["source_note"].startswith("«Цены в Казахстане за 1991-2021 годы» (С-18-Г, BNS 2022), docx, table 1.3 ")
    assert rows[("TOTAL", "1992-12-01", "ytd")]["source_url"].endswith("/17216/file/ru/")
    assert ("TOTAL", "1992-12-01", "yoy") not in rows and ("TOTAL", "1991-12-01", "yoy") not in rows   # yoy from 1994-01
    assert rows[("TOTAL", "2005-03-01", "yoy")]["source_url"] == "https://stat.gov.kz/api/iblock/element/168380/file/ru/"
    assert "overlap with Taldau" in rows[("TOTAL", "2011-01-01", "mom")]["source_note"]
    food = rows[("FOOD", "1992-01-01", "mom")]
    assert food["value"] == 356.4 and "table 1.4 " in food["source_note"] and "element 21933" in food["source_note"]
    assert "column «Продовольственные товары»" in rows[("FOOD", "1995-12-01", "yoy")]["source_note"]
    assert rows[("FOOD", "2005-03-01", "mom")]["value"] == 100.4
    # TOTAL rows first, then the groups in ITEMS order
    items = [r["item"] for r in L.assemble(*_sources())]
    assert items == sorted(items, key=L.ITEMS.index)


def test_assemble_stops_when_two_sources_disagree():
    docx, pdf, eds = _sources()
    pdf["TOTAL"]["mom"]["1992-01-01"] = 312.4
    with pytest.raises(L.SourceError, match="TOTAL 1992-01-01 mom"):
        L.assemble(docx, pdf, eds)
    docx, pdf, eds = _sources()
    pdf["FOOD"]["ytd"]["1995-12-01"] = 158.8
    with pytest.raises(L.SourceError, match="FOOD 1995-12-01 ytd"):
        L.assemble(docx, pdf, eds)


def test_assemble_keeps_a_documented_difference_as_the_docx_prints_it():
    docx, pdf, eds = _sources()
    docx["FOOD"]["mom"]["2004-06-01"] = 100.0
    eds[(2004, 6)] = ("168399", {"FOOD": {"mom": 99.9}})
    with pytest.raises(L.SourceError, match="FOOD 2004-06-01 mom"):
        L.assemble(docx, pdf, eds, printed_differences={})
    rows = {(r["item"], r["date"], r["measure"]): r for r in L.assemble(docx, pdf, eds)}
    r = rows[("FOOD", "2004-06-01", "mom")]
    assert r["value"] == 100.0 and "17216" in r["source_url"]
    assert "printed differently in element 168399 (edition): 99.9" in r["source_note"]
    # an entry whose sources print the same number is stale and stops the load
    eds[(2004, 6)] = ("168399", {"FOOD": {"mom": 100.0}})
    with pytest.raises(L.SourceError, match="match no difference"):
        L.assemble(docx, pdf, eds)


def test_consistency_catches_a_misread_column():
    mom = {f"2005-{m:02d}-01": 100.5 for m in range(1, 13)}
    ytd = {d: round(100 * 1.005 ** int(d[5:7]), 1) for d in mom}
    assert L.check_consistency(mom, ytd, {}) == []
    ytd["2005-06-01"] = 102.0                            # 103.0 misread
    assert L.check_consistency(mom, ytd, {}) == ["2005-06-01: chain of mom 103.04 vs ytd 102.0"]


# ---------------------------------------------------------------- the committed reference file

GROUPS = ("FOOD", "NONFOOD", "SERVICES")


@pytest.fixture(scope="module")
def reference_rows():
    with REFERENCE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def reference(reference_rows):
    return reference_rows, {ms: L.series(reference_rows, ms) for ms in L.MEASURES}


def _item(rows, item):
    return {ms: L.series(rows, ms, item=item) for ms in L.MEASURES}


def test_reference_columns_dates_and_coverage(reference):
    rows, _ = reference
    assert list(rows[0]) == L.FIELDS
    assert all(r["date"][8:] == "01" and r["source_url"].startswith("https://stat.gov.kz/api/iblock/element/")
               and r["source_note"] for r in rows)
    assert len({(r["item"], r["date"], r["measure"]) for r in rows}) == len(rows)
    assert L.check_coverage(rows) == []   # every item: mom, ytd 1991-01..2010-12; yoy 1994-01..2010-12
    assert {r["item"] for r in rows} == set(L.ITEMS)
    assert all(sum(r["item"] == item for r in rows) == 838 for item in L.ITEMS)
    overlap = [r for r in rows if r["date"] >= L.HISTORY_END]
    assert overlap and all("overlap with Taldau" in r["source_note"] for r in overlap)
    assert all(r["measure"] == "mom" or r["date"][5:7] == "12" for r in overlap)
    # TOTAL first, then the groups
    assert [r["item"] for r in rows] == sorted((r["item"] for r in rows), key=L.ITEMS.index)


def test_reference_december_on_december(reference):
    _, s = reference
    dec = {y: s["ytd"][f"{y}-12-01"] for y in range(1991, 2011)}
    assert dec == {1991: 247.1, 1992: 3060.8, 1993: 2265.0, 1994: 1258.3, 1995: 160.3, 1996: 128.7,
                   1997: 111.2, 1998: 101.9, 1999: 117.8, 2000: 109.8, 2001: 106.4, 2002: 106.6,
                   2003: 106.8, 2004: 106.7, 2005: 107.5, 2006: 108.4, 2007: 118.8, 2008: 109.5,
                   2009: 106.2, 2010: 107.8}
    assert all(s["yoy"][f"{y}-12-01"] == dec[y] for y in range(1994, 2011))


@pytest.mark.parametrize("item, expect", [
    ("FOOD", {1991: 204.7, 1992: 2108.3, 1993: 2297.1, 1994: 1155.7, 1995: 158.7, 1996: 116.4, 1997: 106.0,
              1998: 99.4, 1999: 120.6, 2000: 112.8, 2007: 126.6, 2010: 110.1}),
    ("NONFOOD", {1991: 301.6, 1992: 3897.8, 1993: 1795.6, 1994: 1159.9, 1995: 133.5, 1996: 107.4, 1997: 102.7,
                 1998: 100.0, 1999: 119.8, 2000: 106.1, 2007: 110.5, 2010: 105.5}),
    ("SERVICES", {1991: 200.9, 1992: 3019.7, 1993: 4143.4, 1994: 2522.6, 1995: 258.0, 1996: 239.3, 1997: 138.8,
                  1998: 109.2, 1999: 109.9, 2000: 107.1, 2007: 115.4, 2010: 106.8}),
])
def test_reference_groups_december_on_december(reference_rows, item, expect):
    s = _item(reference_rows, item)
    assert {y: s["ytd"][f"{y}-12-01"] for y in expect} == expect
    assert all(s["yoy"][f"{y}-12-01"] == s["ytd"][f"{y}-12-01"] for y in range(1994, 2011))


def test_reference_1999(reference):
    _, s = reference
    assert [s["mom"][f"1999-{m:02d}-01"] for m in range(1, 13)] == \
        [100.9, 99.8, 99.8, 104.6, 101.4, 104.8, 101.1, 99.7, 100.7, 100.7, 101.7, 101.7]   # the tenge floated in April
    assert [s["yoy"][f"1999-{m:02d}-01"] for m in (1, 3, 4, 5, 12)] == [101.0, 98.8, 102.8, 103.9, 117.8]
    assert s["ytd"]["1999-05-01"] == 106.6 and s["ytd"]["1999-11-01"] == 115.9
    assert s["yoy"]["1994-01-01"] == 2430.3 and s["mom"]["1991-04-01"] == 161.0


def test_reference_groups_1999_and_the_first_months(reference_rows):
    food, nonfood, services = (_item(reference_rows, g) for g in GROUPS)
    assert [food["mom"][f"1999-{m:02d}-01"] for m in range(1, 13)] == \
        [101.0, 99.7, 99.7, 105.7, 101.7, 106.6, 100.6, 98.8, 100.3, 100.6, 102.1, 102.7]
    assert [nonfood["mom"][f"1999-{m:02d}-01"] for m in range(1, 13)] == \
        [99.9, 99.7, 99.7, 106.5, 101.2, 104.4, 100.9, 101.0, 101.8, 101.2, 101.3, 100.9]
    assert [services["mom"][f"1999-{m:02d}-01"] for m in range(1, 13)] == \
        [101.6, 100.1, 100.1, 100.6, 101.2, 101.1, 102.4, 100.6, 100.4, 100.2, 101.1, 100.1]
    # the pdf's first rows (1991) and the 1992 liberalisation (docx tables 1.4-1.6)
    assert (food["mom"]["1991-01-01"], nonfood["mom"]["1991-01-01"], services["mom"]["1991-01-01"]) == (104.3, 109.3, 102.8)
    assert (food["mom"]["1991-04-01"], nonfood["mom"]["1991-04-01"], services["mom"]["1991-04-01"]) == (154.8, 170.3, 148.3)
    assert (food["mom"]["1992-01-01"], nonfood["mom"]["1992-01-01"], services["mom"]["1992-01-01"]) == (356.4, 264.0, 286.9)
    assert (food["yoy"]["1994-01-01"], nonfood["yoy"]["1994-01-01"], services["yoy"]["1994-01-01"]) == (2683.2, 1733.4, 4012.2)


def test_reference_food_june_2004_kept_as_the_docx_prints_it(reference_rows):
    r = next(r for r in reference_rows if (r["item"], r["date"], r["measure"]) == ("FOOD", "2004-06-01", "mom"))
    assert float(r["value"]) == 100.0 and "/17216/" in r["source_url"]
    assert "printed differently in element 168399 (edition): 99.9" in r["source_note"]
    noted = [r for r in reference_rows if "printed differently" in r["source_note"]]
    assert len(noted) == len(L.PRINTED_DIFFERENCES) == 1


def test_reference_identities_within_rounding(reference):
    _, s = reference
    assert L.check_consistency(s["mom"], s["ytd"], s["yoy"]) == []
    # without the documented February 1993 slack exactly those months fail
    bad = L.check_consistency(s["mom"], s["ytd"], s["yoy"], known_slack={})
    assert bad and all(p.startswith("1993-0") for p in bad)


@pytest.mark.parametrize("item", GROUPS)
def test_reference_groups_identities_within_rounding(reference_rows, item):
    s = _item(reference_rows, item)
    assert L.check_consistency(s["mom"], s["ytd"], s["yoy"], item=item) == []
    assert L.check_consistency(s["mom"], s["ytd"], s["yoy"], known_slack={}) == []      # no slack needed


# (item, pp from 1995, relative 1991-1994): the largest gaps seen, rounded up
CHAIN_TOLERANCE = {"TOTAL": (0.4, 0.0025), "FOOD": (0.4, 0.0015), "NONFOOD": (0.25, 0.003), "SERVICES": (0.3, 0.0025)}
YOY_TOLERANCE = {"TOTAL": (0.5, 0.004), "FOOD": (0.5, 0.004), "NONFOOD": (0.35, 0.004), "SERVICES": (0.4, 0.004)}


@pytest.mark.parametrize("item", L.ITEMS)
def test_reference_mom_chain_reproduces_december(reference_rows, item):
    s = _item(reference_rows, item)
    pp, rel = CHAIN_TOLERANCE[item]
    for y in range(1991, 2011):
        chain = math.prod(s["mom"][f"{y}-{m:02d}-01"] / 100 for m in range(1, 13)) * 100
        dec = s["ytd"][f"{y}-12-01"]
        if y >= 1995:
            assert abs(chain - dec) <= pp, (y, chain, dec)             # pp; TOTAL seen at most 0.37 (2005)
        else:
            assert abs(chain / dec - 1) <= rel, (y, chain, dec)        # hyperinflation: relative


@pytest.mark.parametrize("item", L.ITEMS)
def test_reference_yoy_is_the_product_of_twelve_mom(reference_rows, item):
    s = _item(reference_rows, item)
    pp, rel = YOY_TOLERANCE[item]
    for d, v in s["yoy"].items():
        prod = math.prod(s["mom"][L._prev(d, k)] / 100 for k in range(12)) * 100
        if d >= "1996-01-01":
            assert abs(prod - v) <= pp, (d, prod, v)                    # pp; TOTAL seen at most 0.40 (2005)
        else:
            assert abs(prod / v - 1) <= rel, (d, prod, v)               # 1994-1995: relative


def _processed(name):
    path = REPO_ROOT / "data" / "processed" / "bns" / f"{name}.csv"
    if not path.exists():
        pytest.skip(f"{path} missing")
    with path.open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f)}


def test_seam_with_taldau_2011():
    """The first Taldau year against the reference file's last: 2011 year on year from twelve
    mom across the seam, and from ytd(2011) / ytd(2010) * Dec/Dec 2010."""
    with REFERENCE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    mom = {**L.series(rows, "mom"), **{d: v for d, v in _processed("cpi").items() if d >= L.HISTORY_END}}
    ytd = {**L.series(rows, "ytd"), **{d: v for d, v in _processed("cpi_ytd").items() if d >= L.HISTORY_END}}
    yoy = {d: v for d, v in _processed("cpi_yoy").items() if "2011-01-01" <= d <= "2011-12-01"}
    assert len(yoy) == 12
    assert L.check_consistency(mom, ytd, yoy) == []


@pytest.mark.parametrize("item", GROUPS)
def test_seam_with_taldau_2011_groups(reference_rows, item):
    """Taldau's 2011 year on year of each group against twelve mom across the seam (the
    groups have no since-December series on Taldau; the file's own ytd covers 2010)."""
    name = f"cpi_{item.lower()}"
    mom = {**L.series(reference_rows, "mom", item=item),
           **{d: v for d, v in _processed(name).items() if d >= L.HISTORY_END}}
    yoy = {d: v for d, v in _processed(f"{name}_yoy").items() if "2011-01-01" <= d <= "2011-12-01"}
    assert len(yoy) == 12
    assert L.check_consistency(mom, L.series(reference_rows, "ytd", item=item), yoy, item=item) == []


# ---------------------------------------------------------------- the splice in the fetcher

def _taldau():
    return [{"date": "2011-01-01", "value": 101.7}, {"date": "2011-02-01", "value": 101.5}]


def test_splice_prepends_history_and_leaves_taldau_alone():
    history = {"2010-11-01": 101.1, "2010-12-01": 100.9, "2011-01-01": 101.7}
    records = _taldau()
    out, note = bns.splice_cpi_history("CPI", records, history)
    assert out == [{"date": "2010-11-01", "value": 101.1}, {"date": "2010-12-01", "value": 100.9}] + _taldau()
    assert records == _taldau() and "equal to Taldau on all 1 months" in note


def test_splice_never_replaces_or_extends_past_2011():
    # a reference month after Taldau's end is not added; one before Taldau's start but after 2010 neither
    history = {"2010-12-01": 100.9, "2011-02-01": 101.5, "2011-03-01": 999.0}
    out, _ = bns.splice_cpi_history("CPI", _taldau(), history)
    assert [r["date"] for r in out] == ["2010-12-01", "2011-01-01", "2011-02-01"]
    assert out[-1]["value"] == 101.5


def test_splice_stops_on_a_disagreement():
    history = {"2010-12-01": 100.9, "2011-01-01": 101.8}
    with pytest.raises(validation.StructuralChangeError, match="shared months differ"):
        bns.splice_cpi_history("CPI", _taldau(), history)
    with pytest.raises(validation.StructuralChangeError, match="(?s)bns/CPI_FOOD .*shared months differ"):
        bns.splice_cpi_history("CPI_FOOD", _taldau(), history)


def test_splice_stops_without_overlap_or_with_a_gap():
    with pytest.raises(validation.StructuralChangeError, match="no month in common"):
        bns.splice_cpi_history("CPI", _taldau(), {"2010-12-01": 100.9})
    later = [{"date": "2012-01-01", "value": 100.4}, {"date": "2012-02-01", "value": 100.6}]
    with pytest.raises(validation.StructuralChangeError, match="does not join"):
        bns.splice_cpi_history("CPI", later, {"2010-12-01": 100.9, "2012-02-01": 100.6})
    with pytest.raises(validation.StructuralChangeError, match="missing"):
        bns.splice_cpi_history("CPI", _taldau(), {})


def test_load_cpi_history_reads_one_item(tmp_path):
    path = tmp_path / "h.csv"
    path.write_text("date,item,measure,value,source_url,source_note\n"
                    "2010-12-01,TOTAL,mom,100.9,u,n\n2010-12-01,FOOD,mom,101.3,u,n\n2010-12-01,FOOD,yoy,110.1,u,n\n",
                    encoding="utf-8")
    assert bns.load_cpi_history("mom", path) == {"2010-12-01": 100.9}                 # TOTAL by default
    assert bns.load_cpi_history("mom", path, item="FOOD") == {"2010-12-01": 101.3}
    assert bns.load_cpi_history("yoy", path, item="NONFOOD") == {}                    # -> the splice stops
    assert bns.load_cpi_history("mom", tmp_path / "absent.csv") == {}


def test_group_fetcher_splices_the_group_history(monkeypatch):
    """_fetch_cpi_group prepends the group's own rows (m/m -> mom, y/y -> yoy) and stops when
    they differ from Taldau; the utilities groups, without history, are left alone."""
    calls = []

    def fake_taldau(index_id, indicator_id, note, **kw):
        calls.append(kw["terms"])
        return _taldau(), {"note": note}

    def fake_history(measure, path=None, item="TOTAL"):
        return {("mom", "FOOD"): {"2010-12-01": 100.9, "2011-01-01": 101.7},
                ("yoy", "SERVICES"): {"2010-12-01": 106.8, "2011-02-01": 999.0}}.get((measure, item), {})

    monkeypatch.setattr(bns, "_fetch_taldau_annual_index", fake_taldau)
    monkeypatch.setattr(bns, "load_cpi_history", fake_history)
    records, manifest = bns.fetch_cpi_food()
    assert [r["date"] for r in records] == ["2010-12-01", "2011-01-01", "2011-02-01"]
    assert "Before 2011: 1991-01 onward" in manifest["note"] and "History: 2010-12..2010-12 (1 months)" in manifest["note"]
    with pytest.raises(validation.StructuralChangeError, match="bns/CPI_SERVICES_YOY"):
        bns.fetch_cpi_services_yoy()
    with pytest.raises(validation.StructuralChangeError, match="missing"):
        bns.fetch_cpi_nonfood()                                        # no NONFOOD rows in the fake file
    records, manifest = bns.fetch_cpi_utilities()
    assert records == _taldau() and "History" not in manifest["note"]


@pytest.mark.parametrize("name, item, measure, start", [
    ("cpi", "TOTAL", "mom", "1991-01-01"), ("cpi_ytd", "TOTAL", "ytd", "1991-01-01"), ("cpi_yoy", "TOTAL", "yoy", "1994-01-01"),
    ("cpi_food", "FOOD", "mom", "1991-01-01"), ("cpi_food_yoy", "FOOD", "yoy", "1994-01-01"),
    ("cpi_nonfood", "NONFOOD", "mom", "1991-01-01"), ("cpi_nonfood_yoy", "NONFOOD", "yoy", "1994-01-01"),
    ("cpi_services", "SERVICES", "mom", "1991-01-01"), ("cpi_services_yoy", "SERVICES", "yoy", "1994-01-01"),
])
def test_splice_with_the_committed_file_against_the_stored_taldau_series(name, item, measure, start):
    path = REPO_ROOT / "data" / "processed" / "bns" / f"{name}.csv"
    if not path.exists():
        pytest.skip(f"{path} missing")
    with path.open(encoding="utf-8") as f:
        stored = [{"date": r["date"], "value": float(r["value"])} for r in csv.DictReader(f)]
    taldau = [r for r in stored if r["date"] >= bns.CPI_HISTORY_END]
    history = bns.load_cpi_history(measure, item=item)
    out, note = bns.splice_cpi_history(name.upper(), taldau, history)
    assert out[0]["date"] == start and out[len(out) - len(taldau):] == taldau
    dates = [r["date"] for r in out]
    assert dates == sorted(set(dates))
    shared = 132 if measure == "mom" else 11                         # every docx month / the Decembers 2011-2021
    assert f"equal to Taldau on all {shared} months" in note
    assert out == stored                                             # the stored series is exactly the splice
