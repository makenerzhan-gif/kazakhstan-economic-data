#!/usr/bin/env python3
"""Update pipeline for Ministry of Finance RK (Minfin) indicators.
See update_bns.py for the design rationale (fetchers only added once confirmed).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import raw_store, metadata, validation, pipeline_logging  # noqa: E402

AGENCY = "minfin"
FETCHERS: dict[str, callable] = {}
INDICATOR_IDS = ["GOV_REVENUE", "GOV_EXPENDITURE", "GOV_DEBT"]


def run(run_logger: pipeline_logging.RunLogger) -> None:
    for indicator_id in INDICATOR_IDS:
        fetch = FETCHERS.get(indicator_id)
        if fetch is None:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(),
                source=AGENCY, dataset=indicator_id, action="fetch", status="skipped",
                warnings=["No confirmed source yet for this indicator. Run the source-research step first."],
            ))
            continue
        try:
            records, manifest_info = fetch()
        except Exception as exc:  # noqa: BLE001
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(),
                source=AGENCY, dataset=indicator_id, action="fetch", status="error", errors=[str(exc)],
            ))
            continue
        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", "monthly"))
        status = "ok" if result.ok else "error"
        run_logger.log(pipeline_logging.LogEntry(
            timestamp=datetime.now().isoformat(),
            source=AGENCY, dataset=indicator_id, action="fetch+validate", status=status,
            records_downloaded=len(records), errors=result.errors, warnings=result.warnings,
        ))


if __name__ == "__main__":
    logger = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    run(logger)
    if logger.has_errors():
        sys.exit(1)
