"""Import-weighted nominal effective exchange rate of the tenge (derived, added 2026-09-27).

Inputs (no download): EXCHANGE_RATES_OFFICIAL_MONTHLY (KZT per unit of 18 currencies,
monthly means) and IMPORTS_BY_PARTNER_COMTRADE (imports by partner country, annual).

Weights: a partner's imports are assigned to its currency (CURRENCY_OF; euro-area members
from their euro adoption year, dollarised or dollar-pegged economies to USD); partners whose
currency has no NBK rate are left out and the rest renormalised. Weights of year y are the
shares of year y-1 (the index needs no revision when year y's trade arrives). Coverage --
the share of the basket that is assigned -- is published as its own item.

Index: a geometric (Törnqvist-style) chain of monthly changes,
    ln I(m) - ln I(m-1) = Σ_c w_c,y(m) · ln[ e_c(m-1) / e_c(m) ],   e = KZT per unit of c,
over the currencies with a rate in both months (weights renormalised among them), so a
currency entering or leaving the table does not move the index. Rebased to the 2020 mean =
100. UP = TENGE APPRECIATION (the NBK's NEER convention).

    NEER_CONSUMER   weights = consumer-goods imports (BEC 112, 122, 522, 61, 62, 63)
    NEER_TOTAL      weights = all goods imports
    COVERAGE_*      share of the basket's imports assigned to a currency, %

History (2026-09-28): the rates reach back to 1993-11 (EXCHANGE_RATES_OFFICIAL_MONTHLY: the NBK
archive 1993-1999 before the daily report) and Comtrade to 1995, Kazakhstan's first reported
year, so the index starts in 1995-12 (weights of 1995 used from 1996-01). Before 1999 the
euro-area partners have no rate in the table (their national currencies are not carried) and
are left out of the basket -- see COVERAGE_*. A basket-year that Comtrade converts only in
part (INCOMPLETE_SHARE: CONSUMER 2000, 36 mln USD of 4 987 total, against 661 in 1999) is not
used: its year takes the last complete year's structure (carry_forward), and the weights
dataset names the year whose structure it holds.

Weights dataset (output: weights): <BASKET>.<currency> = weight in year y, %.
"""
from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

EURO_SINCE = {40: 1999, 56: 1999, 196: 2008, 233: 2011, 246: 1999, 251: 1999, 276: 1999, 300: 2001, 372: 1999,
              380: 1999, 428: 2014, 440: 2015, 442: 1999, 470: 2008, 528: 1999, 620: 1999, 703: 2009, 705: 2007,
              724: 1999, 191: 2023, 499: 2002, 492: 1999, 674: 1999, 20: 1999}
CURRENCY_OF = {643: "RUB", 156: "CNY", 792: "TRY", 860: "UZS", 842: "USD", 112: "BYN", 616: "PLN", 699: "INR",
               757: "CHF", 438: "CHF", 410: "KRW", 826: "GBP", 417: "KGS", 203: "CZK", 762: "TJS", 392: "JPY",
               784: "AED", 31: "AZN", 840: "USD",   # 840: the United States in Kazakhstan's 1995-1999 reports
               # dollarised, or pegged to the dollar
               218: "USD", 222: "USD", 591: "USD", 344: "USD"}
INCOMPLETE_SHARE = 0.05   # a sub-basket below 5% of all goods imports that year is a partial conversion (normal 12-20%)
BASKET_LABELS = {"CONSUMER": "потребительского импорта (BEC 112, 122, 522, 61, 62, 63)", "TOTAL": "всего импорта товаров"}


def currency(partner: int, year: int) -> str | None:
    if partner in EURO_SINCE and year >= EURO_SINCE[partner]:
        return "EUR"
    return CURRENCY_OF.get(partner)


def weights(imports: dict[tuple[str, int, int], float]) -> tuple[dict[tuple[str, int], dict[str, float]], dict[tuple[str, int], float]]:
    """{(basket, year): {currency: share}} and {(basket, year): coverage %} from {(basket, partner, year): value}."""
    by: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    world: dict[tuple[str, int], float] = {}
    for (basket, partner, year), v in imports.items():
        if partner == 0:
            world[(basket, year)] = v
            continue
        c = currency(partner, year)
        if c:
            by[(basket, year)][c] += v
    shares, coverage = {}, {}
    for key, cur in by.items():
        total = sum(cur.values())
        if key[0] != "TOTAL" and world.get(("TOTAL", key[1])) and world.get(key, 0) < INCOMPLETE_SHARE * world[("TOTAL", key[1])]:
            continue          # see INCOMPLETE_SHARE
        if total > 0 and world.get(key):
            shares[key] = {c: v / total for c, v in cur.items()}
            coverage[key] = 100 * total / world[key]
    return shares, coverage


def carry_forward(by_year: dict[int, dict[str, float]]) -> dict[int, tuple[int, dict[str, float]]]:
    """{year: (year whose structure is used, shares)} over first..last year: a year without
    weights takes the last year before it that has them."""
    out: dict[int, tuple[int, dict[str, float]]] = {}
    if not by_year:
        return out
    for y in range(min(by_year), max(by_year) + 1):
        out[y] = (y, by_year[y]) if y in by_year else out[y - 1]
    return out


def chain(rates: dict[str, dict[str, float]], w_by_year: dict[int, dict[str, float]]) -> dict[str, float]:
    months = sorted({m for r in rates.values() for m in r})
    out, level = {}, None
    for prev, m in zip(months, months[1:]):
        w = w_by_year.get(int(m[:4]) - 1)
        if not w:
            continue
        live = {c: s for c, s in w.items() if prev in rates.get(c, {}) and m in rates.get(c, {})}
        total = sum(live.values())
        if total <= 0:
            continue
        if level is None:
            level, out[prev] = 0.0, 0.0
        level += sum(s / total * math.log(rates[c][prev] / rates[c][m]) for c, s in live.items())
        out[m] = level
    base = [v for m, v in out.items() if m.startswith("2020")]
    if len(base) < 12:
        raise validation.StructuralChangeError("neer_import: the index does not cover 2020, cannot rebase")
    b = sum(base) / len(base)
    return {m: 100 * math.exp(v - b) for m, v in out.items()}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    rates: dict[str, dict[str, float]] = defaultdict(dict)
    for r in dims.load_processed("EXCHANGE_RATES_OFFICIAL_MONTHLY"):
        rates[r["item_code"]][r["date"]] = float(r["value"])
    imports = {}
    for r in dims.load_processed("IMPORTS_BY_PARTNER_COMTRADE"):
        basket, partner = r["item_code"].split(".")
        imports[(basket, int(partner), int(r["date"][:4]))] = float(r["value"])
    if not rates or not imports:
        raise validation.StructuralChangeError(
            "neer_import: an input is empty -- run EXCHANGE_RATES_OFFICIAL_MONTHLY and IMPORTS_BY_PARTNER_COMTRADE first")
    shares, coverage = weights(imports)
    by_basket = {basket: carry_forward({y: s for (b, y), s in shares.items() if b == basket}) for basket in BASKET_LABELS}
    records = []
    if ds.get("output") == "weights":
        for basket, years in by_basket.items():
            for year, (source, cur) in sorted(years.items()):
                for c, s in cur.items():
                    records.append({"date": f"{year + 1}-12-31", "region": dims.NATIONAL, "item_code": f"{basket}.{c}",
                                    "item_name": f"Вес {c} в NEER по структуре {BASKET_LABELS[basket]} {source} г., %", "value": round(100 * s, 4)})
                records.append({"date": f"{year + 1}-12-31", "region": dims.NATIONAL, "item_code": f"COVERAGE_{basket}",
                                "item_name": f"Доля {BASKET_LABELS[basket]} {source} г., отнесённая к валютам с курсом НБК, %",
                                "value": round(coverage[(basket, source)], 4)})
        return records, {"frequency": "annual", "source_url": "", "dataset_id": "derived", "note": ds.get("note", "")}
    for basket in BASKET_LABELS:
        index = chain(rates, {y: s for y, (_, s) in by_basket[basket].items()})
        records += [{"date": m, "region": dims.NATIONAL, "item_code": f"NEER_{basket}",
                     "item_name": f"Номинальный эффективный курс тенге, веса {BASKET_LABELS[basket]} (2020 = 100, рост = укрепление)",
                     "value": round(v, 4)} for m, v in index.items()]
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "monthly", "source_url": "", "dataset_id": "derived", "note": ds.get("note", "")}
