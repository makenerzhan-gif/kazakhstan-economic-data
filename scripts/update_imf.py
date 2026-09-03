#!/usr/bin/env python3
"""Update pipeline for IMF indicators (WEO). See update_bns.py for the design rationale."""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import periods, metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
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
    "IMF_GOV_REVENUE_RATIO": imf_fetchers.fetch_gov_revenue_ratio,
    "IMF_GOV_EXPENDITURE_RATIO": imf_fetchers.fetch_gov_expenditure_ratio,
    "IMF_EXPORT_VOLUME_GROWTH": imf_fetchers.fetch_export_volume_growth,
    "IMF_IMPORT_VOLUME_GROWTH": imf_fetchers.fetch_import_volume_growth,
    "IMF_CURRENT_ACCOUNT_USD": imf_fetchers.fetch_current_account_usd,
    "IMF_GDP_PER_CAPITA_PPP": imf_fetchers.fetch_gdp_per_capita_ppp,
    "IMF_GDP_WORLD_SHARE_PPP": imf_fetchers.fetch_gdp_world_share_ppp,
    "IMF_INFLATION_EOP": imf_fetchers.fetch_inflation_eop,
    "IMF_GOV_NET_DEBT_RATIO": imf_fetchers.fetch_gov_net_debt_ratio,
    "IMF_GDP_DEFLATOR_INDEX": imf_fetchers.fetch_nominal_gdp_deflator,
    "IMF_REAL_GDP": imf_fetchers.fetch_real_gdp_national_currency,
    "IMF_GOV_EXPENDITURE": imf_fetchers.fetch_gov_expenditure_level,
    "IMF_GOV_REVENUE": imf_fetchers.fetch_gov_revenue_level,
    "IMF_CPI_INDEX": imf_fetchers.fetch_cpi_index,
    "IMF_GOV_BALANCE_LEVEL": imf_fetchers.fetch_gov_balance_level,
    "IMF_PPP_EXCHANGE_RATE": imf_fetchers.fetch_ppp_exchange_rate,
    "IMF_STRUCTURAL_BALANCE": imf_fetchers.fetch_structural_balance,
    "IMF_CPI_EOP_INDEX": imf_fetchers.fetch_cpi_eop_index,
    "IMF_GDP_PER_CAPITA_NATIONAL": imf_fetchers.fetch_gdp_per_capita_national_currency,
    "OIL_PRICE": imf_fetchers.fetch_oil_price,
    "COMMODITY_TERMS_OF_TRADE": imf_fetchers.fetch_commodity_terms_of_trade,
    "COMMODITY_TERMS_OF_TRADE_FIXED_WEIGHTS": imf_fetchers.fetch_commodity_terms_of_trade_fixed_weights,
}

INDICATOR_IDS = [
    "IMF_GDP_GROWTH", "IMF_INFLATION", "IMF_CURRENT_ACCOUNT",
    "IMF_UNEMPLOYMENT", "IMF_GOV_BALANCE", "IMF_GOV_DEBT",
    "IMF_POPULATION", "IMF_NOMINAL_GDP", "IMF_NOMINAL_GDP_USD",
    "IMF_GDP_PPP", "IMF_INVESTMENT_RATIO", "IMF_SAVINGS_RATIO",
    "IMF_GOV_REVENUE_RATIO", "IMF_GOV_EXPENDITURE_RATIO",
    "IMF_EXPORT_VOLUME_GROWTH", "IMF_IMPORT_VOLUME_GROWTH", "IMF_CURRENT_ACCOUNT_USD",
    "IMF_GDP_PER_CAPITA_PPP", "IMF_GDP_WORLD_SHARE_PPP", "IMF_INFLATION_EOP",
    "IMF_GOV_NET_DEBT_RATIO", "IMF_GDP_DEFLATOR_INDEX", "IMF_REAL_GDP",
    "IMF_GOV_EXPENDITURE", "IMF_GOV_REVENUE", "IMF_CPI_INDEX",
    "IMF_GOV_BALANCE_LEVEL", "IMF_PPP_EXCHANGE_RATE", "IMF_STRUCTURAL_BALANCE",
    "IMF_CPI_EOP_INDEX", "IMF_GDP_PER_CAPITA_NATIONAL",
    "OIL_PRICE",
    "COMMODITY_TERMS_OF_TRADE",
    "COMMODITY_TERMS_OF_TRADE_FIXED_WEIGHTS",
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

        # Normalise BEFORE validating, so the validator judges what will actually
        # be stored. Validating first made validate_period_convention warn about
        # dates the very next step was about to fix -- 24 false warnings on the
        # first run after the convention change. write_processed still
        # normalises as a backstop for any other caller.
        _meta = _indicator_meta(indicator_id)
        records = periods.normalise(
            records, manifest_info.get("frequency") or _meta["frequency"],
            _meta.get("observation_type"))
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
        processed_store.write_processed(
            AGENCY, indicator_id, records, transformation=transformation,
            frequency=manifest_info.get("frequency") or _indicator_meta(indicator_id)["frequency"])

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
