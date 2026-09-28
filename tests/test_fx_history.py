"""Official exchange rates before the NBK daily report (added 2026-09-28, key fx_hist):
the NBK archive «Архив официальных курсов валют с 1993 по 1999» spliced in before
1999-11-17 for EXCHANGE_RATE, _EUR, _CNY and _RUB (scripts/fetchers/nbk.py).

Fixtures only (no network): the workbook is given as the rows archive_sheet_rows would
return, laid out like the real file (codes row with asterisks and footnotes on sheet
'1993-1998'; Russian names with quantities, span labels and the CHY code on sheet '1999').
The last test reads the processed series and is skipped until the history is loaded."""
import csv
import sys
from datetime import date
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import nbk  # noqa: E402
from lib import validation  # noqa: E402

FOOTNOTES = [["*    среднегодовые и среднемесячные"], ["**   за 10 единиц валюты"], ["***  за 100 единиц валюты"],
             ["**** за 1000 единиц валюты (по российскому рублю номинал 1*1000 действовал  до 1 января 1998 года)"]]


def _sheet_9398(footnotes=FOOTNOTES, extra_rows=()):
    blank = ["", "", "", "", "", ""]
    return [
        blank, ["Официальные курсы валют"], ["тенге за единицу"],
        ["", "BEF**", "CNY", "ECU", "USD", "RUR****"],
        ["Дата вступления в силу", "белг. франк", "китайск. Юань", "ЭКЮ", "доллар США", "росс. Рубль"],
        [date(1993, 11, 1), "", "", "", "", ""],                       # month header
        [date(1993, 11, 18), 1.3, "-", 5.5, 4.704, 4.0],
        [date(1993, 11, 19), 1.3, "-", 5.5, 4.68, 3.9],
        [date(1993, 12, 1), "", "", "", "", ""],
        [date(1993, 12, 31), 1.8, "-", 7.0, 6.31, 5.1],
        [date(1996, 5, 6), 21.3, 7.95, 80.0, 66.2, 12.9],
        [date(1996, 5, 13), 21.4, "- -", 80.1, 66.4, 12.9],             # CNY not quoted that week
        [date(1996, 5, 20), 21.5, 7.95, 80.2, 66.5, 12.9],
        ["Декабрь 1997", "", "", "", "", ""],
        [date(1997, 12, 29), 20.0, 9.1, 85.0, 75.55, 13.0],             # per 1000 old roubles
        ["Январь 1998", "", "", "", "", ""],
        [date(1998, 1, 5), 20.1, 9.1, 85.1, 75.55, 13.0],               # per 1 new rouble
        ["19.04 .1998", 20.2, 9.2, 85.2, 76.5, "13,02"],                # text date with a stray space, comma decimal
        [date(1998, 12, 28), 24.23, 10.12, 100.14, 83.8, 4.29],
        *extra_rows,
        blank, *footnotes,
    ]


def _sheet_1999(extra=()):
    return [
        ["", "", "", "", "", ""],
        ["", "10 бельг. франков", "Доллар США", "Евро", "Китайский юань", "Российский рубль"],
        ["", "BEF", "USD", "EUR", "CHY", "RUB"],
        ["Январь 1999", "", "", "", "", ""],
        ["4-8.01.1999", 25.38, 84.0, 96.6, 10.15, 4.2],
        ["", "", "", "", "", ""],
        ["Апрель 1999", "", "", "", "", ""],
        ["1-4.04.1999", 30.0, 87.5, 97.13, 10.57, 3.37],
        ["5,6.04.1999", 34.0, 100.0, 110.75, 12.08, 3.92],
        [date(1999, 4, 7), 40.0, 118.0, 130.57, 14.25, 4.63],
        ["Май 1999", "", "", "", "", ""],
        [date(1999, 5, 6), 38.0, 116.0, 127.02, 14.01, 4.9],
        ["4.05.2002", 38.1, 117.0, 128.12, 14.13, 4.98],               # the source's typo for 07.05.1999
        ["8-10.05.1999", 38.1, 117.0, 126.95, 14.13, 4.98],
        ["Ноябрь 1999", "", "", "", "", ""],
        ["15-16.11.1999", 35.9, 140.0, 149.38, 16.91, 5.23],
        [date(1999, 11, 17), 35.9, 139.8, 146.76, 16.89, 5.28],
        [date(1999, 11, 18), 35.9, 139.8, 146.76, 16.89, 5.28],
        ["19-21.11.1999", 35.9, 139.8, 146.76, 16.89, 5.28],
        ["22,23.11.1999", 35.8, 139.0, 145.13, 16.79, 5.23],
        *extra,
    ]


def _sheets(**kw):
    return {"1993-1998": _sheet_9398(**kw), "1999": _sheet_1999()}


# ---------------------------------------------------------------- labels and units

def test_row_labels_read_as_the_first_day_they_cover():
    assert nbk._archive_label_date("1999", "4-8.01.1999") == date(1999, 1, 4)
    assert nbk._archive_label_date("1999", "24,25,26.11.1999") == date(1999, 11, 24)
    assert nbk._archive_label_date("1999", "05-07.06.1999") == date(1999, 6, 5)
    assert nbk._archive_label_date("1999", "4.05.1999") == date(1999, 5, 4)
    assert nbk._archive_label_date("1993-1998", "19.04 .1995") == date(1995, 4, 19)
    assert nbk._archive_label_date("1999", date(1999, 4, 7)) == date(1999, 4, 7)
    assert nbk._archive_label_date("1999", "4.05.2002") == date(1999, 5, 7)       # known typo
    for header in ("Январь 1999", "", "Дата вступления в силу", "**   за 10 единиц валюты"):
        assert nbk._archive_label_date("1999", header) is None


def test_schedule_units_aliases_and_the_rouble_in_new_roubles():
    s = nbk.parse_official_rates_archive(_sheets())
    usd = dict(s["USD"])
    assert usd[date(1993, 11, 18)] == 4.704 and usd[date(1999, 4, 5)] == 100.0
    assert dict(s["BEF"])[date(1993, 11, 18)] == 0.13                 # '**' = per 10
    assert dict(s["BEF"])[date(1999, 1, 4)] == 2.538                  # '10 бельг. франков' = per 10
    assert "CHY" not in s and dict(s["CNY"])[date(1999, 1, 4)] == 10.15
    assert dict(s["CNY"])[date(1993, 11, 18)] is None and dict(s["CNY"])[date(1996, 5, 13)] is None
    # the rouble: '****' (per 1000) until 1997 = per ONE new rouble after the 1000:1 redenomination
    # of 1998-01-01, and per 1 new rouble from 1998 -- the printed figure throughout, no 1000x step
    rub = dict(s["RUB"])
    assert "RUR" not in s
    assert rub[date(1993, 11, 18)] == 4.0 and rub[date(1997, 12, 29)] == 13.0 and rub[date(1998, 1, 5)] == 13.0
    assert rub[date(1998, 4, 19)] == 13.02 and rub[date(1999, 1, 4)] == 4.2
    assert dict(s["EUR"]) and min(dict(s["EUR"])) == date(1999, 1, 4)  # no euro before 1999
    assert min(dict(s["ECU"])) == date(1993, 11, 18)                  # the ECU stays the ECU
    assert date(1999, 5, 7) in dict(s["USD"])                         # the '4.05.2002' row


# ---------------------------------------------------------------- weekday series

def test_weekday_series_is_the_rate_in_force_each_weekday():
    w = nbk.archive_weekday_series(nbk.parse_official_rates_archive(_sheets()))
    usd = w["USD"]
    assert min(usd) == "1993-11-18" and usd["1993-11-18"] == 4.704 and usd["1993-11-19"] == 4.68
    assert usd["1993-11-22"] == 4.68                         # Monday carries Friday's row
    assert "1993-11-20" not in usd and "1993-11-21" not in usd  # weekends dropped
    assert usd["1993-12-31"] == 6.31
    assert usd["1999-01-01"] == 83.8                         # the 1998-12-28 rate until the first 1999 row
    assert usd["1999-04-02"] == 87.5 and usd["1999-04-05"] == usd["1999-04-06"] == 100.0 and usd["1999-04-07"] == 118.0
    assert usd["1999-05-07"] == 117.0 and usd["1999-11-16"] == 140.0 and usd["1999-12-31"] == 139.0
    cny = w["CNY"]
    assert min(cny) == "1996-05-06"                          # '-' before: no series
    assert "1996-05-13" not in cny and "1996-05-17" not in cny and cny["1996-05-20"] == 7.95  # '- -' week is a hole
    assert "1998-12-31" in w["ECU"] and "1999-01-01" not in w["ECU"]   # not in the 1999 sheet: ends with 1998
    assert min(w["EUR"]) == "1999-01-04"
    rub = w["RUB"]
    assert rub["1997-12-31"] == rub["1998-01-02"] == rub["1998-01-05"] == 13.0


# ---------------------------------------------------------------- structure checks

def test_missing_rouble_footnote_stops_the_parser():
    with pytest.raises(validation.StructuralChangeError, match="footnote"):
        nbk.parse_official_rates_archive(_sheets(footnotes=FOOTNOTES[:3]))


def test_missing_sheet_or_header_stops_the_parser():
    with pytest.raises(validation.StructuralChangeError, match="no sheet"):
        nbk.parse_official_rates_archive({"1993-1998": _sheet_9398()})
    no_usd = {"1993-1998": _sheet_9398(), "1999": [[c.replace("USD", "US$") if isinstance(c, str) else c for c in r]
                                                    for r in _sheet_1999()]}
    with pytest.raises(validation.StructuralChangeError, match="USD"):
        nbk.parse_official_rates_archive(no_usd)


def test_rows_out_of_order_stop_the_parser():
    bad = {"1993-1998": _sheet_9398(), "1999": _sheet_1999(extra=[["1-3.12.1998", 1.0, 80.0, 90.0, 10.0, 4.0]])}
    with pytest.raises(validation.StructuralChangeError):
        nbk.parse_official_rates_archive(bad)


# ---------------------------------------------------------------- overlap with the report

def _report_from(archive: dict[str, float], **override) -> dict[str, float]:
    rep = {d: v for d, v in archive.items() if d >= "1999-11-17"}
    rep.update({"1999-10-19": 142.0, "1999-10-20": 142.12})      # the report's malformed first rows
    rep.update(override)
    return rep


def test_overlap_check_passes_on_equal_values_and_returns_the_report_start(monkeypatch):
    monkeypatch.setattr(nbk, "ARCHIVE_MIN_OVERLAP_DAYS", 5)
    usd = nbk.archive_weekday_series(nbk.parse_official_rates_archive(_sheets()))["USD"]
    assert nbk.check_archive_overlap("USD", usd, _report_from(usd)) == "1999-11-17"


def test_overlap_check_raises_on_any_difference(monkeypatch):
    monkeypatch.setattr(nbk, "ARCHIVE_MIN_OVERLAP_DAYS", 5)
    usd = nbk.archive_weekday_series(nbk.parse_official_rates_archive(_sheets()))["USD"]
    with pytest.raises(validation.StructuralChangeError, match="disagree on 1 of"):
        nbk.check_archive_overlap("USD", usd, _report_from(usd, **{"1999-12-01": 138.01}))


def test_overlap_check_raises_on_too_few_or_no_common_days(monkeypatch):
    usd = nbk.archive_weekday_series(nbk.parse_official_rates_archive(_sheets()))["USD"]
    monkeypatch.setattr(nbk, "ARCHIVE_MIN_OVERLAP_DAYS", 1000)
    with pytest.raises(validation.StructuralChangeError, match="at least 1000"):
        nbk.check_archive_overlap("USD", usd, _report_from(usd))
    with pytest.raises(validation.StructuralChangeError, match="no USD rate"):
        nbk.check_archive_overlap("USD", usd, {"1999-10-19": 142.0})


# ---------------------------------------------------------------- the fetcher, offline

def _offline(monkeypatch, tmp_path, stored=None, report_override=None, archive_error=False):
    monkeypatch.setattr(nbk.raw_store, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(nbk, "ARCHIVE_MIN_OVERLAP_DAYS", 5)
    series = nbk.archive_weekday_series(nbk.parse_official_rates_archive(_sheets()))

    def archive():
        if archive_error:
            raise requests.ConnectionError("offline")
        return series

    def report(begin=None, end=None, raw_id="EXCHANGE_RATES_OFFICIAL"):
        if raw_id == "EXCHANGE_RATES_OFFICIAL_1999":
            return {c: _report_from(series[c], **(report_override or {})) for c in ("USD", "EUR", "CNY", "RUB")}
        return {"USD": {"2026-09-25": 480.0, "2026-09-26": 480.0}}   # the daily window (a Saturday is dropped)

    monkeypatch.setattr(nbk, "_official_rates_archive", archive)
    monkeypatch.setattr(nbk, "_official_rates", report)
    monkeypatch.setattr(nbk, "_load_processed_series", lambda ind: dict(stored or {}))
    return series


def test_fetcher_splices_the_archive_before_the_report(monkeypatch, tmp_path):
    stored = {"1999-11-17": 139.8, "1999-11-18": 139.8, "2026-09-24": 479.0}
    _offline(monkeypatch, tmp_path, stored=stored)
    records, manifest = nbk.fetch_exchange_rate_usd()
    s = {r["date"]: r["value"] for r in records}
    assert min(s) == "1993-11-18" and s["1993-12-31"] == 6.31 and s["1999-04-05"] == 100.0
    assert s["1999-11-16"] == 140.0 and s["1999-11-17"] == 139.8          # archive before, report from 1999-11-17
    assert "1999-11-22" not in s                                           # archive rows after the start are not used
    assert s["2026-09-24"] == 479.0 and s["2026-09-25"] == 480.0 and "2026-09-26" not in s
    assert manifest["history_source_url"] == nbk.OFFICIAL_RATES_ARCHIVE_URL
    assert "Before 1999-11-17" in manifest["note"] and "from 1993-11-18" in manifest["note"]


def test_fetcher_eur_starts_1999_and_rub_note_names_the_unit(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    eur, m_eur = nbk.fetch_exchange_rate_eur()
    assert eur[0]["date"] == "1999-01-04" and "ECU" in m_eur["note"]
    rub, m_rub = nbk.fetch_exchange_rate_rub()
    assert rub[0] == {"date": "1993-11-18", "value": 4.0} and "new rouble" in m_rub["note"]


def test_fetcher_stops_when_archive_and_report_disagree(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path, report_override={"1999-11-18": 139.9})
    with pytest.raises(validation.StructuralChangeError, match="disagree"):
        nbk.fetch_exchange_rate_usd()


def test_unreachable_archive_keeps_history_already_processed_but_not_a_first_load(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path, stored={"1993-11-18": 4.704, "1999-11-17": 139.8}, archive_error=True)
    records, manifest = nbk.fetch_exchange_rate_usd()
    assert records[0] == {"date": "1993-11-18", "value": 4.704} and "not reachable" in manifest["note"]
    _offline(monkeypatch, tmp_path, stored={"1999-11-17": 139.8}, archive_error=True)
    with pytest.raises(requests.ConnectionError):
        nbk.fetch_exchange_rate_usd()


# ---------------------------------------------------------------- the processed series (after a load)

def test_processed_history_holds_known_points():
    path = REPO_ROOT / "data" / "processed" / "nbk" / "exchange_rate.csv"
    with path.open(encoding="utf-8") as f:
        usd = {r["date"]: float(r["value"]) for r in csv.DictReader(f) if r["value"]}
    if min(usd) > "1999-01-01":
        pytest.skip("EXCHANGE_RATE history before 1999-11-17 not loaded yet (pending/fx_hist.md)")
    assert min(usd) == "1993-11-18" and usd["1993-11-18"] == 4.704
    ends = {"1993-12-31": 6.31, "1994-12-30": 54.26, "1995-12-29": 63.95, "1996-12-31": 73.3,
            "1997-12-31": 75.55, "1998-12-31": 83.8, "1999-12-31": 138.2}
    assert all(usd[d] == v for d, v in ends.items())
    assert usd["1999-04-02"] == 87.5 and usd["1999-04-05"] == 100.0 and usd["1999-04-07"] == 118.0
