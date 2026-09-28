"""Monthly average official KZT rates of the currencies of Kazakhstan's import partners
(added 2026-09-27, for an import-weighted effective exchange rate, fetchers/neer_import.py;
extended back to the tenge's introduction, 1993-11, on 2026-09-28).

Sources, spliced per currency:
  1999-11 onward  the NBK report behind «Ежедневные официальные (рыночные) курсы валют»
      (fetchers/nbk.OFFICIAL_RATES_REPORT_URL), one request PER CURRENCY: when several are
      asked together, a currency with no rate on a day is left out of that day's row and the
      columns after it shift, so a joint table cannot be read safely. Each row gives the
      quantity (1, 10, 100 or 1000 units) and the rate. The report's first rows, 1999-10-19..
      10-30, are malformed (JPY 6.5 -> 0.5, CHF 5, KGS 65) and dropped: it is read from
      nbk.OFFICIAL_RATES_FIRST_DATE (1999-11-01; the first usable day is 1999-11-17). Read in
      windows of REPORT_WINDOW_YEARS on the first load (one request answered 17 years whole,
      the windows keep each answer to ~1.5 MB).
  1993-11 .. the report's first day  the NBK archive «Архив официальных курсов валют с 1993
      по 1999» (nbk.OFFICIAL_RATES_ARCHIVE_URL, parsed by nbk.parse_official_rates_archive):
      the rate IN FORCE on each weekday (rates were set once or twice a week before April
      1999; nbk.archive_weekday_series). It carries 11 of the 18 currencies: USD, EUR (1999
      only), CNY (from 1996-02), RUB, GBP, CHF, JPY, KGS, TRY (as TRL), BYN (as BYB, to
      1997-02), UZS (1993-12..1994-04 and 1995-10..1996-11). Where the report also quotes the
      currency in 1999-11-17..12-31, every common weekday must be equal
      (nbk.check_archive_overlap) or the fetcher stops.
The value stored is KZT per ONE CURRENT unit, averaged over the weekdays of the month
(weekend rows of the report repeat Friday's rate and are dropped).

Precision: both sources print two decimals, so a unit worth less than 1 KZT is printed «0.1»
or «0.05» until the NBK switched it to a quote per 10/100/1000 (UZS; the Belarusian rouble
before its 2016 redenomination; the Turkish lira per 1000 in the archive). A day whose
PRINTED figure is below 1.0 is dropped in both sources -- that currency is simply missing for
those months, not a false 50% move.

Redenominations (REDENOMINATIONS) are restated to the current unit, explicitly: a source
quoting OLD units has its earlier per-unit rates multiplied by old-per-new. Each is checked
against the data where the source has a rate within REDENOMINATION_WINDOW_DAYS on both sides
of the date (the jump must be there, within a factor JUMP_FACTOR of old-per-new), and after
restatement no two rates within that window may differ by more than JUMP_FACTOR (an
unexpected ~1000x step = an unlisted redenomination or a quantity change) -- both stop the
fetcher (StructuralChangeError).

Accumulated: the first run (no stored month before the report) loads everything; later runs
re-read the report from the first day of the previous month and recompute those months only.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetchers import nbk  # noqa: E402
from lib import dims, raw_store, validation  # noqa: E402

# ISO code: (report currency id, Russian name) -- ids checked against the report's own list.
CURRENCIES = {
    "USD": ("5", "Доллар США"), "EUR": ("6", "Евро"), "CNY": ("8", "Китайский юань"), "RUB": ("16", "Российский рубль"),
    "TRY": ("41", "Турецкая лира"), "KRW": ("25", "Южно-корейская вона"), "UZS": ("20", "Узбекский сум"),
    "KGS": ("10", "Кыргызский сом"), "BYN": ("38", "Белорусский рубль"), "JPY": ("26", "Японская иена"),
    "GBP": ("2", "Фунт стерлингов"), "INR": ("49", "Индийская рупия"), "CHF": ("23", "Швейцарский франк"),
    "CZK": ("43", "Чешская крона"), "PLN": ("39", "Польский злотый"), "AED": ("4", "Дирхам ОАЭ"),
    "TJS": ("44", "Таджикский сомони"), "AZN": ("48", "Азербайджанский манат"),
}
FIRST_DATE = date(1993, 11, 1)                                 # the tenge: 1993-11-15, first NBK rate 1993-11-18
REPORT_FIRST_DATE = date.fromisoformat(nbk.OFFICIAL_RATES_FIRST_DATE)   # 1999-11-01
REPORT_WINDOW_YEARS = 10
MIN_PRINTED = 1.0
ARCHIVE_CODES = {"TRY": "TRL", "BYN": "BYB"}                   # archive code of the predecessor unit, else the ISO code
# code: [(first day of the new unit, old units per new one, old code, {source: first day that source
# quotes the NEW unit})] -- a source listed quotes OLD units before its day and is restated here; a
# source not listed quotes the new unit throughout (or has no rate near the date).
REDENOMINATIONS = {
    # Archive: «за 1000 единиц ... номинал 1*1000 действовал до 1 января 1998 года» -- the quote per
    # 1000 old roubles IS one new rouble; nbk.parse_official_rates_archive keeps it (13.00 on both sides).
    "RUB": [(date(1998, 1, 1), 1000, "RUR", {})],
    # The sum replaced the sum-coupon 1000:1 on 1994-07-01. The archive's 1993-12..1994-04 figures
    # (1.51..3.42) are per 1000 coupons, i.e. per one sum: per ONE coupon they would put it at
    # hundreds of roubles, and they sit next to the rouble per 1000 (check_uzs_coupon_scale).
    "UZS": [(date(1994, 7, 1), 1000, "sum-coupon", {})],
    "TRY": [(date(2005, 1, 1), 1_000_000, "TRL", {"archive": date(2005, 1, 1), "report": date(2005, 1, 1)})],
    # BYB -> BYR 2000-01-01 and BYR -> BYN 2016-07-01. The report's rate in force on Fri 2016-07-01 was
    # set on 06-30 and is still per 100 old roubles (1.68); its first BYN quote is Sat 07-02 (170.73).
    "BYN": [(date(2000, 1, 1), 1000, "BYB", {"archive": date(2000, 1, 1), "report": date(2000, 1, 1)}),
            (date(2016, 7, 1), 10000, "BYR", {"archive": date(2016, 7, 1), "report": date(2016, 7, 2)})],
    "AZN": [(date(2006, 1, 1), 5000, "AZM", {"report": date(2006, 1, 1)})],
    "TJS": [(date(2000, 10, 30), 1000, "TJR", {"report": date(2000, 10, 30)})],
    "PLN": [(date(1995, 1, 1), 10000, "PLZ", {"report": date(1995, 1, 1)})],
}
REDENOMINATION_WINDOW_DAYS = 31
JUMP_FACTOR = 8.0


def _structural(what: str, action: str = "") -> validation.StructuralChangeError:
    return validation.StructuralChangeError("\n".join([
        "STRUCTURAL CHANGE DETECTED in nbk_fx/EXCHANGE_RATES_OFFICIAL_MONTHLY",
        f"WHAT CHANGED: {what}",
        f"ACTION REQUIRED: {action or 'inspect the source and update REDENOMINATIONS / CURRENCIES in scripts/fetchers/nbk_fx.py'}",
    ]))


def parse_single(html: str) -> dict[str, float]:
    """{ISO date: KZT per one unit} from a one-currency report (weekdays, printed rate >= 1)."""
    out = {}
    for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 3 or not re.match(r"^\d{4}-\d{2}-\d{2}$", cells[0]):
            continue
        try:
            quantity, rate = float(cells[1].replace(",", ".")), float(cells[2].replace(",", "."))
        except ValueError:
            continue
        if quantity > 0 and rate >= MIN_PRINTED and date.fromisoformat(cells[0]).weekday() < 5:
            out[cells[0]] = rate / quantity
    return out


def redenominate(code: str, daily: dict[str, float], source: str = "report") -> dict[str, float]:
    """Rates quoted by `source` in a predecessor unit, restated in the current unit: every
    redenomination after the day that `source` quotes in old units multiplies the rate."""
    steps = [(sources[source].isoformat(), ratio) for _, ratio, _, sources in REDENOMINATIONS.get(code, [])
             if source in sources]
    if not steps:
        return daily
    out = {}
    for d, v in daily.items():
        for when, ratio in steps:
            if d < when:
                v *= ratio
        out[d] = v
    return out


def _neighbours(daily: dict[str, float], when: date) -> tuple[str, str] | None:
    """The last rate before `when` and the first on/after it, if both lie within the window."""
    lo = (when - timedelta(days=REDENOMINATION_WINDOW_DAYS)).isoformat()
    hi = (when + timedelta(days=REDENOMINATION_WINDOW_DAYS)).isoformat()
    before = [d for d in daily if lo <= d < when.isoformat()]
    after = [d for d in daily if when.isoformat() <= d <= hi]
    return (max(before), min(after)) if before and after else None


def check_redenominations(code: str, source: str, quoted: dict[str, float]) -> list[str]:
    """Check each listed redenomination against `source`'s rates AS QUOTED (before restatement):
    where the source quotes the old unit, the rate must jump by about old-per-new at the date;
    where it already quotes the new unit, it must not. Returns what was found, for the note."""
    found = []
    for legal, ratio, old, sources in REDENOMINATIONS.get(code, []):
        when = sources.get(source, legal)
        pair = _neighbours(quoted, when)
        if pair is None:
            continue
        a, b = pair
        observed = quoted[b] / quoted[a]
        expected = ratio if source in sources else 1.0
        if not expected / JUMP_FACTOR <= observed <= expected * JUMP_FACTOR:
            raise _structural(
                f"{code} ({source}): the {old}->{code} redenomination of {when} ({ratio}:1) is "
                + (f"expected in the quote but absent: {a} {quoted[a]:.6g} -> {b} {quoted[b]:.6g} (x{observed:.4g})"
                   if expected > 1 else
                   f"expected to be absorbed in the quote but a step x{observed:.4g} appears: {a} {quoted[a]:.6g} -> {b} {quoted[b]:.6g}"))
        found.append(f"{code} {old}->{code} {when} ({source}): x{observed:,.0f} at the date" if expected > 1
                     else f"{code} {old}->{code} {when} ({source}): quoted in new units, no step (x{observed:.3f})")
    return found


def check_no_jumps(code: str, daily: dict[str, float]) -> None:
    """After restatement, no two rates within REDENOMINATION_WINDOW_DAYS may differ by more than
    JUMP_FACTOR: that is an unlisted redenomination or a changed quantity."""
    days = sorted(daily)
    for a, b in zip(days, days[1:]):
        if (date.fromisoformat(b) - date.fromisoformat(a)).days > REDENOMINATION_WINDOW_DAYS:
            continue
        r = daily[b] / daily[a]
        if not 1 / JUMP_FACTOR <= r <= JUMP_FACTOR:
            raise _structural(f"{code}: an unexpected step x{r:.4g} from {a} ({daily[a]:.6g}) to {b} ({daily[b]:.6g}) "
                              "-- a redenomination not in REDENOMINATIONS, or a quantity change")


def check_uzs_coupon_scale(archive: dict[str, dict[str, float]]) -> None:
    """The archive's UZS before 1994-07-01 must be of the order of the rouble per 1000 old roubles
    (the sum-coupon came in at par with the rouble in November 1993) -- i.e. quoted per 1000
    coupons = one sum, not per coupon (which would be ~1000x smaller)."""
    uzs, rub = archive.get("UZS", {}), archive.get("RUB", {})
    ratios = sorted(uzs[d] / rub[d] for d in uzs if d < "1994-07-01" and d in rub)
    if ratios and not 0.05 <= ratios[len(ratios) // 2] <= 20:
        raise _structural(f"UZS before 1994-07-01: median UZS/RUB {ratios[len(ratios) // 2]:.4g}, expected the "
                          "order of 1 (a quote per 1000 sum-coupons = one sum)")


def archive_rates(sheets: dict[str, list[list]]) -> tuple[dict[str, dict[str, float]], list[str]]:
    """{code: {weekday: KZT per one CURRENT unit}} from the archive workbook for CURRENCIES,
    printed figures below MIN_PRINTED dropped, redenominations restated and checked."""
    # Kept as published, like every official figure here (config/source_issues.yaml lists the two CHF
    # figures of 1995-04-17 and 1998-11-09 that are not the franc's rate).
    series = nbk.archive_weekday_series(nbk.parse_official_rates_archive(sheets, min_printed=MIN_PRINTED))
    check_uzs_coupon_scale(series)
    out, found = {}, []
    for code in CURRENCIES:
        quoted = series.get(ARCHIVE_CODES.get(code, code), {})
        if not quoted:
            continue
        found += check_redenominations(code, "archive", quoted)
        out[code] = redenominate(code, quoted, "archive")
        check_no_jumps(code, out[code])
    return out, found


def splice(code: str, archive: dict[str, float], report: dict[str, float]) -> tuple[dict[str, float], str]:
    """The archive before the report's first day for `code`, the report from it. Where the report
    quotes the currency in 1999-11..12 the two must be equal on every common weekday
    (nbk.check_archive_overlap); otherwise (TRY, BYN, UZS: the archive ends before the report
    starts) nothing overlaps and the archive stands alone."""
    if not archive:
        return dict(report), ""
    window = {d: v for d, v in report.items() if d <= nbk.ARCHIVE_OVERLAP_END.isoformat()}
    if window:
        first = nbk.check_archive_overlap(code, archive, window)
        how = f"archive to {first}, equal to the report on every common weekday to {nbk.ARCHIVE_OVERLAP_END}"
    else:
        first = min(report) if report else "9999-12-31"
        how = "archive only (no overlap with the report)"
    history = {d: v for d, v in archive.items() if d < first}
    merged = {**history, **{d: v for d, v in report.items() if d >= first}}
    check_no_jumps(code, merged)
    return merged, f"{code}: {how}, from {min(history)}" if history else ""


def monthly_means(daily: dict[str, float]) -> dict[str, float]:
    by_month: dict[str, list[float]] = defaultdict(list)
    for d, v in daily.items():
        by_month[d[:7] + "-01"].append(v)
    return {m: sum(v) / len(v) for m, v in by_month.items()}


def report_windows(begin: date, end: date, years: int = REPORT_WINDOW_YEARS) -> list[tuple[date, date]]:
    """begin..end in consecutive windows of at most `years` calendar years (Jan 1 boundaries)."""
    out, start = [], begin
    while start <= end:
        stop = min(date(start.year + years, 1, 1) - timedelta(days=1), end)
        out.append((start, stop))
        start = stop + timedelta(days=1)
    return out


def _report_pages(code: str, begin: date, end: date) -> list[str]:
    cid, name = CURRENCIES[code]
    pages = []
    for lo, hi in report_windows(begin, end):
        params = [("rates[]", cid), ("beginDate", lo.strftime("%d.%m.%Y")), ("endDate", hi.strftime("%d.%m.%Y"))]
        resp = requests.get(nbk.OFFICIAL_RATES_REPORT_URL, headers=nbk.HEADERS, params=params, timeout=180)
        resp.raise_for_status()
        html = resp.content.decode("utf-8", "replace")
        heads = [re.sub(r"\s+", " ", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)]
        if heads and not any(name.split()[0].upper()[:5] in h.upper() for h in heads):
            raise validation.StructuralChangeError(
                f"nbk_fx: currency id {cid} no longer answers {name!r} (headers {heads[:4]}) -- update CURRENCIES")
        pages.append(html)
    return pages


def report_rates(code: str, pages: list[str]) -> tuple[dict[str, float], list[str]]:
    """The report's rates for `code` from REPORT_FIRST_DATE, in the current unit, checked; and
    the redenominations found in them."""
    quoted = {}
    for html in pages:
        quoted.update({d: v for d, v in parse_single(html).items() if d >= REPORT_FIRST_DATE.isoformat()})
    found = check_redenominations(code, "report", quoted)
    daily = redenominate(code, quoted, "report")
    check_no_jumps(code, daily)
    return daily, found


def fetch(ds: dict) -> tuple[list[dict], dict]:
    stored = dims.load_processed(ds["id"])
    today = date.today()
    history_loaded = any(r["date"] < REPORT_FIRST_DATE.isoformat() for r in stored)
    begin = (today.replace(day=1) - timedelta(days=1)).replace(day=1) if history_loaded else REPORT_FIRST_DATE
    archive, found, spliced = {}, [], []
    if not history_loaded:
        archive, found = archive_rates(nbk.official_rates_archive_sheets())
    pages, records, empty = {}, [], []
    for code, (cid, name) in CURRENCIES.items():
        pages[code] = _report_pages(code, begin, today)
        report, in_report = report_rates(code, pages[code])
        found += in_report
        daily, how = splice(code, archive.get(code, {}), report) if not history_loaded else (report, "")
        if how:
            spliced.append(how)
        months = monthly_means(daily)
        if not report:
            empty.append(code)
        records += [{"date": m, "region": dims.NATIONAL, "item_code": code, "item_name": f"{name}, тенге за 1 единицу (среднее за месяц)",
                     "value": round(v, 6)} for m, v in months.items()]
    if len(empty) > 3:
        raise validation.StructuralChangeError(f"nbk_fx: no rates for {empty} since {begin}")
    buf = gzip.compress(json.dumps(pages, ensure_ascii=False).encode(), mtime=0)
    path = raw_store.save_raw_bytes("nbk", ds["id"], today, "json.gz", buf)
    raw_store.write_download_manifest("nbk", ds["id"], today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": nbk.OFFICIAL_RATES_REPORT_URL,
        "begin": begin.isoformat(), "windows": [[a.isoformat(), b.isoformat()] for a, b in report_windows(begin, today)],
        "currencies": {c: v[0] for c, v in CURRENCIES.items()},
        "archive": None if history_loaded else {"source_url": nbk.OFFICIAL_RATES_ARCHIVE_URL,
                                                "raw": "raw/nbk/nbk_exchange_rates_archive_1993_1999_<date>.xls",
                                                "spliced": spliced},
        "redenominations_checked": found})
    fresh = {(r["item_code"], r["date"]) for r in records}
    records += [{**r, "value": float(r["value"])} for r in stored if (r["item_code"], r["date"]) not in fresh
                and r["date"] < begin.isoformat()]
    return sorted(records, key=lambda r: (r["item_code"], r["date"])), {
        "frequency": "monthly", "source_url": nbk.OFFICIAL_RATES_REPORT_URL, "dataset_id": "official-rates-report/monthly-mean",
        "history_source_url": nbk.OFFICIAL_RATES_ARCHIVE_URL,
        "note": ds.get("note", ""), "warnings": [f"no rates since {begin} for {empty}"] if empty else []}
