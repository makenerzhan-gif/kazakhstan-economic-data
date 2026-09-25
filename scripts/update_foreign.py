#!/usr/bin/env python3
"""Update pipeline for the external block of the QPM/BVAR models: Russia (Bank of Russia,
Eurasian Economic Commission, IMF QNEA) and the United States (FRED). One updater for
several agencies -- each indicator's own `agency` names its raw/processed/metadata folder.
See scripts/fetchers/foreign.py for the sources and update_bns.py for the design."""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import periods, metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
from fetchers import foreign as foreign_fetchers  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "RU_KEY_RATE": foreign_fetchers.fetch_ru_key_rate,
    "RUB_USD": foreign_fetchers.fetch_rub_usd,
    "RU_CPI_MOM": foreign_fetchers.fetch_ru_cpi_mom,
    "RU_CPI_YOY": foreign_fetchers.fetch_ru_cpi_yoy,
    "RU_GDP_REAL": foreign_fetchers.fetch_ru_gdp_real,
    "US_FED_FUNDS": foreign_fetchers.fetch_us_fed_funds,
    "US_TREASURY_2Y": foreign_fetchers.fetch_us_treasury_2y,
    "US_TREASURY_10Y": foreign_fetchers.fetch_us_treasury_10y,
    "US_CPI": foreign_fetchers.fetch_us_cpi,
    "US_GDP_REAL": foreign_fetchers.fetch_us_gdp_real,
    "BY_CPI_YOY": foreign_fetchers.fetch_by_cpi_yoy,
    "KG_CPI_YOY": foreign_fetchers.fetch_kg_cpi_yoy,
    "CN_CPI_YOY": foreign_fetchers.fetch_cn_cpi_yoy,
    "CN_GDP_REAL_YOY": foreign_fetchers.fetch_cn_gdp_real_yoy,
    "EA_HICP_YOY": foreign_fetchers.fetch_ea_hicp_yoy,
    "EA_GDP_REAL": foreign_fetchers.fetch_ea_gdp_real,
    "EA_DEPOSIT_RATE": foreign_fetchers.fetch_ea_deposit_rate,
    # Last: built from the partner series written above.
    "FOREIGN_DEMAND_YOY": foreign_fetchers.fetch_foreign_demand_yoy,
}
INDICATOR_IDS = list(FETCHERS)


def _indicator_meta(indicator_id: str) -> dict:
    indicators = yaml.safe_load((REPO_ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))["indicators"]
    return next(i for i in indicators if i["id"] == indicator_id)


def _load_old_processed(agency: str, indicator_id: str) -> list[dict]:
    path = REPO_ROOT / "data" / "processed" / agency / f"{indicator_id.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(run_logger: pipeline_logging.RunLogger) -> None:
    today = date.today()
    for indicator_id in INDICATOR_IDS:
        agency = _indicator_meta(indicator_id)["agency"]
        try:
            records, manifest_info = FETCHERS[indicator_id]()
        except validation.StructuralChangeError as exc:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                action="fetch", status="structural_change", errors=[str(exc)]))
            continue
        except Exception as exc:  # noqa: BLE001
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                action="fetch", status="error", errors=[str(exc)]))
            continue

        ind = _indicator_meta(indicator_id)
        records = periods.normalise(records, manifest_info.get("frequency") or ind["frequency"], ind.get("observation_type"))
        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", ind["frequency"]))
        warnings = list(manifest_info.get("warnings", [])) + result.warnings
        if not result.ok:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                action="validate", status="error", errors=result.errors, warnings=warnings))
            continue

        revs = revisions.detect_revisions(indicator_id, agency, _load_old_processed(agency, indicator_id), records, today)
        if revs:
            revisions.append_revisions(revs)
        processed_store.write_processed(agency, indicator_id, records, transformation="level",
                                        frequency=manifest_info.get("frequency") or ind["frequency"])
        metadata.DatasetMetadata(
            source=agency,
            source_url=manifest_info.get("source_url", ""),
            dataset_id=manifest_info.get("dataset_id", ""),
            indicator_id=indicator_id,
            indicator_name=ind["name_en"],
            description=ind["name_ru"],
            frequency=manifest_info.get("frequency", ind["frequency"]),
            unit=ind["unit"],
            currency="",
            geography={"RUS": "Russian Federation", "USA": "United States", "BLR": "Belarus", "KGZ": "Kyrgyzstan", "CHN": "China", "EA": "Euro area", "KZ": "Kazakhstan (trade-weighted partners)"}.get(ind.get("country"), ind.get("country", "")),
            methodology=manifest_info.get("note", "see scripts/fetchers/foreign.py"),
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
            timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
            action="fetch+validate+process", status="ok",
            records_downloaded=len(records), records_processed=len(records), warnings=warnings))


if __name__ == "__main__":
    logger = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    run(logger)
    if logger.has_errors():
        sys.exit(1)
