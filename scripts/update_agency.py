#!/usr/bin/env python3
"""Fast per-agency verification runner.

`update_all.py` re-fetches every indicator from all four agencies on every run,
which is correct for production but slow (the Minfin bulletin downloads alone
dominate the wall-clock). When a change only touches ONE agency's fetchers, this
script verifies that agency end-to-end in a fraction of the time:

    python scripts/update_agency.py nbk

It runs the named agency updater(s), then rebuilds the unified dataset and runs
the test suite exactly as update_all.py does. The unified rebuild is still
correct because it reads data/processed/, where the untouched agencies' CSVs
persist from the previous full run.

This is a VERIFICATION shortcut, not a replacement for update_all.py -- only a
full run refreshes every agency's data, so keep using update_all.py for
production/scheduled updates.
"""
from __future__ import annotations

import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import pipeline_logging, unified  # noqa: E402
import update_bns, update_nbk, update_minfin, update_imf  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

MODULES = {
    "bns": update_bns,
    "nbk": update_nbk,
    "minfin": update_minfin,
    "imf": update_imf,
}


def main(argv: list[str]) -> int:
    agencies = [a.lower() for a in argv]
    if not agencies:
        print(f"usage: update_agency.py <agency> [...]  (one or more of: {', '.join(MODULES)})",
              file=sys.stderr)
        return 2
    unknown = [a for a in agencies if a not in MODULES]
    if unknown:
        print(f"update_agency: unknown agency/agencies {unknown} — valid: {', '.join(MODULES)}",
              file=sys.stderr)
        return 2

    run_ts = datetime.now().isoformat()
    logger = pipeline_logging.RunLogger(run_timestamp=run_ts)

    for agency in agencies:
        MODULES[agency].run(logger)

    if logger.has_errors():
        print(f"update_agency: {agencies} errored — NOT rebuilding the unified dataset. "
              "See logs/ for details.", file=sys.stderr)
        return 1

    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    long_rows = unified.build_long(indicators)
    unified.write_long_csv(long_rows)
    fieldnames, wide_rows = unified.build_wide(long_rows)
    unified.write_wide_csv(fieldnames, wide_rows)

    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO_ROOT / "tests"), "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    print(test_result.stdout)
    if test_result.returncode != 0:
        print(test_result.stderr, file=sys.stderr)
        print("update_agency: tests failed.", file=sys.stderr)
        return 1

    statuses = {}
    for e in logger.entries:
        statuses[e.status] = statuses.get(e.status, 0) + 1
    print(f"update_agency: {agencies} completed — {statuses}. "
          "Run scripts/update_all.py before a production/scheduled update.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
