#!/usr/bin/env python3
"""Remove byte-identical raw copies from data/raw, keeping one file per distinct content
per agency, and record every removed file -> kept file in data/raw/dedup_<date>.json.

lib/raw_store stops such copies from being written since 2026-09-15; this tool exists for
what was archived before that rule and for copies a merge brings in (a branch made
before the rule, the daily CI run on main). Nothing with distinct content is touched:
a file is removed only when a file with exactly the same bytes stays, and the dated
manifest of the removed file is pointed at the survivor (`raw_file`).

    python scripts/dedup_raw.py            # do it
    python scripts/dedup_raw.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW = REPO_ROOT / "data" / "raw"
NAME = re.compile(r"^(?P<agency>[a-z]+)_(?P<id>.+?)_(?P<date>\d{4}-\d{2}-\d{2})(?P<suffix>_\d{6}(-\d+)?)?\.(?P<ext>\w+)$")
# the indicator whose fetcher owns a shared file from now on comes first
OWNER_PRIORITY = {"bns": ["EXPORTS", "IMPORTS"], "wb": ["WB_COMMODITY_PRICES_ANNUAL", "WB_COMMODITY_PRICE_FORECASTS"]}


def _rank(p: Path) -> tuple:
    """Keep the owner's file, then an un-suffixed name, then the earliest date (the
    first archive of that content)."""
    m = NAME.match(p.name)
    pri = OWNER_PRIORITY.get(p.parent.name, [])
    ind = m.group("id").upper() if m else p.name
    return (0 if ind in pri else 1, pri.index(ind) if ind in pri else 0, 1 if (m and m.group("suffix")) else 0,
            m.group("date") if m else "", p.name)


def find_duplicates() -> list[tuple[Path, list[Path]]]:
    """[(kept, [duplicates])] — grouped by (agency, size) first, hashed only within a group."""
    by_size: dict[tuple, list[Path]] = defaultdict(list)
    for p in RAW.rglob("*"):
        if p.is_file() and not p.name.endswith(".manifest.json") and not p.name.startswith("dedup_"):
            by_size[(p.parent.name, p.stat().st_size)].append(p)
    groups: dict[tuple, list[Path]] = defaultdict(list)
    for (agency, _size), files in by_size.items():
        if len(files) > 1:
            for p in files:
                groups[(agency, hashlib.sha256(p.read_bytes()).hexdigest())].append(p)
    out = []
    for files in groups.values():
        if len(files) > 1:
            files.sort(key=_rank)
            out.append((files[0], files[1:]))
    return out


def point_manifest(removed: Path, kept: Path, today: str) -> bool:
    m = NAME.match(removed.name)
    if not m:
        return False
    manifest = removed.parent / f"{m.group('agency')}_{m.group('id')}_{m.group('date')}.manifest.json"
    if not manifest.exists():
        return False
    try:
        info = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        info = {}
    info["raw_file"] = kept.name
    info["raw_file_note"] = f"byte-identical copy {removed.name} removed {today}; the bytes are in {kept.name}"
    manifest.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    groups = find_duplicates()
    removed: dict[str, str] = {}
    freed = 0
    for kept, dups in groups:
        for d in dups:
            freed += d.stat().st_size
            removed[d.relative_to(REPO_ROOT).as_posix()] = kept.relative_to(REPO_ROOT).as_posix()
            if not args.dry_run:
                point_manifest(d, kept, today)
                d.unlink()
    print(f"dedup_raw{' (dry run)' if args.dry_run else ''}: {len(groups)} contents with copies, "
          f"{len(removed)} files {'would be ' if args.dry_run else ''}removed, {freed / 1e6:.0f} MB")
    if removed and not args.dry_run:
        record = RAW / f"dedup_{today}.json"
        existing = json.loads(record.read_text(encoding="utf-8")) if record.exists() else {
            "date": today, "rule": "byte-identical raw files kept once per agency; every removed file maps to the file holding its bytes", "removed": {}}
        existing["removed"].update(removed)
        existing["removed_files"] = len(existing["removed"])
        record.write_text(json.dumps(existing, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"record: {record.relative_to(REPO_ROOT).as_posix()} ({existing['removed_files']} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
