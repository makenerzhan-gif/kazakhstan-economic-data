"""Forecast vintages kept by hand in config/: the Government's macroeconomic forecast (ПСЭР,
config/gov_forecast_vintages.yaml) and the National Bank's forecasting rounds
(config/nbk_forecast_rounds.yaml). Added 2026-11-07.

Neither is published in a form a scheduled parser could rely on (PDF/DOCX appendices whose
layout changes, a gov.kz listing that misfiles documents, forecast charts pasted as images in
the NBK's xlsx annex), and each gets a new vintage only a few times a year, so the numbers are
transcribed into the YAML files, which name the document of every vintage. This fetcher only
turns them into item-level records: date = the target year (YYYY-12-31), item =
V<vintage>.<variable> (V2026_08.BRENT = the Brent assumption of the August 2026 vintage for
that year). Ranges become <VAR>_LO and <VAR>_HI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

GOV_FIELDS = {  # yaml key: (code, Russian name)
    "gdp_kzt_bn": ("GDP_KZT_BN", "ВВП, млрд тенге"),
    "real_gdp": ("REAL_GDP", "Реальный рост ВВП, % к предыдущему году"),
    "gdp_usd_bn": ("GDP_USD_BN", "ВВП, млрд долларов США"),
    "usdkzt": ("USDKZT", "Расчётный курс, тенге за доллар США (ВВП в тенге / ВВП в долларах)"),
    "brent": ("BRENT", "Цена нефти Brent, долларов за баррель (базовый сценарий)"),
    "oil_mt": ("OIL_MT", "Добыча нефти и газового конденсата, млн тонн"),
    "cpi": ("CPI", "Инфляция (декабрь к декабрю), %"),
}
NBK_FIELDS = {
    "gdp": ("GDP", "Рост реального ВВП, %"),
    "cpi": ("CPI", "Инфляция (декабрь к декабрю), %"),
    "brent": ("BRENT", "Цена нефти Brent, среднегодовая, долларов за баррель"),
}


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"manual/{ds['id']}: {what} ({ds['file']})")


def vintage_records(entries: list[dict], key: str, fields: dict, ds: dict) -> list[dict]:
    out = []
    for e in entries:
        tag = "V" + str(e[key]).replace("-", "_")
        for year, values in e["years"].items():
            for field, value in values.items():
                if field == "near":
                    continue
                if field not in fields:
                    _structural(ds, f"unknown field {field!r} in {e[key]}")
                code, name = fields[field]
                pairs = [(code, name, value)]
                if isinstance(value, list):
                    if len(value) != 2 or value[0] > value[1]:
                        _structural(ds, f"{e[key]} {year} {field}: a range must be [low, high], got {value}")
                    pairs = [(f"{code}_LO", f"{name}, нижняя граница", value[0]), (f"{code}_HI", f"{name}, верхняя граница", value[1])]
                for c, n, v in pairs:
                    out.append({"date": f"{int(year)}-12-31", "region": dims.NATIONAL, "item_code": f"{tag}.{c}",
                                "item_name": f"{n} (вариант {e[key]})", "value": float(v)})
    return out


def fetch(ds: dict) -> tuple[list[dict], dict]:
    doc = yaml.safe_load((REPO_ROOT / ds["file"]).read_text(encoding="utf-8"))
    if ds["file"].endswith("gov_forecast_vintages.yaml"):
        records = vintage_records(doc["vintages"], "vintage", GOV_FIELDS, ds)
    else:
        records = vintage_records(doc["rounds"], "round", NBK_FIELDS, ds)
    if not records:
        _structural(ds, "no values")
    return records, {"frequency": "annual", "source_url": doc.get("base_url", ""), "dataset_id": ds["file"],
                     "note": ds.get("note", "") + " " + doc.get("source", "")}
