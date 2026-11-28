"""What a run did to the history that was already stored -- not to the new points.

The validators look at a series as it is; nothing compared it with what was there before the
run. So on 2026-10..11 four ARDFM series grew by 66 months of one repeated value (the stored
rows were shifted a month back on every run, scripts/fetchers/ardfm.py) and it was found by
hand. This module compares every processed file the run changed with the committed one
(`git show HEAD:<file>`) and reports:

  start     the first observation moved into the past
  inserted  observations appeared inside the span that was already stored (scalar series only)
  removed   observations that were stored are gone
  flat      (scalar series only) a run of identical values inside the old span is now longer than any before
            (FLAT_MIN points or more, and FLAT_GROWTH longer than the old longest run)

A report, never a block: a source does publish back history, and a history load by hand shows
here too. The lines go into the run report (## Stored history changed shape) and from there
into the run's issue (scripts/run_issue.py).
"""
from __future__ import annotations

import csv
import io
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = "data/processed"
FLAT_MIN, FLAT_GROWTH = 6, 3


def _rows(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _key(r: dict) -> tuple:
    return (r.get("region", ""), r.get("item_code", ""))


def _longest_flat(values: list[str]) -> int:
    best = cur = 0
    prev = object()
    for v in values:
        cur = cur + 1 if v == prev and v not in ("", "nan") else 1
        best, prev = max(best, cur), v
    return best


def compare(old_text: str, new_text: str) -> list[str]:
    """The findings for one processed file (scalar: date,value; item-level: + region,item_code)."""
    old, new = _rows(old_text), _rows(new_text)
    if not old or not new or "date" not in old[0] or "date" not in new[0]:
        return []
    old_keys = {(r["date"],) + _key(r) for r in old}
    new_keys = {(r["date"],) + _key(r) for r in new}
    old_first, old_last = min(r["date"] for r in old), max(r["date"] for r in old)
    new_first = min(r["date"] for r in new)
    out = []
    added = new_keys - old_keys
    before = sum(1 for k in added if k[0] < old_first)
    inside = sum(1 for k in added if old_first <= k[0] <= old_last)
    removed = old_keys - new_keys
    if new_first < old_first:
        out.append(f"start moved back from {old_first} to {new_first} ({before} observations before the old start)")
    scalar = "item_code" not in new[0]   # an item-level file gains items at its latest dates all the time
    if inside and scalar:
        dates = sorted(k[0] for k in added if old_first <= k[0] <= old_last)
        out.append(f"{inside} observations inserted inside the stored span ({dates[0]}..{dates[-1]})")
    if removed:
        dates = sorted(k[0] for k in removed)
        out.append(f"{len(removed)} stored observations removed ({dates[0]}..{dates[-1]})")
    if scalar:
        flat_old = _longest_flat([r.get("value", "") for r in sorted(old, key=lambda r: r["date"])])
        flat_new = _longest_flat([r.get("value", "") for r in sorted(new, key=lambda r: r["date"]) if r["date"] <= old_last])
        if flat_new >= FLAT_MIN and flat_new >= flat_old + FLAT_GROWTH:
            out.append(f"{flat_new} identical values in a row inside the old span (the longest run before was {flat_old})")
    return out


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def findings(base: str = "HEAD", head: str | None = None) -> list[dict]:
    """Findings for every processed CSV that differs between `base` and the working tree
    (or the commit `head`). [] when git is not available -- the guard never fails a run."""
    try:
        names = _git("diff", "--name-only", base, *([head] if head else []), "--", PROCESSED).split("\n")
    except (OSError, subprocess.CalledProcessError):
        return []
    out = []
    for name in sorted(n for n in names if n.endswith(".csv")):
        try:
            old_text = _git("show", f"{base}:{name}")
            new_text = _git("show", f"{head}:{name}") if head else (REPO_ROOT / name).read_text(encoding="utf-8")
        except (OSError, subprocess.CalledProcessError):
            continue                     # a new file, or one the run removed
        for line in compare(old_text, new_text):
            out.append({"file": name[len(PROCESSED) + 1:], "finding": line})
    return out


def report_lines(found: list[dict]) -> list[str]:
    if not found:
        return []
    lines = ["## Stored history changed shape", "",
             "Compared with the data committed before this run (scripts/lib/history_guard.py). A source may have "
             "published back history; a fetcher may also have damaged what was stored -- look at each.", ""]
    lines += [f"- **{f['file']}**: {f['finding']}" for f in found]
    lines.append("")
    return lines
