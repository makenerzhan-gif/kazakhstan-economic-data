"""REGIONAL_PRODUCT_BALANCE: an apparent-consumption balance by region and month, derived from
four item-level datasets (no download):

    PROD          INDUSTRY_PRODUCTION_PHYSICAL_BY_REGION_MONTHLY   production (Taldau 701608)
    EXP / IMP     EXPORTS_ / IMPORTS_VOLUME_BY_REGION_PRODUCT       customs trade (BNS 446905/446906)
    SHIP_TOTAL    INDUSTRY_SHIPMENTS_BY_REGION_MONTHLY .TOTAL       shipments of own output (701622)
    SHIP_DOM      INDUSTRY_SHIPMENTS_BY_REGION_MONTHLY .DOM         … of which to the domestic market
    APPARENT_USE  PROD − EXP + IMP

in tonnes, for the products listed in dictionaries/hs_balance_products.csv (codes shared with
the Taldau product list). Taldau's unit (item_name «…, тысяча тонн») is converted to tonnes;
a product in any other unit is left out. National rows use the same sources.

BNS publishes no regional balance; this is a construction with two known distortions, so it
is a cross-check, not a statistic:
  * customs trade is by the region where the trading company is registered -- crude oil is
    exported by companies registered in Atyrau and Astana, not only where it is produced;
  * stocks are ignored, and a region's confidential production is absent (then nothing is
    written for that product and month).
SHIP_DOM is the direct official measure of a region's own output going to the home market;
where APPARENT_USE and PROD − (SHIP_TOTAL − SHIP_DOM) agree, the trade attribution is sound.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

TO_TONNES = {"тысяча тонн": 1000.0, "тыс. тонн": 1000.0, "тонна (метрическая)": 1.0, "тонна": 1.0, "тонн": 1.0}
ARTICLES = {"PROD": "производство", "EXP": "экспорт", "IMP": "импорт", "APPARENT_USE": "видимое потребление (производство − экспорт + импорт)",
            "SHIP_TOTAL": "отгружено собственной продукции", "SHIP_DOM": "отгружено на внутренний рынок"}


def _factor(item_name: str) -> float | None:
    m = re.search(r",\s*([^,]+)$", item_name or "")
    return TO_TONNES.get(m.group(1).strip().lower()) if m else None


def _series(ds_id: str) -> dict[tuple[str, str, str], tuple[float, str]]:
    return {(r["date"], r["region"], r["item_code"]): (float(r["value"]), r["item_name"]) for r in dims.load_processed(ds_id)}


def build(prod: dict, ship: dict, exp: dict, imp: dict, products: dict[str, str]) -> list[dict]:
    out = []
    for (d, region, code), (value, name) in prod.items():
        if code not in products:
            continue
        f = _factor(name)
        if f is None:
            continue
        e, i = exp.get((d, region, code)), imp.get((d, region, code))
        vals = {"PROD": value * f}
        if e is not None and i is not None:
            vals.update(EXP=e[0], IMP=i[0], APPARENT_USE=value * f - e[0] + i[0])
        for art, suffix in (("SHIP_TOTAL", ".TOTAL"), ("SHIP_DOM", ".DOM")):
            s = ship.get((d, region, code + suffix))
            sf = _factor(s[1]) if s else None
            if s and sf:
                vals[art] = s[0] * sf
        for art, v in vals.items():
            out.append({"date": d, "region": region, "item_code": f"{code}.{art}",
                        "item_name": f"{products[code]} — {ARTICLES[art]}, тонн", "value": round(v, 3)})
    return out


def fetch(ds: dict) -> tuple[list[dict], dict]:
    products = {e["code"]: e["name_ru"] for e in dims.load_dictionary("hs_balance_products") if e["code"] != "TOTAL"}
    prod = _series("INDUSTRY_PRODUCTION_PHYSICAL_BY_REGION_MONTHLY")
    ship = _series("INDUSTRY_SHIPMENTS_BY_REGION_MONTHLY")
    exp = _series("EXPORTS_VOLUME_BY_REGION_PRODUCT")
    imp = _series("IMPORTS_VOLUME_BY_REGION_PRODUCT")
    if not (prod and exp and imp):
        raise validation.StructuralChangeError(
            "STRUCTURAL CHANGE DETECTED in derived/REGIONAL_PRODUCT_BALANCE\nWHAT CHANGED: an input dataset is empty "
            "(run the production and regional trade datasets first)")
    records = build(prod, ship, exp, imp, products)
    skipped = sorted(set(products) - {r["item_code"].split(".")[0] for r in records})
    return records, {"frequency": "monthly", "source_url": "", "dataset_id": "derived",
                     "note": ds.get("note", ""), "warnings": [f"products without a tonnage production series: {skipped}"] if skipped else []}
