"""Harmonised panel of Kazakhstan's natural-resource series: one checked value per indicator and year.

Inputs (all already in the repository, written by the natural-capital workflow):
  data/raw/taldau_resources/taldau_resources_long.csv      BNS Taldau 701608 / 701622
  data/raw/resource_history/comtrade_kazakhstan.csv         UN Comtrade, Kazakhstan's own records
  data/raw/resource_history/comtrade_mirror_kazakhstan.csv  UN Comtrade, partners' imports from KZ
  data/raw/resource_history/eia_kazakhstan.csv              EIA international
  data/raw/resource_history/manual_uploads/energy_institute_2026_kazakhstan_narrow.csv
  data/raw/resource_history/usgs_myb/                       USGS Minerals Yearbook (scripts/usgs_myb_parse.py)
  data/raw/bns_seea/seea_mineral_asset_account_long.csv     BNS SEEA asset account (reserves)

Outputs (data/processed/natural_resources/):
  natural_resources_long.csv   every source, harmonised units: var, name, concept, unit, source, series, year, value
  natural_resources_panel.csv  one value per var-year: picked by source priority, skipping values
                               that fail QA (spike, identity, unit, confidential); flags kept
  catalog.csv                  indicator list: code, name, unit, concept, sources in priority order
QA results go to reports/resource_qa.{json,md} (scripts/qa_resources.py).

Concept tags keep different definitions apart: gross vs marketable gas, ore vs concentrate vs metal,
mine vs refined output. Values of different concepts are never put in one row.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import qa_resources as qa  # noqa: E402

RAW = ROOT / "data" / "raw"
RH = RAW / "resource_history"
OUT = ROOT / "data" / "processed" / "natural_resources"

TP = "Произведено продукции в натуральном выражении"
TK = {"P": TP, "T": "отгружено всего", "D": "отгружено на внутренний рынок"}
TSER = {"P": "производство", "T": "отгружено всего", "D": "отгружено на внутренний рынок"}


# ------------------------------------------------------------------ loaders
def load_taldau():
    d = defaultdict(dict)
    f = RAW / "taldau_resources" / "taldau_resources_long.csv"
    if f.exists():
        for r in csv.DictReader(f.open(encoding="utf-8")):
            if r["index_id"] in ("701608", "701622"):
                d[(r["index_name"], r["item"])][int(r["year"])] = float(r["value"])
    return d


def load_comtrade(name):
    d = defaultdict(lambda: defaultdict(float))
    f = RH / name
    if f.exists():
        for r in csv.DictReader(f.open(encoding="utf-8")):
            for fld in ("value_usd", "net_weight_kg"):
                x = r.get(fld)
                if x not in (None, "", "None"):
                    d[(r["flow"], str(r["hs"]), fld)][int(r["year"])] += float(x)
    return d


def load_eia():
    d = defaultdict(dict)
    f = RH / "eia_kazakhstan.csv"
    if f.exists():
        for r in csv.DictReader(f.open(encoding="utf-8")):
            try:
                d[r["series_id"]][int(r["year"])] = float(r["value"])
            except ValueError:
                pass
    return d


def load_ei():
    d = defaultdict(dict)
    f = RH / "manual_uploads" / "energy_institute_2026_kazakhstan_narrow.csv"
    if f.exists():
        for r in csv.DictReader(f.open(encoding="utf-8")):
            try:
                d[r["Var"]][int(r["Year"])] = float(r["Value"])
            except ValueError:
                pass
    return d


def load_usgs():
    try:
        import usgs_myb_parse as u
        S, _ = u.series()
        return {k: {y: x for y, x in v.items() if y != "_paths"} for k, v in S.items()}
    except Exception as exc:  # noqa: BLE001
        print("USGS parse failed:", exc)
        return {}


def load_seea():
    d = defaultdict(dict)
    f = RAW / "bns_seea" / "seea_mineral_asset_account_long.csv"
    if f.exists():
        for r in csv.DictReader(f.open(encoding="utf-8")):
            d[(r["resource"], r["item"])][int(r["year"])] = float(r["value"])
    return d


# ------------------------------------------------------------------ catalog
def T(item, kind="P", scale=1e-3):
    return {"src": "БНС Талдау", "kind": "taldau", "item": item, "tk": kind, "scale": scale}


def PROXY(item, scale=1e-3):
    return {"src": "БНС Талдау (отгрузки)", "kind": "proxy", "item": item, "scale": scale, "series": "экспорт"}


def EI(var, scale=1.0):
    return {"src": "Energy Institute", "kind": "ei", "key": var, "scale": scale}


def EIA(sid, scale=1.0):
    return {"src": "EIA", "kind": "eia", "key": sid, "scale": scale}


def USGS(key, scale, years=None):
    return {"src": "USGS", "kind": "usgs", "key": key, "scale": scale, "years": years}


def CT(flow, hs, scale):
    return {"src": "UN Comtrade", "kind": "ct", "flow": flow, "hs": hs, "scale": scale}


def MIR(hs, scale):
    return {"src": "UN Comtrade, зеркало", "kind": "mir", "hs": hs, "scale": scale}


def SEEA(resource, scale=1.0):
    return {"src": "БНС, счёт активов SEEA", "kind": "seea", "key": resource, "scale": scale}


Mt, kt, t = 1e-9, 1e-6, 1e-3   # kg -> million t / thousand t / t
CATALOG = [
    # var, name, unit, concept, sources (priority order)
    ("oil_prod", "Нефть с конденсатом: добыча", "млн т", "добыча, нефть + газовый конденсат",
     [T("Нефть, включая конденсат газовый"), EI("oilprod_mt"), USGS("oil_t", 1e-6)]),
    ("oil_cons", "Нефть: потребление", "млн т", "потребление нефти и нефтепродуктов", [EI("oilcons_mt")]),
    ("oil_products_prod", "Нефтепродукты: производство", "млн т", "продукты переработки нефти", [T("Продукты переработки нефти")]),
    ("oil_export", "Нефть сырая: экспорт", "млн т", "экспорт, HS 2709",
     [CT("X", "2709", Mt), MIR("2709", Mt), PROXY("Нефть, включая конденсат газовый")]),
    ("oil_products_import", "Нефтепродукты: импорт", "млн т", "импорт, HS 2710", [CT("M", "2710", Mt)]),
    ("gas_gross_prod", "Газ: валовая добыча", "млрд м³", "валовая добыча, включая попутный газ",
     [T("Газ природный"), USGS("gas_m3", 1e-9)]),
    ("gas_assoc_prod", "Газ нефтяной попутный: добыча", "млрд м³", "попутный газ (входит в валовую добычу)", [T("Газ нефтяной попутный")]),
    ("gas_marketed_prod", "Газ: товарная добыча", "млрд м³", "товарный газ: без обратной закачки, сжигания и потерь",
     [EI("gasprod_bcm")]),
    ("gas_dry_prod", "Газ: сухая товарная добыча (EIA)", "млрд м³", "сухой газ: товарный без ШФЛУ и потерь на ГПЗ",
     [EIA("INTL.26-1-KAZ-BCM.A")]),
    ("gas_cons", "Газ: потребление", "млрд м³", "потребление", [EI("gascons_bcm"), EIA("INTL.26-2-KAZ-BCM.A")]),
    ("gas_flared", "Газ: сжигание на факелах", "млрд м³", "сжигание", [EI("gasflared_bcm")]),
    ("gas_export", "Газ: экспорт", "млрд м³", "экспорт товарного газа",
     [EIA("INTL.26-4-KAZ-BCM.A")]),
    ("gas_raw_shipped_out", "Газ природный: отгружено за пределы внутреннего рынка (БНС)", "млрд м³",
     "отгрузки сырого газа; НЕ экспорт (товарный газ экспортируется после ГПЗ)", [PROXY("Газ природный")]),
    ("gas_import", "Газ: импорт", "млрд м³", "импорт", [EIA("INTL.26-3-KAZ-BCM.A")]),
    ("coal_prod", "Уголь: добыча", "млн т", "добыча, включая лигнит и концентрат",
     [T("Уголь каменный, включая лигнит и концентрат угольный"), EI("coalprod_mt"), USGS("coal_t", 1e-6), EIA("INTL.7-1-KAZ-MT.A", 1e-3)]),
    ("coal_cons", "Уголь: потребление", "млн т", "потребление", [EIA("INTL.7-2-KAZ-MT.A", 1e-3)]),
    ("coal_export", "Уголь каменный: экспорт", "млн т", "экспорт, HS 2701",
     [CT("X", "2701", Mt), MIR("2701", Mt), PROXY("Уголь каменный, включая лигнит и концентрат угольный"), EIA("INTL.7-4-KAZ-MT.A", 1e-3)]),
    ("coal_import", "Уголь каменный: импорт", "млн т", "импорт, HS 2701", [CT("M", "2701", Mt), EIA("INTL.7-3-KAZ-MT.A", 1e-3)]),
    ("uranium_prod", "Уран: добыча", "т U", "добыча, U", [USGS("uranium_t", 1.0)]),
    ("uranium_export", "Радиоактивные элементы (уран): экспорт", "т", "экспорт, HS 2844", [CT("X", "2844", t), MIR("2844", t)]),
    ("iron_ore_gross", "Руды железные: добыча", "млн т", "валовая руда", [T("Руды железные")]),
    ("iron_ore_conc", "Руды железные агломерированные и неагломерированные", "млн т", "товарная руда / концентрат",
     [T("Руды железные агломерированные и неагломерированные")]),
    ("iron_ore_usgs", "Железная руда (USGS)", "млн т", "USGS: по годам то валовая руда, то концентрат — см. QA",
     [USGS("iron_ore_t", 1e-6)]),
    ("iron_ore_export", "Железные руды и концентраты: экспорт", "млн т", "экспорт, HS 2601", [CT("X", "2601", Mt), MIR("2601", Mt)]),
    ("chrome_ore", "Руды и концентраты хромовые: производство", "млн т", "руда и концентрат (БНС)", [T("Руды и концентраты хромовые")]),
    ("chromite_marketable", "Хромит товарный (USGS)", "млн т", "товарный хромит", [USGS("chromite_t", 1e-6)]),
    ("chrome_export", "Хромовые руды: экспорт", "млн т", "экспорт, HS 2610", [CT("X", "2610", Mt), MIR("2610", Mt)]),
    ("manganese_ore", "Марганцевая руда: добыча", "млн т", "валовая руда", [USGS("manganese_t", 1e-6)]),
    ("manganese_export", "Марганцевые руды: экспорт", "тыс. т", "экспорт, HS 2602", [CT("X", "2602", kt), MIR("2602", kt)]),
    ("bauxite", "Бокситы: добыча", "млн т", "руда", [USGS("bauxite_t", 1e-6)]),
    ("alumina", "Глинозём: производство", "тыс. т", "глинозём", [T("Оксид алюминия (глинозём)"), USGS("alumina_t", 1e-3)]),
    ("alumina_export", "Глинозём: экспорт", "тыс. т", "экспорт, HS 2818", [CT("X", "2818", kt), MIR("2818", kt)]),
    ("aluminium", "Алюминий необработанный: производство", "тыс. т", "металл", [T("Алюминий необработанный"), USGS("aluminium_t", 1e-3)]),
    ("aluminium_export", "Алюминий необработанный: экспорт", "тыс. т", "экспорт, HS 7601", [CT("X", "7601", kt), MIR("7601", kt)]),
    ("copper_ore", "Руды и концентраты медные: производство", "млн т", "руда и концентрат, валовый вес", [T("Руды и концентраты медные")]),
    ("copper_mine_cu", "Медь в концентрате (рудник)", "тыс. т Cu", "рудник, содержание Cu", [USGS("copper_mine_t", 1e-3)]),
    ("copper_ore_export", "Медные руды и концентраты: экспорт", "тыс. т", "экспорт, HS 2603", [CT("X", "2603", kt), MIR("2603", kt)]),
    ("copper_refined", "Медь рафинированная: производство", "тыс. т", "металл", [T("Медь рафинированная и сплавы медные"), USGS("copper_ref_t", 1e-3)]),
    ("copper_refined_export", "Медь рафинированная: экспорт", "тыс. т", "экспорт, HS 7403", [CT("X", "7403", kt), MIR("7403", kt)]),
    ("zinc_mine", "Цинк в концентрате (рудник)", "тыс. т Zn", "рудник", [USGS("zinc_t", 1e-3)]),
    ("zinc_refined", "Цинк необработанный: производство", "тыс. т", "металл", [T("Цинк необработанный")]),
    ("zinc_export", "Цинк необработанный: экспорт", "тыс. т", "экспорт, HS 7901", [CT("X", "7901", kt), MIR("7901", kt)]),
    ("lead_mine", "Свинец в концентрате (рудник)", "тыс. т Pb", "рудник", [USGS("lead_t", 1e-3)]),
    ("lead_refined", "Свинец необработанный: производство", "тыс. т", "металл", [T("Свинец необработанный")]),
    ("lead_export", "Свинец необработанный: экспорт", "тыс. т", "экспорт, HS 7801", [CT("X", "7801", kt), MIR("7801", kt)]),
    ("ferroalloys", "Ферросплавы: производство", "тыс. т", "ферросплавы", [T("Ферросплавы"), USGS("ferroalloys_t", 1e-3)]),
    ("ferroalloys_export", "Ферросплавы: экспорт", "тыс. т", "экспорт, HS 7202", [CT("X", "7202", kt), MIR("7202", kt)]),
    ("gold_refined", "Золото необработанное: производство", "т", "аффинированное золото", [T("Золото необработанное"), USGS("gold_t", 1.0)]),
    ("gold_export", "Золото: экспорт", "т", "экспорт, HS 7108 (с 2016 г. почти нет: преимущественное право Нацбанка)", [CT("X", "7108", t), MIR("7108", t)]),
    ("silver_refined", "Серебро необработанное: производство", "т", "аффинированное серебро", [T("Серебро необработанное")]),
    ("silver_mine", "Серебро (USGS)", "т", "USGS: рудничное до 2021 г., с 2022 г. — данные БНС", [USGS("silver_t", 1.0)]),
    ("silver_export", "Серебро: экспорт", "т", "экспорт, HS 7106", [CT("X", "7106", t), MIR("7106", t)]),
    ("titanium_sponge", "Титан губчатый", "тыс. т", "металл", [USGS("ti_sponge_t", 1e-3)]),
    ("titanium_export", "Титан: экспорт", "тыс. т", "экспорт, HS 8108", [CT("X", "8108", kt), MIR("8108", kt)]),
    ("molybdenum", "Молибден (рудник)", "т Mo", "рудник", [USGS("molybdenum_t", 1.0)]),
    ("phosphate_rock", "Фосфориты: добыча", "млн т", "руда", [USGS("phosphate_t", 1e-6)]),
    ("pig_iron", "Чугун: производство", "тыс. т", "металл", [T("Чугун")]),
    ("steel", "Сталь нерафинированная: производство", "тыс. т", "металл", [T("Сталь нерафинированная")]),
]
SEEA_VARS = {  # reserves at end of year, BNS asset account (commercially recoverable)
    "Нефть (млн. тонн)": ("reserves_oil", "млн т"), "Конденсат (млн. тонн)": ("reserves_condensate", "млн т"),
    "Газ (млрд.м³)": ("reserves_gas", "млрд м³"), "Уголь (млн. тонн)": ("reserves_coal", "млн т"),
    "Уран (тыс. тонн)": ("reserves_uranium", "тыс. т U"), "Железные руды (млн. тонн)": ("reserves_iron_ore", "млн т"),
    "Хромовые руды (млн. тонн)": ("reserves_chrome_ore", "млн т"), "Марганцевые руды (млн. тонн)": ("reserves_manganese_ore", "млн т"),
    "Бокситы (млн. тонн)": ("reserves_bauxite", "млн т"), "Медь (млн. тонн)": ("reserves_copper", "млн т"),
    "Цинк (млн. тонн)": ("reserves_zinc", "млн т"), "Свинец (млн. тонн)": ("reserves_lead", "млн т"),
    "Золото (тонн)": ("reserves_gold", "т"), "Серебро (тыс. тонн)": ("reserves_silver", "тыс. т"),
    "Молибден (тыс. тонн)": ("reserves_molybdenum", "тыс. т"), "Фосфориты - Р₂О₅ (млн. тонн)": ("reserves_phosphate_p2o5", "млн т"),
}
BLOCKING = {"spike", "identity", "unit", "confidential"}


def build_long():
    TD, CTN, CTM = load_taldau(), load_comtrade("comtrade_kazakhstan.csv"), load_comtrade("comtrade_mirror_kazakhstan.csv")
    EIAd, EId, US, SE = load_eia(), load_ei(), load_usgs(), load_seea()
    rows = []

    def add(var, name, unit, concept, src, series, vals):
        for y, x in sorted(vals.items()):
            rows.append([var, name, concept, unit, src, series, y, round(x, 6)])

    for var, name, unit, concept, specs in CATALOG:
        for s in specs:
            k = s["kind"]
            if k == "taldau":
                for kind in ("P", "T", "D"):
                    v = TD.get((TK[kind], s["item"]), {})
                    if v and (kind == "P" or s["tk"] == "P"):
                        add(var, name, unit, concept, s["src"], TSER[kind], {y: x * s["scale"] for y, x in v.items()})
            elif k == "proxy":
                tt, dd = TD.get((TK["T"], s["item"]), {}), TD.get((TK["D"], s["item"]), {})
                add(var, name, unit, concept, s["src"], "экспорт", {y: (tt[y] - dd[y]) * s["scale"] for y in tt if y in dd})
            elif k == "ei":
                add(var, name, unit, concept, s["src"], "", {y: x * s["scale"] for y, x in EId.get(s["key"], {}).items()})
            elif k == "eia":
                add(var, name, unit, concept, s["src"], "", {y: x * s["scale"] for y, x in EIAd.get(s["key"], {}).items()})
            elif k == "usgs":
                lo, hi = s["years"] or (0, 9999)
                add(var, name, unit, concept, s["src"], "", {y: x * s["scale"] for y, x in US.get(s["key"], {}).items() if lo <= y <= hi})
            elif k in ("ct", "mir"):
                D, flow = (CTN, s["flow"]) if k == "ct" else (CTM, "M")
                add(var, name, unit, concept, s["src"], "вес нетто",
                    {y: x * s["scale"] for y, x in D.get((flow, s["hs"], "net_weight_kg"), {}).items() if x > 0})
                add(var, name, "млн $", concept, s["src"], "стоимость",
                    {y: x * 1e-6 for y, x in D.get((flow, s["hs"], "value_usd"), {}).items() if x > 0})
    for res, (var, unit) in SEEA_VARS.items():
        v = SE.get((res, "Запасы минеральных и энергетических ресурсов на конец периода"), {})
        add(var, f"Запасы на конец года: {res.split(' (')[0]}", unit, "коммерчески извлекаемые запасы (SEEA)",
            "БНС, счёт активов SEEA", "", v)
    return rows


def pick(rows, issues):
    flags = qa.flags_index(issues)
    meta, series = {}, defaultdict(dict)
    for var, name, concept, unit, src, ser, y, x in rows:
        if ser == "стоимость":
            continue
        meta[var] = (name, concept)
        series[(var, src, ser)][y] = (x, unit)
    order = {var: [s["src"] for s in specs] for var, _, _, _, specs in CATALOG}
    order.update({v: ["БНС, счёт активов SEEA"] for v, _ in SEEA_VARS.values()})
    qty_ser = ("производство", "", "вес нетто", "экспорт")
    panel = []
    for var in sorted(meta):
        years = sorted({y for (v, s, ser), d in series.items() if v == var and ser in qty_ser for y in d})
        for y in years:
            cands = []
            for src in order.get(var, []):
                for ser in qty_ser:
                    d = series.get((var, src, ser))
                    if d and y in d:
                        cands.append((src, ser, d[y], flags.get((var, src, ser, y), [])))
            chosen = next((c for c in cands if not (BLOCKING & set(c[3]))), None)
            note = []
            if chosen is None and cands:
                chosen = cands[0]
                note.append("все источники с ошибками QA")
            if chosen is None:
                continue
            if cands and chosen is not cands[0]:
                note.append(f"замена: {cands[0][0]} не прошёл QA ({','.join(sorted(BLOCKING & set(cands[0][3])))})")
            src, ser, (x, unit), fl = chosen
            panel.append([var, meta[var][0], unit, meta[var][1], y, x, src, ";".join(sorted(set(fl))),
                          len(cands), "; ".join(note)])
    return panel


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build_long()
    with (OUT / "natural_resources_long.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["var", "name", "concept", "unit", "source", "series", "year", "value"])
        w.writerows(rows)
    issues = qa.run(qa.load_long(OUT / "natural_resources_long.csv"))
    qa.write_reports(issues)
    panel = pick(rows, issues)
    with (OUT / "natural_resources_panel.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["var", "name", "unit", "concept", "year", "value", "source", "qa_flags", "n_sources", "note"])
        w.writerows(panel)
    with (OUT / "catalog.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["var", "name", "unit", "concept", "sources_priority"])
        for var, name, unit, concept, specs in CATALOG:
            w.writerow([var, name, unit, concept, " > ".join(dict.fromkeys(s["src"] for s in specs))])
        for res, (var, unit) in SEEA_VARS.items():
            w.writerow([var, f"Запасы на конец года: {res.split(' (')[0]}", unit, "коммерчески извлекаемые запасы (SEEA)", "БНС, счёт активов SEEA"])
    n_err = sum(i["severity"] == "error" for i in issues)
    print(f"long rows {len(rows)}, panel rows {len(panel)}, vars {len({p[0] for p in panel})}, "
          f"QA issues {len(issues)} (errors {n_err})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
