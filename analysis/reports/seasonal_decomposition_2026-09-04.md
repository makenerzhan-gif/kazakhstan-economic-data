# Seasonal decomposition -- 2026-09-04

**DERIVED, NOT SOURCED.** Every number below is computed by
`scripts/decompose_seasonality.py` from `data/unified/macro_long.csv`. None of
it is published by БНС, НБ РК, Минфин, АРРФР, or the IMF; it does not belong
in `config/indicators.yaml`, `data/processed/`, or the sourced-data narrative
in `project_knowledge/`, and as of this report it is not synced into the
Claude Project. Treat every figure here as a starting point for a question,
not a finding on its own -- see Methodology and limitations at the end.

Curated set of 4 targets, hand-picked for having enough dense, gap-free history to make STL decomposition meaningful, and being genuinely seasonal in the classic sense -- not every monthly/quarterly indicator in the dataset. See `analysis/README.md` for the full feasibility sweep and why the rest were left out.

## CPI

**Headline CPI, month-over-month (already a comparison index)**

*Why this candidate:* Already a published MoM comparison index (observation_type=comparison_index, comparison_basis=mom, unit '% change vs previous month') -- decompose as published, same 'already a comparison, don't transform it' rule scripts/analysis/correlate.py already uses. Textbook seasonal candidate: 187 gap-free monthly points (2011-01..2026-07), 15.5x this pass's 3-cycle minimum.

- Prepared as: verified gap-free on a regular calendar grid; level as published (no growth-rate transform)
- Window: 2011-01-01 .. 2026-07-01 -- 187 observations, period=12 (monthly).
- **Seasonal strength: 0.174** (0-1 scale; see Methodology for the formula).
- Trend: 100.63 -> 100.75 (rose, 0.1% over the window).

Window includes the 2022 KZT devaluation's inflation spike and the 2020 COVID disruption -- both large, transient, non-seasonal shocks. robust=True exists specifically so neither distorts the seasonal estimate for the calendar month it happened to land in, rather than the shock's size being permanently attributed to that month every year.

![CPI average seasonal effect chart](charts/seasonal_CPI_2026-09-04.png)

**Average seasonal effect by calendar month:**

| Period | Mean seasonal effect | Cycles averaged |
|---|---|---|
| Jan | +0.25 | 16 |
| Feb | +0.34 | 16 |
| Mar | -0.11 | 16 |
| Apr | +0.02 | 16 |
| May | -0.08 | 16 |
| Jun | -0.22 | 16 |
| Jul | -0.20 | 16 |
| Aug | -0.21 | 15 |
| Sep | -0.14 | 15 |
| Oct | +0.06 | 15 |
| Nov | +0.22 | 15 |
| Dec | +0.12 | 15 |

## EXPORTS

**Exports (total), monthly level**

*Why this candidate:* Raw monthly trade-flow level (thousand USD, observation_type=period_total, no cumulation) -- decompose the level, not a growth rate: STL separates trend/seasonal/residual out of the level itself, and a growth-rate series would already be partially deseasonalized before STL ever saw it. 90 gap-free monthly points (2019-01..2026-06), 7.5x the minimum -- shorter margin than CPI, still comfortable.

- Prepared as: verified gap-free on a regular calendar grid; level as published (no growth-rate transform)
- Window: 2019-01-01 .. 2026-06-01 -- 90 observations, period=12 (monthly).
- **Seasonal strength: 0.204** (0-1 scale; see Methodology for the formula).
- Trend: 5,120,267.18 -> 6,498,146.54 (rose, 26.9% over the window).

Same COVID/devaluation shock-window caveat as CPI. Also exposed to global commodity-price swings unrelated to calendar seasonality -- a real seasonal signal here more plausibly reflects shipment/logistics timing than price.

![EXPORTS average seasonal effect chart](charts/seasonal_EXPORTS_2026-09-04.png)

**Average seasonal effect by calendar month:**

| Period | Mean seasonal effect | Cycles averaged |
|---|---|---|
| Jan | -216,590.64 | 8 |
| Feb | -569,393.06 | 8 |
| Mar | +19,533.71 | 8 |
| Apr | +22,392.81 | 8 |
| May | -56,310.06 | 8 |
| Jun | +244,866.01 | 8 |
| Jul | -111,213.33 | 7 |
| Aug | -43,975.58 | 7 |
| Sep | +590,501.60 | 7 |
| Oct | +293,924.14 | 7 |
| Nov | -96,793.61 | 7 |
| Dec | +15,737.31 | 7 |

## IMPORTS

**Imports (total), monthly level**

*Why this candidate:* Same construction as EXPORTS (thousand USD, period_total, no cumulation, 90 gap-free points 2019-01..2026-06) -- run alongside it, not instead of it: imports and exports can carry different seasonal patterns (domestic demand timing vs. what Kazakhstan exports).

- Prepared as: verified gap-free on a regular calendar grid; level as published (no growth-rate transform)
- Window: 2019-01-01 .. 2026-06-01 -- 90 observations, period=12 (monthly).
- **Seasonal strength: 0.688** (0-1 scale; see Methodology for the formula).
- Trend: 3,280,644.53 -> 5,698,918.46 (rose, 73.7% over the window).

Same COVID/devaluation and price-vs-timing caveat as EXPORTS.

![IMPORTS average seasonal effect chart](charts/seasonal_IMPORTS_2026-09-04.png)

**Average seasonal effect by calendar month:**

| Period | Mean seasonal effect | Cycles averaged |
|---|---|---|
| Jan | -853,440.82 | 8 |
| Feb | -738,901.55 | 8 |
| Mar | -482,973.93 | 8 |
| Apr | +155,619.06 | 8 |
| May | +139,334.60 | 8 |
| Jun | +120,290.11 | 8 |
| Jul | +436,885.67 | 7 |
| Aug | +288,239.52 | 7 |
| Sep | +43,672.28 | 7 |
| Oct | +366,179.99 | 7 |
| Nov | +105,796.54 | 7 |
| Dec | +429,247.73 | 7 |

## GDP_NOMINAL

**Nominal GDP, quarterly level (de-cumulated)**

*Why this candidate:* cumulation=year_to_date -- runs through scripts.lib.transformations.decumulate_ytd before decomposition (via timeseries.prepare_level), then decomposes the de-cumulated own-period level as published. 66 gap-free quarterly points (2010-01..2026-04), 16.5x the minimum -- the deepest margin of the four candidates.

- Prepared as: de-cumulated (year-to-date total -> own-period contribution); verified gap-free on a regular calendar grid; level as published (no growth-rate transform)
- Window: 2010-01-01 .. 2026-04-01 -- 66 observations, period=4 (quarterly).
- **Seasonal strength: 0.985** (0-1 scale; see Methodology for the formula).
- Trend: 4,864,601,452,928.95 -> 45,372,746,825,780.68 (rose, 832.7% over the window).

Nominal KZT GDP grew roughly an order of magnitude over this window from real growth, inflation, and the 2022 devaluation combined -- trend dominates the raw level's variance by construction, which is exactly why seasonal strength is reported as a share of seasonal-plus-residual variance, not total variance (see the report's Methodology section).

![GDP_NOMINAL average seasonal effect chart](charts/seasonal_GDP_NOMINAL_2026-09-04.png)

**Average seasonal effect by calendar quarter:**

| Period | Mean seasonal effect | Cycles averaged |
|---|---|---|
| Q1 | -3,276,960,179,222.67 | 17 |
| Q2 | -3,309,306,329,715.01 | 17 |
| Q3 | -586,281,769,399.75 | 16 |
| Q4 | +7,156,831,433,800.41 | 16 |

## Methodology and limitations

- Decomposition is STL (`statsmodels.tsa.seasonal.STL`, seasonal-trend
  decomposition via LOESS), run with `robust=True` on every target: each
  target's window contains at least one large, transient, non-seasonal shock
  (the 2020 COVID disruption, the 2022 KZT devaluation), and a non-robust fit
  would let one anomalous period bleed into the seasonal estimate for that
  calendar position across every year, not just the year it happened.
- Every target is required to clear 3 full seasonal cycles of
  history before decomposition runs at all (stricter than STL's own
  documented ~2-cycle minimum) -- refused, not attempted with a louder
  caveat, below that bar.
- **Seasonal strength** is `max(0, 1 - Var(resid)/Var(seasonal+resid))` (the
  standard Hyndman & Athanasopoulos measure), not `Var(seasonal)/Var(original)`.
  The difference matters for a strongly-trending series: the naive ratio would
  be dominated by trend and understate seasonality. 0 means the seasonal
  component explains nothing beyond noise; 1 means the residual is
  negligible next to it.
- STL's trend estimate is a LOESS smooth and is less reliable at the very
  start and end of the window than in the middle (less data on one side to
  smooth against) -- the reported trend start/end values inherit that edge
  effect and should be read as approximate, not exact boundary values.
- This is a curated set of hand-picked targets, not every monthly/quarterly
  indicator in the dataset -- see `analysis/README.md` for the full
  feasibility sweep and why the rest were left out.
