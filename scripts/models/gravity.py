"""Structural gravity for Kazakhstan's trade: PPML on a partner x year panel, 2000-2025.

    python scripts/models/gravity.py        # writes models/gravity/

Data (all already in the repository):
- flows: WITS (KZ as reporter) for 1995-2019, BNS for 2020 on. WITS is not used after
  2019 because its 2020-2022 imports are incomplete (22 bn USD against BNS's 39 bn in 2020;
  China 2.0 bn against 6.4 bn); from 2023 the two agree within about 1 %. Before 2020 WITS
  totals match the official BNS totals (2019: exports 58.1 vs 57.7 bn), except Russia and
  Belarus in 2010 (MISSING_FLOWS), which are left out rather than read as a collapse. A partner that has a
  GDP in WDI but no flow that year is a zero -- PPML keeps zeros, log-OLS cannot.
- partner GDP: WDI current USD (flows are current USD; year effects absorb the dollar
  price level and everything on Kazakhstan's side of the pair).
- bilateral costs: CEPII Gravity V202211 (distw_harmonic, contiguity, official language,
  WTO membership, EU, WTO-notified agreements), carried forward from 2021, and GeoDist for
  partners missing from Gravity.
- policy: any WTO-notified trade agreement (the CIS free-trade area and bilateral FTAs;
  EAEU members count as covered throughout), an explicit EAEU dummy on top of it -- the
  customs-union deepening beyond a free-trade area: Russia and Belarus from the 2010 customs
  union, Armenia from 2015, Kyrgyzstan from 2016 = first full year after the August 2015
  accession -- both-in-WTO (Kazakhstan a member from 2016), and for imports the
  applied tariff Kazakhstan charges the partner (WITS, trade-weighted, 2004-2023 with gaps).

Kazakhstan is the only reporter, so the panel is one-sided: year effects stand in for
Kazakhstan's own mass and multilateral resistance, but the partner's multilateral
resistance is not controlled for. That is the main reason the distance and GDP
elasticities are not the textbook structural ones; the partner-FE specification, which
identifies only from within-partner changes (EAEU, WTO, tariffs), is the robust one for
policy effects.

Specifications per flow (exports, imports):
  m1  PPML, year FE: ln GDP, ln distance, contiguity, Russian as an official language,
      former USSR, trade agreement, EAEU, both-in-WTO, EU.
  m1_ols  the same by OLS on ln(flow), zeros dropped (the log-linear benchmark).
  m2  PPML, partner FE + year FE: ln GDP, EAEU, both-in-WTO (the agreement dummy is
      constant within partner apart from CEPII coding changes, so it is left to the FE).
  m3  (imports) m2 plus ln(1 + tariff): the tariff coefficient is -(sigma - 1), the trade
      elasticity; sample limited to tariff years.
Standard errors are clustered by partner. Fit is the squared correlation of the flow and
its prediction (Santos Silva & Tenreyro 2006); the RESET check adds the squared linear
index to m1.

Trade potential: actual / m1-predicted flow, averaged over the last three years. A ratio
above one means more trade than a partner of that size and distance "should" have.
Kazakhstan's exports are two-thirds crude oil shipped through fixed pipelines (CPC to the
Black Sea, the Atasu-Alashankou line to China), so export ratios mostly map the pipelines'
destinations, not a trade-policy gap.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT = common.MODELS / "gravity"
FIRST_YEAR, LAST_YEAR = 2000, 2025
WITS_LAST_YEAR = 2019
CEPII_LAST_YEAR = 2021
KZ_WTO_YEAR = 2016
FORMER_USSR = ["ARM", "AZE", "BLR", "EST", "GEO", "KGZ", "LTU", "LVA", "MDA", "RUS", "TJK",
               "TKM", "UKR", "UZB"]
EAEU_FROM = {"RUS": 2010, "BLR": 2010, "ARM": 2015, "KGZ": 2016}
POTENTIAL_YEARS = 3
# WITS 2010: the customs union stopped customs declarations on Russian and Belarusian trade
# from July 2010, and the reporter file misses them (imports 24.0 bn USD against the official
# 31.1; Russia 23 % of imports against 36-43 % either side).
MISSING_FLOWS = {("RUS", 2010), ("BLR", 2010)}
FLOWS = {"exports": ("WITS_KZ_EXPORTS_BY_PARTNER", "KZ_EXPORTS_BY_PARTNER"),
         "imports": ("WITS_KZ_IMPORTS_BY_PARTNER", "KZ_IMPORTS_BY_PARTNER")}
LABELS = {
    "ln_gdp": "ln ВВП партнёра",
    "ln_dist": "ln расстояния",
    "contig": "Общая граница",
    "comlang_ru": "Русский — официальный язык",
    "ex_ussr": "Бывший СССР",
    "rta": "Торговое соглашение (ЗСТ СНГ и др.)",
    "eaeu": "ЕАЭС сверх ЗСТ",
    "wto_both": "Оба члены ВТО",
    "eu": "ЕС",
    "ln_tariff": "ln(1 + тариф РК)",
}
M1 = ["ln_gdp", "ln_dist", "contig", "comlang_ru", "ex_ussr", "rta", "eaeu", "wto_both", "eu"]
M2 = ["ln_gdp", "eaeu", "wto_both"]
NAMES = {
    "CHN": "Китай", "RUS": "Россия", "ITA": "Италия", "NLD": "Нидерланды", "UZB": "Узбекистан",
    "KGZ": "Кыргызстан", "TUR": "Турция", "FRA": "Франция", "DEU": "Германия", "KOR": "Корея",
    "USA": "США", "ESP": "Испания", "GRC": "Греция", "CHE": "Швейцария", "BLR": "Беларусь",
    "TJK": "Таджикистан", "AZE": "Азербайджан", "JPN": "Япония", "IND": "Индия", "IRN": "Иран",
    "GBR": "Великобритания", "POL": "Польша", "UKR": "Украина", "TKM": "Туркменистан",
    "ARE": "ОАЭ", "GEO": "Грузия", "ROU": "Румыния", "AUT": "Австрия", "PRT": "Португалия",
    "BEL": "Бельгия", "LTU": "Литва", "CZE": "Чехия", "HUN": "Венгрия", "ISR": "Израиль",
    "MYS": "Малайзия", "VNM": "Вьетнам", "SGP": "Сингапур", "THA": "Таиланд",
    "AFG": "Афганистан", "MNG": "Монголия", "ARM": "Армения", "CAN": "Канада",
    "BGR": "Болгария", "HRV": "Хорватия", "ROM": "Румыния",
}


# ---------------------------------------------------------------- panel
def year_of(date: pd.Series) -> pd.Series:
    return date.str[:4].astype(int)


def flows(dims: pd.DataFrame, wits_var: str, bns_var: str) -> pd.DataFrame:
    """Partner x year flow in thousand USD: WITS up to 2019, BNS from 2020."""
    d = dims[dims.variable.isin([wits_var, bns_var])].copy()
    d["year"] = year_of(d.date)
    keep = ((d.variable == wits_var) & (d.year <= WITS_LAST_YEAR)) | \
           ((d.variable == bns_var) & (d.year > WITS_LAST_YEAR))
    return (d[keep].groupby(["item_code", "year"], as_index=False).value.sum()
            .rename(columns={"item_code": "iso3", "value": "flow"}))


def build_panel(dims: pd.DataFrame, cepii: pd.DataFrame, geodist: pd.DataFrame) -> pd.DataFrame:
    gdp = dims[(dims.variable == "WDI_GDP_USD")].copy()
    gdp["year"] = year_of(gdp.date)
    gdp = gdp[(gdp.year >= FIRST_YEAR) & (gdp.year <= LAST_YEAR) & (gdp.item_code != "KAZ")
              & (gdp.value > 0)]
    panel = gdp[["item_code", "year", "value"]].rename(columns={"item_code": "iso3", "value": "gdp"})
    panel = panel[panel.iso3.isin(set(geodist.iso3) | set(cepii.iso3))]

    for name, (wits_var, bns_var) in FLOWS.items():
        f = flows(dims, wits_var, bns_var).rename(columns={"flow": name})
        panel = panel.merge(f, on=["iso3", "year"], how="left")
        panel[name] = panel[name].fillna(0.0) / 1e3  # million USD; absent = zero flow
        gap = [(c, y) in MISSING_FLOWS for c, y in zip(panel.iso3, panel.year)]
        panel.loc[gap, name] = np.nan

    tv = cepii.copy()
    tv["cyear"] = tv.year
    panel["cyear"] = panel.year.clip(upper=CEPII_LAST_YEAR)
    panel = panel.merge(tv[["iso3", "cyear", "fta_wto", "wto_d", "eu_d"]], on=["iso3", "cyear"], how="left")
    dist = cepii.groupby("iso3").distw_harmonic.mean()
    geo = geodist.set_index("iso3")
    panel["dist"] = panel.iso3.map(dist).fillna(panel.iso3.map(geo.distw))
    panel["contig"] = panel.iso3.map(geo.contig).fillna(0)
    panel["comlang_ru"] = panel.iso3.map(geo.comlang_off).fillna(0)
    panel = panel.dropna(subset=["dist"])

    panel["ln_gdp"] = np.log(panel.gdp)
    panel["ln_dist"] = np.log(panel.dist)
    panel["ex_ussr"] = panel.iso3.isin(FORMER_USSR).astype(float)
    panel["eaeu"] = [float(y >= EAEU_FROM.get(c, 9999)) for c, y in zip(panel.iso3, panel.year)]
    panel["rta"] = ((panel.fta_wto.fillna(0) > 0) | (panel.eaeu > 0)).astype(float)
    panel["wto_both"] = ((panel.wto_d.fillna(0) > 0) & (panel.year >= KZ_WTO_YEAR)).astype(float)
    panel["eu"] = panel.eu_d.fillna(0)

    tar = dims[(dims.variable == "KZ_TARIFF_APPLIED_BY_PARTNER")].copy()
    tar["year"] = year_of(tar.date)
    tar = tar.groupby(["item_code", "year"], as_index=False).value.mean()
    panel = panel.merge(tar.rename(columns={"item_code": "iso3", "value": "tariff"}), on=["iso3", "year"],
                        how="left")
    panel["ln_tariff"] = np.log1p(panel.tariff / 100.0)
    cols = ["iso3", "year", "exports", "imports", "gdp", "dist", "tariff"] + \
           ["ln_gdp", "ln_dist", "contig", "comlang_ru", "ex_ussr", "rta", "eaeu", "wto_both", "eu", "ln_tariff"]
    return panel[cols].sort_values(["iso3", "year"]).reset_index(drop=True)


# ---------------------------------------------------------------- estimation
def design(df: pd.DataFrame, regressors: list[str], partner_fe: bool) -> pd.DataFrame:
    X = df[regressors].astype(float).copy()
    X = X.join(pd.get_dummies(df.year, prefix="y", drop_first=True, dtype=float))
    if partner_fe:
        X = X.join(pd.get_dummies(df.iso3, prefix="p", drop_first=True, dtype=float))
    return sm.add_constant(X, has_constant="add")


def ppml(df: pd.DataFrame, y: str, regressors: list[str], partner_fe: bool = False):
    d = df.dropna(subset=regressors + [y]).copy()
    if partner_fe:  # partners that never trade are perfectly predicted by their dummy
        d = d[d.groupby("iso3")[y].transform("sum") > 0]
    X = design(d, regressors, partner_fe)
    res = sm.GLM(d[y], X, family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d.iso3)[0]}, maxiter=200)
    return res, d, X


def ols_log(df: pd.DataFrame, y: str, regressors: list[str]):
    d = df.dropna(subset=regressors + [y])
    d = d[d[y] > 0]
    X = design(d, regressors, False)
    res = sm.OLS(np.log(d[y]), X).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.iso3)[0]})
    return res, d


def pseudo_r2(y: pd.Series, mu: pd.Series) -> float:
    return float(np.corrcoef(y, mu)[0, 1] ** 2)


def reset_p(df: pd.DataFrame, y: str, regressors: list[str], res) -> float:
    d = df.dropna(subset=regressors + [y]).copy()
    d["xb2"] = np.log(res.fittedvalues.loc[d.index]) ** 2
    r2, _, _ = ppml(d, y, regressors + ["xb2"])
    return float(r2.pvalues["xb2"])


def coef_rows(res, model: str, flow: str, regressors: list[str], n: int, fit: float) -> list[dict]:
    rows = []
    for r in regressors:
        b, se, p = res.params[r], res.bse[r], res.pvalues[r]
        rows.append({"flow": flow, "model": model, "variable": r, "coef": b, "se": se, "p": p,
                     "effect_pct": (np.exp(b) - 1) * 100 if r not in ("ln_gdp", "ln_dist", "ln_tariff") else np.nan,
                     "n": n, "fit": fit})
    return rows


def estimate(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows, fitted = [], {}
    for flow in FLOWS:
        r1, d1, _ = ppml(panel, flow, M1)
        fit1 = pseudo_r2(d1[flow], r1.fittedvalues)
        rows += coef_rows(r1, "m1", flow, M1, len(d1), fit1)
        rows[-1]["reset_p"] = reset_p(panel, flow, M1, r1)
        fitted[flow] = d1.assign(predicted=r1.fittedvalues)
        ro, do = ols_log(panel, flow, M1)
        rows += coef_rows(ro, "m1_ols", flow, M1, len(do), ro.rsquared)
        r2, d2, _ = ppml(panel, flow, M2, partner_fe=True)
        rows += coef_rows(r2, "m2", flow, M2, len(d2), pseudo_r2(d2[flow], r2.fittedvalues))
        if flow == "imports":
            m3 = M2 + ["ln_tariff"]
            r3, d3, _ = ppml(panel, flow, m3, partner_fe=True)
            rows += coef_rows(r3, "m3", flow, m3, len(d3), pseudo_r2(d3[flow], r3.fittedvalues))
    return pd.DataFrame(rows), fitted


def potential(fitted: dict, last_year: int) -> pd.DataFrame:
    years = range(last_year - POTENTIAL_YEARS + 1, last_year + 1)
    out = []
    for flow, d in fitted.items():
        g = d[d.year.isin(years)].groupby("iso3")[[flow, "predicted"]].mean()
        g = g.rename(columns={flow: "actual"})
        g["flow"] = flow
        g["ratio"] = g.actual / g.predicted
        out.append(g.reset_index())
    p = pd.concat(out, ignore_index=True)
    p["name"] = p.iso3.map(NAMES).fillna(p.iso3)
    return p[["flow", "iso3", "name", "actual", "predicted", "ratio"]]


# ---------------------------------------------------------------- outputs
def chart_potential(pot: pd.DataFrame, path: Path, n: int = 15) -> None:
    import matplotlib.pyplot as plt  # noqa: F401

    total = pot.groupby("iso3").actual.sum().sort_values(ascending=False)
    top = list(total.index[:n])
    fig, ax = common.figure(8.2, 6.4)
    ys = np.arange(len(top))[::-1]
    for i, (flow, label) in enumerate([("exports", "Экспорт"), ("imports", "Импорт")]):
        s = pot[pot.flow == flow].set_index("iso3").reindex(top)
        ax.scatter(s.ratio, ys + (0.16 if i == 0 else -0.16), s=46, color=common.SERIES[i],
                   edgecolor=common.SURFACE, linewidth=1.5, zorder=3, label=label)
    ax.axvline(1, color=common.BASELINE, linewidth=1)
    ax.set_xscale("log")
    ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 4, 10])
    ax.set_xticklabels(["0,1", "0,25", "0,5", "1", "2", "4", "10"])
    ax.set_yticks(ys)
    ax.set_yticklabels([NAMES.get(c, c) for c in top])
    ax.grid(True, axis="x", color=common.GRID, linewidth=0.6)
    ax.grid(False, axis="y")
    ax.set_xlabel("факт / прогноз модели (лог. шкала); 1 = торгует «как положено»", color=common.INK_2, fontsize=9)
    common.title(ax, "Торговый потенциал: 15 крупнейших партнёров",
                 f"PPML m1, средние {pot.attrs.get('years', '')}; справа от 1 — торговли больше, чем предсказывает гравитация")
    common.legend(ax, loc="lower right")
    common.save(fig, path)


def chart_eaeu(panel: pd.DataFrame, path: Path) -> None:
    """Share of the EAEU partners in Kazakhstan's exports and imports -- the raw fact behind
    the EAEU coefficient."""
    members = list(EAEU_FROM)
    g = panel.assign(member=panel.iso3.isin(members))
    share = g.groupby(["year", "member"])[["exports", "imports"]].sum(min_count=1).unstack("member")
    incomplete = g[g.member].groupby("year")[["exports", "imports"]].apply(lambda x: x.isna().any())
    for flow in ("exports", "imports"):
        share.loc[incomplete[flow], flow] = np.nan
    fig, ax = common.figure(8, 4)
    for i, (flow, label) in enumerate([("exports", "Экспорт"), ("imports", "Импорт")]):
        s = share[flow][True] / share[flow].sum(axis=1) * 100
        ax.plot(s.index, s.values, color=common.SERIES[i], linewidth=2, label=label)
        ax.annotate(f"{label} {s.iloc[-1]:.0f} %", (s.index[-1], s.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", fontsize=9, color=common.INK_2, va="center")
    ax.set_ylim(0, 55)
    for year, label in ((2010, "ТС"), (2015, "ЕАЭС")):
        ax.axvline(year, color=common.BASELINE, linestyle="--", linewidth=1)
        ax.text(year + 0.2, 53, label, fontsize=8.5, color=common.INK_2, va="top")
    ax.set_ylabel("% от итога", color=common.INK_2, fontsize=9)
    ax.set_xlim(panel.year.min(), panel.year.max() + 3)
    common.title(ax, "Доля ЕАЭС в торговле Казахстана",
                 "Россия, Беларусь, Армения, Кыргызстан; WITS до 2019, БНС с 2020; 2010 — пропуск в WITS")
    common.legend(ax, loc="lower left", ncol=2)
    common.save(fig, path)


def report(panel: pd.DataFrame, coefs: pd.DataFrame, pot: pd.DataFrame) -> str:
    def cell(flow, model, var):
        r = coefs[(coefs.flow == flow) & (coefs.model == model) & (coefs.variable == var)]
        if r.empty:
            return ""
        r = r.iloc[0]
        stars = "***" if r.p < 0.01 else "**" if r.p < 0.05 else "*" if r.p < 0.1 else ""
        return f"{r.coef:.2f}{stars} ({r.se:.2f})"

    models = [("exports", "m1"), ("exports", "m1_ols"), ("exports", "m2"),
              ("imports", "m1"), ("imports", "m1_ols"), ("imports", "m2"), ("imports", "m3")]
    head = ["Переменная", "Эксп. PPML", "Эксп. OLS", "Эксп. PPML+FE", "Имп. PPML", "Имп. OLS",
            "Имп. PPML+FE", "Имп. +тариф"]
    rows = []
    for var in M1 + ["ln_tariff"]:
        rows.append([LABELS[var]] + [cell(f, m, var) for f, m in models])
    meta = coefs.groupby(["flow", "model"]).agg(n=("n", "first"), fit=("fit", "first"))
    rows.append(["Наблюдений"] + [str(int(meta.loc[(f, m), "n"])) for f, m in models])
    rows.append(["Fit (корр.² / R²)"] + [f"{meta.loc[(f, m), 'fit']:.2f}" for f, m in models])
    table = common.md_table(pd.DataFrame(rows, columns=head))

    def eff(flow, model, var):
        r = coefs[(coefs.flow == flow) & (coefs.model == model) & (coefs.variable == var)].iloc[0]
        return r

    ee, ei = eff("exports", "m2", "eaeu"), eff("imports", "m2", "eaeu")
    tar = eff("imports", "m3", "ln_tariff")
    e_gdp, e_dist = eff("exports", "m1", "ln_gdp").coef, eff("exports", "m1", "ln_dist").coef
    i_gdp, i_dist = eff("imports", "m1", "ln_gdp").coef, eff("imports", "m1", "ln_dist").coef

    def ci(r):
        lo, hi = ((np.exp(r.coef + k * 1.96 * r.se) - 1) * 100 for k in (-1, 1))
        return f"{lo:+.0f}…{hi:+.0f} %"
    reset = coefs[coefs.reset_p.notna()] if "reset_p" in coefs else pd.DataFrame()
    reset_txt = ", ".join(f"{'экспорт' if r.flow == 'exports' else 'импорт'} p = {r.reset_p:.2f}"
                          for r in reset.itertuples()) if len(reset) else "—"
    years = pot.attrs.get("years", "")

    top = pot.groupby("iso3").actual.sum().sort_values(ascending=False).index[:15]
    pt = pot[pot.iso3.isin(top)].pivot_table(index=["iso3", "name"], columns="flow",
                                              values=["actual", "ratio"]).reset_index()
    pt.columns = ["iso3", "name", "act_e", "act_i", "r_e", "r_i"]
    pt = pt.set_index("iso3").loc[top].reset_index()
    ptab = common.md_table(pd.DataFrame({
        "Партнёр": pt.name, "Экспорт, млн $": pt.act_e.map(lambda v: common.fmt(v, 0)),
        "факт/модель": pt.r_e.map(lambda v: common.fmt(v, 2)),
        "Импорт, млн $": pt.act_i.map(lambda v: common.fmt(v, 0)),
        "факт/модель ": pt.r_i.map(lambda v: common.fmt(v, 2))}))

    n_partners = panel.iso3.nunique()
    zeros_e = (panel.exports == 0).mean() * 100
    zeros_i = (panel.imports == 0).mean() * 100
    return f"""# Гравитационная модель торговли Казахстана (PPML)

Производный результат, не официальная статистика. Скрипт: `scripts/models/gravity.py`;
данные: `panel.csv` (панель), `coefficients.csv` (все оценки), `potential.csv` (потенциал).

## Данные

- Панель: {n_partners} стран-партнёров × {panel.year.min()}–{panel.year.max()} ({len(panel)} наблюдений).
  Нулевые потоки сохранены: {zeros_e:.0f} % наблюдений по экспорту и {zeros_i:.0f} % по импорту.
- Потоки, тыс. → млн долл. США: WITS (Казахстан-репортёр) до 2019 г., БНС с 2020 г. WITS за
  2020–2022 не используется: импорт там неполный (2020 г.: 22 млрд $ против 39 млрд $ у БНС,
  Китай 2,0 против 6,4 млрд $); с 2023 г. источники совпадают до ~1 %. До 2020 г. итоги WITS
  совпадают с официальными (2019 г., экспорт: 58,1 против 57,7 млрд $).
- ВВП партнёра: WDI, текущие долл. США. Расстояние: CEPII `distw_harmonic` (взвешенное по
  населению). Граница, язык, ВТО, ЕС, соглашения: CEPII Gravity V202211 (после 2021 г. значения
  2021 г.). ЕАЭС задан явно: Россия и Беларусь с 2010 г. (Таможенный союз), Армения с 2015 г.,
  Кыргызстан с 2016 г. Тариф: применяемый Казахстаном средневзвешенный тариф к партнёру (WITS).

## Спецификации

- **PPML** (Santos Silva & Tenreyro 2006): Пуассон-ПМП на уровнях, нули не выбрасываются,
  устойчив к гетероскедастичности, из-за которой лог-линейный МНК смещён.
- **m1**: фиксированные эффекты года + ВВП партнёра и двусторонние издержки. Эффекты года
  поглощают всё со стороны Казахстана (ВВП, цены, курс, собственное многостороннее
  сопротивление).
- **m1 OLS**: то же на ln(поток) без нулей — эталон, показывающий смещение лог-линейной модели.
- **m2**: эффекты партнёра + года. Идентификация только по изменениям внутри партнёра (вход в
  ЕАЭС, ВТО, рост ВВП партнёра). Это основная спецификация для оценки политики. Дамми
  соглашения в m2 нет: внутри партнёра она не меняется (кроме перекодировок CEPII).
- **m3** (импорт): m2 + ln(1 + тариф). Коэффициент = −(σ − 1), торговая эластичность.
- Стандартные ошибки кластеризованы по партнёру; *** p<0,01, ** p<0,05, * p<0,1.

## Оценки

{table}

Эффекты дамми в процентах = exp(β) − 1. Главное:

- **ЕАЭС сверх ЗСТ СНГ (m2, внутри партнёра):** экспорт {ee.effect_pct:+.0f} %
  (95 % ДИ {ci(ee)}), импорт {ei.effect_pct:+.0f} % (95 % ДИ {ci(ei)}). Таможенный союз и ЕАЭС
  не добавили торговли сверх того, что уже давали зона свободной торговли СНГ, ВВП партнёров и
  общие для года шоки: коэффициенты незначимы. Это согласуется с долей ЕАЭС в импорте:
  37–41 % в 2002–2008 гг. и 36–45 % в 2011–2022 гг. (см. график). Идентификация — по четырём странам, где
  доминирует Россия; 2010 г. для России и Беларуси исключён (разрыв в данных WITS).
- **Тариф (m3):** β = {tar.coef:.2f} (s.e. {tar.se:.2f}, p = {tar.p:.2f}) — торговая
  эластичность **не идентифицирована**, знак не тот, что предсказывает теория (σ − 1 ≈ 4–6,
  Head & Mayer 2014). Причина в данных: при эффектах года тариф РНБ, общий для всех партнёров
  без преференций, поглощается; остающаяся разница между партнёрами в средневзвешенном тарифе —
  это состав импорта (в каких товарах партнёр специализирован), а не политика. Преференции
  (нулевой тариф ЕАЭС/СНГ) уже учтены дамми. Для σ нужны тарифы и потоки на уровне HS-6.
- **ВВП и расстояние (m1):** эластичности (экспорт {e_gdp:.2f} и {e_dist:.2f}, импорт {i_gdp:.2f}
  и {i_dist:.2f}) близки к «каноническим» 1 и −1 лишь отчасти. Это ожидаемо для
  одностороннего набора: многостороннее сопротивление партнёров не контролируется, а экспорт —
  в основном нефть, идущая по трубопроводам в конкретные страны независимо от их размера.
- **PPML против OLS:** OLS даёт другие коэффициенты при расстоянии и ВВП — это смещение
  из-за гетероскедастичности и потерянных нулей, ради устранения которого нужен PPML.
- **RESET** (квадрат линейного индекса в m1): {reset_txt}. Малое p — функциональная форма
  m1 неполна (ожидаемо без эффектов партнёра); для политики используйте m2/m3.

## Торговый потенциал ({years}, m1)

Факт / прогноз модели для 15 крупнейших партнёров. Выше 1 — торговли больше, чем «положено»
по размеру и расстоянию; ниже 1 — недоиспользованный потенциал (или барьер, не учтённый в модели).

{ptab}

![Торговый потенциал](potential.png)

Чтение: экспорт в Италию, Нидерланды и другие страны Европы выше модели из-за нефти (КТК,
танкеры из Новороссийска), а не из-за торговой политики. Для диагностики несырьевого экспорта
нужна модель на товарных группах (HS), которой в репозитории пока нет.

![Доля ЕАЭС](eaeu_share.png)

## Ограничения

1. Один репортёр: нет многостороннего сопротивления партнёров, поэтому m1 — описательная
   модель, а не структурная (для структурной нужны потоки всех пар стран, например BACI).
2. Экспорт на две трети — нефть и газ; гравитация плохо описывает трубопроводную торговлю.
3. Разрыв источников в 2019/2020 (WITS → БНС) поглощается эффектами года только если он
   одинаков для всех партнёров; сверка 2023 г. (расхождение <1 %) это подтверждает для
   крупных партнёров.
4. Тариф — средневзвешенный, эндогенный; эластичность — нижняя граница.
5. Реэкспорт и «параллельный импорт» после 2022 г. (Россия) не выделяются.
"""


def main() -> None:
    dims = common.load_dims(["WDI_GDP_USD", "KZ_TARIFF_APPLIED_BY_PARTNER"]
                            + [v for pair in FLOWS.values() for v in pair])
    cepii = pd.read_csv(common.REFERENCE / "cepii_gravity_kaz.csv")
    geodist = pd.read_csv(common.REFERENCE / "cepii_geodist_kaz.csv")
    panel = build_panel(dims, cepii, geodist)
    coefs, fitted = estimate(panel)
    last = int(panel.year.max())
    pot = potential(fitted, last)
    pot.attrs["years"] = f"{last - POTENTIAL_YEARS + 1}–{last}"
    OUT.mkdir(parents=True, exist_ok=True)
    panel.to_csv(OUT / "panel.csv", index=False, float_format="%.6g")
    coefs.to_csv(OUT / "coefficients.csv", index=False, float_format="%.6g")
    pot.sort_values(["flow", "actual"], ascending=[True, False]).to_csv(
        OUT / "potential.csv", index=False, float_format="%.6g")
    chart_potential(pot, OUT / "potential.png")
    chart_eaeu(panel, OUT / "eaeu_share.png")
    (OUT / "REPORT.md").write_text(report(panel, coefs, pot), encoding="utf-8")
    print(coefs[coefs.model.isin(["m1", "m2", "m3"])][["flow", "model", "variable", "coef", "se", "p"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
