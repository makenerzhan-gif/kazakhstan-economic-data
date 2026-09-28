"""CIS Stat (Статкомитет СНГ, Interstate Statistical Committee of the CIS): 1990s and later data
for Kazakhstan and the other former Soviet republics from the committee's public database
«Статистика СНГ» (added 2026-09-28). Item-level layer (config/dims.yaml, fetcher cisstat).

Source: the JSON service behind the pivot pages https://new.cisstat.org/consstat/pivot/?language=ru&factId={fact},
no key:

    GET https://new.cisstat.org/consstat/service/fact/data/{fact}/freq/{freq}?locale=ru
        freq 44 = year, 41 = month
    -> {"data": [[header...], [row...], ...], "maxUpdateDate": ..., "valueScale": ...}
       header e.g. ['Страны', 'Год', 'Значение', 'Примечание', 'Дата_обновления', 'Оценочное', 'Точность'],
       every value a string ('89.0'), the country a Russian name ('Казахстан').

Records: region = ISO 3166 alpha-3 code of the reporting country (KAZ, RUS, ... ; CIS for the
committee's own aggregate «СНГ»), item_code = the measure, annual values dated 31 December
(population at the start of the year: 1 January, as POPULATION_BOY_BY_REGION). A row flagged
«Оценочное» carries transformation 'estimate'.

    table gdp_volume  fact 714662   CIS_GDP_VOLUME_INDEX  real GDP, % of previous year      item GDP
    table cpi         fact 43370    CIS_CPI               CPI, December rows only:
                                      <GROUP>.DEC_DEC  «К декабрю предыдущего года»  (December on December)
                                      <GROUP>.AVG      «Период с начала года к соответствующему периоду
                                                        предыдущего года» in December (annual average on
                                                        annual average); GROUP TOTAL, GOODS, FOOD, NONFOOD,
                                                        SERVICES
    table population  facts 44176 (1 January), 44177 (annual average), thousand persons
                                    CIS_POPULATION  items BOY, AVG (+ .URBAN/.RURAL, BOY.MEN/.WOMEN)
    table migration   facts 4650866 / 4679599 (arrivals / departures by flow, persons)
                      facts 44243 / 44245   (arrivals / departures by partner country)
                                    CIS_MIGRATION  items ARRIVALS, DEPARTURES, NET (= arrivals - departures),
                                                   ARRIVALS.CIS / .NON_CIS (and DEPARTURES.*),
                                                   ARRIVALS.<ISO3> / DEPARTURES.<ISO3> by partner (2016 on; the
                                                   reporting country's own row included, 0 for KAZ)

Checked live 2026-09-28 (see pending/cisstat.md, tests/test_cisstat.py):
- Kazakhstan's GDP volume index equals BNS GDP_REAL in every year 1991-2025 (1991 89.0, 1992 94.7,
  1993 90.8, 1994 87.4).
- Kazakhstan's CPI December on December 1991-1999: 247.1, 3060.8, 2265.0, 1258.3, 160.33, 128.7,
  111.16, 101.93, 117.83; the annual average 190.9, 1614.8, 1758.4, 1977.4, 276.2, ...
- Kazakhstan's international arrivals/departures (fact 4650866/4679599, «Международная миграция -
  всего») equal BNS MIGRATION_ARRIVALS / MIGRATION_DEPARTURES in every year 2000-2025 except 2008
  (CIS Stat 46 404 / 45 287, BNS 46 113 / 44 813); 1994: 70 389 arrived, 477 068 left.
- The committee's own net-migration fact 5320380 is not used: for Kazakhstan 2016 it gives
  -20 193 while its arrivals minus departures are 13 755 - 34 900 = -21 145.

Hard checks (StructuralChangeError): the answer is not {"data": [header, rows...]}; a column the
parser reads is missing; a country, partner, flow, CPI group/base, sex or area label nobody has
mapped; a value that is not a number; two different values for one (date, country, item);
Kazakhstan without 1991-1999 in a table; for Kazakhstan, partner countries not summing to the
CIS total, CIS + non-CIS not equal to the international total, or the two migration facts
disagreeing on it (for the other countries these three are warnings).

The committee updates these a few times a year; a dataset is re-downloaded once a week
(`refresh_days`, default 7 -- as imf_dims), the stored records are returned in between.
"""
from __future__ import annotations

import gzip
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import raw_store, validation  # noqa: E402

AGENCY = "cisstat"
BASE = "https://new.cisstat.org/consstat"
DATA_URL = BASE + "/service/fact/data/{fact}/freq/{freq}?locale=ru"
PIVOT_URL = BASE + "/pivot/?language=ru&factId={fact}"
FREQ_YEAR = 44
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KZEconDataPipeline/1.0; +https://github.com/)",
           "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
REFRESH_DAYS = 7
FIRST_YEARS = range(1991, 2000)          # Kazakhstan must be present in each of these years

# Russian country names as the committee writes them -> ISO3. 'CHГ' (Latin C and H, Cyrillic Г)
# is how the CIS aggregate is spelled in some facts; names are matched after folding look-alikes.
COUNTRIES = {"азербайджан": "AZE", "армения": "ARM", "беларусь": "BLR", "грузия": "GEO", "казахстан": "KAZ",
             "кыргызстан": "KGZ", "молдова": "MDA", "россия": "RUS", "таджикистан": "TJK", "туркменистан": "TKM",
             "узбекистан": "UZB", "украина": "UKR", "снг": "CIS"}
_LATIN = str.maketrans({"a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у", "k": "к", "b": "в",
                        "h": "н", "m": "м", "t": "т"})

C_COUNTRY, C_YEAR, C_VALUE, C_ESTIMATE = "Страны", "Год", "Значение", "Оценочное"

CPI_GROUPS = {"все товары и услуги": "TOTAL", "товары": "GOODS", "продовольственные товары": "FOOD",
              "непродовольственные товары": "NONFOOD", "услуги": "SERVICES"}
CPI_BASES = {"к декабрю предыдущего года": "DEC_DEC",
             "период с начала года к соответствующему периоду предыдущего года": "AVG",
             "к соответствующему периоду предыдущего года": None,     # in December = DEC_DEC (checked)
             "к предыдущему периоду": None}                            # December on November
SEX = {"всего": None, "мужчины": "MEN", "женщины": "WOMEN"}
AREA = {"всего": None, "городская местность": "URBAN", "сельская местность": "RURAL"}
FLOWS = {"международная миграция - всего": "", "всего по странам снг": ".CIS",
         "другие страны (исключая страны снг) - всего": ".NON_CIS",
         # Not kept: internal moves, all moves, and «Неизвестно», which the answer lists twice per
         # country and year with different values (unknown origin within internal AND within
         # international moves -- the hidden parent is not in the JSON), so it cannot be keyed.
         "внутри страны": None, "вся миграция": None, "неизвестно": None}

TABLES = {
    "gdp_volume": {"gdp": 714662},
    "cpi": {"cpi": 43370},
    "population": {"boy": 44176, "avg": 44177},
    "migration": {"arrivals": 4650866, "departures": 4679599, "arrivals_partner": 44243, "departures_partner": 44245},
}
NAMES = {
    "GDP": "Индекс физического объема ВВП, % к предыдущему году",
    "DEC_DEC": "декабрь к декабрю предыдущего года", "AVG": "год к предыдущему году (в среднем за год)",
    "TOTAL": "Все товары и услуги", "GOODS": "Товары", "FOOD": "Продовольственные товары",
    "NONFOOD": "Непродовольственные товары", "SERVICES": "Услуги",
    "BOY": "Численность постоянного населения на начало года", "AVG_POP": "Среднегодовая численность постоянного населения",
    "MEN": "мужчины", "WOMEN": "женщины", "URBAN": "городская местность", "RURAL": "сельская местность",
    "ARRIVALS": "Прибывшие (международная миграция)", "DEPARTURES": "Выбывшие (международная миграция)",
    "NET": "Сальдо международной миграции (прибывшие минус выбывшие)",
    "CIS": "страны СНГ", "NON_CIS": "другие страны (исключая страны СНГ)",
}


class FormatError(ValueError):
    """A parser's view of a structural change; fetch() turns it into StructuralChangeError."""


# ---------------------------------------------------------------- helpers

def _norm(label) -> str:
    return re.sub(r"\s+", " ", str(label or "")).strip().lower().replace("ё", "е")


def country_code(name) -> str:
    code = COUNTRIES.get(_norm(name).translate(_LATIN))
    if code is None:
        raise FormatError(f"unknown country {name!r} (not in cisstat.COUNTRIES)")
    return code


def _lookup(mapping: dict, label, what: str):
    key = _norm(label)
    if key not in mapping:
        raise FormatError(f"unknown {what} {label!r} (known: {sorted(mapping)})")
    return mapping[key]


def _value(cell, where: str) -> float:
    try:
        return round(float(cell), 6)
    except (TypeError, ValueError):
        raise FormatError(f"value {cell!r} is not a number ({where})") from None


def parse_payload(content: bytes | str | dict, fact: int, required: tuple[str, ...]) -> tuple[list[dict], dict]:
    """(rows as {column: cell}, the answer's other keys) -- header checked for `required`."""
    try:
        payload = content if isinstance(content, dict) else json.loads(content)
    except ValueError as exc:
        raise FormatError(f"fact {fact}: the answer is not JSON ({exc})") from None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data or not isinstance(data[0], list):
        raise FormatError(f"fact {fact}: no 'data' table ([header, rows...]) in the answer")
    header = [str(h) for h in data[0]]
    missing = [c for c in required if c not in header]
    if missing:
        raise FormatError(f"fact {fact}: columns {missing} missing; header is {header}")
    rows = []
    for r in data[1:]:
        if not isinstance(r, list) or len(r) != len(header):
            raise FormatError(f"fact {fact}: a row does not match the header ({r!r})")
        rows.append(dict(zip(header, r)))
    if not rows:
        raise FormatError(f"fact {fact}: the table is empty")
    return rows, {k: v for k, v in payload.items() if k != "data"}


def _year(row: dict, fact: int) -> int:
    y = str(row.get(C_YEAR) or "").strip()
    if not re.fullmatch(r"\d{4}", y):
        raise FormatError(f"fact {fact}: year {y!r} is not a four-digit year")
    return int(y)


def _transformation(row: dict) -> str:
    flag = _norm(row.get(C_ESTIMATE))
    if flag not in ("f", "t", ""):
        raise FormatError(f"«Оценочное» flag {row.get(C_ESTIMATE)!r} is neither 't' nor 'f'")
    return "estimate" if flag == "t" else "level"


def _record(d: str, region: str, code: str, name: str, value: float, transformation: str = "level") -> dict:
    return {"date": d, "region": region, "item_code": code, "item_name": name, "value": value,
            "transformation": transformation}


def dedupe(records: list[dict]) -> list[dict]:
    """One record per (date, region, item); a second, different value is a structural change."""
    seen: dict[tuple, dict] = {}
    for r in records:
        k = (r["date"], r["region"], r["item_code"])
        if k in seen:
            if seen[k]["value"] != r["value"]:
                raise FormatError(f"two values for {r['item_code']} @{r['region']} on {r['date']}: "
                                  f"{seen[k]['value']} and {r['value']}")
            continue
        seen[k] = r
    return list(seen.values())


def require_kazakhstan(records: list[dict], items: list[str], years=FIRST_YEARS, day: str = "12-31") -> None:
    have = {(r["item_code"], r["date"]) for r in records if r["region"] == "KAZ"}
    missing = [f"{i} {y}" for i in items for y in years if (i, f"{y}-{day}") not in have]
    if missing:
        raise FormatError(f"Kazakhstan's 1990s values missing: {missing[:12]}")


# ---------------------------------------------------------------- tables

def gdp_records(rows: list[dict], fact: int = 714662) -> list[dict]:
    out = []
    for r in rows:
        if r.get(C_VALUE) in (None, ""):
            continue
        out.append(_record(f"{_year(r, fact)}-12-31", country_code(r[C_COUNTRY]), "GDP", NAMES["GDP"],
                           _value(r[C_VALUE], f"fact {fact} {r[C_COUNTRY]} {r[C_YEAR]}"), _transformation(r)))
    out = dedupe(out)
    require_kazakhstan(out, ["GDP"])
    return out


CPI_COLUMNS = ("В % к", "Потребительские товары и услуги", "Периоды")


def cpi_records(rows: list[dict], fact: int = 43370) -> list[dict]:
    """December rows only: DEC_DEC and AVG per consumer group. The third base («к соответствующему
    периоду предыдущего года») must equal DEC_DEC in December -- checked, a difference above
    rounding is a structural change (the committee would then mean something else by one of them)."""
    base_col, group_col, period_col = CPI_COLUMNS
    out, same_month = [], {}
    for r in rows:
        base = _lookup(CPI_BASES, r[base_col], "CPI base («В % к»)")
        group = _lookup(CPI_GROUPS, r[group_col], "CPI group")
        if _norm(r[period_col]) != "декабрь" or r.get(C_VALUE) in (None, ""):
            continue
        d, region = f"{_year(r, fact)}-12-31", country_code(r[C_COUNTRY])
        value = _value(r[C_VALUE], f"fact {fact} {r[C_COUNTRY]} {r[C_YEAR]}")
        if base is None:
            if _norm(r[base_col]) == "к соответствующему периоду предыдущего года":
                same_month[(d, region, f"{group}.DEC_DEC")] = value
            continue
        out.append(_record(d, region, f"{group}.{base}", f"ИПЦ: {NAMES[group]}, {NAMES[base]}", value, _transformation(r)))
    out = dedupe(out)
    for r in out:
        other = same_month.get((r["date"], r["region"], r["item_code"]))
        if other is not None and abs(other - r["value"]) > 0.051 * max(1.0, abs(r["value"]) / 1000):
            raise FormatError(f"{r['item_code']} @{r['region']} {r['date']}: December «к декабрю предыдущего года» "
                              f"{r['value']} differs from «к соответствующему периоду предыдущего года» {other}")
    require_kazakhstan(out, ["TOTAL.DEC_DEC", "TOTAL.AVG"])
    return out


def _population_code(base: str, row: dict) -> tuple[str, str]:
    parts, names = [base], [NAMES["BOY" if base == "BOY" else "AVG_POP"]]
    sex_col = "Справочник половозрастных характеристик"
    if sex_col in row:
        sex = _lookup(SEX, row[sex_col], "sex")
        if sex:
            parts.append(sex)
            names.append(NAMES[sex])
    area = _lookup(AREA, row["Тип местности"], "area («Тип местности»)")
    if area:
        parts.append(area)
        names.append(NAMES[area])
    return ".".join(parts), ", ".join(names)


def population_records(boy_rows: list[dict], avg_rows: list[dict], facts=(44176, 44177)) -> list[dict]:
    out = []
    for base, rows, fact, day in (("BOY", boy_rows, facts[0], "01-01"), ("AVG", avg_rows, facts[1], "12-31")):
        for r in rows:
            if r.get(C_VALUE) in (None, ""):
                continue
            code, name = _population_code(base, r)
            out.append(_record(f"{_year(r, fact)}-{day}", country_code(r[C_COUNTRY]), code, name,
                               _value(r[C_VALUE], f"fact {fact} {r[C_COUNTRY]} {r[C_YEAR]}"), _transformation(r)))
    out = dedupe(out)
    require_kazakhstan(out, ["BOY"], day="01-01")
    require_kazakhstan(out, ["AVG"])
    return out


PARTNER_COL = "Территориальный справочник по миграции"


def migration_records(arrivals: list[dict], departures: list[dict], arrivals_partner: list[dict] | None = None,
                      departures_partner: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    """(records, warnings). Totals and CIS / non-CIS / unknown from the flow facts; partner countries
    from the partner facts («Тип местности» = «Всего»); NET = ARRIVALS - DEPARTURES where both exist."""
    out, warnings = [], []
    partner_totals: dict[tuple, float] = {}
    for base, flow_rows, partner_rows in (("ARRIVALS", arrivals, arrivals_partner or []),
                                          ("DEPARTURES", departures, departures_partner or [])):
        for r in flow_rows:
            suffix = _lookup(FLOWS, r[PARTNER_COL], "migration flow")
            if suffix is None or r.get(C_VALUE) in (None, ""):
                continue
            code = base + suffix
            name = NAMES[base] + (f": {NAMES[suffix[1:]]}" if suffix else "")
            out.append(_record(f"{_year(r, 0)}-12-31", country_code(r[C_COUNTRY]), code, name,
                               _value(r[C_VALUE], f"{base} {r[C_COUNTRY]} {r[C_YEAR]}"), _transformation(r)))
        for r in partner_rows:
            if _lookup(AREA, r["Тип местности"], "area («Тип местности»)") is not None or r.get(C_VALUE) in (None, ""):
                continue
            label = _norm(r[PARTNER_COL])
            d, region = f"{_year(r, 0)}-12-31", country_code(r[C_COUNTRY])
            value = _value(r[C_VALUE], f"{base} partner {r[C_COUNTRY]} {r[C_YEAR]}")
            if label in FLOWS:
                if FLOWS[label] is None:
                    continue
                partner_totals[(d, region, base + FLOWS[label])] = value
                continue
            # the reporting country's own row is kept: 0 for Kazakhstan, but Moldova reports
            # moves from Moldova (1-11 a year), and the partners sum to the CIS total only with it
            partner = country_code(r[PARTNER_COL])
            out.append(_record(d, region, f"{base}.{partner}", f"{NAMES[base]}: {r[PARTNER_COL]}", value, _transformation(r)))
    out = dedupe(out)
    by_key = {(r["date"], r["region"], r["item_code"]): r["value"] for r in out}
    # the two facts must agree on the totals they share (hard for Kazakhstan, a warning for the others)
    for (d, region, code), v in sorted(partner_totals.items()):
        mine = by_key.get((d, region, code))
        if mine is not None and mine != v:
            msg = f"{code} @{region} {d}: flow fact {mine}, partner fact {v}"
            if region == "KAZ":
                raise FormatError(msg)
            warnings.append(msg)
    # partner countries sum to the CIS total
    sums: dict[tuple, float] = {}
    for r in out:
        m = re.fullmatch(r"(ARRIVALS|DEPARTURES)\.([A-Z]{3})", r["item_code"])
        if m and m.group(2) != "CIS":
            sums[(r["date"], r["region"], f"{m.group(1)}.CIS")] = sums.get((r["date"], r["region"], f"{m.group(1)}.CIS"), 0.0) + r["value"]
    for k, s in sorted(sums.items()):
        total = by_key.get(k, partner_totals.get(k))
        if total is not None and abs(total - s) > 0.5:
            msg = f"{k[2]} @{k[1]} {k[0]}: partner countries sum to {s:.0f}, the CIS total is {total:.0f}"
            if k[1] == "KAZ":
                raise FormatError(msg)
            warnings.append(msg)
    # CIS + non-CIS = the international total (the unknown-origin rest is not separable, see FLOWS)
    for (d, region, code), v in sorted(by_key.items()):
        if code in ("ARRIVALS", "DEPARTURES") and (d, region, f"{code}.CIS") in by_key and (d, region, f"{code}.NON_CIS") in by_key:
            s = by_key[(d, region, f"{code}.CIS")] + by_key[(d, region, f"{code}.NON_CIS")]
            if abs(s - v) > 0.5:
                msg = f"{code} @{region} {d}: CIS + non-CIS = {s:.0f}, the international total is {v:.0f}"
                if region == "KAZ":
                    raise FormatError(msg)
                warnings.append(msg)
    for (d, region, code), v in list(by_key.items()):
        if code == "ARRIVALS" and (d, region, "DEPARTURES") in by_key:
            out.append(_record(d, region, "NET", NAMES["NET"], round(v - by_key[(d, region, "DEPARTURES")], 6),
                               "arrivals minus departures"))
    require_kazakhstan(out, ["ARRIVALS", "DEPARTURES"])
    return out, warnings


# ---------------------------------------------------------------- download

def _get(url: str, timeout: int = 180) -> bytes:
    import requests
    last = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
            print(f"cisstat: transport error on {url} (attempt {attempt + 1}/3): {type(exc).__name__}", file=sys.stderr)
    raise last  # type: ignore[misc]


def _structural(ds: dict, what: str, url: str) -> None:
    raise validation.StructuralChangeError("\n".join([
        f"STRUCTURAL CHANGE DETECTED in {AGENCY}/{ds['id']}",
        f"WHAT CHANGED: {what}",
        "EXPECTED: the layout described in scripts/fetchers/cisstat.py (checked 2026-09-28)",
        f"ACTION REQUIRED: inspect {url} (pivot page {PIVOT_URL.format(fact='<fact>')}) and update scripts/fetchers/cisstat.py",
    ]))


def download(ds: dict, role: str, fact: int, freq: int = FREQ_YEAR) -> tuple[bytes, str]:
    """The answer for one fact, archived gzip-compressed (fixed mtime: unchanged data, same bytes)."""
    url = DATA_URL.format(fact=fact, freq=freq)
    content = _get(url)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(content)
    today = date.today()
    name = f"{ds['id']}_{fact}"
    path = raw_store.save_raw_bytes(AGENCY, name, today, "json.gz", buf.getvalue())
    raw_store.write_download_manifest(AGENCY, name, today, {
        "downloaded_at": datetime.now().isoformat(), "raw_file": path.name, "source_url": url, "fact": fact, "role": role})
    return content, url


def stored_if_fresh(ds: dict, name: str) -> tuple[list[dict], dict] | None:
    """The stored records (with their transformation: 'estimate', 'arrivals minus departures')
    when the last download is younger than `refresh_days`; None when a download is due."""
    from fetchers import imf_dims
    from lib import dims
    days = ds.get("refresh_days", REFRESH_DAYS)
    last = imf_dims.last_download(AGENCY, name)
    stored = dims.load_processed(ds["id"])
    if not days or last is None or not stored or (date.today() - last).days >= days:
        return None
    records = [{"date": r["date"], "region": r["region"], "item_code": r["item_code"], "item_name": r["item_name"],
                "value": float(r["value"]), "transformation": r.get("transformation") or "level"} for r in stored]
    return records, {"frequency": "annual", "note": ds.get("note", ""),
                     "warnings": [f"not re-downloaded: last download {last.isoformat()}, refreshed every {days} days"]}


REQUIRED = {"gdp_volume": (C_COUNTRY, C_YEAR, C_VALUE, C_ESTIMATE),
            "cpi": (C_COUNTRY, C_YEAR, C_VALUE, C_ESTIMATE) + CPI_COLUMNS,
            "population": (C_COUNTRY, C_YEAR, C_VALUE, C_ESTIMATE, "Тип местности"),
            "migration": (C_COUNTRY, C_YEAR, C_VALUE, C_ESTIMATE, PARTNER_COL)}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    table = ds["table"]
    facts = {**TABLES[table], **(ds.get("facts") or {})}
    fresh = stored_if_fresh(ds, f"{ds['id']}_{next(iter(facts.values()))}")
    if fresh:
        return fresh
    rows, meta, urls = {}, {}, []
    for role, fact in facts.items():
        content, url = download(ds, role, fact)
        urls.append(url)
        required = REQUIRED[table] + (("Справочник половозрастных характеристик",) if role == "boy" else ())
        try:
            rows[role], meta[role] = parse_payload(content, fact, required)
        except FormatError as exc:
            _structural(ds, str(exc), url)
    warnings: list[str] = []
    try:
        if table == "gdp_volume":
            records = gdp_records(rows["gdp"], facts["gdp"])
        elif table == "cpi":
            records = cpi_records(rows["cpi"], facts["cpi"])
        elif table == "population":
            records = population_records(rows["boy"], rows["avg"], (facts["boy"], facts["avg"]))
        elif table == "migration":
            records, warnings = migration_records(rows["arrivals"], rows["departures"],
                                                  rows.get("arrivals_partner"), rows.get("departures_partner"))
        else:
            raise KeyError(table)
    except FormatError as exc:
        _structural(ds, str(exc), " ".join(urls))
    min_countries = ds.get("min_countries", 9)
    n = len({r["region"] for r in records if r["region"] != "CIS"})
    if n < min_countries:
        _structural(ds, f"only {n} countries (expected at least {min_countries})", " ".join(urls))
    updated = max((m.get("maxUpdateDate") or "" for m in meta.values()), default="")
    return records, {"frequency": "annual", "source_url": urls[0] if len(urls) == 1 else "; ".join(urls),
                     "dataset_id": "cisstat/" + "+".join(str(f) for f in facts.values()),
                     "release": updated[:10] or None, "warnings": warnings,
                     "note": ds.get("note", "") + (f" CIS Stat last updated {updated[:10]}." if updated else "")}
