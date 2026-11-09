"""KazMunayGas quarterly databook («Справочник_<N>кв<YYYY>_rus.xlsx», added 2026-11-09): oil and
condensate production by asset in KMG's equity share, and crude transportation by pipeline
operator. https://www.kmg.kz/ru/investors/reporting/ lists one workbook per quarterly IFRS
release; each holds every quarter from 1Q 2015 plus annual columns, so the latest file is enough.

Sheet «стр. 6», block «ДОБЫЧА НЕФТИ»: thousand tonnes, operating assets (Озенмунайгаз,
Эмбамунайгаз, …) and the three non-operated giants in KMG's share -- Тенгизшевройл 20 %,
Норт Каспиан (Кашаган) 8.44 % to 15.09.2022 and 16.88 % after, Карачаганак 10 %. The gross
output of the giants is derived here from those shares (<ASSET>_GROSS; 2022 Q3 skipped for
Kashagan, the quarter the share changed). Sheet «стр. 7»: transport by КазТрансОйл, the
Kazakhstan-China pipeline, МунайТас and the CPC (KMG basis), million tonnes, and the export /
transit / domestic shares of pipeline transport.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, raw_store, validation  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)"}
LISTING = "https://www.kmg.kz/ru/investors/reporting/"
FILE_RE = re.compile(r'href="([^"]*?[Сс]правочник_(\d)кв(\d{4})_rus?\.xlsx)"')
QUARTER_COL = re.compile(r"^\s*(\d)\s*кв\.?\s*(\d{4})\s*$")

PRODUCTION_ASSETS = {  # label start (lower case): (code, Russian name, KMG share or None)
    "ао \"озенмунайгаз\"": ("OMG", "Озенмунайгаз", None), "ао \"эмбамунайгаз\"": ("EMG", "Эмбамунайгаз", None),
    "ао \"каражанбасмунай\"": ("KBM", "Каражанбасмунай (50 %)", None), "тоо \"сп \"казгермунай\"": ("KGM", "Казгермунай (50 %)", None),
    "ао \"петроказахстан инк\"": ("PKI", "ПетроКазахстан Инк (33 %)", None), "тоо \"амангельды газ\"": ("AMANGELDY", "Амангельды Газ (конденсат)", None),
    "ао \"мангистаумунайгаз\"": ("MMG", "Мангистаумунайгаз (50 %)", None), "тоо \"казахойл актобе\"": ("KOA", "Казахойл Актобе (50 %)", None),
    "тоо \"казахтуркмунай\"": ("KTM", "Казахтуркмунай", None), "тоо \"урихтау оперейтинг\"": ("URIKHTAU", "Урихтау Оперейтинг", None),
    "dunga operating": ("DUNGA", "Dunga Operating (60 %)", None), "тоо «урал ойл энд газ»": ("UOG", "Урал Ойл энд Газ (50 %)", None),
    "итого операционные активы": ("OPERATING", "Итого операционные активы", None),
    "тоо \"тенгизшевройл\"": ("TCO", "Тенгизшевройл (доля КМГ 20 %)", 0.20),
    "\"норт каспиан оперейтинг компани": ("NCOC", "Норт Каспиан Оперейтинг Компани, Кашаган (доля КМГ 8,44 % до 15.09.2022, 16,88 % после)", "ncoc"),
    "\"карачаганак петролеум оперейтинг": ("KPO", "Карачаганак Петролеум Оперейтинг (доля КМГ 10 %)", 0.10),
    "итого неоперационные активы": ("NON_OPERATING", "Итого неоперационные активы", None),
    "всего с учетом операционной доли": ("TOTAL", "Всего с учётом операционной доли", None),
}
TRANSPORT = {
    "ао \"казтрансойл\"": ("KTO", "КазТрансОйл"), "тоо \"казахстанско-китайский трубопровод\"": ("KCP", "Казахстанско-Китайский Трубопровод"),
    "ао \"мунайтас\"": ("MUNAITAS", "МунайТас"), "каспийский трубопроводный консорциум": ("CPC", "Каспийский трубопроводный консорциум (на базе доли КМГ)"),
    "ооо \"батумский нефтяной терминал\"": ("BATUMI", "Батумский нефтяной терминал"),
}
SHARES = {"экспорт": ("SHARE_EXPORT", "Экспорт, доля трубопроводной транспортировки"), "транзит": ("SHARE_TRANSIT", "Транзит, доля"),
          "внутренний рынок": ("SHARE_DOMESTIC", "Внутренний рынок (НПЗ РК), доля")}


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"kmg/{ds['id']}: {what}")


def _norm(c) -> str:
    return " ".join(str(c or "").replace("\xa0", " ").split()).lower()


def _value(c) -> float | None:
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return float(c)
    s = str(c or "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def latest_file(html: str) -> tuple[str, int, int]:
    hits = [(int(m.group(3)), int(m.group(2)), m.group(1)) for m in FILE_RE.finditer(html)]
    if not hits:
        raise validation.StructuralChangeError(f"kmg: no «Справочник_Nкв YYYY» xlsx linked on {LISTING}")
    y, q, href = max(hits)
    return (href if href.startswith("http") else "https://www.kmg.kz" + href), y, q


def _quarter_cols(row) -> dict[int, str]:
    cols = {}
    for j, c in enumerate(row):
        m = QUARTER_COL.match(str(c or ""))
        if m:
            cols[j] = f"{m.group(2)}-{(int(m.group(1)) - 1) * 3 + 1:02d}-01"
    return cols


def _blocks(rows, title: str) -> list[tuple[dict[int, str], list]]:
    """Every block headed `title` (a column B cell starting with it, with quarter columns on the
    row), each with its quarter columns and the rows down to the next such heading."""
    starts = [i for i, r in enumerate(rows) if _norm(r[1]).startswith(title) and _quarter_cols(r)]
    out = []
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(rows)
        out.append((_quarter_cols(rows[i]), rows[i + 1:end]))
    return out


def _block(rows, title: str, unit: str | None) -> tuple[dict[int, str], list]:
    """The first block headed `title` whose rows carry `unit` in column C (any block when None)."""
    for cols, body in _blocks(rows, title):
        if unit is None or any(_norm(r[2]).startswith(unit) for r in body):
            return cols, body
    return {}, []


def parse_databook(content: bytes, ds: dict) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    out = []
    # production
    rows = [list(r) + [None] * 3 for r in wb["стр. 6"].iter_rows(values_only=True)]
    cols, body = _block(rows, "добыча нефти", "тыс. тонн")
    if not cols:
        _structural(ds, "no «ДОБЫЧА НЕФТИ» block with quarter columns on sheet «стр. 6»")
    seen = set()
    for r in body:
        label = _norm(r[1])
        hit = next((v for k, v in PRODUCTION_ASSETS.items() if label.startswith(k)), None)
        if hit is None or hit[0] in seen:
            continue
        code, name, share = hit
        seen.add(code)
        for j, d in cols.items():
            v = _value(r[j])
            if v is None:
                continue
            out.append({"date": d, "region": dims.NATIONAL, "item_code": code, "item_name": f"{name}, тыс. тонн (доля КМГ)", "value": v})
            if share == "ncoc":
                if d == "2022-07-01":
                    continue
                share_q = 0.0844 if d < "2022-07-01" else 0.1688
                if v > 0:
                    out.append({"date": d, "region": dims.NATIONAL, "item_code": "NCOC_GROSS", "item_name": "Кашаган, добыча всего (100 %), тыс. тонн", "value": round(v / share_q, 3)})
            elif share and v > 0:
                out.append({"date": d, "region": dims.NATIONAL, "item_code": f"{code}_GROSS", "item_name": f"{name.split(' (')[0]}, добыча всего (100 %), тыс. тонн", "value": round(v / share, 3)})
    missing = {"TCO", "KPO", "TOTAL", "OMG"} - seen
    if missing:
        _structural(ds, f"production rows {sorted(missing)} not found on sheet «стр. 6»")
    # transport
    rows = [list(r) + [None] * 3 for r in wb["стр. 7"].iter_rows(values_only=True)]
    cols, body = _block(rows, "транспортировка нефти по магистральным нефтепроводам", "млн тонн")
    if not cols:
        _structural(ds, "no pipeline transport block on sheet «стр. 7»")
    for r in body:
        label = _norm(r[1])
        hit = next((v for k, v in TRANSPORT.items() if label.startswith(k)), None)
        if hit is None:
            continue
        for j, d in cols.items():
            v = _value(r[j])
            if v is not None:
                out.append({"date": d, "region": dims.NATIONAL, "item_code": f"TRANSPORT_{hit[0]}", "item_name": f"Транспортировка нефти: {hit[1]}, млн тонн", "value": v})
    cols, body = _block(rows, "транспортировка нефти по магистральным нефтепроводам", "%")
    for r in body:
        label = _norm(r[1])
        hit = next((v for k, v in SHARES.items() if label.startswith(k)), None)
        if hit is None or _norm(r[2]) != "%":
            continue
        for j, d in cols.items():
            v = _value(r[j])
            if v is not None:
                out.append({"date": d, "region": dims.NATIONAL, "item_code": hit[0], "item_name": f"{hit[1]}, %", "value": round(v * 100, 4)})
    return out


def fetch(ds: dict) -> tuple[list[dict], dict]:
    from fetchers import imf_dims
    fresh = imf_dims.stored_if_fresh(ds, "kmg", ds["id"])
    if fresh:
        return fresh
    html = requests.get(LISTING, headers=HEADERS, timeout=120)
    html.raise_for_status()
    url, year, quarter = latest_file(html.text)
    resp = requests.get(url, headers=HEADERS, timeout=300)
    resp.raise_for_status()
    today = date.today()
    path = raw_store.save_raw_bytes("kmg", ds["id"], today, "xlsx", resp.content)
    raw_store.write_download_manifest("kmg", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name if path else None, "source_url": url, "release": f"{quarter}Q {year}"})
    records = parse_databook(resp.content, ds)
    if len({r["item_code"] for r in records}) < ds.get("min_items", 15):
        _structural(ds, f"only {len({r['item_code'] for r in records})} items in {url}")
    return records, {"frequency": "quarterly", "source_url": url, "dataset_id": f"KMG databook {quarter}Q {year}", "release": f"{quarter}Q {year}",
                     "note": ds.get("note", "")}
