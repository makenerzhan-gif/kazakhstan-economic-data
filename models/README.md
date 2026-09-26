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
```

None of them is part of `update_all.py`: re-run them when the inputs change.

| Folder | Model | Method | Main outputs |
|---|---|---|---|
| `gravity/` | Kazakhstan's exports and imports by partner, 2000–2025 | PPML (Santos Silva & Tenreyro 2006), year FE and partner + year FE; log-OLS benchmark | `coefficients.csv`, `potential.csv` (actual / predicted by partner), `panel.csv` |
| `bvar/` | Brent, Fed funds, RUB/USD → GDP, USD/KZT, inflation, TONIA; 2011Q2–2026Q1 | Minnesota prior by dummy observations, λ/μ by marginal likelihood, block exogeneity (Gibbs), crisis quarters with scaled volatility (Lenza & Primiceri 2022), recursive identification | `irf.csv`, `fevd.csv`, `historical_decomposition.csv`, `forecast.csv` |
| `rstar/` | r*, trend growth, potential output, output gap; 2012Q1–2026Q1 | Holston–Laubach–Williams-type state space, Kalman filter, posterior mode with QPM-style priors; production-function and HP gaps, interest-parity floor as cross-checks | `states.csv`, `gaps.csv`, `parameters.csv`, `sensitivity.csv` |

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
