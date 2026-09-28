#!/usr/bin/env python3
"""One-off load of the national CPI before Taldau (1991-01 .. 2010-12) from BNS's own
publications, into data/reference/bns_cpi_history.csv.

Taldau index 703076 (the CPI, CPI_YTD and CPI_YOY fetchers in scripts/fetchers/bns.py)
starts in January 2011. BNS printed the earlier months in three places, all on stat.gov.kz:

  17216   «Цены в Казахстане за 1991-2021 годы» (statistical collection С-18-Г, 2022), a zip
          with a docx: table 1.1 «в процентах к декабрю предыдущего года» (Dec/Dec, 1991-2021)
          and table 1.3 «в процентах к предыдущему месяцу» (1992-2021), all goods and services.
  21933   «Цены в Казахстане в 1991-2000 гг.» (Almaty 2001), a rar with a pdf (662845.pdf):
          «Индексы цен и тарифов на продовольственные, непродовольственные товары и платные
          услуги в 1991-2000 гг.» (pp. 39-45): per year, «к предыдущему месяцу», «к декабрю
          предыдущего года» and, from 1994, «к соответствующему месяцу предыдущего года»;
          first column = all goods and services.
  166775  «Индекс потребительских цен в Республике Казахстан», one edition per month from May
          1999 (rar archives): html text tables to June 2004, xls from July 2004 (the xls ones
          are the editions scripts/backfill_cpi_publication.py reads into CPI_DETAIL_*).

What the file holds (measure: months, first-listed source wins, every other source that
prints the same month must print the same number or the load stops):

  mom  1991-01 .. 2021-12   docx 1.3 (1992-), pdf (1991-2000), editions (1999-05 -)
  ytd  1991-01 .. 2010-12   docx 1.1 (Decembers), pdf (1991-2000), editions (1999-05 -)
  yoy  1994-01 .. 2010-12   docx 1.1 (Decembers: Dec/Dec is December's year-on-year),
                            pdf (1994-2000), editions (1999-05 -)

and, for 2011-2021, the docx's mom months and Decembers (ytd, yoy) again: those rows are the
overlap with Taldau. The fetcher prepends only months before 2011-01 and stops if any
overlap row differs from Taldau (scripts/fetchers/bns.py, splice_cpi_history). Nothing
before 1994-01 is published year-on-year, and nothing is derived here.

Checks run before the file is written (check_consistency, also in tests/test_cpi_history.py):
within each year the chain of mom reproduces ytd, and yoy equals ytd(t)/ytd(t-12)*Dec/Dec(y-1)
and the product of the last twelve mom, each within the bound that rounding every published
figure to 0.1 allows (see rounding_bound).

Run:    python scripts/load_cpi_history.py [--cache DIR]
Needs:  unar (apt install unar) for the rar archives; pypdf. The 142 archives (19 MB, 161 MB unpacked)
are cached in --cache (default: <tmp>/bns_cpi_history) and not added to data/raw.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import math
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetchers import bns, bns_cpi, bns_dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "data" / "reference" / "bns_cpi_history.csv"
FIELDS = ["date", "measure", "value", "source_url", "source_note"]
MEASURES = ("mom", "ytd", "yoy")
HISTORY_END = "2011-01-01"            # Taldau 703076 starts here
YOY_START = "1994-01-01"              # the first year-on-year month BNS printed (the 1991-2000 pdf)
DOCX_ELEMENT, PDF_ELEMENT, PUBLICATION = "17216", "21933", "166775"
FILE_URL = bns_cpi.FILE_URL           # https://stat.gov.kz/api/iblock/element/{eid}/file/ru/
EQUAL = 1e-6                          # every source prints one decimal: equal means equal

DOCX_NOTE = "«Цены в Казахстане за 1991-2021 годы» (С-18-Г, BNS 2022), docx"
PDF_NOTE = "«Цены в Казахстане в 1991-2000 гг.» (Almaty 2001), pdf pp. 39-45"
EDITION_NOTE = "«Индекс потребительских цен в Республике Казахстан» (publication 166775)"
MONTHS_RU = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
             "октябрь", "ноябрь", "декабрь")


class SourceError(ValueError):
    """A source did not read as expected, or two sources disagree."""


def _num(text: str) -> float | None:
    s = re.sub(r"[\s\xa0]", "", str(text)).replace(",", ".").rstrip("*")
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def _date(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}-01"


# ---------------------------------------------------------------- 17216: the 1991-2021 docx

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_blocks(docx: bytes):
    """('p', text) and ('t', rows of cell texts) in document order."""
    body = ET.fromstring(zipfile.ZipFile(io.BytesIO(docx)).read("word/document.xml")).find(_W + "body")
    text = lambda el: "".join(t.text or "" for t in el.iter(_W + "t"))  # noqa: E731
    for el in body:
        if el.tag == _W + "p":
            yield "p", text(el)
        elif el.tag == _W + "tbl":
            yield "t", [[re.sub(r"\s+", " ", text(tc)).strip() for tc in tr.findall(_W + "tc")]
                        for tr in el.iter(_W + "tr")]


def parse_docx(docx: bytes) -> dict[str, dict[str, float]]:
    """{'mom': {date: v}, 'decdec': {december date: v}} for all goods and services: the tables
    under the titles «1.1 ... Индекс цен и тарифов на потребительские товары и услуги» / «в
    процентах к декабрю предыдущего года» and «1.3 ...» / «в процентах к предыдущему месяцу»."""
    out: dict[str, dict[str, float]] = {"mom": {}, "decdec": {}}
    paras: list[str] = []
    for kind, x in docx_blocks(docx):
        if kind == "p":
            if x.strip():
                paras.append(re.sub(r"\s+", " ", x.strip()))
            continue
        context = " ".join(paras[-3:]).lower()
        paras = []
        title = re.search(r"\b1\.([13])\s", context)
        if not title or "потребительские товары и услуги" not in context:
            continue
        which = "decdec" if title.group(1) == "1" else "mom"
        if out[which]:
            continue
        if which == "decdec":
            if "к декабрю предыдущего года" not in context or "Все товары и услуги" not in x[0][1]:
                raise SourceError(f"docx table 1.1: unexpected header {x[0][:2]} under {context[-120:]!r}")
            for r in x[1:]:
                if re.fullmatch(r"(19|20)\d\d", r[0]) and _num(r[1]) is not None:
                    out["decdec"][_date(int(r[0]), 12)] = _num(r[1])
        else:
            if "к предыдущему месяцу" not in context or x[0][1:13] != ["I", "II", "III", "IV", "V", "VI", "VII",
                                                                      "VIII", "IX", "X", "XI", "XII"]:
                raise SourceError(f"docx table 1.3: unexpected header {x[0][:4]} under {context[-120:]!r}")
            for r in x[1:]:
                if not re.fullmatch(r"(19|20)\d\d", r[0]):
                    continue
                for month, cell in enumerate(r[1:13], 1):
                    if _num(cell) is not None:
                        out["mom"][_date(int(r[0]), month)] = _num(cell)
    if not out["mom"] or not out["decdec"]:
        raise SourceError(f"docx: tables 1.1/1.3 not found (mom {len(out['mom'])}, Dec/Dec {len(out['decdec'])})")
    return out


# ---------------------------------------------------------------- 21933: the 1991-2000 pdf

_YEAR_LINE = re.compile(r"^(199\d|2000)$")
_ROW = re.compile(r"^([^\d]+?)\s+(\d[\d ,]*)$")


def row_values(line: str) -> list[float] | None:
    """The numbers of a month row. The pdf's text layer splits some numbers after a leading
    «1» («1 13,3» is 113,3; «1 133,1» is 1133,1): every value has exactly one decimal comma, so
    a token without one is the head of the next."""
    m = _ROW.match(line.strip())
    if not m:
        return None
    vals, head = [], ""
    for tok in m.group(2).split():
        if "," not in tok:
            head += tok
            continue
        if not re.fullmatch(r"\d+,\d", head + tok):
            return None
        vals.append(float((head + tok).replace(",", ".")))
        head = ""
    return None if head else vals


def parse_pdf_table(lines: list[str]) -> dict[str, dict[str, float]]:
    """{'mom'|'ytd'|'yoy': {date: v}} from the text lines of pp. 39-45 (first column).

    The Cyrillic font of this pdf has no usable ToUnicode map, so its labels come out as
    mojibake («Œ ïðåäßäóøåìó ìåæÿöó» is «к предыдущему месяцу»); numbers are clean. The table
    is read by structure: a year line (1991 .. 2000), then blocks of twelve month rows of four
    numbers, each block introduced by a label line; a page break repeats the column header
    and may fall inside a block. Blocks are, in order, previous month / December of previous
    year / same month of previous year (the third from 1994). Checked on the way: every block
    has twelve rows, the k-th block carries the same label in every year, January mom = January
    ytd, December ytd = December yoy, and the years run 1991 .. 2000 without a gap."""
    kinds = ("mom", "ytd", "yoy")
    out: dict[str, dict[str, float]] = {k: {} for k in kinds}
    labels: dict[int, set[str]] = {}
    year, blocks, prev_line = None, [], ""
    years: list[int] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _YEAR_LINE.match(line):
            if year == 2000 and len(blocks) == 3 and len(blocks[-1][1]) == 12:
                break                                   # the chart axis of the next table
            if blocks and len(blocks[-1][1]) != 12:
                raise SourceError(f"pdf: {year} block {len(blocks)} has {len(blocks[-1][1])} rows")
            year, blocks = int(line), []
            years.append(year)
            prev_line = line
            continue
        vals = row_values(line)
        if year is None:
            prev_line = line
            continue
        if vals is None or len(vals) != 4:
            prev_line = line
            continue
        if not blocks or len(blocks[-1][1]) == 12:
            if len(blocks) == 3:
                if year == 2000:
                    break
                raise SourceError(f"pdf: a fourth block in {year} after {prev_line!r}")
            if row_values(prev_line) is not None:
                raise SourceError(f"pdf: {year}: a block starts without a label line: {line!r}")
            blocks.append((prev_line, []))
        blocks[-1][1].append(vals[0])
        if len(blocks[-1][1]) == 12:
            k = len(blocks) - 1
            labels.setdefault(k, set()).add(blocks[-1][0])
            for month, v in enumerate(blocks[-1][1], 1):
                out[kinds[k]][_date(year, month)] = v
        prev_line = line
    if years != list(range(1991, 2001)):
        raise SourceError(f"pdf: years read {years}, expected 1991 .. 2000")
    if len(out["mom"]) != 120 or len(out["ytd"]) != 120 or len(out["yoy"]) != 84:
        raise SourceError(f"pdf: {', '.join(f'{k} {len(v)}' for k, v in out.items())} months, expected 120, 120, 84")
    if any(len(v) != 1 for v in labels.values()) or len(labels) != 3:
        raise SourceError(f"pdf: block labels are not the same in every year: {labels}")
    for y in range(1991, 2001):
        if out["mom"].get(_date(y, 1)) != out["ytd"].get(_date(y, 1)):
            raise SourceError(f"pdf: {y}: January mom {out['mom'].get(_date(y, 1))} != ytd {out['ytd'].get(_date(y, 1))}")
        if _date(y, 12) in out["yoy"] and out["yoy"][_date(y, 12)] != out["ytd"][_date(y, 12)]:
            raise SourceError(f"pdf: {y}: December yoy != ytd")
    yoy_years = sorted({int(d[:4]) for d in out["yoy"]})
    if yoy_years != list(range(1994, 2001)):
        raise SourceError(f"pdf: year-on-year block in {yoy_years}, expected 1994 .. 2000")
    return out


def pdf_lines(pdf: bytes) -> list[str]:
    """Text lines of the pages holding the table (the page of «1991» + block, to 2000's)."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    pages = [p.extract_text() or "" for p in reader.pages]
    start = next((i for i, t in enumerate(pages)
                  if re.search(r"^1991\s*$", t, re.M) and re.search(r"^2000\s*$", "\n".join(pages[i:i + 8]), re.M)
                  and any(row_values(ln) and len(row_values(ln)) == 4 for ln in t.split("\n"))), None)
    if start is None:
        raise SourceError("pdf: no page with the 1991 block of the monthly CPI table")
    return "\n".join(pages[start:start + 8]).split("\n")


# ---------------------------------------------------------------- 166775: the monthly editions

_DATIVE = bns_cpi._DATIVE
_FULL_MONTHS = set(_DATIVE) | set(MONTHS_RU)
_NUM = r"(\d{2,3}[.,]\d)"


def decode_text(b: bytes) -> str:
    """An html/txt file of a 1999-2004 edition as text: cp1251, cp866 or utf-8, whichever
    reads as Cyrillic rather than box-drawing characters; tags stripped, cells tab-separated."""
    best = None
    for enc in ("cp1251", "cp866", "utf-8"):
        try:
            s = b.decode(enc)
        except UnicodeDecodeError:
            continue
        score = len(re.findall(r"[а-яА-Я]", s)) - 5 * len(re.findall(r"[╚╩╠═╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀]", s))
        if best is None or score > best[0]:
            best = (score, s)
    s = best[1] if best else b.decode("latin-1")
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>", "\n", s)
    s = re.sub(r"(?i)</t[dh]>", "\t", s)
    return html.unescape(re.sub(r"<[^>]+>", " ", s))


def edition_text(files: list[tuple[str, bytes]]) -> str:
    """All html/htm/txt files of one edition, in path order, each after a «##### FILE» line;
    month names hyphenated across header lines («де-\\n кабрю») joined again."""
    parts = [f"\n##### FILE {name}\n{decode_text(b)}" for name, b in sorted(files)
             if Path(name).suffix.lower() in (".html", ".htm", ".txt")]
    s = "".join(parts).replace("H", "Н").replace("\xa0", " ")

    def join(mt):
        return mt.group(0) if mt.group(1).lower() in _FULL_MONTHS else mt.group(1) + mt.group(2)
    return re.sub(r"([А-Яа-я]+)-[ \t]*\n\s*([а-я]+)", join, s)


def _nums(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in re.findall(r"(?<![\d.,])" + _NUM + r"(?![\d.,])", text)]


def _layout_a(text: str, y: int, m: int) -> dict[str, float]:
    """May 1999 - 2000: fixed-width tables, one comparison each («Май 1999 года в процентах к
    декабрю 1998 года»), row «Республика Казахстан», first column all goods and services."""
    out: dict[str, float] = {}
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ":" not in ln or not re.search(r"(\S+)\s+(\d{4})\s*(?:года|г\.)\s+в\s+процентах\s+к\s+(.+?\d{4})", ln):
            continue
        block = "\n".join(lines[i:i + 14])
        if "Все" not in block or "Продукты" not in block:
            continue
        measures = bns_cpi.column_measures(ln, y, m)
        for ln2 in lines[i + 1:i + 30]:
            if re.match(r"\s*Республика\s+Казахстан", ln2, re.I):
                v = _nums(ln2)
                if len(v) >= 4:
                    for ms in measures:
                        out.setdefault(ms, v[0])
                break
    return out


def _layout_b(text: str, y: int, m: int) -> dict[str, float]:
    """2001 - June 2004: one summary table, columns named in a multi-line header («Март
    2001г. к | февралю 2001г. | декабрю 2000г. | марту 2000г. | Январь-март ...»), row «Все
    товары и услуги». The January-month average column is dropped before the columns are
    matched; quarterly columns come after it and are not read."""
    flat = re.sub(r"[ \t]+", " ", text)
    for mt in re.finditer(r"Все\s+товары\s+и\s+услуги ((?:" + _NUM + r" ?){2,})", flat):
        start = mt.start()
        header = flat[max(flat.rfind("Индекс потребительских цен", 0, start), flat.rfind("FILE", 0, start)):start]
        if len(header) > 1500:
            continue
        h = re.sub(r"январ\w*\s*-\s*\w+", " ", re.sub(r"\s+", " ", header.lower()))
        toks = re.findall(r"(" + "|".join(_DATIVE) + r")\s*(\d{4})", h)
        if not toks:
            continue
        if m == 12 and (_DATIVE[toks[-1][0]], int(toks[-1][1])) == (12, y):
            # December 2002 heads its December/December column «декабрю 2002г.» (the value, 106.6,
            # is BNS's Dec/Dec 2002 in the 1991-2021 docx): a header typo for «декабрю 2001г.»
            toks[-1] = ("декабрю", str(y - 1))
        out: dict[str, float] = {}
        for (word, yy), val in zip(toks, _nums(flat[mt.start(1):mt.end(1)])):
            for ms in bns_cpi.column_measures(f"{word} {yy}", y, m):
                out.setdefault(ms, val)
        if out:
            return out
    return {}


def parse_html_edition(text: str, y: int, m: int) -> dict[str, float]:
    """{'mom', 'ytd', 'yoy'} for all goods and services from a 1999-05 .. 2004-06 edition."""
    a, b = _layout_a(text, y, m), _layout_b(text, y, m)
    for k in set(a) & set(b):
        if abs(a[k] - b[k]) > EQUAL:
            raise SourceError(f"edition {y}-{m:02d}: {k} reads {a[k]} in one table and {b[k]} in another")
    got = {**b, **a}
    return {k: got[k] for k in MEASURES if k in got}


def parse_xls_edition(workbooks: list[bytes], y: int, m: int) -> dict[str, float]:
    """{'mom', 'ytd', 'yoy'} for all goods and services from a 2004-07 .. 2010-12 edition, read
    with the CPI publication parser (scripts/fetchers/bns_cpi.py) exactly as CPI_DETAIL_* is."""
    tables = []
    for content in workbooks:
        tables += bns_cpi.parse_workbook(bns_dims._sheets(content), y, m)
    recs, _ = bns_cpi.edition_records(tables, y, m)
    out = {}
    for ms in MEASURES:
        hit = [r["value"] for r in recs.get(f"CPI_DETAIL_{ms.upper()}", [])
               if r["region"] == "national" and r["item_code"] == "TOTAL"]
        if hit:
            out[ms] = hit[0]
    return out


# ---------------------------------------------------------------- assembling and checking

def assemble(docx: dict, pdf: dict, editions: dict[tuple[int, int], tuple[str, dict[str, float]]]) -> list[dict]:
    """Rows of the reference file. Candidates per (date, measure), in order of preference:
    the 2022 docx, the 2001 pdf, the monthly edition. All candidates must be equal."""
    cands: dict[tuple[str, str], list[tuple[float, str, str, str]]] = {}

    def add(d, ms, v, url, note, tag):
        cands.setdefault((d, ms), []).append((v, url, note, tag))

    docx_url, pdf_url = FILE_URL.format(eid=DOCX_ELEMENT), FILE_URL.format(eid=PDF_ELEMENT)
    docx_tag, pdf_tag = f"element {DOCX_ELEMENT} (1991-2021 docx)", f"element {PDF_ELEMENT} (1991-2000 pdf)"
    for d, v in docx["mom"].items():
        add(d, "mom", v, docx_url, f"{DOCX_NOTE}, table 1.3 (к предыдущему месяцу)", docx_tag)
    for d, v in docx["decdec"].items():
        add(d, "ytd", v, docx_url, f"{DOCX_NOTE}, table 1.1 (к декабрю предыдущего года)", docx_tag)
        if d < YOY_START:        # 1991-1993: a December alone would be an isolated point of a monthly series
            continue
        add(d, "yoy", v, docx_url, f"{DOCX_NOTE}, table 1.1 (к декабрю предыдущего года: in December "
                                   "the same month of the previous year)", docx_tag)
    pdf_labels = {"mom": "к предыдущему месяцу", "ytd": "к декабрю предыдущего года",
                  "yoy": "к соответствующему месяцу предыдущего года"}
    for ms, vals in pdf.items():
        for d, v in vals.items():
            add(d, ms, v, pdf_url, f"{PDF_NOTE} ({pdf_labels[ms]})", pdf_tag)
    for (y, m), (eid, vals) in sorted(editions.items()):
        for ms, v in vals.items():
            add(_date(y, m), ms, v, FILE_URL.format(eid=eid),
                f"{EDITION_NOTE}, edition {MONTHS_RU[m - 1]} {y} (element {eid})", f"element {eid} (edition)")

    rows, clashes = [], []
    for (d, ms), cs in sorted(cands.items()):
        if d >= HISTORY_END and (ms != "mom" and d[5:7] != "12" or cs[0][3] != docx_tag):
            continue
        values = {c[0] for c in cs}
        if max(values) - min(values) > EQUAL:
            clashes.append(f"{d} {ms}: " + "; ".join(f"{c[0]} ({c[3]})" for c in cs))
            continue
        v, url, note, _ = cs[0]
        if len(cs) > 1:
            note += "; the same in " + ", ".join(c[3] for c in cs[1:])
        if d >= HISTORY_END:
            note += "; overlap with Taldau 703076, kept only to check the splice"
        rows.append({"date": d, "measure": ms, "value": v, "source_url": url, "source_note": note})
    if clashes:
        raise SourceError("sources disagree:\n  " + "\n  ".join(clashes))
    return rows


def series(rows: list[dict], measure: str, before: str = HISTORY_END) -> dict[str, float]:
    return {r["date"]: float(r["value"]) for r in rows if r["measure"] == measure and r["date"] < before}


# Published month-on-month figures that BNS's own year-to-date figures do not bear out beyond
# rounding, with the extra slack (index points) the checks allow on that month. February 1993:
# both the 2001 pdf and the 2022 docx print 131.9, while January 132.9 and February's
# «к декабрю» 175.0 imply 131.7 (175.0 / 132.9); March's 133.0 against 232.8 / 175.0 = 133.03
# confirms that the year-to-date chain is the consistent one. Kept as printed.
KNOWN_SLACK = {"1993-02-01": 0.2}


def rounding_bound(values: list[float], result: float, slack: list[float] | None = None) -> float:
    """Largest gap between a product of published indices (each rounded to 0.1) and a
    published index `result` that rounding alone can produce: result * sum(0.05 / v) + 0.05,
    plus result * slack / v for a month in KNOWN_SLACK.

    In index points this is 0.3-0.7 in a year of 5-20% inflation (the largest gaps actually seen
    are 0.37: December 2005 before Taldau, December 2023 on Taldau), and it scales with the
    index level: 14 points on 1992's 3060.8, where the largest gap seen is 4.8 (1993)."""
    slack = slack or [0.0] * len(values)
    return result * sum((0.05 + s) / v for v, s in zip(values, slack)) + 0.05


def _prev(d: str, k: int = 1) -> str:
    y, m = int(d[:4]), int(d[5:7]) - k
    while m < 1:
        y, m = y - 1, m + 12
    return _date(y, m)


def check_consistency(mom: dict[str, float], ytd: dict[str, float], yoy: dict[str, float],
                      known_slack: dict[str, float] = KNOWN_SLACK) -> list[str]:
    """Problems (empty when none): the three identities of a CPI, each within rounding_bound.
      1. ytd(t) = product of mom from January to t (January: mom = ytd)
      2. yoy(t) = ytd(t) / ytd(t-12) * ytd(December y-1)       (needs t-12 and December y-1)
      3. yoy(t) = product of the twelve mom to t
    December yoy must equal December ytd exactly."""
    out = []
    for d in sorted(ytd):
        y, m = int(d[:4]), int(d[5:7])
        months = [_date(y, k) for k in range(1, m + 1)]
        if all(x in mom for x in months):
            vals = [mom[x] for x in months]
            est = math.prod(v / 100 for v in vals) * 100
            if abs(est - ytd[d]) > rounding_bound(vals, ytd[d], [known_slack.get(x, 0.0) for x in months]):
                out.append(f"{d}: chain of mom {est:.2f} vs ytd {ytd[d]}")
    for d in sorted(yoy):
        y, m = int(d[:4]), int(d[5:7])
        a, b = _date(y - 1, m), _date(y - 1, 12)
        if d in ytd and a in ytd and b in ytd:
            est = ytd[d] / ytd[a] * ytd[b]
            bound = est * (0.05 / ytd[d] + 0.05 / ytd[a] + 0.05 / ytd[b]) + 0.05
            if abs(est - yoy[d]) > bound:
                out.append(f"{d}: ytd identity {est:.2f} vs yoy {yoy[d]}")
        last12 = [_prev(d, k) for k in range(12)]
        if all(x in mom for x in last12):
            vals = [mom[x] for x in last12]
            est = math.prod(v / 100 for v in vals) * 100
            if abs(est - yoy[d]) > rounding_bound(vals, yoy[d], [known_slack.get(x, 0.0) for x in last12]):
                out.append(f"{d}: product of 12 mom {est:.2f} vs yoy {yoy[d]}")
        if m == 12 and d in ytd and abs(ytd[d] - yoy[d]) > EQUAL:
            out.append(f"{d}: December yoy {yoy[d]} != ytd {ytd[d]}")
    return out


def check_coverage(rows: list[dict]) -> list[str]:
    want = {"mom": (1991, 1), "ytd": (1991, 1), "yoy": (int(YOY_START[:4]), int(YOY_START[5:7]))}
    out = []
    for ms, (y0, m0) in want.items():
        have = series(rows, ms)
        expect, (y, m) = [], (y0, m0)
        while _date(y, m) < HISTORY_END:
            expect.append(_date(y, m))
            y, m = (y, m + 1) if m < 12 else (y + 1, 1)
        missing = sorted(set(expect) - set(have))
        extra = sorted(set(have) - set(expect))
        if missing or extra:
            out.append(f"{ms}: missing {missing[:6]}{'...' if len(missing) > 6 else ''}, unexpected {extra[:6]}")
    return out


# ---------------------------------------------------------------- downloading

def fetch_archive(eid: str, cache: Path) -> Path:
    path = cache / f"{eid}.bin"
    if not path.exists() or path.stat().st_size < 1000:
        path.write_bytes(bns._download(FILE_URL.format(eid=eid)))
    return path


def unpack(archive: Path, into: Path) -> list[Path]:
    """Every file of a zip or rar (and of the archives inside it)."""
    if not into.exists() or not any(into.rglob("*")):
        into.mkdir(parents=True, exist_ok=True)
        if zipfile.is_zipfile(archive):
            zipfile.ZipFile(archive).extractall(into)
        else:
            tool = shutil.which("unar")
            if not tool:
                sys.exit("unar is needed for the rar archives: apt install unar")
            subprocess.run([tool, "-q", "-f", "-D", "-o", str(into), str(archive)], check=True, capture_output=True)
        for inner in [p for p in into.rglob("*") if p.suffix.lower() in (".rar", ".zip")]:
            subprocess.run([shutil.which("unar") or "unar", "-q", "-f", "-D", "-o", str(inner.parent), str(inner)],
                           check=False, capture_output=True)
    return sorted(p for p in into.rglob("*") if p.is_file())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "bns_cpi_history")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    docx_file = next(p for p in unpack(fetch_archive(DOCX_ELEMENT, args.cache), args.cache / DOCX_ELEMENT)
                     if p.suffix.lower() == ".docx")
    docx = parse_docx(docx_file.read_bytes())
    pdf_file = next(p for p in unpack(fetch_archive(PDF_ELEMENT, args.cache), args.cache / PDF_ELEMENT)
                    if p.suffix.lower() == ".pdf")
    pdf = parse_pdf_table(pdf_lines(pdf_file.read_bytes()))
    print(f"docx {DOCX_ELEMENT}: mom {len(docx['mom'])}, Dec/Dec {len(docx['decdec'])}; "
          f"pdf {PDF_ELEMENT}: " + ", ".join(f"{k} {len(v)}" for k, v in pdf.items()))

    listing = bns_cpi.parse_listing(bns._download(bns_cpi.LISTING_URL.format(name=PUBLICATION)).decode("utf-8", "replace"))
    wanted = [e for e in listing if (e["year"], e["month"]) < (2011, 1)]
    editions: dict[tuple[int, int], tuple[str, dict[str, float]]] = {}
    for e in wanted:
        y, m = e["year"], e["month"]
        files = unpack(fetch_archive(e["element_id"], args.cache), args.cache / e["element_id"])
        if (y, m) < (2004, 7):
            vals = parse_html_edition(edition_text([(str(p.relative_to(args.cache)), p.read_bytes()) for p in files]), y, m)
        else:
            vals = parse_xls_edition([p.read_bytes() for p in files if p.suffix.lower() in (".xls", ".xlsx")], y, m)
        missing = [ms for ms in MEASURES if ms not in vals]
        if missing:
            raise SourceError(f"edition {y}-{m:02d} (element {e['element_id']}): no {missing} for all goods and services")
        editions[(y, m)] = (e["element_id"], vals)
    print(f"publication {PUBLICATION}: {len(editions)} editions {min(editions)} .. {max(editions)}")

    rows = assemble(docx, pdf, editions)
    problems = check_coverage(rows) + check_consistency(*(series(rows, ms) for ms in MEASURES))
    if problems:
        raise SourceError("checks failed:\n  " + "\n  ".join(problems))
    with args.out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    by = {ms: series(rows, ms) for ms in MEASURES}
    print(f"wrote {args.out.relative_to(REPO_ROOT) if args.out.is_relative_to(REPO_ROOT) else args.out}: {len(rows)} rows; "
          + ", ".join(f"{ms} {min(v)[:7]} .. {max(v)[:7]} ({len(v)})" for ms, v in by.items())
          + f"; {sum(r['date'] >= HISTORY_END for r in rows)} overlap rows 2011-2021")
    print("December/December:", ", ".join(f"{y} {by['ytd'][_date(y, 12)]}" for y in range(1991, 2011)))


if __name__ == "__main__":
    main()
