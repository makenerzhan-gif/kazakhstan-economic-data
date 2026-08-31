#!/usr/bin/env python3
"""Update pipeline for Ministry of Finance RK (Minfin) indicators.
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
from fetchers import minfin as minfin_fetchers  # noqa: E402

AGENCY = "minfin"
REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "GOV_REVENUE": minfin_fetchers.fetch_gov_revenue,
    "GOV_EXPENDITURE": minfin_fetchers.fetch_gov_expenditure,
    "GOV_DEBT": minfin_fetchers.fetch_gov_debt,
    "GOV_HEALTH_SPENDING": minfin_fetchers.fetch_gov_health_spending,
    "GOV_EDUCATION_SPENDING": minfin_fetchers.fetch_gov_education_spending,
    "GOV_SOCIAL_SPENDING": minfin_fetchers.fetch_gov_social_spending,
    "TAX_REVENUE": minfin_fetchers.fetch_tax_revenue,
    "CORPORATE_TAX": minfin_fetchers.fetch_corporate_tax,
    "VAT_REVENUE": minfin_fetchers.fetch_vat_revenue,
    "GOV_DEFENSE_SPENDING": minfin_fetchers.fetch_gov_defense_spending,
    "GOV_GENERAL_SERVICES_SPENDING": minfin_fetchers.fetch_gov_general_services_spending,
    "GOV_TRANSPORT_SPENDING": minfin_fetchers.fetch_gov_transport_spending,
    "GOV_DEBT_SERVICING": minfin_fetchers.fetch_gov_debt_servicing,
    "NET_BUDGET_LENDING": minfin_fetchers.fetch_net_budget_lending,
    "BUDGET_DEFICIT": minfin_fetchers.fetch_budget_deficit,
    "NON_OIL_BUDGET_DEFICIT": minfin_fetchers.fetch_non_oil_budget_deficit,
    "EXCISE_TAX_REVENUE": minfin_fetchers.fetch_excise_tax_revenue,
    "GOV_DEBT_DOMESTIC": minfin_fetchers.fetch_gov_debt_domestic,
    "GOV_DEBT_EXTERNAL": minfin_fetchers.fetch_gov_debt_external,
    "GG_TAXES": minfin_fetchers.fetch_gg_taxes,
    "GG_SOCIAL_CONTRIBUTIONS": minfin_fetchers.fetch_gg_social_contributions,
    "GG_CASH_SURPLUS_DEFICIT": minfin_fetchers.fetch_gg_cash_surplus_deficit,
    "CUSTOMS_DUTIES": minfin_fetchers.fetch_customs_duties,
    "GOV_WAGES_EXPENDITURE": minfin_fetchers.fetch_gov_wages_expenditure,
    "GOV_CAPITAL_EXPENDITURE": minfin_fetchers.fetch_gov_capital_expenditure,
    "GOV_PENSIONS_EXPENDITURE": minfin_fetchers.fetch_gov_pensions_expenditure,
    "GOV_SUBSIDIES_EXPENDITURE": minfin_fetchers.fetch_gov_subsidies_expenditure,
    "SUBVENTIONS_REPUBLICAN": minfin_fetchers.fetch_subventions_republican,
    "LOCAL_GOV_WAGES_EXPENDITURE": minfin_fetchers.fetch_local_gov_wages_expenditure,
    "LOCAL_GOV_CAPITAL_EXPENDITURE": minfin_fetchers.fetch_local_gov_capital_expenditure,
    "LOCAL_GOV_SUBSIDIES_EXPENDITURE": minfin_fetchers.fetch_local_gov_subsidies_expenditure,
    "NATIONAL_FUND_STABILIZATION_PORTFOLIO": minfin_fetchers.fetch_national_fund_stabilization_portfolio,
    "NATIONAL_FUND_SAVINGS_PORTFOLIO": minfin_fetchers.fetch_national_fund_savings_portfolio,
    "NATIONAL_FUND_SAVINGS_BONDS": minfin_fetchers.fetch_national_fund_savings_bonds,
    "NATIONAL_FUND_EQUITIES": minfin_fetchers.fetch_national_fund_equities,
    "NATIONAL_FUND_GOLD": minfin_fetchers.fetch_national_fund_gold,
    "GOV_ACCOUNTS_PAYABLE": minfin_fetchers.fetch_gov_accounts_payable,
    "GOV_ACCOUNTS_RECEIVABLE": minfin_fetchers.fetch_gov_accounts_receivable,
    "GOV_FINANCIAL_ASSETS_SOLD": minfin_fetchers.fetch_gov_financial_assets_sold,
    "GOV_AUDIT_VIOLATIONS_AMOUNT": minfin_fetchers.fetch_gov_audit_violations_amount,
    "TAX_ARREARS_TOTAL": minfin_fetchers.fetch_tax_arrears_total,
    "PENSION_CONTRIBUTIONS_RECEIVED": minfin_fetchers.fetch_pension_contributions_received,
    "PENSION_CONTRIBUTIONS_ARREARS": minfin_fetchers.fetch_pension_contributions_arrears,
    "GOV_PROCUREMENT_TOTAL_VALUE": minfin_fetchers.fetch_gov_procurement_total_value,
    "INDIVIDUAL_INCOME_TAX": minfin_fetchers.fetch_individual_income_tax,
    "STATE_BUDGET_REVENUE": minfin_fetchers.fetch_state_budget_revenue,
    "STATE_BUDGET_EXPENDITURE": minfin_fetchers.fetch_state_budget_expenditure,
    "STATE_BUDGET_DEFICIT": minfin_fetchers.fetch_state_budget_deficit,
    "STATE_NON_OIL_DEFICIT": minfin_fetchers.fetch_state_non_oil_deficit,
}

INDICATOR_IDS = [
    "GOV_REVENUE", "GOV_EXPENDITURE", "GOV_DEBT",
    "GOV_HEALTH_SPENDING", "GOV_EDUCATION_SPENDING", "GOV_SOCIAL_SPENDING",
    "TAX_REVENUE", "CORPORATE_TAX", "VAT_REVENUE",
    "GOV_DEFENSE_SPENDING", "GOV_GENERAL_SERVICES_SPENDING", "GOV_TRANSPORT_SPENDING",
    "GOV_DEBT_SERVICING", "NET_BUDGET_LENDING", "BUDGET_DEFICIT", "NON_OIL_BUDGET_DEFICIT",
    "EXCISE_TAX_REVENUE", "GOV_DEBT_DOMESTIC", "GOV_DEBT_EXTERNAL",
    "GG_TAXES", "GG_SOCIAL_CONTRIBUTIONS", "GG_CASH_SURPLUS_DEFICIT",
    "CUSTOMS_DUTIES",
    "GOV_WAGES_EXPENDITURE", "GOV_CAPITAL_EXPENDITURE",
    "GOV_PENSIONS_EXPENDITURE", "GOV_SUBSIDIES_EXPENDITURE",
    "SUBVENTIONS_REPUBLICAN",
    "LOCAL_GOV_WAGES_EXPENDITURE", "LOCAL_GOV_CAPITAL_EXPENDITURE", "LOCAL_GOV_SUBSIDIES_EXPENDITURE",
    "NATIONAL_FUND_STABILIZATION_PORTFOLIO", "NATIONAL_FUND_SAVINGS_PORTFOLIO",
    "NATIONAL_FUND_SAVINGS_BONDS", "NATIONAL_FUND_EQUITIES", "NATIONAL_FUND_GOLD",
    "GOV_ACCOUNTS_PAYABLE", "GOV_ACCOUNTS_RECEIVABLE",
    "GOV_FINANCIAL_ASSETS_SOLD", "GOV_AUDIT_VIOLATIONS_AMOUNT",
    "TAX_ARREARS_TOTAL", "PENSION_CONTRIBUTIONS_RECEIVED", "PENSION_CONTRIBUTIONS_ARREARS",
    "GOV_PROCUREMENT_TOTAL_VALUE",
    "INDIVIDUAL_INCOME_TAX", "STATE_BUDGET_REVENUE", "STATE_BUDGET_EXPENDITURE",
    "STATE_BUDGET_DEFICIT", "STATE_NON_OIL_DEFICIT",
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
            methodology=manifest_info.get("note", "Ministry of Finance of Kazakhstan official methodology"),
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
