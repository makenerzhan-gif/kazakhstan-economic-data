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
    "TONIA": nbk_fetchers.fetch_tonia,
    "NATIONAL_FUND_TRANSFERS": nbk_fetchers.fetch_national_fund_transfers,
    "KASE_USD_VOLUME": nbk_fetchers.fetch_kase_usd_volume,
    "REMITTANCES_SENT": nbk_fetchers.fetch_remittances_sent,
    "REMITTANCES_RECEIVED": nbk_fetchers.fetch_remittances_received,
    "INFLATION_EXPECTATIONS": nbk_fetchers.fetch_inflation_expectations,
    "BUSINESS_ACTIVITY_INDEX": nbk_fetchers.fetch_business_activity_index,
    "NON_CASH_PAYMENTS_SHARE": nbk_fetchers.fetch_non_cash_payments_share,
    "CAPITAL_ADEQUACY_RATIO": nbk_fetchers.fetch_capital_adequacy_ratio,
    "NPL_RATIO": nbk_fetchers.fetch_npl_ratio,
    "LOANS_TO_ECONOMY": nbk_fetchers.fetch_loans_to_economy,
    "FDI_NET_INFLOW": nbk_fetchers.fetch_fdi_net_inflow,
    "GOV_SECURITIES_MEUKAM": nbk_fetchers.fetch_gov_securities_meukam,
    "IIP_NET": nbk_fetchers.fetch_iip_net,
    "IIP_ASSETS": nbk_fetchers.fetch_iip_assets,
    "IIP_LIABILITIES": nbk_fetchers.fetch_iip_liabilities,
    "CURRENT_ACCOUNT_BALANCE": nbk_fetchers.fetch_current_account_balance,
    "BANK_ROA": nbk_fetchers.fetch_bank_roa,
    "BANK_ROE": nbk_fetchers.fetch_bank_roe,
    "PENSION_FUND_ASSETS": nbk_fetchers.fetch_pension_fund_assets,
    "INSURANCE_PREMIUMS_GENERAL": nbk_fetchers.fetch_insurance_premiums_general,
    "INSURANCE_PREMIUMS_LIFE": nbk_fetchers.fetch_insurance_premiums_life,
    "PENSION_PAYMENTS": nbk_fetchers.fetch_pension_payments,
    "RESERVES_IMPORT_COVER": nbk_fetchers.fetch_reserves_import_cover,
    "PRODUCTION_VOLUME_DIFFUSION_INDEX": nbk_fetchers.fetch_production_volume_diffusion_index,
    "PRODUCTION_EXPECTATIONS_DIFFUSION_INDEX": nbk_fetchers.fetch_production_expectations_diffusion_index,
    "DEMAND_DIFFUSION_INDEX": nbk_fetchers.fetch_demand_diffusion_index,
    "DEMAND_EXPECTATIONS_DIFFUSION_INDEX": nbk_fetchers.fetch_demand_expectations_diffusion_index,
    "LOAN_RATE_ACCEPTABLE_KZT": nbk_fetchers.fetch_loan_rate_acceptable_kzt,
    "LOAN_RATE_ACCEPTABLE_FX": nbk_fetchers.fetch_loan_rate_acceptable_fx,
    "LOAN_TERM_ACCEPTABLE_KZT": nbk_fetchers.fetch_loan_term_acceptable_kzt,
    "LOAN_TERM_ACCEPTABLE_FX": nbk_fetchers.fetch_loan_term_acceptable_fx,
    "INVENTORIES_DIFFUSION_INDEX": nbk_fetchers.fetch_inventories_diffusion_index,
    "INVENTORIES_EXPECTATIONS_DIFFUSION_INDEX": nbk_fetchers.fetch_inventories_expectations_diffusion_index,
    "IMPORT_PRICE_DIFFUSION_INDEX": nbk_fetchers.fetch_import_price_diffusion_index,
    "IMPORT_PRICE_EXPECTATIONS_DIFFUSION_INDEX": nbk_fetchers.fetch_import_price_expectations_diffusion_index,
    "RAW_MATERIALS_PRICE_DIFFUSION_INDEX": nbk_fetchers.fetch_raw_materials_price_diffusion_index,
    "RAW_MATERIALS_PRICE_EXPECTATIONS_DIFFUSION_INDEX": nbk_fetchers.fetch_raw_materials_price_expectations_diffusion_index,
    "CAPACITY_UTILIZATION": nbk_fetchers.fetch_capacity_utilization,
    "FINISHED_GOODS_PRICE_DIFFUSION_INDEX": nbk_fetchers.fetch_finished_goods_price_diffusion_index,
    "FINISHED_GOODS_PRICE_EXPECTATIONS_DIFFUSION_INDEX": nbk_fetchers.fetch_finished_goods_price_expectations_diffusion_index,
    "OVERDUE_ACCOUNTS_PAYABLE_SHARE": nbk_fetchers.fetch_overdue_accounts_payable_share,
    "OVERDUE_ACCOUNTS_RECEIVABLE_SHARE": nbk_fetchers.fetch_overdue_accounts_receivable_share,
    "OVERDUE_BANK_LOANS_SHARE": nbk_fetchers.fetch_overdue_bank_loans_share,
    "ENTERPRISE_DEBT_BURDEN": nbk_fetchers.fetch_enterprise_debt_burden,
    "EXPORTERS_SHARE": nbk_fetchers.fetch_exporters_share,
    "IMPORTERS_SHARE": nbk_fetchers.fetch_importers_share,
    "PAYMENTS_TOTAL_VALUE": nbk_fetchers.fetch_payments_total_value,
    "CASHLESS_PAYMENTS_VALUE": nbk_fetchers.fetch_cashless_payments_value,
    "CASH_WITHDRAWALS_VALUE": nbk_fetchers.fetch_cash_withdrawals_value,
    "PAYMENT_CARDS_VALUE": nbk_fetchers.fetch_payment_cards_value,
    "HOUSEHOLD_DEPOSITS_FIXED_TERM_KZT": nbk_fetchers.fetch_household_deposits_fixed_term_kzt,
    "HOUSEHOLD_DEPOSITS_FIXED_TERM_FX": nbk_fetchers.fetch_household_deposits_fixed_term_fx,
    "HOUSEHOLD_DEPOSITS_DEMAND_KZT": nbk_fetchers.fetch_household_deposits_demand_kzt,
    "HOUSEHOLD_DEPOSITS_DEMAND_FX": nbk_fetchers.fetch_household_deposits_demand_fx,
    "HOUSEHOLD_DEPOSITS_SAVING_KZT": nbk_fetchers.fetch_household_deposits_saving_kzt,
    "HOUSEHOLD_DEPOSITS_SAVING_FX": nbk_fetchers.fetch_household_deposits_saving_fx,
    "LOANS_BUSINESS_KZT": nbk_fetchers.fetch_loans_business_kzt,
    "LOANS_BUSINESS_FX": nbk_fetchers.fetch_loans_business_fx,
    "LOANS_INDIVIDUALS_KZT": nbk_fetchers.fetch_loans_individuals_kzt,
    "LOANS_INDIVIDUALS_FX": nbk_fetchers.fetch_loans_individuals_fx,
    "LOANS_MICROFINANCE_INDIVIDUALS": nbk_fetchers.fetch_loans_microfinance_individuals,
    "LOANS_MICROFINANCE_BUSINESS": nbk_fetchers.fetch_loans_microfinance_business,
    "EXTERNAL_DEBT_LONG_TERM": nbk_fetchers.fetch_external_debt_long_term,
    "EXTERNAL_DEBT_SHORT_TERM": nbk_fetchers.fetch_external_debt_short_term,
    "PRIVATE_EXTERNAL_DEBT_INTERCOMPANY": nbk_fetchers.fetch_private_external_debt_intercompany,
    "PRIVATE_EXTERNAL_DEBT_BANKS_OTHER_LT": nbk_fetchers.fetch_private_external_debt_banks_other_lt,
    "GOLD_BULLION_SALES": nbk_fetchers.fetch_gold_bullion_sales,
    "REMITTANCES_SENT_USD": nbk_fetchers.fetch_remittances_sent_usd,
    "REMITTANCES_SENT_KZT": nbk_fetchers.fetch_remittances_sent_kzt,
    "REMITTANCES_SENT_RUB": nbk_fetchers.fetch_remittances_sent_rub,
    "REMITTANCES_RECEIVED_USD": nbk_fetchers.fetch_remittances_received_usd,
    "REMITTANCES_RECEIVED_KZT": nbk_fetchers.fetch_remittances_received_kzt,
    "REMITTANCES_RECEIVED_RUB": nbk_fetchers.fetch_remittances_received_rub,
    "EXTERNAL_DEBT_GOV_LOANS_LT": nbk_fetchers.fetch_external_debt_gov_loans_lt,
    "EXTERNAL_DEBT_BANKS_LOANS_LT": nbk_fetchers.fetch_external_debt_banks_loans_lt,
    "EXTERNAL_DEBT_BANKS_SECURITIES_LT": nbk_fetchers.fetch_external_debt_banks_securities_lt,
    "EXTERNAL_DEBT_OTHER_SECURITIES_LT": nbk_fetchers.fetch_external_debt_other_securities_lt,
    "GOV_SECURITIES_SECONDARY_NBK_NOTES": nbk_fetchers.fetch_gov_securities_secondary_nbk_notes,
    "EXCHANGE_RATE_EUR_OTC": nbk_fetchers.fetch_exchange_rate_eur_otc,
    "EXCHANGE_RATE_RUB_OTC": nbk_fetchers.fetch_exchange_rate_rub_otc,
    "EXCHANGE_RATE_USD_OTC": nbk_fetchers.fetch_exchange_rate_usd_otc,
    "FX_OTC_VOLUME_USD": nbk_fetchers.fetch_fx_otc_volume_usd,
    "FX_OTC_VOLUME_EUR": nbk_fetchers.fetch_fx_otc_volume_eur,
    "FX_OTC_VOLUME_RUB": nbk_fetchers.fetch_fx_otc_volume_rub,
    "OFC_NET_FOREIGN_ASSETS": nbk_fetchers.fetch_ofc_net_foreign_assets,
    "OFC_CLAIMS_ON_NONRESIDENTS": nbk_fetchers.fetch_ofc_claims_on_nonresidents,
    "OFC_LIABILITIES_TO_NONRESIDENTS": nbk_fetchers.fetch_ofc_liabilities_to_nonresidents,
    "OFC_CLAIMS_ON_BANKING_SYSTEM": nbk_fetchers.fetch_ofc_claims_on_banking_system,
}

INDICATOR_IDS = [
    "BASE_RATE", "EXCHANGE_RATE", "M2", "M3", "MONETARY_BASE", "M0", "M1",
    "FX_RESERVES", "NATIONAL_FUND_ASSETS", "REER", "NEER", "DEPOSITS_TOTAL",
    "EXTERNAL_DEBT", "LENDING_RATE", "DEPOSIT_RATE",
    "TONIA", "NATIONAL_FUND_TRANSFERS", "KASE_USD_VOLUME",
    "REMITTANCES_SENT", "REMITTANCES_RECEIVED",
    "INFLATION_EXPECTATIONS", "BUSINESS_ACTIVITY_INDEX",
    "NON_CASH_PAYMENTS_SHARE", "CAPITAL_ADEQUACY_RATIO", "NPL_RATIO",
    "LOANS_TO_ECONOMY",
    "FDI_NET_INFLOW", "GOV_SECURITIES_MEUKAM",
    "IIP_NET", "IIP_ASSETS", "IIP_LIABILITIES", "CURRENT_ACCOUNT_BALANCE",
    "BANK_ROA", "BANK_ROE", "PENSION_FUND_ASSETS",
    "INSURANCE_PREMIUMS_GENERAL", "INSURANCE_PREMIUMS_LIFE",
    "PENSION_PAYMENTS", "RESERVES_IMPORT_COVER",
    "PRODUCTION_VOLUME_DIFFUSION_INDEX", "PRODUCTION_EXPECTATIONS_DIFFUSION_INDEX",
    "DEMAND_DIFFUSION_INDEX", "DEMAND_EXPECTATIONS_DIFFUSION_INDEX",
    "LOAN_RATE_ACCEPTABLE_KZT",
    "LOAN_RATE_ACCEPTABLE_FX",
    "LOAN_TERM_ACCEPTABLE_KZT",
    "LOAN_TERM_ACCEPTABLE_FX",
    "INVENTORIES_DIFFUSION_INDEX",
    "INVENTORIES_EXPECTATIONS_DIFFUSION_INDEX",
    "IMPORT_PRICE_DIFFUSION_INDEX",
    "IMPORT_PRICE_EXPECTATIONS_DIFFUSION_INDEX",
    "RAW_MATERIALS_PRICE_DIFFUSION_INDEX",
    "RAW_MATERIALS_PRICE_EXPECTATIONS_DIFFUSION_INDEX",
    "CAPACITY_UTILIZATION",
    "FINISHED_GOODS_PRICE_DIFFUSION_INDEX",
    "FINISHED_GOODS_PRICE_EXPECTATIONS_DIFFUSION_INDEX",
    "OVERDUE_ACCOUNTS_PAYABLE_SHARE",
    "OVERDUE_ACCOUNTS_RECEIVABLE_SHARE",
    "OVERDUE_BANK_LOANS_SHARE",
    "ENTERPRISE_DEBT_BURDEN",
    "EXPORTERS_SHARE",
    "IMPORTERS_SHARE",
    "PAYMENTS_TOTAL_VALUE",
    "CASHLESS_PAYMENTS_VALUE",
    "CASH_WITHDRAWALS_VALUE",
    "PAYMENT_CARDS_VALUE",
    "HOUSEHOLD_DEPOSITS_FIXED_TERM_KZT",
    "HOUSEHOLD_DEPOSITS_FIXED_TERM_FX",
    "HOUSEHOLD_DEPOSITS_DEMAND_KZT",
    "HOUSEHOLD_DEPOSITS_DEMAND_FX",
    "HOUSEHOLD_DEPOSITS_SAVING_KZT",
    "HOUSEHOLD_DEPOSITS_SAVING_FX",
    "LOANS_BUSINESS_KZT",
    "LOANS_BUSINESS_FX",
    "LOANS_INDIVIDUALS_KZT",
    "LOANS_INDIVIDUALS_FX",
    "LOANS_MICROFINANCE_INDIVIDUALS",
    "LOANS_MICROFINANCE_BUSINESS",
    "EXTERNAL_DEBT_LONG_TERM",
    "EXTERNAL_DEBT_SHORT_TERM",
    "PRIVATE_EXTERNAL_DEBT_INTERCOMPANY",
    "PRIVATE_EXTERNAL_DEBT_BANKS_OTHER_LT",
    "GOLD_BULLION_SALES",
    "REMITTANCES_SENT_USD",
    "REMITTANCES_SENT_KZT",
    "REMITTANCES_SENT_RUB",
    "REMITTANCES_RECEIVED_USD",
    "REMITTANCES_RECEIVED_KZT",
    "REMITTANCES_RECEIVED_RUB",
    "EXTERNAL_DEBT_GOV_LOANS_LT",
    "EXTERNAL_DEBT_BANKS_LOANS_LT",
    "EXTERNAL_DEBT_BANKS_SECURITIES_LT",
    "EXTERNAL_DEBT_OTHER_SECURITIES_LT",
    "GOV_SECURITIES_SECONDARY_NBK_NOTES",
    "EXCHANGE_RATE_EUR_OTC",
    "EXCHANGE_RATE_RUB_OTC",
    "EXCHANGE_RATE_USD_OTC",
    "FX_OTC_VOLUME_USD",
    "FX_OTC_VOLUME_EUR",
    "FX_OTC_VOLUME_RUB",
    "OFC_NET_FOREIGN_ASSETS",
    "OFC_CLAIMS_ON_NONRESIDENTS",
    "OFC_LIABILITIES_TO_NONRESIDENTS",
    "OFC_CLAIMS_ON_BANKING_SYSTEM",
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
