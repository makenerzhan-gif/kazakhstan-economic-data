"""EXCHANGE_RATES_OFFICIAL_MONTHLY back to 1993 (added 2026-09-28, key fx_monthly_hist):
the NBK daily report from 1999-11 and the NBK archive 1993-1999 before it, redenominations
restated to the current unit (scripts/fetchers/nbk_fx.py), and the NEER history that
follows from it (scripts/fetchers/neer_import.py).

Fixtures only (no network) except the last tests, which read the processed files and are
skipped until the history is loaded."""
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from fetchers import nbk, nbk_fx, neer_import  # noqa: E402
from lib import validation  # noqa: E402

FOOTNOTES = [["**   за 10 единиц валюты"], ["***  за 100 единиц валюты"],
             ["**** за 1000 единиц валюты (по российскому рублю номинал 1*1000 действовал  до 1 января 1998 года)"]]


def _sheets():
    """The archive workbook as archive_sheet_rows returns it: CHF, TRL per 1000, USD, BYB per 100,
    RUR per 1000 and UZS (per 1000 sum-coupons in 1993-1994, unmarked) on '1993-1998'."""
    s9398 = [
        ["Официальные курсы валют"], ["тенге за единицу"],
        ["", "CHF", "TRL****", "USD", "BYB***", "RUR****", "UZS"],
        ["Дата вступления в силу", "швейц. Франк", "турец. лира", "доллар США", "беларус. Рубль", "росс. Рубль", "узбекс. Сумы"],
        [date(1993, 11, 1), "", "", "", "", "", ""],
        [date(1993, 11, 18), 3.16, 0.3, 4.704, 0.1, 4.0, "-"],
        [date(1993, 12, 21), 3.5, 0.45, 6.0, 0.81, 4.5, 1.51],
        [date(1994, 1, 5), 20.0, 0.54, 30.0, 1.11, 5.5, 1.8],
        [date(1995, 4, 14), 53.83, 1.23, 62.0, 0.52, 13.0, "-"],
        [date(1995, 4, 17), 12.83, 1.23, 62.1, 0.52, 13.1, "-"],     # the French franc's figure under CHF (as in the source)
        [date(1995, 4, 19), 55.38, 1.24, 62.25, 0.52, 13.2, "-"],
        [date(1997, 12, 29), 53.0, 0.4, 75.55, "-", 13.0, "-"],
        [date(1998, 1, 5), 53.1, 0.4, 75.55, "-", 13.0, "-"],          # the rouble: per 1 new = per 1000 old
        [date(1998, 12, 28), 60.0, 0.27, 83.8, "-", 4.29, "-"],
        [""], *FOOTNOTES,
    ]
    s1999 = [
        [""],
        ["", "Доллар США", "1000 турецких лир", "Швейцарский франк", "Российский рубль", "Евро"],
        ["", "USD", "TRL", "CHF", "RUB", "EUR"],
        ["Январь 1999", "", "", "", "", ""],
        ["4-8.01.1999", 84.0, 0.27, 62.22, 4.2, 96.6],
        ["15-16.11.1999", 140.0, 0.27, 89.0, 5.23, 149.38],
        [date(1999, 11, 17), 139.8, 0.27, 89.1, 5.28, 146.76],
        ["18-21.11.1999", 139.9, 0.27, 89.2, 5.3, 146.8],
    ]
    return {"1993-1998": s9398, "1999": s1999}


def _html(rows):
    """A one-currency report page: rows of (ISO date, quantity, rate)."""
    body = "".join(f"<tr><td>{d}</td><td>{q}</td><td>{r}</td></tr>" for d, q, r in rows)
    return f"<table><tr><th></th><th>Числовое значение</th><th>X</th></tr>{body}</table>"


def _days(first: str, last: str):
    d, end = date.fromisoformat(first), date.fromisoformat(last)
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)


# ---------------------------------------------------------------- redenominations

def test_restatement_by_source_and_switch_day():
    # the report: BYR per unit up to Fri 2016-07-01 inclusive (set on 06-30), BYN from 07-02
    rep = nbk_fx.redenominate("BYN", {"2016-06-30": 0.0169, "2016-07-01": 0.0168, "2016-07-04": 170.73}, "report")
    assert rep == pytest.approx({"2016-06-30": 169.0, "2016-07-01": 168.0, "2016-07-04": 170.73})
    # the archive's BYB: both redenominations, 1000 x 10 000
    assert nbk_fx.redenominate("BYN", {"1994-01-05": 0.0111}, "archive")["1994-01-05"] == pytest.approx(111000.0)
    assert nbk_fx.redenominate("TRY", {"1995-04-14": 0.00123}, "archive")["1995-04-14"] == pytest.approx(1230.0)
    # sources already in the new unit are left alone: the rouble in the archive, the report after the date
    assert nbk_fx.redenominate("RUB", {"1997-12-31": 13.0}, "archive") == {"1997-12-31": 13.0}
    assert nbk_fx.redenominate("TRY", {"2005-01-06": 94.44}, "report") == {"2005-01-06": 94.44}
    assert nbk_fx.redenominate("USD", {"1993-11-18": 4.704}, "archive") == {"1993-11-18": 4.704}


def test_expected_break_must_be_in_the_data():
    quoted = {"2016-06-30": 0.0169, "2016-07-01": 0.0168, "2016-07-04": 170.73}
    found = nbk_fx.check_redenominations("BYN", "report", quoted)
    assert found == ["BYN BYR->BYN 2016-07-02 (report): x10,162 at the date"]
    # the source already quotes BYN before the switch day: the expected step is absent
    with pytest.raises(validation.StructuralChangeError, match="expected in the quote but absent"):
        nbk_fx.check_redenominations("BYN", "report", {"2016-06-30": 169.0, "2016-07-04": 170.73})
    # no rate on both sides within the window: nothing to check (AZN 2006, TJS 2000, PLN 1995)
    assert nbk_fx.check_redenominations("AZN", "report", {"2014-02-25": 20.0}) == []
    assert nbk_fx.check_redenominations("TRY", "report", {"2005-01-06": 94.44, "2005-01-07": 92.79}) == []


def test_a_break_where_the_source_already_quotes_new_units_stops_the_fetcher():
    ok = nbk_fx.check_redenominations("RUB", "archive", {"1997-12-31": 13.0, "1998-01-05": 13.0})
    assert ok == ["RUB RUR->RUB 1998-01-01 (archive): quoted in new units, no step (x1.000)"]
    with pytest.raises(validation.StructuralChangeError, match="absorbed in the quote but a step"):
        nbk_fx.check_redenominations("RUB", "archive", {"1997-12-31": 0.013, "1998-01-05": 13.0})


def test_unexpected_thousandfold_step_stops_the_fetcher_but_a_long_gap_does_not():
    with pytest.raises(validation.StructuralChangeError, match="unexpected step x1000"):
        nbk_fx.check_no_jumps("KGS", {"2001-03-01": 3.0, "2001-03-02": 3000.0})
    nbk_fx.check_no_jumps("BYN", {"1997-02-24": 34000.0, "2014-02-25": 190.0})     # 17 years apart
    nbk_fx.check_no_jumps("TRY", {"2021-12-20": 29.72, "2021-12-21": 24.97, "2021-12-22": 35.51})


def test_uzs_before_the_sum_is_per_1000_coupons():
    nbk_fx.check_uzs_coupon_scale({"UZS": {"1994-01-05": 1.8}, "RUB": {"1994-01-05": 5.5}})
    with pytest.raises(validation.StructuralChangeError, match="UZS before 1994-07-01"):
        nbk_fx.check_uzs_coupon_scale({"UZS": {"1994-01-05": 0.0018}, "RUB": {"1994-01-05": 5.5}})


# ---------------------------------------------------------------- the archive

def test_archive_rates_precision_units_and_restatement():
    rates, found = nbk_fx.archive_rates(_sheets())
    assert set(rates) == {"USD", "EUR", "RUB", "TRY", "BYN", "CHF", "UZS"}
    usd = rates["USD"]
    assert usd["1993-11-18"] == 4.704 and usd["1993-11-22"] == 4.704           # the rate in force on each weekday
    # TRL per 1000: printed 0.3 / 0.45 / 0.54 dropped (precision), 1.23 = 1230 KZT per new lira
    assert min(rates["TRY"]) == "1995-04-14" and rates["TRY"]["1995-04-14"] == pytest.approx(1230.0)
    # 0.4 and 0.27 per 1000 dropped; a currency whose last usable figure is in 1995 ends with that year
    assert max(rates["TRY"]) == "1995-12-29"
    # BYB per 100: 0.1 and 0.81 dropped, 1.11 -> 0.0111 per BYB -> x10 000 000 per BYN; 0.52 dropped
    assert rates["BYN"] == pytest.approx({d: 111000.0 for d in _weekdays("1994-01-05", "1994-12-30")})
    # UZS 1993-12-21 1.51 (per 1000 coupons = one sum), no restatement
    assert rates["UZS"]["1993-12-21"] == 1.51 and rates["UZS"]["1994-01-05"] == 1.8
    # the rouble in new roubles, no step over 1998-01-01; the check is reported
    assert rates["RUB"]["1997-12-31"] == rates["RUB"]["1998-01-05"] == 13.0
    assert "RUB RUR->RUB 1998-01-01 (archive): quoted in new units, no step (x1.000)" in found
    # CHF 1995-04-17: the French franc's 12.83 in the source's CHF column, kept as published (source_issues)
    chf = rates["CHF"]
    assert chf["1995-04-14"] == 53.83 and chf["1995-04-17"] == chf["1995-04-18"] == 12.83 and chf["1995-04-19"] == 55.38
    assert min(rates["EUR"]) == "1999-01-04"


def _weekdays(first, last):
    return [d for d in _days(first, last) if date.fromisoformat(d).weekday() < 5]


def test_splice_checks_the_overlap_and_starts_the_report_on_its_first_day(monkeypatch):
    monkeypatch.setattr(nbk, "ARCHIVE_MIN_OVERLAP_DAYS", 5)
    rates, _ = nbk_fx.archive_rates(_sheets())
    usd = rates["USD"]
    report = {d: v for d, v in usd.items() if d >= "1999-11-17"}
    report["2000-01-04"] = 138.5
    merged, how = nbk_fx.splice("USD", usd, report)
    assert min(merged) == "1993-11-18" and merged["1999-11-16"] == 140.0 and merged["1999-11-17"] == 139.8
    assert merged["2000-01-04"] == 138.5 and "equal to the report" in how
    with pytest.raises(validation.StructuralChangeError, match="disagree on 1 of"):
        nbk_fx.splice("USD", usd, {**report, "1999-11-18": 139.95})


def test_splice_without_overlap_keeps_the_archive_alone():
    rates, _ = nbk_fx.archive_rates(_sheets())
    merged, how = nbk_fx.splice("TRY", rates["TRY"], {"2005-01-06": 94.44})
    assert min(merged) == "1995-04-14" and merged["2005-01-06"] == 94.44 and "no overlap" in how
    assert nbk_fx.splice("KRW", {}, {"2000-05-29": 0.1253}) == ({"2000-05-29": 0.1253}, "")


def test_report_starts_1999_11_and_windows_cover_the_range():
    page = _html([("1999-10-19", 1, 5), ("1999-10-20", 10, 5), ("1999-11-17", 10, 13.51), ("2008-12-03", 1, 1.3)])
    daily, found = nbk_fx.report_rates("JPY", [page])
    assert daily == pytest.approx({"1999-11-17": 1.351, "2008-12-03": 1.3}) and found == []
    w = nbk_fx.report_windows(date(1999, 11, 1), date(2026, 9, 28))
    assert w[0] == (date(1999, 11, 1), date(2008, 12, 31)) and w[-1][1] == date(2026, 9, 28)
    assert all(b + timedelta(days=1) == c for (_, b), (c, _) in zip(w, w[1:]))


# ---------------------------------------------------------------- the fetcher, offline

SUBSET = {"USD": ("5", "Доллар США"), "TRY": ("41", "Турецкая лира"), "CHF": ("23", "Швейцарский франк"),
          "RUB": ("16", "Российский рубль"), "BYN": ("38", "Белорусский рубль")}


def _offline(monkeypatch, tmp_path, stored, archive_calls):
    monkeypatch.setattr(nbk.raw_store, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(nbk, "ARCHIVE_MIN_OVERLAP_DAYS", 5)
    monkeypatch.setattr(nbk_fx, "CURRENCIES", SUBSET)
    monkeypatch.setattr(nbk_fx.dims, "load_processed", lambda ds_id: stored)
    rates, _ = nbk_fx.archive_rates(_sheets())
    windows = []

    def sheets():
        archive_calls.append(1)
        return _sheets()

    def pages(code, begin, end):
        windows.append((code, begin))
        if code == "TRY":
            return [_html([("2005-01-06", 1, 94.44), ("2005-01-07", 1, 92.79)])]
        if code == "BYN":
            return [_html([("2016-06-30", 100, 1.69), ("2016-07-01", 100, 1.68), ("2016-07-02", 1, 170.73),
                           ("2016-07-04", 1, 170.73)])]
        tail = {"USD": 138.5, "CHF": 90.0, "RUB": 5.2}[code]
        rows = [("1999-10-19", 1, 5)] + [(d, 1, v) for d, v in rates[code].items() if d >= "1999-11-17"]
        return [_html(rows + [("2000-01-04", 1, tail)])]

    monkeypatch.setattr(nbk, "official_rates_archive_sheets", sheets)
    monkeypatch.setattr(nbk_fx, "_report_pages", pages)
    return windows


def test_first_load_splices_the_archive_from_1993(monkeypatch, tmp_path):
    calls = []
    windows = _offline(monkeypatch, tmp_path, stored=[
        {"date": "2010-01-01", "region": "national", "item_code": "USD", "item_name": "x", "value": "148.1"}], archive_calls=calls)
    records, manifest = nbk_fx.fetch({"id": "EXCHANGE_RATES_OFFICIAL_MONTHLY", "note": "n"})
    m = {(r["item_code"], r["date"]): r["value"] for r in records}
    assert calls and {b for _, b in windows} == {date(1999, 11, 1)}
    assert m[("USD", "1993-11-01")] == 4.704
    assert m[("USD", "2000-01-01")] == 138.5 and ("USD", "1999-10-01") in m
    assert m[("TRY", "1995-04-01")] == pytest.approx((3 * 1230 + 8 * 1240) / 11) and m[("TRY", "2005-01-01")] == pytest.approx(93.615)
    assert m[("BYN", "1994-01-01")] == pytest.approx(111000.0)
    assert m[("BYN", "2016-07-01")] == pytest.approx((168.0 + 170.73) / 2)       # Fri 1 July in BYR, restated
    assert 13.0 < m[("RUB", "1997-12-01")] < 13.2 and m[("RUB", "1998-01-01")] == 13.0      # no 1000x step
    assert not any(c == "CHF" and d.startswith("1999-10") and v < 50 for (c, d), v in m.items())   # 1999-10-19 dropped
    assert ("USD", "2010-01-01") not in m                     # a first load rebuilds every month from the sources
    assert manifest["history_source_url"] == nbk.OFFICIAL_RATES_ARCHIVE_URL


def test_later_runs_read_the_last_two_months_only(monkeypatch, tmp_path):
    calls = []
    stored = [{"date": "1993-11-01", "region": "national", "item_code": "USD", "item_name": "x", "value": "4.689"},
              {"date": "2000-01-01", "region": "national", "item_code": "USD", "item_name": "x", "value": "138.5"}]
    windows = _offline(monkeypatch, tmp_path, stored=stored, archive_calls=calls)
    records, _ = nbk_fx.fetch({"id": "EXCHANGE_RATES_OFFICIAL_MONTHLY"})
    begin = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    assert not calls and {b for _, b in windows} == {begin}
    m = {(r["item_code"], r["date"]): r["value"] for r in records}
    assert m[("USD", "1993-11-01")] == 4.689 and m[("USD", "2000-01-01")] == 138.5


# ---------------------------------------------------------------- NEER weights before 2010

def test_incomplete_consumer_year_is_skipped_and_the_last_structure_carried():
    imports = {("TOTAL", 0, 2000): 100.0, ("TOTAL", 643, 2000): 60.0, ("TOTAL", 840, 2000): 40.0,
               ("CONSUMER", 0, 2000): 1.0, ("CONSUMER", 643, 2000): 1.0,
               ("CONSUMER", 0, 1999): 18.0, ("CONSUMER", 643, 1999): 9.0, ("CONSUMER", 840, 1999): 9.0}
    shares, coverage = neer_import.weights(imports)
    assert ("CONSUMER", 2000) not in shares and shares[("TOTAL", 2000)] == {"RUB": 0.6, "USD": 0.4}
    assert shares[("CONSUMER", 1999)] == {"RUB": 0.5, "USD": 0.5}                 # 840 = the US in the 1990s
    carried = neer_import.carry_forward({1999: {"RUB": 1.0}, 2001: {"USD": 1.0}})
    assert carried == {1999: (1999, {"RUB": 1.0}), 2000: (1999, {"RUB": 1.0}), 2001: (2001, {"USD": 1.0})}


# ---------------------------------------------------------------- the processed files (after a load)

def _processed(name):
    path = REPO_ROOT / "data" / "processed" / "dims" / f"{name}.csv"
    with path.open(encoding="utf-8") as f:
        return {(r["item_code"], r["date"]): float(r["value"]) for r in csv.DictReader(f)}


def test_processed_monthly_history_holds_known_points():
    fx = _processed("exchange_rates_official_monthly")
    if ("USD", "1993-11-01") not in fx:
        pytest.skip("EXCHANGE_RATES_OFFICIAL_MONTHLY history before 2010 not loaded yet")
    assert fx[("USD", "1999-12-01")] == pytest.approx(138.222727) and fx[("USD", "1997-12-01")] == 75.55
    assert fx[("RUB", "1997-12-01")] == 13.0 and fx[("RUB", "1998-01-01")] == pytest.approx(13.047727)   # no 1000x step
    assert fx[("EUR", "1999-01-01")] > 90 and ("EUR", "1998-12-01") not in fx
    assert fx[("TRY", "2005-01-01")] == pytest.approx(96.066667) and 1000 < fx[("TRY", "1995-06-01")] < 2000
    assert fx[("BYN", "2016-07-01")] == pytest.approx(171.001905)             # Fri 1 July 2016 restated (was 163.00)
    assert 100000 < fx[("BYN", "1994-01-01")] < 150000
    for code in ("USD", "RUB", "GBP", "CHF"):
        assert min(d for c, d in fx if c == code) == "1993-11-01"


def test_monthly_items_equal_the_scalar_daily_series():
    fx = _processed("exchange_rates_official_monthly")
    if ("USD", "1993-11-01") not in fx:
        pytest.skip("EXCHANGE_RATES_OFFICIAL_MONTHLY history before 2010 not loaded yet")
    last = max(d for _, d in fx)
    for code, name in (("USD", "exchange_rate"), ("EUR", "exchange_rate_eur"), ("CNY", "exchange_rate_cny"),
                       ("RUB", "exchange_rate_rub")):
        days: dict[str, list[float]] = {}
        with (REPO_ROOT / "data" / "processed" / "nbk" / f"{name}.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                # weekdays: EXCHANGE_RATE carries four weekend rows of 2026-08 from before the report
                if r["value"] and date.fromisoformat(r["date"]).weekday() < 5:
                    days.setdefault(r["date"][:7] + "-01", []).append(float(r["value"]))
        months = [m for m in days if m < last and (code, m) in fx]
        assert len(months) > 150
        assert all(abs(sum(days[m]) / len(days[m]) - fx[(code, m)]) < 1e-5 for m in months), code


def test_neer_history_starts_1995_12():
    neer = _processed("neer_import_weighted")
    if ("NEER_TOTAL", "1995-12-01") not in neer:
        pytest.skip("NEER history before 2010 not loaded yet")
    assert min(d for c, d in neer if c == "NEER_TOTAL") == "1995-12-01"
    # the rouble crash of August 1998: the tenge gains ~50% against the import basket in a month
    assert neer[("NEER_TOTAL", "1998-09-01")] / neer[("NEER_TOTAL", "1998-08-01")] > 1.4
    # the float of April 1999 reverses it
    assert neer[("NEER_TOTAL", "1999-06-01")] < neer[("NEER_TOTAL", "1999-03-01")] * 0.75
