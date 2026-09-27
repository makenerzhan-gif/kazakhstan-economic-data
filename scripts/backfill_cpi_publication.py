#!/usr/bin/env python3
"""One-off: build the history of the CPI publication datasets (config/dims.yaml, fetcher
bns_cpi) from every edition BNS keeps online, July 2004 – today.

    python scripts/backfill_cpi_publication.py [--cache DIR]

Sources (stat.gov.kz → Экономика → Цены → Электронные таблицы):
  166775  «Индекс потребительских цен в Республике Казахстан», May 1999 – December 2022
          (rar/zip archives of xls to 2019, xlsx after; the html editions before July 2004
          are a different, pre-COICOP layout and are not read)
  27168   «Вклад отдельных составляющих в индексе потребительских цен», January 2020 –
          December 2022 (xls)
  19117   «Индекс потребительских цен и производные показатели» (Т-15-02-М), October 2022 on;
          wins over 166775 on the three months both cover

Needs `unar` (apt install unar) for the rar archives. The archives are read from --cache
when present and downloaded otherwise; they are not added to data/raw (65 MB of history
that the processed layer and this script reproduce). After this script, the daily
update_dims run (fetchers/bns_cpi.fetch) keeps the datasets current from 19117.

The 2012–2019 editions print Kazakh and Russian in one cell («Көлік Транспорт»), sometimes
Kazakh alone; the Russian label is recovered from the editions that print both cleanly
(2004–2012 and 2019–2026): the Kazakh→Russian pairs they contain and the set of Russian
labels they use (see Resolver). Two BNS typos are corrected explicitly (TYPOS).
"""
from __future__ import annotations

import argparse
import collections
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetchers import bns, bns_cpi, bns_dims  # noqa: E402
from lib import dims  # noqa: E402

N = dims.normalise_label
# (Kazakh, Russian) as printed → the Russian label meant. March 2008: the alcohol-and-tobacco
# row is labelled «Продовольственные товары» in Russian (its Kazakh label and values are
# the division's). May 2022: «Қант» / «Сахар, джем, мед,шоколад…» is the group, kept as printed.
TYPOS = {("Алкогольді ішімдіктер, темекі өнімдері", "Продовольственные товары"): "Алкогольные напитки, табачные изделия"}


def reliable(year: int, month: int) -> bool:
    """Editions whose labels split cleanly into Kazakh and Russian (or are Russian only)."""
    return (year, month) <= (2012, 1) or (year, month) >= (2019, 5)


class Resolver:
    def __init__(self, parsed: dict):
        self.known: collections.Counter = collections.Counter()
        self.kz2ru: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for (_, year, month), tables in parsed.items():
            if not reliable(year, month):
                continue
            for t in tables:
                for r in t.rows:
                    for kz, ru in ((r.kz, r.ru), (r.block_kz or "", r.block or "")):
                        if ru:
                            self.known[N(ru)] += 1
                            if kz:
                                self.kz2ru[N(kz)][ru] += 1

    def __call__(self, kz: str, ru: str) -> str:
        kz, ru = (kz or "").strip(), (ru or "").strip()
        if (kz, ru) in TYPOS:
            return TYPOS[(kz, ru)]
        tokens = ru.split()
        for i in range(1, len(tokens)):          # «Байланыс Связь»: a Kazakh word with no Kazakh letter in front
            head, tail = " ".join(tokens[:i]), " ".join(tokens[i:])
            if N(head) in self.kz2ru and N(tail) in self.known:
                return tail
        if ru and N(ru) in self.known:
            return ru
        for text in (ru, kz):                     # «Қарақұмық гречневая»: the Russian tail in lower case
            tokens = text.split()
            for i in range(1, len(tokens)):
                tail = " ".join(tokens[i:])
                if N(tail) in self.known:
                    return tail[:1].upper() + tail[1:]
        if kz and N(kz) in self.kz2ru:
            return self.kz2ru[N(kz)].most_common(1)[0][0]
        return ru


def borrow_labels(parsed: dict) -> None:
    """May 2021 of the contribution table (27168) is printed in Kazakh only, in labels the CPI
    tables never use. Its rows are the same 46 in the same order as April and June 2021, so
    the Russian labels are taken from there by position — only when both neighbours agree."""
    for (name, year, month), tables in parsed.items():
        for t in tables:
            if t.kind != "contribution" or sum(bool(r.ru) for r in t.rows) > len(t.rows) // 2:
                continue
            prev = (year, month - 1) if month > 1 else (year - 1, 12)
            nxt = (year, month + 1) if month < 12 else (year + 1, 1)
            sides = [[x for x in parsed.get((name, *ym), []) if x.kind == "contribution"] for ym in (prev, nxt)]
            if not all(len(s) == 1 and len(s[0].rows) == len(t.rows) for s in sides):
                continue
            ru_prev, ru_next = ([r.ru for r in s[0].rows] for s in sides)
            if ru_prev == ru_next:
                for r, ru in zip(t.rows, ru_prev):
                    r.ru = ru


def extract(archive: Path, into: Path) -> list[Path]:
    into.mkdir(parents=True, exist_ok=True)
    tool = shutil.which("unar")
    if not tool:
        sys.exit("unar is needed for the rar archives: apt install unar")
    subprocess.run([tool, "-q", "-f", "-D", "-o", str(into), str(archive)], check=False, capture_output=True)
    for inner in list(into.rglob("*.rar")) + list(into.rglob("*.zip")):
        subprocess.run([tool, "-q", "-f", "-D", "-o", str(inner.parent), str(inner)], check=False, capture_output=True)
    return sorted(p for p in into.rglob("*") if p.suffix.lower() in (".xls", ".xlsx"))


def workbooks(edition: dict, cache: Path) -> list[bytes]:
    path = cache / f"{edition['element_id']}.{edition['format']}"
    if not path.exists() or path.stat().st_size < 1000:
        path.write_bytes(bns._download(bns_cpi.FILE_URL.format(eid=edition["element_id"])))
    if edition["format"] in ("rar", "zip"):
        return [p.read_bytes() for p in extract(path, cache / edition["element_id"])]
    return [path.read_bytes()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "bns_cpi_editions")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)

    parsed: dict[tuple[str, int, int], list[bns_cpi.Table]] = {}
    for name in (*bns_cpi.PREDECESSORS, bns_cpi.PUBLICATION):
        listing = bns_cpi.parse_listing(bns._download(bns_cpi.LISTING_URL.format(name=name)).decode("utf-8", "replace"))
        print(f"publication {name}: {len(listing)} editions, {listing[0]['year']}-{listing[0]['month']:02d} … "
              f"{listing[-1]['year']}-{listing[-1]['month']:02d}")
        for e in listing:
            if (e["year"], e["month"]) < (2004, 7):
                continue
            tables = []
            for content in workbooks(e, args.cache):
                tables += bns_cpi.parse_workbook(bns_dims._sheets(content), e["year"], e["month"])
            parsed[(name, e["year"], e["month"])] = tables

    borrow_labels(parsed)
    resolve = Resolver(parsed)
    by_dataset: dict[str, dict[tuple, dict]] = collections.defaultdict(dict)
    problems: list[str] = []
    overlap: list[tuple] = []
    # predecessors first, the current publication last: it wins where both cover a month
    for (name, year, month), tables in sorted(parsed.items(), key=lambda kv: (kv[0][0] == bns_cpi.PUBLICATION, kv[0][1:])):
        recs, probs = bns_cpi.edition_records(tables, year, month, resolve)
        problems += probs + [f"{year}-{month:02d} {t.kind}: {t.repaired}" for t in tables if t.repaired]
        for ds_id, rows in recs.items():
            for r in rows:
                key = (r["date"], r["region"], r["item_code"])
                old = by_dataset[ds_id].get(key)
                if old and name == bns_cpi.PUBLICATION:
                    overlap.append((ds_id, key, old["value"], r["value"]))
                by_dataset[ds_id][key] = r

    for ds_id in sorted(by_dataset):
        rows = sorted(by_dataset[ds_id].values(), key=lambda r: (r["item_code"], r["region"], r["date"]))
        dims.write_processed(ds_id, rows)
        print(f"{ds_id}: {len(rows)} rows, {len({r['item_code'] for r in rows})} items, "
              f"{min(r['date'] for r in rows)} … {max(r['date'] for r in rows)}")
    diff = [o for o in overlap if abs(o[2] - o[3]) > 0.051]
    print(f"overlap 166775/19117 (2022-10 … 2022-12): {len(overlap)} values, {len(diff)} differ by more than 0.05")
    for o in diff[:10]:
        print("   ", o)
    print(f"{len(problems)} problems")
    for p in problems:
        print("   ", p)


if __name__ == "__main__":
    main()
