# model_data/ — model-ready panels

Derived by this repository, **not published by any source** — the same status as
`analysis/`, and the reason this is a top-level folder rather than part of `data/`.
Everything is built from `data/unified/` by `scripts/build_model_data.py` according to
`model_data/spec.yaml`:

```bash
python scripts/build_model_data.py   # after a pipeline update; not part of update_all.py
```

| File | What |
|---|---|
| `monthly.csv` | 1994-01 on: prices (chained CPI and components, PPI), activity (industrial production, retail, freight, trade, tax receipts), money and rates (base rate, TONIA, lending/deposit rates, KASE curve, M0-M3 at end of month), exchange rates, external block (Brent, Fed, UST, Russia, euro area, China), risk premia (Eurobond spread, carry) |
| `quarterly.csv` | national accounts at 2010 prices (BNS seasonally adjusted: GDP and demand components, mining, manufacturing), labour (employment, unemployment, wages, hours, capacity utilisation), external GDPs, quarterly means of the key monthly variables, and the production-function block: `gfcf_benchmarked`, `capital`, `labour_share`, `tfp_log` |
| `annual.csv` | the annual perpetual-inventory capital stock and its inputs |
| `VARIABLES.md` | one card per variable — source, operations, SA method, sample, columns, caveats — and the production-function assumptions with a sensitivity check |

Column suffixes: `_sa` seasonally adjusted, `_yoy` % change on a year earlier (from the
unadjusted level), `_saar` % annualised change on the previous period (from the adjusted
level). Rates and balances (`kind: rate`) get no logs or growth rates.

Conventions and choices, each explained in the script's docstring and the cards:
- periods are dated at their first day; stocks the source dates "as at the 1st" are moved
  to the end of the previous period;
- seasonal adjustment is STL (robust) on logs or levels; the official BNS/FRED adjustment is
  used where it exists (`sa: official`); X-13ARIMA-SEATS is not available here;
- policy rates are monthly means of the daily step function;
- quarterly means/sums/end values of monthly variables use complete quarters only;
- the capital stock is a perpetual inventory at 2010 prices with δ from BNS book depreciation;
  TFP is a Solow residual with α from the national-accounts labour share.

What a model user must still decide: the estimation sample (breaks: 2014-02 and 2015-08
devaluations, 2020, 2022), how to treat the Eurobond spread's missing 2020-11..2022-07, and
whether the high capital share (mining) suits the question.
