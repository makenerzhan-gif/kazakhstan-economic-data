#!/usr/bin/env python3
"""Scalar indicators derived from the item-level layer (config/indicators.yaml,
`derived_from`).

A national total that the item-level layer already carries — the export workbook's
national row, the industrial production index of section B, the average population —
used to be fetched a second time by its own scalar fetcher from the same or a sibling
BNS table. Those twelve series are now written from data/processed/dims/<dataset>.csv:
one download, one parse, one raw copy, and the scalar keeps its id, unit and place in
macro_long.csv / macro_wide.csv. The values are the published ones (the item-level
parsers keep the sum-against-total proofs); `scale` only converts units (thousand
persons -> persons, million KZT -> KZT).

    derived_from: {dataset: EMPLOYED_BY_REGION, item: TOTAL, region: national, scale: 1000}

Runs after update_dims.py in update_all.py. Revisions, metadata and logging follow
update_bns.py; the metadata names the dataset and item the series comes from.
"""
from __future__ import annotations

import csv
import sys
import yaml
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import dims, metadata, periods, pipeline_logging, processed_store, revisions, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
INDICATORS_PATH = REPO_ROOT / "config" / "indicators.yaml"


def derived_indicators(path: Path = INDICATORS_PATH) -> list[dict]:
    return [i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["indicators"] if i.get("derived_from")]


def derive(ind: dict, dims_records: list[dict]) -> list[dict]:
    """The scalar records for one indicator from its dataset's processed rows."""
    spec = ind["derived_from"]
    region = spec.get("region", dims.NATIONAL)
    # Decimal, not float: 16804418.1 * 1e6 in floats is 16804418100000.002, and that noise
    # was being logged as a "revision" of GDP_NOMINAL and stored in ELECTRICITY_PRODUCTION.
    scale = Decimal(str(spec.get("scale", 1)))
    out = []
    for r in dims_records:
        if r["item_code"] != spec["item"] or (r.get("region") or dims.NATIONAL) != region:
            continue
        if r.get("value") in (None, ""):
            continue
        out.append({"date": r["date"], "value": float(Decimal(str(r["value"])) * scale), "transformation": r.get("transformation") or "level"})
    out.sort(key=lambda r: r["date"])
    return out


def _load_old_processed(agency: str, indicator_id: str) -> list[dict]:
    path = REPO_ROOT / "data" / "processed" / agency / f"{indicator_id.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(run_logger: pipeline_logging.RunLogger) -> None:
    today = date.today()
    for ind in derived_indicators():
        indicator_id, agency, spec = ind["id"], ind["agency"], ind["derived_from"]
        dataset = spec["dataset"]
        try:
            source_rows = dims.load_processed(dataset)
            if not source_rows:
                raise FileNotFoundError(f"data/processed/dims/{dataset.lower()}.csv is missing or empty")
            records = derive(ind, source_rows)
            if not records:
                raise validation.StructuralChangeError("\n".join([
                    f"STRUCTURAL CHANGE DETECTED in {agency}/{indicator_id} (derived)",
                    f"WHAT CHANGED: {dataset} carries no rows for item {spec['item']!r}, region {spec.get('region', dims.NATIONAL)!r}",
                    "EXPECTED: the item the indicator is derived from (config/indicators.yaml derived_from)",
                    f"ACTUAL: items present: {sorted({r['item_code'] for r in source_rows})[:20]}",
                    "ACTION REQUIRED: check the dataset's dictionary and the derived_from entry.",
                ]))
        except validation.StructuralChangeError as exc:
            run_logger.log(pipeline_logging.LogEntry(timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                                                     action="derive", status="structural_change", errors=[str(exc)]))
            continue
        except Exception as exc:  # noqa: BLE001
            run_logger.log(pipeline_logging.LogEntry(timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                                                     action="derive", status="error", errors=[str(exc)]))
            continue

        records = periods.normalise(records, ind["frequency"], ind.get("observation_type"))
        result = validation.run_all(records, indicator_id, expected_frequency=ind["frequency"], cumulation=ind.get("cumulation"))
        if not result.ok:
            run_logger.log(pipeline_logging.LogEntry(timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                                                     action="validate", status="error", errors=result.errors, warnings=result.warnings))
            continue

        revs = revisions.detect_revisions(indicator_id, agency, _load_old_processed(agency, indicator_id), records, today)
        if revs:
            revisions.append_revisions(revs)
        transformation = records[0].get("transformation") or "level"   # the source dataset's, e.g. year-to-date cumulative for GDP_NOMINAL
        processed_store.write_processed(agency, indicator_id, records, transformation=transformation, frequency=ind["frequency"])

        src_meta = metadata.load(agency, dataset) or {}
        metadata.DatasetMetadata(
            source=agency,
            source_url=src_meta.get("source_url", ""),
            dataset_id=f"{dataset}[{spec['item']}]" + ("" if spec.get("region", dims.NATIONAL) == dims.NATIONAL else f"@{spec['region']}"),
            indicator_id=indicator_id,
            indicator_name=ind["name_en"],
            description=ind["name_ru"],
            frequency=ind["frequency"],
            unit=ind["unit"],
            currency="KZT" if "KZT" in ind["unit"] else ("USD" if "USD" in ind["unit"] else ""),
            geography=src_meta.get("geography", "Kazakhstan (national)"),
            methodology=f"Derived from the item-level dataset {dataset}, item {spec['item']}"
                        + (f", scale {spec['scale']}" if spec.get("scale") not in (None, 1, 1.0) else "")
                        + f". {src_meta.get('methodology', '')}".rstrip(),
            publication_date=src_meta.get("publication_date"),
            last_update_date=today.isoformat(),
            download_date=src_meta.get("download_date", today.isoformat()),
            period_start=records[0]["date"] if records else None,
            period_end=records[-1]["date"] if records else None,
            next_update_date=src_meta.get("next_update_date"),
            transformation=transformation,
            revision_status="revised" if revs else "original",
        ).write()
        run_logger.log(pipeline_logging.LogEntry(timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                                                 action="derive+validate+process", status="ok",
                                                 records_downloaded=0, records_processed=len(records), warnings=result.warnings))
    run_gap_fill(run_logger)


def gap_filled_indicators(path: Path = INDICATORS_PATH) -> list[dict]:
    return [i for i in yaml.safe_load(path.read_text(encoding="utf-8"))["indicators"] if i.get("gaps_filled_from")]


def fill_gaps(ind: dict, own_rows: list[dict], dims_records: list[dict], tolerance: float = 1e-9) -> tuple[list[dict], int]:
    """The indicator's own records plus the item-level values for the dates it lacks.

    Only when the two agree on every date they share: the BNS expenditure table on
    Taldau skips 2010-2013 while the xlsx table 4439's expenditure sheet carries them,
    and on the fifteen years both hold they are the same numbers to 1e-16. A single
    disagreement means they are no longer the same series and nothing is filled.
    """
    spec = ind["gaps_filled_from"]
    other = {r["date"]: r["value"] for r in derive({"derived_from": spec}, dims_records)}
    own = {r["date"]: float(r["value"]) for r in own_rows if r.get("value") not in (None, "")}
    shared = set(own) & set(other)
    if not shared:
        raise validation.StructuralChangeError(f"{ind['id']}: no date in common with {spec['dataset']}[{spec['item']}] -- cannot prove they are one series")
    worst = max(abs(own[d] - other[d]) / max(abs(own[d]), 1e-12) for d in shared)
    if worst > tolerance:
        raise validation.StructuralChangeError(
            f"{ind['id']}: differs from {spec['dataset']}[{spec['item']}] by up to {worst:.2e} (relative) on shared dates -- gaps not filled")
    added = {d: v for d, v in other.items() if d not in own}
    merged = [{"date": d, "value": v} for d, v in sorted({**own, **added}.items())]
    return merged, len(added)


def run_gap_fill(run_logger: pipeline_logging.RunLogger) -> None:
    for ind in gap_filled_indicators():
        indicator_id, agency = ind["id"], ind["agency"]
        try:
            merged, added = fill_gaps(ind, _load_old_processed(agency, indicator_id),
                                      dims.load_processed(ind["gaps_filled_from"]["dataset"]))
        except Exception as exc:  # noqa: BLE001 -- the scalar series stays as fetched
            run_logger.log(pipeline_logging.LogEntry(timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                                                     action="fill_gaps", status="error", errors=[str(exc)]))
            continue
        if added:
            processed_store.write_processed(agency, indicator_id, merged, transformation="level", frequency=ind["frequency"])
        run_logger.log(pipeline_logging.LogEntry(timestamp=datetime.now().isoformat(), source=agency, dataset=indicator_id,
                                                 action="fill_gaps", status="ok", records_downloaded=0, records_processed=added))


if __name__ == "__main__":
    logger = pipeline_logging.RunLogger(run_timestamp=datetime.now().isoformat())
    run(logger)
    if logger.has_errors():
        sys.exit(1)
    print(f"update_derived: {sum(1 for e in logger.entries if e.status == 'ok')}/{len(logger.entries)} derived indicators ok")
