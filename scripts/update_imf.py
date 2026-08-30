#!/usr/bin/env python3
"""Update pipeline for IMF indicators (WEO). See update_bns.py for the design rationale."""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
from fetchers import imf as imf_fetchers  # noqa: E402

AGENCY = "imf"
REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "IMF_GDP_GROWTH": imf_fetchers.fetch_gdp_growth,
    "IMF_INFLATION": imf_fetchers.fetch_inflation,
    "IMF_CURRENT_ACCOUNT": imf_fetchers.fetch_current_account,
    "IMF_UNEMPLOYMENT": imf_fetchers.fetch_unemployment,
    "IMF_GOV_BALANCE": imf_fetchers.fetch_gov_balance,
    "IMF_GOV_DEBT": imf_fetchers.fetch_gov_debt,
    "IMF_POPULATION": imf_fetchers.fetch_population,
    "IMF_NOMINAL_GDP": imf_fetchers.fetch_nominal_gdp,
    "IMF_NOMINAL_GDP_USD": imf_fetchers.fetch_nominal_gdp_usd,
    "IMF_GDP_PPP": imf_fetchers.fetch_gdp_ppp,
    "IMF_INVESTMENT_RATIO": imf_fetchers.fetch_investment_ratio,
    "IMF_SAVINGS_RATIO": imf_fetchers.fetch_savings_ratio,
}

INDICATOR_IDS = [
    "IMF_GDP_GROWTH", "IMF_INFLATION", "IMF_CURRENT_ACCOUNT",
    "IMF_UNEMPLOYMENT", "IMF_GOV_BALANCE", "IMF_GOV_DEBT",
    "IMF_POPULATION", "IMF_NOMINAL_GDP", "IMF_NOMINAL_GDP_USD",
    "IMF_GDP_PPP", "IMF_INVESTMENT_RATIO", "IMF_SAVINGS_RATIO",
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
                warnings=["No confirmed source yet for this indicator. Run the source-research step first."],
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

        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", "annual"))
        status = "ok" if result.ok else "error"
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
            currency="",
            geography="Kazakhstan (national)",
            methodology="IMF World Economic Outlook (WEO), biannual exercise (April/October vintages)",
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
