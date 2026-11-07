"""Taldau (taldau.stat.gov.kz) probe and download for natural-resource series: production of oil,
gas, coal, ores and metals, exports in physical units, reserves -- national, annual, longest history.

Method as documented in docs/UPDATE_LOG_ARCHIVE.md (2026-09-01, "the Taldau browser dependency is
GONE") and used by fetchers/bns.py / taldau_dims.py:
  1. POST /ru/Search/getSearchPageGridData  keyword + page/start/limit  -> candidate indexes
  2. GET  /ru/NewIndex/GetIndex/<id>?keyword=                           -> options.measure.id
  3. POST /ru/NewIndex/GetSegmentList node/indexId/periodId/keyword    -> dicIds + termIds (seg[0])
  4. POST /ru/NewIndex/GetIndexTreeData                                 -> root node 'yMMYYYY' values;
     when a non-region dimension is a product list, its children are opened one level (idx = its
     position) so every product of the index comes out.
Everything lands in data/raw/taldau_resources/ (raw JSON per index + tidy CSV) and the log in
reports/taldau_resources.json.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "taldau_resources"
REPORT = ROOT / "reports" / "taldau_resources.json"
BASE = "https://taldau.stat.gov.kz/ru"
H = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)",
     "X-Requested-With": "XMLHttpRequest"}
NATIONAL = "741880"
KEYWORDS = ["нефть", "газовый конденсат", "газ природный", "уголь", "лигнит", "руды", "руда железная", "медь",
            "цинк", "свинец", "ферросплав", "глинозем", "алюминий", "уран", "золото", "серебро", "хром",
            "марганец", "в натуральном выражении", "добыча", "горнодобывающ", "запасы", "экспорт нефти",
            "нефтепродукт", "производство продукции"]
NAME_OK = re.compile(r"нефт|газ|угл|уголь|лигнит|руд|мед|цинк|свин|ферросплав|глинозем|алюмин|уран|золот|серебр|хром|"
                     r"марган|добыч|натуральн|горнодобыв|запас|минерал", re.I)
LOG: dict = {"started_utc": datetime.now(timezone.utc).isoformat(), "search": {}, "indexes": {}}


def post(path, data, timeout=60):
    for a in range(3):
        try:
            r = requests.post(BASE + path, data=data, headers=H, timeout=timeout)
            if r.status_code == 200:
                return r
            LOG.setdefault("errors", []).append({"path": path, "status": r.status_code, "data": str(data)[:200]})
            if r.status_code in (400, 404, 500):
                return None
        except requests.RequestException as e:
            LOG.setdefault("errors", []).append({"path": path, "error": str(e)[:200]})
        time.sleep(2 * (a + 1))
    return None


def get(path, timeout=60):
    try:
        r = requests.get(BASE + path, headers=H, timeout=timeout)
        return r if r.status_code == 200 else None
    except requests.RequestException:
        return None


def search(keyword):
    r = post("/Search/getSearchPageGridData", {"keyword": keyword, "page": "1", "start": "0", "limit": "100"})
    if r is None:
        return []
    try:
        j = r.json()
    except ValueError:
        return []
    items = j.get("data") or j.get("items") or j.get("rows") or (j if isinstance(j, list) else [])
    return items


def tree(index_id, period, measure, terms, dics, parent="", idx="0", term=NATIONAL):
    body = {"p_parent_id": parent, "p_index_id": index_id, "p_keyword": "", "p_period_id": period,
            "p_measure_id": measure, "p_term_id": term, "p_terms": terms, "p_dicIds": dics, "idx": idx,
            "filter": '[{"property":null,"value":null}]', "id": ""}
    r = post("/NewIndex/GetIndexTreeData", body)
    if r is None:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def values(node):
    out = {}
    for k, v in node.items():
        if isinstance(k, str) and len(k) == 7 and k[0] == "y" and k[1:].isdigit() and v not in (None, ""):
            try:
                out[int(k[3:])] = float(str(v).replace(",", ".").replace(" ", ""))
            except ValueError:
                pass
    return out


def probe(index_id, name):
    rec = {"name": name}
    page = get(f"/NewIndex/GetIndex/{index_id}?keyword=")
    measure = None
    if page is not None:
        m = re.search(r"measure\s*:\s*\{[^}]*?id\s*:\s*['\"]?(\d+)", page.text) or \
            re.search(r"\"measure\"\s*:\s*\{[^}]*?\"id\"\s*:\s*\"?(\d+)", page.text)
        measure = m.group(1) if m else None
        u = re.search(r"measure\s*:\s*\{[^}]*?name\s*:\s*['\"]([^'\"]+)", page.text)
        rec["unit"] = u.group(1) if u else None
    rec["measure"] = measure
    periods = post("/NewIndex/GetPeriodList", {"indexId": index_id, "node": index_id, "keyword": ""})
    try:
        rec["periods"] = periods.json() if periods is not None else None
    except ValueError:
        rec["periods"] = None
    period = "7"
    if isinstance(rec["periods"], list) and rec["periods"]:
        ids = [str(p.get("id") or p.get("periodId") or "") for p in rec["periods"]]
        period = "7" if "7" in ids else ids[0]
    rec["period"] = period
    seg = post("/NewIndex/GetSegmentList", {"node": index_id, "indexId": index_id, "periodId": period, "keyword": ""})
    try:
        segs = seg.json() if seg is not None else []
    except ValueError:
        segs = []
    rec["segments"] = segs[:12] if isinstance(segs, list) else segs
    if not measure or not segs:
        rec["status"] = "no measure or segments"
        return rec, []
    s0 = segs[0]
    dics = str(s0.get("dicId", "")).replace("+", ",")
    terms = str(s0.get("termIds", ""))
    rec.update({"dicIds": dics, "terms": terms, "termNames": s0.get("termNames"), "dicNames": s0.get("dicNames") or s0.get("name")})
    root = tree(index_id, period, measure, terms, dics)
    rows = []
    if not root:
        rec["status"] = "tree empty"
        return rec, rows
    (OUT / f"{index_id}_root.json").write_text(json.dumps(root, ensure_ascii=False), encoding="utf-8")
    nat = next((n for n in root if str(n.get("id")) == NATIONAL), root[0])
    v = values(nat)
    rec["root_years"] = [min(v), max(v)] if v else None
    for y, x in v.items():
        rows.append([index_id, name, rec.get("unit"), "Всего", y, x])
    # open every non-region dimension one level (products, types ...)
    dl = dics.split(",")
    tl = terms.split(",")
    rec["children"] = {}
    for pos in range(1, len(dl)):
        kids = tree(index_id, period, measure, terms, dics, parent=tl[pos], idx=str(pos), term=tl[pos])
        if not kids:
            continue
        (OUT / f"{index_id}_dim{pos}.json").write_text(json.dumps(kids, ensure_ascii=False), encoding="utf-8")
        rec["children"][pos] = len(kids)
        for k in kids:
            kv = values(k)
            for y, x in kv.items():
                rows.append([index_id, name, rec.get("unit"), k.get("text") or k.get("name") or k.get("id"), y, x])
    rec["status"] = "ok"
    return rec, rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cands = {}
    for kw in KEYWORDS:
        items = search(kw)
        LOG["search"][kw] = len(items)
        for it in items:
            iid = str(it.get("id") or it.get("indexId") or it.get("Id") or "")
            nm = it.get("name") or it.get("text") or it.get("indexName") or ""
            if iid and NAME_OK.search(nm):
                cands[iid] = nm
        time.sleep(0.5)
    LOG["candidates"] = cands
    (OUT / "search_candidates.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    allrows = []
    for iid, nm in list(cands.items())[:120]:
        try:
            rec, rows = probe(iid, nm)
        except Exception as e:  # noqa: BLE001
            rec, rows = {"name": nm, "status": f"error {e!r}"[:300]}, []
        LOG["indexes"][iid] = rec
        allrows += rows
        time.sleep(0.3)
    with (OUT / "taldau_resources_long.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["index_id", "index_name", "unit", "item", "year", "value"])
        w.writerows(allrows)
    LOG["rows"] = len(allrows)
    LOG["finished_utc"] = datetime.now(timezone.utc).isoformat()
    REPORT.write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in LOG.items() if k != "indexes"}, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    sys.exit(main())
