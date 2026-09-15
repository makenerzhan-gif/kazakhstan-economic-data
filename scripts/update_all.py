#!/usr/bin/env python3
"""Orchestrator: run every agency updater, rebuild the unified dataset, refresh
metadata/project_knowledge, and stop the production dataset from updating if
anything failed (MASTER TASK section 11).

Steps: check sources -> download -> save raw -> validate schema/quality ->
process -> update unified dataset -> update metadata -> changelog -> run
tests -> (caller decides whether to git commit) -> update report.
"""
from __future__ import annotations

import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import pipeline_logging, unified  # noqa: E402
import update_bns, update_nbk, update_minfin, update_imf, update_ardfm, update_wb  # noqa: E402
import update_dims, update_derived  # noqa: E402
import build_project_knowledge  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    run_ts = datetime.now().isoformat()
    logger = pipeline_logging.RunLogger(run_timestamp=run_ts)

    # update_derived last: its scalar series are written from the item-level datasets
    for module in (update_bns, update_nbk, update_minfin, update_imf, update_ardfm, update_wb, update_dims, update_derived):
        module.run(logger)

    if logger.has_errors():
        print("update_all: one or more agency updates errored — NOT updating the unified "
              "dataset or committing. See logs/ for details.", file=sys.stderr)
        _write_report(run_ts, logger, unified_updated=False)
        return 1

    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    long_rows = unified.build_long(indicators)
    unified.write_long_csv(long_rows)
    fieldnames, wide_rows = unified.build_wide(long_rows)
    unified.write_wide_csv(fieldnames, wide_rows)
    update_dims.build_unified()   # item-level series: data/unified/macro_dims_long.csv

    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO_ROOT / "tests"), "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    print(test_result.stdout)
    if test_result.returncode != 0:
        print(test_result.stderr, file=sys.stderr)
        print("update_all: tests failed — production dataset changes will NOT be committed.",
              file=sys.stderr)
        _write_report(run_ts, logger, unified_updated=True, tests_passed=False)
        return 1

    # Refresh project_knowledge/ only once the data behind it is known-good --
    # this is the only folder synced into the Claude Project, so it should
    # never be left pointing at a run that failed validation or tests.
    build_project_knowledge.main()

    _write_report(run_ts, logger, unified_updated=True, tests_passed=True)
    print("update_all: completed successfully. Review changes and commit "
          "(this script does not push to GitHub itself outside of CI).")
    return 0


def _write_report(run_ts: str, logger: pipeline_logging.RunLogger, unified_updated: bool,
                   tests_passed: bool | None = None) -> None:
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date().isoformat()
    path = reports_dir / f"update_report_{today}.md"
    lines = [
        f"# Update report — {today}",
        "",
        f"Run timestamp: {run_ts}",
        f"Unified dataset updated: {unified_updated}",
        f"Tests passed: {tests_passed}",
        "",
        "## Per-dataset results",
        "",
    ]
    for e in logger.entries:
        lines.append(f"- **{e.source}/{e.dataset}** — {e.action}: {e.status} "
                      f"(downloaded={e.records_downloaded}, processed={e.records_processed})")
        for w in e.warnings:
            lines.append(f"  - warning: {w}")
        for err in e.errors:
            lines.append(f"  - ERROR: {err}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
