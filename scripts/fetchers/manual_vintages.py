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


# ---------------------------------------------------------------- sovereign ratings (added 2026-11-10)
# config/sovereign_ratings.yaml: one row per rating action. Monthly step series of the rating in force at the end of
# each month, on the common 21-notch scale (AAA/Aaa = 21 ... BBB-/Baa3 = 12, the investment-grade floor ... C/D = 1).
SCALE_SP = ["D", "C", "CC", "CCC-", "CCC", "CCC+", "B-", "B", "B+", "BB-", "BB", "BB+", "BBB-", "BBB", "BBB+",
            "A-", "A", "A+", "AA-", "AA", "AA+", "AAA"]
SCALE_MOODYS = ["C", "C", "Ca", "Caa3", "Caa2", "Caa1", "B3", "B2", "B1", "Ba3", "Ba2", "Ba1", "Baa3", "Baa2", "Baa1",
                "A3", "A2", "A1", "Aa3", "Aa2", "Aa1", "Aaa"]
OUTLOOK = {"stable": 0, "positive": 1, "negative": -1, "review_up": 1, "review_down": -1, "developing": 0}
AGENCY_NAMES = {"SP": "S&P Global Ratings", "MOODYS": "Moody's", "FITCH": "Fitch Ratings"}


def rating_notch(agency: str, rating: str) -> int:
    scale = SCALE_MOODYS if agency == "MOODYS" else SCALE_SP
    if rating not in scale:
        raise ValueError(f"{agency}: unknown rating {rating!r}")
    return len(scale) - 1 - scale[::-1].index(rating)   # the highest position (Moody's C appears twice)


def rating_records(doc: dict, ds: dict, today=None) -> list[dict]:
    import pandas as pd
    end = pd.Timestamp(today or pd.Timestamp.today()).to_period("M")
    out, notches = [], {}
    for agency, actions in doc["actions"].items():
        if agency not in AGENCY_NAMES:
            _structural(ds, f"unknown agency {agency}")
        rows = sorted(actions, key=lambda a: str(a["date"]))
        for a in rows:
            if a["outlook"] not in OUTLOOK:
                _structural(ds, f"{agency} {a['date']}: unknown outlook {a['outlook']!r}")
            try:
                a["_n"] = rating_notch(agency, a["rating"])
            except ValueError as e:
                _structural(ds, str(e))
        month, i, state, series = pd.Period(str(rows[0]["date"])[:7], "M"), 0, None, {}
        while month <= end:
            while i < len(rows) and pd.Period(str(rows[i]["date"])[:7], "M") <= month:
                state, i = rows[i], i + 1
            series[month] = state
            month += 1
        name = AGENCY_NAMES[agency]
        for m, a in series.items():
            d = m.start_time.strftime("%Y-%m-%d")
            out += [{"date": d, "region": dims.NATIONAL, "item_code": f"{agency}.RATING", "item_name": f"{name}: рейтинг (шкала 1-21, BBB-/Baa3 = 12)", "value": float(a["_n"])},
                    {"date": d, "region": dims.NATIONAL, "item_code": f"{agency}.OUTLOOK", "item_name": f"{name}: прогноз (+1 позитивный / пересмотр на повышение, 0 стабильный, -1 негативный)", "value": float(OUTLOOK[a["outlook"]])}]
            notches.setdefault(d, []).append(a["_n"] + OUTLOOK[a["outlook"]] / 3)
    for d, v in notches.items():
        if len(v) == 3:
            out.append({"date": d, "region": dims.NATIONAL, "item_code": "AVG.RATING_OUTLOOK",
                        "item_name": "Среднее трёх агентств: рейтинг + прогноз/3", "value": round(sum(v) / 3, 4)})
    return out


def fetch_ratings(ds: dict) -> tuple[list[dict], dict]:
    doc = yaml.safe_load((REPO_ROOT / ds["file"]).read_text(encoding="utf-8"))
    records = rating_records(doc, ds)
    return records, {"frequency": "monthly", "source_url": "https://nationalbank.kz/ru/news/informacionnye-soobshcheniya",
                     "dataset_id": ds["file"], "note": ds.get("note", "") + " " + doc.get("source", "")}


# ---------------------------------------------------------------- hand-kept annual tables (added 2026-11-10)
def step_records(doc: dict, ds: dict, today=None) -> list[dict]:
    """Values keyed «YYYY-MM» (the month a level took effect), held until the next one, monthly to `today`; a null value opens a gap."""
    import pandas as pd
    end = pd.Timestamp(today or pd.Timestamp.today()).to_period("M")
    out = []
    for item in doc["items"]:
        changes = {}
        for key, value in item["values"].items():
            try:
                changes[pd.Period(str(key), "M")] = None if value is None else float(value)
            except ValueError:
                _structural(ds, f"{item['code']}: bad month {key!r}")
        month, level = min(changes), None
        while month <= end:
            level = changes.get(month, level)
            if level is None:                    # «YYYY-MM: null» opens a gap: the level of those months was not read in a source
                month += 1
                continue
            out.append({"date": month.start_time.strftime("%Y-%m-%d"), "region": dims.NATIONAL, "item_code": item["code"],
                        "item_name": item["name"], "value": level})
            month += 1
    return out


def table_records(doc: dict, ds: dict) -> list[dict]:
    if ds.get("step") == "monthly":
        return step_records(doc, ds)
    out = []
    for item in doc["items"]:
        for year, value in item["values"].items():
            if not isinstance(year, int) or not 1990 <= year <= 2100:
                _structural(ds, f"{item['code']}: bad year {year!r}")
            out.append({"date": f"{year}-12-31", "region": dims.NATIONAL, "item_code": item["code"],
                        "item_name": item["name"], "value": float(value)})
    return out


def fetch_table(ds: dict) -> tuple[list[dict], dict]:
    doc = yaml.safe_load((REPO_ROOT / ds["file"]).read_text(encoding="utf-8"))
    records = table_records(doc, ds)
    if not records:
        _structural(ds, "no values")
    return records, {"frequency": ds["frequency"], "source_url": "", "dataset_id": ds["file"],
                     "note": ds.get("note", "") + " " + doc.get("source", "")}
