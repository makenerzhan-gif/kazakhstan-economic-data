"""Minfin Statistical Bulletin, the PDF editions of 2005-2012, as spreadsheet-shaped sheets.

Until 2012 the monthly bulletin was published as a PDF (text, not a scan; twelve a year inside the
yearly RAR archives on gov.kz). Its tables 4, 8 (receipts by budget code) and the two tables of the
economic classification of expenditure are the same tables the later xlsx editions carry, so this
module only turns the text of a PDF into rows shaped like those sheets -- the code columns, the name,
the value of the report period, the Russian name -- under the sheet names the xlsx readers look for
(«табл 4», «табл 8 (дох)», «табл 6», «табл 10»). Everything else is done by
fetchers/minfin_classification.py, with the same checks: an edition whose rows do not add up is not
loaded, which is also what catches a misread line.

How a table is read. `pdftotext -tsv` gives every word with its place on the page, and the layout
of the tables is regular:
  * a table starts at a line ending «Таблица N» and runs to the next such line; which table is which is
    decided by its title, not its number (the economic classification is table 7 in 2005-2006 and
    table 6 from 2007);
  * under the header of every page there is a numbering row «1 2 3 …»: one number centred in each
    column. Codes are centred in their columns too, so a short number standing under the «1»…«4» of
    that row is the code of that column -- and a number inside a name is not;
  * numbers are right-aligned: the right edge shared by most numbers of the last value column (the
    earlier value columns are previous years) is found on each page, and the value of a line is the
    digit groups that end exactly there. «-» is zero;
  * the Russian name is everything to the right of that edge; a line with no code and no value
    continues the name of the row above.
The 2002-2004 editions follow the pre-2005 budget classification and garble Cyrillic (a legacy font
encoding, repaired here); their tables are not mapped.

Needs the `pdftotext` program (poppler-utils).
"""
from __future__ import annotations

import collections
import re
import shutil
import subprocess

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
_MONTH_STEMS = ["январ", "феврал", "март", "апрел", "ма[йя]", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
TABLE_RE = re.compile(r"Таблица\s+(\d+(?:\.\d+)?)\s*$|^(\d+(?:\.\d+)?)\s*-?\s*кесте\b")   # the Russian mark is sometimes missing
FOOTER_RE = re.compile(r"бюллетен[ьі]\s*№|^\d{1,3}$")
_NUM_GROUP = re.compile(r"\d+")


class PdfUnavailable(RuntimeError):
    pass


def repair_encoding(text: str) -> str:
    """The 2002-2006 files come out of pdftotext as cp1251 bytes read as cp1252."""
    if "ÏÎÑÒÓÏËÅÍ" not in text and "Òàáëèöà" not in text:
        return text
    out = []
    for ch in text:
        if 127 < ord(ch) < 256:
            try:
                ch = ch.encode("cp1252").decode("cp1251")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        out.append(ch)
    return "".join(out)


def pdf_words(content: bytes) -> list[list[tuple[float, float, float, str]]]:
    """Pages of words: (left, right, top, text)."""
    if not shutil.which("pdftotext"):
        raise PdfUnavailable("pdftotext (poppler-utils) is not installed")
    run = subprocess.run(["pdftotext", "-tsv", "-", "-"], input=content, capture_output=True, check=True)
    pages: dict[int, list] = {}
    for raw in repair_encoding(run.stdout.decode("utf-8", "replace")).split("\n")[1:]:
        f = raw.split("\t")
        if len(f) < 12 or f[0] != "5":
            continue
        try:
            left, top, width = float(f[6]), float(f[7]), float(f[8])
        except ValueError:
            continue
        pages.setdefault(int(f[1]), []).append((left, left + width, top, f[11]))
    return [pages[k] for k in sorted(pages)]


def _lines(words: list[tuple]) -> list[list[tuple]]:
    """Words of a page grouped into lines (same top within two points), each left to right."""
    out: list[list[tuple]] = []
    for w in sorted(words, key=lambda w: (w[2], w[0])):
        if out and abs(out[-1][0][2] - w[2]) <= 2.0:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w[0]) for line in out]


def _text(line: list[tuple]) -> str:
    return " ".join(w[3] for w in line)


def tables(pages: list[list[tuple]]) -> dict[str, list[list[list[tuple]]]]:
    """{table number: pages, each a list of lines of words}."""
    out: dict[str, list[list[list[tuple]]]] = {}
    current = None
    for words in pages:
        lines: list[list[tuple]] = []
        for line in _lines(words):
            text = _text(line)
            m = TABLE_RE.search(text)
            if m:
                number = m.group(1) or m.group(2)
                if number != current:
                    if current and lines:
                        out[current].append(lines)
                    current, lines = number, []
                    out.setdefault(current, [])
                continue
            if FOOTER_RE.search(text):
                continue
            lines.append(line)
        if current and lines:
            out[current].append(lines)
    for number, table in out.items():                    # some editions carry the same page twice
        seen, kept = set(), []
        for lines in table:
            key = "\n".join(_text(line) for line in lines)
            if key not in seen:
                seen.add(key)
                kept.append(lines)
        out[number] = kept
    return out


def _numbering(line: list[tuple]) -> list[float] | None:
    """Centres of the columns when the line is the numbering row «1 2 3 …» (at least five columns)."""
    texts = [w[3] for w in line]
    if len(texts) < 5 or texts[0] != "1" or not all(re.fullmatch(r"\d{1,2}", t) for t in texts):
        return None
    numbers = [int(t) for t in texts]
    if any(b <= a for a, b in zip(numbers, numbers[1:])):
        # one edition numbers the columns «1 2 3 4 3 4 5 6 7»: the row is still one number per column
        return [(w[0] + w[1]) / 2 for w in line] if len(numbers) >= 7 and numbers[:4] == [1, 2, 3, 4] else None
    if numbers[-1] > len(numbers) + 1:
        return None
    centres = {n: (w[0] + w[1]) / 2 for n, w in zip(numbers, line)}
    for n in range(2, numbers[-1]):                              # one edition leaves a number out: its column is
        if n not in centres:                                     # taken to be midway between its neighbours
            centres[n] = (centres[n - 1] + centres[n + 1]) / 2
    return [centres[n] for n in sorted(centres)]


def _head_end(lines: list[list[tuple]]) -> int | None:
    """Index of the numbering row that closes the header of a page. Some first pages carry a stray copy of
    the row above the title, so the last one among the first 25 lines is taken."""
    found = [i for i, line in enumerate(lines[:25]) if _numbering(line)]
    return found[-1] if found else None


_INT = re.compile(r"-?\d+")


def _value_edge(lines: list[list[tuple]], centre: float) -> float | None:
    """Right edge of the numbers of the column whose numbering sits at `centre`."""
    edges = collections.Counter(round(w[1], 0) for line in lines for w in line
                                if _INT.fullmatch(w[3]) and centre - 3 <= w[1] <= centre + 45)
    if not edges:
        return None
    near = lambda e: edges[e] + edges.get(e - 1, 0) + edges.get(e + 1, 0)          # noqa: E731
    top = max(near(e) for e in edges)
    best = max(e for e in edges if near(e) >= 0.7 * top)       # every digit group ends somewhere: the right-most stack is the column's edge
    exact = [w[1] for line in lines for w in line if _INT.fullmatch(w[3]) and abs(w[1] - best) <= 1.0]
    return sum(exact) / len(exact)


def _value(line: list[tuple], edge: float, centre: float) -> float | None:
    """The number of the line that ends at `edge`; «-» in the column is zero."""
    # rows set in bold (the total, the categories) end a few points to the right of the others, and so does
    # the odd row whose cells are set with another margin; names begin further away than that
    at = [i for i, w in enumerate(line) if -3.0 <= w[1] - edge <= 8.0 and re.fullmatch(r"-?\d+|\d{3},0", w[3])]
    idx = min(at, key=lambda i: abs(line[i][1] - edge)) if at else None
    if idx is None:
        dash = any(w[3] in ("-", "–", "—") and centre - 30 <= w[1] <= edge + 2 for w in line)
        return 0.0 if dash else None
    # «5 303,0» is 5303; a number below a thousand with a decimal («0,2», «1,0») is left unread, see the docstring
    take = [line[idx][3].removesuffix(",0")]
    if len(take[0]) == 3:
        i = idx
        while i > 0:
            prev, cur = line[i - 1], line[i]
            if not _INT.fullmatch(prev[3]) or len(prev[3].lstrip("-")) > 3 or cur[0] - prev[1] > 4.5:
                break
            take.insert(0, prev[3])
            i -= 1
            if len(prev[3].lstrip("-")) < 3 or prev[3].startswith("-"):
                break
        if i > 0 and line[i - 1][3] == "-" and line[i][0] - line[i - 1][1] <= 2.0 and not take[0].startswith("-"):
            take.insert(0, "-")
    if line[idx][3].endswith(",0") and len(take) == 1:
        return None
    try:
        return float("".join(take))
    except ValueError:
        return None


def _rows(pages: list[list[list[tuple]]], n_codes: int, stop=None) -> list[dict]:
    """Rows of one table: {"codes": [per code column], "value", "label"}. `stop(label)` ends the table."""
    rows: list[dict] = []
    centres = edge = None
    held: list[str] = []
    for lines in pages:
        start = _head_end(lines)
        if start is not None:
            centres = _numbering(lines[start])
            body = lines[start + 1:]
            if (len(centres) >= n_codes + 4 and str(len(centres) - 1) not in [w[3] for w in lines[start]]
                    and _value_edge(body, centres[-2]) is None):
                centres = centres[:-2] + centres[-1:]                 # numbered «… 7 9» and nothing between: no column 8
        else:
            body = lines
            if centres is not None and len(centres) >= n_codes + 3:
                centres = [c + _shift(body, centres, n_codes, edge) for c in centres]
        if centres is None or len(centres) < n_codes + 3:
            continue
        edge = _value_edge(body, centres[-2])
        if edge is None:
            continue
        gaps = [b - a for a, b in zip(centres[:n_codes], centres[1:n_codes + 1])]
        reach = max(4.5, 0.55 * min(gaps))                            # how far from its column's centre a code may stand
        first_on_page = True
        break_all = False
        page_start = len(rows)
        pending: list[tuple[float, list]] = []                        # codes printed above the line of their row
        names = [line[0][2] for line in body if any(w[0] > edge + 1.0 for w in line)]
        steps = sorted(b - a for a, b in zip(names, names[1:]))
        pitch = steps[len(steps) // 2] if steps else 10.0             # the usual distance between two lines of names
        for nth, line in enumerate(body):
            if _numbering(line):                                      # a second header on the page: another part of the table
                if stop is not None:
                    break_all = True
                    break
                continue
            if re.search(r"Примечание\s*:|^Ескерту\b", _text(line)):          # footnotes close the page
                break
            value = _value(line, edge, centres[-2])
            codes = [None] * n_codes
            cells: list[tuple] = []
            for w in line:
                if w[1] > centres[n_codes]:
                    break
                if cells and w[3].isdigit() and cells[-1][3].isdigit() and w[0] - cells[-1][1] <= 1.5:
                    cells[-1] = (cells[-1][0], w[1], w[2], cells[-1][3] + w[3])      # «2 6»: a code set letter by letter
                else:
                    cells.append(w)
            for w in cells:
                if re.fullmatch(r"\d{1,3}", w[3]):
                    mid = (w[0] + w[1]) / 2
                    col = min(range(n_codes), key=lambda c: abs(centres[c] - mid))
                    if abs(centres[col] - mid) <= reach:
                        codes[col] = w[3]
            label = " ".join(w[3] for w in line if w[0] > edge + 1.0)
            if value is None and not any(codes) and re.match(r"(в том числе|из них)\s*:?$", label.strip(), re.IGNORECASE):
                continue
            if value is None and not any(codes):
                # the second case is a name carried over the page break
                if label and (not first_on_page or re.match(r"[а-яё(]", label) or not rows):
                    held.append(label)
                continue
            first_on_page = False
            if stop is not None and stop(label):
                break_all = True
                break
            # The Kazakh and the Russian halves of a row are set separately, and where their names break
            # differently the codes (set with the Kazakh name) stand a line above or below the value (set
            # with the Russian one). Three rules put them together, each within a line's distance:
            #  * a line with codes, no value and no beginning of a name is not a row when a value stands that
            #    near: its codes belong to the row just above if that one has a value and no code, otherwise
            #    they wait for the row that begins just below, and that row's own codes wait in turn. Its text
            #    continues the name above. (With no value that near, it is a row whose cell is empty.)
            #  * a line that is only a value and the beginning of a name -- no code, nothing of the Kazakh
            #    half, not a heading in capitals -- is a row whose codes come with the next line; that line's
            #    own value is then a row of the same kind.
            top = line[0][2]
            near = 1.25 * pitch
            last = rows[-1] if len(rows) > page_start else None
            if last and last.get("wants") and any(codes) and not pending and top - last["top"] <= near:
                last.update(codes=codes, wants=False)
                codes = [None] * n_codes
                if value is None:
                    held.append(label)
                    continue
                wants = True
            else:
                wants = (value is not None and not any(codes) and not pending and not _capitals(label)
                         and bool(re.match(r"[^а-яё]", label))
                         and all(_INT.fullmatch(w[3]) or w[3] in "-–—" for w in line if w[0] <= edge + 1.0)
                         and line[0][0] > centres[n_codes])
            if value is None and not re.match(r"[^а-яё]", label):
                up = (top - last["top"] if last and not pending and not any(last["codes"]) and last["value"] is not None
                      and not _capitals(last["label"]) else None)
                down = next((x[0][2] - top for x in body[nth + 1:nth + 6] if _value(x, edge, centres[-2]) is not None), None)
                above = up is not None and up <= near and (down is None or up <= down + 1.0)
                if above or (down is not None and down <= near):
                    if above:
                        last.update(codes=codes, wants=False)
                    else:
                        pending.append((top, codes))
                    if label:
                        held.append(label)
                    continue
            if (value is not None and not any(codes) and not held and not pending and last and last["value"] is not None
                    and last["value"].is_integer() and top - last["top"] <= near and not re.match(r"[^а-яё]", label)
                    and any(len(w[3]) == 3 and float(w[3]) == value for w in line if _INT.fullmatch(w[3]) and -3.0 <= w[1] - edge <= 8.0)):
                # a number too long for its cell breaks like a name: «1 061» and, on the next line, «785»
                last["value"] = last["value"] * 1000 + (value if last["value"] >= 0 else -value)
                last["label"] = _join(last["label"], label) if label else last["label"]
                last["top"] = top
                continue
            pending = [p for p in pending if top - p[0] <= near]             # nothing began under them: empty rows
            if pending:
                if any(codes):
                    pending.append((top, codes))
                codes = pending.pop(0)[1]
            # Lines of names met since the last row. Some editions print the codes and the value on the LAST
            # line of a name: then the row's own text starts in lower case (or is empty) and its beginning is
            # among the held lines, from the last one that starts with a capital.
            mine: list[str] = []
            if held and not re.match(r"[A-ZА-ЯЁ\"«]", label):
                at = max((i for i, h in enumerate(held) if re.match(r"[A-ZА-ЯЁ\"«]", h)), default=None)
                if at is not None:
                    held, mine = held[:at], held[at:]
            for h in held:
                if rows:
                    rows[-1]["label"] = _join(rows[-1]["label"], h)
            held = []
            for h in reversed(mine):
                label = _join(h, label) if label else h
            if (not any(codes) and rows and rows[-1]["value"] is None and any(rows[-1]["codes"])
                    and not (_capitals(label) and not _capitals(rows[-1]["label"]))):
                # the value of a two-line row is printed on its second line (a line in capitals under a name
                # that is not is a heading row with no code, as the 2005 editions print above every category)
                rows[-1].update(value=value, label=_join(rows[-1]["label"], label), top=top)
                continue
            rows.append({"codes": codes, "value": value, "label": label, "top": top, "wants": wants})
        _drop_overlap(rows, page_start)
        if break_all:                                                 # what is held is the end of the last name
            break
    for h in held:
        if rows:
            rows[-1]["label"] = _join(rows[-1]["label"], h)
    return rows


def _capitals(label: str) -> bool:
    letters = [ch for ch in label if ch.isalpha()]
    return len(letters) >= 5 and all(ch.isupper() for ch in letters)


def _drop_overlap(rows: list[dict], page_start: int) -> None:
    """Some editions start a page with rows the page before already printed (the same lines laid out twice):
    a run of at least five rows that repeats the end of what is already read is dropped."""
    key = lambda r: (tuple(r["codes"]), r["value"])              # noqa: E731
    page = rows[page_start:]
    if len(page) < 5 or page_start < 5:
        return
    for j in range(max(0, page_start - 150), page_start):
        n = 0
        while j + n < page_start and n < len(page) and key(rows[j + n]) == key(page[n]):
            n += 1
        if n >= 5 and (j + n == page_start or n == len(page)):
            del rows[page_start:page_start + n]
            return


def _shift(lines: list[list[tuple]], centres: list[float], n_codes: int, edge: float | None = None) -> float:
    """A page without the numbering row takes the columns of the page before it, moved sideways by the
    distance that puts most of its codes under them (odd and even pages have different margins). A page
    that has codes in its last columns only fits as well one or two columns to the left: of the distances
    that fit, the one that also moves the edge of the value column onto the page's numbers is taken."""
    votes: collections.Counter = collections.Counter()
    for line in lines:
        for w in line:
            if w[1] > centres[n_codes] + 40:
                break
            if not re.fullmatch(r"\d{1,3}", w[3]):
                break                                             # codes stand before the name
            for c in centres[:n_codes]:
                d = round((w[0] + w[1]) / 2 - c)
                if abs(d) <= 40:
                    votes[d] += 1
    if not votes:
        return 0.0
    near = lambda d: votes[d] + votes.get(d - 1, 0) + votes.get(d + 1, 0)      # noqa: E731
    top = max(near(d) for d in votes)
    ends = collections.Counter(round(w[1]) for line in lines for w in line if _INT.fullmatch(w[3])) if edge is not None else {}
    at_edge = lambda d: sum(ends.get(round(edge + d) + k, 0) for k in (-1, 0, 1)) if ends else 0      # noqa: E731
    return float(max((d for d in votes if near(d) >= 0.9 * top), key=lambda d: (at_edge(d), near(d), -abs(d))))


def _join(head: str, tail: str) -> str:
    """A name and its next line; a word split by the line end («акти-» «вов») is put together, a compound
    («инженерно-» «коммуникационной») keeps its hyphen."""
    head = re.sub(r"[\u00ad\u2010\u2011]$", "-", head)
    if re.search(r"[а-яё]-$", head) and re.match(r"[а-яё]", tail):
        return head + tail if re.search(r"[а-яё]{3}[нвк]о-$", head) else head[:-1] + tail
    return (head + " " + tail).strip()


EXPENDITURE_RE = re.compile(r"^(II\.?\s*)?(ЗАТРАТЫ|РАСХОДЫ)\b", re.IGNORECASE)


def receipt_sheet(pages, header: str, republican: bool = False) -> list[list]:
    """Rows shaped like «табл 4»: category, class, subclass, specific, Kazakh name, value, Russian name.
    Table 8 prints the republican budget's receipts and then its expenditure by function: it is read up to
    «ЗАТРАТЫ»."""
    out = [["Санаты/ Категория", "Сыныбы/ Класс", "Сыныпшасы/ Подкласс", "Ерешелігі/ Специфика", "Атауы", header, "Наименование"],
           ["1", "2", "3", "4", "5", "6", "7"]]
    stop = (lambda label: bool(EXPENDITURE_RE.match(label))) if republican else None
    plain = lambda c: str(int(c)) if c else c                    # noqa: E731  (early 2008 prints category «01», subclass «01»)
    cls = sub = None
    for r in _rows(pages, 4, stop):
        c = list(r["codes"])
        if c[0] or c[1]:
            cls, sub = c[1], c[2]
        elif c[2]:
            sub = c[2]
        elif c[3]:
            # A specific is written with its class and subclass: the rows of those may have no value this
            # module can read (a blank cell, «0,2»), and the classification passes such rows over.
            c[1], c[2] = cls, sub
        out.append([plain(c[0]), c[1], plain(c[2]), c[3], None, r["value"], r["label"]])
    return out


def economic_sheet(pages, header: str, with_specifics: bool) -> list[list]:
    """Rows shaped like «табл 6» (category, subclass, name, value, name) or «табл 10» (with the specific)."""
    n = 3 if with_specifics else 2
    head = ["Cанаты/ Категория", "Iшкi сыныбы/ Подкласс"] + (["Ерекшелiгi/ Специфика"] if with_specifics else [])
    out = [head + ["Атауы", header, "Наименование"], [str(i + 1) for i in range(n + 3)]]
    for r in _rows(pages, n):
        out.append(r["codes"] + [None, r["value"], r["label"]])
    return out


def _report_cell(pages) -> str:
    """Text of the header cell above the report column of a table's first page."""
    lines = pages[0] if pages else []
    end = _head_end(lines)
    if end is None:
        return ""
    centre = _numbering(lines[end])[-2]
    return " ".join(w[3] for line in lines[:end] for w in line if abs((w[0] + w[1]) / 2 - centre) <= 28)


def _header(pages) -> str:
    """Text of a table's first page above its numbering row."""
    if not pages:
        return ""
    lines = pages[0]
    end = _head_end(lines)
    return " ".join(_text(line) for line in lines[:end if end is not None else 25])


def _title(pages) -> str:
    """The title of a table: its first lines down to the «(млн. тенге)» line."""
    out = []
    for line in (pages[0] if pages else [])[:12]:
        text = _text(line)
        if _numbering(line):
            continue
        out.append(text)
        if "(млн" in text.lower():
            break
    else:
        out = out[:6]
    return " ".join(out)


def period_of(header: str, year: int | None = None) -> tuple[int, int] | None:
    """(year, last month) of the report column named in a table's header."""
    head = header.lower()
    years = [int(y) for y in re.findall(r"(?<!\d)(20[01]\d)(?!\d)", head)]
    if not years and year is None:
        return None
    y = max(years) if years else year
    month = None
    for m in re.finditer(r"январ[ьяе]\s*-\s*([а-я]+)", head):
        for i, stem in enumerate(_MONTH_STEMS):
            if re.match(stem, m.group(1)):
                month = max(month or 0, i + 1)
    if month is None:
        month = 1 if re.search(r"январ[ьяе]", head) else 12
    return y, month


def classify(title: str, header: str) -> str | None:
    """Which sheet a table is, by its title; the receipts tables must also have the code columns."""
    flat = re.sub(r"\s+", " ", title).upper()
    has_codes = any(word in header.upper() for word in ("СПЕЦИФИКА", "ПОДКЛАСС", "СЫНЫПШАСЫ"))   # one edition cuts the Russian half off
    if "ЭКОНОМИЧЕСК" in flat and "КЛАССИФИКАЦИИ" in flat and "СВОДНАЯ" not in flat:
        if "РЕСПУБЛИКАНСК" in flat:
            return "табл 10"
        if "ГОСУДАРСТВЕНН" in flat:
            return "табл 6"
    if has_codes and "ПОСТУПЛЕНИЯ В ГОСУДАРСТВЕННЫЙ БЮДЖЕТ" in flat:
        return "табл 4"
    if has_codes and "ИСПОЛНЕНИЕ РЕСПУБЛИКАНСКОГО БЮДЖЕТА" in flat and "ВЕДОМСТВЕНН" not in flat and "ЭКОНОМИЧЕСК" not in flat:
        return "табл 8 (дох)"
    return None


def sheets(content: bytes, year: int | None = None) -> dict[str, list[list]]:
    """{sheet name: rows} for the tables this module maps; empty when the PDF has none of them."""
    out: dict[str, list[list]] = {}
    found = [(classify(_title(pages), _header(pages)), pages) for pages in tables(pdf_words(content)).values() if pages]
    found = [(name, pages) for name, pages in found if name]
    # One period for the whole edition, from the receipts table: its header names the month range in one cell,
    # the expenditure tables spread theirs over several columns of earlier years.
    order = sorted(found, key=lambda x: {"табл 4": 0, "табл 8 (дох)": 1}.get(x[0], 2))
    period = next((p for p in (period_of(_report_cell(pages), year) for _, pages in order) if p), None)
    if period is None:
        return out
    y, m = period
    header = f"{y} ж. есеп / январь-{MONTHS[m - 1]} отчет {y} г." if m > 1 else f"{y} ж. қаңтар есеп / январь отчет {y} г."
    for name, pages in found:
        if name in out:
            continue
        if name in ("табл 4", "табл 8 (дох)"):
            out[name] = receipt_sheet(pages, header, republican=name != "табл 4")
        else:
            out[name] = economic_sheet(pages, header, with_specifics=name == "табл 10")
    return out
