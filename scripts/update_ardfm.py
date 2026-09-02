#!/usr/bin/env python3
"""Update pipeline for ARDFM (financial market regulator) indicators.

Fifth agency, added to replace the banking block frozen at 2024-04-01 --
see scripts/fetchers/ardfm.py for why NBK could not supply it. Same shape
as update_imf.py; see update_bns.py for the design rationale."""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
from fetchers import ardfm as ardfm_fetchers  # noqa: E402

AGENCY = "ardfm"
REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "BANK_NPL_90_SHARE": ardfm_fetchers.fetch_bank_npl_90_share,
    "BANK_NPL_90_AMOUNT": ardfm_fetchers.fetch_bank_npl_90_amount,
    "BANK_LOANS_TOTAL": ardfm_fetchers.fetch_bank_loans_total,
    "BANK_PROVISIONS_IFRS": ardfm_fetchers.fetch_bank_provisions_ifrs,
    "BANK_CAPITAL_ADEQUACY_K1": ardfm_fetchers.fetch_bank_capital_adequacy_k1,
    "BANK_CAPITAL_ADEQUACY_K2": ardfm_fetchers.fetch_bank_capital_adequacy_k2,
    "BANK_ROA_MONTHLY": ardfm_fetchers.fetch_bank_roa_monthly,
    "BANK_ROE_MONTHLY": ardfm_fetchers.fetch_bank_roe_monthly,
    "BANK_NET_INCOME": ardfm_fetchers.fetch_bank_net_income,
    "BANK_ASSETS_TOTAL": ardfm_fetchers.fetch_bank_assets_total,
    "BANK_ASSETS_GROSS": ardfm_fetchers.fetch_bank_assets_gross,
    "BANK_LIABILITIES_TOTAL": ardfm_fetchers.fetch_bank_liabilities_total,
    "BANK_CLIENT_DEPOSITS": ardfm_fetchers.fetch_bank_client_deposits,
    "BANK_DEPOSITS_LEGAL_ENTITIES": ardfm_fetchers.fetch_bank_deposits_legal_entities,
    "BANK_DEPOSITS_INDIVIDUALS": ardfm_fetchers.fetch_bank_deposits_individuals,
    "BANK_DEPOSITS_INDIVIDUALS_FX_SHARE": ardfm_fetchers.fetch_bank_deposits_individuals_fx_share,
    "BANK_LIQUID_ASSETS": ardfm_fetchers.fetch_bank_liquid_assets,
    "BANK_ASSETS_TO_GDP": ardfm_fetchers.fetch_bank_assets_to_gdp,
    "BANK_LOANS_TO_GDP": ardfm_fetchers.fetch_bank_loans_to_gdp,
    "BANK_DEPOSITS_TO_GDP": ardfm_fetchers.fetch_bank_deposits_to_gdp,
    "BANK_LOANS_CORPORATE": ardfm_fetchers.fetch_bank_loans_corporate,
    "BANK_NPL_90_CORPORATE_SHARE": ardfm_fetchers.fetch_bank_npl_90_corporate_share,
    "BANK_LOANS_RETAIL": ardfm_fetchers.fetch_bank_loans_retail,
    "BANK_NPL_90_RETAIL_SHARE": ardfm_fetchers.fetch_bank_npl_90_retail_share,
    "BANK_LOANS_SME": ardfm_fetchers.fetch_bank_loans_sme,
    "BANK_NPL_90_SME_SHARE": ardfm_fetchers.fetch_bank_npl_90_sme_share,
    "BANK_SHARE_CAPITAL": ardfm_fetchers.fetch_bank_share_capital,
    "BANK_TOP5_ASSETS_SHARE": ardfm_fetchers.fetch_bank_top5_assets_share,
    "BANK_TOP5_LOANS_SHARE": ardfm_fetchers.fetch_bank_top5_loans_share,
    "BANK_TOP5_DEPOSITS_SHARE": ardfm_fetchers.fetch_bank_top5_deposits_share,
}

INDICATOR_IDS = [
    "BANK_NPL_90_SHARE", "BANK_NPL_90_AMOUNT", "BANK_LOANS_TOTAL",
    "BANK_PROVISIONS_IFRS", "BANK_CAPITAL_ADEQUACY_K1", "BANK_CAPITAL_ADEQUACY_K2",
    "BANK_ROA_MONTHLY", "BANK_ROE_MONTHLY", "BANK_NET_INCOME",
    "BANK_ASSETS_TOTAL",
    "BANK_ASSETS_GROSS",
    "BANK_LIABILITIES_TOTAL",
    "BANK_CLIENT_DEPOSITS",
    "BANK_DEPOSITS_LEGAL_ENTITIES",
    "BANK_DEPOSITS_INDIVIDUALS",
    "BANK_DEPOSITS_INDIVIDUALS_FX_SHARE",
    "BANK_LIQUID_ASSETS",
    "BANK_ASSETS_TO_GDP",
    "BANK_LOANS_TO_GDP",
    "BANK_DEPOSITS_TO_GDP",
    "BANK_LOANS_CORPORATE",
    "BANK_NPL_90_CORPORATE_SHARE",
    "BANK_LOANS_RETAIL",
    "BANK_NPL_90_RETAIL_SHARE",
    "BANK_LOANS_SME",
    "BANK_NPL_90_SME_SHARE",
    "BANK_SHARE_CAPITAL",
    "BANK_TOP5_ASSETS_SHARE",
    "BANK_TOP5_LOANS_SHARE",
    "BANK_TOP5_DEPOSITS_SHARE",
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

        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", "monthly"))
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
            unit=manifest_info.get("unit", ind["unit"]),
            currency="",
            geography="Kazakhstan (national)",
            methodology="ARDFM monthly banking sector bulletin (PDF), tables 4, 12 and 14",
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
