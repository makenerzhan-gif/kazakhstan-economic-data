"""Balance sheets of the state development institutions from their IFRS statements on KASE
(added 2026-09-27, for the quasi-fiscal block).

Issuers (config/dims.yaml `issuers`): BTRK -- «Байтерек» holding, consolidated (DBK, Damu,
Otbasy bank, KazakhExport, Kazakhstan Housing Company, Agrarian Credit Corporation and others);
BRKZ -- Development Bank of Kazakhstan, consolidated; KFUS -- Kazakhstan Sustainability Fund
(ФПК, formerly the Problem Loans Fund's successor for mortgage refinancing and the NBK's
programme operator); AGKK -- Agrarian Credit Corporation.

Source: the issuer's page https://kase.kz/ru/listing/issuers/<CODE>/ embeds a JSON list of
documents; statements are «Финансовая отчетность за январь–<месяц> YYYY года» (quarterly) and
«Годовая … финансовая отчетность за YYYY год» as xlsx under /files/emitters/<CODE>/. Every
statement is read (history back to 2014 for AGKK/BRKZ, 2019 for BTRK, 2020 for KFUS), each
file giving the reporting date and the comparative date. When two files give the same date,
the later file wins (restatements).

Parsing: the balance-sheet sheet is the first one with an «Итого/Всего активов» row; its date
columns are the header cells that read as dates; amounts in thousands of KZT (the unit line
is checked) are stored in billions. Lines (LINES below) are matched on the row label. A
column is kept only if TOTAL_ASSETS = TOTAL_LIABILITIES + EQUITY within 0.5% -- a misread
column fails that identity rather than entering the data. Files that give no such column are
listed in the manifest warnings.
"""
from __future__ import annotations

import io
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

ISSUER_URL = "https://kase.kz/ru/listing/issuers/{code}/"
FILE_BASE = "https://kase.kz"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
DOC_RE = re.compile(r'"name":"([^"]*)","link":"(/files/emitters/[^"]*\.xlsx)"')
MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
          "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
# (code, Russian name, regex on the normalised label). First match wins, so the order matters.
LINES = [
    ("TOTAL_ASSETS", "Итого активов", r"^(итого|всего):? актив"),
    ("TOTAL_LIABILITIES", "Итого обязательств", r"^(итого|всего):? обязательств[оа]?$"),
    ("EQUITY", "Итого капитала", r"^(итого|всего):? (собственн\w* )?капитал\w*$"),
    ("LOANS_CUSTOMERS", "Кредиты, выданные клиентам", r"^(кредиты|займы),? (выданные |предоставленные )?клиентам"),
    ("LOANS_BANKS", "Кредиты, выданные банкам и финансовым институтам",
     r"^(кредиты|займы),? (выданные |предоставленные )?(банкам|кредитным|финансовым)"),
    ("FIN_LEASE", "Дебиторская задолженность по финансовой аренде", r"^дебиторская задолженность по (договорам )?финансов\w* аренд"),
    ("DEBT_SECURITIES", "Выпущенные долговые ценные бумаги", r"^выпущенные (долговые ценные бумаги|облигации)|^долговые ценные бумаги выпущенные"),
    ("GOV_LOANS", "Займы и средства от Правительства РК",
     r"^(займы|кредиты|средства),? (полученные )?от правительства|^задолженность перед правительством"),
    ("PARENT_LOANS", "Займы и задолженность перед акционером (материнской компанией)",
     r"^задолженность перед (акционером|материнской)|^займы,? (полученные )?от (материнской|акционера)"),
    ("GOV_SUBSIDIES", "Государственные субсидии (отложенный доход)", r"^государственные субсидии"),
    ("CUSTOMER_FUNDS", "Средства клиентов", r"^(средства|текущие счета и вклады) клиентов"),
]
_LINES = [(c, n, re.compile(r)) for c, n, r in LINES]


def _norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("ё", "е")).strip().lower()


def _as_date(cell) -> str | None:
    if isinstance(cell, datetime):
        return cell.date().isoformat()
    s = _norm(cell)
    m = re.search(r"(\d{1,2})\.(\d{2})\.(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    m = re.search(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})", s)
    if m:
        month = next((v for k, v in MONTHS.items() if m.group(2).startswith(k)), None)
        if month:
            return date(int(m.group(3)), month, int(m.group(1))).isoformat()
    return None


def _number(cell) -> float | None:
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell or "").strip().replace("\xa0", "").replace(" ", "")
    if s in ("", "-", "–", "—"):
        return 0.0 if s else None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):  # 24.297.440 (thousands separated by dots)
        s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_balance_sheet(content: bytes) -> tuple[dict[str, dict[str, float]], str]:
    """{date: {line code: bn KZT}} for the columns that pass the balance identity, and a
    note on what was skipped."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True, max_row=200))
        if any(re.match(r"^(итого|всего) актив", _norm(c)) for r in rows for c in r[:6] if isinstance(c, str)):
            break
    else:
        return {}, "no sheet with a total-assets row"
    head = " ".join(_norm(c) for r in rows[:15] for c in r if isinstance(c, str))
    scale = 1e3 if "тыс" in head else 1e6 if "млн" in head else None
    if scale is None:
        return {}, "unit line (тыс./млн тенге) not found"
    cols: dict[int, str] = {}
    for k, r in enumerate(rows[:25]):
        found = {i: _as_date(c) for i, c in enumerate(r) if _as_date(c)}
        if len(found) < 2 and k + 1 < len(rows):  # «На 31 марта» over «2019 года (неаудировано)»
            nxt = rows[k + 1]
            found = {i: _as_date(f"{c} {nxt[i] if i < len(nxt) else ''}") for i, c in enumerate(r)
                     if isinstance(c, str) and _as_date(f"{c} {nxt[i] if i < len(nxt) else ''}")}
        if len(found) >= 2:
            cols = found
            break
    if not cols:
        return {}, "no header row with two dates"
    # Column headers carry typos (KFUS 9M-2022 heads its September column «30 июня 2022»; KFUS
    # 6M-2026 heads the year-end comparative «30 июня 2025»). The reporting date in the title
    # («по состоянию на 30 сентября 2022 года») names the current column; any other column
    # must be a year-end comparative, or it is dropped.
    notes = []
    title = next((_as_date(c) for r in rows[:10] for c in r if isinstance(c, str) and _as_date(c)
                  and re.search(r"(^|\s)(на|за)\s+\d", _norm(c))), None)
    current = max(cols, key=lambda i: cols[i])
    if title and cols[current] != title:
        notes.append(f"header {cols[current]} read as the title's {title}")
        cols[current] = title
    for i in [i for i in cols if i != current and not cols[i].endswith("-12-31")]:
        notes.append(f"comparative column headed {cols[i]} dropped (not a year end)")
        del cols[i]
    values: dict[str, dict[str, float]] = {d: {} for d in cols.values()}
    for r in rows:
        label = next((_norm(c) for c in r[:4] if isinstance(c, str) and re.search(r"[а-я]{3}", _norm(c))), "")
        hit = next(((code) for code, _, rx in _LINES if rx.search(label)), None)
        if hit is None:
            continue
        for i, d in cols.items():
            v = _number(r[i]) if i < len(r) else None
            if v is not None and hit not in values[d]:
                values[d][hit] = v * scale / 1e9
    kept, skipped = {}, []
    for d, v in values.items():
        a, l, e = v.get("TOTAL_ASSETS"), v.get("TOTAL_LIABILITIES"), v.get("EQUITY")
        if a and l is not None and e is not None and abs(a - l - e) <= 0.005 * abs(a):
            kept[d] = v
        else:
            skipped.append(d)
    if skipped:
        notes.append(f"columns failing assets = liabilities + equity: {skipped}")
    return kept, "; ".join(notes)


def documents(code: str) -> list[tuple[str, str]]:
    html = requests.get(ISSUER_URL.format(code=code), headers=HEADERS, timeout=60)
    html.raise_for_status()
    text = html.text.replace("\\u002F", "/")
    docs = sorted({(n, l) for n, l in DOC_RE.findall(text) if "отчетност" in n.lower() and "700" not in l
                   and ("консолид" in n.lower() or code not in ("BTRK", "BRKZ"))}, key=lambda x: x[1])
    if not docs:
        raise validation.StructuralChangeError(f"kase_ifrs: no financial statements listed on {ISSUER_URL.format(code=code)}")
    return docs


def _get(url: str) -> bytes:
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError


def fetch(ds: dict) -> tuple[list[dict], dict]:
    fresh = imf_dims.stored_if_fresh(ds, "kase", ds["id"])
    if fresh:
        return fresh
    today = date.today()
    names = {c: n for c, n, _ in LINES}
    best: dict[tuple[str, str], tuple[str, float]] = {}  # (issuer.line, date) -> (link, value) of the latest statement
    warnings, files = [], 0
    for issuer, issuer_name in ds["issuers"].items():
        for title, link in documents(issuer):
            content = _get(FILE_BASE + link)
            files += 1
            raw_store.save_raw_bytes("kase", f"ifrs_{Path(link).stem}", today, "xlsx", content)
            try:
                sheet, note = parse_balance_sheet(content)
            except Exception as exc:  # a corrupt or non-xlsx file must not stop the other issuers
                sheet, note = {}, f"unreadable: {exc}"
            if note:
                warnings.append(f"{Path(link).name}: {note}")
            for d, lines in sheet.items():
                for line, v in lines.items():
                    key = (f"{issuer}.{line}", d)
                    if key not in best or (_order(link), link) > (_order(best[key][0]), best[key][0]):
                        best[key] = (link, v)
    raw_store.write_download_manifest("kase", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "source_url": ISSUER_URL.format(code="<CODE>"),
        "issuers": list(ds["issuers"]), "files": files})
    records = [{"date": d, "region": dims.NATIONAL, "item_code": code,
                "item_name": f"{ds['issuers'][code.split('.')[0]]}: {names[code.split('.', 1)[1]]}, млрд тенге",
                "value": round(v, 6)} for (code, d), (_, v) in sorted(best.items())]
    if len({r["item_code"].split(".")[0] for r in records}) < len(ds["issuers"]):
        raise validation.StructuralChangeError(
            f"kase_ifrs: no balance sheet read for {sorted(set(ds['issuers']) - {r['item_code'].split('.')[0] for r in records})}")
    return records, {"frequency": "quarterly", "source_url": ISSUER_URL.format(code="<CODE>"),
                     "dataset_id": "KASE issuer financial statements", "note": ds.get("note", ""), "warnings": warnings}


def _order(link: str) -> tuple[int, int]:
    """(year, quarter) of a statement from its file name: …fm1_2024… → (2024, 1); annual → (year, 4)."""
    m = re.search(r"f(?:m(\d))?_(\d{4})", Path(link).name)
    return (int(m.group(2)), int(m.group(1) or 4)) if m else (0, 0)
