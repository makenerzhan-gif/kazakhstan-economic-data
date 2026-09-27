"""Supply and use by product and region, added 2026-09-27: trade by HS chapter and by region
(BNS trade workbooks), the monthly resources-and-use publication, the agricultural and
fuel-energy balances, industry by region (Taldau) and the derived regional balance. Parser
tests on built fixtures; data tests on the processed files against published figures."""
import csv
import io
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import bns_balances, bns_resource_use as ru, bns_trade, regional_balance  # noqa: E402
from lib import validation  # noqa: E402

DIMS = REPO_ROOT / "data" / "processed" / "dims"


def _dims(name: str) -> dict[tuple[str, str, str], float]:
    with (DIMS / f"{name.lower()}.csv").open(encoding="utf-8") as f:
        return {(r["date"], r["region"], r["item_code"]): float(r["value"]) for r in csv.DictReader(f)}


# ---------------------------------------------------------------- trade by region

def _trade_workbook(akm_heading=(130.0, 34.0), footnote=True) -> bytes:
    """January 2025 only: two regions with heading rows, [tonnes, unit, USD]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "2025"
    ws.append(["Импорт"])
    ws.append(["Код", "Наименование", "Доп.", "январь 2025 года", None, None])
    ws.append([None, None, None, "тонн", "доп.", "тыс.долларов США"])
    ws.append(["Республики Казахстан", None, None, 1130.0, None, 534.0])
    ws.append(["Акмолинская", None, None, akm_heading[0], None, akm_heading[1]])
    ws.append(["100199", "пшеница", None, 100.0, None, 30.0])
    ws.append(["720810", "прокат", None, 30.0, None, 4.0])
    ws.append(["Атырауская", None, None, 1000.0, None, 500.0])
    ws.append(["270900", "нефть", None, 1000.0, None, 500.0])
    if footnote:
        ws.append(["*Предварительные данные."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SECTIONS = [{"code": "TOTAL", "prefixes": []}, {"code": "II", "prefixes": ["10"]}, {"code": "V", "prefixes": ["27"]},
            {"code": "XV", "prefixes": ["72"]}]


def test_regional_sections_sum_the_lines_of_each_region_and_keep_the_published_totals():
    sc = bns_trade.scan(_trade_workbook(), {"s": SECTIONS}, {"id": "T"})
    out = bns_trade.regional_groups(sc, "s", SECTIONS, "usd")["2025-01-01"]
    assert out[("national", "TOTAL")] == 534.0 and out[("national", "V")] == 500.0
    assert out[("AKM", "TOTAL")] == 34.0 and out[("AKM", "II")] == 30.0 and out[("AKM", "XV")] == 4.0 and out[("AKM", "V")] == 0.0
    assert out[("ATY", "V")] == 500.0


def test_a_region_whose_lines_miss_its_heading_keeps_its_total_only():
    sc = bns_trade.scan(_trade_workbook(akm_heading=(130.0, 40.0)), {"s": SECTIONS}, {"id": "T"})
    out = bns_trade.regional_groups(sc, "s", SECTIONS, "usd")["2025-01-01"]
    assert out[("AKM", "TOTAL")] == 40.0 and ("AKM", "II") not in out and out[("ATY", "V")] == 500.0


def test_an_unknown_text_row_with_numbers_is_a_structural_change():
    content = _trade_workbook()
    wb = openpyxl.load_workbook(io.BytesIO(content))
    wb["2025"].append(["Неизвестная область", None, None, 1.0, None, 1.0])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(validation.StructuralChangeError):
        bns_trade.scan(buf.getvalue(), {"s": SECTIONS}, {"id": "T"})


def test_hs_dictionaries_partition_the_chapters():
    chapters = bns_trade.load_groups("hs_chapters")
    sections = bns_trade.load_groups("hs_sections")
    ch = [p for g in chapters for p in g["prefixes"]]
    sec = [p for g in sections for p in g["prefixes"]]
    assert len(ch) == len(set(ch)) == 97 and len(sec) == len(set(sec)) and set(ch) <= set(sec)
    for name in ("hs_chapters", "hs_sections", "hs_balance_products"):
        groups = bns_trade.load_groups(name)
        pre = [(p, g["code"]) for g in groups for p in g["prefixes"]]
        assert not [(p, q) for p, a in pre for q, b in pre if a != b and q.startswith(p)], name


def test_regional_trade_adds_up_to_the_national_rows():
    for ds in ("IMPORTS_VALUE_BY_REGION_HS_SECTION", "EXPORTS_VOLUME_BY_REGION_HS_SECTION"):
        v = _dims(ds)
        regions = defaultdict(float)
        for (d, reg, code), x in v.items():
            if reg != "national" and code == "TOTAL":
                regions[d] += x
        # September 2022: BNS's national rows fall short of their regions (config/source_issues.yaml trade_national_row_2022_09)
        checked = [d for (d, reg, code) in v if reg == "national" and code == "TOTAL" and d in regions and d != "2022-09-01"]
        assert len(checked) > 130 and all(abs(regions[d] - v[(d, "national", "TOTAL")]) <= 1e-4 * v[(d, "national", "TOTAL")] + 1 for d in checked), ds
    chapters = _dims("IMPORTS_VALUE_BY_HS_CHAPTER")
    sections = _dims("IMPORTS_VALUE_BY_REGION_HS_SECTION")
    d = "2025-06-01"
    assert abs(sum(x for (dd, r, c), x in chapters.items() if dd == d and c != "TOTAL")
               - sum(x for (dd, r, c), x in sections.items() if dd == d and r == "national" and c != "TOTAL")) < 1.0


# ---------------------------------------------------------------- resources and use

def _ru_sheet(bilingual: bool) -> list[list]:
    head = ["июнь 2026г.", "январь-июнь 2026г.", "июль 2026г.", " январь-июль 2026г.", " июль 2025г.", " январь-июль 2025г."]
    if bilingual:
        head = [f"2026 жылғы маусым /\n{h}" for h in head]
    rows = [["1. Ресурсы и использование"], ["Наименование продукции", "Фактически за", "Фактически за"], [""] + head + ["%"],
            ["Горнодобывающая промышленность"], ["Уголь каменный, тыс.тонн"]]
    for label, vals in (("Ресурсы", [10, 60, 12, 72, 11, 70]), ("Производство", [9, 55, 11, 66, 10, 64]),
                        ("Импорт", [1, 5, 1, 6, 1, 6]), ("Использование", [10, 60, 12, 72, 11, 70]),
                        ("Экспорт", [3, 20, "x", 23, 4, 25]), ("Реализация на внутреннем рынке", [7, 40, 8, 49, 7, 45])):
        row = [label] + vals + [99.0]
        rows.append(row + [label] if bilingual else row)
    return rows


@pytest.mark.parametrize("bilingual", [False, True])
def test_resource_use_sheet_gives_three_months_and_three_year_to_date_figures(bilingual):
    kind, recs = ru.parse_sheet("1", _ru_sheet(bilingual))
    got = {(m, d, a): v for m, d, code, name, a, v in recs}
    assert kind == "monthly" and {code for _m, _d, code, _n, _a, _v in recs} == {"ugol_kamennyy_tys_tonn"}
    assert got[("monthly", "2026-07-01", "PROD")] == 11 and got[("monthly", "2026-06-01", "PROD")] == 9
    assert got[("monthly", "2025-07-01", "EXP")] == 4 and ("monthly", "2026-07-01", "EXP") not in got     # 'x' is confidential
    assert got[("ytd", "2026-07-01", "DOM")] == 49 and got[("ytd", "2026-06-01", "RES")] == 60 and got[("ytd", "2025-07-01", "IMP")] == 6


def test_resource_use_rejects_shifted_columns():
    rows = _ru_sheet(False)
    rows[2][3] = "август 2026г."
    with pytest.raises(ValueError):
        ru.parse_sheet("1", rows)


def test_resource_use_titles_headers_and_codes():
    assert ru.edition_of("Ресурсы … (январь-июль 2026г.)") == ("monthly", 2026, 7)
    assert ru.edition_of("Ресурсы … (январь 2021 года)") == ("monthly", 2021, 1)
    assert ru.edition_of("Ресурсы … (2024г.)") == ("annual", 2024, 12)
    assert ru._month_of("2019 жылғы\nқаңтар-желтоқсан /\nянварь-декабрь 2019г.") == (2019, 12, True)
    assert ru._month_of("январь 2020г.") == (2020, 1, False)
    assert ru.product_code("1", "Коньяки и напитки коньячные, тыс.литров") == ru.product_code("1", "коньяк и напитки коньячные, тыс. литров")
    assert ru.product_code("3", "Конина, тонн") == ru.product_code("3", "Мясо конины, тонн") == "szpt_myaso_koniny_tonn"
    long_a = "экскаваторы одноковшовые механические самоходные и погрузчики ковшовые неполноворотные, штук"
    long_b = "экскаваторы одноковшовые механические самоходные и погрузчики ковшовые неполноворотные, машины самоходные для горнодобывающей промышленности прочие, штук"
    assert ru.product_code("1", long_a) != ru.product_code("1", long_b)


def test_resource_use_data_matches_the_publication():
    ytd = _dims("RESOURCE_USE_YTD")
    coal = "ugol_kamennyy_i_lignit_ugol_buryy_tys_tonn"
    assert ytd[("2026-07-01", "national", f"{coal}.PROD")] == 63029.033                 # edition January–July 2026
    assert ytd[("2026-07-01", "national", f"{coal}.EXP")] == 17833.073
    wheat = "crops_pshenitsa_tverdaya_pshenitsa_myagkaya_i_surzhik_meslin_tonn"
    assert abs(ytd[("2026-07-01", "national", f"{wheat}.EXP")] - 4947050.527) < 0.01
    annual = _dims("RESOURCE_USE_ANNUAL")
    assert annual[("2024-12-31", "national", f"{coal}.PROD")] == pytest.approx(ytd[("2024-12-01", "national", f"{coal}.PROD")])
    monthly = _dims("RESOURCE_USE_MONTHLY")
    res = [(d, c) for (d, _r, c) in monthly if c.endswith(".RES")]
    ok = sum(1 for d, c in res if (d, "national", c[:-4] + ".PROD") in monthly
             and abs(monthly[(d, "national", c[:-4] + ".PROD")] + monthly.get((d, "national", c[:-4] + ".IMP"), 0)
                     + monthly.get((d, "national", c[:-4] + ".EST"), 0) - monthly[(d, "national", c)])
             <= max(0.01 * abs(monthly[(d, "national", c)]), 0.5))
    with_prod = sum(1 for d, c in res if (d, "national", c[:-4] + ".PROD") in monthly)
    assert with_prod > 20000 and ok / with_prod > 0.99
    assert min(d for d, _r, _c in monthly) == "2018-03-01" and len({c.rsplit(".", 1)[0] for _d, _r, c in monthly}) > 300


# ---------------------------------------------------------------- annual balances

def test_agricultural_balance_matches_the_2025_edition_and_adds_up():
    v = _dims("AGRI_BALANCE")
    assert round(v[("2024-12-31", "national", "GRAIN.PROD")], 1) == 25204.8
    assert round(v[("2024-12-31", "national", "GRAIN.EXP")], 1) == 8250.5
    for y in range(2017, 2026):
        d = f"{y}-12-31"
        g = {c.split(".")[1]: x for (dd, _r, c), x in v.items() if dd == d and c.startswith("GRAIN.")}
        assert abs(g["STOCK_BEGIN"] + g["PROD"] + g["IMP"] - g["RES"]) < 0.5, y
        use = g["PROD_USE"] + g["FOOD_PROC"] + g["OTHER_IND"] + g["LOSS"] + g["EXP"] + g["CONS"] + g["STOCK_END"]
        assert abs(use - g["RES"]) < 0.5, y


def test_energy_balance_supply_identity_holds_every_year():
    v = _dims("ENERGY_BALANCE_TJ")
    for y in range(2021, 2026):
        g = lambda k: v.get((f"{y}-12-31", "national", "TOTAL." + k), 0.0)  # noqa: E731
        calc = (g("S1.proizvodstvo_dobycha_pervichnoy_energii") + g("S1.import") + g("S1.eksport")
                + g("S1.mezhdunarodnaya_morskaya_i_aviatsionnaya_bunkerovka") + g("S1.izmenenie_obema_ostatkov"))
        assert abs(calc - g("S1.obshchee_pervichnoe_potreblenie_energii_i_ee_ekvivalentov")) < 1.0, y


def test_energy_flow_codes_follow_the_blocks():
    rows = [["ТЭБ"], [None], [None, "Уголь", None, None], [None, "уголь, тыс.тонн", "газ, млн куб. м", "мазут, тыс.тонн"] + [f"f{i}" for i in range(20)],
            ["1. Общее предложение энергии"], ["Импорт (+)", 1, 2, 3], ["2. Преобразование"], ["Сектор преобразования - Вход", 5, 0, 0],
            ["Коксовые печи", 5, None, "-"], ["Потребление в энергетическом секторе (собственные нужды)", 1, 1, 1], ["Коксовые печи", 1, 1, 1],
            ["Доступно для конечного потребления", 9, 9, 9], ["3. Конечное потребление энергии", 8, 8, 8],
            ["Конечное потребление для энергетических целей", 8, 8, 8], ["Сектор транспорта", 2, 2, 2], ["Автодорожный транспорт", 2, 2, 2],
            ["Статистические расхождения", 0, 0, 0], ["1) сноска"]]
    codes = {r["item_code"] for r in bns_balances.parse_energy(rows, 2025)}
    assert {"ugol_tys_tonn.S1.import", "ugol_tys_tonn.TRANSFORM_IN.koksovye_pechi",
            "ugol_tys_tonn.ENERGY_OWN_USE.koksovye_pechi", "ugol_tys_tonn.S2.dostupno_dlya_konechnogo_potrebleniya",
            "ugol_tys_tonn.FINAL_ENERGY.TRANSPORT.avtodorozhnyy_transport", "ugol_tys_tonn.S3.statisticheskie_raskhozhdeniya"} <= codes
    assert "mazut_tys_tonn.TRANSFORM_IN.koksovye_pechi" not in codes          # '-' is no value


# ---------------------------------------------------------------- industry by region

def test_regional_industrial_output_adds_up_to_the_national_figure():
    v = _dims("INDUSTRY_OUTPUT_BY_REGION_MONTHLY")
    regions = defaultdict(float)
    for (d, reg, code), x in v.items():
        if reg != "national" and code == "IND":
            regions[d] += x
    months = [d for (d, reg, code) in v if reg == "national" and code == "IND"]
    assert len(months) >= 80 and min(months) == "2020-01-01"
    assert all(abs(regions[d] - v[(d, "national", "IND")]) < 1.0 for d in months)
    assert len({reg for (_d, reg, _c) in v}) == 21


def test_regional_balance_converts_units_and_derives_apparent_use():
    prod = {("2025-01-01", "PVL", "COAL"): (5000.0, "Уголь каменный, тысяча тонн"),
            ("2025-01-01", "PVL", "BEER"): (10.0, "Пиво, тысяча литров")}
    ship = {("2025-01-01", "PVL", "COAL.TOTAL"): (4900.0, "Уголь — отгружено всего, тысяча тонн"),
            ("2025-01-01", "PVL", "COAL.DOM"): (3000.0, "Уголь — на внутренний рынок, тысяча тонн")}
    exp = {("2025-01-01", "PVL", "COAL"): (1_800_000.0, "")}
    imp = {("2025-01-01", "PVL", "COAL"): (100.0, "")}
    out = {r["item_code"]: r["value"] for r in regional_balance.build(prod, ship, exp, imp, {"COAL": "Уголь", "BEER": "Пиво"})}
    assert out == {"COAL.PROD": 5_000_000.0, "COAL.EXP": 1_800_000.0, "COAL.IMP": 100.0, "COAL.APPARENT_USE": 3_200_100.0,
                   "COAL.SHIP_TOTAL": 4_900_000.0, "COAL.SHIP_DOM": 3_000_000.0}


def test_taldau_regional_reads_the_national_node_and_the_regions(monkeypatch):
    from fetchers import taldau_dims
    calls = []

    def fake_post(ds, terms, parent="", pos="0", term="741880"):
        calls.append((terms, parent))
        if terms.split(",")[1] == "999":
            return []                                                   # a term the index no longer has
        if not parent:
            return [{"id": "741880", "text": "РЕСПУБЛИКА КАЗАХСТАН", "leaf": "false", "measureName": "Тысяча тонн",
                     "y012026": "10.5", "y022026": "11"}]
        return [{"id": "247783", "text": "АКМОЛИНСКАЯ ОБЛАСТЬ", "leaf": "true", "y012026": "4"},
                {"id": "77208141", "text": "ОБЛАСТЬ АБАЙ", "leaf": "true", "y012026": "6.5"}]

    monkeypatch.setattr(taldau_dims, "_post", fake_post)
    monkeypatch.setattr(taldau_dims.raw_store, "save_raw_bytes", lambda *a, **k: Path("x.json.gz"))
    monkeypatch.setattr(taldau_dims.raw_store, "write_download_manifest", lambda *a, **k: None)
    ds = {"id": "T", "index_id": "1", "dic_ids": "68,1973", "terms": "741880,1", "item_pos": 1, "frequency": "monthly",
          "unit_in_name": True, "items": [{"code": "COAL", "term": "5", "name": "Уголь"}, {"code": "GONE", "term": "999", "name": "x"}]
          + [{"code": f"P{i}", "term": str(10 + i), "name": "Уголь"} for i in range(4)]}   # one missing item in five is tolerated
    recs, man = taldau_dims.fetch_regional(ds)
    got = {(r["date"], r["region"], r["item_code"]): r["value"] for r in recs if r["item_code"] == "COAL"}
    assert got == {("2026-01-01", "national", "COAL"): 10.5, ("2026-02-01", "national", "COAL"): 11.0,
                   ("2026-01-01", "AKM", "COAL"): 4.0, ("2026-01-01", "ABY", "COAL"): 6.5}
    assert {r["item_name"] for r in recs} == {"Уголь, тысяча тонн"} and "GONE" in man["warnings"][0]
