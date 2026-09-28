"""X-13ARIMA-SEATS driver (scripts/lib/x13.py): the Kazakhstan holiday calendar, the regressor
file, the hand-written spec and the output parsers without the program; synthetic series
adjusted by the real binary when one is found (vendored tools/x13as/x13as_ascii, the cache,
$X13PATH or PATH) -- skipped otherwise. No network."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib import x13  # noqa: E402

needs_x13 = pytest.mark.skipif(not x13.available(), reason="no X-13ARIMA-SEATS binary (git lfs pull tools/x13as?)")


# ---------------------------------------------------------------- calendar
def test_kurban_ait_table_covers_1990_2035_and_kazakhstan_dates():
    assert set(x13.KURBAN_AIT) == set(range(1990, 2036))
    assert x13.KURBAN_AIT[2006] == (date(2006, 1, 10), date(2006, 12, 31))       # two in one year
    assert x13.KURBAN_AIT[2015] == (date(2015, 9, 24),)                           # Kazakhstan, not Umm al-Qura 09-23
    assert x13.KURBAN_AIT[2016] == (date(2016, 9, 12),)
    assert x13.KURBAN_AIT[2024] == (date(2024, 6, 16),)
    assert x13.KURBAN_AIT[2026] == (date(2026, 5, 27),)
    # Eid al-Adha moves 10-12 days earlier each Gregorian year.
    firsts = [x13.KURBAN_AIT[y][-1] for y in range(2007, 2036)]
    gaps = [(b - date(b.year - 1, b.month, b.day)).days - (b - a).days for a, b in zip(firsts, firsts[1:])]
    assert all(9 <= g <= 13 for g in gaps), gaps


def test_holiday_list_follows_the_law_by_year():
    names = lambda y: [(h.day, h.name) for h in x13.kz_holidays(y)]  # noqa: E731
    h2024 = {d for d, _ in names(2024)}
    for d in (date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 7), date(2024, 3, 8), date(2024, 3, 21),
              date(2024, 3, 22), date(2024, 3, 23), date(2024, 5, 1), date(2024, 5, 7), date(2024, 5, 9),
              date(2024, 7, 6), date(2024, 8, 30), date(2024, 10, 25), date(2024, 12, 16), date(2024, 6, 16)):
        assert d in h2024, d
    assert date(2024, 12, 1) not in h2024 and date(2024, 12, 17) not in h2024      # abolished in 2022
    h2015 = {d for d, _ in names(2015)}
    assert date(2015, 12, 1) in h2015 and date(2015, 12, 17) in h2015 and date(2015, 10, 25) not in h2015
    h2005 = {d for d, _ in names(2005)}
    assert date(2005, 1, 7) not in h2005 and date(2005, 1, 21) not in h2005       # religious days off from 2006
    assert date(2005, 3, 22) in h2005 and date(2005, 3, 21) not in h2005          # Nauryz 3 days from 2010


def test_weekend_holidays_move_to_the_next_working_day_religious_ones_do_not():
    off = x13.kz_days_off(2020)
    # Nauryz 2020: Sat 21, Sun 22, Mon 23 -> 23 off, 24 and 25 transferred; 8 March (Sun) -> 9 March.
    assert {date(2020, 3, 9), date(2020, 3, 23), date(2020, 3, 24), date(2020, 3, 25)} <= off
    assert date(2020, 3, 26) not in off
    # Orthodox Christmas on Sunday 2018-01-07: no transfer; New Year Mon-Tue 1-2 Jan.
    off18 = x13.kz_days_off(2018)
    assert date(2018, 1, 8) not in off18 and date(2018, 1, 1) in off18 and date(2018, 1, 2) in off18
    # Kurban Ait on Saturday 2014-10-04: no transfer.
    assert date(2014, 10, 6) not in x13.kz_days_off(2014)


def test_working_days_in_known_months():
    assert x13.working_days(2020, 3) == 18        # 22 weekdays - 9, 23, 24, 25 March
    assert x13.working_days(2024, 5) == 20        # 23 weekdays - 1, 7, 9 May (bridge day 8 May not modelled)
    assert x13.working_days(2023, 1) == 20        # 22 weekdays - 2, 3 Jan (1 Jan on Sunday moved to 3 Jan)
    assert x13.working_days(2021, 2) == 20


def test_calendar_regressors_are_centred_by_calendar_month():
    m = x13.calendar_regressors(12)
    assert m.index[0] == pd.Timestamp("1990-01-01") and m.index[-1] == pd.Timestamp("2035-12-01")
    assert list(m.columns) == ["kzwd", "kurban"]
    assert m.groupby(m.index.month).mean().abs().max().max() < 1e-12
    # Kurban Ait fell in June 2024: above its June mean; not in July 2024: below.
    assert m.loc["2024-06-01", "kurban"] > 0 > m.loc["2024-07-01", "kurban"]
    q = x13.calendar_regressors(4)
    assert len(q) == 46 * 4 and q.groupby(q.index.quarter).mean().abs().max().max() < 1e-12
    raw_q1 = sum(x13.working_days(2020, mm) for mm in (1, 2, 3))
    raw_mean = np.mean([sum(x13.working_days(y, mm) for mm in (1, 2, 3)) for y in range(1990, 2036)])
    assert q.loc["2020-01-01", "kzwd"] == pytest.approx(raw_q1 - raw_mean)


def test_regressor_file_is_datevalue():
    lines = x13.regressor_file_text(12).splitlines()
    assert len(lines) == 46 * 12
    y, m, a, b = lines[0].split()
    assert (y, m) == ("1990", "1") and float(a) == pytest.approx(x13.calendar_regressors(12).iloc[0, 0], abs=1e-6)
    assert x13.regressor_file_text(4).splitlines()[5].split()[:2] == ["1991", "2"]


# ---------------------------------------------------------------- series helpers and spec
def _m(values, start="2015-01-01", freq="MS"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), dtype=float)


def test_longest_run_keeps_the_longest_gap_free_stretch():
    s = _m(range(1, 61))
    s.iloc[10] = np.nan
    s = s.drop(s.index[20])                       # a missing month, not just a NaN
    run = x13.longest_run(s, 12)
    assert run.index[0] == pd.Timestamp("2016-10-01") and len(run) == 39
    q = _m(range(8), start="2020-01-01", freq="QS")
    assert len(x13.longest_run(q, 4)) == 8


def test_build_spec_x11_kz_calendar():
    s = _m(np.arange(1, 49), start="2019-03-01")
    spec = x13.build_spec(s, 12, title="cpi/test", transform="auto")
    assert "start = 2019.3" in spec and "period = 12" in spec
    assert "transform { function = auto }" in spec
    assert "user = (kzwd kurban)" in spec and "usertype = (td holiday)" in spec
    assert 'format = "datevalue"' in spec and "start = 1990.1" in spec and "aictest = (td user)" in spec
    assert "outlier { types = (ao ls tc) }" in spec and "automdl { }" in spec
    assert "save = (d10 d11 d12 d13 d16)" in spec and "mode =" not in spec
    assert 'title = "cpi_test"' in spec
    assert spec.count("\n1.0\n") == 1 and "\n48.0\n" in spec


def test_build_spec_variants():
    q = _m(np.arange(1, 17), start="2020-04-01", freq="QS")
    spec = x13.build_spec(q, 4, transform="none", calendar="none", outliers=())
    assert "start = 2020.2" in spec and "period = 4" in spec and "regression" not in spec
    assert "outlier" not in spec and "mode = add" in spec
    spec = x13.build_spec(q, 4, transform="log", method="seats", calendar="builtin")
    assert "seats { save = (s10 s11 s12 s13 s16) }" in spec and "variables = (td)" in spec and "x11" not in spec
    with pytest.raises(x13.X13Error):
        x13.build_spec(q, 4, transform="sqrt")
    with pytest.raises(x13.X13Error):
        x13.build_spec(q, 4, calendar="ru")


def test_parsers(tmp_path):
    p = tmp_path / "s.d10"
    p.write_text("date\ts.d10\n------\t-----------------------\n201401\t+0.904421309545643E+00\n"
                 "201402\t+0.916867626233935E+00\n")
    s = x13._read_table(p, 12)
    assert list(s.index) == [pd.Timestamp("2014-01-01"), pd.Timestamp("2014-02-01")]
    assert s.iloc[0] == pytest.approx(0.904421309545643)
    p.write_text("date\ts.d10\n------\t---\n201003\t+0.1E+01\n")
    assert x13._read_table(p, 4).index[0] == pd.Timestamp("2010-07-01")
    udg = x13.parse_udg("arimamdl: (0 1 1)(0 1 1)\nf3.m07:  0.371\nf3.q:  0.41\n"
                        "AutoOutlier$LS2026.Jan: +0.48 +0.06 +7.35\n"
                        "User-defined Trading Day$kzwd: +0.03 +0.004 +7.3\nUser-defined Holiday$kurban: -0.01 0.01 -0.5\n"
                        "chi$All User-defined Regressors: 2 59.6 0.1\n")
    assert x13._num(udg, "f3.m07") == pytest.approx(0.371) and x13._num(udg, "missing") is None
    assert x13._outliers(udg) == ["LS2026.Jan"]
    assert x13._kept_calendar(udg, "kz") == ["kzwd(t=7.3)", "kurban(t=-0.5)"]


def test_short_series_and_bad_inputs_are_refused_before_running():
    with pytest.raises(x13.X13Error, match="3 years"):
        x13.adjust(_m(np.arange(1, 36)), 12, binary=Path("/nonexistent"))
    gappy = _m(np.arange(1, 61))
    gappy.iloc[30] = np.nan                        # runs of 30 and 29 months
    with pytest.raises(x13.X13Error, match="gap-free run is 30"):
        x13.adjust(gappy, 12, binary=Path("/nonexistent"))
    with pytest.raises(x13.X13Error, match="non-positive"):
        x13.adjust(_m(np.arange(-5, 55)), 12, transform="log", binary=Path("/nonexistent"))
    with pytest.raises(x13.X13Error, match="period"):
        x13.adjust(_m(np.arange(1, 60)), 6)
    with pytest.raises(x13.X13Error, match="calendar covers"):
        x13.adjust(_m(np.arange(1, 61), start="1985-01-01"), 12, binary=Path("/nonexistent"))


def test_x13path_must_point_to_a_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("X13PATH", str(tmp_path))
    with pytest.raises(x13.X13Unavailable, match="X13PATH"):
        x13.find_binary()
    assert x13.available() is False
    pointer = tmp_path / "x13as_ascii"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:72e4\nsize 4812584\n")
    assert x13._runnable(pointer) is None          # an LFS pointer is not a program


def test_vendored_binary_matches_the_pinned_checksum():
    import hashlib
    if not x13._is_elf(x13.VENDORED):
        pytest.skip("tools/x13as/x13as_ascii is not checked out (git lfs pull)")
    assert hashlib.sha256(x13.VENDORED.read_bytes()).hexdigest() == x13.X13_BINARY_SHA256


# ---------------------------------------------------------------- with the program
@needs_x13
def test_multiplicative_series_is_adjusted():
    rng = np.random.default_rng(1)
    n = 120
    trend = 100 * np.exp(0.01 * np.arange(n))
    factor = 1 + 0.05 * np.cos(2 * np.pi * np.arange(n) / 12)
    s = _m(trend * factor * np.exp(rng.normal(0, 0.004, n)), start="2010-01-01")
    r = x13.adjust(s, 12, calendar="none")
    assert r.transform == "log" and r.mode == "multiplicative" and r.method == "x11"
    assert (r.sa / trend - 1).abs().max() < 0.02
    assert np.abs(r.seasonal.to_numpy() - factor).max() < 0.01
    assert r.m7 is not None and r.m7 < 1 and r.q < 1 and r.model.startswith("(")
    assert r.span == ("2010-01", "2019-12") and r.n == n


@needs_x13
def test_additive_series_and_seats():
    rng = np.random.default_rng(42)
    true = np.array([4, 2, -1, -3, -4, -2, 0, 1, 3, 2, -1, -1], float)
    s = _m(100 + 0.8 * np.arange(96) + np.tile(true, 8) + rng.normal(0, 0.3, 96))
    r = x13.adjust(s, 12, transform="none", calendar="none")
    assert r.mode == "additive"
    eff = r.seasonal.groupby(r.seasonal.index.month).mean().to_numpy()
    assert np.abs(eff - true).max() < 0.3
    seats = x13.adjust(s, 12, transform="none", calendar="none", method="seats")
    assert seats.method == "seats" and (seats.sa - r.sa).abs().max() < 1.5


@needs_x13
def test_kazakhstan_working_day_effect_is_found():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2012-01-01", periods=144, freq="MS")
    cal = x13.calendar_regressors(12).loc[idx]
    f = np.tile([0.9, 0.92, 1.0, 1.02, 1.03, 1.04, 1.02, 1.01, 1.0, 1.02, 1.01, 1.03], 12)
    s = pd.Series(100 * np.exp(0.005 * np.arange(144)) * f * np.exp(0.02 * cal.kzwd.to_numpy()
                                                                     + rng.normal(0, 0.004, 144)), index=idx)
    r = x13.adjust(s, 12)
    assert any(c.startswith("kzwd") for c in r.calendar)
    coef = float(r.udg["User-defined Trading Day$kzwd"].split()[0])
    assert coef == pytest.approx(0.02, abs=0.003)
    none = x13.adjust(s, 12, calendar="none")
    assert r.aicc < none.aicc


@needs_x13
def test_quarterly_with_a_gap_uses_the_longest_run():
    rng = np.random.default_rng(3)
    pattern = np.tile([0.9, 1.0, 1.05, 1.05], 14)
    q = _m(100 * np.exp(0.01 * np.arange(56)) * pattern * np.exp(rng.normal(0, 0.004, 56)),
           start="2010-01-01", freq="QS")
    q.iloc[3] = np.nan
    r = x13.adjust(q, 4, calendar="none")
    assert r.span == ("2011-01", "2023-10") and r.n == 52 and r.dropped == 3
    assert np.abs(r.seasonal.to_numpy() - pattern[4:]).max() < 0.01


@needs_x13
def test_x13_errors_carry_the_program_message():
    s = _m(np.linspace(100, 200, 96) * (1 + 0.1 * np.sin(np.arange(96))))   # no noise at all
    with pytest.raises(x13.X13Error, match="ERROR"):
        x13.adjust(s, 12, calendar="none")
