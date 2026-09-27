"""IMF statistical datasets for Kazakhstan as item-level series (config/dims.yaml, fetcher
imf_sdmx): Balance of Payments (BOP) and International Investment Position (IIP), BPM6,
all standard components; Government Finance Statistics — the statement of operations
(GFS_SOO), expenditure by function (GFS_COFOG), the balance sheet (GFS_BS), all
subsectors, annual; and the quarterly GFS (QGFS). Added 2026-09-27.

Source: the IMF SDMX 3.0 API (api.imf.org/external/sdmx/3.0), the dataflow's latest
version ('+'). A dataset names its dataflow, a series key (dimension values with '*'
wildcards, e.g. KAZ.*.*.USD.Q), the dimensions that make the item code and a divisor:

    flow: IMF.STA/BOP        key: KAZ.*.*.USD.Q
    code_dims: [BOP_ACCOUNTING_ENTRY, INDICATOR]      → item_code "NETCD_T.CAB"
    divisor: 1000000                                   → million USD (the API gives units)
    period: flow | stock                               → how a quarter is dated
    region: world, countries_only: true                → an all-country panel (WEO; groups dropped)
    weo_outturn_only: true                             → drop the vintage's estimates/projections

The item name joins the English names of the code dimensions from the dataflow's own
codelists (the structure query, references=all): «Net (credits less debits) | Current
account balance». Dates: annual 31 December; a quarterly flow the first day of its quarter
(the repository's period-start convention, as NBK's CURRENT_ACCOUNT_BALANCE); a quarterly
stock the last day of its quarter (the as-at date, as FSI_* — NBK's IIP_NET dates the same
position the next day, 1 April for 31 March).

Checked on 2026-09-27: the quarterly current account (NETCD_T.CAB) equals NBK's
CURRENT_ACCOUNT_BALANCE in 94 of 104 common quarters (2023Q1-2025Q2 are NBK revisions the
IMF does not carry yet); the net IIP (NETAL_P.NIIP) equals NBK's IIP_NET on all 22 common
quarters; general-government revenue - expense - net investment in nonfinancial assets
equals net lending (GFS). See tests/test_imf_dims.py.

A download takes minutes (GFS_SOO alone ~1 minute and 12 MB) and the IMF updates these
monthly at most, so a dataset is re-downloaded once a week (REFRESH_DAYS); in between the
stored records are returned.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf  # noqa: E402
from lib import raw_store, validation  # noqa: E402

API = "https://api.imf.org/external/sdmx/3.0"
DATA_URL = API + "/data/dataflow/{agency}/{flow}/+/{key}"
STRUCTURE_URL = API + "/structure/dataflow/{agency}/{flow}/+?references=all&detail=full"
QUARTER_START = {1: "01", 2: "04", 3: "07", 4: "10"}
QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
_STRUCTURES: dict[str, dict[str, dict[str, str]]] = {}


def _structural(ds: dict, what: str, url: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in imf/{ds['id']}", f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: inspect {url} and update config/dims.yaml / scripts/fetchers/imf_dims.py"]))


def _get(url: str, timeout: int = 300) -> bytes:
    import requests
    headers = dict(imf.HEADERS)
    if "/structure/" in url:
        headers["Accept"] = "application/json"
    last = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
            print(f"imf_dims: transport error on {url} (attempt {attempt + 1}/3): {type(exc).__name__}", file=sys.stderr)
    raise last  # type: ignore[misc]


def dimension_names(structure: dict) -> dict[str, dict[str, str]]:
    """{dimension id: {code: English name}} from a structure answer (references=all):
    dimension → concept (conceptIdentity) → the concept's codelist → its codes."""
    data = structure["data"]
    concepts = {}
    for cs in data.get("conceptSchemes", []):
        for c in cs.get("concepts", []):
            concepts[(cs["agencyID"], cs["id"], c["id"])] = (c.get("coreRepresentation") or {}).get("enumeration")
    codelists = {}
    for cl in data.get("codelists", []):
        codelists[(cl["agencyID"], cl["id"])] = {c["id"]: (c.get("name") or (c.get("names") or {}).get("en") or c["id"])
                                                for c in cl.get("codes", [])}
    out = {}
    for dsd in data.get("dataStructures", []):
        comps = dsd["dataStructureComponents"]
        for dim in comps["dimensionList"]["dimensions"]:
            enum = (dim.get("localRepresentation") or {}).get("enumeration")
            if not enum:
                m = re.search(r"Concept=([^:]+):([^(]+)\([^)]*\)\.(\w+)$", dim.get("conceptIdentity", ""))
                enum = concepts.get(m.groups()) if m else None
            m = re.search(r"Codelist=([^:]+):([^(]+)\(", enum or "")
            if m:
                out[dim["id"]] = codelists.get(m.groups(), {})
    return out


def _names(ds: dict) -> dict[str, dict[str, str]]:
    agency, flow = ds["flow"].split("/")
    if flow not in _STRUCTURES:
        import json
        url = STRUCTURE_URL.format(agency=agency, flow=flow)
        _STRUCTURES[flow] = dimension_names(json.loads(_get(url)))
    return _STRUCTURES[flow]


def period_date(period: str, frequency: str, kind: str) -> str | None:
    """'2025' → 2025-12-31; '2025-Q3' → 2025-07-01 (flow) or 2025-09-30 (stock); other forms None."""
    period = period.strip()
    if frequency == "annual":
        return f"{period}-12-31" if re.fullmatch(r"\d{4}", period) else None
    m = re.fullmatch(r"(\d{4})-Q([1-4])", period)
    if not m:
        return None
    y, q = m.group(1), int(m.group(2))
    return f"{y}-{QUARTER_START[q]}-01" if kind == "flow" else f"{y}-{QUARTER_END[q]}"


def parse(content: bytes, ds: dict, names: dict[str, dict[str, str]]) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    code_dims = ds["code_dims"]
    divisor = float(ds.get("divisor", 1))
    wanted_freq = {"annual": "A", "quarterly": "Q"}[ds["frequency"]]
    records, seen = [], {}
    for r in rows:
        raw = (r.get("OBS_VALUE") or "").strip()
        if not raw or r.get("FREQUENCY", wanted_freq) != wanted_freq:
            continue
        if any(r.get(k) != v for k, v in (ds.get("filter") or {}).items()):
            continue
        d = period_date(r.get("TIME_PERIOD", ""), ds["frequency"], ds.get("period", "flow"))
        if d is None or d[:4] < str(ds.get("from_year", 0)):
            continue
        try:
            value = float(raw) / divisor
        except ValueError:
            continue
        if ds.get("countries_only") and not re.fullmatch(r"[A-Z]{3}", r.get("COUNTRY", "")):
            continue                      # WEO country groups (G001, GX123 …) are not economies
        if ds.get("weo_outturn_only"):
            vintage = imf.weo_vintage_year(r)
            if vintage is not None and int(d[:4]) >= vintage:
                continue                  # estimates/projections of the WEO vintage are not kept
        code = ".".join(r[k] for k in code_dims)
        name = " | ".join(names.get(k, {}).get(r[k], r[k]) for k in code_dims)
        if (d, code) in seen:
            raise ValueError(f"{ds['id']}: two observations for {code} on {d} — code_dims do not identify a series")
        seen[(d, code)] = True
        records.append({"date": d, "region": ds.get("region", "national"), "item_code": code, "item_name": name,
                        "value": round(value, 6)})
    return records


REFRESH_DAYS = 7   # these datasets change monthly at most; the full set takes ~6 minutes to download


def last_download(agency: str, name: str) -> date | None:
    """Date of the latest download manifest for (agency, name) — written on every download,
    also when the bytes were unchanged and no new raw file was archived."""
    folder = raw_store.RAW_ROOT / agency
    dates = []
    for p in folder.glob(f"{agency}_{name.lower()}_*.manifest.json") if folder.exists() else []:
        m = re.search(r"_(\d{4}-\d{2}-\d{2})(?:_\d+)?\.manifest\.json$", p.name)
        if m:
            dates.append(date.fromisoformat(m.group(1)))
    return max(dates) if dates else None


def stored_if_fresh(ds: dict, agency: str, name: str) -> tuple[list[dict], dict] | None:
    """The stored records when the last download is younger than `refresh_days` (default
    REFRESH_DAYS), so the daily run does not re-download a slow, monthly-changing source;
    None when a download is due. `refresh_days: 0` always downloads."""
    from lib import dims
    days = ds.get("refresh_days", REFRESH_DAYS)
    last = last_download(agency, name)
    stored = dims.load_processed(ds["id"])
    if not days or last is None or not stored or (date.today() - last).days >= days:
        return None
    records = [{"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
                "value": float(r["value"])} for r in stored]
    return records, {"frequency": ds["frequency"], "note": ds.get("note", ""),
                     "warnings": [f"not re-downloaded: last download {last.isoformat()}, refreshed every {days} days"]}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    fresh = stored_if_fresh(ds, "imf", ds["id"])
    if fresh:
        return fresh
    agency, flow = ds["flow"].split("/")
    url = DATA_URL.format(agency=agency, flow=flow, key=ds["key"])
    content = _get(url)
    today = date.today()
    # gzip with a fixed mtime: identical content gives identical bytes, so an unchanged
    # download is not archived twice (lib/raw_store dedups by content)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(content)
    path = raw_store.save_raw_bytes("imf", ds["id"], today, "csv.gz", buf.getvalue())
    raw_store.write_download_manifest("imf", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": url})
    records = parse(content, ds, _names(ds))
    n_items = len({r["item_code"] for r in records})
    if n_items < ds.get("min_items", 1):
        _structural(ds, f"{n_items} series, expected at least {ds.get('min_items')}", url)
    for code in ds.get("required_items", []):
        if not any(r["item_code"] == code for r in records):
            _structural(ds, f"series {code} missing", url)
    return records, {"frequency": ds["frequency"], "source_url": url, "dataset_id": f"{ds['flow']}/{ds['key']}",
                     "note": ds.get("note", "")}
