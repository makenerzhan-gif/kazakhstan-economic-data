"""Shapiro (2022)-style demand/supply labelling of Kazakhstan's goods inflation.

    python scripts/models/shapiro_goods.py     # writes models/shapiro_goods/

Shapiro, A. H. (2022) "Decomposing Supply and Demand Driven Inflation", FRBSF WP 2022-18:
for each CPI component, a reduced-form VAR in its price and quantity; a month in which the
price and quantity innovations have the same sign is "demand-driven", opposite signs is
"supply-driven"; in the robust version innovations within +-0.25 s.d. of zero are
"ambiguous". The component's inflation that month is attributed to that label, and labelled
monthly inflation, weighted by the component's CPI weight and summed over 12 months, gives
the contribution to y/y inflation.

Kazakhstan version (what the data allow):
  * two components with monthly price AND quantity: food and non-food goods -- together
    ~0.69 of the CPI in 2024-2026 (weights below);
  * prices: BNS CPI groups (Taldau 703076), m/m and y/y;
  * quantities: BNS physical volume index of retail trade by commodity group, y/y
    (Taldau 702041, dictionary 3013 «Структура товаров для месячной формы»), 2016-01 on --
    fetched live from Taldau by this script;
  * y/y rates only exist for the quantities, so the VAR is in 12-month log changes with 13
    lags: given the lags, the innovation in a y/y change equals the innovation in the m/m
    change (dlog_t - dlog_{t-12}; the second term is known at t-1), so the sign test is the
    same as Shapiro's;
  * services (~0.31) are left unclassified -- BNS has no monthly volume of paid services to
    households (index 702501 is quarterly and covers business services too).
Weights: estimated each year from index arithmetic (headline m/m on the three groups,
coefficients summing to 1); the fit error is <= 0.08 pp a month, i.e. rounding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

OUT = common.MODELS / "shapiro_goods"
URL = "https://taldau.stat.gov.kz/ru/NewIndex/GetIndexTreeData"
HEADERS = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
LAGS = 13
BAND = 0.25


def fetch_retail_volume() -> pd.DataFrame:
    body = {"p_parent_id": "18224344", "p_index_id": "702041", "p_keyword": "", "p_period_id": "4",
            "p_measure_id": "7", "p_term_id": "18224344", "p_terms": "741880,741917,2695732,18224344",
            "p_dicIds": "68,776,848,3013", "idx": "3", "filter": '[{"property":null,"value":null}]', "id": ""}
    r = requests.post(URL, data=body, headers=HEADERS, timeout=60)
    r.raise_for_status()
    nodes = r.json()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "taldau_702041_raw.json").write_text(json.dumps(nodes, ensure_ascii=False))
    names = {"Продовольственные товары": "food", "Непродовольственные товары": "nonfood"}
    out = {}
    for n in nodes:
        key = names[n["text"]]
        s = {}
        for k, v in n.items():
            if isinstance(k, str) and len(k) == 7 and k[0] == "y" and k[1:].isdigit() and v not in ("", None, "x"):
                s[pd.Period(f"{k[3:]}-{k[1:3]}", "M")] = float(v)
        out[key] = pd.Series(s).sort_index()
    df = pd.DataFrame(out)
    # Taldau has no value for 2025-10 (checked 2026-09-27); a gap would shift every VAR lag and
    # the 12-month sums, so the missing month is interpolated linearly and flagged.
    full = pd.period_range(df.index[0], df.index[-1], freq="M")
    missing = full.difference(df.index)
    if len(missing):
        print("retail volume: interpolated", [str(p) for p in missing])
    df = df.reindex(full).interpolate()
    return df


def weights(m: pd.DataFrame) -> pd.DataFrame:
    L = (np.log(m[["cpi", "cpi_food", "cpi_nonfood", "cpi_services"]]).diff() * 100).dropna()
    rows = []
    for y in sorted(set(L.index.year)):
        d = L[L.index.year == y]
        if len(d) < 6:
            continue
        X = np.column_stack([d.cpi_food - d.cpi_services, d.cpi_nonfood - d.cpi_services])
        b = np.linalg.lstsq(X, d.cpi - d.cpi_services, rcond=None)[0]
        fit = b[0] * d.cpi_food + b[1] * d.cpi_nonfood + (1 - b.sum()) * d.cpi_services
        rows.append({"year": y, "food": b[0], "nonfood": b[1], "services": 1 - b.sum(),
                     "max_abs_error_pp": float((fit - d.cpi).abs().max())})
    return pd.DataFrame(rows).set_index("year")


def var_resid(Y: np.ndarray, p: int) -> np.ndarray:
    T = len(Y)
    X = np.hstack([Y[p - j:T - j] for j in range(1, p + 1)] + [np.ones((T - p, 1))])
    B = np.linalg.lstsq(X, Y[p:], rcond=None)[0]
    return Y[p:] - X @ B


def label(res: np.ndarray, band: float) -> np.ndarray:
    sd = res.std(axis=0, ddof=1)
    z = res / sd
    lab = np.where(np.sign(z[:, 0]) == np.sign(z[:, 1]), "demand", "supply").astype(object)
    if band > 0:
        lab[(np.abs(z[:, 0]) < band) | (np.abs(z[:, 1]) < band)] = "ambiguous"
    return lab


def decompose(band: float = BAND, lags: int = LAGS) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m = common.load_monthly()
    vol = fetch_retail_volume()
    w = weights(m)
    out, labels = [], {}
    for g in ("food", "nonfood"):
        price_yoy = 100 * np.log(1 + m[f"cpi_{g}_yoy"] / 100)
        qty_yoy = 100 * np.log(vol[g] / 100)
        d = pd.concat([price_yoy.rename("p"), qty_yoy.rename("q")], axis=1).dropna()
        res = var_resid(d.values, lags)
        idx = d.index[lags:]
        lab = pd.Series(label(res, band), index=idx)
        labels[g] = lab
        mom = 100 * np.log(m[f"cpi_{g}"]).diff()  # NSA m/m log change, the inflation that gets labelled
        wt = pd.Series([w.loc[p.year, g] if p.year in w.index else np.nan for p in idx], index=idx)
        for cat in ("demand", "supply", "ambiguous"):
            x = (mom.reindex(idx) * (lab == cat) * wt)
            out.append(x.rolling(12).sum().rename(f"{g}_{cat}"))
        out.append((mom.reindex(idx) * wt).rolling(12).sum().rename(f"{g}_total"))
    c = pd.concat(out, axis=1).dropna()
    for cat in ("demand", "supply", "ambiguous"):
        c[f"goods_{cat}"] = c[f"food_{cat}"] + c[f"nonfood_{cat}"]
    c["goods_total"] = c.food_total + c.nonfood_total
    c["headline_yoy_log"] = (100 * np.log(1 + m["cpi_yoy"] / 100)).reindex(c.index)
    lab = pd.DataFrame(labels)
    return c, lab, w


def chart(c: pd.DataFrame, path: Path) -> None:
    import matplotlib.pyplot as plt

    d = c.loc["2018-01":]
    fig, ax = common.figure(10.5, 5.2)
    x = np.arange(len(d))
    cols = {"goods_demand": ("Спрос", "#eb6834"), "goods_supply": ("Предложение", "#2a78d6"),
            "goods_ambiguous": ("Неопределённые", "#c3c2b7")}
    pos, neg = np.zeros(len(d)), np.zeros(len(d))
    for k, (lab, col) in cols.items():
        v = d[k].values
        bottom = np.where(v >= 0, pos, neg)
        ax.bar(x, v, bottom=bottom, width=1.0, color=col, label=lab, linewidth=0)
        pos += np.where(v >= 0, v, 0)
        neg += np.where(v < 0, v, 0)
    ax.plot(x, d.goods_total.values, color=common.INK, lw=1.4, label="Вклад товаров в ИПЦ г/г")
    ax.plot(x, d.headline_yoy_log.values, color=common.MUTED, lw=1.2, ls="--", label="ИПЦ г/г (всего)")
    common.zero_line(ax)
    ticks = [i for i, p in enumerate(d.index) if p.month == 1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(d.index[i].year) for i in ticks])
    ax.set_ylabel("п.п.", color=common.INK_2, fontsize=9)
    common.title(ax, "Товарная инфляция: спрос или предложение (метод Shapiro)",
                 "Вклад продовольственных и непродовольственных товаров в ИПЦ г/г по типу месяца, п.п. "
                 "(услуги не классифицированы)")
    ax.legend(frameon=False, fontsize=8.5, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.07))
    fig.tight_layout()
    common.save(fig, path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c, lab, w = decompose()
    c.index = c.index.astype(str)
    c.to_csv(OUT / "contributions.csv", float_format="%.3f")
    lab.index = lab.index.astype(str)
    lab.to_csv(OUT / "labels.csv")
    w.to_csv(OUT / "cpi_group_weights_estimated.csv", float_format="%.4f")
    rob = {}
    for name, kw in {"band0": dict(band=0.0), "lags7": dict(lags=7), "band50": dict(band=0.5)}.items():
        r, _, _ = decompose(**kw)
        r.index = r.index.astype(str)
        r.to_csv(OUT / f"contributions_{name}.csv", float_format="%.3f")
        rob[name] = r
    c2 = c.copy()
    c2.index = pd.PeriodIndex(c2.index, freq="M")
    chart(c2, OUT / "shapiro_goods.png")
    show = ["2019-12", "2021-12", "2022-12", "2023-12", "2024-12", "2025-06", "2025-09", "2025-12", "2026-03", "2026-04"]
    cols = ["goods_demand", "goods_supply", "goods_ambiguous", "goods_total", "headline_yoy_log"]
    print(c.loc[[s for s in show if s in c.index], cols].round(2))
    for k, r in rob.items():
        print(k)
        print(r.loc[[s for s in show if s in r.index], cols].round(2))
    print(w.round(3))


if __name__ == "__main__":
    main()
