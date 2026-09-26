#!/usr/bin/env python3
"""Build the model-ready panels in model_data/ from the unified dataset.

    python scripts/build_model_data.py

Reads data/unified/macro_long.csv and data/unified/macro_dims_long.csv.gz only (never raw
or processed files) and the variable spec model_data/spec.yaml; writes

    model_data/monthly.csv     date x variables (levels, _sa, _yoy, _saar)
    model_data/quarterly.csv   the same by quarter, plus the production-function block
    model_data/annual.csv      the annual capital-stock build (perpetual inventory)
    model_data/VARIABLES.md    one card per variable: source, operations, sample, caveats

Everything here is derived by this repository -- see model_data/README.md. Not wired into
update_all.py: rerun it after a pipeline update, like the analysis/ scripts.

Dates: monthly and quarterly periods are dated at their first day (the pipeline's
convention); a stock "as at the 1st" is moved to the end of the previous period by
`asat_to_eop`, so month m holds the end-of-m stock.

Seasonal adjustment: statsmodels STL, robust, on ln(level) (`sa: log`) or the level
(`sa: additive`), on the longest run without gaps that covers at least three years; months
outside that run get no SA value. X-13ARIMA-SEATS is not available in this environment.
Where the source publishes an adjusted series (BNS quarterly national accounts, FRED) that
series is used as is (`sa: official`).
"""
from __future__ import annotations

import gzip
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from statsmodels.tsa.seasonal import STL

REPO_ROOT = Path(__file__).resolve().parents[1]
UNIFIED = REPO_ROOT / "data" / "unified"
OUT = REPO_ROOT / "model_data"
MIN_SA_YEARS = 3


# ---------------------------------------------------------------- loading
def load_long() -> pd.DataFrame:
    df = pd.read_csv(UNIFIED / "macro_long.csv", usecols=["date", "variable", "value", "frequency", "unit"],
                     dtype={"date": str})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


def load_dims() -> pd.DataFrame:
    with gzip.open(UNIFIED / "macro_dims_long.csv.gz", "rt", encoding="utf-8") as f:
        df = pd.read_csv(f, usecols=["date", "region", "variable", "item_code", "value"], dtype={"date": str})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


def series_of(long: pd.DataFrame, dims: pd.DataFrame, source: dict) -> tuple[pd.Series, str]:
    if "series" in source:
        d = long[long.variable == source["series"]]
        freq = d.frequency.iloc[0] if len(d) else ""
    else:
        d = dims[(dims.variable == source["dims"]) & (dims.item_code == source["item"])
                 & (dims.region == source.get("region", "national"))]
        freq = ""
    if d.empty:
        raise SystemExit(f"model_data: no data for {source}")
    s = pd.Series(d.value.values, index=pd.to_datetime(d.date.values)).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s, freq


# ---------------------------------------------------------------- operations
def chain(s: pd.Series) -> pd.Series:
    """Previous-period = 100 indices -> a level index, 100 at the first period."""
    return 100 * (s / 100).cumprod() / (s.iloc[0] / 100)


def decumulate_ytd(s: pd.Series, per_year: int) -> pd.Series:
    """Year-to-date -> own period; a period whose predecessor in the same year is missing
    stays missing (never differenced across a gap)."""
    out = {}
    step = 12 // per_year
    for d, v in s.items():
        first = d.month == 1
        if first:
            out[d] = v
            continue
        prev = d - pd.DateOffset(months=step)
        if prev in s.index:
            out[d] = v - s[prev]
    return pd.Series(out).sort_index()


def asat_to_eop(s: pd.Series, per_year: int) -> pd.Series:
    return pd.Series(s.values, index=s.index - pd.DateOffset(months=12 // per_year))


def to_monthly(s: pd.Series, how: str, event: bool) -> pd.Series:
    """Daily or event-dated -> months. Event series (policy rates) are a step function held
    until the next decision; the last month is the previous complete one."""
    last_month = pd.Timestamp(date.today().replace(day=1)) - pd.DateOffset(months=1)
    if event:
        days = pd.date_range(s.index.min(), last_month + pd.offsets.MonthEnd(0), freq="D")
        s = s.reindex(days.union(s.index)).ffill().reindex(days)
    g = s.groupby(s.index.to_period("M"))
    m = g.mean() if how == "mean" else g.last()
    m.index = m.index.to_timestamp()
    return m[m.index <= last_month]


def seasonal_adjust(s: pd.Series, period: int, mode: str, robust: bool) -> pd.Series:
    """STL on the longest gap-free run (>= MIN_SA_YEARS years); NaN elsewhere."""
    s = s.dropna()
    if s.empty:
        return s
    step = 12 // period
    expected = pd.date_range(s.index.min(), s.index.max(), freq=f"{step}MS")
    full = s.reindex(expected)
    runs, cur = [], []
    for d, v in full.items():
        if pd.isna(v):
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(d)
    if cur:
        runs.append(cur)
    best = max(runs, key=len)
    if len(best) < MIN_SA_YEARS * period:
        return pd.Series(dtype=float)
    x = full.loc[best]
    if mode == "log":
        if (x <= 0).any():
            raise SystemExit(f"model_data: log SA on a non-positive series ({x.name})")
        fit = STL(np.log(x.values), period=period, robust=robust).fit()
        return pd.Series(np.exp(np.log(x.values) - fit.seasonal), index=x.index)
    fit = STL(x.values, period=period, robust=robust).fit()
    return pd.Series(x.values - fit.seasonal, index=x.index)


def derived_columns(name: str, level: pd.Series, sa: pd.Series | None, kind: str, per_year: int) -> dict:
    cols = {name: level}
    if sa is not None and not sa.empty:
        cols[f"{name}_sa"] = sa
    if kind == "level":
        full = level.asfreq(f"{12 // per_year}MS")
        cols[f"{name}_yoy"] = (100 * (full / full.shift(per_year) - 1)).dropna()
        base = sa if sa is not None and not sa.empty else None
        if base is not None:
            b = base.asfreq(f"{12 // per_year}MS")
            cols[f"{name}_saar"] = (100 * ((b / b.shift(1)) ** per_year - 1)).dropna()
    return cols


# ---------------------------------------------------------------- panels
EVENT_SERIES = {"BASE_RATE", "RU_KEY_RATE", "EA_DEPOSIT_RATE"}


def build_variable(v: dict, long, dims, per_year: int, robust: bool, monthly_panel=None) -> tuple[dict, dict]:
    kind = v.get("kind", "level")
    src = v["source"]
    info = {"name": v["name"], "source": src, "ops": list(v.get("ops", [])), "sa": v.get("sa", "none"),
            "kind": kind, "note": v.get("note", ""), "agg": v.get("agg"), "to_monthly": v.get("to_monthly")}
    if "monthly" in src:                                  # quarterly aggregate of a monthly variable
        how = v["agg"]
        cols = {}
        for suffix in ("", "_sa"):
            col = src["monthly"] + suffix
            if monthly_panel is None or col not in monthly_panel:
                continue
            m = monthly_panel[col].dropna()
            q = m.groupby(m.index.to_period("Q"))
            n = q.count()
            agg = {"mean": q.mean(), "sum": q.sum(), "last": q.last()}[how]
            agg = agg[n == 3]                             # complete quarters only
            agg.index = agg.index.to_timestamp()
            cols[v["name"] + suffix] = agg
        level = cols[v["name"]]
        sa = cols.get(v["name"] + "_sa")
        return derived_columns(v["name"], level, sa, kind, per_year), info
    s, freq = series_of(long, dims, src)
    info["source_frequency"] = freq
    if v.get("to_monthly"):
        s = to_monthly(s, v["to_monthly"], src.get("series") in EVENT_SERIES)
    for op in v.get("ops", []):
        s = {"chain": chain, "decumulate_ytd": lambda x: decumulate_ytd(x, per_year),
             "asat_to_eop": lambda x: asat_to_eop(x, per_year)}[op](s)
    if per_year == 4:                                     # quarterly panel: quarter-start dates
        s.index = s.index.to_period("Q").to_timestamp()
        s = s[~s.index.duplicated(keep="last")]
    if v.get("from"):
        s = s[s.index >= pd.Timestamp(v["from"])]
    s.name = v["name"]
    mode = v.get("sa", "none")
    sa = None
    if mode in ("log", "additive"):
        sa = seasonal_adjust(s, per_year, mode, robust)
    elif mode == "official":
        sa = s.copy()
    return derived_columns(v["name"], s, sa, kind, per_year), info


def assemble(cols: dict, per_year: int) -> pd.DataFrame:
    df = pd.DataFrame(cols).sort_index()
    df.index.name = "date"
    return df


# ---------------------------------------------------------------- capital stock and TFP
def capital_block(long, dims, params: dict, quarterly: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    def annual(var):
        d = long[long.variable == var]
        return pd.Series(d.value.values, index=d.date.str[:4].astype(int).values).sort_index()

    gfcf_nom, gfcf_vi, gdp_vi = annual("GFCF"), annual("GFCF_VOLUME_INDEX"), annual("GDP_REAL")
    dep, gross0 = annual("FIXED_ASSETS_DEPRECIATION"), annual("FIXED_ASSETS_GROSS_START")
    cfg = params["capital"]
    ratio = (dep / gross0).dropna()
    if cfg["delta"] == "book_median":
        delta = float(ratio[~ratio.index.isin(cfg.get("exclude_years", []))].median())
    else:
        delta = float(cfg["delta"])
    # Real GFCF at 2010 prices: the 2010 nominal level chained with the volume index.
    years = sorted(set(gfcf_nom.index) & set(gfcf_vi.index))
    real = {2010: gfcf_nom[2010] / 1e6}                  # million KZT
    for y in [y for y in years if y > 2010]:
        real[y] = real[y - 1] * gfcf_vi[y] / 100
    for y in sorted([y for y in years if y < 2010], reverse=True):
        real[y] = real[y + 1] / (gfcf_vi[y + 1] / 100)
    inv = pd.Series(real).sort_index()
    g = float(np.exp(np.mean(np.log(gdp_vi.loc[2000:2009] / 100))) - 1)
    k0 = inv.iloc[0] / (g + delta)
    k, prev = {}, k0
    for y, i in inv.items():
        prev = (1 - delta) * prev + i
        k[y] = prev
    annual_df = pd.DataFrame({"gfcf_real_2010": inv, "capital_real_2010": pd.Series(k)})
    annual_df["depreciation_book_ratio"] = ratio
    annual_df.index.name = "year"
    # Quarterly: BNS SA GFCF at 2010 prices from 2010-Q1, benchmarked pro rata to the annual
    # real GFCF (the quarterly accounts of 2010-2022 are an older vintage, 5-13 % above the
    # revised annual nominal GFCF; from 2023 they agree), starting from the end-2009 stock.
    # A year without an annual figure yet keeps the previous year's factor.
    dq = 1 - (1 - delta) ** 0.25
    iq_raw = quarterly["gfcf"].dropna()
    by_year = iq_raw.groupby(iq_raw.index.year).sum()
    counts = iq_raw.groupby(iq_raw.index.year).count()
    factors = {}
    for y in sorted(by_year.index):
        if y in inv.index and counts[y] == 4:
            factors[y] = inv[y] / by_year[y]
        elif factors:
            factors[y] = factors[max(factors)]
    iq = pd.Series([v * factors.get(d.year, float("nan")) for d, v in iq_raw.items()], index=iq_raw.index).dropna()
    kq, prev = {}, k[2009]
    for d, i in iq.items():
        prev = (1 - dq) * prev + i
        kq[d] = prev
    kq = pd.Series(kq)
    # Labour share and TFP.
    inc = dims[(dims.variable == "QNA_GDP_INCOME") & (dims.region == "national")]
    p = inc.pivot_table(index="date", columns="item_code", values="value")
    p.index = pd.to_datetime(p.index)
    ls = (p["COMPENSATION"] / (p["GDP"] - p["NET_TAXES_PRODUCTION_IMPORTS"])).dropna()
    alpha = 1 - float(ls.mean())
    y, l = quarterly["gdp"].dropna(), quarterly.get("employment_sa", pd.Series(dtype=float)).dropna()
    common = y.index.intersection(kq.index).intersection(l.index)
    tfp = np.log(y[common]) - alpha * np.log(kq[common]) - (1 - alpha) * np.log(l[common])
    q = pd.DataFrame({"gfcf_benchmarked": iq, "capital": kq, "labour_share": ls, "tfp_log": 100 * (tfp - tfp.iloc[0])})
    def tfp_change(d: float) -> float:
        """TFP change over the sample (log points x100) for a depreciation rate d."""
        kk, pv = {}, inv.iloc[0] / (g + d)
        for yy, ii in inv.items():
            pv = (1 - d) * pv + ii
            kk[yy] = pv
        dqq, pv, kq2 = 1 - (1 - d) ** 0.25, kk[2009], {}
        for dd, ii in iq.items():
            pv = (1 - dqq) * pv + ii
            kq2[dd] = pv
        kq2 = pd.Series(kq2)
        t = np.log(y[common]) - alpha * np.log(kq2[common]) - (1 - alpha) * np.log(l[common])
        return float(100 * (t.iloc[-1] - t.iloc[0]))

    meta = {"benchmark_factors": {int(yy): round(float(f), 4) for yy, f in factors.items()},
            "tfp_sensitivity": {dd: round(tfp_change(dd), 1) for dd in (0.05, round(delta, 4), 0.12)},
            "tfp_window": (common[0].strftime("%Y-%m"), common[-1].strftime("%Y-%m")), "delta": delta, "delta_quarterly": dq, "g_2000_2009": g, "k_end_1999": k0, "alpha": alpha,
            "labour_share_mean": float(ls.mean()), "check_2011_2012": {
                y: (float(inv.get(y, float("nan"))),
                    float(quarterly["gfcf"].loc[str(y)].sum()) if "gfcf" in quarterly else None) for y in (2011, 2012)}}
    return q, meta, annual_df


# ---------------------------------------------------------------- cards
def card(info: dict, df: pd.DataFrame, per_year: int) -> str:
    name = info["name"]
    s = df[name].dropna() if name in df else pd.Series(dtype=float)
    src = info["source"]
    src_txt = (f"`{src['series']}`" if "series" in src else
               f"`{src['dims']}` item `{src['item']}`" if "dims" in src else f"monthly `{src['monthly']}`, {info['agg']}")
    ops = ", ".join(info["ops"]) or "—"
    if info.get("to_monthly"):
        ops = f"to monthly: {info['to_monthly']}; " + ops
    fmt = (lambda d: d.strftime("%Y-%m")) if per_year == 12 else (lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}")
    sample = f"{fmt(s.index[0])} … {fmt(s.index[-1])}, {len(s)} obs" if len(s) else "no data"
    cols = [c for c in df.columns if c == name or c.startswith(name + "_") and c[len(name) + 1:] in ("sa", "yoy", "saar")]
    line = f"| `{name}` | {src_txt} | {ops} | {info['sa']} | {sample} | {', '.join('`' + c + '`' for c in cols)} | {info['note']} |"
    return line


def main() -> int:
    spec = yaml.safe_load((OUT / "spec.yaml").read_text(encoding="utf-8"))
    robust = bool(spec["parameters"].get("stl_robust", True))
    long, dims = load_long(), load_dims()
    mcols, minfo = {}, []
    for v in spec["monthly"]:
        cols, info = build_variable(v, long, dims, 12, robust)
        mcols.update(cols)
        minfo.append(info)
    start = pd.Timestamp(spec["parameters"].get("panel_start", "1994-01-01"))
    monthly = assemble(mcols, 12)
    monthly = monthly[monthly.index >= start]
    qcols, qinfo = {}, []
    for v in spec["quarterly"]:
        cols, info = build_variable(v, long, dims, 4, robust, monthly_panel=monthly)
        qcols.update(cols)
        qinfo.append(info)
    quarterly = assemble(qcols, 4)
    quarterly = quarterly[quarterly.index >= start]
    pf, meta, annual_df = capital_block(long, dims, spec["parameters"], quarterly)
    quarterly = quarterly.join(pf, how="outer")
    monthly.round(6).to_csv(OUT / "monthly.csv", date_format="%Y-%m-%d")
    quarterly.round(6).to_csv(OUT / "quarterly.csv", date_format="%Y-%m-%d")
    annual_df.round(6).to_csv(OUT / "annual.csv")
    write_cards(minfo, monthly, qinfo, quarterly, meta)
    print(f"model_data: monthly {monthly.shape}, quarterly {quarterly.shape}, annual {annual_df.shape}; "
          f"delta {meta['delta']:.4f}, alpha {meta['alpha']:.3f}")
    return 0


def write_cards(minfo, monthly, qinfo, quarterly, meta) -> None:
    head = "| variable | source | operations | SA | sample | columns | note |\n|---|---|---|---|---|---|---|"
    k = meta["check_2011_2012"]
    lines = [
        "# Model data — variable cards",
        "",
        f"Generated by `scripts/build_model_data.py` on {date.today().isoformat()} from `data/unified/` "
        "and `model_data/spec.yaml`. Derived by this repository (see README.md). Column suffixes: "
        "`_sa` seasonally adjusted, `_yoy` % change on a year earlier (from the unadjusted level), "
        "`_saar` % annualised change on the previous period (from the adjusted level).",
        "",
        "## Monthly (`monthly.csv`)", "", head, *[card(i, monthly, 12) for i in minfo], "",
        "## Quarterly (`quarterly.csv`)", "", head, *[card(i, quarterly, 4) for i in qinfo], "",
        "## Production function (`quarterly.csv`: `capital`, `labour_share`, `tfp_log`; `annual.csv`)", "",
        f"- **Capital** — perpetual inventory at average 2010 prices, million KZT. Annual real GFCF: the 2010 "
        f"nominal level chained with BNS `GFCF_VOLUME_INDEX` (2000–2025). Depreciation δ = {meta['delta']:.4f} a year "
        f"({meta['delta_quarterly']:.4f} a quarter): the median of BNS book depreciation over gross fixed assets at the "
        "start of the year, 2000–2025 without the 2019–2021 revaluation years. Initial stock at end-1999 = I₂₀₀₀/(g+δ) "
        f"with g = {meta['g_2000_2009']:.4f} (mean real GDP growth 2000–2009): {meta['k_end_1999']:,.0f}. From 2010-Q1 the "
        "quarterly stock accumulates BNS seasonally adjusted GFCF at 2010 prices from the end-2009 annual stock.",
        f"- Quarterly investment is BNS SA GFCF at 2010 prices benchmarked pro rata to the annual real GFCF "
        f"(column `gfcf_benchmarked`): the quarterly accounts of 2010–2022 are an older vintage above the revised annual "
        f"figures, and their fixed 2010 prices drift from the chain-linked annual volume index (a factor near 0.91 remains "
        f"after 2023, when the nominal figures agree) (2011: annual chain {k[2011][0]:,.0f} vs quarterly sum {k[2011][1]:,.0f}; 2012: {k[2012][0]:,.0f} vs "
        f"{k[2012][1]:,.0f}); factors by year: {meta['benchmark_factors']}. Pro rata keeps the quarterly pattern but "
        "can step at year boundaries.",
        f"- **Labour share** — compensation of employees / (GDP − net taxes on production and imports), QNA income "
        f"approach, quarterly; mean {meta['labour_share_mean']:.3f}. Mixed income of the self-employed sits in gross "
        "profit, so this understates labour's share.",
        f"- **TFP** — `tfp_log` = 100·(ln Y − α ln K − (1−α) ln L), rebased to 0 at its first quarter; Y = `gdp` (SA, 2010 "
        f"prices), K = `capital`, L = `employment_sa`, α = 1 − mean labour share = {meta['alpha']:.3f}. A residual: it "
        "absorbs utilisation, hours and measurement error, and the high α reflects the mining sector. "
        f"Its change over {meta['tfp_window'][0]}…{meta['tfp_window'][1]} (log points ×100) by δ: "
        + ", ".join(f"δ={d}: {v}" for d, v in meta["tfp_sensitivity"].items())
        + ". The quarterly stock depreciates investment within the year, so it runs 2–3 % below the annual "
        "end-year stock.",
        "- Book values (`FIXED_ASSETS_*`) are historical cost with revaluations; they set δ only, never the level of K.",
        "",
    ]
    (OUT / "VARIABLES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
