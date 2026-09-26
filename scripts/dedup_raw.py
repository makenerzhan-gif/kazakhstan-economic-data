#!/usr/bin/env python3
"""Remove byte-identical raw copies from data/raw, keeping one file per distinct content
per agency, and record every removed file -> kept file in data/raw/dedup_<date>.json.

lib/raw_store stops such copies from being written since 2026-09-15; this tool exists for
what was archived before that rule and for copies a merge brings in (a branch made
before the rule, the daily CI run on main). Nothing with distinct content is touched:
a file is removed only when a file with exactly the same bytes stays, and the dated
manifest of the removed file is pointed at the survivor (`raw_file`).

    python scripts/dedup_raw.py                     # do it
    python scripts/dedup_raw.py --dry-run           # report only
    python scripts/dedup_raw.py --repair-manifests  # re-point manifests left naming a file an earlier dedup removed
    python scripts/dedup_raw.py --nbk-forms         # NBK form downloads equal in canonical form (below)

--nbk-forms compares the paginated NBK open-data form downloads (data/raw/nbk, the pages
archived by fetchers.nbk._fetch_nbk_form_paginated) by their CANONICAL form (lib/nbk_pages):
the API returns the same rows with per-page column labels that change on every call, and
no promised row order, so byte comparison never matched them and the 13.7 MB insurance
form was archived again on nearly every run from 2026-08-31. Files are grouped when their
canonical bytes are equal -- same rows, same values, same envelope and column entries;
only page arrangement, row order and per-page labels differ -- and one is kept: a file
already in canonical form if the group has one (it is what the fetcher writes now, so the
next unchanged download is recognised by raw_store.identical_twin), otherwise the earliest.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import nbk_pages  # noqa: E402

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


def find_nbk_form_duplicates() -> list[tuple[Path, list[Path]]]:
    """[(kept, [duplicates])] among the NBK form downloads whose canonical form
    (lib/nbk_pages) is identical. Files that are not form downloads are left out."""
    groups: dict[str, list[tuple[bool, Path]]] = defaultdict(list)
    for p in sorted((RAW / "nbk").glob("nbk_*.json")):
        if p.name.endswith(".manifest.json"):
            continue
        content = p.read_bytes()
        canonical = nbk_pages.canonical_bytes_of_archived(content)
        if canonical is not None:
            groups[hashlib.sha256(canonical).hexdigest()].append((canonical == content, p))
    out = []
    for files in groups.values():
        if len(files) > 1:
            files.sort(key=lambda cp: (0 if cp[0] else 1, _rank(cp[1])))
            out.append((files[0][1], [p for _, p in files[1:]]))
    return out


def _manifests(folder: Path):
    for manifest in sorted(folder.glob("*.manifest.json")):
        try:
            info = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(info, dict):
            yield manifest, info


BYTE_NOTE = "byte-identical copy {removed} removed {today}; the bytes are in {kept}"
CANONICAL_NOTE = ("copy {removed} removed {today}: same NBK form content as {kept} (equal in the canonical form of "
                  "scripts/lib/nbk_pages.py -- same rows and values; only page arrangement, row order and per-page "
                  "column labels differed); the content is in {kept}")


def _repoint(manifest: Path, info: dict, removed_name: str, kept_name: str, today: str, note: str = BYTE_NOTE) -> None:
    info["raw_file"] = kept_name
    info["raw_file_note"] = note.format(removed=removed_name, kept=kept_name, today=today)
    manifest.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")


def point_manifests(removed: Path, kept: Path, today: str, note: str = BYTE_NOTE) -> int:
    """Point every manifest in the folder that names the removed file at the survivor --
    not only the manifest named after the removed file: a shared workbook is named by
    the manifests of every indicator that reads it (the wage table 346883 feeds
    AVG_WAGE_QUARTERLY and AVG_WAGE_AGRICULTURE; until 2026-09-23 only the owner's
    manifest was re-pointed and the others were left dangling). A manifest with no
    `raw_file` names the file of its own stem (the NBK form manifests before 2026-09-26)."""
    n = 0
    own = removed.name.rsplit(".", 1)[0] + ".manifest.json"
    for manifest, info in _manifests(removed.parent):
        if info.get("raw_file", removed.name if manifest.name == own else None) == removed.name:
            _repoint(manifest, info, removed.name, kept.name, today, note)
            n += 1
    return n


def repair_manifests(today: str, dry_run: bool = False) -> int:
    """Re-point every manifest whose `raw_file` no longer exists but is named in a
    dedup record (data/raw/dedup_*.json), following chains (a survivor of one dedup
    removed by a later one). Returns the number of manifests changed."""
    mapping: dict[tuple[str, str], str] = {}                      # (agency, removed name) -> kept name
    for record in sorted(RAW.glob("dedup_*.json")):
        for removed_rel, kept_rel in json.loads(record.read_text(encoding="utf-8")).get("removed", {}).items():
            mapping[(Path(removed_rel).parent.name, Path(removed_rel).name)] = Path(kept_rel).name
    n = 0
    for folder in sorted(p for p in RAW.iterdir() if p.is_dir()):
        for manifest, info in _manifests(folder):
            name = info.get("raw_file")
            if not name or (folder / name).exists():
                continue
            seen, target = {name}, mapping.get((folder.name, name))
            while target is not None and not (folder / target).exists() and target not in seen:
                seen.add(target)
                target = mapping.get((folder.name, target))
            if target is None or not (folder / target).exists():
                print(f"dedup_raw: {manifest.name} names {name}, which is missing and not in any dedup record -- left as is")
                continue
            n += 1
            if not dry_run:
                _repoint(manifest, info, name, target, today)
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repair-manifests", action="store_true",
                    help="only re-point manifests whose raw_file was removed by an earlier dedup (see repair_manifests)")
    ap.add_argument("--nbk-forms", action="store_true",
                    help="NBK form downloads with equal canonical content instead of byte-identical files (see above)")
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    if args.repair_manifests:
        n = repair_manifests(today, dry_run=args.dry_run)
        print(f"dedup_raw --repair-manifests{' (dry run)' if args.dry_run else ''}: {n} manifests {'would be ' if args.dry_run else ''}re-pointed")
        return 0
    groups = find_nbk_form_duplicates() if args.nbk_forms else find_duplicates()
    note = CANONICAL_NOTE if args.nbk_forms else BYTE_NOTE
    removed: dict[str, str] = {}
    freed = 0
    for kept, dups in groups:
        for d in dups:
            freed += d.stat().st_size
            removed[d.relative_to(REPO_ROOT).as_posix()] = kept.relative_to(REPO_ROOT).as_posix()
            if not args.dry_run:
                point_manifests(d, kept, today, note)
                d.unlink()
    print(f"dedup_raw{' --nbk-forms' if args.nbk_forms else ''}{' (dry run)' if args.dry_run else ''}: "
          f"{len(groups)} contents with copies, "
          f"{len(removed)} files {'would be ' if args.dry_run else ''}removed, {freed / 1e6:.0f} MB")
    if removed and not args.dry_run:
        record = RAW / f"dedup_{today}.json"
        existing = json.loads(record.read_text(encoding="utf-8")) if record.exists() else {
            "date": today, "rule": "byte-identical raw files kept once per agency; every removed file maps to the file holding its bytes", "removed": {}}
        existing["removed"].update(removed)
        if args.nbk_forms:
            existing["nbk_forms_rule"] = (
                "NBK paginated form downloads whose canonical form (scripts/lib/nbk_pages.py) is identical -- same rows "
                "and values, differing only in page arrangement, row order and per-page column labels -- kept once; a "
                "file already in canonical form is kept when the group has one, otherwise the earliest. These removals "
                "are listed in nbk_forms_removed and, with the file kept, in removed.")
            existing["nbk_forms_removed"] = sorted(set(existing.get("nbk_forms_removed", [])) | set(removed))
        existing["removed_files"] = len(existing["removed"])
        record.write_text(json.dumps(existing, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"record: {record.relative_to(REPO_ROOT).as_posix()} ({existing['removed_files']} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
