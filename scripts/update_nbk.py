#!/usr/bin/env python3
"""Update pipeline for National Bank of Kazakhstan (NBK) indicators.
See update_bns.py for the design rationale (fetchers only added once confirmed).
"""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
from fetchers import nbk as nbk_fetchers  # noqa: E402

AGENCY = "nbk"
REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "BASE_RATE": nbk_fetchers.fetch_base_rate,
    "EXCHANGE_RATE": nbk_fetchers.fetch_exchange_rate_usd,
    "M2": nbk_fetchers.fetch_m2,
    "M3": nbk_fetchers.fetch_m3,
    "MONETARY_BASE": nbk_fetchers.fetch_monetary_base,
    "M0": nbk_fetchers.fetch_m0,
    "M1": nbk_fetchers.fetch_m1,
    "FX_RESERVES": nbk_fetchers.fetch_fx_reserves,
    "NATIONAL_FUND_ASSETS": nbk_fetchers.fetch_national_fund_assets,
    "REER": nbk_fetchers.fetch_reer,
    "NEER": nbk_fetchers.fetch_neer,
    "DEPOSITS_TOTAL": nbk_fetchers.fetch_deposits_total,
    "EXTERNAL_DEBT": nbk_fetchers.fetch_external_debt,
    "LENDING_RATE": nbk_fetchers.fetch_lending_rate,
    "DEPOSIT_RATE": nbk_fetchers.fetch_deposit_rate,
}

INDICATOR_IDS = [
    "BASE_RATE", "EXCHANGE_RATE", "M2", "M3", "MONETARY_BASE", "M0", "M1",
    "FX_RESERVES", "NATIONAL_FUND_ASSETS", "REER", "NEER", "DEPOSITS_TOTAL",
    "EXTERNAL_DEBT", "LENDING_RATE", "DEPOSIT_RATE",
]


def _indicator_meta(indicator_id: str) -> dict:
    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    return next(i for i in indicators if i["id"] == indicator_id)


def _load_old_processed(indicator_id: str) -> list[dict]:
    path = REPO_ROOT / "data" / "processed" / AGENCY / f"{indicator_id.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(run_logger: pipeline_logging.RunLogger) -> None:
    today = date.today()
    for indicator_id in INDICATOR_IDS:
        fetch = FETCHERS.get(indicator_id)
        if fetch is None:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(),
                source=AGENCY, dataset=indicator_id, action="fetch", status="skipped",
                warnings=["No confirmed source yet for this indicator (see config/sources.yaml "
                          "agencies.nbk.endpoints). Run/extend the source-research step before enabling."],
            ))
            continue

        try:
            records, manifest_info = fetch()
        except validation.StructuralChangeError as exc:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(),
                source=AGENCY, dataset=indicator_id, action="fetch", status="structural_change",
                errors=[str(exc)],
            ))
            continue
        except Exception as exc:  # noqa: BLE001
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(),
                source=AGENCY, dataset=indicator_id, action="fetch", status="error", errors=[str(exc)],
            ))
            continue

        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", "daily"))
        if not result.ok:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(),
                source=AGENCY, dataset=indicator_id, action="validate", status="error",
                errors=result.errors, warnings=result.warnings,
            ))
            continue

        old_records = _load_old_processed(indicator_id)
        revs = revisions.detect_revisions(indicator_id, AGENCY, old_records, records, today)
        if revs:
            revisions.append_revisions(revs)

        transformation = manifest_info.get("transformation", "level")
        processed_store.write_processed(AGENCY, indicator_id, records, transformation=transformation)

        ind = _indicator_meta(indicator_id)
        metadata.DatasetMetadata(
            source=AGENCY,
            source_url=manifest_info.get("source_url", ""),
            dataset_id=manifest_info.get("dataset_id", ""),
            indicator_id=indicator_id,
            indicator_name=ind["name_en"],
            description=ind["name_ru"],
            frequency=manifest_info.get("frequency", ind["frequency"]),
            unit=ind["unit"],
            currency="KZT" if "KZT" in ind["unit"] else "",
            geography="Kazakhstan (national)",
            methodology=manifest_info.get("note", "National Bank of Kazakhstan official methodology"),
            publication_date=None,
            last_update_date=today.isoformat(),
            download_date=today.isoformat(),
            period_start=records[0]["date"] if records else None,
            period_end=records[-1]["date"] if records else None,
            next_update_date=None,
            transformation=transformation,
            revision_status="revised" if revs else "original",
        ).write()

        run_logger.log(pipeline_logging.LogEntry(
            timestamp=datetime.now().isoformat(),
            source=AGENCY, dataset=indicator_id, action="fetch+validate+process", status="ok",
            records_downloaded=len(records), records_processed=len(records), warnings=result.warnings,
        ))


if __name__ == "__main__":
    logger = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    run(logger)
    if logger.has_errors():
        sys.exit(1)
