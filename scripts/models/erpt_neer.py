"""Exchange-rate pass-through by CPI division: USD/KZT against the NEER weighted by CONSUMER imports
(BEC 112, 122, 522, 61-63; previous-year Comtrade weights; RUB and CNY carry most of the weight).

    python scripts/models/erpt_neer.py      # writes models/erpt_neer/

Per division d (monthly, 2016-01..2026-08, HAC(6) errors):
    pi_d,t = c + sum_{k=0..12} b_k * e_{t-k} + r1 pi_d,t-1 + r2 pi_d,t-2 + g0 oil_t + g1 oil_t-1 + month FE
e = 100 dln USD/KZT (depreciation +) or -100 dln NEER_CONSUMER (depreciation +).
Reported: 12-month pass-through sum b_k (short run) and b/(1-r1-r2) (long run), t-stat, adjusted R2,
and a horse race with both rates (sum of each block). Inputs: models/cpi_components/division_mm.csv
(BNS CPI by COICOP division, m/m), model_data/monthly.csv, dims NEER_CONSUMER.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT = common.MODELS / "erpt_neer"
L = 12
W = {  # official BNS basket weights 2025, % (as in the accounting decomposition)
    "Продукты питания и безалкогольные напитки": 38.6, "Алкогольные напитки и табачные изделия": 1.7,
    "Одежда и обувь": 9.0, "Жилищные услуги, вода, электроэнергия, газ и другие виды топлива": 13.2,
    "Предметы домашнего обихода, бытовая техника и текущее обслуживание жилья": 5.2, "Здравоохранение": 8.8,
    "Транспорт": 7.7, "Связь": 3.3, "Отдых и культура": 1.9, "Образование": 2.4, "Рестораны и гостиницы": 1.4}


def load():
    m = common.load_monthly()
    div = pd.read_csv(common.MODELS / "cpi_components" / "division_mm.csv", index_col=0, parse_dates=True)
    div.index = div.index.to_period("M")
    n = pd.read_csv(common.REPO_ROOT / "data" / "processed" / "dims" / "neer_import_weighted.csv", parse_dates=["date"])
    neer = n[n.item_code == "NEER_CONSUMER"].set_index("date")["value"]
    neer.index = neer.index.to_period("M")
    rates = pd.DataFrame({"usd": 100 * np.log(m.usdkzt).diff(), "neer": -100 * np.log(neer).diff(),
                          "rub": 100 * np.log(m.usdkzt / m.rubusd).diff(), "oil": 100 * np.log(m.brent).diff()})
    return div, rates


def fit(y, rates, blocks):
    df = pd.DataFrame({"y": y})
    for b in blocks:
        for k in range(L + 1):
            df[f"{b}{k}"] = rates[b].shift(k)
    df["y1"], df["y2"] = y.shift(1), y.shift(2)
    df["oil"], df["oil1"] = rates.oil, rates.oil.shift(1)
    md = pd.get_dummies(pd.Series(df.index.month, index=df.index), prefix="m", drop_first=True, dtype=float)
    df = pd.concat([df, md], axis=1).loc["2016-01":"2026-08"].dropna()
    r = sm.OLS(df.y, sm.add_constant(df.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    out = {"adj_r2": r.rsquared_adj, "aic": r.aic, "nobs": int(r.nobs)}
    rho = r.params["y1"] + r.params["y2"]
    for b in blocks:
        cols = [f"{b}{k}" for k in range(L + 1)]
        s = r.params[cols].sum()
        se = float(np.sqrt(np.ones(L + 1) @ r.cov_params().loc[cols, cols].values @ np.ones(L + 1)))
        out.update({f"{b}_sr": s, f"{b}_t": s / se, f"{b}_lr": s / (1 - rho)})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    div, rates = load()
    rows = []
    for name, w in W.items():
        y = 100 * np.log(div[name] / 100)
        a, b, c = fit(y, rates, ["usd"]), fit(y, rates, ["neer"]), fit(y, rates, ["usd", "neer"])
        rows.append({"раздел": name, "вес": w,
                     "USD: перенос 12м": a["usd_sr"], "USD: t": a["usd_t"], "USD: adjR2": a["adj_r2"],
                     "NEER: перенос 12м": b["neer_sr"], "NEER: t": b["neer_t"], "NEER: adjR2": b["adj_r2"],
                     "ΔAIC (NEER−USD)": b["aic"] - a["aic"],
                     "вместе: USD": c["usd_sr"], "вместе: USD t": c["usd_t"],
                     "вместе: NEER": c["neer_sr"], "вместе: NEER t": c["neer_t"]})
    T = pd.DataFrame(rows)
    tot = {k: (T[k] * T["вес"]).sum() / T["вес"].sum() for k in ["USD: перенос 12м", "NEER: перенос 12м"]}
    T.to_csv(OUT / "erpt_usd_vs_neer.csv", index=False, float_format="%.3f")
    corr = rates[["usd", "neer", "rub"]].loc["2016":].corr()
    corr.to_csv(OUT / "rate_correlations.csv", float_format="%.3f")
    print(T.round(2).to_string(index=False))
    print("weighted 12m pass-through:", {k: round(v, 3) for k, v in tot.items()})
    print(corr.round(2))


if __name__ == "__main__":
    main()
