"""The parts of the run report that compare this run with the ones before it.

Warnings. The validators repeat on every run every warning the stored history has ever
earned: the report of 2026-11-26 was 1.6 MB, 12 442 warning lines, and a warning about a
point published that day could not be found among them. The report now prints only the
warnings not seen in the previous run and counts the rest by kind. What "seen" means is
kept in metadata/known_warnings.txt: one short hash per (source, dataset, warning text),
sorted, rewritten by every run. The first run with no such file records the baseline and
prints no warning as new.

Revisions. Every run appends what it revised to metadata/revisions/<id>_revisions.jsonl
and nothing summed it up. `revision_lines` lists, for this run's detection date, each
series whose stored history changed: how many observations, over which periods, by how
much at most. Series revised on ROUTINE_RUNS or more earlier dates (seasonally adjusted
series, indices recomputed by their source every week) are collapsed into one line.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWN_WARNINGS = REPO_ROOT / "metadata" / "known_warnings.txt"
REVISIONS_ROOT = REPO_ROOT / "metadata" / "revisions"
MAX_NEW_PER_DATASET = 20
ROUTINE_RUNS = 5
MAX_REVISED_LISTED = 60

# Kinds counted in the report. The last two change their text on every run (a date, a count)
# and say nothing about the data, so they are never "new".
KINDS = (("jump", re.compile(r"Unexpected jump")), ("gap", re.compile(r"Gap of ")),
         ("not re-downloaded", re.compile(r"not re-downloaded")), ("not listed", re.compile(r"more warnings not listed")))
VOLATILE = ("not re-downloaded", "not listed")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def kind(warning: str) -> str:
    return next((name for name, rx in KINDS if rx.search(warning)), "other")


def latest_date(warning: str) -> str:
    """The latest ISO date a warning names ('' when none) -- newest-first order for a capped list."""
    return max(_DATE.findall(warning), default="")


def key(source: str, dataset: str, warning: str) -> str:
    return hashlib.sha1(f"{source}/{dataset}|{warning}".encode("utf-8")).hexdigest()[:16]


def load_known(path: Path = KNOWN_WARNINGS) -> set[str] | None:
    return set(path.read_text(encoding="utf-8").split()) if path.exists() else None


def split_warnings(entries: list, known: set[str] | None) -> tuple[dict[int, list[str]], set[str], Counter]:
    """(new warnings by entry position, the keys of this run, counts by kind). With no record
    of earlier runs (`known` is None) nothing is new: this run is the baseline."""
    new: dict[int, list[str]] = {}
    seen: set[str] = set()
    kinds: Counter = Counter()
    for i, e in enumerate(entries):
        for w in e.warnings:
            k = kind(w)
            kinds[k] += 1
            if k in VOLATILE:
                continue
            h = key(e.source, e.dataset, w)
            seen.add(h)
            if known is not None and h not in known:
                new.setdefault(i, []).append(w)
    return new, seen, kinds


def save_known(seen: set[str], path: Path = KNOWN_WARNINGS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(seen)) + "\n", encoding="utf-8")


def warning_lines(entries: list, new: dict[int, list[str]], kinds: Counter, baseline: bool) -> list[str]:
    total = sum(kinds.values())
    lines = ["## Warnings", "",
             f"{total} in all: " + (", ".join(f"{k} {n}" for k, n in kinds.most_common()) or "none") + ". "
             "Only those not raised by the previous run are printed (metadata/known_warnings.txt); "
             "the full text of every warning is in logs/ of the run's artifact.", ""]
    if baseline:
        lines += ["No record of earlier runs: this run is the baseline, nothing is printed as new.", ""]
    elif not new:
        lines += ["No new warnings.", ""]
    else:
        lines += [f"### New this run: {sum(len(v) for v in new.values())} in {len(new)} datasets", ""]
        for i in sorted(new):
            e = entries[i]
            ws = sorted(new[i], key=latest_date, reverse=True)
            lines.append(f"- **{e.source}/{e.dataset}**")
            lines += [f"  - {w}" for w in ws[:MAX_NEW_PER_DATASET]]
            if len(ws) > MAX_NEW_PER_DATASET:
                lines.append(f"  - ... and {len(ws) - MAX_NEW_PER_DATASET} more")
        lines.append("")
    return lines


# ---------------------------------------------------------------- revisions

def _rel(old: float, new: float) -> float | None:
    return abs(new / old - 1) * 100 if old not in (0, None) and old == old and new == new else None


def revisions_of(day: str, root: Path = REVISIONS_ROOT) -> list[dict]:
    """One row per series revised on `day` (ISO date): n, first and last revised period, the
    largest relative change in % (None when no old value allows one), earlier revision dates."""
    out = []
    for path in sorted(root.glob("*_revisions.jsonl")) if root.exists() else []:
        todays, earlier = [], set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if f'"{day}"' not in line:
                m = re.search(r'"detected_date": "(\d{4}-\d{2}-\d{2})"', line)
                if m:
                    earlier.add(m.group(1))
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("detected_date") == day:
                todays.append(r)
        if not todays:
            continue
        periods = sorted(str(r["period"]).split()[0] for r in todays)
        rels = [x for x in (_rel(r["old_value"], r["new_value"]) for r in todays) if x is not None]
        out.append({"id": todays[0]["indicator_id"], "n": len(todays), "first": periods[0], "last": periods[-1],
                    "max_pct": max(rels) if rels else None, "earlier_runs": len(earlier - {day})})
    return out


def revision_lines(rows: list[dict]) -> list[str]:
    if not rows:
        return ["## Revisions of stored history", "", "None this run.", ""]
    fmt = lambda r: (f"- **{r['id']}**: {r['n']} observations, {r['first']}..{r['last']}, "          # noqa: E731
                     + (f"largest change {r['max_pct']:.3g}%" if r["max_pct"] is not None else "no relative change computable")
                     + f"; revised on {r['earlier_runs']} earlier dates")
    rare = sorted((r for r in rows if r["earlier_runs"] < ROUTINE_RUNS), key=lambda r: -r["n"])
    routine = sorted((r for r in rows if r["earlier_runs"] >= ROUTINE_RUNS), key=lambda r: -r["n"])
    lines = ["## Revisions of stored history", "",
             f"{len(rows)} series changed values that were already stored "
             f"({sum(r['n'] for r in rows)} observations; metadata/revisions/).", ""]
    if rare:
        lines += [f"### Seldom revised (fewer than {ROUTINE_RUNS} earlier dates): {len(rare)}", ""]
        lines += [fmt(r) for r in rare[:MAX_REVISED_LISTED]]
        lines += [f"- ... and {len(rare) - MAX_REVISED_LISTED} more"] if len(rare) > MAX_REVISED_LISTED else []
        lines.append("")
    if routine:
        lines += [f"### Revised routinely: {len(routine)}", "",
                  ", ".join(f"{r['id']} ({r['n']})" for r in routine), ""]
    return lines
