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
| `shapiro_goods/` | Demand- vs supply-driven goods inflation, contributions 2018-01 – 2026-04 | Shapiro (2022): sign of price and quantity residuals per CPI goods group | `contributions.csv` |
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

## Inflation models: what was checked on 2026-11-13 and what to keep in mind

All ten scripts of the inflation block (`svar_v2`, `bvar_sign*`, `bvar_market`, `shapiro_goods`, `erpt_*`,
`fiscal_lp`, `regional_fiscal_lp`) were re-run and reviewed line by line; every output here is regenerated on the
data of 2026-11-13, and `svar_v2.py` gives the same files on a second run.

**Corrected**
- Forecast-error variance shares are posterior means and add up to one (share-by-share medians summed to
  0.83-0.89 and understated demand and monetary policy by about 40 %). SVAR v2, 8 quarters: external 37.6 %,
  tenge 18.4 %, supply 16.8 %, demand 10.2 %, policy rate 8.1 %, tariffs 5.6 %, non-oil deficit 3.3 %.
- The decomposition to quote is `svar_v2/mean_<variant>.csv` (posterior means): it adds up to inflation exactly.
  Group-by-group medians (`changes_*`, `levels_*`) do not add up, and the median-target model
  (`median_target_*`) is one draw that can sit far from the centre in the latest quarters.
- `hd_v2.png` drew the non-oil deficit under the label of government consumption.
- `erpt_border.csv`: the import price index is «December of the previous year = 100» and was read as a monthly
  change; border pass-through for food from the NEER is 0.65, not 2.59.
- `erpt_usd_vs_neer.csv`: «перенос 12м» is now the cumulative 12-month response including the AR terms (food
  0.55, the lag sum alone 0.14); the lag sum and the long run are separate columns.
- `shapiro_goods`: the price innovation comes from the month-on-month equation, the band is robust, the weights
  are the official BNS ones (non-food 2019: 0.298, the estimated 0.410 was used before; 2015, 2018 and 2021 are
  not in the BNS file and are interpolated).
- `fiscal_lp`, `bvar_sign*`, `bvar_market`: the files were from the STL vintage of the data and did not
  reproduce; the industrial-production panel of `fiscal_lp` was built on a broken level (see `model_data`: `ip`).
- A quarter of GDP not yet in BNS's adjusted series is added through X-13 of the unadjusted level, not by
  applying a y/y index to the adjusted one.

**Not errors, but they limit what the results mean**
- *Tariff steps* are in effect the regulated CPI: 109 of 190 months are flagged and the correlation is 0.99.
- *Fiscal shock*: a recursive ordering on a deficit-to-GDP ratio; revenue and the denominator respond to
  activity within the quarter, so the shock is not a clean policy shock (the median price response is slightly negative, -0.07 to -0.10,
  and every 68 % band includes zero).
- *Levels versus changes*: the baseline drifts (54 % of the retained draws have a root slightly above one), so
  level contributions are relative to a different baseline in each variant; changes are robust.
- *`v2_ma4` and `v2_split`*: the innovation of a four-quarter average is not a structural shock in a VAR(2),
  and the three separately adjusted pieces of the split do not add up (0.22 pp on average, up to 0.52).
- *One rotation per reduced-form draw* is kept, so «accepted = 1000» is not an acceptance rate; the importance
  weights of Arias et al. for zero restrictions are not applied.
- *USD versus NEER*: the dollar's lead comes from 2022; without March 2022 - June 2023 its pass-through to the
  headline CPI is near zero. No positive 12-month pass-through here is significant at 5 % (food: 0.55, t = 1.4, and that t is an upper
  bound); the only significant ones are negative (alcohol and tobacco from the NEER, -0.07, t = -2.0).
- *`fiscal_lp`*: the «shock» is the level of a persistent budgeted flow, scaled to 1 % of GDP in a month, about
  7.6 standard deviations of what is observed.
- *`regional_fiscal`*: 20 clusters; two horizons are significant at the normal 5 % level (16 and 18 months, t = 2.0 and 2.2), one
  with a t(19) critical value, none without Turkestan oblast (t = 1.3 at 18 months).
- *Shapiro*: quantities exist only as y/y rates, so base effects still enter the quantity residual.
- BNS's seasonally adjusted GDP itself moves +6.5 % q/q in 2026Q2; the models take it as published.

**Not verified**: how `cpi_components/` (market core index, divisions, regional files) was built -- there is no
script for it in the repository; the amount removed from the deficit for July 2017 (2 135.8 bn tenge in the
code) against a primary source.

Tests: `tests/test_models_inflation.py` (the properties above), `tests/test_models.py` (synthetic data: PPML recovers known elasticities, the BVAR
marginal likelihood equals the chain of Student-t predictives, block exogeneity is exact, the
historical decomposition adds up, the Kalman filter tracks a simulated potential).
