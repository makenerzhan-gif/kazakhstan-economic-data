"""CPI basket weights of Kazakhstan by COICOP division (added 2026-09-27).

BNS publishes no table of its CPI weights by year. What exists:

* CPI_WEIGHTS (official):
  - 2005-2019, the 12 COICOP-1999 divisions: the weights BNS reports to the IMF, IMF CPI
    dataflow (SDMX 3.0, IMF.STA/CPI, key KAZ.CPI.*.WGT_PT.M). The monthly observations are
    constant within a year except January 2014, which repeats 2013 -- so each year is read
    from its December. Checked: CP01+CP02 equals BNS's published food share (2014 36.97 vs
    37.0; 2016 36.73 vs 36.7; 2017 37.64 vs 37.6; 2019 38.77 vs 38.8), and the weights
    reproduce the national year-to-date CPI from the division indices within 0.02-0.07
    index points (2008 0.10, 2009 0.23).
  - 2022: the full scheme of the BNS brochure «Индекс потребительских цен: вопросы и
    ответы» (divisions, food groups, goods/food/non-food/services).
  - FOOD / NONFOOD / SERVICES shares from BNS's January releases 2023-2026 (stat.gov.kz) and
    press reprints of them for 2014, 2016, 2017, 2019, 2020 (status official_secondary).
  The last two come from data/reference/bns_cpi_weights.csv (a hand-kept seed; see its
  README entry). Item names say the source.

* CPI_WEIGHTS_ESTIMATED (derived, output: estimated): the division weights 2020-2026
  recovered from BNS's contributions to year-to-date CPI growth: the contribution of a
  division is w·(I_ytd − 100)/100, so per year w = 100·Σ c·(I−100) / Σ (I−100)², over
  months where |I − 100| > 0.05; then CP01+CP02 is rescaled to the published food share
  and the other divisions to the rest. Against the official 2022 scheme the error is
  0.1-0.5 pp for most divisions (CP01 38.87 vs 38.75); up to ±2 pp for CP04/CP06/CP12.
  From 2026 BNS uses COICOP 2018 (CP12_2018 insurance and financial services, CP13_2018
  personal care and other).

Dates: YYYY-12-31 (the year the weights apply to); percent of the basket.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import imf_dims  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

IMF_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/+/KAZ.CPI.*.WGT_PT.M"
           "?dimensionAtObservation=TIME_PERIOD&attributes=none&measures=all")
SEED = Path(__file__).resolve().parents[2] / "data" / "reference" / "bns_cpi_weights.csv"
DIVISION_NAMES = {
    "CP01": "Продукты питания и безалкогольные напитки", "CP02": "Алкогольные напитки и табачные изделия",
    "CP03": "Одежда и обувь", "CP04": "Жилищные услуги, вода, электроэнергия, газ и другие виды топлива",
    "CP05": "Предметы домашнего обихода, бытовая техника и уход за жилищем", "CP06": "Здравоохранение",
    "CP07": "Транспорт", "CP08": "Связь", "CP09": "Отдых и культура", "CP10": "Образование",
    "CP11": "Рестораны и гостиницы", "CP12": "Разные товары и услуги",
    "CP12_2018": "Страхование и финансовые услуги (КООЛИЦ 2018)",
    "CP13_2018": "Личный уход, социальная защита и прочие товары и услуги (КООЛИЦ 2018)"}
# contribution tables name CP05 by its item slug before 2026
CONTRIBUTION_ALIASES = {"CP05": ["CP05", "predmety_domashnego_obikhoda"]}


def imf_weights(payload: dict) -> dict[tuple[int, str], float]:
    """{(year, division): weight} from the IMF SDMX-JSON answer, December observations."""
    d = payload["data"]
    st = d["structures"][0]
    series_dims = st["dimensions"]["series"]
    pos = next(i for i, dim in enumerate(series_dims) if dim["id"] in ("COICOP_1999", "COICOP"))
    times = [v["value"] for v in st["dimensions"]["observation"][0]["values"]]
    out = {}
    for key, s in d["dataSets"][0]["series"].items():
        code = series_dims[pos]["values"][int(key.split(":")[pos])]["id"]
        for k, v in s.get("observations", {}).items():
            t = times[int(k)]
            if v and v[0] is not None and t.endswith("-M12"):
                out[(int(t[:4]), code)] = float(v[0])
    return out


def seed_rows() -> list[dict]:
    with SEED.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def official_records(imf: dict[tuple[int, str], float], seed: list[dict]) -> list[dict]:
    records = []
    for year in sorted({y for y, _ in imf}):
        total = sum(v for (y, _), v in imf.items() if y == year)
        if abs(total - 100) > 0.05:
            raise validation.StructuralChangeError(f"cpi_weights: IMF weights for {year} sum to {total:.3f}, not 100")
    for (year, code), v in sorted(imf.items()):
        records.append({"date": f"{year}-12-31", "region": dims.NATIONAL, "item_code": code,
                        "item_name": f"{DIVISION_NAMES.get(code, code)} (БНС через МВФ, IMF.STA/CPI)", "value": round(v, 4)})
    for r in seed:
        records.append({"date": f"{r['year']}-12-31", "region": dims.NATIONAL, "item_code": r["code"],
                        "item_name": f"{r['name_ru']} ({'БНС' if r['status'] == 'official' else 'БНС, по публикации в прессе'})",
                        "value": float(r["weight_pct"])})
    keys = [(r["date"], r["item_code"]) for r in records]
    if len(keys) != len(set(keys)):
        raise validation.StructuralChangeError("cpi_weights: the IMF and the seed give the same year and item twice")
    return records


def estimate(contrib: dict[tuple[str, str], float], ytd: dict[tuple[str, str], float],
             food_share: dict[int, float]) -> list[dict]:
    """Division weights per year from contributions (see the module docstring)."""
    years = sorted({int(d[:4]) for d, _ in contrib})
    out = []
    for year in years:
        raw = {}
        for code in DIVISION_NAMES:
            num = den = 0.0
            for d, c_code in contrib:
                if int(d[:4]) != year or c_code not in CONTRIBUTION_ALIASES.get(code, [code]):
                    continue
                index = ytd.get((d, code))
                if index is None or abs(index - 100) <= 0.05:
                    continue
                num += contrib[(d, c_code)] * (index - 100)
                den += (index - 100) ** 2
            if den > 0:
                raw[code] = 100 * num / den
        if len(raw) < 11:
            continue
        food = raw.get("CP01", 0) + raw.get("CP02", 0)
        rest = sum(v for k, v in raw.items() if k not in ("CP01", "CP02"))
        target_food = food_share.get(year, 100 * food / (food + rest))
        for code, v in raw.items():
            scaled = v * (target_food / food if code in ("CP01", "CP02") else (100 - target_food) / rest)
            out.append({"date": f"{year}-12-31", "region": dims.NATIONAL, "item_code": code,
                        "item_name": f"{DIVISION_NAMES[code]} (оценка по вкладам в ИПЦ)", "value": round(scaled, 3)})
    return out


def fetch(ds: dict) -> tuple[list[dict], dict]:
    if ds.get("output") == "estimated":
        contrib = {(r["date"], r["item_code"]): float(r["value"]) for r in dims.load_processed("CPI_CONTRIBUTION_YTD")
                   if r["region"] == dims.NATIONAL}
        ytd = {(r["date"], r["item_code"]): float(r["value"]) for r in dims.load_processed("CPI_DETAIL_YTD")
               if r["region"] == dims.NATIONAL}
        food = {int(r["year"]): float(r["weight_pct"]) for r in seed_rows() if r["code"] == "FOOD"}
        records = estimate(contrib, ytd, food)
        if not records:
            raise validation.StructuralChangeError("cpi_weights: no year could be estimated -- run CPI_CONTRIBUTION_YTD first")
        return records, {"frequency": "annual", "source_url": "", "dataset_id": "derived", "note": ds.get("note", "")}
    fresh = imf_dims.stored_if_fresh(ds, "imf", ds["id"])
    if fresh:
        return fresh
    import requests
    resp = requests.get(IMF_URL, headers={"Accept": "application/json", "User-Agent": "KZEconDataPipeline/1.0"}, timeout=180)
    resp.raise_for_status()
    content = resp.content
    today = date.today()
    path = raw_store.save_raw_bytes("imf", ds["id"], today, "json", content)
    raw_store.write_download_manifest("imf", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": IMF_URL, "seed": str(SEED.name)})
    imf = imf_weights(json.load(io.BytesIO(content)))
    if len({y for y, _ in imf}) < 10:
        raise validation.StructuralChangeError(f"cpi_weights: only {len({y for y, _ in imf})} years of IMF weights")
    return official_records(imf, seed_rows()), {"frequency": "annual", "source_url": IMF_URL,
                                                "dataset_id": "IMF.STA/CPI KAZ WGT_PT + data/reference/bns_cpi_weights.csv",
                                                "note": ds.get("note", "")}
