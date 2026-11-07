"""National Bank monetary operations (added 2026-11-07): foreign-exchange interventions,
the open position of the NBK's liquidity operations, deposit auctions.

NBK_FX_INTERVENTIONS  https://nationalbank.kz/ru/news/foreign-exchange-market-interventions:
    the history tab (rubrics/1990) is an HTML matrix year x month of the NBK's net operations
    on the FX market, mln USD, 1996 on («+» net purchase, «−» net sale; «*» marks the 2024
    operations to buy Kazatomprom shares for the National Fund; the November 2024 cell is
    free text «- 1 181 (включая 133,8*)», read as -1181). The year tabs from 2025 add a table of
    FX sales «для целей монетарной нейтральности» mirroring the priority purchases of refined
    gold (mln USD and bn KZT, from 2025-01); every tab linked from the page is read for it.
NBK_OPEN_POSITION  https://nationalbank.kz/ru/nbkoperation/otkrytaya-poziciya-po-operaciyam-nbk:
    daily balances of the NBK's liquidity operations, bn KZT (negative = the NBK absorbs
    liquidity), `/records` JSON from 2023-11-08; before that the xlsx annexes of the Monetary
    Policy Report (/file/download/85709 sheet «13», 2020-01-05 … 2022-11-30; 99362 sheet «12»,
    2022-01-05 … 2024-01-31; equal to the JSON on all 58 common days, checked 2026-11-07).
    Kept monthly: <ITEM>.AVG (mean of the business days) and <ITEM>.EOM (last business day).
NBK_DEPOSIT_AUCTIONS  https://nationalbank.kz/ru/depositauction/depozitnyy-aukcion-nbk,
    `/excel?from=…&to=…`: one row per auction from 2019-02. Kept monthly: VOLUME (bn KZT
    placed, by auction date), N (auctions), YIELD (volume-weighted average yield, %).
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path

import openpyxl
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
NBK = "https://nationalbank.kz"
INTERVENTIONS_PAGE = f"{NBK}/ru/news/foreign-exchange-market-interventions"
INTERVENTIONS_HISTORY = f"{INTERVENTIONS_PAGE}/rubrics/1990"
OPEN_POSITION_RECORDS = f"{NBK}/ru/nbkoperation/otkrytaya-poziciya-po-operaciyam-nbk/records"
OPEN_POSITION_ANNEXES = [(f"{NBK}/file/download/85709", "13"), (f"{NBK}/file/download/99362", "12")]
DEPOSIT_AUCTIONS_XLSX = f"{NBK}/ru/depositauction/depozitnyy-aukcion-nbk/excel"

MONTHS = {"январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6, "июль": 7, "август": 8,
          "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12}
MONTH_STEMS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
               "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}

# open position: JSON field, item code, Russian name (annex columns are in this order after the date and balance)
OPEN_POSITION_ITEMS = [
    ("b", "BALANCE", "Сальдо открытой позиции"),
    ("d", "DEPOSITS", "Депозиты БВУ (операции постоянного доступа)"),
    ("d_r", "DIRECT_REPO", "Прямое РЕПО (операции постоянного доступа)"),
    ("r_r", "REVERSE_REPO", "Обратное РЕПО (операции постоянного доступа)"),
    ("c_s", "FX_SWAP", "Валютный своп (операции постоянного доступа)"),
    ("d_a", "DEPOSIT_AUCTION", "Депозитный аукцион (операции открытого рынка)"),
    ("nbk_a_s_s", "REPO_AUCTION", "Аукцион НБРК по покупке ценных бумаг с обратной продажей"),
    ("n", "NOTES", "Ноты НБРК (операции открытого рынка)"),
    (None, "OTHER", "Другие операции"),
]
OTHER_FIELDS = ("f_c_i_r_s_stb", "i_r_swap_mfi", "r_r_w_m", "stb_l")
CORR_FIELD = ("f_b_c_a_w_nbk", "CORR_ACCOUNTS", "Средства банков на корреспондентских счетах в НБРК (справочно)")


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"nbk/{ds['id']}: {what}")


def _get(url: str, **params) -> bytes:
    last = None
    for _ in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, params=params or None, timeout=120)
            resp.raise_for_status()
            return resp.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
    raise last  # type: ignore[misc]


def _archive(ds: dict, name: str, ext: str, content: bytes, url: str) -> None:
    today = date.today()
    path = raw_store.save_raw_bytes("nbk", name, today, ext, content)
    raw_store.write_download_manifest("nbk", name, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name if path else None, "source_url": url,
        "dataset": ds["id"]})


class _Tables(HTMLParser):
    """Every <table> as rows of cell texts (colspan cells padded); the text before each table kept as its title."""

    def __init__(self):
        super().__init__()
        self.tables, self.titles, self._stack, self._cell, self._span, self._text = [], [], [], None, 1, []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
            self.titles.append(" ".join(" ".join(self._text).split())[-300:])
            self._text = []
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack:
            self._cell, self._span = [], int(dict(attrs).get("colspan") or 1)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._stack and self._stack[-1]:
            self._stack[-1][-1].append(" ".join("".join(self._cell).split()))
            self._stack[-1][-1].extend([""] * (self._span - 1))
            self._cell = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif not self._stack:
            self._text.append(data)


def html_tables(content: bytes) -> list[tuple[str, list[list[str]]]]:
    p = _Tables()
    p.feed(content.decode("utf-8", "replace"))
    return list(zip(p.titles, p.tables))


NUMBER = re.compile(r"^[-–−]?\s*\d[\d\s]*(?:[.,]\d+)?")


def number(cell) -> float | None:
    """'-1 181 (включая 133,8*)' -> -1181; '869,8*' -> 869.8; '' / '-' / 'х' -> None."""
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell).replace("\xa0", " ").replace("*", "").strip()
    m = NUMBER.match(s)
    if not m:
        return None
    t = re.sub(r"\s", "", m.group(0)).replace("–", "-").replace("−", "-").replace(",", ".")
    return float(t)


# ---------------------------------------------------------------- interventions

def intervention_matrix(tables) -> dict[str, float]:
    """{YYYY-MM-01: net mln USD} from the history matrix (a header row with the 12 month names)."""
    for _, rows in tables:
        head = next((i for i, r in enumerate(rows) if sum(1 for c in r if c.strip().lower() in MONTHS) == 12), None)
        if head is None:
            continue
        cols = {j: MONTHS[c.strip().lower()] for j, c in enumerate(rows[head]) if c.strip().lower() in MONTHS}
        out = {}
        for r in rows[head + 1:]:
            if not r or not re.fullmatch(r"\d{4}", r[0].strip()):
                continue
            for j, m in cols.items():
                v = number(r[j]) if j < len(r) else None
                if v is not None:
                    out[f"{r[0].strip()}-{m:02d}-01"] = v
        return out
    return {}


def _month_of(label: str) -> str | None:
    s = " ".join(str(label).lower().replace("\xa0", " ").split())
    y = re.search(r"(\d{4})", s)
    word = re.sub(r"[\d\s]", "", s)
    m = next((n for stem, n in MONTH_STEMS.items() if word.startswith(stem) and (stem != "ма" or word in ("май", "мая"))), None)
    return f"{y.group(1)}-{m:02d}-01" if y and m else None


def mirroring(tables) -> dict[str, tuple[float, float | None]]:
    """{YYYY-MM-01: (mln USD, bn KZT)} from the «зеркалирование» tables of the year tabs."""
    out = {}
    for title, rows in tables:
        head = (title + " " + " ".join(" ".join(r) for r in rows[:2])).lower()   # the title is the table's first row
        if "зеркалирован" not in head or "монетарной нейтральности" not in head:
            continue
        for r in rows:
            when = _month_of(r[0]) if r else None
            if when and len(r) >= 2 and number(r[1]) is not None:
                out[when] = (number(r[1]), number(r[2]) if len(r) > 2 else None)
    return out


def fetch_interventions(ds: dict) -> tuple[list[dict], dict]:
    page = _get(INTERVENTIONS_PAGE)
    history = _get(INTERVENTIONS_HISTORY)
    tabs = sorted({int(t) for t in re.findall(r"/foreign-exchange-market-interventions/rubrics/(\d+)", page.decode("utf-8", "replace"))})
    tab_pages = {t: _get(f"{INTERVENTIONS_PAGE}/rubrics/{t}") for t in tabs if t != 1990}
    _archive(ds, ds["id"], "json", json.dumps(
        {"history": history.decode("utf-8", "replace"), **{str(t): c.decode("utf-8", "replace") for t, c in tab_pages.items()}},
        ensure_ascii=False, sort_keys=True).encode(), INTERVENTIONS_PAGE)
    net = intervention_matrix(html_tables(history))
    if len(net) < 300 or "2014-10-01" not in net:
        _structural(ds, f"history matrix not found or short ({len(net)} months) at {INTERVENTIONS_HISTORY}")
    mirror = {}
    for content in tab_pages.values():
        mirror.update(mirroring(html_tables(content)))
    records = [{"date": d, "region": dims.NATIONAL, "item_code": "NET", "value": v,
                "item_name": "Нетто-операции НБК на валютном рынке (интервенции), млн долл. США"} for d, v in net.items()]
    for d, (usd, kzt) in mirror.items():
        records.append({"date": d, "region": dims.NATIONAL, "item_code": "MIRRORING_USD", "value": usd,
                        "item_name": "Продажа валюты в рамках зеркалирования покупок золота, млн долл. США"})
        if kzt is not None:
            records.append({"date": d, "region": dims.NATIONAL, "item_code": "MIRRORING_KZT", "value": kzt,
                            "item_name": "Продажа валюты в рамках зеркалирования покупок золота, млрд тенге"})
    warnings = [] if mirror else ["no «зеркалирование» table found in the year tabs"]
    return records, {"frequency": "monthly", "source_url": INTERVENTIONS_PAGE, "dataset_id": "rubrics/1990 + year tabs",
                     "note": ds.get("note", ""), "warnings": warnings}


# ---------------------------------------------------------------- open position

def annex_days(content: bytes, sheet: str) -> dict[str, dict[str, float]]:
    ws = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)[sheet]
    out = {}
    for r in ws.iter_rows(values_only=True):
        if not r or not isinstance(r[0], datetime):
            continue
        vals = [number(c) for c in r[1:10]]
        if vals[0] is None:
            continue
        day = {code: (vals[i] or 0.0) for i, (_, code, _) in enumerate(OPEN_POSITION_ITEMS)}
        out[r[0].date().isoformat()] = day
    return out


def record_days(rows: list[dict]) -> dict[str, dict[str, float]]:
    out = {}
    for r in rows:
        day = {}
        for field, code, _ in OPEN_POSITION_ITEMS:
            day[code] = float(sum(r.get(f) or 0 for f in OTHER_FIELDS)) if field is None else float(r.get(field) or 0)
        day[CORR_FIELD[1]] = float(r.get(CORR_FIELD[0]) or 0)
        out[str(r["reporting_date"])[:10]] = day
    return out


def monthly(days: dict[str, dict[str, float]], names: dict[str, str]) -> list[dict]:
    by_month: dict[str, list[str]] = defaultdict(list)
    for d in sorted(days):
        by_month[d[:7] + "-01"].append(d)
    out = []
    for m, ds_ in by_month.items():
        for code in {c for d in ds_ for c in days[d]}:
            vals = [days[d][code] for d in ds_ if code in days[d]]
            last = [d for d in ds_ if code in days[d]][-1]
            out.append({"date": m, "region": dims.NATIONAL, "item_code": f"{code}.AVG", "value": round(sum(vals) / len(vals), 4),
                        "item_name": f"{names[code]}, в среднем за месяц"})
            out.append({"date": m, "region": dims.NATIONAL, "item_code": f"{code}.EOM", "value": round(days[last][code], 4),
                        "item_name": f"{names[code]}, на последний рабочий день месяца"})
    return out


def fetch_open_position(ds: dict) -> tuple[list[dict], dict]:
    days: dict[str, dict[str, float]] = {}
    for url, sheet in OPEN_POSITION_ANNEXES:
        content = _get(url)
        _archive(ds, f"{ds['id']}_annex_{url.rsplit('/', 1)[-1]}", "xlsx", content, url)
        days.update(annex_days(content, sheet))
    raw = _get(OPEN_POSITION_RECORDS)
    _archive(ds, ds["id"], "json", raw, OPEN_POSITION_RECORDS)
    rows = json.loads(raw)
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    fresh = record_days(rows)
    if len(fresh) < 500:
        _structural(ds, f"only {len(fresh)} days in {OPEN_POSITION_RECORDS}")
    for d, day in fresh.items():          # the identity the NBK's table states: the balance is the sum of the operations
        parts = sum(v for c, v in day.items() if c not in ("BALANCE", CORR_FIELD[1]))
        if abs(parts - day["BALANCE"]) > 0.05:
            _structural(ds, f"{d}: operations sum to {parts:.2f}, the balance is {day['BALANCE']:.2f}")
    days.update(fresh)
    names = {code: name for _, code, name in OPEN_POSITION_ITEMS} | {CORR_FIELD[1]: CORR_FIELD[2]}
    return monthly(days, names), {"frequency": "monthly", "source_url": OPEN_POSITION_RECORDS,
                                  "dataset_id": "open position records + MPR annexes 85709/99362", "note": ds.get("note", "")}


# ---------------------------------------------------------------- deposit auctions

def auction_months(rows: list[tuple]) -> list[dict]:
    head = next((i for i, r in enumerate(rows) if r and any(str(c or "").startswith("Дата аукциона") for c in r)), None)
    if head is None:
        return []
    h = [str(c or "") for c in rows[head]]
    col = {"date": h.index("Дата аукциона"),
           "volume": next(i for i, c in enumerate(h) if c.startswith("Фактический объем размещения")),
           "yield": next(i for i, c in enumerate(h) if c.startswith("Средневзвешенная доходность"))}
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])   # volume, n, volume * yield
    for r in rows[head + 1:]:
        when = str(r[col["date"]] or "").strip()
        m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", when)
        vol, yld = number(r[col["volume"]]), number(r[col["yield"]])
        if not m or vol is None:
            continue
        key = f"{m.group(3)}-{m.group(2)}-01"
        agg[key][0] += vol / 1e9
        agg[key][1] += 1
        agg[key][2] += (vol / 1e9) * (yld or 0)
    out = []
    for d, (vol, n, vy) in agg.items():
        out.append({"date": d, "region": dims.NATIONAL, "item_code": "VOLUME", "value": round(vol, 4),
                    "item_name": "Объём размещения на депозитных аукционах НБК за месяц, млрд тенге"})
        out.append({"date": d, "region": dims.NATIONAL, "item_code": "N", "value": n,
                    "item_name": "Число депозитных аукционов НБК за месяц"})
        if vol > 0:
            out.append({"date": d, "region": dims.NATIONAL, "item_code": "YIELD", "value": round(vy / vol, 4),
                        "item_name": "Средневзвешенная доходность депозитных аукционов НБК за месяц (по объёму), %"})
    return out


def fetch_deposit_auctions(ds: dict) -> tuple[list[dict], dict]:
    content = _get(DEPOSIT_AUCTIONS_XLSX, **{"from": "01.01.2000", "to": date.today().strftime("%d.%m.%Y")})
    _archive(ds, ds["id"], "xlsx", content, DEPOSIT_AUCTIONS_XLSX)
    rows = list(openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True).active.iter_rows(values_only=True))
    records = auction_months(rows)
    if len({r["date"] for r in records}) < 60:
        _structural(ds, f"only {len({r['date'] for r in records})} months of auctions in {DEPOSIT_AUCTIONS_XLSX}")
    return records, {"frequency": "monthly", "source_url": DEPOSIT_AUCTIONS_XLSX, "dataset_id": "deposit auctions xlsx",
                     "note": ds.get("note", "")}
