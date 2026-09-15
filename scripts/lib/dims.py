"""Dimensional series: one value per (date, region, variable, item).

The scalar layers (processed/<agency>/, macro_long.csv) promise one value per date
and variable; a national-accounts breakdown by ОКЭД section, expenditure component,
ownership form — or by region — does not fit that promise, so it gets a parallel
layer with the same shape and the same rules:

  raw            data/raw/<agency>/<agency>_<id>_<date>.xlsx  (append-only, lib/raw_store)
  processed      data/processed/dims/<id>.csv                 date,region,item_code,item_name,value,transformation
  metadata       metadata/<agency>/<id>.json                  (lib/metadata.DatasetMetadata)
  revisions      metadata/revisions/<id>_revisions.jsonl      period is "<date> <item_code>[ @<region>]"
  unified        data/unified/macro_dims_long.csv             macro_long's columns + item_code, item_name

`region` is "national" for the country total (the value macro_long.csv uses) and a
code from dictionaries/regions.csv otherwise; the World Bank and EIA datasets, which
are not about Kazakhstan at all, carry region "world" and country "WLD" (set per
dataset in dims.yaml — the rest default to KZ). Item codes come from
dictionaries/<name>.csv: code, name_ru, match (a case-insensitive regex applied to
the normalised label). Matching is strict: a data row that matches no entry, or more
than one, is a structural change and stops the dataset loudly.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

import yaml

from . import revisions, validation

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "dims.yaml"
DICT_ROOT = REPO_ROOT / "dictionaries"
PROCESSED_ROOT = REPO_ROOT / "data" / "processed" / "dims"
METADATA_ROOT = REPO_ROOT / "metadata"
UNIFIED_PATH = REPO_ROOT / "data" / "unified" / "macro_dims_long.csv"

NATIONAL = "national"
PROCESSED_COLUMNS = ["date", "region", "item_code", "item_name", "value", "transformation"]
LONG_COLUMNS = [
    "date", "country", "region", "frequency", "variable", "item_code", "item_name", "value",
    "unit", "source", "source_version", "transformation", "last_updated",
]
MAX_WARNINGS = 30
_FOOTNOTE = re.compile(r"\s*\d\)\s*|\*+$")
# Kazakh letters as BNS spells region names (Жетісу, Ұлытау), and Latin letters that
# BNS occasionally types inside Cyrillic words ("Cнабжение" with a Latin C).
_KAZAKH = str.maketrans({"і": "и", "ұ": "у", "ү": "у", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "һ": "х", "ә": "а"})
_HOMOGLYPHS = str.maketrans({"a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у", "k": "к", "b": "в", "h": "н", "m": "м", "t": "т"})


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def normalise_label(label) -> str:
    """Lower-case, single-spaced, footnote markers ('1)', trailing '*') removed,
    ё -> е, Kazakh letters and Latin look-alikes folded to their Russian shapes."""
    s = _FOOTNOTE.sub(" ", str(label or ""))
    s = re.sub(r"\s+", " ", s).strip().lower().replace("ё", "е")
    s = s.translate(_KAZAKH).translate(_HOMOGLYPHS)
    # Column headers wrapped mid-word ("Горнодобы-вающая", "промышлен-\nность"): a hyphen
    # between two letters is dropped, so every dictionary regex is written hyphen-free
    # or with an optional hyphen (косвенно-измеряемые, Западно-Казахстанская).
    return re.sub(r"(?<=[а-я])-\s*(?=[а-я])", "", s)


def normalise_region_label(label) -> str:
    """As normalise_label, with the word «область» dropped: BNS writes «Акмолинская»,
    «Акмолинская область» and «Область Абай» for the same region."""
    s = normalise_label(label).replace("область", " ")
    return re.sub(r"\s+", " ", s).strip()


_FOOTNOTE_EN = re.compile(r"\s*\d/\s*|\s*\*+\s*$")


def normalise_label_en(label) -> str:
    """For English-language sources (World Bank, EIA): lower-case, single-spaced
    (header cells wrap with newlines), footnote markers ('1/', trailing '**') removed.
    Deliberately NOT normalise_label — that one folds Latin letters into Cyrillic."""
    s = _FOOTNOTE_EN.sub(" ", str(label or ""))
    return re.sub(r"\s+", " ", s).strip().lower()


_DICT_CACHE: dict[str, list[dict]] = {}


def load_dictionary(name: str) -> list[dict]:
    if name not in _DICT_CACHE:
        with (DICT_ROOT / f"{name}.csv").open(encoding="utf-8") as f:
            entries = list(csv.DictReader(f))
        for e in entries:
            e["regex"] = re.compile(e["match"])
        _DICT_CACHE[name] = entries
    return _DICT_CACHE[name]


def match_item(label, dictionary: list[dict], normaliser=normalise_label) -> tuple[str, str] | None:
    """(code, canonical name) for a label, None when nothing matches.
    Two matches is a dictionary defect, not a data fact — raise."""
    norm = normaliser(label)
    if not norm:
        return None
    hits = [e for e in dictionary if e["regex"].search(norm)]
    if len(hits) > 1:
        raise ValueError(f"label {label!r} matches several dictionary codes: {[h['code'] for h in hits]}")
    return (hits[0]["code"], hits[0]["name_ru"]) if hits else None


def match_region(label) -> tuple[str, str] | None:
    """(region code, canonical name) for a region label; the country total is coded 'national'."""
    hit = match_item(label, load_dictionary("regions"), normalise_region_label)
    if hit is None:
        return None
    code, name = hit
    return (NATIONAL if code == "KZ" else code, name)


def normalise_code(cell) -> str | None:
    """Item codes as they sit in a sheet: numbers become two-digit strings ('5' -> '05')."""
    if cell is None:
        return None
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return f"{int(cell):02d}"
    s = str(cell).strip()
    return s or None


# ---------------------------------------------------------------- processed layer

def write_processed(dataset_id: str, records: list[dict], transformation: str = "level") -> Path:
    """A record may carry its own `transformation` ('forecast' for the months past EIA's
    last historical month, for the World Bank outlook years); `transformation` is the
    default for the rest."""
    PROCESSED_ROOT.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_ROOT / f"{dataset_id.lower()}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROCESSED_COLUMNS)
        writer.writeheader()
        for r in records:
            writer.writerow({"date": r["date"], "region": r.get("region") or NATIONAL, "item_code": r["item_code"],
                             "item_name": r["item_name"], "value": r["value"],
                             "transformation": r.get("transformation") or transformation})
    return path


def load_processed(dataset_id: str) -> list[dict]:
    path = PROCESSED_ROOT / f"{dataset_id.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.setdefault("region", NATIONAL)
        r["region"] = r["region"] or NATIONAL
    return rows


def _key(r: dict) -> tuple[str, str, str]:
    return (r["date"], r.get("region") or NATIONAL, r["item_code"])


# ---------------------------------------------------------------- validation and revisions

def validate(records: list[dict], dataset_id: str, frequency: str) -> validation.ValidationResult:
    """The scalar checks, applied per (region, item): types on every row, duplicates on
    (date, region, item), frequency gaps and outliers within each series. Warnings are
    capped per dataset — a regional breakdown has hundreds of series."""
    result = validation.ValidationResult(indicator_id=dataset_id)
    if not records:
        result.add_error("No records to validate (empty dataset).")
        return result
    missing = {"date", "item_code", "value"} - set(records[0].keys())
    if missing:
        result.add_error(f"Missing expected columns: {missing}")
        return result
    types = validation.validate_types(records, dataset_id)
    result.errors.extend(types.errors)
    seen, dupes = set(), set()
    for r in records:
        k = _key(r)
        if k in seen:
            dupes.add(k)
        seen.add(k)
    if dupes:
        result.add_error(f"Duplicate (date, region, item) keys: {sorted(dupes)[:10]}")
    by_series: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        by_series.setdefault((r.get("region") or NATIONAL, r["item_code"]), []).append(r)
    warnings: list[str] = []
    for (region, code), rows in by_series.items():
        tag = code if region == NATIONAL else f"{code}@{region}"
        for sub in (validation.validate_frequency(rows, dataset_id, frequency),
                    validation.validate_outliers(rows, dataset_id)):
            warnings.extend(f"[{tag}] {w}" for w in sub.warnings)
    if len(warnings) > MAX_WARNINGS:
        warnings = warnings[:MAX_WARNINGS] + [f"... {len(warnings) - MAX_WARNINGS} more warnings not listed"]
    result.warnings.extend(warnings)
    result.ok = result.ok and not result.errors
    return result


def detect_revisions(dataset_id: str, source: str, old_records: list[dict], new_records: list[dict],
                     detected_date: date) -> list[revisions.Revision]:
    """Same contract as lib/revisions.detect_revisions, keyed on (date, region, item)."""
    old = {_key(r): r.get("value") for r in old_records}
    out = []
    for r in new_records:
        old_val, new_val = old.get(_key(r)), r.get("value")
        if old_val not in (None, "") and new_val is not None and float(old_val) != float(new_val):
            region = r.get("region") or NATIONAL
            period = f"{r['date']} {r['item_code']}" + ("" if region == NATIONAL else f" @{region}")
            out.append(revisions.Revision(indicator_id=dataset_id, period=period, old_value=float(old_val),
                                          new_value=float(new_val), detected_date=detected_date.isoformat(), source=source))
    return out


# ---------------------------------------------------------------- unified layer

def build_long(datasets: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for ds in datasets:
        meta_path = METADATA_ROOT / ds["agency"] / f"{ds['id'].lower()}.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        for rec in load_processed(ds["id"]):
            rows.append({
                "date": rec["date"], "country": ds.get("country", "KZ"), "region": rec["region"], "frequency": ds["frequency"],
                "variable": ds["id"], "item_code": rec["item_code"], "item_name": rec["item_name"],
                "value": rec["value"], "unit": ds["unit"], "source": ds["agency"],
                "source_version": meta.get("download_date"), "transformation": rec.get("transformation", "level"),
                "last_updated": meta.get("last_update_date"),
            })
    rows.sort(key=lambda r: (r["variable"], r["item_code"], r["region"], r["date"]))
    return rows


def write_long_csv(rows: list[dict], path: Path | None = None) -> Path:
    path = path or UNIFIED_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LONG_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path
