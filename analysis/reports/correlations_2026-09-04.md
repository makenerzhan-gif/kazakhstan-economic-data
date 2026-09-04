# Correlation analysis -- 2026-09-04

**DERIVED, NOT SOURCED.** Every number below is computed by
`scripts/analyze_correlations.py` from `data/unified/macro_long.csv`. None of
it is published by БНС, НБ РК, Минфин, АРРФР, or the IMF; it does not belong
in `config/indicators.yaml`, `data/processed/`, or the sourced-data narrative
in `project_knowledge/`, and as of this report it is not synced into the
Claude Project. Treat every figure here as a starting point for a question,
not a finding on its own -- see Methodology and limitations at the end.

Curated set of 8 pairs, hand-picked for shared history and a plausible economic relationship -- not an all-pairs matrix. See `analysis/README.md` for the full candidate list and why the rest were left out of v1.

## CPI_YOY vs CORE_CPI_YOY_EX3

**Headline vs core inflation (ex-3)**

*Why this pair:* Both already-published YoY comparison indices (observation_type=comparison_index) sharing the same base convention; core (ex food and energy-adjacent items) should broadly track headline inflation.

| | CPI_YOY | CORE_CPI_YOY_EX3 |
|---|---|---|
| Transform applied | used as-is (already a published comparison) | used as-is (already a published comparison) |

- Overlap window: 2023-01-01 .. 2026-07-01 -- 42 observations.
- **Pearson r = 0.991** (p = <0.001, significant at 5%; survives Bonferroni correction)

Strong co-movement is expected here almost by construction -- core is a subset of the same basket headline is built from. A weak reading would be the surprising result worth chasing, not a strong one.

## OIL_PRICE vs EXCHANGE_RATE

**Oil price vs USD/KZT**

*Why this pair:* Classic oil-exporter pass-through question: does a costlier or cheaper barrel show up in the tenge the same month.

| | OIL_PRICE | EXCHANGE_RATE |
|---|---|---|
| Transform applied | period-over-period % change (transformations.growth_rate) | resampled daily -> monthly (mean, per config/frequency.yaml); period-over-period % change (transformations.growth_rate) |

- Overlap window: 2021-06-01 .. 2026-07-01 -- 62 observations.
- **Pearson r = 0.063** (p = 0.627, not significant at 5%)

NBK manages the exchange rate rather than floating it freely, so a same-month linear read may understate a lagged or asymmetric response -- see the lag scan below for whether shifting the two series relative to each other finds a stronger reading. Resampling the daily rate to a monthly mean also blurs when in the month a move happened, and the overlap window folds very different regimes (COVID recovery, the 2022 devaluation, disinflation) into one number.

**Lag scan** (positive lag = OIL_PRICE leads EXCHANGE_RATE):

| Lag (periods) | r | p | n |
|---|---|---|---|
| -3 | 0.013 | 0.922 | 59 |
| -2 | -0.033 | 0.803 | 60 |
| -1 | -0.168 | 0.197 | 61 |
| +0 (contemporaneous) | 0.063 | 0.627 | 62 |
| +1 | -0.045 | 0.731 | 62 |
| +2 | 0.060 | 0.642 | 62 |
| +3 | -0.040 | 0.760 | 61 |

Strongest same-window reading: lag -1, r = -0.168, p = 0.197, not significant at 5% (n=61). Descriptive only -- scanning multiple lags means this is the best of several looks, not a confirmed finding on its own; see Methodology.

## REER vs CPI

**Real effective exchange rate vs headline inflation**

*Why this pair:* REER is meant to net out relative price levels against trading partners; checking it against domestic CPI is a natural first read.

| | REER | CPI |
|---|---|---|
| Transform applied | used as-is (already a published comparison) | used as-is (already a published comparison) |

- Overlap window: 2011-01-01 .. 2026-06-01 -- 186 observations.
- **Pearson r = -0.197** (p = 0.007, significant at 5%; does not survive Bonferroni correction)

This compares a slow-moving fixed-base level index against a fast month-over-month comparison -- a weak correlation is expected from that mismatch in what's being measured, not necessarily evidence of no relationship.

## NEER vs CPI

**Nominal effective exchange rate vs headline inflation**

*Why this pair:* Same question as REER vs CPI without the inflation adjustment already baked into the index, run alongside it for comparison.

| | NEER | CPI |
|---|---|---|
| Transform applied | used as-is (already a published comparison) | used as-is (already a published comparison) |

- Overlap window: 2011-01-01 .. 2026-07-01 -- 187 observations.
- **Pearson r = -0.245** (p = <0.001, significant at 5%; survives Bonferroni correction)

Same level-vs-comparison mismatch caveat as REER vs CPI.

## GOV_REVENUE vs GOV_EXPENDITURE

**Budget revenue vs expenditure**

*Why this pair:* Both minfin, annual, verified to share the same period-end (12-31) date convention over the same 2014-2025 window -- one of the cleanest-matched pairs in the whole dataset.

| | GOV_REVENUE | GOV_EXPENDITURE |
|---|---|---|
| Transform applied | period-over-period % change (transformations.growth_rate) | period-over-period % change (transformations.growth_rate) |

- Overlap window: 2015-12-31 .. 2025-12-31 -- 11 observations.
- **Pearson r = 0.904** (p = <0.001, significant at 5%; survives Bonferroni correction)

- n=11 -- small sample; treat as descriptive, not confirmatory.

Only 12 annual observations means roughly 11 usable points after taking growth rates -- treat any result as descriptive, not confirmatory, regardless of how large the coefficient is.

## OIL_PRICE vs OIL_EXPORTS_VALUE

**Oil price vs crude export value**

*Why this pair:* Tests whether more expensive oil shows up in the value of what BNS records as actually exported, independent of the exchange-rate pass-through question above.

| | OIL_PRICE | OIL_EXPORTS_VALUE |
|---|---|---|
| Transform applied | period-over-period % change (transformations.growth_rate) | period-over-period % change (transformations.growth_rate) |

- Overlap window: 2019-02-01 .. 2026-06-01 -- 88 observations.
- **Pearson r = -0.170** (p = 0.114, not significant at 5%)

Export value moves with shipped volume as well as price, and volume has its own logistics-driven variation independent of price -- a weak reading doesn't mean price is irrelevant to revenue, only that value alone doesn't isolate the price effect. See OIL_PRICE vs OIL_EXPORTS_VOLUME below for a direct check of that volume-noise explanation, and the lag scan for whether a shipment/settlement delay between a price move and its showing up in recorded export value fits better than same-month.

**Lag scan** (positive lag = OIL_PRICE leads OIL_EXPORTS_VALUE):

| Lag (periods) | r | p | n |
|---|---|---|---|
| -3 | 0.163 | 0.137 | 85 |
| -2 | -0.075 | 0.492 | 86 |
| -1 | -0.140 | 0.197 | 87 |
| +0 (contemporaneous) | -0.170 | 0.114 | 88 |
| +1 | -0.096 | 0.378 | 87 |
| +2 | 0.247 | 0.022 | 86 |
| +3 | 0.746 | <0.001 | 85 |

Strongest same-window reading: lag +3, r = 0.746, p = <0.001, significant at 5%; survives Bonferroni correction (n=85). Descriptive only -- scanning multiple lags means this is the best of several looks, not a confirmed finding on its own; see Methodology.

## CPI_YOY vs CORE_CPI_YOY_EX7

**Headline vs core inflation (ex-7)**

*Why this pair:* Same question as headline vs core (ex-3) above, with the wider exclusion basket -- run alongside it rather than in place of it, since the two core measures can diverge from each other even when both track headline.

| | CPI_YOY | CORE_CPI_YOY_EX7 |
|---|---|---|
| Transform applied | used as-is (already a published comparison) | used as-is (already a published comparison) |

- Overlap window: 2023-01-01 .. 2026-07-01 -- 42 observations.
- **Pearson r = 0.980** (p = <0.001, significant at 5%; survives Bonferroni correction)

Same construction caveat as CPI_YOY vs CORE_CPI_YOY_EX3: strong co-movement is the expected result, not evidence of anything beyond core being a subset of the headline basket.

## OIL_PRICE vs OIL_EXPORTS_VOLUME

**Oil price vs crude export volume**

*Why this pair:* Direct counterpart to OIL_PRICE vs OIL_EXPORTS_VALUE: if price and volume move independently, that's the mechanism behind value's weak correlation with price above, not evidence price doesn't matter.

| | OIL_PRICE | OIL_EXPORTS_VOLUME |
|---|---|---|
| Transform applied | period-over-period % change (transformations.growth_rate) | period-over-period % change (transformations.growth_rate) |

- Overlap window: 2019-02-01 .. 2026-06-01 -- 88 observations.
- **Pearson r = -0.048** (p = 0.655, not significant at 5%)

A near-zero reading here is the supporting case for that explanation; a strong one (in either direction) would mean the value result above needs a different explanation. Same lag scan as the value pair, for the same reason.

**Lag scan** (positive lag = OIL_PRICE leads OIL_EXPORTS_VOLUME):

| Lag (periods) | r | p | n |
|---|---|---|---|
| -3 | 0.124 | 0.260 | 85 |
| -2 | -0.060 | 0.581 | 86 |
| -1 | -0.015 | 0.891 | 87 |
| +0 (contemporaneous) | -0.048 | 0.655 | 88 |
| +1 | -0.058 | 0.592 | 87 |
| +2 | -0.068 | 0.532 | 86 |
| +3 | 0.095 | 0.385 | 85 |

Strongest same-window reading: lag -3, r = 0.124, p = 0.260, not significant at 5% (n=85). Descriptive only -- scanning multiple lags means this is the best of several looks, not a confirmed finding on its own; see Methodology.

## Methodology and limitations

- Correlation is Pearson (`scipy.stats.pearsonr`, which also gives the
  p-value below -- the same r `pandas.Series.corr` would give), computed on
  the transform stated per indicator above, over the intersection of
  available dates for each pair.
- The p-value tests the null hypothesis of no linear correlation (rho=0)
  against a t-distribution, which assumes the underlying data is
  approximately bivariate normal -- not verified for any series here, and
  probably false for some of them (growth rates in particular can be
  skewed). Read it as a rough guide, not an exact one, especially at the
  small sample sizes some of these pairs have.
- "Significant at 5%" below means p < 0.05
  for that single test in isolation.
- **Multiple comparisons.** This report represents 26 distinct tests
  (one per pair, plus one per non-zero lag on the pairs with a lag scan --
  a lag scan's own contemporaneous point is the same test as that pair's
  headline, not counted again). At 5% uncorrected,
  roughly 1 in 20 tests would clear the bar by chance alone even with no
  real relationship anywhere in the data, and a lag scan's "strongest
  reading" is the best of several such tests by construction. "Survives
  Bonferroni correction" below means p < 0.0019
  (0.05 / 26, the standard conservative adjustment
  for testing 26 hypotheses in one report). Treat a reading that is
  significant uncorrected but does not survive correction as a lead worth
  checking again with fresh data, not a conclusion.
- Significant is not the same as strong: the p-value mainly reflects sample
  size, so a large-n pair can flag "significant" on a coefficient too weak
  to matter for anything (REER and NEER vs CPI both do exactly this in this
  report -- n>180 makes r around -0.2 to -0.25 clear the bar easily), while
  a genuinely strong relationship at small n can fail to. Read the r value
  for how strong the relationship is; read the p-value only for how
  confidently this sample rules out "no relationship at all."
- Correlation is not causation, and none of the above controls for
  confounders.
- This is a curated set of hand-picked pairs, not an all-pairs matrix over
  every indicator in the dataset -- see `analysis/README.md` for the full
  candidate list and why the rest were left out.
