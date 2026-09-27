"""BNS CPI publication (fetchers/bns_cpi.py, scripts/backfill_cpi_publication.py): header
reading across the four layouts of 2004-2026, labels in Kazakh/Russian, and the stored
history against the scalar CPI series it must reproduce."""
import csv
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import bns_cpi  # noqa: E402

DIMS = REPO_ROOT / "data" / "processed" / "dims"


@pytest.mark.parametrize("header,year,month,expected", [
    ("июлю 2026г.", 2026, 8, ["mom"]),
    ("декабрю 2025г.", 2026, 8, ["ytd"]),
    ("августу 2025г.", 2026, 8, ["yoy"]),
    ("декабрю 2020г.", 2026, 8, []),                                        # fixed base: a chain, not kept
    ("Январь-август 2026г. к январю-августу 2025г.", 2026, 8, ["avg_yoy"]),
    ("Январь -июль 2004г. к январю - июлю 2003г.", 2004, 7, ["avg_yoy"]),
    ("декабрю 2004г.", 2005, 1, ["mom", "ytd"]),                            # January: both
    ("январю 2004г.", 2005, 1, ["yoy", "avg_yoy"]),
    ("ноябрю 2005г.", 2005, 12, ["mom"]),
    ("декабрю 2004г.", 2005, 12, ["ytd", "yoy"]),                           # December: both
    ("2007ж.\nжелтоқсанына\nдекабрю 2007г.", 2008, 4, ["ytd"]),            # желтоқсан is not a quarter
    ("2015ж.\nIV тоқсан\n2015ж.\nIII тоқсанға", 2015, 12, []),
    ("IV квартал 2005г. к IV кварталу 2004г.", 2005, 12, []),
])
def test_column_measures(header, year, month, expected):
    assert bns_cpi.column_measures(header, year, month) == expected


@pytest.mark.parametrize("cells,expected", [
    (["Тауарлар мен қызметтер", 100.7, 128.9, "Товары и услуги"], ("Тауарлар мен қызметтер", "Товары и услуги")),
    (["Барлық тауарлар мен қызмет\nкөрсетулер\nВсе товары и услуги", 100.7], ("Барлық тауарлар мен қызмет көрсетулер", "Все товары и услуги")),
    (["Денсаулық сақтау Здравоохранение", 100.5], ("Денсаулық сақтау", "Здравоохранение")),
    (["Говядина", 100.3, "-"], ("", "Говядина")),                           # a «-» cell is not a label
    (["Қарақұмық", 100.2], ("Қарақұмық", "")),
])
def test_split_label(cells, expected):
    assert bns_cpi.split_label(cells) == expected


@pytest.mark.parametrize("title,expected", [
    ("Индекс … в Республике Казахстан (август 2026 года)", (2026, 8)),
    ("Индекс … в Республике Казахстан ( 2023 г. сентябрь)", (2023, 9)),
    ("Индекс … в Республике Казахстан (10.2023)", (2023, 10)),
    ("Индекс … в Республике Казахстан (  Сентябрь  2025 года)", (2025, 9)),
    ("Индекс … в Республике Казахстан (Май 1999 года)", (1999, 5)),
])
def test_edition_month(title, expected):
    assert bns_cpi.edition_month(title) == expected


def _grid(title, rows, header=("июлю 2026г.", "декабрю 2025г.", "августу 2025г.", "декабрю 2020г.")):
    return [[title], ["в процентах"], [None, "Август 2026г. к", None, None, None, "Январь-август 2026г. к январю-августу 2025г."],
            [None, *header, None], *rows]


def test_edition_records_codes_regions_and_duplicates():
    national = _grid("1. Индекс потребительских цен", [
        ["Товары и услуги", 100.6, 106.4, 109.8, 185.8, 110.8],
        ["Связь", 100.9, 106.5, 107.2, 138.1, 106.1],
        ["Верхняя одежда", 100.5, 105.0, 108.0, 170.0, 108.0],
        ["Мужская", 100.3, 104.0, 107.0, 160.0, 107.0],
        ["Обувь", 100.6, 107.0, 110.8, 189.1, 111.3],
        ["Мужская", 100.9, 108.0, 112.0, 190.0, 112.0],
        ["Бензин АИ-92", 99.0, 101.0, 104.0, 150.0, 103.0],
    ])
    regional = _grid("2. Индекс потребительских цен по регионам", [
        ["Tовары и услуги"],                                                  # Latin T, as BNS types it
        ["Республика Казахстан", 100.6, 106.4, 109.8, 185.8, 110.8],
        ["Абай", 100.7, 106.0, 109.0, 180.0, 110.0],
        ["город Алматы", 100.5, 106.1, 108.7, 180.0, 109.9],
        ["Рис"],
        ["Абай", 101.0, 101.0, 101.0, 101.0, 101.0],                          # item blocks are not kept
    ])
    tables = [bns_cpi.parse_grid(g, 2026, 8) for g in (national, regional)]
    recs, problems = bns_cpi.edition_records(tables, 2026, 8)
    assert problems == []
    mom = {(r["region"], r["item_code"]): r for r in recs["CPI_DETAIL_MOM"]}
    assert mom[("national", "TOTAL")]["value"] == 100.6 and mom[("national", "CP08")]["value"] == 100.9
    assert mom[("national", "muzhskaya_verkhnyaya_odezhda")]["item_name"] == "Мужская (верхняя одежда)"
    assert mom[("national", "muzhskaya_obuv")]["value"] == 100.9
    assert ("national", "benzin_ai_92") in mom
    assert mom[("ABY", "TOTAL")]["value"] == 100.7 and mom[("ALA", "TOTAL")]["value"] == 100.5
    assert not any(code == "ris" for _, code in mom)
    assert {r["value"] for r in recs["CPI_DETAIL_AVG_YOY"] if r["item_code"] == "TOTAL"} == {110.8, 110.0, 109.9}
    assert all(r["date"] == "2026-08-01" for rs in recs.values() for r in rs)


def test_mislabelled_year_on_year_column_is_repaired():
    """February 2026: the year-on-year column is headed «январю 2025г.»."""
    grid = [["1. Индекс потребительских цен"], ["в процентах"], [None, "Февраль 2026г. к"],
            [None, "январю 2026г.", "декабрю 2025г.", "январю 2025г.", "декабрю 2020г.", "Январь-февраль 2026г. к январю-февралю 2025г."],
            ["Товары и услуги", 100.9, 102.1, 111.6, 173.6, 111.6]]
    t = bns_cpi.parse_grid(grid, 2026, 2)
    assert t.rows[0].values == {"mom": 100.9, "ytd": 102.1, "yoy": 111.6, "avg_yoy": 111.6}
    assert "read as year-on-year" in t.repaired


def test_january_contribution_table_is_both_bases():
    grid = [["6. Вклад отдельных составляющих в индексе потребительских цен"], ["в процентах"],
            [None, "К предыдущему месяцу"], [None, "темп прироста", "вклад в прирост цен"],
            ["Товары и услуги", 1.2, 1.18]]
    t = bns_cpi.parse_grid(grid, 2026, 1)
    assert t.kind == "contribution" and t.rows[0].values == {"mom": 1.18, "ytd": 1.18}


# ---------------------------------------------------------------- the stored history

def _series(dataset, code, region="national"):
    with (DIMS / f"{dataset.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["item_code"] == code and r["region"] == region}


def _scalar(indicator):
    with (REPO_ROOT / "data" / "processed" / "bns" / f"{indicator.lower()}.csv").open(encoding="utf-8") as f:
        return {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["value"]}


@pytest.mark.parametrize("scalar,dataset,code", [
    ("CPI", "CPI_DETAIL_MOM", "TOTAL"), ("CPI_YOY", "CPI_DETAIL_YOY", "TOTAL"), ("CPI_YTD", "CPI_DETAIL_YTD", "TOTAL"),
    ("CPI_FOOD", "CPI_DETAIL_MOM", "FOOD"), ("CPI_NONFOOD_YOY", "CPI_DETAIL_YOY", "NONFOOD"),
    ("CPI_SERVICES", "CPI_DETAIL_MOM", "SERVICES"), ("CORE_CPI_YOY_EX7", "CPI_DETAIL_YOY", "CORE_EX7"),
])
def test_publication_equals_the_scalar_series(scalar, dataset, code):
    a, b = _scalar(scalar), _series(dataset, code)
    common = set(a) & set(b)
    assert len(common) >= 40
    assert all(abs(a[d] - b[d]) < 0.051 for d in common)


def test_history_reaches_2004_with_every_division_and_region():
    total = _series("CPI_DETAIL_MOM", "TOTAL")
    assert min(total) == "2004-07-01" and len(total) >= 265
    months = sorted(total)
    for code in ("FOOD", "NONFOOD", "SERVICES", *(f"CP{i:02d}" for i in range(1, 12))):
        assert set(_series("CPI_DETAIL_MOM", code)) == set(months), code
    with (DIMS / "cpi_detail_mom.csv").open(encoding="utf-8") as f:
        regions_by_month = {}
        for r in csv.DictReader(f):
            if r["item_code"] == "TOTAL":
                regions_by_month.setdefault(r["date"], set()).add(r["region"])
    assert all(len(v) >= 17 for v in regions_by_month.values())


def test_contribution_total_is_the_cpi_growth():
    contrib, cpi = _series("CPI_CONTRIBUTION_MOM", "TOTAL"), _series("CPI_DETAIL_MOM", "TOTAL")
    assert min(contrib) == "2020-01-01"
    assert all(abs(contrib[d] - (cpi[d] - 100)) < 0.06 for d in contrib)
