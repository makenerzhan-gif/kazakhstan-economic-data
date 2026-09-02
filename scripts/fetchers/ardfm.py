#!/usr/bin/env python3
"""Fetchers for ARDFM -- the Agency of the Republic of Kazakhstan for Regulation
and Development of the Financial Market (АРРФР).

WHY A FIFTH AGENCY EXISTS AT ALL. The sector audit's single remaining real
defect was the banking block: NPL_RATIO, CAPITAL_ADEQUACY_RATIO, BANK_ROA,
BANK_ROE and LOANS_TO_ECONOMY all stop at 2024-04-01. They come from NBK
formId=314, which stopped updating. All 239 NBK forms were swept and none
carries a replacement -- formId=1 lists 45 balance-sheet lines with no totals,
formId=60 returns seven unlabelled rows per bank-date. Banking supervision
moved to ARDFM, and ARDFM publishes the numbers monthly.

HOW THE SOURCE IS REACHED. ARDFM has no API of its own and finreg.kz no longer
resolves. Its content sits behind the same gov.kz content-manager API that
already serves Minfin, under projects=ardfm. The banking bulletin is found by
the API's `title` filter rather than by a hardcoded document id, because ids
change with every monthly edition. Three editions were online on 2026-09-02
(01.05, 01.06 and 01.07.2026), so these series ACCUMULATE across runs like the
BNS publication-layer ones.

THE DOCUMENTS ARE PDF, not spreadsheets. Text extracts cleanly with pypdf --
pdftotext drops every Cyrillic character on these files, which is worth knowing
before reaching for it.

TWO TRAPS FOUND BY PROBING, BOTH OF WHICH WOULD HAVE PRODUCED PLAUSIBLE WRONG
NUMBERS RATHER THAN AN ERROR:

1. EVERY HEADLINE FIGURE APPEARS TWICE -- once in the narrative commentary and
   once in the table. They do not agree, because the narrative rounds and
   compares against the SAME DATE A YEAR EARLIER while the table compares
   against the START OF THE YEAR. For 01.07.2026 the narrative reads "ROA
   составило – 3,7% (4,6% на аналогичную дату)" and the table reads "4,21%
   3,65%". The narrative comes first in the document, so a naive first-match
   lookup silently takes the rounded number on the wrong comparison basis.
   Every lookup here is therefore anchored to its table heading.

2. THE CAPITAL RATIO LABELS NEST: "k1" is a prefix of "k1-2". Matching on the
   label alone picks up both rows. Labels are stripped before parsing and the
   remainder must contain exactly the expected count of numbers.

Numbers are Russian-formatted: comma decimal separator, spaces (ordinary AND
non-breaking) as thousands separators. The label is removed before parsing,
because otherwise the digit in "k1" or the "90" in "свыше 90 дней" is read as
part of the value.
"""
from __future__ import annotations

import io
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
SOURCE = "ardfm"
GOV_KZ_BASE = "https://www.gov.kz"
LISTING_URL = f"{GOV_KZ_BASE}/api/v1/public/content-manager/documents"
BANKING_TITLE_FILTER = "Текущее состояние банковского сектора"
REPORT_DATE_RE = re.compile(r"на\s+(\d{2})\.(\d{2})\.(\d{4})")
COLUMN_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


_DOCUMENT_CACHE: dict[str, bytes] = {}
_TEXT_CACHE: dict[str, str] = {}
_DOWNLOAD_ATTEMPTS = 3


def _download(path: str) -> bytes:
    """Fetch one document, once per process, retrying only transport failures.

    THE CACHE IS NOT AN OPTIMISATION, IT IS A FIX. Every indicator in this
    module is a separate fetcher and each one walks all listed editions, so
    thirty indicators over three bulletins meant NINETY downloads of a ~450 KB
    PDF per run -- about 40 MB, all of it the same handful of files. gov.kz
    started refusing connections partway through the first thirty-indicator
    run, which is what exposed this. The cache is per-process: a fresh run
    still re-downloads, so the append-only raw archive still sees today's
    bytes, but within one run each document is fetched exactly once.

    Retries cover ConnectionError and Timeout only -- never an HTTP status --
    for the same reason as the IMF module: a 404 or a 500 is information about
    the source, and retrying it hides a real change behind a delay.
    """
    url = path if path.startswith("http") else GOV_KZ_BASE + path
    cached = _DOCUMENT_CACHE.get(url)
    if cached is not None:
        return cached
    last: Exception | None = None
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=180)
            resp.raise_for_status()
            _DOCUMENT_CACHE[url] = resp.content
            return resp.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
            if attempt < _DOWNLOAD_ATTEMPTS:
                print(f"ardfm: transport error on {url} (attempt {attempt}/"
                      f"{_DOWNLOAD_ATTEMPTS}), retrying in {attempt}s: "
                      f"{type(exc).__name__}", file=sys.stderr)
                time.sleep(attempt)
    raise last


def _save_raw(indicator_id: str, content: bytes, extra: dict) -> None:
    raw_store.save_raw_bytes(SOURCE, indicator_id, date.today(), "pdf", content)
    raw_store.write_download_manifest(SOURCE, indicator_id, date.today(), {
        "downloaded_at": datetime.now().isoformat(), **extra,
    })


def _list_banking_bulletins(indicator_id: str) -> list[dict]:
    """Every 'Текущее состояние банковского сектора' document currently listed.

    Found by title filter, not by id: each monthly edition is a new document.
    """
    resp = requests.get(LISTING_URL, headers=HEADERS, timeout=120,
                        params={"title": BANKING_TITLE_FILTER, "size": "50"})
    resp.raise_for_status()
    docs = [d for d in resp.json() if REPORT_DATE_RE.search(d.get("title") or "")]
    if not docs:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in ardfm/{indicator_id}",
                f"WHAT CHANGED: no document titled {BANKING_TITLE_FILTER!r} with a parseable "
                "'на DD.MM.YYYY' date is listed",
                f"ACTION REQUIRED: inspect {LISTING_URL}?title={BANKING_TITLE_FILTER} and update "
                "scripts/fetchers/ardfm.py",
            ])
        )
    return docs


def _pdf_text(content: bytes) -> str:
    """Extracted text of one bulletin, parsed once per process.

    Cached for the same reason the download is: thirty indicators over three
    bulletins meant ninety pypdf parses of a fourteen-page document per run,
    which dominated the module's runtime even after the bytes were cached.
    Keyed by the document's own bytes, so two different documents never share
    an entry and a changed document is re-parsed.
    """
    key = hashlib.sha256(content).hexdigest()
    cached = _TEXT_CACHE.get(key)
    if cached is not None:
        return cached
    text = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(content)).pages)
    _TEXT_CACHE[key] = text
    return text


def _table_body(text: str, number: int) -> str:
    """Text of one numbered table, from its heading to the next table's heading.

    The document opens with a contents list whose entries also start 'Таблица
    N.', so the LAST occurrence is taken -- the contents entry is a dotted line
    with a page number and carries none of the data rows.
    """
    starts = [m.start() for m in re.finditer(rf"Таблица {number}\.", text)]
    if not starts:
        return ""
    begin = starts[-1]
    rest = text[begin:]
    nxt = re.search(r"\nТаблица \d+\.", rest[1:])
    return rest[: nxt.start() + 1] if nxt else rest


def _row_numbers(table: str, label: str, indicator_id: str, expect: int,
                 exclude: str | None = None) -> list[float]:
    """Numbers on the row whose label starts with `label`, label removed first.

    Removing the label matters: the digit in 'k1' and the '90' in 'свыше 90
    дней' are otherwise read as values. `expect` is the number of values the
    row must yield -- a changed column count raises rather than shifting every
    later column silently.
    """
    for line in table.split("\n"):
        stripped = line.strip()
        if not stripped.startswith(label):
            continue
        # `exclude` separates nested labels: 'Всего активы' is a prefix of
        # 'Всего активы (без учета резервов (провизий))', and BOTH rows carry
        # five numbers, so the column-count check alone cannot tell them apart.
        if exclude is not None and exclude in stripped:
            continue
        tail = stripped[len(label):]
        values = []
        for token in re.findall(r"-?\d[\d   ]*(?:,\d+)?", tail):
            cleaned = token.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
            try:
                values.append(float(cleaned))
            except ValueError:
                continue
        if len(values) == expect:
            return values
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in ardfm/{indicator_id}",
                f"WHAT CHANGED: row {label!r} yielded {len(values)} numbers, expected {expect}",
                f"ACTUAL LINE: {stripped[:160]!r}",
                "EXPECTED: a stable column count; a change shifts every later column silently",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/ardfm.py",
            ])
        )
    return []


def _column_dates(table: str, indicator_id: str) -> list[tuple[int, int]]:
    """The (year, month) of each data column, read from the table's own header.

    Anchored to the header marker "Наименование", not to a line offset. In some
    editions a chart is extracted ahead of the table it belongs to -- the
    01.06.2026 bulletin puts table 16's real header on line 33 of its span --
    so counting lines from the top of the span finds nothing at all. The dates
    sit either on the marker line itself or on the next one or two, depending
    on the table.

    Chart axis labels are a live hazard here: one of them reads
    "01.01.26 01.02.26 01.03.26 01.04.2026 01.05.2026 01.06.2026", mixing two-
    and four-digit years. Requiring four digits rejects the short ones, and
    anchoring to the header keeps the long ones out of range.
    """
    body = table.split("\n")
    start = next((k for k, line in enumerate(body) if "Наименование" in line), None)
    window = body[start:start + 3] if start is not None else body[:8]
    found: list[tuple[int, int]] = []
    for line in window:
        for m in COLUMN_DATE_RE.finditer(line):
            pair = (int(m.group(3)), int(m.group(2)))
            if pair not in found:
                found.append(pair)
        if len(found) >= 2:
            break
    return found

def _fetch_banking_series(table_no: int, label: str, expect: int, value_index: int,
                          indicator_id: str, note: str, unit: str,
                          date_index: int | None = None,
                          absolute: bool = False,
                          exclude: str | None = None) -> tuple[list[dict], dict]:
    """One series from one row of one table, across every listed edition.

    `value_index` picks the column within the row. `date_index` says which of
    the table's own header dates that column belongs to; when None the
    document's reporting date is used (tables that print a single column).
    """
    processed = (Path(__file__).resolve().parents[2] / "data" / "processed" / SOURCE
                 / f"{indicator_id.lower()}.csv")
    existing: dict[str, float] = {}
    if processed.exists():
        import csv as _csv
        with processed.open(encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                try:
                    existing[row["date"]] = float(row["value"])
                except (KeyError, TypeError, ValueError):
                    continue

    fetched: dict[str, float] = {}
    inspected = 0
    for doc in _list_banking_bulletins(indicator_id):
        title = doc.get("title") or ""
        m = REPORT_DATE_RE.search(title)
        full_text = doc.get("full_text") or []
        if not m or not full_text:
            continue
        path = full_text[0].get("document")
        if not path:
            continue

        content = _download(path)
        text = _pdf_text(content)
        table = _table_body(text, table_no)
        if not table:
            continue
        values = _row_numbers(table, label, indicator_id, expect, exclude=exclude)
        if not values:
            continue
        inspected += 1

        if date_index is None:
            year, month = int(m.group(3)), int(m.group(2))
        else:
            dates = _column_dates(table, indicator_id)
            if len(dates) <= date_index:
                raise validation.StructuralChangeError(
                    "\n".join([
                        f"STRUCTURAL CHANGE DETECTED in ardfm/{indicator_id}",
                        f"WHAT CHANGED: table {table_no} header carries {len(dates)} column "
                        f"date(s), expected at least {date_index + 1}",
                        f"ACTUAL: {dates}",
                        "ACTION REQUIRED: inspect a recent bulletin and update "
                        "scripts/fetchers/ardfm.py",
                    ])
                )
            year, month = dates[date_index]

        _save_raw(f"{indicator_id}_{year:04d}{month:02d}", content,
                  {"source_url": GOV_KZ_BASE + path, "document_id": doc.get("id"),
                   "title": title, "table": table_no, "row": label})
        value = values[value_index]
        # The provisions row is printed with a leading minus in some editions and
        # without one in others for the identical figure -- 1,925.9 at 01.01.2026
        # appears as both '-1 925,9' and '1 925,9'. That is a presentation change,
        # not a data change, so the magnitude is stored and the sign discarded
        # rather than letting it manufacture a swing of twice the value.
        fetched[f"{year:04d}-{month:02d}-01"] = abs(value) if absolute else value

    merged = {**existing, **fetched}
    if not merged:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in ardfm/{indicator_id}",
                f"WHAT CHANGED: no listed bulletin yielded table {table_no} row {label!r} with "
                f"{expect} numbers, and no processed history exists",
                f"ACTUAL: {inspected} bulletin(s) had the expected shape",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/ardfm.py",
            ])
        )

    records = [{"date": d, "value": v} for d, v in sorted(merged.items())]
    manifest = {
        "frequency": "monthly",
        "source_url": f"{LISTING_URL}?title={BANKING_TITLE_FILTER}",
        "dataset_id": f"ardfm-banking-bulletin/table-{table_no}/{label}/col{value_index}",
        "note": note,
        "unit": unit,
    }
    return records, manifest


# --- Table 4: loan portfolio quality -----------------------------------------
# Columns per row: [amount at 1 January, share at 1 January, amount at the
# reporting date, share at the reporting date, growth %]. Both dated columns
# are read, so each edition contributes the reporting month and the year-start
# figure; the year-start column repeats across editions of the same year and
# merges to one point.
TABLE_LOANS = 4
ROW_LOANS_TOTAL = "Банковские займы, в т.ч.:"
ROW_NPL_90 = "Займы с просроченной задолженностью свыше 90 дней"
ROW_PROVISIONS = "Провизии по МСФО"

# --- Table 12: capital adequacy ----------------------------------------------
# Single column, the reporting date only. NOTE 'k1' is a prefix of 'k1-2': the
# label is stripped and the number count checked, so the two cannot be confused.
TABLE_CAPITAL = 12
ROW_K1 = "Коэффициент достаточности собственного капитала k1 "
ROW_K2 = "Коэффициент достаточности собственного капитала k2"

# --- Table 14: profitability --------------------------------------------------
# Columns: [1 January, reporting date]. The ratios are trailing twelve-month
# averages, which the table states in its own footnote.
TABLE_PROFIT = 14
ROW_ROA = "Отношение чистого дохода к совокупным активам (ROA)"
ROW_ROE = "Отношение чистого дохода к собственному капиталу по балансу (ROE)"
ROW_NET_INCOME = "Чистый доход (убыток) после уплаты подоходного налога"

_FROZEN_NOTE = (
    "Source: ARDFM, the financial market regulator, which took over banking supervision. This "
    "does NOT continue the NBK series of the same concept (frozen at 2024-04-01, NBK formId=314 "
    "stopped updating): different compiler, monthly rather than quarterly, and the definitions "
    "are not verified to match. Read them as two series, not one. ")


def fetch_bank_npl_90_share() -> tuple[list[dict], dict]:
    """Loans overdue more than 90 days, share of the loan book, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS, ROW_NPL_90, 5, 3, "BANK_NPL_90_SHARE",
        _FROZEN_NOTE + "Percent of total bank loans overdue by more than 90 days -- 4.12% at "
        "01.07.2026 against 3.63% at 01.01.2026. The frozen NBK NPL_RATIO last read 3.06% for "
        "2024-04-01, so the level and direction are consistent, but the two are compiled "
        "differently and must not be spliced.",
        "%", date_index=1)


def fetch_bank_npl_90_amount() -> tuple[list[dict], dict]:
    """Loans overdue more than 90 days, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS, ROW_NPL_90, 5, 2, "BANK_NPL_90_AMOUNT",
        _FROZEN_NOTE + "Billion KZT of principal on loans overdue by more than 90 days. Read "
        "against BANK_PROVISIONS_IFRS for coverage.",
        "billion KZT", date_index=1)


def fetch_bank_loans_total() -> tuple[list[dict], dict]:
    """Total bank loans, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS, ROW_LOANS_TOTAL, 5, 2, "BANK_LOANS_TOTAL",
        _FROZEN_NOTE + "Billion KZT, principal outstanding on all bank loans -- 44,754.2 bln at "
        "01.07.2026. The frozen NBK LOANS_TO_ECONOMY last read 30,283 bln for 2024-04-01; the "
        "concepts differ (loans to the economy against all bank loans) as well as the compiler.",
        "billion KZT", date_index=1)


def fetch_bank_provisions_ifrs() -> tuple[list[dict], dict]:
    """IFRS provisions against the loan book, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS, ROW_PROVISIONS, 5, 2, "BANK_PROVISIONS_IFRS",
        _FROZEN_NOTE + "Billion KZT of IFRS provisions. THE SOURCE IS INCONSISTENT ABOUT THE "
        "SIGN: the 01.05 and 01.06.2026 editions print this row negative and the 01.07.2026 "
        "edition prints it positive, while the shared 01.01.2026 figure is 1,925.9 in both "
        "presentations. That is a formatting change, not a data change, so the MAGNITUDE is "
        "stored and the sign discarded -- keeping it would manufacture a swing of twice the "
        "value between two consecutive months.",
        "billion KZT", date_index=1, absolute=True)


def fetch_bank_capital_adequacy_k1() -> tuple[list[dict], dict]:
    """Tier 1 capital adequacy ratio k1, percent, monthly."""
    return _fetch_banking_series(
        TABLE_CAPITAL, ROW_K1, 1, 0, "BANK_CAPITAL_ADEQUACY_K1",
        _FROZEN_NOTE + "Percent. Kazakhstan's k1 ratio, 19.7% at 01.07.2026. The label 'k1' is a "
        "prefix of 'k1-2' in the same table, so the row is matched with a trailing space and the "
        "number count checked.",
        "%")


def fetch_bank_capital_adequacy_k2() -> tuple[list[dict], dict]:
    """Total capital adequacy ratio k2, percent, monthly."""
    return _fetch_banking_series(
        TABLE_CAPITAL, ROW_K2, 1, 0, "BANK_CAPITAL_ADEQUACY_K2",
        _FROZEN_NOTE + "Percent. Total capital ratio, 20.5% at 01.07.2026 -- the closest "
        "counterpart to the frozen NBK CAPITAL_ADEQUACY_RATIO, which last read 21.44% for "
        "2024-04-01.",
        "%")


def fetch_bank_roa_monthly() -> tuple[list[dict], dict]:
    """Return on assets, percent, monthly."""
    return _fetch_banking_series(
        TABLE_PROFIT, ROW_ROA, 2, 1, "BANK_ROA_MONTHLY",
        _FROZEN_NOTE + "Percent, TRAILING TWELVE-MONTH average as the table's own footnote "
        "states -- 3.65% at 01.07.2026. BEWARE when reading the source directly: the same figure "
        "appears earlier in the narrative text as '3,7% (4,6% на аналогичную дату)', rounded and "
        "compared against the same date a year earlier rather than the start of the year. This "
        "fetcher reads the table, not the narrative.",
        "%", date_index=1)


def fetch_bank_roe_monthly() -> tuple[list[dict], dict]:
    """Return on equity, percent, monthly."""
    return _fetch_banking_series(
        TABLE_PROFIT, ROW_ROE, 2, 1, "BANK_ROE_MONTHLY",
        _FROZEN_NOTE + "Percent, trailing twelve-month average -- 24.14% at 01.07.2026 against "
        "28.55% at 01.01.2026. Same narrative-versus-table trap as BANK_ROA_MONTHLY.",
        "%", date_index=1)


def fetch_bank_net_income() -> tuple[list[dict], dict]:
    """Banking sector net income after tax, billion KZT, cumulative from January."""
    return _fetch_banking_series(
        TABLE_PROFIT, ROW_NET_INCOME, 2, 1, "BANK_NET_INCOME",
        _FROZEN_NOTE + "Billion KZT after tax. CUMULATIVE FROM 1 JANUARY, not a monthly flow: "
        "795.9 at 01.05.2026, 1,035.7 at 01.06.2026, 1,195.6 at 01.07.2026, against 2,723.7 for "
        "the whole of 2025. The year-start column is that full prior-year figure, so it is not "
        "read here -- only the reporting-date column.",
        "billion KZT", date_index=1)


# ---------------------------------------------------------------------------
# The rest of the bulletin: balance sheet, deposits, liquidity, and the
# sector's size relative to GDP.
#
# WHERE THE ASSET ROWS ACTUALLY LIVE. "Таблица 2. Структура совокупных активов"
# extracts as a heading and nothing else -- its data is a chart, not text. The
# asset rows are nonetheless in the document, and they fall inside TABLE 1's
# span in every edition checked. They are therefore anchored to table 1, not to
# the table whose heading names them.
#
# THE ASSET LABELS NEST, like the capital ratios did. "Всего активы" is a
# prefix of "Всего активы (без учета резервов (провизий))" and BOTH rows carry
# five numbers, so a column-count check cannot separate them -- the net figure
# is matched with an explicit exclusion.
#
# WHICH ASSET MEASURE THE GDP RATIO USES, checked rather than assumed: the
# bulletin's own "Отношение активов к ВВП" reads 45.3% for 01.07.2026, and
# 74,226.8 / 163,678.5 = 45.35% while the gross figure would give 46.7%. So the
# ratio is built on NET assets. Recorded because the bulletin publishes both
# asset measures without saying which feeds the ratio.
#
# NOT PUBLISHED, so not derived: balance-sheet equity has no clean total row
# (the label "Всего расчетный собственный капитал" wraps onto its own line with
# no figures), so assets = liabilities + equity cannot be checked here. Gross
# assets minus provisions does not reproduce net assets either -- the gap is
# about 120 bln KZT at both dates -- so provisions are not the only difference
# and that is not an identity either.
# ---------------------------------------------------------------------------
TABLE_ASSETS = 1          # not table 2: see the comment above
TABLE_LIABILITIES = 8
TABLE_DEPOSITS = 9
TABLE_LIQUIDITY = 13
TABLE_ROLE = 16

ROW_ASSETS_NET = "Всего активы"
ROW_ASSETS_NET_EXCLUDE = "(без учета"
ROW_ASSETS_GROSS = "Всего активы (без учета резервов (провизий))"
ROW_LIABILITIES = "Всего обязательств"
ROW_CLIENT_DEPOSITS = "Вклады клиентов"
ROW_DEPOSITS_LEGAL = "Вклады юридических лиц"
ROW_DEPOSITS_INDIVIDUALS = "Вклады физических лиц"
ROW_LIQUID_ASSETS = "Высоколиквидные активы (среднемесячное значение)"
ROW_ASSETS_TO_GDP = "Отношение активов к ВВП"
ROW_LOANS_TO_GDP = "Отношение ссудного портфеля к ВВП"
ROW_DEPOSITS_TO_GDP = "Отношение вкладов клиентов к ВВП"


def fetch_bank_assets_total() -> tuple[list[dict], dict]:
    """Total banking sector assets, net of provisions, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_ASSETS, ROW_ASSETS_NET, 5, 2, "BANK_ASSETS_TOTAL",
        _FROZEN_NOTE + "Billion KZT, NET of provisions -- 74,226.8 at 01.07.2026. This is the "
        "figure the sector audit asked for and that NBK could not supply: formId=1 lists 45 "
        "balance-sheet lines and publishes no total at all, and formId=60 returns seven "
        "unlabelled rows per bank-date. ARDFM publishes the total outright. Note the label is a "
        "prefix of the gross row, so the two are separated explicitly rather than by column "
        "count, which is identical for both.",
        "billion KZT", date_index=1, exclude=ROW_ASSETS_NET_EXCLUDE)


def fetch_bank_assets_gross() -> tuple[list[dict], dict]:
    """Banking sector assets before provisions, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_ASSETS, ROW_ASSETS_GROSS, 5, 2, "BANK_ASSETS_GROSS",
        _FROZEN_NOTE + "Billion KZT, BEFORE provisions -- 76,425.4 at 01.07.2026 against 74,226.8 "
        "net. The two do not differ by the provisions figure alone (the gap is about 120 bln "
        "wider), so the pair is published as-is rather than reconciled here.",
        "billion KZT", date_index=1)


def fetch_bank_liabilities_total() -> tuple[list[dict], dict]:
    """Total banking sector liabilities, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LIABILITIES, ROW_LIABILITIES, 5, 2, "BANK_LIABILITIES_TOTAL",
        _FROZEN_NOTE + "Billion KZT -- 63,037.1 at 01.07.2026, of which client deposits are 80.5%. "
        "Balance-sheet equity is NOT published as a clean total in this bulletin, so assets minus "
        "liabilities is not offered as an equity series here.",
        "billion KZT", date_index=1)


def fetch_bank_client_deposits() -> tuple[list[dict], dict]:
    """Client deposits, billion KZT, monthly.

    Runs the cross-table deposit-split identity on every fetch.
    """
    records, manifest = _fetch_banking_series(
        TABLE_LIABILITIES, ROW_CLIENT_DEPOSITS, 5, 2, "BANK_CLIENT_DEPOSITS",
        _FROZEN_NOTE + "Billion KZT -- 50,716.0 at 01.07.2026, 80.5% of all bank liabilities. "
        "Kazakhstan's banks are deposit-funded to an unusual degree, which is the context for "
        "reading BANK_LIABILITIES_TOTAL. The label appears on five lines across the document; "
        "this one is anchored to the liabilities table.",
        "billion KZT", date_index=1)
    manifest["identity_editions_checked"] = _verify_deposit_split("BANK_CLIENT_DEPOSITS")
    return records, manifest


def fetch_bank_deposits_legal_entities() -> tuple[list[dict], dict]:
    """Deposits of legal entities, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_DEPOSITS, ROW_DEPOSITS_LEGAL, 6, 3, "BANK_DEPOSITS_LEGAL_ENTITIES",
        _FROZEN_NOTE + "Billion KZT -- 20,579.9 at 01.07.2026. This table carries SIX numbers per "
        "row, not five: [amount, of which foreign currency, FX share, then the same three for the "
        "reporting date]. The FX columns are what make it worth taking separately from the "
        "aggregate.",
        "billion KZT", date_index=1)


def fetch_bank_deposits_individuals() -> tuple[list[dict], dict]:
    """Deposits of individuals, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_DEPOSITS, ROW_DEPOSITS_INDIVIDUALS, 6, 3, "BANK_DEPOSITS_INDIVIDUALS",
        _FROZEN_NOTE + "Billion KZT -- 30,136.2 at 01.07.2026, half again the corporate figure. "
        "Same six-column layout as BANK_DEPOSITS_LEGAL_ENTITIES.",
        "billion KZT", date_index=1)


def fetch_bank_deposits_individuals_fx_share() -> tuple[list[dict], dict]:
    """Share of individuals' deposits held in foreign currency, percent, monthly."""
    return _fetch_banking_series(
        TABLE_DEPOSITS, ROW_DEPOSITS_INDIVIDUALS, 6, 5, "BANK_DEPOSITS_INDIVIDUALS_FX_SHARE",
        _FROZEN_NOTE + "Percent of household deposits denominated in foreign currency -- 20.2% at "
        "01.07.2026, down from 21.8% at 01.01.2026. THIS IS A PUBLISHED DOLLARIZATION MEASURE, "
        "which NBK could not supply: its formId=42 carries the right currency dimension but "
        "returns ten unlabelled rows per date-currency. Household deposits only, not the whole "
        "banking system.",
        "%", date_index=1)


def fetch_bank_liquid_assets() -> tuple[list[dict], dict]:
    """Highly liquid assets, monthly average, billion KZT."""
    return _fetch_banking_series(
        TABLE_LIQUIDITY, ROW_LIQUID_ASSETS, 2, 1, "BANK_LIQUID_ASSETS",
        _FROZEN_NOTE + "Billion KZT, MONTHLY AVERAGE as the row states -- 21,945.4 at 01.07.2026, "
        "about 30% of assets. Not a point-in-time stock, so it does not sit on the balance sheet "
        "alongside BANK_ASSETS_TOTAL.",
        "billion KZT", date_index=1)


def fetch_bank_assets_to_gdp() -> tuple[list[dict], dict]:
    """Banking sector assets as a share of GDP, percent, monthly."""
    return _fetch_banking_series(
        TABLE_ROLE, ROW_ASSETS_TO_GDP, 2, 1, "BANK_ASSETS_TO_GDP",
        _FROZEN_NOTE + "Percent -- 45.3% at 01.07.2026. Published by the source, not computed "
        "here. It is built on the NET asset figure: 74,226.8 / 163,678.5 = 45.35%, while gross "
        "assets would give 46.7%. The bulletin publishes both asset measures without saying which "
        "feeds the ratio, so this was checked rather than assumed.",
        "%", date_index=1)


def fetch_bank_loans_to_gdp() -> tuple[list[dict], dict]:
    """Bank loan portfolio as a share of GDP, percent, monthly."""
    return _fetch_banking_series(
        TABLE_ROLE, ROW_LOANS_TO_GDP, 2, 1, "BANK_LOANS_TO_GDP",
        _FROZEN_NOTE + "Percent -- 27.3% at 01.07.2026. The standard measure of financial depth, "
        "and the one the sector audit listed as a derived indicator; it turns out the source "
        "publishes it directly, so nothing is computed here. Low by international standards, "
        "which is the usual starting point for any credit-cycle discussion about Kazakhstan.",
        "%", date_index=1)


def fetch_bank_deposits_to_gdp() -> tuple[list[dict], dict]:
    """Client deposits as a share of GDP, percent, monthly."""
    return _fetch_banking_series(
        TABLE_ROLE, ROW_DEPOSITS_TO_GDP, 2, 1, "BANK_DEPOSITS_TO_GDP",
        _FROZEN_NOTE + "Percent -- 31.0% at 01.07.2026. Deposits exceed loans relative to GDP, "
        "the mirror of the deposit-funded structure visible in BANK_LIABILITIES_TOTAL.",
        "%", date_index=1)


# ---------------------------------------------------------------------------
# Cross-table identity: the deposits table (9) splits client deposits into
# legal entities and individuals, and the liabilities table (8) carries the
# total. The two tables are compiled separately, so this checks the row
# lookups rather than restating one number.
#
# Verified across all three editions online on 2026-09-02: 19,581.9 + 28,586.4
# = 48,168.3 exactly, 19,634.2 + 29,311.6 = 48,945.8 exactly, and 20,579.9 +
# 30,136.2 = 50,716.1 against a published 50,716.0 -- one rounding step, which
# is what the tolerance allows for.
# ---------------------------------------------------------------------------
DEPOSIT_SPLIT_TOLERANCE = 0.5  # billion KZT; the tables round to one decimal


def _verify_deposit_split(indicator_id: str) -> int:
    """legal entities + individuals == client deposits, per edition."""
    checked = 0
    for doc in _list_banking_bulletins(indicator_id):
        full_text = doc.get("full_text") or []
        if not full_text or not full_text[0].get("document"):
            continue
        text = _pdf_text(_download(full_text[0]["document"]))
        total_row = _row_numbers(_table_body(text, TABLE_LIABILITIES),
                                 ROW_CLIENT_DEPOSITS, indicator_id, 5)
        deposits = _table_body(text, TABLE_DEPOSITS)
        legal = _row_numbers(deposits, ROW_DEPOSITS_LEGAL, indicator_id, 6)
        people = _row_numbers(deposits, ROW_DEPOSITS_INDIVIDUALS, indicator_id, 6)
        if not (total_row and legal and people):
            continue
        checked += 1
        parts = legal[3] + people[3]
        if abs(parts - total_row[2]) > DEPOSIT_SPLIT_TOLERANCE:
            raise validation.StructuralChangeError(
                "\n".join([
                    f"STRUCTURAL CHANGE DETECTED in ardfm/{indicator_id}",
                    f"WHAT CHANGED: in {doc.get('title') or ''!r} the deposit split does not add "
                    f"up -- legal entities {legal[3]:,.1f} plus individuals {people[3]:,.1f} = "
                    f"{parts:,.1f}, against client deposits of {total_row[2]:,.1f}",
                    "EXPECTED: tables 8 and 9 are compiled separately and must reconcile; a "
                    "mismatch means a row lookup has drifted onto the wrong line",
                    "ACTION REQUIRED: inspect a recent bulletin and update "
                    "scripts/fetchers/ardfm.py",
                ])
            )
    if checked == 0:
        raise validation.StructuralChangeError(
            "\n".join([
                f"STRUCTURAL CHANGE DETECTED in ardfm/{indicator_id}",
                "WHAT CHANGED: no edition carried both the deposits split and the client-deposit "
                "total, so the cross-table identity could not be checked on any date",
                "ACTION REQUIRED: inspect a recent bulletin and update scripts/fetchers/ardfm.py",
            ])
        )
    return checked


# ---------------------------------------------------------------------------
# Loan quality by borrower segment (tables 5, 6, 7), the capital component
# published in the funding table (11), and market concentration (15).
#
# WHY THE SEGMENTS ARE WORTH SEPARATING: the headline 90-day overdue share is
# 4.12%, and it hides a wide spread. At 01.07.2026 corporate loans run 2.0%,
# SME 3.9% and retail 4.8%. The three move differently too -- corporate
# overdue debt FELL 20.8% since the start of the year while SME rose 40.1% --
# so the aggregate is an average of divergent trends rather than a summary of
# a common one.
#
# THE THREE SEGMENTS DO NOT SUM TO THE TOTAL PORTFOLIO, and that is left as it
# is rather than reconciled. Corporate + retail + SME gives 44,449.9 bln KZT
# against a published 44,754.2 at 01.07.2026 -- a residual of about 304 bln,
# and the gap is a stable 304-322 bln (roughly 0.7%) across all three editions.
# Something sits outside the three named categories; the bulletin does not say
# what, so no identity is asserted and nothing is derived from the difference.
# Anyone summing these three and expecting BANK_LOANS_TOTAL should know that in
# advance.
#
# Table 15's rows end their label with a bare "%" before the figures, which
# yields no number and so does not disturb the column count.
# ---------------------------------------------------------------------------
TABLE_LOANS_CORPORATE = 5
TABLE_LOANS_RETAIL = 6
TABLE_LOANS_SME = 7
TABLE_FUNDING = 11
TABLE_CONCENTRATION = 15

ROW_SEGMENT_NPL_90 = ROW_NPL_90          # the same label heads the 90-day row in every segment table
ROW_CORPORATE_TOTAL = "Займы юридических лиц, в т.ч.:"
ROW_RETAIL_TOTAL = "Займы физических лиц, в т.ч.:"
ROW_SME_TOTAL = "Займы МСБ, в т.ч.:"
ROW_SHARE_CAPITAL = "Уставный капитал"
ROW_TOP5_ASSETS = "Доля 5 крупнейших банков в совокупных активах"
ROW_TOP5_LOANS = "Доля 5 крупнейших банков в совокупном ссудном портфеле"
ROW_TOP5_DEPOSITS = "Доля 5 крупнейших банков в совокупных вкладах клиентов"

_SEGMENT_NOTE = (
    "The three borrower segments do NOT sum to BANK_LOANS_TOTAL -- corporate plus retail plus SME "
    "is about 304 bln KZT short of the published portfolio, a stable ~0.7% gap across every "
    "edition. Something sits outside the three named categories and the bulletin does not say "
    "what, so the difference is neither explained nor used here. ")


def fetch_bank_loans_corporate() -> tuple[list[dict], dict]:
    """Loans to legal entities, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS_CORPORATE, ROW_CORPORATE_TOTAL, 5, 2, "BANK_LOANS_CORPORATE",
        _FROZEN_NOTE + "Billion KZT -- 6,428.2 at 01.07.2026, DOWN 11.1% since the start of the "
        "year while retail and SME both grew. The corporate book is the smallest of the three "
        "segments and the only one shrinking. " + _SEGMENT_NOTE,
        "billion KZT", date_index=1)


def fetch_bank_npl_90_corporate_share() -> tuple[list[dict], dict]:
    """Corporate loans overdue more than 90 days, share, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS_CORPORATE, ROW_SEGMENT_NPL_90, 5, 3, "BANK_NPL_90_CORPORATE_SHARE",
        _FROZEN_NOTE + "Percent of the corporate loan book overdue by more than 90 days -- 2.0% "
        "at 01.07.2026, HALF the headline 4.12%, and the overdue amount fell 20.8% since the "
        "start of the year. Read with the retail and SME shares before treating the aggregate as "
        "a description of credit risk.",
        "%", date_index=1)


def fetch_bank_loans_retail() -> tuple[list[dict], dict]:
    """Loans to individuals, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS_RETAIL, ROW_RETAIL_TOTAL, 5, 2, "BANK_LOANS_RETAIL",
        _FROZEN_NOTE + "Billion KZT -- 25,848.9 at 01.07.2026, the largest segment by far and "
        "four times the corporate book. " + _SEGMENT_NOTE,
        "billion KZT", date_index=1)


def fetch_bank_npl_90_retail_share() -> tuple[list[dict], dict]:
    """Retail loans overdue more than 90 days, share, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS_RETAIL, ROW_SEGMENT_NPL_90, 5, 3, "BANK_NPL_90_RETAIL_SHARE",
        _FROZEN_NOTE + "Percent of the household loan book overdue by more than 90 days -- 4.8% "
        "at 01.07.2026, the highest of the three segments and rising. Since retail is also the "
        "largest book, this is what pulls the headline rate up.",
        "%", date_index=1)


def fetch_bank_loans_sme() -> tuple[list[dict], dict]:
    """Loans to small and medium enterprises, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS_SME, ROW_SME_TOTAL, 5, 2, "BANK_LOANS_SME",
        _FROZEN_NOTE + "Billion KZT -- 12,172.8 at 01.07.2026, up 9.6% since the start of the "
        "year, the fastest-growing of the three segments. " + _SEGMENT_NOTE,
        "billion KZT", date_index=1)


def fetch_bank_npl_90_sme_share() -> tuple[list[dict], dict]:
    """SME loans overdue more than 90 days, share, monthly."""
    return _fetch_banking_series(
        TABLE_LOANS_SME, ROW_SEGMENT_NPL_90, 5, 3, "BANK_NPL_90_SME_SHARE",
        _FROZEN_NOTE + "Percent of the SME loan book overdue by more than 90 days -- 3.9% at "
        "01.07.2026, and the overdue AMOUNT rose 40.1% since the start of the year, the sharpest "
        "deterioration of the three segments. Growing fast and souring fastest is the combination "
        "worth watching here.",
        "%", date_index=1)


def fetch_bank_share_capital() -> tuple[list[dict], dict]:
    """Share capital of the banking sector, billion KZT, monthly."""
    return _fetch_banking_series(
        TABLE_FUNDING, ROW_SHARE_CAPITAL, 4, 2, "BANK_SHARE_CAPITAL",
        _FROZEN_NOTE + "Billion KZT of paid-in share capital -- 1,600.6 at 01.07.2026, 2.2% of "
        "total funding. This is a COMPONENT of equity, not total equity: the bulletin does not "
        "publish a balance-sheet equity total anywhere, which is why BANK_LIABILITIES_TOTAL has "
        "no equity counterpart. The funding table carries four numbers per row rather than five.",
        "billion KZT", date_index=1)


def fetch_bank_top5_assets_share() -> tuple[list[dict], dict]:
    """Share of the five largest banks in sector assets, percent, monthly."""
    return _fetch_banking_series(
        TABLE_CONCENTRATION, ROW_TOP5_ASSETS, 2, 1, "BANK_TOP5_ASSETS_SHARE",
        _FROZEN_NOTE + "Percent -- 69.2% at 01.07.2026. Kazakhstan's banking system is highly "
        "concentrated, which is context for reading every sector aggregate here: the averages are "
        "dominated by a handful of institutions.",
        "%", date_index=1)


def fetch_bank_top5_loans_share() -> tuple[list[dict], dict]:
    """Share of the five largest banks in the sector loan portfolio, percent."""
    return _fetch_banking_series(
        TABLE_CONCENTRATION, ROW_TOP5_LOANS, 2, 1, "BANK_TOP5_LOANS_SHARE",
        _FROZEN_NOTE + "Percent -- 75.8% at 01.07.2026. Lending is MORE concentrated than assets "
        "(69.2%) or deposits (72.7%), so the segment NPL rates are largely a statement about five "
        "banks.",
        "%", date_index=1)


def fetch_bank_top5_deposits_share() -> tuple[list[dict], dict]:
    """Share of the five largest banks in client deposits, percent, monthly."""
    return _fetch_banking_series(
        TABLE_CONCENTRATION, ROW_TOP5_DEPOSITS, 2, 1, "BANK_TOP5_DEPOSITS_SHARE",
        _FROZEN_NOTE + "Percent -- 72.7% at 01.07.2026.",
        "%", date_index=1)
