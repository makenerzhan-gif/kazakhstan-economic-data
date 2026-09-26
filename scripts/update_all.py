#!/usr/bin/env python3
"""Orchestrator: run every agency updater, rebuild the unified dataset, refresh
metadata/project_knowledge, and stop the production dataset from updating if
the run is broken as a whole (MASTER TASK section 11).

A FAILED DATASET DOES NOT BLOCK THE OTHERS (2026-09-26). Until then one error
anywhere -- a changed BNS file format on 2026-09-25, an IMF API reset -- stopped
the unified rebuild and the commit, so ~660 healthy series went un-updated for a
day over one broken one. Every updater logs `error` BEFORE it writes anything, so
a failed dataset keeps its previous processed file and the unified dataset keeps
its previous values; the failure is listed at the top of the update report and
raised as a GitHub Actions warning. The run still stops when more than
MAX_FAILED_SHARE of the datasets fail: that is an outage or a bug in shared code,
not one source changing.

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
import update_bns, update_nbk, update_minfin, update_imf, update_ardfm, update_wb, update_kase, update_foreign  # noqa: E402
import update_dims, update_derived  # noqa: E402
import build_project_knowledge, build_calendar  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_FAILED_SHARE = 0.20


def failure_gate(entries: list) -> tuple[bool, list]:
    """(proceed, failed entries): proceed unless more than MAX_FAILED_SHARE of the
    datasets attempted this run ended in `error`."""
    failed = [e for e in entries if e.status == "error"]
    attempted = {(e.source, e.dataset) for e in entries}
    return len(failed) <= MAX_FAILED_SHARE * max(len(attempted), 1), failed


def announce_failures(failed: list) -> None:
    """One GitHub Actions warning per failed dataset (plain text outside Actions), and the
    list in the job summary when the runner provides one."""
    import os
    for e in failed:
        first = (e.errors[0].splitlines()[0] if e.errors else "")[:300]
        print(f"::warning title=Dataset failed, previous data kept::{e.source}/{e.dataset}: {first}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and failed:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Datasets that failed this run (previous data kept)\n\n")
            for e in failed:
                f.write(f"- `{e.source}/{e.dataset}`: {(e.errors[0].splitlines()[0] if e.errors else '')[:300]}\n")


def main() -> int:
    run_ts = datetime.now().isoformat()
    logger = pipeline_logging.RunLogger(run_timestamp=run_ts)

    # update_derived last: its scalar series are written from the item-level datasets
    for module in (update_bns, update_nbk, update_minfin, update_imf, update_ardfm, update_wb, update_kase, update_foreign, update_dims, update_derived):
        module.run(logger)

    proceed, failed = failure_gate(logger.entries)
    if not proceed:
        print(f"update_all: {len(failed)} dataset updates errored, more than {MAX_FAILED_SHARE:.0%} of "
              "the run -- an outage or a shared-code bug, not one source. NOT updating the unified "
              "dataset or committing. See logs/ for details.", file=sys.stderr)
        _write_report(run_ts, logger, unified_updated=False)
        return 1
    if failed:
        print(f"update_all: {len(failed)} dataset(s) failed and keep their previous data; "
              "continuing with the rest.", file=sys.stderr)
        announce_failures(failed)

    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    long_rows = unified.build_long(indicators)
    unified.write_long_csv(long_rows)
    fieldnames, wide_rows = unified.build_wide(long_rows)
    unified.write_wide_csv(fieldnames, wide_rows)
    update_dims.build_unified()   # item-level series: data/unified/macro_dims_long.csv.gz

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
    build_calendar.main()          # project_knowledge/CALENDAR.md: what the model's sources update next

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
    ]
    failed = [e for e in logger.entries if e.status == "error"]
    if failed:
        lines += ["## Failed this run — previous data kept", ""]
        lines += [f"- **{e.source}/{e.dataset}**: {(e.errors[0].splitlines()[0] if e.errors else '')[:300]}"
                  for e in failed]
        lines.append("")
    lines += ["## Per-dataset results", ""]
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
