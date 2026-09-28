# models/ — estimated models (derived)

Estimated by this repository, **not published by any source** — the same status as
`analysis/` and `model_data/`. Each model reads `model_data/` (and, for gravity,
`data/unified/` and `data/reference/`), and writes its folder here: a report in Russian
(`REPORT.md`), charts (PNG), and every number behind them as CSV.

```bash
python scripts/build_model_data.py      # first, after a pipeline update
python scripts/models/gravity.py        # ~10 s
python scripts/models/bvar.py           # ~30 s
python scripts/models/rstar.py          # ~1 min
python scripts/models/svar_v2.py        # ~1.5 min (inflation decomposition, current)
python scripts/models/erpt_neer.py && python scripts/models/erpt_border.py
```

None of them is part of `update_all.py`: re-run them when the inputs change.

| Folder | Model | Method | Main outputs |
|---|---|---|---|
| `gravity/` | Kazakhstan's exports and imports by partner, 2000–2025 | PPML (Santos Silva & Tenreyro 2006), year FE and partner + year FE; log-OLS benchmark | `coefficients.csv`, `potential.csv` (actual / predicted by partner), `panel.csv` |
| `bvar/` | Brent, Fed funds, RUB/USD → GDP, USD/KZT, inflation, TONIA; 2011Q2–2026Q1 | Minnesota prior by dummy observations, λ/μ by marginal likelihood, block exogeneity (Gibbs), crisis quarters with scaled volatility (Lenza & Primiceri 2022), recursive identification | `irf.csv`, `fevd.csv`, `historical_decomposition.csv`, `forecast.csv` |
| `rstar/` | r*, trend growth, potential output, output gap; 2012Q1–2026Q1 | Holston–Laubach–Williams-type state space, Kalman filter, posterior mode with QPM-style priors; production-function and HP gaps, interest-parity floor as cross-checks | `states.csv`, `gaps.csv`, `parameters.csv`, `sensitivity.csv` |
| `bvar_sign/`, `bvar_sign_ext/` | Inflation decomposition into demand, supply, policy-rate, tenge (and real G, regulated tariffs); 2011Q2–2026Q1 | BVAR as `bvar/`, sign + zero restrictions (Rubio-Ramírez–Waggoner–Zha), Blanchard–Perotti recursive fiscal and tariff blocks, HD median target (Fry–Pagan) | `bands_*.csv`, `median_target_*.csv`, `fiscal_irf_*.csv` — **estimated on the STL-adjusted model_data of 2026-09-27; superseded by `svar_v2/`** |
| `svar_v2/` | Same decomposition, fiscal block = non-oil deficit % GDP (quarterly, annual stance, quasi-fiscal split), tariffs = identified CPI tariff steps; 2013Q3–2026Q2 | as `bvar_sign_ext/`, X-13 data; variants `old_2011`, `old_2013`, `v2`, `v2_split`, `v2_ma4`, `v2_market`, `v2_ma4_market` | `changes_*.csv` (contribution changes over episodes), `levels_*.csv`, `median_target_*.csv`, `irf_*_*.csv`, `summary.csv` (FEVD at 8 quarters), `inputs_quarterly.csv` |
| `bvar_market/` | The sign-restricted SVARs on the market core CPI (headline without fruit & veg, fuel, coal, regulated utilities) | as above; three weights for the utilities (±30 %) | `bands7_*.csv`, `bands9_*.csv` (STL vintage) |
| `shapiro_goods/` | Demand- vs supply-driven goods inflation, 2016–2026 | Shapiro (2022): sign of price and quantity residuals per CPI goods group | `contributions.csv` |
| `fiscal_lp/` | Price response to fiscal shocks | Jordà local projections, HAC | `lp.csv`, `nf_transfers_pct_gdp.csv` |
| `regional_fiscal/` | Regional price response to budget-financed investment, 2018–2026 | panel LP, month and region×calendar-month FE, clustered by region | `lp_shock*.csv` |
| `erpt_neer/` | Exchange-rate pass-through by COICOP division: USD/KZT vs consumer-import NEER; border (import prices) vs retail | distributed lags, AR(2), month FE, HAC | `erpt_usd_vs_neer.csv`, `erpt_border.csv`, `rate_correlations.csv` |
| `cpi_components/` | Inputs built from BNS form Т-15-02-М and regional CPI (not in `data/`): market core index, CPI by division, regional CPI, regional budget investment | accounting with official BNS weights | `market_core_index.csv`, `division_mm.csv`, `regional_*.csv` |

Choices made along the way, each argued in the script's docstring and the report:
- **gravity:** flows are WITS to 2019 and BNS from 2020 (WITS 2020–22 imports are
  incomplete); Russia and Belarus 2010 are dropped (the customs-union gap in WITS); the
  applied tariff turns out not to identify the trade elasticity (composition, not policy).
- **BVAR:** inflation instead of the CPI level (the log price level is close to I(2) here);
  the exchange rate before inflation in the ordering (with it last, the 2015 devaluation
  cannot reach prices in the quarter); the 2014–16 and 2020 quarters are down-weighted, which
  the marginal likelihood prefers by ~90 log points.
- **r\*:** maximum likelihood gives a gap with no persistence and no rate effect, so r* is
  not identified; the posterior mode with priors is reported next to it. The level of r* is
  weakly identified in 57 quarters — the report says so and gives the probability that
  policy is tighter than neutral rather than a precise number.

Tests: `tests/test_models.py` (synthetic data: PPML recovers known elasticities, the BVAR
marginal likelihood equals the chain of Student-t predictives, block exogeneity is exact, the
historical decomposition adds up, the Kalman filter tracks a simulated potential).
