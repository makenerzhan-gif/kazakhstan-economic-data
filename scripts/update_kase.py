#!/usr/bin/env python3
"""Update pipeline for the Kazakhstan Stock Exchange (KASE) indicators: TONIA, the
government securities zero-coupon yield curve and the sovereign Eurobond yield/spread
(scripts/fetchers/kase_eurobonds.py). See update_bns.py for the design
rationale and scripts/fetchers/kase.py for the two sources."""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import periods, metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
from fetchers import kase as kase_fetchers, kase_eurobonds  # noqa: E402

AGENCY = "kase"
REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "TONIA": kase_fetchers.fetch_tonia,
    "GS_YIELD_3M": kase_fetchers.fetch_gs_yield_3m,
    "GS_YIELD_6M": kase_fetchers.fetch_gs_yield_6m,
    "GS_YIELD_1Y": kase_fetchers.fetch_gs_yield_1y,
    "GS_YIELD_2Y": kase_fetchers.fetch_gs_yield_2y,
    "GS_YIELD_5Y": kase_fetchers.fetch_gs_yield_5y,
    "GS_YIELD_10Y": kase_fetchers.fetch_gs_yield_10y,
    "KZ_EUROBOND_YIELD": kase_eurobonds.fetch_kz_eurobond_yield,
    "KZ_EUROBOND_SPREAD": kase_eurobonds.fetch_kz_eurobond_spread,
}
INDICATOR_IDS = list(FETCHERS)


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
        try:
            records, manifest_info = FETCHERS[indicator_id]()
        except validation.StructuralChangeError as exc:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=AGENCY, dataset=indicator_id,
                action="fetch", status="structural_change", errors=[str(exc)]))
            continue
        except Exception as exc:  # noqa: BLE001
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=AGENCY, dataset=indicator_id,
                action="fetch", status="error", errors=[str(exc)]))
            continue

        ind = _indicator_meta(indicator_id)
        records = periods.normalise(records, manifest_info.get("frequency") or ind["frequency"], ind.get("observation_type"))
        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", ind["frequency"]))
        warnings = list(manifest_info.get("warnings", [])) + result.warnings
        if not result.ok:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=AGENCY, dataset=indicator_id,
                action="validate", status="error", errors=result.errors, warnings=warnings))
            continue

        revs = revisions.detect_revisions(indicator_id, AGENCY, _load_old_processed(indicator_id), records, today)
        if revs:
            revisions.append_revisions(revs)
        processed_store.write_processed(AGENCY, indicator_id, records, transformation="level",
                                        frequency=manifest_info.get("frequency") or ind["frequency"])
        metadata.DatasetMetadata(
            source=AGENCY,
            source_url=manifest_info.get("source_url", ""),
            dataset_id=manifest_info.get("dataset_id", ""),
            indicator_id=indicator_id,
            indicator_name=ind["name_en"],
            description=ind["name_ru"],
            frequency=manifest_info.get("frequency", ind["frequency"]),
            unit=ind["unit"],
            currency="",
            geography="Kazakhstan (national)",
            methodology=manifest_info.get("note", "Kazakhstan Stock Exchange (KASE)"),
            publication_date=manifest_info.get("release"),
            last_update_date=today.isoformat(),
            download_date=today.isoformat(),
            period_start=records[0]["date"] if records else None,
            period_end=records[-1]["date"] if records else None,
            next_update_date=None,
            transformation="level",
            revision_status="revised" if revs else "original",
        ).write()
        run_logger.log(pipeline_logging.LogEntry(
            timestamp=datetime.now().isoformat(), source=AGENCY, dataset=indicator_id,
            action="fetch+validate+process", status="ok",
            records_downloaded=len(records), records_processed=len(records), warnings=warnings))


if __name__ == "__main__":
    logger = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    run(logger)
    if logger.has_errors():
        sys.exit(1)
