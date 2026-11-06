"""One-off / on-demand fetch of two natural-capital sources (run by .github/workflows/natural-capital.yml).

1. BNS «Система природно-экономического учёта» (stat.gov.kz → Окружающая среда → stat-speu):
   every edition of the «Счёт активов минеральных и энергетических ресурсов» and the related
   SEEA account publications. The listing pages are crawled for publication ids, each
   publication's own file (stat.gov.kz/api/iblock/element/<id>/file/ru/) is downloaded into
   data/raw/bns_seea/, and PDF text is extracted next to it (.txt) for parsing.
   Known editions are seeded so the run still yields something if the listing markup changes.

2. OECD NEA / IAEA «Uranium 2026: Resources, Production and Demand» (Red Book, 14.09.2026).
   The PDF itself is NOT committed (the repository is public; the report stays with its
   publisher) -- it is kept only as a workflow artifact. What is committed is a data extract:
   numeric lines of the Kazakhstan country report and every line mentioning Kazakhstan in the
   global tables, with page numbers (data/raw/nea/redbook2026_kazakhstan_lines.txt).

Every step logs into reports/natural_capital_fetch.json, which is committed, so a failed or
partial run can be diagnosed from the repository alone.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
BNS_DIR = ROOT / "data" / "raw" / "bns_seea"
NEA_DIR = ROOT / "data" / "raw" / "nea"
TMP_DIR = ROOT / "tmp_natural_capital"          # artifact only, not committed
REPORT = ROOT / "reports" / "natural_capital_fetch.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)",
           "Accept-Language": "ru,en;q=0.8"}

BNS_BASE = "https://stat.gov.kz"
BNS_LISTINGS = [
    "/ru/industries/environment/stat-speu/publications/",
    "/ru/industries/environment/stat-speu/spreadsheets/",
    "/ru/industries/environment/stat-speu/",
    "/en/industries/environment/stat-speu/publications/",
]
BNS_FILE = BNS_BASE + "/api/iblock/element/{eid}/file/{lang}/"
# Seen in the 22.01.2026 edition and its references (ru / en / kz pages and source files).
BNS_SEED_IDS = ["504418", "509558", "509550", "478736", "479809", "479470"]
KEYWORDS = ("минерал", "энергетическ", "актив", "запас", "природно-эконом", "seea", "mineral", "asset",
            "счет", "счёт")

NEA_PAGES = [
    "https://www.oecd-nea.org/jcms/pl_121658/uranium-2026-resources-production-and-demand",
    "https://www.oecd-nea.org/jcms/pl_121582/adequate-uranium-resources-available-but-sustained-investment-essential-to-support-global-nuclear-capacity-growth",
    "https://www.iaea.org/newscenter/pressreleases/adequate-uranium-resources-available-but-sustained-investment-essential-to-support-global-nuclear-capacity-growth",
]

LOG: dict = {"started_utc": datetime.now(timezone.utc).isoformat(), "bns": {}, "nea": {}}


def get(url: str, timeout: int = 120) -> requests.Response | None:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            LOG.setdefault("http_errors", []).append({"url": url, "status": r.status_code})
            if r.status_code in (403, 404):
                return None
        except requests.RequestException as exc:
            LOG.setdefault("http_errors", []).append({"url": url, "error": str(exc)[:300]})
        time.sleep(3 * (attempt + 1))
    return None


def kind_of(content: bytes) -> str:
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:2] == b"PK":
        return "xlsx"
    if content[:4] == bytes.fromhex("d0cf11e0"):
        return "xls"
    return "bin"


def pdf_text(content: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    return [(p.extract_text() or "") for p in reader.pages]


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


# ------------------------------------------------------------------ BNS
def bns() -> None:
    log = LOG["bns"]
    BNS_DIR.mkdir(parents=True, exist_ok=True)
    found: dict[str, str] = {}                    # publication id -> title
    log["listings"] = []
    for path in BNS_LISTINGS:
        for page in range(1, 11):
            url = BNS_BASE + path + (f"?PAGEN_1={page}" if page > 1 else "")
            r = get(url)
            if r is None:
                log["listings"].append({"url": url, "ok": False})
                break
            html = r.text
            new = 0
            for href, text in re.findall(r'<a[^>]+href="([^"]*/(?:publications|spreadsheets)/\d+/?[^"]*)"[^>]*>(.*?)</a>', html, re.S):
                m = re.search(r"/(?:publications|spreadsheets)/(\d+)", href)
                if m and m.group(1) not in found:
                    found[m.group(1)] = strip_tags(text)
                    new += 1
            for eid in re.findall(r"/api/iblock/element/(\d+)/file/", html):
                if eid not in found:
                    found[eid] = ""
                    new += 1
            log["listings"].append({"url": url, "ok": True, "new_ids": new, "bytes": len(html)})
            if new == 0:
                break
    for sid in BNS_SEED_IDS:
        found.setdefault(sid, "(seed)")
    log["ids_found"] = found

    # publication pages can carry their own titles and more file links
    targets: dict[str, str] = {}
    for pid, title in found.items():
        page = get(f"{BNS_BASE}/ru/industries/environment/stat-speu/publications/{pid}/")
        page_title = ""
        extra: list[str] = []
        if page is not None:
            m = re.search(r"<title>(.*?)</title>", page.text, re.S)
            page_title = strip_tags(m.group(1)) if m else ""
            extra = re.findall(r"/api/iblock/element/(\d+)/file/", page.text)
        t = " ".join([title, page_title]).lower()
        if title == "(seed)" or any(k in t for k in KEYWORDS):
            targets[pid] = (title + " | " + page_title).strip(" |")
            for e in extra:
                targets.setdefault(e, f"(file linked from {pid})")
    log["targets"] = targets

    files = []
    for eid, title in sorted(targets.items()):
        for lang in ("ru", "en"):
            r = get(BNS_FILE.format(eid=eid, lang=lang))
            if r is None or not r.content:
                continue
            k = kind_of(r.content)
            name = f"bns_seea_{eid}_{lang}.{k}"
            (BNS_DIR / name).write_bytes(r.content)
            rec = {"element_id": eid, "lang": lang, "title": title, "file": name, "bytes": len(r.content),
                   "sha256": hashlib.sha256(r.content).hexdigest()}
            if k == "pdf":
                try:
                    pages = pdf_text(r.content)
                    txt = "\n\n".join(f"===== page {i + 1} =====\n{p}" for i, p in enumerate(pages))
                    (BNS_DIR / name.replace(".pdf", ".txt")).write_text(txt, encoding="utf-8")
                    rec["pages"] = len(pages)
                    head = re.sub(r"\s+", " ", pages[0])[:300] if pages else ""
                    rec["first_page"] = head
                except Exception as exc:  # noqa: BLE001
                    rec["pdf_error"] = str(exc)[:300]
            files.append(rec)
            break  # ru found -> skip en
    log["files"] = files


# ------------------------------------------------------------------ Red Book
def nea() -> None:
    log = LOG["nea"]
    NEA_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    candidates: list[str] = []
    for page in NEA_PAGES:
        r = get(page)
        log.setdefault("pages", []).append({"url": page, "ok": r is not None})
        if r is None:
            continue
        for href in re.findall(r'href="([^"]+)"', r.text):
            h = href.lower()
            if (".pdf" in h or "/upload/docs/application/pdf" in h or "download" in h) and ("uranium" in h or "red" in h or "pdf" in h):
                u = urljoin(page, href)
                if u not in candidates:
                    candidates.append(u)
    log["pdf_candidates"] = candidates[:40]
    pdf = None
    for u in candidates:
        r = get(u, timeout=300)
        if r is not None and r.content[:4] == b"%PDF" and len(r.content) > 2_000_000:
            pdf, log["pdf_url"] = r.content, u
            break
    if pdf is None:
        log["error"] = "no Red Book PDF found among candidates"
        return
    (TMP_DIR / "uranium_2026_red_book.pdf").write_bytes(pdf)
    log["pdf_bytes"] = len(pdf)
    log["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
    pages = pdf_text(pdf)
    log["pdf_pages"] = len(pages)
    out = []
    kz_pages = []
    for i, p in enumerate(pages, 1):
        n = p.count("Kazakhstan")
        if n == 0:
            continue
        lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
        # country report pages: page header/running title "Kazakhstan" and dense mentions
        is_report = n >= 3 or (lines and lines[0].startswith("Kazakhstan")) or (lines and lines[-1].startswith("Kazakhstan"))
        if is_report:
            kz_pages.append(i)
            keep = [ln for ln in lines if re.search(r"\d", ln) or ln.isupper() or ln.lower().startswith(("table", "kazakhstan", "reasonably", "inferred", "identified", "prognosticated", "speculative", "production", "cost"))]
        else:
            keep = [ln for ln in lines if "Kazakhstan" in ln or ln.lower().startswith("table")]
        out.append(f"===== page {i} ({'country report' if is_report else 'global table'}) =====")
        out.extend(keep)
    (NEA_DIR / "redbook2026_kazakhstan_lines.txt").write_text("\n".join(out), encoding="utf-8")
    log["kazakhstan_report_pages"] = kz_pages
    log["extract_lines"] = len(out)


def main() -> int:
    for part in (bns, nea):
        try:
            part()
        except Exception as exc:  # noqa: BLE001 -- the report must still be written
            LOG.setdefault("fatal", []).append(f"{part.__name__}: {exc!r}"[:500])
    LOG["finished_utc"] = datetime.now(timezone.utc).isoformat()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(LOG, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: (v if k != "bns" else {kk: vv for kk, vv in v.items() if kk != "ids_found"}) for k, v in LOG.items()},
                     ensure_ascii=False, indent=1)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
