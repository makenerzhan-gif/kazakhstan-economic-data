"""Analytical indicators DERIVED BY THIS REPOSITORY from series the pipeline already holds
(added 2026-11-10). Nothing here is published by a source; every dataset says how it is
computed, and the inputs are the processed files of the same run (data/processed/), so the
datasets must stay after their inputs in config/dims.yaml.

Datasets (config/dims.yaml, `fetcher: analytics`, `measure:`):

core_inflation      Alternative core inflation measures from the CPI components: the 2022
    official BNS weights (CPI_WEIGHTS, the only year with a full public scheme; held fixed --
    BNS reweights every January, so the measures are approximations) over 21 components: nine
    food groups, non-alcoholic drinks, alcohol, tobacco and the eleven non-food divisions. Per
    month, from the components' m/m indices (CPI_DETAIL_MOM, the national rows; a food or
    drink group a release does not print -- the 2026 basket, September 2026 -- takes the change
    of its division, CP01 or CP02, and N_FILLED_BY_DIVISION counts them):
      TRIMMED_MEAN_15 / TRIMMED_MEAN_30  weighted mean of the central 70 % / 40 % of the weight,
                                         the m/m changes sorted (Bryan-Cecchetti style);
      WEIGHTED_MEDIAN                    the change at 50 % of the cumulative weight;
      COMPONENTS_MEAN                    the plain weighted mean of the components (a check
                                         against the published CPI: correlation in the note);
      DIFFUSION_RISING / _ABOVE_TARGET   weight share of components rising, and rising faster
                                         than 5 % a year (0.4074 % a month), %.
    .MOM is the monthly change, %; .YOY the 12-month compounded change, %.
monetary_conditions Real interest rates and a monetary conditions index, monthly:
      BASE_RATE (monthly mean of the step function), TONIA (monthly mean), CPI_YOY (%),
      EXPECTED_INFLATION (household survey median, INFLATION_EXPECTATIONS);
      REAL_BASE_EX_ANTE = (1+i)/(1+pi_e)-1, REAL_BASE_EX_POST = (1+i)/(1+pi)-1, REAL_TONIA_EX_ANTE;
      MCI = (real ex-ante rate - its mean since 2016) + W * 100*ln(REER / its mean since 2016),
      W = 1/3 (the 3:1 rule of thumb for small open economies; a rise = tighter).
output_gap          Quarterly output gap, % of potential, by four methods on log real GDP
    (QNA_GDP_EXPENDITURE_SA_CONSTANT_2010, seasonally adjusted, 2010 prices, from 2010 Q1):
      HP (two-sided Hodrick-Prescott, lambda 1600), HP_ONESIDED (the last point of HP filters
      run on the sample to each quarter -- what was knowable then), HAMILTON (Hamilton 2018:
      y(t+8) regressed on y(t)..y(t-3), the residual), UC (unobserved components: local linear
      trend + AR(2) cycle, Kalman-smoothed), and MEAN of the four. POTENTIAL_GROWTH_HP: q/q
      annualised growth of the HP trend, %.
credit              Quarterly credit indicators: CREDIT_TO_GDP (bank loans at the end of the
    quarter, BANK_LOANS_STB_TOTAL, over the sum of four quarters of nominal GDP, QNA, %),
      CREDIT_GAP (Basel III: deviation from a one-sided HP trend, lambda 400 000, pp),
      CREDIT_IMPULSE (change in the four-quarter credit flow over four-quarter GDP, pp;
      Biggs-Mayer-Pick), CREDIT_GROWTH_REAL (y/y growth deflated by CPI, %).
fiscal              Annual fiscal stance: NON_OIL_GDP (GDP less the oil-gas sector's GVA,
      OIL_GAS_SECTOR_GVA, bn KZT), OIL_SHARE_GDP (%), NON_OIL_BALANCE_PCT (state budget non-oil
      balance, STATE_NON_OIL_DEFICIT, % of non-oil GDP; negative = deficit), FISCAL_IMPULSE
      (-change in that ratio, pp: positive = expansionary), OVERALL_BALANCE_PCT (state budget
      balance, STATE_BUDGET_DEFICIT, % of GDP). Not cyclically adjusted (no published
      elasticities); the non-oil balance is not primary (interest on the state budget is
      quarterly only from 2019, GG_INTEREST).
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import dims, validation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"


def _structural(ds: dict, what: str) -> None:
    raise validation.StructuralChangeError(f"derived/{ds['id']}: {what}")


def scalar(agency: str, indicator_id: str) -> pd.Series:
    path = PROCESSED / agency / f"{indicator_id.lower()}.csv"
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    s = pd.Series({pd.Timestamp(r["date"]): float(r["value"]) for r in rows if r.get("value") not in (None, "")})
    return s.sort_index()


def dimser(dataset: str, item: str, region: str = dims.NATIONAL) -> pd.Series:
    rows = dims.load_processed(dataset)
    s = pd.Series({pd.Timestamp(r["date"]): float(r["value"]) for r in rows
                   if r["item_code"] == item and (r.get("region") or dims.NATIONAL) == region and r.get("value") not in (None, "")})
    return s.sort_index()


def _records(series: dict[str, pd.Series], names: dict[str, str], ndigits: int = 4) -> list[dict]:
    out = []
    for code, s in series.items():
        for d, v in s.dropna().items():
            if np.isfinite(v):
                out.append({"date": d.strftime("%Y-%m-%d"), "region": dims.NATIONAL, "item_code": code,
                            "item_name": names[code], "value": round(float(v), ndigits)})
    return out


# ---------------------------------------------------------------- core inflation

CORE_COMPONENTS = {  # weight code in CPI_WEIGHTS 2022: CPI_DETAIL_MOM item codes, first available wins
    "CP011_bread": ["khlebobulochnye_izdeliya_i_krupy", "khleboprodukty_i_krupyanye_izdeliya", "krupy_i_zernovye_produkty"],
    "CP011_meat": ["myaso_vklyuchaya_myasoprodukty", "myaso_i_myasoprodukty", "myaso"],
    "CP011_fish": ["ryba_i_moreprodukty"],
    "CP011_milk": ["molochnye_produkty", "moloko_i_molokoprodukty", "moloko_syr_i_yaytsa", "moloko"],
    "CP011_eggs": ["yaytsa"],
    "CP011_oils": ["masla_i_zhiry"],
    "CP011_fruitveg": ["frukty_i_ovoshchi"],
    "CP011_sugar": ["sakhar_dzhem_med_shokolad_konditerskie_izdeliya", "sakhar_dzhem_med_shokolad_i_konditerskie_izdeliya", "sakhar_i_konditerskie_izdeliya"],
    "CP012": ["bezalkogolnye_napitki"], "CP021": ["alkogolnye_napitki"], "CP022": ["tabachnye_izdeliya"],
    "CP03": ["CP03"], "CP04": ["CP04"], "CP05": ["CP05"], "CP06": ["CP06"], "CP07": ["CP07"], "CP08": ["CP08"],
    "CP09": ["CP09"], "CP10": ["CP10"], "CP11": ["CP11"], "CP12": ["CP12", "CP13_2018"],
}
PARENT = {c: "CP01" for c in CORE_COMPONENTS if c.startswith("CP01")} | {"CP021": "CP02", "CP022": "CP02"}
TARGET_MONTHLY = (1.05 ** (1 / 12) - 1) * 100       # 0.4074 % a month = 5 % a year
MIN_COMPONENTS = 18


def weighted_quantile_mean(changes: np.ndarray, weights: np.ndarray, lo: float, hi: float) -> float:
    """Weighted mean of the changes between cumulative weight shares lo and hi (partial weights
    at the cut points); lo = hi gives the weighted quantile."""
    order = np.argsort(changes, kind="mergesort")
    x, w = changes[order], weights[order] / weights.sum()
    cum_hi = np.cumsum(w)
    cum_lo = cum_hi - w
    if hi <= lo:
        i = int(np.searchsorted(cum_hi, lo, side="left"))
        return float(x[min(i, len(x) - 1)])
    keep = np.clip(np.minimum(cum_hi, hi) - np.maximum(cum_lo, lo), 0, None)
    return float((x * keep).sum() / keep.sum())


def core_inflation(ds: dict) -> list[dict]:
    weights = {r["item_code"]: float(r["value"]) for r in dims.load_processed("CPI_WEIGHTS") if r["date"] == "2022-12-31"}
    missing = set(CORE_COMPONENTS) - set(weights)
    if missing:
        _structural(ds, f"CPI_WEIGHTS 2022 lacks {sorted(missing)}")
    detail: dict[str, dict[pd.Timestamp, float]] = {}
    wanted = {c for codes in CORE_COMPONENTS.values() for c in codes} | set(PARENT.values())
    for r in dims.load_processed("CPI_DETAIL_MOM"):
        if r["item_code"] in wanted and (r.get("region") or dims.NATIONAL) == dims.NATIONAL and r.get("value") not in (None, ""):
            detail.setdefault(r["item_code"], {})[pd.Timestamp(r["date"])] = float(r["value"]) - 100
    months = sorted({d for s in detail.values() for d in s})
    rows = {}
    for d in months:
        ch, w, filled = [], [], 0
        for comp, codes in CORE_COMPONENTS.items():
            v = next((detail[c][d] for c in codes if c in detail and d in detail[c]), None)
            if v is None and comp in PARENT and d in detail.get(PARENT[comp], {}):
                v, filled = detail[PARENT[comp]][d], filled + 1     # the division's change stands in
            if v is not None:
                ch.append(v)
                w.append(weights[comp])
        if len(ch) < MIN_COMPONENTS:
            continue
        x, wt = np.array(ch), np.array(w)
        share = wt / wt.sum()
        rows[d] = {"TRIMMED_MEAN_15.MOM": weighted_quantile_mean(x, wt, 0.15, 0.85),
                   "TRIMMED_MEAN_30.MOM": weighted_quantile_mean(x, wt, 0.30, 0.70),
                   "WEIGHTED_MEDIAN.MOM": weighted_quantile_mean(x, wt, 0.5, 0.5),
                   "COMPONENTS_MEAN.MOM": float((x * share).sum()),
                   "DIFFUSION_RISING": float(share[x > 0].sum() * 100),
                   "DIFFUSION_ABOVE_TARGET": float(share[x > TARGET_MONTHLY].sum() * 100),
                   "N_COMPONENTS": float(len(x)), "N_FILLED_BY_DIVISION": float(filled)}
    df = pd.DataFrame(rows).T.sort_index()
    if df.empty or len(df) < 60:
        _structural(ds, f"only {len(df)} months with at least {MIN_COMPONENTS} of the {len(CORE_COMPONENTS)} components")
    idx = pd.date_range(df.index.min(), df.index.max(), freq="MS")
    df = df.reindex(idx)
    for m in ("TRIMMED_MEAN_15", "TRIMMED_MEAN_30", "WEIGHTED_MEDIAN", "COMPONENTS_MEAN"):
        growth = 1 + df[f"{m}.MOM"] / 100
        df[f"{m}.YOY"] = (growth.rolling(12, min_periods=12).apply(np.prod, raw=True) - 1) * 100
    names = {"TRIMMED_MEAN_15.MOM": "Усечённое среднее (15 % с каждого хвоста), м/м, %", "TRIMMED_MEAN_15.YOY": "Усечённое среднее (15 %), за 12 месяцев, %",
             "TRIMMED_MEAN_30.MOM": "Усечённое среднее (30 % с каждого хвоста), м/м, %", "TRIMMED_MEAN_30.YOY": "Усечённое среднее (30 %), за 12 месяцев, %",
             "WEIGHTED_MEDIAN.MOM": "Взвешенная медиана, м/м, %", "WEIGHTED_MEDIAN.YOY": "Взвешенная медиана, за 12 месяцев, %",
             "COMPONENTS_MEAN.MOM": "Средневзвешенное по 21 компоненте (проверка против ИПЦ), м/м, %",
             "COMPONENTS_MEAN.YOY": "Средневзвешенное по 21 компоненте, за 12 месяцев, %",
             "DIFFUSION_RISING": "Индекс диффузии: доля веса компонент с ростом цен, %",
             "DIFFUSION_ABOVE_TARGET": "Индекс диффузии: доля веса компонент с ростом быстрее 5 % годовых, %",
             "N_COMPONENTS": "Число компонент в расчёте",
             "N_FILLED_BY_DIVISION": "Число компонент, заменённых изменением цен своего раздела (01 или 02)"}
    return _records({c: df[c] for c in names}, names)


# ---------------------------------------------------------------- monetary conditions

MCI_REER_WEIGHT = 1 / 3
MCI_BASE_FROM = "2016-01-01"


def monthly_step_mean(events: pd.Series, end: pd.Timestamp) -> pd.Series:
    """Monthly mean of a step function given by its change dates (the base rate)."""
    daily = events.reindex(pd.date_range(events.index.min(), end, freq="D")).ffill()
    return daily.resample("MS").mean()


def monetary_conditions(ds: dict) -> list[dict]:
    cpi_yoy = scalar("bns", "CPI_YOY") - 100
    end = max(cpi_yoy.index.max(), pd.Timestamp.today().normalize().replace(day=1)) + pd.offsets.MonthEnd(0)
    base = monthly_step_mean(scalar("nbk", "BASE_RATE"), end)
    tonia = scalar("kase", "TONIA").resample("MS").mean()
    expected = scalar("nbk", "INFLATION_EXPECTATIONS")
    reer = scalar("nbk", "REER")
    df = pd.DataFrame({"BASE_RATE": base, "TONIA": tonia, "CPI_YOY": cpi_yoy, "EXPECTED_INFLATION": expected, "REER": reer})
    df = df[df.index >= "2015-09-01"]
    df["REAL_BASE_EX_ANTE"] = ((1 + df.BASE_RATE / 100) / (1 + df.EXPECTED_INFLATION / 100) - 1) * 100
    df["REAL_BASE_EX_POST"] = ((1 + df.BASE_RATE / 100) / (1 + df.CPI_YOY / 100) - 1) * 100
    df["REAL_TONIA_EX_ANTE"] = ((1 + df.TONIA / 100) / (1 + df.EXPECTED_INFLATION / 100) - 1) * 100
    base_period = df.index >= MCI_BASE_FROM
    r_gap = df.REAL_BASE_EX_ANTE - df.loc[base_period, "REAL_BASE_EX_ANTE"].mean()
    e_gap = 100 * np.log(df.REER / df.loc[base_period, "REER"].mean())
    df["MCI"] = r_gap + MCI_REER_WEIGHT * e_gap
    df["MCI_RATE_PART"] = r_gap
    df["MCI_REER_PART"] = MCI_REER_WEIGHT * e_gap
    names = {"BASE_RATE": "Базовая ставка, среднее за месяц, %", "TONIA": "TONIA, среднее за месяц, %",
             "CPI_YOY": "Инфляция за 12 месяцев, %", "EXPECTED_INFLATION": "Ожидаемая населением инфляция на 12 месяцев (медиана), %",
             "REAL_BASE_EX_ANTE": "Реальная базовая ставка ex ante (по ожиданиям населения), %",
             "REAL_BASE_EX_POST": "Реальная базовая ставка ex post (по фактической инфляции за 12 месяцев), %",
             "REAL_TONIA_EX_ANTE": "Реальная TONIA ex ante, %",
             "MCI": "Индекс денежно-кредитных условий (рост = ужесточение), п.п.",
             "MCI_RATE_PART": "Индекс ДКУ: вклад реальной ставки, п.п.", "MCI_REER_PART": "Индекс ДКУ: вклад реального эффективного курса, п.п."}
    return _records({c: df[c] for c in names}, names)


# ---------------------------------------------------------------- output gap

def hp_filter(y: np.ndarray, lam: float) -> np.ndarray:
    """HP trend: (I + lam D'D)^-1 y."""
    n = len(y)
    d = np.zeros((n - 2, n))
    for i in range(n - 2):
        d[i, i:i + 3] = (1, -2, 1)
    return np.linalg.solve(np.eye(n) + lam * d.T @ d, y)


def hp_onesided(y: np.ndarray, lam: float, min_obs: int = 12) -> np.ndarray:
    out = np.full(len(y), np.nan)
    for t in range(min_obs - 1, len(y)):
        out[t] = hp_filter(y[: t + 1], lam)[-1]
    return out


def hamilton_gap(y: pd.Series, h: int = 8, p: int = 4) -> pd.Series:
    """Residual of y(t+h) on a constant and y(t), …, y(t-p+1), dated t+h (Hamilton 2018)."""
    X = pd.concat([y.shift(h + k) for k in range(p)], axis=1)
    X.insert(0, "const", 1.0)
    data = pd.concat([y.rename("y"), X], axis=1).dropna()
    beta, *_ = np.linalg.lstsq(data.drop(columns="y").values, data["y"].values, rcond=None)
    fitted = data.drop(columns="y").values @ beta
    return pd.Series(data["y"].values - fitted, index=data.index)


def uc_gap(y: pd.Series) -> pd.Series:
    import warnings
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = UnobservedComponents(y.values, level="local linear trend", autoregressive=2).fit(disp=False, maxiter=500)
    trend = res.level["smoothed"]
    return pd.Series(y.values - trend, index=y.index)


def output_gap(ds: dict) -> list[dict]:
    gdp = dimser("QNA_GDP_EXPENDITURE_SA_CONSTANT_2010", "GDP")
    if len(gdp) < 40:
        _structural(ds, f"only {len(gdp)} quarters of seasonally adjusted real GDP")
    y = 100 * np.log(gdp)
    trend = hp_filter(y.values, 1600)
    df = pd.DataFrame(index=y.index)
    df["HP"] = y - trend
    df["HP_ONESIDED"] = y.values - hp_onesided(y.values, 1600)
    df["HAMILTON"] = hamilton_gap(y)
    df["UC"] = uc_gap(y)
    df["MEAN"] = df[["HP", "HP_ONESIDED", "HAMILTON", "UC"]].mean(axis=1, skipna=False)
    df["POTENTIAL_GROWTH_HP"] = pd.Series(trend, index=y.index).diff() * 4
    df["GDP_SA_REAL"] = gdp / 1000
    names = {"HP": "Разрыв выпуска, фильтр Ходрика-Прескотта (двусторонний, λ=1600), % потенциала",
             "HP_ONESIDED": "Разрыв выпуска, односторонний HP (оценка в реальном времени), %",
             "HAMILTON": "Разрыв выпуска, фильтр Гамильтона (h=8, p=4), %",
             "UC": "Разрыв выпуска, модель ненаблюдаемых компонент (локальный линейный тренд + AR(2)), %",
             "MEAN": "Разрыв выпуска, среднее четырёх методов, %",
             "POTENTIAL_GROWTH_HP": "Рост потенциального ВВП (тренд HP), % годовых",
             "GDP_SA_REAL": "Реальный ВВП с устранением сезонности, млрд тенге в ценах 2010 г."}
    return _records({c: df[c] for c in names}, names)


# ---------------------------------------------------------------- credit

def credit(ds: dict) -> list[dict]:
    loans = scalar("nbk", "BANK_LOANS_STB_TOTAL")                 # as at the 1st = end of the previous month
    eoq = loans[loans.index.month.isin([1, 4, 7, 10])]
    eoq.index = eoq.index - pd.offsets.QuarterBegin(startingMonth=1)   # 2026-04-01 (end of Q1) -> 2026-01-01
    gdp = dimser("QNA_GDP_EXPENDITURE", "GDP")
    gdp4 = gdp.rolling(4, min_periods=4).sum()
    df = pd.DataFrame({"credit": eoq, "gdp4": gdp4}).dropna()
    df["CREDIT_TO_GDP"] = df.credit / df.gdp4 * 100
    ratio = df["CREDIT_TO_GDP"].values
    df["CREDIT_GAP"] = ratio - hp_onesided(ratio, 400_000, min_obs=12)
    flow4 = df.credit.diff(4)
    df["CREDIT_IMPULSE"] = (flow4 - flow4.shift(4)) / df.gdp4 * 100
    cpi = scalar("bns", "CPI_YOY")
    cpi_q = cpi[cpi.index.month.isin([3, 6, 9, 12])]
    cpi_q.index = cpi_q.index - pd.offsets.QuarterBegin(startingMonth=1)
    growth = df.credit.pct_change(4) * 100
    df["CREDIT_GROWTH_NOMINAL"] = growth
    df["CREDIT_GROWTH_REAL"] = ((1 + growth / 100) / (cpi_q.reindex(df.index) / 100) - 1) * 100
    names = {"CREDIT_TO_GDP": "Кредиты банков экономике к ВВП за 4 квартала, %",
             "CREDIT_GAP": "Разрыв кредит/ВВП (Базель III: односторонний HP, λ=400 000), п.п.",
             "CREDIT_IMPULSE": "Кредитный импульс: изменение кредитного потока за 4 квартала к ВВП, п.п.",
             "CREDIT_GROWTH_NOMINAL": "Рост кредитов банков за год, номинальный, %",
             "CREDIT_GROWTH_REAL": "Рост кредитов банков за год, реальный (дефлятор ИПЦ), %"}
    return _records({c: df[c] for c in names}, names)


# ---------------------------------------------------------------- fiscal

def fiscal(ds: dict) -> list[dict]:
    gdp = dimser("QNA_GDP_EXPENDITURE", "GDP")
    gdp_y = gdp.groupby(gdp.index.year).agg(["sum", "count"])
    gdp_y = gdp_y.loc[gdp_y["count"] == 4, "sum"]
    oil = dimser("OIL_GAS_SECTOR_GVA", "OIL_GAS")
    oil.index = oil.index.year
    non_oil_bal = scalar("minfin", "STATE_NON_OIL_DEFICIT")
    non_oil_bal.index = non_oil_bal.index.year
    bal = scalar("minfin", "STATE_BUDGET_DEFICIT")
    bal.index = bal.index.year
    df = pd.DataFrame({"gdp": gdp_y, "oil": oil, "nob": non_oil_bal, "bal": bal})
    df["NON_OIL_GDP"] = (df.gdp - df.oil) / 1000
    df["OIL_SHARE_GDP"] = df.oil / df.gdp * 100
    df["NON_OIL_BALANCE_PCT"] = df.nob / (df.gdp - df.oil) * 100
    df["FISCAL_IMPULSE"] = -df["NON_OIL_BALANCE_PCT"].diff()
    df["OVERALL_BALANCE_PCT"] = df.bal / df.gdp * 100
    df.index = pd.to_datetime([f"{y}-12-31" for y in df.index])
    names = {"NON_OIL_GDP": "Ненефтяной ВВП (ВВП минус ВДС нефтегазового сектора), млрд тенге",
             "OIL_SHARE_GDP": "Доля нефтегазового сектора в ВВП, %",
             "NON_OIL_BALANCE_PCT": "Ненефтяной баланс государственного бюджета, % ненефтяного ВВП",
             "FISCAL_IMPULSE": "Фискальный импульс: -изменение ненефтяного баланса, п.п. ненефтяного ВВП (рост = стимулирование)",
             "OVERALL_BALANCE_PCT": "Баланс государственного бюджета, % ВВП"}
    return _records({c: df[c] for c in names}, names)


MEASURES = {"core_inflation": core_inflation, "monetary_conditions": monetary_conditions, "output_gap": output_gap,
            "credit": credit, "fiscal": fiscal}


def fetch(ds: dict) -> tuple[list[dict], dict]:
    records = MEASURES[ds["measure"]](ds)
    if len({r["item_code"] for r in records}) < ds.get("min_items", 1):
        _structural(ds, f"only {len({r['item_code'] for r in records})} items")
    return records, {"frequency": ds["frequency"], "source_url": "derived by this repository (scripts/fetchers/analytics.py)",
                     "dataset_id": f"analytics/{ds['measure']}", "note": ds.get("note", ""),
                     "transformation": "derived (see the note)"}
