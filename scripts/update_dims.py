#!/usr/bin/env python3
"""Update pipeline for the dimensional (item-level) datasets in config/dims.yaml.

Same shape as update_bns.py — fetch, validate, record revisions, write processed,
write metadata, log — but every record carries an item_code, and the result goes
to data/unified/macro_dims_long.csv.gz (gzip) rather than macro_long.csv (see lib/dims.py).
Each dataset names its agency; the fetcher is chosen by it (bns, wb, eia).

    python scripts/update_dims.py                 # every dataset
    python scripts/update_dims.py --only wb eia   # by agency or dataset id
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import dims, metadata, pipeline_logging, revisions, validation  # noqa: E402
from fetchers import bns_dims, bns_trade, eia, gravity, nbk_dims, taldau_dims, wb  # noqa: E402

# Keyed by a dataset's `fetcher` when it names one, else by its agency.
AGENCY_FETCHERS = {"bns": bns_dims.fetch, "bns_trade": bns_trade.fetch, "wb": wb.fetch, "eia": eia.fetch,
                   "gravity": gravity.fetch, "taldau": taldau_dims.fetch,
                   "nbk_survey": nbk_dims.fetch, "nbk_debt_schedule": nbk_dims.fetch_debt_schedule}
METHODOLOGY = {"bns": "Bureau of National Statistics official methodology",
               "wb": "World Bank Commodity Markets (Pink Sheet / Commodity Markets Outlook), nominal US dollars",
               "eia": "U.S. EIA Short-Term Energy Outlook, monthly release",
               "wits": "World Bank WITS TradeStats (UN Comtrade / TRAINS data)",
               "nbk": "National Bank of Kazakhstan, enterprise monitoring survey"}
CONFIG = dims.load_config()
DATASETS = {d["id"]: d for d in CONFIG["datasets"]}
DATASET_IDS = list(DATASETS)
FETCHERS = {ds_id: (lambda ds=ds: AGENCY_FETCHERS[ds.get("fetcher", ds["agency"])](ds)) for ds_id, ds in DATASETS.items()}


def _geography(ds: dict, records: list[dict]) -> str:
    if ds.get("geography"):
        return ds["geography"]
    regional = any((r.get("region") or dims.NATIONAL) != dims.NATIONAL for r in records)
    return "Kazakhstan (national and regions)" if regional else "Kazakhstan (national)"


def run(run_logger: pipeline_logging.RunLogger, only: set[str] | None = None) -> None:
    today = date.today()
    for ds_id in DATASET_IDS:
        ds = DATASETS[ds_id]
        agency = ds["agency"]
        if only and ds_id not in only and agency not in only:
            continue
        try:
            records, manifest_info = FETCHERS[ds_id]()
        except validation.StructuralChangeError as exc:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=agency, dataset=ds_id,
                action="fetch", status="structural_change", errors=[str(exc)]))
            continue
        except Exception as exc:  # noqa: BLE001
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=agency, dataset=ds_id,
                action="fetch", status="error", errors=[str(exc)]))
            continue

        result = dims.validate(records, ds_id, ds["frequency"], cumulation=ds.get("cumulation"))
        warnings = list(manifest_info.get("warnings", [])) + result.warnings
        if not result.ok:
            run_logger.log(pipeline_logging.LogEntry(
                timestamp=datetime.now().isoformat(), source=agency, dataset=ds_id,
                action="validate", status="error", errors=result.errors, warnings=warnings))
            continue

        revs = dims.detect_revisions(ds_id, agency, dims.load_processed(ds_id), records, today)
        if revs:
            revisions.append_revisions(revs)
        dims.write_processed(ds_id, records, ds.get("transformation", "level"))
        metadata.DatasetMetadata(
            source=agency,
            source_url=manifest_info.get("source_url", ""),
            dataset_id=manifest_info.get("dataset_id", ""),
            indicator_id=ds_id,
            indicator_name=ds["name_en"],
            description=ds["name_ru"],
            frequency=ds["frequency"],
            unit=ds["unit"],
            currency="KZT" if "KZT" in ds["unit"] else ("USD" if "USD" in ds["unit"] or "$" in ds["unit"] else ""),
            geography=_geography(ds, records),
            methodology=manifest_info.get("note") or METHODOLOGY[agency],
            publication_date=manifest_info.get("release"),
            last_update_date=today.isoformat(),
            download_date=today.isoformat(),
            period_start=min(r["date"] for r in records),
            period_end=max(r["date"] for r in records),
            next_update_date=manifest_info.get("next_update") or ds.get("next_update"),
            transformation=manifest_info.get("transformation") or ds.get("transformation") or "level",
            revision_status="revised" if revs else "original",
        ).write()
        run_logger.log(pipeline_logging.LogEntry(
            timestamp=datetime.now().isoformat(), source=agency, dataset=ds_id,
            action="fetch+validate+process", status="ok",
            records_downloaded=len(records), records_processed=len(records), warnings=warnings))


def build_unified() -> Path:
    return dims.write_long_csv(dims.build_long(CONFIG["datasets"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", nargs="*", help="dataset ids or agencies to update (default: all)")
    args = ap.parse_args()
    logger = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    run(logger, set(args.only) if args.only else None)
    if logger.has_errors():
        sys.exit(1)
    path = build_unified()
    print(f"update_dims: {sum(1 for e in logger.entries if e.status == 'ok')}/{len(logger.entries)} datasets ok; wrote {path}")
