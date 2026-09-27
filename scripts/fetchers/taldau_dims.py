"""Item-level series from Taldau (taldau.stat.gov.kz), BNS's indicator database: one
dimension of an index expanded into its children (ОКЭД sections, asset types …), national.

Added 2026-09-25 for the production function (capital by section and by asset type,
employment by section back to 2001). Mechanism as in fetchers/bns.py
`_fetch_taldau_annual_index`, with the tree opened one level: POST GetIndexTreeData with
`p_parent_id` = `p_term_id` = the root term of the dimension to expand and `idx` = that
dimension's position in `p_dicIds`; the answer is the list of child nodes, each carrying
the usual 'yMMYYYY' value keys. The total comes from the same call without a parent. The
children are checked to add up to the total in the latest year before anything is kept.

Dataset keys (config/dims.yaml, fetcher: taldau): index_id, period_id, measure_id, dic_ids,
terms, expand_pos (the dimension's position), expand_term (its root term), dictionary
(okved_sections, or from_table: the Taldau term id is the code), term_codes ({term id: code},
in place of a dictionary; an unlisted child stops the dataset), scale (divide by), sum_check
(false for ratios). Monthly values are dated the first day of the month.
"""
from __future__ import annotations

import calendar
import gzip
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, raw_store, validation  # noqa: E402

TREE_URL = "https://taldau.stat.gov.kz/ru/NewIndex/GetIndexTreeData"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)",
           "X-Requested-With": "XMLHttpRequest"}
NATIONAL_TERM = "741880"


def _tree(ds: dict, parent: str = "", pos: str = "0", term: str = NATIONAL_TERM) -> list[dict]:
    body = {"p_parent_id": parent, "p_index_id": ds["index_id"], "p_keyword": "", "p_period_id": ds.get("period_id", "7"),
            "p_measure_id": ds["measure_id"], "p_term_id": term, "p_terms": ds["terms"], "p_dicIds": ds["dic_ids"],
            "idx": pos, "filter": '[{"property":null,"value":null}]', "id": ""}
    resp = requests.post(TREE_URL, data=body, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    today = date.today()
    name = f"{ds['id']}_{'children' if parent else 'total'}"
    path = raw_store.save_raw_bytes("bns", name, today, "json", resp.content)
    raw_store.write_download_manifest("bns", name, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": TREE_URL, "request_body": body})
    return json.loads(resp.content)


def node_values(node: dict, frequency: str) -> dict[str, float]:
    """{date: value} from a node's 'yMMYYYY' keys; annual and quarterly dated at period end
    here, as fetchers/bns.py does (update_dims does not restate dates; annual stays YYYY-12-31)."""
    out = {}
    for k, v in node.items():
        if not (isinstance(k, str) and len(k) == 7 and k[0] == "y" and k[1:].isdigit()) or v in (None, ""):
            continue
        month, year = int(k[1:3]), int(k[3:])
        try:
            value = float(v)
        except (TypeError, ValueError):
            continue
        if frequency == "quarterly":
            out[f"{year:04d}-{month - 2:02d}-01"] = value      # the quarter's first day, the dims convention
        elif frequency == "monthly":
            out[f"{year:04d}-{month:02d}-01"] = value          # the month's first day, as the CPI detail
        else:
            out[f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"] = value
    return out


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in bns/{ds['id']}", f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: inspect {TREE_URL} (index {ds['index_id']}) and update config/dims.yaml / scripts/fetchers/taldau_dims.py"]))


def fetch(ds: dict) -> tuple[list[dict], dict]:
    freq = ds["frequency"]
    scale = float(ds.get("scale", 1))
    total_nodes = [n for n in _tree(ds) if n.get("id") == NATIONAL_TERM]
    if not total_nodes:
        _structural(ds, "no national root node")
    total = node_values(total_nodes[0], freq)
    children = _tree(ds, parent=ds["expand_term"], pos=str(ds["expand_pos"]), term=ds["expand_term"])
    dictionary = None if ds.get("dictionary", "from_table") == "from_table" else dims.load_dictionary(ds["dictionary"])
    records = []
    for node in children:
        values = node_values(node, freq)
        if not values:
            continue
        label = " ".join(str(node.get("text", "")).split())
        if ds.get("term_codes"):
            code = ds["term_codes"].get(int(node["id"]))
            if code is None:
                _structural(ds, f"child {node['id']} {label!r} is not in the dataset's term_codes")
            name = label
        elif dictionary is None:
            code, name = str(node["id"]), label
        else:
            hit = dims.match_item(label, dictionary)
            if hit is None:
                _structural(ds, f"child {label!r} matches no entry of dictionaries/{ds['dictionary']}.csv")
            code, name = hit[0], label
        records += [{"date": d, "region": dims.NATIONAL, "item_code": code, "item_name": name, "value": round(v / scale, 6)}
                    for d, v in values.items()]
    if len({r["item_code"] for r in records}) < ds.get("min_items", 3):
        _structural(ds, f"only {len({r['item_code'] for r in records})} children with data")
    if ds.get("sum_check", True):
        latest = max(total)
        parts = sum(r["value"] for r in records if r["date"] == latest) * scale
        if abs(parts - total[latest]) > 1e-4 * abs(total[latest]):
            _structural(ds, f"children sum to {parts:.0f} in {latest}, the total is {total[latest]:.0f}")
    records += [{"date": d, "region": dims.NATIONAL, "item_code": "TOTAL", "item_name": "Всего", "value": round(v / scale, 6)}
                for d, v in total.items()]
    records.sort(key=lambda r: (r["item_code"], r["date"]))
    return records, {"frequency": freq, "source_url": TREE_URL, "dataset_id": f"taldau-index-{ds['index_id']}",
                     "note": ds.get("note", "")}


# ---------------------------------------------------------------- regional × item, monthly (fetcher: taldau_regional)
#
# Added 2026-09-27 for industry by region: an index with a region dimension and an item
# dimension (ОКЭД activity, industrial product, shipment direction …). For each configured
# item two calls: the national node, then the region dimension opened one level (the oblasts
# and the three cities). Items are listed in config/dims.yaml (`items`: Taldau term id and
# code), so the dataset does not drift when BNS adds terms. Other dimensions stay at the
# segment's defaults (`terms`); `fixed` pins extra positions per item group (e.g. the
# shipment direction). Monthly values are dated the first day of the month (the dims
# convention for flows); the raw answers of a run are archived as one gzipped JSON file.

def _post(ds: dict, terms: str, parent: str = "", pos: str = "0", term: str = NATIONAL_TERM) -> list[dict]:
    body = {"p_parent_id": parent, "p_index_id": ds["index_id"], "p_keyword": "", "p_period_id": ds.get("period_id", "4"),
            "p_measure_id": ds.get("measure_id", "0"), "p_term_id": term, "p_terms": terms, "p_dicIds": ds["dic_ids"],
            "idx": pos, "filter": '[{"property":null,"value":null}]', "id": ""}
    last = None
    for attempt in range(3):
        try:
            resp = requests.post(TREE_URL, data=body, headers=HEADERS, timeout=120)
            resp.raise_for_status()
            return json.loads(resp.content)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, ValueError) as exc:
            last = exc
    raise last  # type: ignore[misc]


def monthly_values(node: dict) -> dict[str, float]:
    """{YYYY-MM-01: value} from a node's 'yMMYYYY' keys (period 4 = month)."""
    return {d[:8] + "01": v for d, v in node_values(node, "monthly").items()}


def fetch_regional(ds: dict) -> tuple[list[dict], dict]:
    """`refresh_days` (default 0): the stored records are returned while the last download is
    younger -- a product dataset takes a few hundred calls and Taldau updates monthly."""
    if ds.get("refresh_days"):
        from fetchers import imf_dims
        fresh = imf_dims.stored_if_fresh(ds, "bns", ds["id"])
        if fresh:
            return fresh
    today = date.today()
    scale = float(ds.get("scale", 1))
    base = ds["terms"].split(",")
    rp, ip = int(ds.get("region_pos", 0)), int(ds["item_pos"])
    variants = ds.get("variants") or [{"suffix": "", "fixed": {}}]
    records, raw, unknown, missing = [], [], set(), []
    for item in ds["items"]:
        for var in variants:
            terms = list(base)
            terms[ip], terms[rp] = str(item["term"]), NATIONAL_TERM
            for p, t in (var.get("fixed") or {}).items():
                terms[int(p)] = str(t)
            tstr = ",".join(terms)
            code = f"{item['code']}{var['suffix']}"
            top = [n for n in _post(ds, tstr) if str(n.get("id")) == NATIONAL_TERM]
            regions = _post(ds, tstr, parent=NATIONAL_TERM, pos=str(rp), term=NATIONAL_TERM) if top and str(top[0].get("leaf")).lower() != "true" else []
            raw.append({"code": code, "terms": tstr, "national": top, "regions": regions})
            if not top:
                missing.append(code)
                continue
            name = " ".join(str(item["name"]).split())      # the node's own text is the region's
            unit = top[0].get("measureName")
            name = f"{name}{var.get('name', '')}" + (f", {unit.lower()}" if unit and ds.get("unit_in_name") else "")
            for d, v in monthly_values(top[0]).items():
                records.append({"date": d, "region": dims.NATIONAL, "item_code": code, "item_name": name, "value": round(v / scale, 6)})
            for node in regions:
                hit = dims.match_region(node.get("text", ""))
                if hit is None:
                    unknown.add(node.get("text"))
                    continue
                for d, v in monthly_values(node).items():
                    records.append({"date": d, "region": hit[0], "item_code": code, "item_name": name, "value": round(v / scale, 6)})
    if unknown:
        _structural(ds, f"region nodes matching no entry of dictionaries/regions.csv: {sorted(unknown)}")
    if len(missing) > len(ds["items"]) * len(variants) * 0.2:
        _structural(ds, f"no national node for {missing}")
    # gzip with a fixed mtime: an unchanged answer gives identical bytes (raw_store dedups them)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(raw, ensure_ascii=False).encode())
    path = raw_store.save_raw_bytes("bns", ds["id"], today, "json.gz", buf.getvalue())
    raw_store.write_download_manifest("bns", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": TREE_URL, "index_id": ds["index_id"]})
    warnings = [f"no national node (term not in this index any more?): {missing}"] if missing else []
    return records, {"frequency": ds["frequency"], "source_url": TREE_URL, "dataset_id": f"taldau-index-{ds['index_id']}",
                     "note": ds.get("note", ""), "warnings": warnings}
