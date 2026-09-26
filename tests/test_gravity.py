"""Gravity-model datasets (scripts/fetchers/gravity.py): BNS trade by partner, WITS, WDI."""
import csv
import io
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetchers import gravity  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bns_book(sheets: dict[str, list[list]]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=name, header=False, index=False)
    return buf.getvalue()


HEADER = [["Основные показатели", None, None, None, None, None, None],
          [None, "Товарооборот", "%", "Экспорт", "%", "Импорт", "%"]]


def test_bns_partner_file_takes_country_rows_and_checks_the_total():
    rows = HEADER + [["Всего", 30.0, 100, 20.0, 100, 10.0, 100],
                     ["Страны СНГ", 12.0, None, 5.0, None, 7.0, None],
                     ["Россия", 12.0, None, 5.0, None, 7.0, None],
                     ["Европа", 18.0, None, 15.0, None, 3.0, None],
                     ["Италия", 15.0, None, 15.0, None, None, None],     # blank import cell: no flow
                     ["Андорра", 3.0, None, None, None, 3.0, None],
                     ["*Предварительные данные", None, None, None, None, None, None]]
    content = _bns_book({"12_2021": rows, "12_2020": rows, "Лист1": [[1]]})
    out = gravity.parse_bns_partner_file(content, "exports")
    assert set(out) == {2020, 2021}
    assert out[2021] == {"Россия": 5.0, "Италия": 15.0, "Андорра": 0.0}
    assert gravity.parse_bns_partner_file(content, "imports")[2021]["Италия"] == 0.0


def test_bns_partner_file_rejects_rows_that_do_not_add_up():
    rows = HEADER + [["Всего", 30.0, 100, 20.0, 100, 10.0, 100], ["Россия", 12.0, None, 5.0, None, 7.0, None]]
    with pytest.raises(ValueError, match="sum"):
        gravity.parse_bns_partner_file(_bns_book({"2025": rows}), "exports")


def test_full_year_editions_prefer_the_final_edition():
    listings = [
        {"eid": "1", "title": "Основные показатели внешней торговли РК по странам (январь-декабрь 2025г.)", "released": "2026-02-13"},
        {"eid": "2", "title": "Основные показатели внешней торговли РК по странам (2025г.)", "released": "2026-07-27"},
        {"eid": "3", "title": "Основные показатели внешней торговли РК по странам (январь-июль 2026г.)", "released": "2026-09-14"},
        {"eid": "4", "title": "Основные показатели внешней торговли РК по странам (январь-декабрь 2026г.)", "released": "2027-02-12"},
    ]
    best = gravity.full_year_editions(listings)
    assert {y: e["eid"] for y, e in best.items()} == {2025: "2", 2026: "4"}
    assert best[2025]["final"] and not best[2026]["final"]


def test_parse_bns_listing():
    page = ('<div class="divTableRow" id="bx_123_347387"><div class="divTableCell">'
            '<a href="/api/iblock/element/347387/file/ru/"> Основные показатели внешней торговли РК по странам (2025г.) </a>'
            '</div><div class="divTableCell text-right"> 27.07.2026 </div></div>')
    assert gravity.parse_bns_listing(page) == [{"eid": "347387", "released": "2026-07-27",
                                                "title": "Основные показатели внешней торговли РК по странам (2025г.)"}]


def test_parse_sdmx_json():
    payload = {"structure": {"dimensions": {
        "series": [{"id": "PARTNER", "values": [{"id": "RUS", "name": "Russia"}, {"id": "ROM", "name": "Romania"}]},
                   {"id": "INDICATOR", "values": [{"id": "XPRT-TRD-VL"}]}],
        "observation": [{"id": "TIME_PERIOD", "values": [{"id": "2022"}, {"id": "2023"}]}]}},
        "dataSets": [{"series": {"0:0": {"observations": {"0": [9091.0], "1": [10207.0]}},
                                 "1:0": {"observations": {"1": [12.5]}}}}]}
    rows = gravity.parse_sdmx_json(payload)
    assert [(r["PARTNER"], r["TIME_PERIOD"], r["value"]) for r in rows] == [
        ("RUS", "2022", 9091.0), ("RUS", "2023", 10207.0), ("ROM", "2023", 12.5)]
    assert gravity.WITS_LEGACY_CODES["ROM"] == "ROU"


def test_partner_dictionary_is_unique_and_iso3():
    with (REPO_ROOT / "dictionaries" / "partner_countries.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    names = [" ".join(r["name_ru"].split()).casefold() for r in rows]
    assert len(names) == len(set(names))
    assert all(len(r["code"]) == 3 and r["code"].isupper() for r in rows)
    for name, code in (("Российская Федерация", "RUS"), ("Китай", "CHN"), ("Италия", "ITA")):
        hit = gravity.partner_names().get(name.casefold())
        assert hit is None or hit[0] == code


def test_reference_tables_are_keyed_by_iso3():
    geo = pd.read_csv(REPO_ROOT / "data" / "reference" / "cepii_geodist_kaz.csv")
    grav = pd.read_csv(REPO_ROOT / "data" / "reference" / "cepii_gravity_kaz.csv")
    assert geo["iso3"].is_unique and not grav.duplicated(["iso3", "year"]).any()
    rus = grav[(grav.iso3 == "RUS") & (grav.year == 2021)].iloc[0]
    assert rus.contig == 1 and rus.fta_wto == 1
