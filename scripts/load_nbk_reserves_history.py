#!/usr/bin/env python3
"""One-off load of gross international reserves and of the National Fund's FX assets before the
NBK open-data form (1995 .. 2017) into data/reference/nbk_reserves_history.csv.

FX_RESERVES and NATIONAL_FUND_ASSETS (scripts/fetchers/nbk.py) come from formId=34 of the NBK
open-data API, which starts with the 2018-01-01 observation. NBK publishes the same table from
January 1995 on its site, section «Международные резервы и активы Национального фонда РК»:

    https://nationalbank.kz/ru/international-reserve-and-asset/mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk
    records (JSON):  <page>/records?beginMount=1&beginYear=1995&endMount=12&endYear=<year>

One record per month, USD million rounded to whole numbers, dated by `reporting_date` (an
irregular day inside the month). The API dates the same position on the first day of the
NEXT month: the page's December 2017 record (30 997, reporting_date 2017-12-12) is the API's
2018-01-01 (30 996.649). With that one-month shift the page equals the API rounded to whole
numbers on all 106 months 2018-01 .. 2026-10 for both series (checked 2026-11-26); the
fetchers prepend only dates before the API's first and stop if any overlap month differs.

Columns: date (pipeline convention, first day of month), fx_reserves, national_fund_assets
(empty before the Fund's first published month), reporting_date (as on the page).

Run:   python scripts/load_nbk_reserves_history.py [--json FILE]
       without --json the records are downloaded from the page above.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "data" / "reference" / "nbk_reserves_history.csv"
PAGE = "https://nationalbank.kz/ru/international-reserve-and-asset/mezhdunarodnye-rezervy-i-aktivy-nacionalnogo-fonda-rk"
GROSS = "gross_international_reserve_volume_million_dollar"
NF = "national_fund_republic_of_kazakhstan_volume_million_dollar"


def next_month_start(reporting_date: str) -> str:
    y, m = int(reporting_date[:4]), int(reporting_date[5:7])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01"


def rows_from_records(records: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in records:
        if r.get(GROSS) in (None, "") and r.get(NF) in (None, ""):
            continue
        d = next_month_start(str(r["reporting_date"]))
        if d in seen:
            raise ValueError(f"two page records fall on {d}: the one-record-per-month layout changed")
        seen.add(d)
        out.append({"date": d,
                    "fx_reserves": "" if r.get(GROSS) in (None, "") else float(r[GROSS]),
                    "national_fund_assets": "" if r.get(NF) in (None, "") else float(r[NF]),
                    "reporting_date": str(r["reporting_date"])[:10]})
    out.sort(key=lambda x: x["date"])
    months = [(int(x["date"][:4]), int(x["date"][5:7])) for x in out]
    for (y0, m0), (y1, m1) in zip(months, months[1:]):
        if (y1 * 12 + m1) - (y0 * 12 + m0) != 1:
            raise ValueError(f"gap in the page records between {y0}-{m0:02d} and {y1}-{m1:02d}")
    return out


def download() -> list[dict]:
    import requests
    q = {"beginMount": 1, "beginYear": 1995, "endMount": 12, "endYear": date.today().year}
    resp = requests.get(f"{PAGE}/records", params=q, headers={"User-Agent": "kazakhstan-economic-data"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, help="a saved copy of the page's /records response")
    a = ap.parse_args()
    records = json.loads(a.json.read_text(encoding="utf-8")) if a.json else download()
    rows = rows_from_records(records)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "fx_reserves", "national_fund_assets", "reporting_date"])
        w.writeheader()
        w.writerows(rows)
    print(f"{OUT.relative_to(REPO_ROOT)}: {len(rows)} months, {rows[0]['date']} .. {rows[-1]['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
