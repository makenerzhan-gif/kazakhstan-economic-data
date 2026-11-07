"""Quality checks for the natural-resources series (data/processed/natural_resources/).

Reads natural_resources_long.csv (every source, harmonised units) and writes
reports/resource_qa.json and reports/resource_qa.md. Run on its own or from
build_resource_panel.py, which also uses the flags to pick values for the panel.

Checks (severity in brackets):
  identity     [error]   shipments to the domestic market > total shipments;
                         total shipments > 1.1 x production (BNS 701622 vs 701608)
  spike        [error]   a value off by more than 60% from both neighbours while the
                         neighbours agree with each other within 25% (one-year outlier)
  break        [warning] a year-on-year jump above 30% that does not revert next year
                         (level shift: real event or a change in how the series is counted)
  gap          [info]    a missing year inside a series
  unit         [error]   Comtrade unit value ($/kg) off by more than 3x from the series
                         median (weight recorded in the wrong unit)
  confidential [warning] national export below 20% of the partner-reported (mirror) figure,
                         or below 10% of the neighbouring-years median (records withheld)
  cross_source [warning] two sources of the same concept differ by more than the tolerance
                         set for the pair in CROSS below
  freshness    [info]    the latest year a source holds is older than expected
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed" / "natural_resources"
REPORTS = ROOT / "reports"

# same-concept pairs: (var, base source, other source, tolerance, note)
CROSS = [
    ("oil_prod", "БНС Талдау", "Energy Institute", 0.02, ""),
    ("oil_prod", "БНС Талдау", "USGS", 0.05, ""),
    ("gas_gross_prod", "БНС Талдау", "USGS", 0.03, ""),
    ("coal_prod", "БНС Талдау", "Energy Institute", 0.02, ""),
    ("coal_prod", "БНС Талдау", "USGS", 0.06, ""),
    ("coal_prod", "БНС Талдау", "EIA", 0.05, ""),
    ("copper_refined", "БНС Талдау", "USGS", 0.05, ""),
    ("aluminium", "БНС Талдау", "USGS", 0.06, ""),
    ("ferroalloys", "БНС Талдау", "USGS", 0.03, ""),
    ("gold_refined", "БНС Талдау", "USGS", 0.03, ""),
    ("alumina", "БНС Талдау", "USGS", 0.05, ""),
    ("oil_export", "UN Comtrade", "БНС Талдау (отгрузки)", 0.08, "косвенная оценка экспорта по отгрузкам"),
    ("oil_export", "UN Comtrade", "UN Comtrade, зеркало", 0.10, "зеркало: импорт партнёров, CIF, транзит"),
    ("coal_export", "UN Comtrade", "БНС Талдау (отгрузки)", 0.10, "косвенная оценка экспорта по отгрузкам"),
    ("coal_export", "UN Comtrade", "UN Comtrade, зеркало", 0.15, "зеркало: импорт партнёров"),
    ("coal_export", "UN Comtrade", "EIA", 0.10, ""),
]
# national export near zero for a known, genuine reason: not a confidentiality gap
CONF_EXEMPT = {"gold_export": "с 2016 г. аффинированное золото выкупает Нацбанк (преимущественное право); "
                              "зеркало Великобритании отражает движение монетарного золота, а не товарный экспорт"}
# latest year a source should already have by today's date (lag in years)
LAG = {"БНС Талдау": 1, "БНС Талдау (отгрузки)": 1, "UN Comtrade": 1, "UN Comtrade, зеркало": 2,
       "Energy Institute": 1, "EIA": 2, "USGS": 3, "БНС, счёт активов SEEA": 2}


def load_long(path: Path | None = None) -> dict:
    """{(var, source, series): {"unit":..., "concept":..., "values": {year: value}}}"""
    path = path or PROC / "natural_resources_long.csv"
    out: dict = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            k = (r["var"], r["source"], r["series"])
            e = out.setdefault(k, {"unit": r["unit"], "concept": r["concept"], "values": {}})
            e["values"][int(r["year"])] = float(r["value"])
    return out


def _issue(out, check, sev, var, source, series, year, value, detail):
    out.append({"check": check, "severity": sev, "var": var, "source": source, "series": series,
                "year": year, "value": None if value is None else round(value, 6), "detail": detail})


def spikes_and_breaks(var, src, ser, v, out):
    ys = sorted(v)
    top = max(abs(x) for x in v.values()) or 1.0
    for i, y in enumerate(ys):
        prev = v.get(y - 1)
        nxt = v.get(y + 1)
        x = v[y]
        if max(abs(x), abs(prev or 0), abs(nxt or 0)) < 0.01 * top:
            continue  # negligible volumes (e.g. 0.0001 Mt): noise, not information
        if prev and nxt and prev > 0 and nxt > 0 and x > 0:
            nb_agree = abs(math.log(nxt / prev)) < math.log(1.25)
            far = abs(math.log(x / prev)) > math.log(1.6) and abs(math.log(x / nxt)) > math.log(1.6)
            if nb_agree and far:
                _issue(out, "spike", "error", var, src, ser, y, x,
                       f"выброс: {x:,.3g} при {prev:,.3g} ({y-1}) и {nxt:,.3g} ({y+1})")
                continue
        if "Comtrade" in src:
            continue  # trade flows swing for real reasons; breaks are checked on output series only
        if prev and prev > 0 and x > 0 and abs(x / prev - 1) > 0.30:
            reverts = nxt is not None and nxt > 0 and abs(math.log(nxt / prev)) < math.log(1.15)
            if not reverts:
                _issue(out, "break", "warning", var, src, ser, y, x,
                       f"скачок {x / prev - 1:+.0%} к {y-1} г. без возврата — реальное событие или смена учёта")


def gaps(var, src, ser, v, out):
    ys = sorted(v)
    for y in range(ys[0], ys[-1] + 1):
        if y not in v:
            _issue(out, "gap", "info", var, src, ser, y, None, "пропуск года внутри ряда")


def run(long: dict) -> list[dict]:
    out: list[dict] = []
    for (var, src, ser), e in long.items():
        v = e["values"]
        if len(v) >= 3 and not var.startswith("reserves_") and not var.endswith("_share") and ser != "стоимость":
            spikes_and_breaks(var, src, ser, v, out)
        if v:
            gaps(var, src, ser, v, out)

    # identity checks on BNS shipments
    by = defaultdict(dict)
    for (var, src, ser), e in long.items():
        if src.startswith("БНС Талдау"):
            by[var][ser] = e["values"]
    for var, d in by.items():
        p, t, dm = d.get("производство"), d.get("отгружено всего"), d.get("отгружено на внутренний рынок")
        for y in sorted(set(t or {}) | set(dm or {})):
            if t and dm and y in t and y in dm and dm[y] > t[y] * 1.001:
                _issue(out, "identity", "error", var, "БНС Талдау", "отгружено на внутренний рынок", y, dm[y],
                       f"на внутренний рынок {dm[y]:,.3g} > отгружено всего {t[y]:,.3g}")
            if p and t and y in p and y in t and t[y] > p[y] * 1.10:
                _issue(out, "identity", "error", var, "БНС Талдау", "отгружено всего", y, t[y],
                       f"отгружено {t[y]:,.3g} > 110% производства {p[y]:,.3g}")

    conf_years = set()
    # confidential records: national export vs mirror and vs neighbours
    nat = {var: e["values"] for (var, src, ser), e in long.items() if src == "UN Comtrade" and ser == "вес нетто"}
    mir = {var: e["values"] for (var, src, ser), e in long.items() if src == "UN Comtrade, зеркало" and ser == "вес нетто"}
    for var, nv in nat.items():
        if var in CONF_EXEMPT:
            continue
        mv = mir.get(var, {})
        for y, x in nv.items():
            nb = [nv[z] for z in range(y - 4, y + 5) if z != y and z in nv and nv[z] > 0]
            low_vs_nb = len(nb) >= 3 and x < 0.10 * statistics.median(nb)
            low_vs_mir = y in mv and mv[y] > 0 and x < 0.20 * mv[y]
            if low_vs_nb or low_vs_mir:
                conf_years.add((var, y))
                why = []
                if low_vs_mir:
                    why.append(f"зеркало {mv[y]:,.3g}")
                if low_vs_nb:
                    why.append(f"медиана соседних лет {statistics.median(nb):,.3g}")
                _issue(out, "confidential", "warning", var, "UN Comtrade", "вес нетто", y, x,
                       "экспорт РК почти нулевой: " + "; ".join(why) + " — вероятно, данные закрыты")

    # unit values for Comtrade
    w = {(var, src): e["values"] for (var, src, ser), e in long.items() if ser == "вес нетто" and "Comtrade" in src}
    val = {(var, src): e["values"] for (var, src, ser), e in long.items() if ser == "стоимость" and "Comtrade" in src}
    for k, wv in w.items():
        vv = val.get(k)
        if not vv:
            continue
        uv = {y: vv[y] / wv[y] for y in wv if y in vv and wv[y] > 0 and vv[y] > 0
              and not (k[1] == "UN Comtrade" and (k[0], y) in conf_years)}
        if len(uv) < 5:
            continue
        for y, x in uv.items():
            nb = [uv[z] for z in range(y - 3, y + 4) if z != y and z in uv]
            if len(nb) < 3:
                continue
            med = statistics.median(nb)
            if x > 3 * med or x < med / 3:
                _issue(out, "unit", "error", k[0], k[1], "вес нетто", y, wv[y],
                       f"удельная стоимость {x:,.3g} при медиане соседних лет {med:,.3g} — ошибка единиц веса")

    # cross-source deviations
    for var, base, other, tol, note in CROSS:
        bs = [e["values"] for (v_, s, ser), e in long.items() if v_ == var and s == base and ser in ("", "производство", "вес нетто", "экспорт")]
        os_ = [e["values"] for (v_, s, ser), e in long.items() if v_ == var and s == other and ser in ("", "производство", "вес нетто", "экспорт")]
        if not bs or not os_:
            continue
        b, o = bs[0], os_[0]
        for y in sorted(set(b) & set(o)):
            if b[y] and abs(o[y] / b[y] - 1) > tol:
                _issue(out, "cross_source", "warning", var, other, base, y, o[y],
                       f"{other} {o[y]:,.4g} vs {base} {b[y]:,.4g}: {o[y] / b[y] - 1:+.1%} (допуск ±{tol:.0%})"
                       + (f"; {note}" if note else ""))

    classify_breaks(out, long)

    # freshness
    latest = defaultdict(int)
    for (var, src, ser), e in long.items():
        if e["values"]:
            latest[src] = max(latest[src], max(e["values"]))
    today = date.today().year
    for src, lag in LAG.items():
        if src in latest and latest[src] < today - lag:
            _issue(out, "freshness", "info", "*", src, "", latest[src], None,
                   f"последний год {latest[src]}, ожидается не раньше {today - lag}")
    return out


# Events that plausibly explain a level shift. Hypotheses to check, not established causes.
EVENTS = [
    (("oil", "gas", "coal", "iron", "chrom", "mangan", "bauxite", "alumin", "copper", "zinc", "lead", "ferro",
      "gold", "silver", "titan", "uranium", "phosph", "steel", "pig"), range(1991, 1999), "down",
     "трансформационный спад после распада СССР (1991–1998)"),
    (("copper_ore", "copper_mine"), range(2015, 2019), "up", "ввод Бозшаколя (2016) и Актогая (2017, сульфидная руда)"),
    (("uranium",), range(2001, 2011), "up", "наращивание добычи Казатомпрома, выход на 1-е место в мире (2009)"),
    (("oil", "gas"), range(2016, 2018), "up", "возобновление добычи на Кашагане (конец 2016 г.)"),
    (("oil", "gas"), (2025,), "up", "ввод Проекта будущего расширения на Тенгизе (2025)"),
]
SIBLING_SER = ("", "производство", "вес нетто", "экспорт")
# indicators that measure the same activity under another definition: a jump in one should show in the other
RELATED = [("copper_ore", "copper_mine_cu"), ("iron_ore_gross", "iron_ore_conc", "iron_ore_usgs"),
           ("chrome_ore", "chromite_marketable"), ("zinc_refined", "zinc_mine"), ("lead_refined", "lead_mine"),
           ("silver_refined", "silver_mine"), ("gas_gross_prod", "gas_assoc_prod", "gas_marketed_prod", "gas_dry_prod"),
           ("alumina", "bauxite"), ("aluminium", "alumina"), ("oil_prod", "oil_products_prod")]


def classify_breaks(issues: list[dict], long: dict) -> None:
    """Adds i["class"] to break warnings: does the jump show in other measures of the same activity?
    Production is compared with other sources and related definitions (not with shipments: ore is mostly
    processed on site, so shipments move differently); shipments are compared with production."""
    by_var = defaultdict(list)
    for (var, src, ser), e in long.items():
        if ser != "стоимость":
            by_var[var].append((var, src, ser, e["values"]))
    rel = defaultdict(set)
    for grp in RELATED:
        for a in grp:
            rel[a] |= set(grp) - {a}
    spikes = {(i["var"], i["source"], i["series"], i["year"]) for i in issues if i["check"] == "spike"}
    drop = []
    for i in issues:
        if i["check"] != "break":
            continue
        var, y, ser = i["var"], i["year"], i["series"]
        key = (var, i["source"], ser)
        if (*key, y) in spikes or (*key, y - 1) in spikes:
            drop.append(i)       # consequence of a one-year outlier already reported as an error
            continue
        own = next(v for _, s_, se, v in by_var[var] if s_ == i["source"] and se == ser)
        chg = own[y] / own[y - 1] - 1
        is_ship = ser.startswith("отгружено")
        sib = []
        pool = by_var[var] + ([] if is_ship else [x for r_ in rel[var] for x in by_var.get(r_, [])])
        for v_, s_, se, v in pool:
            if (v_, s_, se) == key or not (y in v and y - 1 in v and v[y - 1] > 0 and v[y] > 0):
                continue
            if is_ship and se != "производство":
                continue
            if not is_ship and (se.startswith("отгружено") or se not in SIBLING_SER):
                continue
            lab = (v_ + ": " if v_ != var else "") + s_ + (" / " + se if se else "")
            sib.append((lab, v[y] / v[y - 1] - 1))
        conf = [x for x in sib if x[1] * chg > 0 and abs(x[1]) >= max(0.15, 0.5 * abs(chg))]
        flat = [x for x in sib if abs(x[1]) < 0.10]
        fmt = lambda xs: "; ".join(f"{l} {c:+.0%}" for l, c in xs[:3])
        if conf:
            cls, why = "подтверждён", fmt(conf)
        elif sib and len(flat) == len(sib):
            cls, why = "только этот ряд", fmt(sib)
        elif sib:
            cls, why = "частично", fmt(sib)
        else:
            cls, why = "один источник", "сравнить не с чем"
        ev = None
        if not is_ship and ser != "экспорт":
            ev = next((t for pref, yrs, d, t in EVENTS if var.startswith(pref) and y in yrs
                       and ((d == "up") == (chg > 0))), None)
        i["class"] = cls
        i["detail"] += f" | класс: {cls} ({why})" + (f" | гипотеза: {ev}" if ev else "")
    for i in drop:
        issues.remove(i)


def flags_index(issues: list[dict]) -> dict:
    """{(var, source, series, year): [check,...]} for the panel builder."""
    idx = defaultdict(list)
    for i in issues:
        if i["year"] is not None:
            idx[(i["var"], i["source"], i["series"], i["year"])].append(i["check"])
    return idx


def write_reports(issues: list[dict]) -> None:
    REPORTS.mkdir(exist_ok=True)
    summary = defaultdict(lambda: defaultdict(int))
    for i in issues:
        summary[i["severity"]][i["check"]] += 1
    (REPORTS / "resource_qa.json").write_text(json.dumps(
        {"generated": date.today().isoformat(), "summary": {k: dict(v) for k, v in summary.items()}, "issues": issues},
        ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Контроль качества: природные ресурсы ({date.today().isoformat()})", ""]
    for sev in ("error", "warning", "info"):
        lines.append(f"- **{sev}**: " + ", ".join(f"{k} {v}" for k, v in sorted(summary[sev].items())) if summary[sev] else f"- **{sev}**: 0")
    bc = defaultdict(int)
    for i in issues:
        if i["check"] == "break":
            bc[i.get("class", "?")] += 1
    if bc:
        lines += ["", "Скачки (break) по классам: " + ", ".join(f"{k} — {v}" for k, v in sorted(bc.items())),
                  "«подтверждён» — тот же скачок есть в другом источнике (вероятно реальная динамика); "
                  "«только этот ряд» — другие источники стабильны (вероятна смена учёта или ошибка); "
                  "«частично» — другие источники меняются слабее или разнонаправленно; «один источник» — проверить нечем."]
    for sev in ("error", "warning"):
        rows = [i for i in issues if i["severity"] == sev]
        if not rows:
            continue
        lines += ["", f"## {sev} ({len(rows)})", "", "| Проверка | Показатель | Источник / ряд | Год | Описание |", "|---|---|---|---|---|"]
        for i in sorted(rows, key=lambda r: (r["check"], r["var"], r["year"] or 0)):
            lines.append(f"| {i['check']} | {i['var']} | {i['source']} / {i['series']} | {i['year']} | {i['detail']} |")
    (REPORTS / "resource_qa.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    issues = run(load_long())
    write_reports(issues)
    n_err = sum(i["severity"] == "error" for i in issues)
    print(f"QA: {len(issues)} issues, {n_err} errors -> reports/resource_qa.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
