import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib import dims, validation  # noqa: E402
from fetchers import bns_dims  # noqa: E402
import update_dims  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DS = {"id": "TEST", "element_id": 0, "dictionary": "okved_sections", "region": "Республика Казахстан"}


def test_every_dataset_has_a_fetcher_and_a_known_layout():
    assert set(update_dims.FETCHERS) == set(update_dims.DATASET_IDS)
    for ds in update_dims.DATASETS.values():
        key = ds.get("fetcher", ds["agency"])
        assert key in update_dims.AGENCY_FETCHERS, f"{ds['id']}: no fetcher for {key}"
        if key == "bns":
            assert ds["layout"] in ("periods_across", "region_blocks", "year_subcolumns", "group_blocks", "product_blocks", "year_quarters",
                                    "year_months", "year_sheets", "year_blocks_regions_items", "year_blocks_items_regions",
                                    "year_blocks_items_regions_ytd", "month_rows", "region_blocks_months", "sector_columns")
        elif key == "bns_trade":
            assert ds["measure"] in ("usd", "tonnes") and ds["dictionary"] == "hs_export_groups" and ds["frequency"] == "monthly"
        elif key == "gravity":
            assert ds["table"] in update_dims.gravity.TABLES and ds["frequency"] == "annual"
        elif ds["agency"] == "wb":
            assert ds["table"] in ("annual_prices", "annual_indices", "monthly_prices", "monthly_indices",
                                   "forecast_prices", "forecast_indices")
            assert ds["fallback_url"].startswith("https://thedocs.worldbank.org/") and ds["sheet"]
        elif ds["agency"] == "eia":
            assert ds["sheet"] and ds["items"]
        if ds.get("dictionary") not in (None, "from_table"):
            assert (REPO_ROOT / "dictionaries" / f"{ds['dictionary']}.csv").exists()
        if ds.get("row_dimension") == "region":
            assert ds["fixed_item"], f"{ds['id']}: region rows need a fixed item"
        if ds.get("country", "KZ") != "KZ":        # a world-price dataset: its region tag and geography must be explicit
            assert ds.get("region") == "world" and ds.get("geography"), f"{ds['id']}: a non-Kazakh dataset must say its region and geography"


def test_dictionaries_have_unique_codes_and_unambiguous_patterns():
    for name in ("okved_sections", "expenditure_items"):
        d = dims.load_dictionary(name)
        codes = [e["code"] for e in d]
        assert len(codes) == len(set(codes))
        for e in d:                                  # the canonical name must resolve to its own code only
            assert dims.match_item(e["name_ru"], d) == (e["code"], e["name_ru"]), e["code"]


@pytest.mark.parametrize("label, code", [
    ("  Строительство", "F"), ("Электроснабжение", "D"), ("Снабжение электроэнергией, газом", "D"),
    ("Услуги по проживанию и питанию", "I"), ("Предоставление услуг по проживанию и питанию", "I"),
    ("Оптовая и розничнаяторговля; ремонт", "G"), ("Деятельность в области административного", "N"),
    ("Деятельность домашних хозяйств, нанимающих", "T"), (" 2025 год3)", None), ("Итого по отраслям", "TOTAL"),
    ("Чистые налоги на продукты", "NET_TAXES"), ("Налоги на продукты", "TAXES"), ("Производство услуг", "SERVICES"),
])
def test_section_labels_seen_in_bns_files_resolve(label, code):
    d = dims.load_dictionary("okved_sections")
    got = dims.match_item(label, d)
    assert (got[0] if got else None) == code


def test_expenditure_labels_distinguish_total_from_its_parts():
    d = dims.load_dictionary("expenditure_items")
    assert dims.match_item("Валовое накопление", d)[0] == "GROSS_CAPITAL_FORMATION"
    assert dims.match_item("валовое накопление основного капитала", d)[0] == "GFCF"
    assert dims.match_item("экспорт товаров и услуг1)", d)[0] == "EXPORTS"
    assert dims.match_item("Валовой внутренний продукт2)", d)[0] == "GDP"


def test_periods_across_takes_annual_columns_only_and_dates_them_at_year_end():
    grid = [
        ["Индекс физического объема", None, None, None, None, None],
        ["ОКЭД", "1 квартал 2024г.", "1 полугодие 2024г.", "2024 год", "1 квартал 2025г.", " 2025 год3)"],
        ["Сельское, лесное и рыбное хозяйство", 101.0, 102.0, 113.7, 99.0, 105.7],
        ["Строительство", "-", "-", "112.0", "…", "108.1"],
        ["1) Расчет предварительный", None, None, None, None, None],
    ]
    d = dims.load_dictionary("okved_sections")
    recs = bns_dims.parse_periods_across(grid, d, 0, DS)
    assert {(r["date"], r["item_code"], r["value"]) for r in recs} == {
        ("2024-12-31", "A", 113.7), ("2025-12-31", "A", 105.7), ("2024-12-31", "F", 112.0), ("2025-12-31", "F", 108.1)}


def test_periods_across_stops_on_an_unknown_data_label():
    grid = [["ОКЭД", "2024 год", "2025 год"], ["Сельское хозяйство", 1.0, 2.0], ["Новая строка БНС", 3.0, 4.0]]
    d = dims.load_dictionary("okved_sections")
    with pytest.raises(validation.StructuralChangeError) as exc:
        bns_dims.parse_periods_across(grid, d, 0, DS)
    assert "Новая строка БНС" in str(exc.value) and "ACTION REQUIRED" in str(exc.value)


def test_region_blocks_reads_the_national_block_annual_rows_and_codes():
    grid = [
        ["111203", "Валовая добавленная стоимость", None, None, None],
        [None, None, None, None, None],
        ["код КАТО", "Наименование регионов", "Промышленность- всего", "Горнодобывающая промышленность", "Добыча угля"],
        [None, None, None, "B", 5],
        ["0", "Республика Казахстан", None, None, None],
        [None, "9 месяцев 2024 года", 100.0, 60.0, 5.0],
        [None, "2024 год", 130.0, 80.0, 7.5],
        [None, "I квартал 2025 года", 30.0, 20.0, 2.0],
        ["11", "Акмолинская", None, None, None],
        [None, "2024 год", 9.0, 5.0, 1.0],
    ]
    recs = bns_dims.parse_region_blocks(grid, {**DS, "dictionary": "from_table"})
    assert {(r["item_code"], r["value"]) for r in recs} == {("IND", 130.0), ("B", 80.0), ("05", 7.5)}
    assert all(r["date"] == "2024-12-31" and r["region"] == "national" for r in recs)


def test_year_subcolumns_picks_the_requested_sub_column():
    grid = [
        [None, "2024 год", None, "2025 год *", None],
        [None, "Ненаблюдаемая экономика", "в том числе", "Ненаблюдаемая экономика", "в том числе"],
        [None, None, "Незаконная", None, "Незаконная"],
        ["Производство товаров", 5.2, 0.5, 4.6, 0.3],
        ["Итого по отраслям", 16.7, 1.2, 15.7, 1.1],
    ]
    d = dims.load_dictionary("okved_sections")
    total = bns_dims.parse_year_subcolumns(grid, d, 0, 0, DS)
    illegal = bns_dims.parse_year_subcolumns(grid, d, 0, 1, DS)
    assert {(r["date"], r["item_code"], r["value"]) for r in total} == {
        ("2024-12-31", "GOODS", 5.2), ("2025-12-31", "GOODS", 4.6), ("2024-12-31", "TOTAL", 16.7), ("2025-12-31", "TOTAL", 15.7)}
    assert {r["value"] for r in illegal if r["item_code"] == "GOODS"} == {0.5, 0.3}


def test_year_subcolumns_with_the_ownership_header_regex():
    grid = [[None, "2010г.", None, None, None, "2011г.", None, None, None],
            [None, "ВДС", "в том числе", None, None, "ВДС", "в том числе", None, None],
            ["Образование", 10.0, 7.0, 3.0, 0.0, 12.0, 8.0, 4.0, 0.0]]
    d = dims.load_dictionary("okved_sections")
    state = bns_dims.parse_year_subcolumns(grid, d, 0, 1, DS, re.compile(r"^\s*(\d{4})\s*г\.?\s*$"))
    assert [(r["date"], r["value"]) for r in state] == [("2010-12-31", 7.0), ("2011-12-31", 8.0)]


def test_validate_rejects_duplicate_date_item_pairs():
    recs = [{"date": "2024-12-31", "item_code": "A", "item_name": "a", "value": 1.0},
            {"date": "2024-12-31", "item_code": "A", "item_name": "a", "value": 2.0}]
    assert not dims.validate(recs, "TEST", "annual").ok


def test_detect_revisions_keys_on_date_and_item():
    old = [{"date": "2024-12-31", "item_code": "A", "value": "1.0"}, {"date": "2024-12-31", "item_code": "B", "value": "5.0"}]
    new = [{"date": "2024-12-31", "item_code": "A", "value": 1.5}, {"date": "2024-12-31", "item_code": "B", "value": 5.0}]
    revs = dims.detect_revisions("TEST", "bns", old, new, __import__("datetime").date(2026, 9, 14))
    assert [(r.period, r.old_value, r.new_value) for r in revs] == [("2024-12-31 A", 1.0, 1.5)]


def test_long_columns_extend_the_scalar_contract():
    from lib import unified
    assert dims.LONG_COLUMNS[:5] == unified.LONG_COLUMNS[:5]
    assert "item_code" in dims.LONG_COLUMNS and "item_name" in dims.LONG_COLUMNS
    assert dims.PROCESSED_COLUMNS[:2] == ["date", "region"]


@pytest.mark.parametrize("label, code", [
    ("Республика Казахстан ", "national"), ("РЕСПУБЛИКА КАЗАХСТАН", "national"), ("Абай", "ABY"), ("Область Абай3)", "ABY"),
    ("Акмолинская область ", "AKM"), ("АКМОЛИНСКАЯ ОБЛАСТЬ", "AKM"), ("З-Казахстанская ", "ZKO"), ("Западно-Казахстанская", "ZKO"),
    ("Жетісу", "ZHT"), ("Жетысу", "ZHT"), ("Ұлытау", "ULT"), ("Ю-Казахстанская ", "YKO"), ("Туркестанская3)", "TRK"), ("Туркестанская*", "TRK"),
    ("В-Казахстанская", "VKO"), ("г. Астана", "AST"), ("г.Алматы ", "ALA"), ("Г.АЛМАТЫ", "ALA"), ("г.Шымкент3)", "SHM"),
    ("Абайский район", None), ("Кокшетау г.а.", None), ("Семей г.а.", None), ("Среднегодовая численность населения", None),
])
def test_region_labels_seen_in_bns_files_and_the_model_resolve(label, code):
    hit = dims.match_region(label)
    assert (hit[0] if hit else None) == code


def test_periods_across_with_region_rows_and_plain_year_headers():
    ds = {**DS, "row_dimension": "region", "fixed_item": "TOTAL", "fixed_item_name": "Занятое население"}
    grid = [["Занятое население1)", None, None], [None, 2024.0, "2025"], ["Республика Казахстан", 9214.184, 9320.639],
            ["Абай", "-", 295.87], ["Акмолинская ", 401.827, 400.109], ["1)Данные сформированы", None, None]]
    recs = bns_dims.parse_periods_across(grid, None, 0, ds, re.compile(r"^\s*(\d{4})(?!\d)"))
    assert {(r["region"], r["date"][:4], r["value"]) for r in recs} == {
        ("national", "2024", 9214.184), ("national", "2025", 9320.639), ("ABY", "2025", 295.87), ("AKM", "2024", 401.827), ("AKM", "2025", 400.109)}
    assert all(r["item_code"] == "TOTAL" for r in recs)


def test_periods_across_region_rows_stop_on_an_unknown_region_unless_not_strict():
    ds = {**DS, "row_dimension": "region", "fixed_item": "TOTAL"}
    grid = [[None, "2024", "2025"], ["Республика Казахстан", 1.0, 2.0], ["Новая область", 3.0, 4.0]]
    with pytest.raises(validation.StructuralChangeError):
        bns_dims.parse_periods_across(grid, None, 0, ds, re.compile(r"^\s*(\d{4})(?!\d)"))
    recs = bns_dims.parse_periods_across(grid, None, 0, {**ds, "strict": False}, re.compile(r"^\s*(\d{4})(?!\d)"))
    assert {r["region"] for r in recs} == {"national"}


def test_region_blocks_over_all_regions_with_dictionary_item_names():
    ds = {**DS, "regions": "all"}
    grid = [
        ["111203", "ВДС", None, None, None, None],
        [None, None, None, None, None, None],
        ["КАТО коды", None, "Валовой региональный продукт", "Валовая добавленная стоимость", None, "Чистые налоги на продукты"],
        [None, None, None, "Сельское, лесное и рыбное хозяйство", "Промышленность", None],
        ["0", "Республика Казахстан", None, None, None, None],
        [None, "9 месяцев 2024 года", 100.0, 5.0, 40.0, 8.0],
        [None, "2024 год", 136.0, 5.3, 42.0, 8.3],
        ["10", "Абай", None, None, None, None],
        [None, "2024 год", 2.0, 0.3, 0.9, 0.1],
    ]
    d = dims.load_dictionary("okved_sections")
    recs = bns_dims.parse_region_blocks(grid, ds, d)
    assert {(r["region"], r["item_code"], r["value"]) for r in recs} == {
        ("national", "GDP", 136.0), ("national", "A", 5.3), ("national", "IND", 42.0), ("national", "NET_TAXES", 8.3),
        ("ABY", "GDP", 2.0), ("ABY", "A", 0.3), ("ABY", "IND", 0.9), ("ABY", "NET_TAXES", 0.1)}


def test_group_blocks_reads_population_groups_and_sex_subgroups():
    ds = {**DS, "groups": {"ALL": "^все население", "URBAN": "^городское население", "MEN": "^мужчины"}, "subgroups": ["MEN"]}
    grid = [["Код КАТО", None, "2024.0", "2025"], [None, "Все население", None, None], [None, "Республика Казахстан ", 20158620.5, 20391610.5],
            ["100000000", "Абай", 605210.5, 600000.0], [None, "Мужчины", None, None], ["100000000", "Абай", 300000.0, 299000.0],
            [None, "Городское население", None, None], ["100000000", "Абай", 373392.5, 370000.0], [None, "*Данные пересчитаны", None, None]]
    recs = bns_dims.parse_group_blocks(grid, ds, re.compile(r"^\s*(\d{4})"))
    assert {(r["region"], r["item_code"], r["date"][:4], r["value"]) for r in recs} == {
        ("national", "ALL", "2024", 20158620.5), ("national", "ALL", "2025", 20391610.5), ("ABY", "ALL", "2024", 605210.5), ("ABY", "ALL", "2025", 600000.0),
        ("ABY", "ALL_MEN", "2024", 300000.0), ("ABY", "ALL_MEN", "2025", 299000.0), ("ABY", "URBAN", "2024", 373392.5), ("ABY", "URBAN", "2025", 370000.0)}


def test_year_subcolumns_skips_a_year_that_lacks_the_requested_sub_column():
    grid = [[None, "2003 год", "2004 год", "в % к прошлому году", "2005 год", "в % к прошлому году"],
            ["Всего", 1327864.2, 1703684.0, 123.1, 2420976.0, 134.1]]
    ds = {**DS, "label_overrides": {"всего": "TOTAL"}}
    d = dims.load_dictionary("okved_sections")
    pct = bns_dims.parse_year_subcolumns(grid, d, 0, 1, ds)
    assert {(r["date"][:4], r["value"]) for r in pct} == {("2004", 123.1), ("2005", 134.1)}      # 2003 has no % column
    val = bns_dims.parse_year_subcolumns(grid, d, 0, 0, ds)
    assert {(r["date"][:4], r["value"]) for r in val} == {("2003", 1327864.2), ("2004", 1703684.0), ("2005", 2420976.0)}


def test_latin_lookalikes_inside_cyrillic_labels_still_resolve():
    d = dims.load_dictionary("okved_sections")
    assert dims.match_item("Cнабжение электроэнергией, газом", d)[0] == "D"     # Latin C as BNS typed it in 5831


def test_product_and_industry_dictionaries_resolve_their_own_names_uniquely():
    for name in ("products", "industry_divisions"):
        d = dims.load_dictionary(name)
        assert len({e["code"] for e in d}) == len(d)
        for e in d:
            assert dims.match_item(e["name_ru"], d) == (e["code"], e["name_ru"]), (name, e["code"])


@pytest.mark.parametrize("label, code", [
    ("Нефть, включая конденсат газовый, тыс.тонн", "OIL_INCL_CONDENSATE"),
    ("нефть сырая (природная смесь углеводородов),\nвключая нефть, полученную из минералов\nбитуминозных, тыс. тонн", "CRUDE_OIL"),
    ("Газ природный в жидком или газообразном состоянии, млн.куб.м", "NATURAL_GAS"),
    ("газ природный (естественный) в газообразном состоянии (товарный выпуск), млн.куб.м", "NATURAL_GAS_MARKETABLE"),
    ("Электроэнергия,  млн.кВт.ч", "ELECTRICITY"), ("Обувь с верхом из кожи, кроме спортивной обуви", "LEATHER_FOOTWEAR"),
    ('"-" - Нет производства.', None), ("Ұлытау", None),
])
def test_product_labels_from_5814_resolve(label, code):
    hit = dims.match_item(label, dims.load_dictionary("products"))
    assert (hit[0] if hit else None) == code


@pytest.mark.parametrize("label, code", [
    ("Итого по промышленности", "IND"), ("Добыча сырой нефти и природного газа", "06"), ("Добыча сырой нефти", "06.1"),
    ("Производство  хлебобулочных, макаронных и мучных кондитерских изделий", "10.7"), ("Производство прочих продуктов питания", "10.8"),
    ("Производство прочей не металлической минеральной продукции", "23"), ("Черная металлургия, кроме литья металлов", "24.1"),
    ("Cнабжение паром, горячей водой и кондиционированным воздухом", "35.3"), ("Збор, обработка и распределение воды", "36"),
])
def test_industry_labels_from_5792_resolve(label, code):
    assert dims.match_item(label, dims.load_dictionary("industry_divisions"))[0] == code


def test_product_blocks_reads_products_and_their_regions():
    grid = [[None, " ", "2024", "2025"], [None, None, None, None],
            ["Уголь каменный, включая лигнит и концентрат угольный, тыс. тонн", None, None, None],
            ["Республика Казахстан", None, 112986.3, 120044.6], ["Абай", None, 7580.6, 6927.4], ["Ұлытау", None, "..", ".."],
            ["Соль и хлорид натрия чистый,  вода морская, тонн", None, None, None], ["Республика Казахстан", None, 1.0, 2.0],
            ["Какой-то продукт вне справочника, тонн", None, None, None], ["Республика Казахстан", None, 9.0, 9.0],
            ['"-" - Нет производства.', None, None, None]]
    ds = {**DS, "dictionary": "products", "strict": False}
    recs = bns_dims.parse_product_blocks(grid, dims.load_dictionary("products"), ds, re.compile(r"^\s*(\d{4})(?!\d)"))
    assert {(r["item_code"], r["region"], r["date"][:4], r["value"]) for r in recs} == {
        ("COAL", "national", "2024", 112986.3), ("COAL", "national", "2025", 120044.6), ("COAL", "ABY", "2024", 7580.6), ("COAL", "ABY", "2025", 6927.4),
        ("SALT", "national", "2024", 1.0), ("SALT", "national", "2025", 2.0)}


def test_group_blocks_with_labels_in_column_a_and_unknown_groups_skipped():
    grid = [["Валовой сбор", None, None], [None, "2024", "2025"], ["Всего", None, None], ["Республика Казахстан", 25204.8, 25946.3],
            ["Мангыстауская", "-", "-"], ["из них:\nпшеницы", None, None], ["Республика Казахстан", 17000.0, 18000.0],
            ["ячменя", None, None], ["Республика Казахстан", 3000.0, 3100.0]]
    ds = {**DS, "label_col": 0, "groups": {"TOTAL": "^всего", "WHEAT": "пшениц"}, "skip_unknown_groups": True}
    recs = bns_dims.parse_group_blocks(grid, ds, re.compile(r"^\s*(\d{4})(?!\d)"))
    assert {(r["item_code"], r["value"]) for r in recs} == {("TOTAL", 25204.8), ("TOTAL", 25946.3), ("WHEAT", 17000.0), ("WHEAT", 18000.0)}


def test_periods_across_with_a_code_column_keeps_codes_and_skips_uncoded_rows():
    grid = [["Код ОКЭД", "Наименование", "2024.0", "2025.0"], ["А", "Сельское, лесное и рыбное хозяйство", 113.6, 105.9],
            ["011", "Выращивание сезонных культур", 122.8, 107.8], [None, "Сельское хозяйство", 113.7, 105.8]]
    recs = bns_dims.parse_periods_across(grid, None, 1, {**DS, "code_col": 0}, re.compile(r"^\s*(\d{4})"))
    assert {(r["item_code"], r["date"][:4], r["value"]) for r in recs} == {("A", "2024", 113.6), ("A", "2025", 105.9), ("011", "2024", 122.8), ("011", "2025", 107.8)}


def test_legacy_xls_is_recognised_by_signature_not_extension():
    assert bns_dims.is_legacy_xls(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16)
    assert not bns_dims.is_legacy_xls(b"PK\x03\x04" + b"\x00" * 16)


def test_detect_revisions_labels_regions():
    old = [{"date": "2024-12-31", "region": "AKM", "item_code": "TOTAL", "value": "1.0"}]
    new = [{"date": "2024-12-31", "region": "AKM", "item_code": "TOTAL", "value": 2.0}]
    revs = dims.detect_revisions("TEST", "bns", old, new, __import__("datetime").date(2026, 9, 14))
    assert revs[0].period == "2024-12-31 TOTAL @AKM"


def test_unified_long_file_is_written_gzipped_and_read_back(tmp_path):
    import gzip
    import model_sync
    rows = [{"date": "2024-12-31", "country": "KZ", "region": "national", "frequency": "annual", "variable": "X", "item_code": "A",
             "item_name": "a", "value": 1.5, "unit": "u", "source": "bns", "source_version": "2026-09-23", "transformation": "level", "last_updated": "2026-09-23"}]
    p = dims.write_long_csv(rows, tmp_path / "macro_dims_long.csv.gz")
    assert p.exists() and gzip.open(p, "rt", encoding="utf-8").readline().startswith("date,country,region")
    assert model_sync.load_unified_dims(p)[("X", "A", "national")][0].value == 1.5
    plain = dims.write_long_csv(rows, tmp_path / "plain.csv")
    assert model_sync.load_unified_dims(plain)[("X", "A", "national")][0].value == 1.5
    assert dims.UNIFIED_PATH.name.endswith(".csv.gz")


def test_year_patterns_accept_a_footnoted_year_but_not_a_longer_number():
    """The labour tables head 2015 as '20152)' (year + footnote 2). The old pattern
    `(\\d{4})(?!\\d)` rejected it, and 2015 vanished from six regional datasets and
    EMPLOYED_TOTAL (audit 2026-09-25)."""
    patterns = {ds["year_regex"] for ds in dims.load_config()["datasets"] if "(?=" in ds.get("year_regex", "")}
    assert patterns
    for p in patterns:
        rx = re.compile(p)
        assert rx.search("20152)").group(1) == "2015"
        assert rx.search("2016").group(1) == "2016"
        assert rx.search("2021 1)").group(1) == "2021"
        assert rx.search("201501") is None


def test_regional_labour_tables_have_no_missing_year():
    for ds_id in ("EMPLOYED_BY_REGION", "LABOUR_FORCE_BY_REGION", "UNEMPLOYED_BY_REGION",
                  "EMPLOYEES_BY_REGION", "SELF_EMPLOYED_BY_REGION", "UNEMPLOYMENT_RATE_BY_REGION"):
        years = sorted({int(r["date"][:4]) for r in dims.load_processed(ds_id) if r.get("region") == dims.NATIONAL})
        assert years == list(range(years[0], years[-1] + 1)), ds_id
