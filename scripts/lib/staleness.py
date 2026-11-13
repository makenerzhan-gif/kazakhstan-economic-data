"""Series whose newest observation is older than their frequency allows (added 2026-11-13).

A run reports a dataset `ok` when the source answered and the file parsed -- also when the
source has simply stopped adding observations (a form frozen since 2024, a report filed
under a new heading). On 2026-11-13 thirty of 561 scalar series were in that state and
nothing in the report said so. This check compares each series' last date with today:

    daily      20 days        monthly    150 days
    quarterly  330 days       annual     700 days

The limits leave room for ordinary publication lags (annual national accounts arrive up to
a year and a half after the year ends) -- a series past them needs a look, not a fix by
default. Projections are skipped. An indicator whose stop is understood stays in the report
but in a separate, quiet list (`known`), so it is not forgotten and does not raise the warning:
  * `lifecycle:` (superseded / superseded_not_spliceable / stale_source, with its note) -- the
    series is finished, config/indicators.yaml names the replacement;
  * `stale_ok: "<reason>"` -- the source is late or paused and nothing in the fetcher is wrong
    (Minfin has posted no National Fund statement since 1 July 2026). Remove the key when the
    source resumes: a second stop should be noticed again.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIMIT_DAYS = {"daily": 20, "monthly": 150, "quarterly": 330, "annual": 700}
SKIP_CATEGORIES = {"international_projection"}


def last_date(path: Path) -> date | None:
    if not path.exists():
        return None
    last = None
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("value") not in (None, "") and (last is None or row["date"] > last):
                last = row["date"]
    return date.fromisoformat(last[:10]) if last else None


def stale_series(indicators: list[dict], today: date | None = None, processed_root: Path | None = None) -> list[dict]:
    """[{id, agency, frequency, last, days}] for the scalar indicators past their limit, oldest first."""
    today = today or date.today()
    root = processed_root or REPO_ROOT / "data" / "processed"
    out = []
    for ind in indicators:
        limit = LIMIT_DAYS.get(ind.get("frequency"))
        if limit is None or ind.get("category") in SKIP_CATEGORIES:
            continue
        last = last_date(root / ind["agency"] / f"{ind['id'].lower()}.csv")
        if last is not None and (today - last).days > limit:
            known = ind.get("stale_ok") or (f"{ind['lifecycle']}" + (f", see {ind['superseded_by']}" if ind.get("superseded_by") else "")
                                            if ind.get("lifecycle") else None)
            out.append({"id": ind["id"], "agency": ind["agency"], "frequency": ind["frequency"],
                        "last": last.isoformat(), "days": (today - last).days, "known": known})
    return sorted(out, key=lambda r: r["last"])


def unexplained(stale: list[dict]) -> list[dict]:
    return [r for r in stale if not r.get("known")]


def report_lines(stale: list[dict]) -> list[str]:
    new, known = unexplained(stale), [r for r in stale if r.get("known")]
    lines = []
    if new:
        lines += ["## Series with no new observations for longer than their frequency allows", "",
                  "The source answered, but its newest observation is old: it may have stopped publishing, moved, or "
                  "the fetcher reads a superseded document. Fix the fetcher, or say why in config/indicators.yaml "
                  "(`stale_ok: \"reason\"`, or a `lifecycle`; scripts/lib/staleness.py).", ""]
        lines += [f"- **{r['agency']}/{r['id']}** ({r['frequency']}): last observation {r['last']}, {r['days']} days ago" for r in new]
        lines.append("")
    if known:
        lines += ["## Stopped series with a known reason", ""]
        lines += [f"- {r['agency']}/{r['id']}: last {r['last']} — {' '.join(str(r['known']).split())[:220]}" for r in known]
        lines.append("")
    return lines
