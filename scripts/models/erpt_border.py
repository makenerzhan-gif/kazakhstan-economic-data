"""Where does exchange-rate pass-through stop: at the border or in retail?

    python scripts/models/erpt_border.py    # writes models/erpt_neer/erpt_border.csv

Stage 1 (border): import price m/m of HS section s (BNS, CIF, in tenge, Taldau 19073959, 2020-01+)
                  on USD/KZT and on the consumer-import NEER, lags 0..3.
Stage 2 (retail): CPI division m/m on the matching import price, lags 0..6, AR(2), month FE.
Pairs: XI+XII (textiles, footwear) -> clothing & footwear; XVI (appliances) -> household goods;
IV (prepared food) -> food; VI (chemicals, pharma) -> health. Sample 2020-02..2026-07, HAC(4).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common, erpt_neer as N  # noqa: E401,E402

PAIRS = {"Одежда и обувь": ["XI", "XII"], "Предметы домашнего обихода, бытовая техника и текущее обслуживание жилья": ["XVI"],
         "Продукты питания и безалкогольные напитки": ["IV"], "Здравоохранение": ["VI"]}


def blocksum(r, cols):
    s = r.params[cols].sum()
    se = float(np.sqrt(np.ones(len(cols)) @ r.cov_params().loc[cols, cols].values @ np.ones(len(cols))))
    return s, s / se


def main():
    div, rates = N.load()
    ip = pd.read_csv(common.REPO_ROOT / "data/processed/dims/import_price_index_by_hs_section.csv", parse_dates=["date"])
    ip = ip.pivot_table(index="date", columns="item_code", values="value")
    ip.index = ip.index.to_period("M")
    ipm = 100 * np.log(ip / 100)  # chain m/m, January = Jan/Dec by BNS convention
    rows = []
    for name, secs in PAIRS.items():
        x = ipm[secs].mean(axis=1)
        row = {"раздел": name, "разделы ТН ВЭД": "+".join(secs)}
        for rate in ("usd", "neer"):
            df = pd.DataFrame({"x": x, **{f"e{k}": rates[rate].shift(k) for k in range(4)}}).loc["2020-02":"2026-07"].dropna()
            r = sm.OLS(df.x, sm.add_constant(df.drop(columns="x"))).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
            row[f"граница←{rate}"], row[f"t {rate}"] = blocksum(r, [f"e{k}" for k in range(4)])
        y = 100 * np.log(div[name] / 100)
        df = pd.DataFrame({"y": y, **{f"x{k}": x.shift(k) for k in range(7)}, "y1": y.shift(1), "y2": y.shift(2)})
        md = pd.get_dummies(pd.Series(df.index.month, index=df.index), prefix="m", drop_first=True, dtype=float)
        df = pd.concat([df, md], axis=1).loc["2020-08":"2026-07"].dropna()
        r = sm.OLS(df.y, sm.add_constant(df.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        row["розница←импорт 6м"], row["t розница"] = blocksum(r, [f"x{k}" for k in range(7)])
        row["n"] = int(r.nobs)
        rows.append(row)
    T = pd.DataFrame(rows)
    T.to_csv(common.MODELS / "erpt_neer" / "erpt_border.csv", index=False, float_format="%.3f")
    print(T.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
