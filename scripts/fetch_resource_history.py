"""Long historical series on Kazakhstan's natural resources, for the longest period each source holds.
Run by .github/workflows/natural-capital.yml (on demand). Everything Kazakhstan-specific is cut out
of the big international files and written as tidy CSV under data/raw/resource_history/:

  ei_kazakhstan.csv        Energy Institute Statistical Review of World Energy (panel CSV):
                           oil, gas, coal production / consumption / reserves, from 1965 (KZ data from 1985).
  eia_kazakhstan.csv       U.S. EIA international bulk file (INTL.zip): production, consumption,
                           imports, exports, proved reserves of oil, gas, coal; 1980-.
  wb_kazakhstan.csv        World Bank WDI API: resource rents, depletion, fuel/ore exports, water,
                           land and forest; 1960/1990-.
  comtrade_kazakhstan.csv  UN Comtrade (public preview API): exports and imports, value and net
                           weight, for HS headings of fuels, ores and metals; 1995-.
  comtrade_mirror_kazakhstan.csv
                           UN Comtrade mirror flows: imports FROM Kazakhstan (partner 398) reported by
                           every partner country, same HS headings; 1995-. Fills years in which
                           Kazakhstan's own export records are confidential (metals 2020-2022) and
                           cross-checks the national records.
  usgs_myb/                USGS Minerals Yearbook, Kazakhstan country chapter tables (xls/xlsx),
                           every year found (each table carries five years).
  bgs/                     BGS World Mineral Statistics, if its export endpoint answers.

reports/resource_history_fetch.json logs every request, so a partial run is diagnosable from git.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "resource_history"
REPORT = ROOT / "reports" / "resource_history_fetch.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 KZEconDataPipeline/1.0",
           "Accept-Language": "en,ru;q=0.8"}
LOG: dict = {"started_utc": datetime.now(timezone.utc).isoformat()}


def get(url: str, timeout: int = 180, **kw) -> requests.Response | None:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            LOG.setdefault("http_errors", []).append({"url": url[:300], "status": r.status_code})
            if r.status_code in (400, 403, 404):
                return None
            if r.status_code == 429:
                time.sleep(20)
        except requests.RequestException as exc:
            LOG.setdefault("http_errors", []).append({"url": url[:300], "error": str(exc)[:200]})
        time.sleep(3 * (attempt + 1))
    return None


def write_csv(name: str, header: list[str], rows: list) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


# ------------------------------------------------------------------ Energy Institute
EI_PAGES = ["https://www.energyinst.org/statistical-review/resources-and-data-downloads",
            "https://www.energyinst.org/statistical-review"]


def energy_institute() -> None:
    log = LOG.setdefault("ei", {})
    links = []
    for page in EI_PAGES:
        r = get(page)
        log.setdefault("pages", []).append({"url": page, "ok": r is not None})
        if r is None:
            continue
        for href in re.findall(r'href="([^"]+\.(?:csv|xlsx)[^"]*)"', r.text, re.I):
            u = urljoin(page, href)
            if u not in links:
                links.append(u)
    log["links"] = links[:60]
    panel = [u for u in links if "panel" in u.lower() and u.lower().endswith(".csv")] or \
            [u for u in links if u.lower().endswith(".csv")]
    rows, header = [], None
    for u in panel:
        r = get(u, timeout=300)
        if r is None:
            continue
        text = r.content.decode("utf-8-sig", "replace")
        rd = csv.reader(io.StringIO(text))
        header = next(rd)
        ci = next((i for i, h in enumerate(header) if h.strip().lower() == "country"), None)
        if ci is None:
            continue
        rows = [row for row in rd if len(row) > ci and row[ci].strip().lower() == "kazakhstan"]
        log["panel_url"] = u
        break
    if rows:
        # keep only columns that are not empty for Kazakhstan
        keep = [i for i in range(len(header)) if any(i < len(r) and r[i].strip() for r in rows)]
        log["rows"] = write_csv("ei_kazakhstan.csv", [header[i] for i in keep], [[r[i] if i < len(r) else "" for i in keep] for r in rows])
        log["columns"] = [header[i] for i in keep]
    # consolidated xlsx (has reserves history sheets in some editions) -> keep the file for parsing
    xl = [u for u in links if u.lower().endswith(".xlsx") and ("all" in u.lower() or "consolidated" in u.lower() or "data" in u.lower())]
    for u in xl[:2]:
        r = get(u, timeout=300)
        if r is not None and r.content[:2] == b"PK":
            (OUT / "ei_statistical_review_all_data.xlsx").write_bytes(r.content)
            log["xlsx_url"] = u
            log["xlsx_bytes"] = len(r.content)
            break


def owid_energy() -> None:
    """Our World in Data energy dataset (GitHub): Energy Institute series in TWh, 1985- for Kazakhstan.
    Used because energyinst.org refuses automated downloads (403)."""
    log = LOG.setdefault("owid", {})
    r = get("https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv", timeout=300)
    if r is None:
        return
    rd = csv.reader(io.StringIO(r.content.decode("utf-8-sig", "replace")))
    header = next(rd)
    rows = [row for row in rd if row and row[0] == "Kazakhstan"]
    keep = [i for i in range(len(header)) if any(i < len(x) and x[i].strip() for x in rows)]
    log["rows"] = write_csv("owid_energy_kazakhstan.csv", [header[i] for i in keep], [[x[i] for i in keep] for x in rows])


# ------------------------------------------------------------------ EIA bulk
def eia() -> None:
    log = LOG.setdefault("eia", {})
    r = get("https://api.eia.gov/bulk/INTL.zip", timeout=600)
    if r is None:
        log["error"] = "INTL.zip not downloaded"
        return
    log["zip_bytes"] = len(r.content)
    rows = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            with z.open(name) as fh:
                for line in io.TextIOWrapper(fh, encoding="utf-8", errors="replace"):
                    if "KAZ" not in line and "Kazakhstan" not in line:
                        continue
                    try:
                        s = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "data" not in s or "Kazakhstan" not in s.get("name", ""):
                        continue
                    if s.get("f") not in ("A", None):
                        continue
                    for period, value in s["data"]:
                        if value in (None, "", "NA", "--", "(s)", "W"):
                            continue
                        rows.append([s.get("series_id"), s.get("name"), s.get("units"), period, value])
    log["rows"] = write_csv("eia_kazakhstan.csv", ["series_id", "name", "units", "year", "value"], rows)
    log["series"] = len({r[0] for r in rows})


# ------------------------------------------------------------------ World Bank
WB_INDICATORS = {
    "NY.GDP.TOTL.RT.ZS": "Total natural resources rents (% of GDP)",
    "NY.GDP.PETR.RT.ZS": "Oil rents (% of GDP)",
    "NY.GDP.NGAS.RT.ZS": "Natural gas rents (% of GDP)",
    "NY.GDP.COAL.RT.ZS": "Coal rents (% of GDP)",
    "NY.GDP.MINR.RT.ZS": "Mineral rents (% of GDP)",
    "NY.GDP.FRST.RT.ZS": "Forest rents (% of GDP)",
    "NY.ADJ.DRES.GN.ZS": "Adjusted savings: natural resources depletion (% of GNI)",
    "NY.ADJ.DNGY.GN.ZS": "Adjusted savings: energy depletion (% of GNI)",
    "NY.ADJ.DMIN.GN.ZS": "Adjusted savings: mineral depletion (% of GNI)",
    "TX.VAL.FUEL.ZS.UN": "Fuel exports (% of merchandise exports)",
    "TX.VAL.MMTL.ZS.UN": "Ores and metals exports (% of merchandise exports)",
    "TM.VAL.FUEL.ZS.UN": "Fuel imports (% of merchandise imports)",
    "EG.IMP.CONS.ZS": "Energy imports, net (% of energy use)",
    "EG.USE.PCAP.KG.OE": "Energy use (kg of oil equivalent per capita)",
    "ER.H2O.INTR.K3": "Renewable internal freshwater resources (billion m3)",
    "ER.H2O.FWTL.K3": "Annual freshwater withdrawals, total (billion m3)",
    "ER.H2O.FWST.ZS": "Level of water stress (% of available freshwater)",
    "ER.H2O.FWAG.ZS": "Freshwater withdrawals for agriculture (% of total)",
    "AG.LND.ARBL.HA": "Arable land (hectares)",
    "AG.LND.FRST.K2": "Forest area (sq. km)",
    "AG.LND.AGRI.K2": "Agricultural land (sq. km)",
}


def world_bank() -> None:
    log = LOG.setdefault("wb", {})
    rows = []
    for code, name in WB_INDICATORS.items():
        r = get(f"https://api.worldbank.org/v2/country/KAZ/indicator/{code}?format=json&per_page=200&date=1960:2026")
        if r is None:
            continue
        try:
            data = r.json()[1] or []
        except (ValueError, IndexError, TypeError):
            continue
        for d in data:
            if d.get("value") is not None:
                rows.append([code, name, d["date"], d["value"]])
    log["rows"] = write_csv("wb_kazakhstan.csv", ["indicator", "name", "year", "value"], rows)


# ------------------------------------------------------------------ Comtrade
HS = {"2601": "Железные руды и концентраты", "2602": "Марганцевые руды", "2603": "Медные руды и концентраты",
      "2606": "Алюминиевые руды (бокситы)", "2607": "Свинцовые руды", "2608": "Цинковые руды", "2610": "Хромовые руды",
      "2611": "Вольфрамовые руды", "2612": "Урановые и ториевые руды", "2613": "Молибденовые руды",
      "2616": "Руды драгоценных металлов", "2701": "Уголь каменный", "2702": "Лигнит", "2709": "Нефть сырая",
      "2710": "Нефтепродукты", "2711": "Газ нефтяной и природный", "2818": "Оксид алюминия (глинозём)",
      "2844": "Радиоактивные элементы (уран)", "7108": "Золото", "7106": "Серебро", "7202": "Ферросплавы",
      "7401": "Медный штейн", "7403": "Медь рафинированная", "7601": "Алюминий необработанный",
      "7801": "Свинец необработанный", "7901": "Цинк необработанный", "8101": "Вольфрам", "8108": "Титан"}


def comtrade() -> None:
    log = LOG.setdefault("comtrade", {})
    rows = []
    codes = ",".join(HS)
    years_ok = []
    for year in range(1995, 2026):
        url = ("https://comtradeapi.un.org/public/v1/preview/C/A/HS"
               f"?reporterCode=398&period={year}&cmdCode={codes}&flowCode=X,M&partnerCode=0&partner2Code=0"
               "&customsCode=C00&motCode=0&includeDesc=true")
        r = get(url, timeout=120)
        time.sleep(1.5)
        if r is None:
            continue
        try:
            data = r.json().get("data") or []
        except ValueError:
            continue
        if data:
            years_ok.append(year)
        for d in data:
            rows.append([year, d.get("flowCode"), d.get("cmdCode"), HS.get(str(d.get("cmdCode")), d.get("cmdDesc")),
                         d.get("primaryValue"), d.get("netWgt"), d.get("qty"), d.get("qtyUnitAbbr"), d.get("classificationCode")])
    log["years"] = years_ok
    log["rows"] = write_csv("comtrade_kazakhstan.csv",
                            ["year", "flow", "hs", "name", "value_usd", "net_weight_kg", "qty", "qty_unit", "classification"], rows)


def comtrade_mirror() -> None:
    """Partner-reported imports from Kazakhstan. The preview API caps a call at 500 records,
    so headings go in batches of seven (about 40 partners each). Years from 2010: the span that
    overlaps Taldau and covers the confidential years; a time budget keeps the job under 25 minutes."""
    log = LOG.setdefault("comtrade_mirror", {})
    rows, truncated, years_ok, skipped = [], [], set(), []
    codes = list(HS)
    batches = [codes[i:i + 7] for i in range(0, len(codes), 7)]
    t0 = time.time()
    for year in range(2025, 2009, -1):
        for b in batches:
            if time.time() - t0 > 25 * 60:
                skipped.append(year)
                break
            url = ("https://comtradeapi.un.org/public/v1/preview/C/A/HS"
                   f"?period={year}&partnerCode=398&cmdCode={','.join(b)}&flowCode=M&partner2Code=0"
                   "&customsCode=C00&motCode=0&includeDesc=true")
            r = get(url, timeout=120)
            time.sleep(1.2)
            if r is None:
                continue
            try:
                data = r.json().get("data") or []
            except ValueError:
                continue
            print(f"mirror {year} {b[0]}..: {len(data)} rows ({time.time() - t0:.0f}s)", flush=True)
            if len(data) >= 500:
                truncated.append(f"{year}:{','.join(b)}")
            for d in data:
                years_ok.add(year)
                rows.append([year, d.get("reporterCode"), d.get("reporterISO") or d.get("reporterDesc"), "M",
                             d.get("cmdCode"), HS.get(str(d.get("cmdCode")), d.get("cmdDesc")),
                             d.get("primaryValue"), d.get("netWgt"), d.get("qty"), d.get("qtyUnitAbbr")])
    log["years"] = sorted(years_ok)
    log["truncated_calls"] = truncated
    log["skipped_years_time_budget"] = sorted(set(skipped))
    log["rows"] = write_csv("comtrade_mirror_kazakhstan.csv",
                            ["year", "reporter_code", "reporter", "flow", "hs", "name", "value_usd",
                             "net_weight_kg", "qty", "qty_unit"], rows)


# ------------------------------------------------------------------ USGS Minerals Yearbook
def usgs_myb() -> None:
    """USGS Minerals Yearbook, Kazakhstan chapter. 2016+ are xlsx on pubs.usgs.gov; older chapters are
    xls/pdf on pubs.usgs.gov or on the USGS S3 archive of the former minerals.usgs.gov site."""
    log = LOG.setdefault("usgs_myb", {})
    d = OUT / "usgs_myb"
    d.mkdir(parents=True, exist_ok=True)
    have = {p.name for p in d.iterdir()}
    found, tried = {}, 0
    bases = ["https://pubs.usgs.gov/myb/vol3/{y}/",
             "https://s3-us-west-2.amazonaws.com/prd-wret/assets/palladium/production/mineral-pubs/country/{y}/",
             "https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/mineral-pubs/country/{y}/"]
    for y in range(1994, 2016):
        yy = str(y)[2:]
        names = [f"myb3-{y}-kz.xlsx", f"myb3-{y}-kz.xls", f"myb3-{y}-kz.pdf", f"kzmyb{yy}.pdf", f"kzmyb{yy}.xls",
                 f"myb3-{y}-kazakhstan.xlsx", f"myb3-{y}-kazakhstan.pdf"]
        got = False
        for base in bases:
            for n in names:
                if got and n.endswith(".pdf"):
                    continue
                url = base.format(y=y) + n
                tried += 1
                try:
                    r = requests.get(url, headers=HEADERS, timeout=60)
                except requests.RequestException:
                    continue
                ok = r.status_code == 200 and (r.content[:2] in (b"PK", bytes.fromhex("d0cf")) or r.content[:4] == b"%PDF")
                if ok:
                    fn = f"{y}_{n}"
                    (d / fn).write_bytes(r.content)
                    found[fn] = url
                    got = True
                    if r.content[:4] == b"%PDF":
                        try:
                            from pypdf import PdfReader
                            txt = "\n\n".join(f"===== page {i + 1} =====\n{(pg.extract_text() or '')}"
                                               for i, pg in enumerate(PdfReader(io.BytesIO(r.content)).pages))
                            (d / (fn + ".txt")).write_text(txt, encoding="utf-8")
                        except Exception as exc:  # noqa: BLE001
                            found[fn] += f" (pdf text error: {exc})"
            if got:
                break
    log["files"] = found
    log["tried"] = tried
    log["already_had"] = sorted(have)


# ------------------------------------------------------------------ BGS
def bgs() -> None:
    log = LOG.setdefault("bgs", {})
    url = "https://www2.bgs.ac.uk/mineralsuk/statistics/wms.cfc?method=searchWMS"
    r = get(url)
    log["search_page"] = r is not None
    # BGS WMS is an interactive tool; no stable export URL is documented. Recorded for manual follow-up.


def main() -> int:
    only = set(sys.argv[1:])
    parts_file = ROOT / "config" / "resource_history_parts.txt"
    if not only and parts_file.exists():
        only = set(parts_file.read_text(encoding="utf-8").split())
    for part in (energy_institute, owid_energy, eia, world_bank, comtrade, comtrade_mirror, usgs_myb, bgs):
        if only and part.__name__ not in only:
            continue
        try:
            part()
        except Exception as exc:  # noqa: BLE001
            LOG.setdefault("fatal", []).append(f"{part.__name__}: {exc!r}"[:500])
    LOG["finished_utc"] = datetime.now(timezone.utc).isoformat()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(LOG, ensure_ascii=False, indent=1)[:15000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
