"""X-13ARIMA-SEATS seasonal adjustment (US Census Bureau) with a Kazakhstan calendar.

    from lib import x13
    res = x13.adjust(series, period=12)               # X-11 with regARIMA pre-adjustment
    res.sa, res.seasonal, res.model, res.outliers, res.m7, res.q

THE PROGRAM. The official Census Bureau build, X-13ARIMA-SEATS Version 1.1 Build 62, ASCII
output (the build statsmodels also drives), from
https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/program-archives/
x13as_ascii-v1-1-b62.tar.gz (listing dated 2025-07-10; the newest Linux build on
2026-09-27; b61 of 2024-07-09 is the one before). The tarball holds x13as/x13as_ascii, a
statically linked x86-64 ELF of 4 812 584 bytes that runs on any Linux without libraries.
US-government work, public domain. It is vendored at tools/x13as/x13as_ascii (see
tools/x13as/README.md) so a fresh clone and the tests work offline; `find_binary` looks, in
order, at $X13PATH (the binary itself or its directory; an explicit setting that does not
point to a working program is an error, never silently skipped), the vendored copy, the
download cache ($X13_CACHE or ~/.cache/kazakhstan-economic-data/x13as) and x13as_ascii /
x13as on $PATH. `ensure_binary(download=True)` downloads the pinned tarball into the cache
when none is found and checks both sha256 sums below. A vendored copy that is still a git-LFS
pointer (a clone without `git lfs pull`, e.g. actions/checkout without lfs: true) is not an
ELF file and is skipped.

THE SPEC. Written by hand (statsmodels.tsa.x13 only writes a subset: no user regressors, no
outlier types, no SEATS), one spec per run in a temporary directory:

    series      the data, start, period; the longest gap-free run of the input
    transform   function = auto (log vs none by AICC) unless the caller forces log / none
    regression  calendar: Kazakhstan working days (usertype td) and Kurban Ait (usertype
                holiday), both kept only if AICC prefers them (aictest = (td user));
                calendar="builtin" uses X-13's own td instead, "none" drops calendar effects
    automdl     automatic ARIMA order selection (TRAMO-style, maxorder (2 1))
    outlier     automatic AO / LS / TC detection, default critical value for the length
    x11         (default) or seats: the decomposition; mode follows the transform

and the saved tables d10/d11/d12/d13/d16 (X-11) or s10/s11/s12/s13/s16 (SEATS) plus the
diagnostics summary (.udg: chosen transform, ARIMA model, outliers, AICC, M1-M11, Q, Q2).

THE KAZAKHSTAN CALENDAR. Law of 13.12.2001 No. 267-II «О праздниках в Республике Казахстан»
and Labour Code art. 84-85: holidays are non-working days; when a holiday falls on a Saturday
or Sunday the next working day is off; the first day of Kurban Ait and Orthodox Christmas
(7 January) are days off WITHOUT that transfer. Holidays modelled, with the years they are
non-working days here:
    New Year 1-2 Jan (all years); Orthodox Christmas 7 Jan (2006-); 8 March (all);
    Nauryz 22 March (1991-2009), 21-23 March (2010-); Unity Day 1 May (all);
    Defender of the Fatherland 7 May (2013-); Victory Day 9 May (all);
    Capital Day 6 July (2009-); Constitution Day 30 Aug (1996-);
    Republic Day 25 Oct (1995-2008 and 2022-); First President Day 1 Dec (2012-2021);
    Independence Day 16 Dec (all), 17 Dec (1996-2021); Kurban Ait, first day (2006-).
The introduction years before 2002 are the least certain; everything this repository
adjusts starts in 1994 or later and the X-11 seasonal filters absorb a fixed-date holiday
anyway -- what the regressor adds is the weekday on which it falls and the transfer. The
government's one-off bridge-day decrees (a Saturday worked to lengthen a holiday) are NOT
modelled: they are announced year by year and have no rule.

Kurban Ait (Eid al-Adha, 10 Dhu al-Hijjah) moves about 11 days earlier every year, so it is
the one holiday that changes calendar month. KURBAN_AIT holds its first day 1990-2035 from
the Umm al-Qura calendar (computed with the hijridate package), with the Kazakhstan
observance where it differed: 2015-09-24 (Umm al-Qura 09-23) and 2016-09-12 (09-11), both
checked against the Muftiate / egov announcements of those years. 2006 has two (10 Jan and
31 Dec).

Regressors, one row per month (or quarter) 1990-2035, file format "datevalue":
    kzwd    working days (Mon-Fri minus holidays and transferred days off) minus the mean
            for that calendar month over 1990-2035: a deviation, zero on average by month,
            so it moves only the level of an adjusted series' calendar component
    kurban  1 if the first day of Kurban Ait falls in the period, minus its 1990-2035
            calendar-month mean: the feast itself (livestock and food purchases), on top of
            the day off already in kzwd
Verified: 2020-03 had 17 working days (Nauryz 21-23 on Sat-Mon, 24-25 transferred off) and
2024-05 had 20 (1, 7, 9 May on Wed/Tue/Thu); tests/test_x13.py.

PITFALLS. X-13 needs at least three complete years (X13Error below that) and at most 780
observations; missing values inside the span are not allowed, so `adjust` works on the
longest gap-free run (as build_model_data always did) and reports what it dropped. A log
transform needs positive data (a forced log on a non-positive series is an X13Error;
auto picks none). Multiplicative seasonal factors are saved as ratios (d10 ~ 1.0), additive
ones in the series' units. X-13 writes warnings to the .err file even on success; they are
returned in `warnings`, and a line with ERROR fails the run.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED = REPO_ROOT / "tools" / "x13as" / "x13as_ascii"
X13_VERSION = "1.1 build 62"
X13_URL = ("https://www2.census.gov/software/x-13arima-seats/x13as/unix-linux/program-archives/"
           "x13as_ascii-v1-1-b62.tar.gz")
X13_TARBALL_SHA256 = "a91d37bb2fef46237e1eadd7d9b4f1c00a422d58f6b286c9bfe485289e8ac6f5"
X13_BINARY_SHA256 = "72e4735dd8d96974fbfe2d80d38a83ee1cca5c8b6fa3dfd9a89aa952a1cb4a15"
X13_MEMBER = "x13as/x13as_ascii"
MIN_YEARS = 3
MAX_OBS = 780
CAL_START, CAL_END = 1990, 2035


class X13Error(Exception):
    """X-13 refused the series or failed: the message carries X-13's own error text."""


class X13Unavailable(X13Error):
    """No working X-13 binary (and, for ensure_binary, none could be downloaded)."""


# ---------------------------------------------------------------- the binary
def _cache_dir() -> Path:
    env = os.environ.get("X13_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "kazakhstan-economic-data" / "x13as"


def _is_elf(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def _runnable(p: Path) -> Path | None:
    """p if it is an ELF binary we can execute (setting the x bit if we own the file)."""
    if not p.is_file() or not _is_elf(p):
        return None
    if not os.access(p, os.X_OK):
        try:
            p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            return None
    return p


def find_binary() -> Path | None:
    """The X-13 program to run, or None. $X13PATH wins and must be valid."""
    env = os.environ.get("X13PATH")
    if env:
        p = Path(env)
        cands = [p] if p.is_file() else [p / "x13as_ascii", p / "x13as"]
        for c in cands:
            if _runnable(c):
                return c
        raise X13Unavailable(f"X13PATH={env!r} does not point to an X-13 binary (tried {', '.join(map(str, cands))}).")
    for c in (VENDORED, _cache_dir() / "x13as_ascii"):
        if _runnable(c):
            return c
    for name in ("x13as_ascii", "x13as"):
        w = shutil.which(name)
        if w and _runnable(Path(w)):
            return Path(w)
    return None


def ensure_binary(download: bool = True, timeout: int = 120) -> Path:
    """find_binary(), else download the pinned tarball into the cache (sha256-checked)."""
    found = find_binary()
    if found:
        return found
    if not download:
        raise X13Unavailable("No X-13ARIMA-SEATS binary: not vendored (git lfs pull?), not cached, not on PATH.")
    import requests  # only needed here

    try:
        r = requests.get(X13_URL, timeout=timeout)
        r.raise_for_status()
    except Exception as e:  # network down, proxy, 404
        raise X13Unavailable(f"Could not download {X13_URL}: {e}") from e
    blob = r.content
    got = hashlib.sha256(blob).hexdigest()
    if got != X13_TARBALL_SHA256:
        raise X13Unavailable(f"{X13_URL}: sha256 {got}, expected {X13_TARBALL_SHA256} -- the archive changed; "
                             "verify the new build and update X13_URL / the sums in scripts/lib/x13.py.")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
        member = tf.extractfile(X13_MEMBER)
        if member is None:
            raise X13Unavailable(f"{X13_URL}: no {X13_MEMBER} inside")
        exe = member.read()
    if hashlib.sha256(exe).hexdigest() != X13_BINARY_SHA256:
        raise X13Unavailable(f"{X13_MEMBER}: sha256 mismatch against X13_BINARY_SHA256")
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "x13as_ascii.part"
    tmp.write_bytes(exe)
    tmp.chmod(0o755)
    tmp.replace(d / "x13as_ascii")
    return d / "x13as_ascii"


def available() -> bool:
    try:
        return find_binary() is not None
    except X13Unavailable:
        return False


# ---------------------------------------------------------------- Kazakhstan calendar
# First day of Kurban Ait. Umm al-Qura (hijridate 2.6.0) 10 Dhu al-Hijjah, except 2015 and
# 2016 (Kazakhstan observed a day later). 2006 has two.
KURBAN_AIT: dict[int, tuple[date, ...]] = {y: tuple(date.fromisoformat(s) for s in v) for y, v in {
    1990: ["1990-07-02"], 1991: ["1991-06-22"], 1992: ["1992-06-11"], 1993: ["1993-05-31"],
    1994: ["1994-05-20"], 1995: ["1995-05-09"], 1996: ["1996-04-27"], 1997: ["1997-04-17"],
    1998: ["1998-04-07"], 1999: ["1999-03-27"], 2000: ["2000-03-16"], 2001: ["2001-03-05"],
    2002: ["2002-02-22"], 2003: ["2003-02-11"], 2004: ["2004-02-01"], 2005: ["2005-01-21"],
    2006: ["2006-01-10", "2006-12-31"], 2007: ["2007-12-20"], 2008: ["2008-12-08"],
    2009: ["2009-11-27"], 2010: ["2010-11-16"], 2011: ["2011-11-06"], 2012: ["2012-10-26"],
    2013: ["2013-10-15"], 2014: ["2014-10-04"], 2015: ["2015-09-24"], 2016: ["2016-09-12"],
    2017: ["2017-09-01"], 2018: ["2018-08-21"], 2019: ["2019-08-11"], 2020: ["2020-07-31"],
    2021: ["2021-07-20"], 2022: ["2022-07-09"], 2023: ["2023-06-28"], 2024: ["2024-06-16"],
    2025: ["2025-06-06"], 2026: ["2026-05-27"], 2027: ["2027-05-16"], 2028: ["2028-05-05"],
    2029: ["2029-04-24"], 2030: ["2030-04-13"], 2031: ["2031-04-02"], 2032: ["2032-03-22"],
    2033: ["2033-03-11"], 2034: ["2034-03-01"], 2035: ["2035-02-18"],
}.items()}

# (month, day, name, first year, last year, transferred when on a weekend)
FIXED_HOLIDAYS: list[tuple[int, int, str, int, int, bool]] = [
    (1, 1, "New Year", 1990, 9999, True),
    (1, 2, "New Year", 1990, 9999, True),
    (1, 7, "Orthodox Christmas", 2006, 9999, False),
    (3, 8, "International Women's Day", 1990, 9999, True),
    (3, 21, "Nauryz", 2010, 9999, True),
    (3, 22, "Nauryz", 1991, 9999, True),
    (3, 23, "Nauryz", 2010, 9999, True),
    (5, 1, "Unity Day", 1990, 9999, True),
    (5, 7, "Defender of the Fatherland Day", 2013, 9999, True),
    (5, 9, "Victory Day", 1990, 9999, True),
    (7, 6, "Capital Day", 2009, 9999, True),
    (8, 30, "Constitution Day", 1996, 9999, True),
    (10, 25, "Republic Day", 1995, 2008, True),
    (10, 25, "Republic Day", 2022, 9999, True),
    (12, 1, "First President Day", 2012, 2021, True),
    (12, 16, "Independence Day", 1990, 9999, True),
    (12, 17, "Independence Day", 1996, 2021, True),
]
KURBAN_DAY_OFF_FROM = 2006


@dataclass(frozen=True)
class Holiday:
    day: date
    name: str
    transferred: bool          # moved to the next working day when it falls on a weekend


def kz_holidays(year: int) -> list[Holiday]:
    """Official non-working holidays of `year` (before any weekend transfer)."""
    out = [Holiday(date(year, m, d), n, t) for m, d, n, y0, y1, t in FIXED_HOLIDAYS if y0 <= year <= y1]
    if year >= KURBAN_DAY_OFF_FROM:
        out += [Holiday(d, "Kurban Ait", False) for d in KURBAN_AIT.get(year, ())]
    return sorted(out, key=lambda h: h.day)


@lru_cache(maxsize=None)
def kz_days_off(year: int) -> frozenset[date]:
    """Weekday holidays plus the working days a weekend holiday moves to (Labour Code rule).
    Weekends themselves are not listed. A transfer from late December can land in January
    of the next year; it is counted in the year it lands in."""
    offs: set[date] = set()
    for y in (year - 1, year):
        hols = kz_holidays(y)
        hol_days = {h.day for h in hols}
        taken = set(hol_days)
        for h in hols:
            if h.transferred and h.day.weekday() >= 5:
                d = h.day + timedelta(days=1)
                while d.weekday() >= 5 or d in taken:
                    d += timedelta(days=1)
                taken.add(d)
                offs.add(d)
        offs |= {d for d in hol_days if d.weekday() < 5}
    return frozenset(d for d in offs if d.year == year)


def working_days(year: int, month: int) -> int:
    first = date(year, month, 1)
    n = (date(year + month // 12, month % 12 + 1, 1) - first).days
    off = kz_days_off(year)
    return sum(1 for i in range(n) if (d := first + timedelta(days=i)).weekday() < 5 and d not in off)


@lru_cache(maxsize=4)
def calendar_regressors(period: int) -> pd.DataFrame:
    """kzwd and kurban for every month (period=12) or quarter (period=4) of 1990-2035,
    each centred on its own calendar-month (quarter) mean. Index: first day of the period."""
    months = pd.date_range(f"{CAL_START}-01-01", f"{CAL_END}-12-01", freq="MS")
    wd = pd.Series([working_days(d.year, d.month) for d in months], index=months, dtype=float)
    kur = pd.Series(0.0, index=months)
    for days in KURBAN_AIT.values():
        for d in days:
            kur[pd.Timestamp(d.year, d.month, 1)] += 1.0
    df = pd.DataFrame({"kzwd": wd, "kurban": kur})
    if period == 4:
        df = df.groupby(df.index.to_period("Q")).sum()
        df.index = df.index.to_timestamp()
    elif period != 12:
        raise X13Error(f"period={period}: only monthly (12) and quarterly (4) series")
    pos = df.index.month if period == 12 else df.index.quarter
    return df - df.groupby(pos).transform("mean")


# ---------------------------------------------------------------- series helpers
def longest_run(s: pd.Series, period: int) -> pd.Series:
    """The longest stretch without a missing period (the latest one on a tie)."""
    s = s.dropna().sort_index()
    if s.empty:
        return s
    step = 12 // period
    full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq=f"{step}MS"))
    ok = full.notna().to_numpy()
    best, cur_start, best_len = (0, 0), None, 0
    for i, v in enumerate(ok):
        if v and cur_start is None:
            cur_start = i
        if cur_start is not None and (not v or i == len(ok) - 1):
            end = i + 1 if v else i
            if end - cur_start >= best_len:
                best, best_len = (cur_start, end), end - cur_start
            cur_start = None
    return full.iloc[best[0]:best[1]].astype(float)


def _date_code(ts: pd.Timestamp, period: int) -> str:
    return f"{ts.year}.{ts.month if period == 12 else (ts.month - 1) // 3 + 1}"


def _fmt(v: float) -> str:
    return repr(float(v))


# ---------------------------------------------------------------- spec
TABLES = {"x11": ("d10", "d11", "d12", "d13", "d16"), "seats": ("s10", "s11", "s12", "s13", "s16")}


def build_spec(s: pd.Series, period: int, *, title: str = "series", transform: str = "auto",
               method: str = "x11", calendar: str = "kz", outliers: tuple[str, ...] = ("ao", "ls", "tc"),
               regressor_file: str = "kzcal.dat") -> str:
    """The .spc text for a gap-free series `s` (DatetimeIndex at period starts)."""
    if transform not in ("auto", "log", "none"):
        raise X13Error(f"transform={transform!r}: auto | log | none")
    if method not in TABLES:
        raise X13Error(f"method={method!r}: x11 | seats")
    if calendar not in ("kz", "builtin", "none"):
        raise X13Error(f"calendar={calendar!r}: kz | builtin | none")
    title = re.sub(r"[^A-Za-z0-9 _.,()-]", "_", title)[:70]
    data = "\n".join(_fmt(v) for v in s.values)
    lines = [
        "series {",
        f'  title = "{title}"',
        f"  start = {_date_code(s.index[0], period)}",
        f"  period = {period}",
        "  data = (",
        data,
        "  )",
        "}",
        f"transform {{ function = {transform} }}",
    ]
    reg: list[str] = []
    if calendar == "kz":
        reg = ["  user = (kzwd kurban)", "  usertype = (td holiday)", f"  start = {CAL_START}.1",
               f'  file = "{regressor_file}"', '  format = "datevalue"', "  aictest = (td user)"]
    elif calendar == "builtin":
        reg = ["  variables = (td)", "  aictest = (td)"]
    if reg:
        lines += ["regression {", *reg, "  save = (td hol)", "}"]
    lines += ["automdl { }"]
    if outliers:
        lines += [f"outlier {{ types = ({' '.join(outliers)}) }}"]
    else:
        lines += ["estimate { }"]
    save = " ".join(TABLES[method])
    if method == "x11":
        mode = {"log": "  mode = mult", "none": "  mode = add"}.get(transform)
        lines += ["x11 {", *([mode] if mode else []), f"  save = ({save})", "}"]
    else:
        lines += [f"seats {{ save = ({save}) }}"]
    return "\n".join(lines) + "\n"


def regressor_file_text(period: int) -> str:
    df = calendar_regressors(period)
    pos = df.index.month if period == 12 else df.index.quarter
    return "\n".join(f"{d.year} {p} {r.kzwd:.6f} {r.kurban:.6f}"
                     for (d, r), p in zip(df.iterrows(), pos)) + "\n"


# ---------------------------------------------------------------- run + parse
@dataclass
class X13Result:
    sa: pd.Series
    seasonal: pd.Series             # d10 / s10: ratio (multiplicative) or units (additive)
    trend: pd.Series
    irregular: pd.Series
    adjustment: pd.Series           # d16 / s16: combined seasonal + calendar factor
    mode: str                       # "multiplicative" | "additive"
    transform: str                  # "log" | "none"
    model: str                      # "(0 1 1)(0 1 1)"
    method: str                     # "x11" | "seats"
    calendar: list[str] = field(default_factory=list)     # calendar regressors kept by AICC
    calendar_option: str = "kz"                           # what was offered: kz | builtin | none
    outliers: list[str] = field(default_factory=list)     # "LS2026.Jan", ...
    aicc: float | None = None
    m7: float | None = None
    q: float | None = None
    q2: float | None = None
    span: tuple[str, str] = ("", "")
    n: int = 0
    dropped: int = 0                # observations outside the longest gap-free run
    warnings: list[str] = field(default_factory=list)
    udg: dict = field(default_factory=dict)

    def summary(self, include_method: bool = True) -> str:
        """One line for a variable card: X-13 X-11; log; (0 1 1)(0 1 1); calendar: ...; M7; Q."""
        bits = [f"X-13 {self.method.upper().replace('X11', 'X-11')}"] if include_method else []
        bits += [self.transform, self.model]
        bits.append("calendar: " + ("+".join(self.calendar) if self.calendar else
                                    "not modelled" if self.calendar_option == "none" else "none kept"))
        bits.append(f"outliers: {', '.join(self.outliers) if self.outliers else 'none'}")
        if self.m7 is not None:
            bits.append(f"M7 {self.m7:.2f}")
        if self.q is not None:
            bits.append(f"Q {self.q:.2f}")
        return "; ".join(bits)


def _read_table(path: Path, period: int) -> pd.Series:
    if not path.exists():
        raise X13Error(f"X-13 did not write {path.name}")
    rows = []
    for line in path.read_text().splitlines()[2:]:
        parts = line.split()
        if len(parts) != 2:
            continue
        code, val = parts[0], float(parts[1])
        y, p = int(code[:4]), int(code[4:])
        rows.append((pd.Timestamp(y, p if period == 12 else 3 * p - 2, 1), val))
    return pd.Series(dict(rows), dtype=float).sort_index()


def parse_udg(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _num(d: dict, k: str) -> float | None:
    try:
        return float(d[k].split()[0])
    except (KeyError, ValueError, IndexError):
        return None


def _outliers(udg: dict) -> list[str]:
    return [k.split("$", 1)[1] for k in udg if k.startswith("AutoOutlier$")]


def _kept_calendar(udg: dict, calendar: str) -> list[str]:
    """Calendar regressors left in the final model, with their t-values: "kzwd(t=2.1)"."""
    kept = []
    for k, v in udg.items():
        if calendar == "builtin" and k.startswith("Trading Day$"):
            if "td" not in kept:
                kept.append("td")
            continue
        if not (k.startswith("User-defined") and "$" in k):
            continue
        name = k.split("$", 1)[1]
        try:
            tval = float(v.split()[2])
            kept.append(f"{name}(t={tval:.1f})")
        except (IndexError, ValueError):
            kept.append(name)
    return kept


def adjust(s: pd.Series, period: int, *, transform: str = "auto", method: str = "x11",
           calendar: str = "kz", outliers: tuple[str, ...] = ("ao", "ls", "tc"),
           title: str | None = None, binary: Path | None = None, timeout: int = 120) -> X13Result:
    """Seasonally adjust `s` (monthly or quarterly, dated at period starts) with X-13.

    Runs on the longest gap-free run; fewer than MIN_YEARS years there is an X13Error.
    `transform`: auto (AICC chooses log or none) | log | none. `method`: x11 | seats.
    `calendar`: kz (Kazakhstan working days + Kurban Ait, AICC-tested) | builtin (X-13 td) |
    none. Raises X13Unavailable when no binary is found (it never downloads by itself --
    call ensure_binary() first for that)."""
    if period not in (4, 12):
        raise X13Error(f"period={period}: only monthly (12) and quarterly (4) series")
    x = longest_run(s, period)
    dropped = int(s.dropna().shape[0] - x.shape[0])
    name = title or str(s.name or "series")
    if len(x) < MIN_YEARS * period:
        raise X13Error(f"{name}: longest gap-free run is {len(x)} periods, X-13 needs {MIN_YEARS * period} "
                       f"({MIN_YEARS} years)")
    if len(x) > MAX_OBS:
        x = x.iloc[-MAX_OBS:]
    if transform == "log" and (x <= 0).any():
        raise X13Error(f"{name}: log transform on a series with non-positive values")
    if calendar == "kz" and (x.index[0].year < CAL_START or x.index[-1].year + 2 > CAL_END):
        raise X13Error(f"{name}: the Kazakhstan calendar covers {CAL_START}-{CAL_END}; series spans "
                       f"{x.index[0]:%Y-%m}..{x.index[-1]:%Y-%m} (forecasts need one more year)")
    exe = binary or find_binary()
    if exe is None:
        raise X13Unavailable("No X-13ARIMA-SEATS binary (see scripts/lib/x13.py: X13PATH, tools/x13as, cache).")
    with tempfile.TemporaryDirectory(prefix="x13_") as tmp:
        t = Path(tmp)
        (t / "s.spc").write_text(build_spec(x, period, title=name, transform=transform, method=method,
                                            calendar=calendar, outliers=outliers), encoding="ascii")
        if calendar == "kz":
            (t / "kzcal.dat").write_text(regressor_file_text(period), encoding="ascii")
        try:
            proc = subprocess.run([str(exe), "s", "-s", "-q", "-n"], cwd=t, capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise X13Error(f"{name}: X-13 did not finish in {timeout}s") from e
        err = (t / "s.err").read_text(errors="replace") if (t / "s.err").exists() else ""
        err_lines = [ln.strip() for ln in err.splitlines() if ln.strip()][2:]
        if "ERROR" in err or proc.returncode != 0:
            text = re.sub(r"\s+", " ", " ".join(err_lines))
            errors = re.findall(r"ERROR:.*?(?=\*{5,}|ERROR:|$)", text)
            raise X13Error(f"{name}: X-13 failed (exit {proc.returncode}): "
                           + (" | ".join(e.strip() for e in errors) or text)[:1500])
        udg = parse_udg((t / "s.udg").read_text(errors="replace")) if (t / "s.udg").exists() else {}
        tabs = [_read_table(t / f"s.{k}", period) for k in TABLES[method]]
    seasonal, sa, trend, irr, adj = tabs
    if transform == "auto":
        tr = "log" if udg.get("aictrans", "").lower().startswith("log") else "none"
    else:
        tr = transform
    mode = "multiplicative" if tr == "log" else "additive"     # build_spec ties x11 mode to it
    return X13Result(
        sa=sa.rename(name), seasonal=seasonal, trend=trend, irregular=irr, adjustment=adj,
        mode=mode, transform=tr, model=udg.get("arimamdl", ""), method=method,
        calendar=_kept_calendar(udg, calendar), calendar_option=calendar, outliers=_outliers(udg), aicc=_num(udg, "aicc"),
        m7=_num(udg, "f3.m07"), q=_num(udg, "f3.q"), q2=_num(udg, "f3.qm2"),
        span=(x.index[0].strftime("%Y-%m"), x.index[-1].strftime("%Y-%m")), n=len(x), dropped=dropped,
        warnings=[ln for ln in err_lines if ln], udg=udg)
