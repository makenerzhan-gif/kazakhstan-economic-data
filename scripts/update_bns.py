#!/usr/bin/env python3
"""Update pipeline for Bureau of National Statistics (BNS) indicators.

Each indicator has a fetch function registered in FETCHERS. A fetch function
is only added once config/sources.yaml has a *confirmed* (not pending_research)
entry for it, backed by a real verified URL. Until then the indicator is
reported as skipped — this script never fabricates a downloader against a
guessed endpoint.
"""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import metadata, pipeline_logging, processed_store, revisions, validation  # noqa: E402
from fetchers import bns as bns_fetchers  # noqa: E402

AGENCY = "bns"
REPO_ROOT = Path(__file__).resolve().parents[1]

FETCHERS = {
    "CPI": bns_fetchers.fetch_cpi,
    "UNEMPLOYMENT": bns_fetchers.fetch_unemployment,
    "GDP_NOMINAL": bns_fetchers.fetch_gdp_nominal,
    "GDP_REAL": bns_fetchers.fetch_gdp_real,
    "IND_PROD": bns_fetchers.fetch_ind_prod,
    "INVESTMENT": bns_fetchers.fetch_investment,
    "EXPORTS": bns_fetchers.fetch_exports,
    "IMPORTS": bns_fetchers.fetch_imports,
    "GDP_PER_CAPITA": bns_fetchers.fetch_gdp_per_capita,
    "GDP_DEFLATOR": bns_fetchers.fetch_gdp_deflator,
    "GFCF": bns_fetchers.fetch_gfcf,
    "GFCF_VOLUME_INDEX": bns_fetchers.fetch_gfcf_volume_index,
    "NET_EXPORTS": bns_fetchers.fetch_net_exports,
    "HOUSEHOLD_CONSUMPTION": bns_fetchers.fetch_household_consumption,
    "COMPENSATION_EMPLOYEES": bns_fetchers.fetch_compensation_employees,
    "AVG_WAGE": bns_fetchers.fetch_avg_wage,
    "GDP_INCOME_METHOD": bns_fetchers.fetch_gdp_income_method,
    "GROSS_OUTPUT": bns_fetchers.fetch_gross_output,
    "TAXES_ON_PRODUCTS": bns_fetchers.fetch_taxes_on_products,
    "NET_TAXES_ON_PRODUCTS": bns_fetchers.fetch_net_taxes_on_products,
    "SUBSIDIES": bns_fetchers.fetch_subsidies,
    "INTERMEDIATE_CONSUMPTION": bns_fetchers.fetch_intermediate_consumption,
    "GROSS_ACCUMULATION": bns_fetchers.fetch_gross_accumulation,
    "IMPORT_VOLUME_INDEX": bns_fetchers.fetch_import_volume_index,
    "EXPORT_VOLUME_INDEX": bns_fetchers.fetch_export_volume_index,
    "TOTAL_CONSUMPTION_EXPENDITURE": bns_fetchers.fetch_total_consumption_expenditure,
    "CAPITAL_CONSUMPTION": bns_fetchers.fetch_capital_consumption,
    "RETAIL_TRADE": bns_fetchers.fetch_retail_trade,
    "CONSTRUCTION": bns_fetchers.fetch_construction,
    "POPULATION_BNS": bns_fetchers.fetch_population_bns,
    "REAL_WAGE_INDEX": bns_fetchers.fetch_real_wage_index,
    "EMPLOYED_TOTAL": bns_fetchers.fetch_employed_total,
    "BIRTHS_TOTAL": bns_fetchers.fetch_births_total,
    "DEATHS_TOTAL": bns_fetchers.fetch_deaths_total,
    "HOUSING_COMMISSIONED": bns_fetchers.fetch_housing_commissioned,
    "PPI": bns_fetchers.fetch_ppi,
    "WHOLESALE_TRADE": bns_fetchers.fetch_wholesale_trade,
    "RETAIL_TRADE_VOLUME_INDEX": bns_fetchers.fetch_retail_trade_volume_index,
    "EMISSIONS": bns_fetchers.fetch_emissions,
    "FREIGHT_TURNOVER": bns_fetchers.fetch_freight_turnover,
    "PASSENGER_TURNOVER": bns_fetchers.fetch_passenger_turnover,
    "AGRICULTURE_OUTPUT": bns_fetchers.fetch_agriculture_output,
    "PER_CAPITA_INCOME": bns_fetchers.fetch_per_capita_income,
    "REAL_INCOME_INDEX": bns_fetchers.fetch_real_income_index,
    "TELECOM_SERVICES": bns_fetchers.fetch_telecom_services,
    "DOCTORS_TOTAL": bns_fetchers.fetch_doctors_total,
    "ENERGY_INTENSITY": bns_fetchers.fetch_energy_intensity,
    "ENERGY_CONSUMPTION": bns_fetchers.fetch_energy_consumption,
    "ELECTRICITY_PRODUCTION": bns_fetchers.fetch_electricity_production,
    "IND_PROD_MINING": bns_fetchers.fetch_ind_prod_mining,
    "IND_PROD_MANUFACTURING": bns_fetchers.fetch_ind_prod_manufacturing,
    "IND_PROD_ELECTRICITY": bns_fetchers.fetch_ind_prod_electricity,
    "FINAL_ENERGY_CONSUMPTION": bns_fetchers.fetch_final_energy_consumption,
    "RENEWABLE_ENERGY_SHARE": bns_fetchers.fetch_renewable_energy_share,
    "POVERTY_HEADCOUNT": bns_fetchers.fetch_poverty_headcount,
    "MIGRATION_ARRIVALS": bns_fetchers.fetch_migration_arrivals,
    "MIGRATION_DEPARTURES": bns_fetchers.fetch_migration_departures,
    "LABOR_PRODUCTIVITY": bns_fetchers.fetch_labor_productivity,
    "TOURISM_VALUE_ADDED": bns_fetchers.fetch_tourism_value_added,
    "TOURISM_GDP_SHARE": bns_fetchers.fetch_tourism_gdp_share,
    "TOURISM_EMPLOYMENT": bns_fetchers.fetch_tourism_employment,
    "TOURISM_EMPLOYMENT_SHARE": bns_fetchers.fetch_tourism_employment_share,
    "TOURISM_INBOUND_CONSUMPTION": bns_fetchers.fetch_tourism_inbound_consumption,
    "TOURISM_OUTBOUND_CONSUMPTION": bns_fetchers.fetch_tourism_outbound_consumption,
    "TOURISM_INBOUND_TRIPS": bns_fetchers.fetch_tourism_inbound_trips,
    "TOURISM_DOMESTIC_TRIPS": bns_fetchers.fetch_tourism_domestic_trips,
    "TOURISM_OUTBOUND_TRIPS": bns_fetchers.fetch_tourism_outbound_trips,
    "TOURISM_INBOUND_NIGHTS": bns_fetchers.fetch_tourism_inbound_nights,
    "LIFE_EXPECTANCY": bns_fetchers.fetch_life_expectancy,
    "CRUDE_BIRTH_RATE": bns_fetchers.fetch_crude_birth_rate,
    "TOTAL_FERTILITY_RATE": bns_fetchers.fetch_total_fertility_rate,
    "CRUDE_DEATH_RATE": bns_fetchers.fetch_crude_death_rate,
    "INFANT_MORTALITY_RATE": bns_fetchers.fetch_infant_mortality_rate,
    "UNDER5_MORTALITY_RATE": bns_fetchers.fetch_under5_mortality_rate,
    "STILLBIRTH_RATE": bns_fetchers.fetch_stillbirth_rate,
    "INNOVATION_EXPENDITURE": bns_fetchers.fetch_innovation_expenditure,
    "ORGANIZATIONS_USING_COMPUTERS": bns_fetchers.fetch_organizations_using_computers,
    "COMPUTERS_IN_ORGANIZATIONS": bns_fetchers.fetch_computers_in_organizations,
    "COMPUTERS_INTERNET_CONNECTED": bns_fetchers.fetch_computers_internet_connected,
    "WORKERS_USING_COMPUTERS": bns_fetchers.fetch_workers_using_computers,
    "WORKERS_USING_INTERNET": bns_fetchers.fetch_workers_using_internet,
    "ECOMMERCE_RETAIL_ORDERS": bns_fetchers.fetch_ecommerce_retail_orders,
    "ECOMMERCE_SERVICES_VALUE": bns_fetchers.fetch_ecommerce_services_value,
    "DOCTORS_PER_10K": bns_fetchers.fetch_doctors_per_10k,
    "HOSPITAL_BEDS": bns_fetchers.fetch_hospital_beds,
    "HOSPITAL_BEDS_PER_10K": bns_fetchers.fetch_hospital_beds_per_10k,
    "SME_GDP_SHARE": bns_fetchers.fetch_sme_gdp_share,
    "SMALL_BUSINESS_GDP_SHARE": bns_fetchers.fetch_small_business_gdp_share,
    "MEDIUM_BUSINESS_GDP_SHARE": bns_fetchers.fetch_medium_business_gdp_share,
    "SMALL_BUSINESS_VALUE_ADDED": bns_fetchers.fetch_small_business_value_added,
    "MEDIUM_BUSINESS_VALUE_ADDED": bns_fetchers.fetch_medium_business_value_added,
    "HOUSING_INVESTMENT": bns_fetchers.fetch_housing_investment,
    "ICT_SPECIALISTS": bns_fetchers.fetch_ict_specialists,
    "GRADUATES_HIRED": bns_fetchers.fetch_graduates_hired,
    "OIL_EXPORTS_VOLUME": bns_fetchers.fetch_oil_exports_volume,
    "OIL_EXPORTS_VALUE": bns_fetchers.fetch_oil_exports_value,
    "OIL_PRODUCTION": bns_fetchers.fetch_oil_production,
    "INDUSTRIAL_OUTPUT": bns_fetchers.fetch_industrial_output,
    "INDUSTRIAL_PRODUCTION_INDEX": bns_fetchers.fetch_industrial_production_index,
    "MINING_OUTPUT": bns_fetchers.fetch_mining_output,
    "MANUFACTURING_OUTPUT": bns_fetchers.fetch_manufacturing_output,
    "INVESTMENT_FIXED_CAPITAL": bns_fetchers.fetch_investment_fixed_capital,
    "INVESTMENT_INDEX": bns_fetchers.fetch_investment_index,
    "RETAIL_TRADE_MONTHLY": bns_fetchers.fetch_retail_trade_monthly,
    "WHOLESALE_TRADE_MONTHLY": bns_fetchers.fetch_wholesale_trade_monthly,
    "RETAIL_TRADE_INDEX_MONTHLY": bns_fetchers.fetch_retail_trade_index_monthly,
    "WHOLESALE_TRADE_INDEX_MONTHLY": bns_fetchers.fetch_wholesale_trade_index_monthly,
    "CONSTRUCTION_OUTPUT": bns_fetchers.fetch_construction_output,
    "CONSTRUCTION_INDEX": bns_fetchers.fetch_construction_index,
    "EXPORT_PRICE_INDEX": bns_fetchers.fetch_export_price_index,
    "IMPORT_PRICE_INDEX": bns_fetchers.fetch_import_price_index,
    "CPI_YOY": bns_fetchers.fetch_cpi_yoy,
    "CPI_YTD": bns_fetchers.fetch_cpi_ytd,
}

INDICATOR_IDS = [
    "GDP_REAL", "GDP_NOMINAL", "IND_PROD", "CPI", "UNEMPLOYMENT",
    "INVESTMENT", "EXPORTS", "IMPORTS",
    "GDP_PER_CAPITA", "GDP_DEFLATOR", "GFCF", "GFCF_VOLUME_INDEX",
    "NET_EXPORTS", "HOUSEHOLD_CONSUMPTION", "COMPENSATION_EMPLOYEES", "AVG_WAGE",
    "GDP_INCOME_METHOD", "GROSS_OUTPUT", "TAXES_ON_PRODUCTS", "NET_TAXES_ON_PRODUCTS",
    "SUBSIDIES", "INTERMEDIATE_CONSUMPTION", "GROSS_ACCUMULATION",
    "IMPORT_VOLUME_INDEX", "EXPORT_VOLUME_INDEX", "TOTAL_CONSUMPTION_EXPENDITURE",
    "CAPITAL_CONSUMPTION", "RETAIL_TRADE",
    "CONSTRUCTION", "POPULATION_BNS", "REAL_WAGE_INDEX", "EMPLOYED_TOTAL",
    "BIRTHS_TOTAL", "DEATHS_TOTAL", "HOUSING_COMMISSIONED", "PPI",
    "WHOLESALE_TRADE", "RETAIL_TRADE_VOLUME_INDEX", "EMISSIONS",
    "FREIGHT_TURNOVER", "PASSENGER_TURNOVER",
    "AGRICULTURE_OUTPUT", "PER_CAPITA_INCOME", "REAL_INCOME_INDEX",
    "TELECOM_SERVICES", "DOCTORS_TOTAL",
    "ENERGY_INTENSITY", "ENERGY_CONSUMPTION", "ELECTRICITY_PRODUCTION",
    "IND_PROD_MINING", "IND_PROD_MANUFACTURING", "IND_PROD_ELECTRICITY",
    "FINAL_ENERGY_CONSUMPTION", "RENEWABLE_ENERGY_SHARE", "POVERTY_HEADCOUNT",
    "MIGRATION_ARRIVALS", "MIGRATION_DEPARTURES", "LABOR_PRODUCTIVITY",
    "TOURISM_VALUE_ADDED",
    "TOURISM_GDP_SHARE",
    "TOURISM_EMPLOYMENT",
    "TOURISM_EMPLOYMENT_SHARE",
    "TOURISM_INBOUND_CONSUMPTION",
    "TOURISM_OUTBOUND_CONSUMPTION",
    "TOURISM_INBOUND_TRIPS",
    "TOURISM_DOMESTIC_TRIPS",
    "TOURISM_OUTBOUND_TRIPS",
    "TOURISM_INBOUND_NIGHTS",
    "LIFE_EXPECTANCY",
    "CRUDE_BIRTH_RATE",
    "TOTAL_FERTILITY_RATE",
    "CRUDE_DEATH_RATE",
    "INFANT_MORTALITY_RATE",
    "UNDER5_MORTALITY_RATE",
    "STILLBIRTH_RATE",
    "INNOVATION_EXPENDITURE",
    "ORGANIZATIONS_USING_COMPUTERS",
    "COMPUTERS_IN_ORGANIZATIONS",
    "COMPUTERS_INTERNET_CONNECTED",
    "WORKERS_USING_COMPUTERS",
    "WORKERS_USING_INTERNET",
    "ECOMMERCE_RETAIL_ORDERS",
    "ECOMMERCE_SERVICES_VALUE",
    "DOCTORS_PER_10K",
    "HOSPITAL_BEDS",
    "HOSPITAL_BEDS_PER_10K",
    "SME_GDP_SHARE",
    "SMALL_BUSINESS_GDP_SHARE",
    "MEDIUM_BUSINESS_GDP_SHARE",
    "SMALL_BUSINESS_VALUE_ADDED",
    "MEDIUM_BUSINESS_VALUE_ADDED",
    "HOUSING_INVESTMENT",
    "ICT_SPECIALISTS",
    "GRADUATES_HIRED",
    "OIL_EXPORTS_VOLUME",
    "OIL_EXPORTS_VALUE",
    "OIL_PRODUCTION",
    "INDUSTRIAL_OUTPUT",
    "INDUSTRIAL_PRODUCTION_INDEX",
    "MINING_OUTPUT",
    "MANUFACTURING_OUTPUT",
    "INVESTMENT_FIXED_CAPITAL",
    "INVESTMENT_INDEX",
    "RETAIL_TRADE_MONTHLY",
    "WHOLESALE_TRADE_MONTHLY",
    "RETAIL_TRADE_INDEX_MONTHLY",
    "WHOLESALE_TRADE_INDEX_MONTHLY",
    "CONSTRUCTION_OUTPUT",
    "CONSTRUCTION_INDEX",
    "EXPORT_PRICE_INDEX",
    "IMPORT_PRICE_INDEX",
    "CPI_YOY",
    "CPI_YTD",
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
                source=AGENCY,
                dataset=indicator_id,
                action="fetch",
                status="skipped",
                warnings=["No confirmed source yet for this indicator (see config/sources.yaml "
                          "agencies.bns.endpoints). Run/extend the source-research step before enabling."],
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
                source=AGENCY, dataset=indicator_id, action="fetch", status="error",
                errors=[str(exc)],
            ))
            continue

        result = validation.run_all(records, indicator_id, expected_frequency=manifest_info.get("frequency", "monthly"))
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
            methodology=manifest_info.get("note", "Bureau of National Statistics official methodology"),
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
