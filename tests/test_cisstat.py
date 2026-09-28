"""CIS Stat datasets (scripts/fetchers/cisstat.py): GDP volume, CPI, population and migration for
the CIS countries. Fixtures are small excerpts of the answers of
https://new.cisstat.org/consstat/service/fact/data/{fact}/freq/44?locale=ru as downloaded on
2026-09-28 (values unchanged); no network."""
import gzip
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import cisstat  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402
import update_derived  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
TAIL = ["Значение", "Примечание", "Дата_обновления", "Оценочное", "Точность"]
STAMP = "2026-09-17T13:02:44.987380"

# Kazakhstan 1991-1999 as the committee publishes them (checked live 2026-09-28)
KZ_GDP = {1991: "89.0", 1992: "94.7", 1993: "90.8", 1994: "87.4", 1995: "91.8", 1996: "100.5", 1997: "101.7",
          1998: "98.1", 1999: "102.7"}
KZ_CPI_DEC = {1991: "247.1", 1992: "3060.8", 1993: "2265.0", 1994: "1258.3", 1995: "160.33", 1996: "128.7",
              1997: "111.16", 1998: "101.93", 1999: "117.83"}
KZ_CPI_AVG = {1991: "190.9", 1992: "1614.8", 1993: "1758.4", 1994: "1977.4", 1995: "276.2", 1996: "139.35",
              1997: "117.39", 1998: "107.12", 1999: "108.31"}
KZ_ARR = {1991: 170787, 1992: 161499, 1993: 111082, 1994: 70389, 1995: 71137, 1996: 53874, 1997: 38067,
          1998: 40624, 1999: 41320, 2000: 47442, 2008: 46404}
KZ_DEP = {1991: 228473, 1992: 317760, 1993: 330107, 1994: 477068, 1995: 309632, 1996: 229412, 1997: 299455,
          1998: 243663, 1999: 164947, 2000: 155749, 2008: 45287}


def payload(dims_cols: list[str], rows: list[list], max_update: str = STAMP) -> dict:
    """An answer: header = the fact's dimensions + TAIL; each row = dimension cells + [value, estimate]."""
    data = [dims_cols + TAIL]
    for r in rows:
        *cells, value, est = r
        data.append(list(cells) + [value, None, max_update, est, "1"])
    return {"dateLabel": "Дата", "valueScale": 1, "maxUpdateDate": max_update, "data": data}


def rows_of(p: dict, fact: int, table: str, extra=()) -> list[dict]:
    return cisstat.parse_payload(json.dumps(p, ensure_ascii=False).encode(), fact, cisstat.REQUIRED[table] + tuple(extra))[0]


def gdp_payload(extra_rows=()) -> dict:
    rows = [["Казахстан", str(y), v, "f"] for y, v in KZ_GDP.items()]
    rows += [["Россия", "1992", "85.5", "f"], ["Кыргызстан", "1993", "84.5", "f"], ["CHГ", "2025", "102.1", "t"]]
    return payload(["Страны", "Год"], rows + list(extra_rows))


def cpi_payload(extra_rows=()) -> dict:
    rows = []
    for y in KZ_GDP:
        rows.append(["Казахстан", "К декабрю предыдущего года", "Все товары и услуги", "Декабрь", str(y), KZ_CPI_DEC[y], "f"])
        rows.append(["Казахстан", "К соответствующему периоду предыдущего года", "Все товары и услуги", "Декабрь", str(y), KZ_CPI_DEC[y], "f"])
        rows.append(["Казахстан", "Период с начала года к соответствующему периоду предыдущего года", "Все товары и услуги",
                     "Декабрь", str(y), KZ_CPI_AVG[y], "f"])
    rows += [["Казахстан", "К декабрю предыдущего года", "Все товары и услуги", "Ноябрь", "1994", "1156.0", "f"],
             ["Казахстан", "К предыдущему периоду", "Все товары и услуги", "Декабрь", "1994", "108.0", "f"],
             ["Казахстан", "К декабрю предыдущего года", "Продовольственные товары", "Декабрь", "1994", "1155.7", "f"],
             ["Узбекистан", "Период с начала года к соответствующему периоду предыдущего года", "Все товары и услуги",
              "Декабрь", "1994", "1381.0", "f"]]
    return payload(["Страны", "В % к", "Потребительские товары и услуги", "Периоды", "Год"], rows + list(extra_rows))


def population_payloads() -> tuple[dict, dict]:
    boy = [["Казахстан", "Всего", "Всего", str(y), str(16358.2 - (y - 1991) * 100), "f"] for y in range(1991, 2000)]
    boy += [["Казахстан", "Женщины", "Городская местность", "2026", "6846.3250000000001424035600", "f"],
            ["Казахстан", "Мужчины", "Всего", "1991", "7912.2", "f"],
            ["Казахстан", "Всего", "Сельская местность", "1991", "6991.3", "f"]]
    avg = [["Казахстан", "Всего", str(y), str(16404.95 - (y - 1991) * 100), "f"] for y in range(1991, 2000)]
    avg += [["Россия", "Городская местность", "1991", "108736.0", "f"]]
    return (payload(["Страны", "Справочник половозрастных характеристик", "Тип местности", "Год"], boy),
            payload(["Страны", "Тип местности", "Год"], avg))


def migration_payloads(kz_rus_2020: str = "3599") -> tuple[dict, dict, dict, dict]:
    cols = ["Страны", "Территориальный справочник по миграции", "Год"]
    arr = [["Казахстан", "Международная миграция - всего", str(y), str(v), "f"] for y, v in KZ_ARR.items()]
    dep = [["Казахстан", "Международная миграция - всего", str(y), str(v), "f"] for y, v in KZ_DEP.items()]
    arr += [["Казахстан", "Международная миграция - всего", "2020", "11370", "f"],
            ["Казахстан", "Всего по странам СНГ", "2020", "8277", "f"],
            ["Казахстан", "Другие страны (исключая страны СНГ) - всего", "2020", "3093", "f"],
            # «Неизвестно» and «Внутри страны» come twice per country and year: not keyable, not kept
            ["Казахстан", "Неизвестно", "2020", "0", "f"], ["Казахстан", "Неизвестно", "2020", "5", "f"],
            ["Казахстан", "Внутри страны", "2020", "390987", "f"], ["Казахстан", "Внутри страны", "2020", "454213", "f"],
            ["Армения", "Международная миграция - всего", "2020", "5961", "f"]]
    dep += [["Казахстан", "Международная миграция - всего", "2020", "29088", "f"],
            ["Армения", "Международная миграция - всего", "2020", "2587", "f"]]
    pcols = ["Страны", "Тип местности", "Территориальный справочник по миграции", "Год"]
    kz_partners = {"Россия": kz_rus_2020, "Узбекистан": "2554", "Туркменистан": "1189", "Кыргызстан": "465",
                   "Азербайджан": "176", "Таджикистан": "150", "Украина": "70", "Беларусь": "42", "Армения": "23",
                   "Молдова": "9", "Казахстан": "0"}
    parr = [["Казахстан", "Всего", p, "2020", v, "f"] for p, v in kz_partners.items()]
    parr += [["Казахстан", "Всего", "Всего по странам СНГ", "2020", "8277", "f"],
             ["Казахстан", "Всего", "Международная миграция - всего", "2020", "11370", "f"],
             ["Казахстан", "Городская местность", "Россия", "2020", "3000", "f"],
             ["Армения", "Всего", "Россия", "2020", "100", "f"],           # Armenia's CIS total: 101 (a warning)
             ["Армения", "Всего", "Всего по странам СНГ", "2020", "101", "f"]]
    pdep = [["Казахстан", "Всего", "Россия", "2020", "25126", "f"], ["Казахстан", "Всего", "Беларусь", "2020", "234", "f"]]
    return payload(cols, arr), payload(cols, dep), payload(pcols, parr), payload(pcols, pdep)


def migration_rows(**kw):
    a, d, pa, pd_ = migration_payloads(**kw)
    return [rows_of(p, 1, "migration") for p in (a, d, pa, pd_)]


# ---------------------------------------------------------------- parse_payload

def test_payload_is_read_by_column_name():
    rows = rows_of(gdp_payload(), 714662, "gdp_volume")
    assert rows[0] == {"Страны": "Казахстан", "Год": "1991", "Значение": "89.0", "Примечание": None,
                       "Дата_обновления": STAMP, "Оценочное": "f", "Точность": "1"}


@pytest.mark.parametrize("content, what", [
    (b"<html>maintenance</html>", "not JSON"),
    (b'{"rows": []}', "no 'data' table"),
    (json.dumps({"data": [["Страны", "Год", "Значение"]]}).encode(), "columns"),
    (json.dumps({"data": [["Страны", "Год", "Значение", "Оценочное"]]}).encode(), "empty"),
    (json.dumps({"data": [["Страны", "Год", "Значение", "Оценочное"], ["Казахстан", "1991"]]}).encode(), "does not match"),
])
def test_payload_format_changes_are_refused(content, what):
    with pytest.raises(cisstat.FormatError, match=what):
        cisstat.parse_payload(content, 714662, cisstat.REQUIRED["gdp_volume"])


def test_country_names_map_to_iso3_including_the_latin_spelt_cis_aggregate():
    assert cisstat.country_code("Казахстан") == "KAZ" and cisstat.country_code(" Россия ") == "RUS"
    assert cisstat.country_code("CHГ") == "CIS" and cisstat.country_code("СНГ") == "CIS"
    with pytest.raises(cisstat.FormatError, match="unknown country"):
        cisstat.country_code("Абхазия")


# ---------------------------------------------------------------- tables

def test_gdp_volume_index_for_kazakhstan_matches_bns_gdp_real_1991_1999():
    recs = cisstat.gdp_records(rows_of(gdp_payload(), 714662, "gdp_volume"))
    kz = {r["date"]: r["value"] for r in recs if r["region"] == "KAZ"}
    assert kz["1991-12-31"] == 89.0 and kz["1992-12-31"] == 94.7 and kz["1993-12-31"] == 90.8
    assert {r["region"] for r in recs} == {"KAZ", "RUS", "KGZ", "CIS"} and {r["item_code"] for r in recs} == {"GDP"}
    assert [r["transformation"] for r in recs if r["region"] == "CIS"] == ["estimate"]
    bns = {line.split(",")[0]: float(line.split(",")[1])
           for line in (REPO_ROOT / "data" / "processed" / "bns" / "gdp_real.csv").read_text().splitlines()[1:]}
    assert all(bns[d] == v for d, v in kz.items()), "CIS Stat and BNS GDP_REAL differ in the 1990s"


def test_gdp_stops_on_unknown_country_duplicates_and_missing_1990s():
    with pytest.raises(cisstat.FormatError, match="unknown country"):
        cisstat.gdp_records(rows_of(gdp_payload([["Абхазия", "1995", "90.0", "f"]]), 714662, "gdp_volume"))
    with pytest.raises(cisstat.FormatError, match="two values"):
        cisstat.gdp_records(rows_of(gdp_payload([["Казахстан", "1991", "88.0", "f"]]), 714662, "gdp_volume"))
    with pytest.raises(cisstat.FormatError, match="not a number"):
        cisstat.gdp_records(rows_of(gdp_payload([["Россия", "1995", "н/д", "f"]]), 714662, "gdp_volume"))
    short = payload(["Страны", "Год"], [["Казахстан", str(y), v, "f"] for y, v in KZ_GDP.items() if y != 1992])
    with pytest.raises(cisstat.FormatError, match="GDP 1992"):
        cisstat.gdp_records(rows_of(short, 714662, "gdp_volume"))


def test_cpi_keeps_december_rows_as_separate_dec_dec_and_average_items():
    recs = cisstat.cpi_records(rows_of(cpi_payload(), 43370, "cpi"))
    kz = {(r["item_code"], r["date"][:4]): r["value"] for r in recs if r["region"] == "KAZ"}
    assert kz[("TOTAL.DEC_DEC", "1994")] == 1258.3 and kz[("TOTAL.AVG", "1994")] == 1977.4
    assert kz[("TOTAL.DEC_DEC", "1992")] == 3060.8 and kz[("TOTAL.AVG", "1991")] == 190.9
    assert kz[("FOOD.DEC_DEC", "1994")] == 1155.7
    assert {r["item_code"] for r in recs} == {"TOTAL.DEC_DEC", "TOTAL.AVG", "FOOD.DEC_DEC"}   # no November, no m/m
    assert all(r["date"].endswith("-12-31") for r in recs)
    assert next(r for r in recs if r["region"] == "UZB")["item_code"] == "TOTAL.AVG"


def test_cpi_stops_on_new_labels_and_on_inconsistent_december_bases():
    with pytest.raises(cisstat.FormatError, match="CPI group"):
        cisstat.cpi_records(rows_of(cpi_payload([["Казахстан", "К декабрю предыдущего года", "Алкоголь", "Декабрь", "1994", "1.0", "f"]]), 43370, "cpi"))
    with pytest.raises(cisstat.FormatError, match="CPI base"):
        cisstat.cpi_records(rows_of(cpi_payload([["Казахстан", "К базисному году", "Товары", "Декабрь", "1994", "1.0", "f"]]), 43370, "cpi"))
    bad = cpi_payload()
    for row in bad["data"][1:]:
        if row[1] == "К соответствующему периоду предыдущего года" and row[4] == "1995":
            row[5] = "170.0"
    with pytest.raises(cisstat.FormatError, match="differs"):
        cisstat.cpi_records(rows_of(bad, 43370, "cpi"))


def test_population_dates_the_start_of_year_stock_on_1_january():
    boy, avg = population_payloads()
    recs = cisstat.population_records(rows_of(boy, 44176, "population", ["Справочник половозрастных характеристик"]),
                                      rows_of(avg, 44177, "population"))
    by = {(r["region"], r["item_code"], r["date"]): r["value"] for r in recs}
    assert by[("KAZ", "BOY", "1991-01-01")] == 16358.2 and by[("KAZ", "AVG", "1991-12-31")] == 16404.95
    assert by[("KAZ", "BOY.MEN", "1991-01-01")] == 7912.2 and by[("KAZ", "BOY.RURAL", "1991-01-01")] == 6991.3
    assert by[("KAZ", "BOY.WOMEN.URBAN", "2026-01-01")] == 6846.325           # the service's long decimals, rounded
    assert by[("RUS", "AVG.URBAN", "1991-12-31")] == 108736.0


def test_population_stops_on_an_unknown_area():
    boy, avg = population_payloads()
    avg["data"].append(["Казахстан", "Пригород", "1991", "1.0", None, STAMP, "f", "1"])
    with pytest.raises(cisstat.FormatError, match="area"):
        cisstat.population_records(rows_of(boy, 44176, "population", ["Справочник половозрастных характеристик"]),
                                   rows_of(avg, 44177, "population"))


def test_migration_totals_net_and_partner_countries():
    recs, warnings = cisstat.migration_records(*migration_rows())
    kz = {(r["item_code"], r["date"][:4]): r for r in recs if r["region"] == "KAZ"}
    assert kz[("ARRIVALS", "1994")]["value"] == 70389 and kz[("DEPARTURES", "1994")]["value"] == 477068
    assert kz[("NET", "1994")]["value"] == 70389 - 477068 and kz[("NET", "1994")]["transformation"] == "arrivals minus departures"
    assert kz[("ARRIVALS.CIS", "2020")]["value"] == 8277 and kz[("ARRIVALS.NON_CIS", "2020")]["value"] == 3093
    assert kz[("ARRIVALS.RUS", "2020")]["value"] == 3599 and kz[("DEPARTURES.RUS", "2020")]["value"] == 25126
    assert kz[("ARRIVALS.KAZ", "2020")]["value"] == 0                          # own row kept (Moldova's is not 0)
    assert not any(c.endswith("UNKNOWN") for c, _ in kz) and ("ARRIVALS", "2020") in kz
    assert all(r["region"] != "KAZ" or r["item_code"] != "ARRIVALS.RUS" or r["value"] != 3000 for r in recs)   # urban rows skipped
    assert warnings == ["ARRIVALS.CIS @ARM 2020-12-31: partner countries sum to 100, the CIS total is 101"]
    assert {r["date"][:4] for r in recs if r["region"] == "KAZ" and r["item_code"] == "NET"} >= {str(y) for y in range(1991, 2000)}


def test_migration_checks_are_hard_for_kazakhstan():
    with pytest.raises(cisstat.FormatError, match="partner countries sum"):
        cisstat.migration_records(*migration_rows(kz_rus_2020="3600"))
    a, d, pa, pd_ = migration_payloads()
    for row in pa["data"][1:]:
        if row[0] == "Казахстан" and row[2] == "Международная миграция - всего":
            row[4] = "11371"
    with pytest.raises(cisstat.FormatError, match="flow fact 11370.0, partner fact 11371.0"):
        cisstat.migration_records(*[rows_of(p, 1, "migration") for p in (a, d, pa, pd_)])
    a["data"].append(["Казахстан", "Возвратная миграция", "2020", "1", None, STAMP, "f", "0"])
    with pytest.raises(cisstat.FormatError, match="migration flow"):
        cisstat.migration_records(*[rows_of(p, 1, "migration") for p in (a, d, pa, pd_)])


# ---------------------------------------------------------------- fetch: archive, hard checks, refresh

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_store, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(dims, "PROCESSED_ROOT", tmp_path / "dims")
    return tmp_path


def test_fetch_archives_the_raw_answer_and_reports_the_update_date(sandbox, monkeypatch):
    calls = []
    body = json.dumps(gdp_payload(), ensure_ascii=False).encode()
    monkeypatch.setattr(cisstat, "_get", lambda url, timeout=180: calls.append(url) or body)
    ds = {"id": "CIS_GDP_VOLUME_INDEX", "table": "gdp_volume", "min_countries": 3}
    recs, info = cisstat.fetch(ds)
    assert calls == ["https://new.cisstat.org/consstat/service/fact/data/714662/freq/44?locale=ru"]
    assert info["dataset_id"] == "cisstat/714662" and info["release"] == "2026-09-17"
    raw = sandbox / "raw" / "cisstat" / f"cisstat_cis_gdp_volume_index_714662_{date.today().isoformat()}.json.gz"
    assert gzip.decompress(raw.read_bytes()) == body
    assert json.loads(raw.with_name(raw.name.replace(".json.gz", ".manifest.json")).read_text())["fact"] == 714662
    # stored and downloaded today: the next run returns the stored records (transformation kept)
    dims.write_processed(ds["id"], recs)
    again, info2 = cisstat.fetch(ds)
    assert len(calls) == 1 and "not re-downloaded" in info2["warnings"][0]
    assert sorted((r["region"], r["date"], r["value"], r["transformation"]) for r in again) == \
        sorted((r["region"], r["date"], r["value"], r["transformation"]) for r in recs)


def test_fetch_turns_format_changes_into_structural_change(sandbox, monkeypatch):
    changed = gdp_payload()
    changed["data"][0][0] = "Страна"                                   # a renamed column
    monkeypatch.setattr(cisstat, "_get", lambda url, timeout=180: json.dumps(changed, ensure_ascii=False).encode())
    with pytest.raises(validation.StructuralChangeError, match="STRUCTURAL CHANGE DETECTED in cisstat/CIS_GDP_VOLUME_INDEX"):
        cisstat.fetch({"id": "CIS_GDP_VOLUME_INDEX", "table": "gdp_volume", "refresh_days": 0})
    monkeypatch.setattr(cisstat, "_get", lambda url, timeout=180: json.dumps(gdp_payload(), ensure_ascii=False).encode())
    with pytest.raises(validation.StructuralChangeError, match="only 3 countries"):
        cisstat.fetch({"id": "CIS_GDP_VOLUME_INDEX", "table": "gdp_volume", "refresh_days": 0})


def test_fetch_reads_all_four_migration_facts(sandbox, monkeypatch):
    a, d, pa, pd_ = migration_payloads()
    by_fact = {4650866: a, 4679599: d, 44243: pa, 44245: pd_}
    monkeypatch.setattr(cisstat, "_get", lambda url, timeout=180: json.dumps(
        by_fact[int(url.split("/data/")[1].split("/")[0])], ensure_ascii=False).encode())
    recs, info = cisstat.fetch({"id": "CIS_MIGRATION", "table": "migration", "min_countries": 2, "refresh_days": 0})
    assert info["dataset_id"] == "cisstat/4650866+4679599+44243+44245" and info["warnings"]
    assert len(list((sandbox / "raw" / "cisstat").glob("*.json.gz"))) == 4


# ---------------------------------------------------------------- the scalar MIGRATION_* back to 1991

def test_migration_scalars_are_gap_filled_from_1991_with_2008_as_a_known_difference():
    recs, _ = cisstat.migration_records(*migration_rows())
    rows = [{**r, "value": str(r["value"])} for r in recs]
    own = [{"date": "2000-12-31", "value": "47442.0"}, {"date": "2008-12-31", "value": "46113.0"}]   # BNS
    spec = {"dataset": "CIS_MIGRATION", "item": "ARRIVALS", "region": "KAZ"}
    with pytest.raises(validation.StructuralChangeError, match="differs"):
        update_derived.fill_gaps({"id": "MIGRATION_ARRIVALS", "gaps_filled_from": spec}, own, rows)
    spec["known_differences"] = {date(2008, 12, 31): "BNS revised 2008 (46 113); CIS Stat 46 404"}   # as YAML loads it
    merged, added = update_derived.fill_gaps({"id": "MIGRATION_ARRIVALS", "gaps_filled_from": spec}, own, rows)
    by = {r["date"]: r["value"] for r in merged}
    assert added == 10 and by["1994-12-31"] == 70389 and by["2008-12-31"] == 46113.0 and min(by) == "1991-12-31"
    own[0]["value"] = "47000.0"                              # an unlisted difference still stops the fill
    with pytest.raises(validation.StructuralChangeError):
        update_derived.fill_gaps({"id": "MIGRATION_ARRIVALS", "gaps_filled_from": spec}, own, rows)
