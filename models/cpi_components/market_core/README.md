# Market core CPI (`cpi_components/market_core_index.csv`)

Builder: `python scripts/models/build_market_core.py [--out DIR] [--refresh-taldau] [--sa auto|x13|filter]`
(pandas and numpy; no network at run time). Sample 2011-01 to 2026-10, January 2011 = 100.

## Definition

Headline CPI of Kazakhstan without (a) fruit and vegetables, (b) petrol and diesel, (c) solid fuel
(coal), (d) regulated utility services (electricity, gas through the network, cold and hot water,
central heating, sewerage — BNS's own index «Коммунальные услуги регулируемые»).

BNS compiles the CPI on December of the previous year with weights fixed for the calendar year, so
within a year `H = Σ w_i·I_i` on indices with December = 100. The exclusion is therefore exact:

    core_ytd(t) = (H_ytd(t) − Σ_E w_i·I_i,ytd(t)) / (1 − Σ_E w_i),   core m/m = core_ytd(t) / core_ytd(t−1)

chained through December. This is `π_core = (π − Σ w_i π_i)/(1 − Σ w_i)` on month-on-month changes
with the weights price-updated inside the year; in January the two are the same formula. Applying
the annual weights to every monthly change unchanged gives a 12-month rate that differs by 0.05 pp
on average and up to 0.48 pp (column `mkt_base_fixedw` of `market_core_components.csv`). That the
December form is the one BNS uses is checked on its own index «без фруктов и овощей»: Decembers
2022–2025 are 120.24 / 109.80 / 108.50 / 112.60 at BNS and 120.25 / 109.82 / 108.55 / 112.57 here
(120.19 / 110.15 / 108.67 / 112.71 with unchanged monthly weights).

Columns: `mkt_base`; `mkt_low` / `mkt_high` — the weight of regulated utilities × 0.7 / × 1.3, the
component whose weight is least well known before 2020 and matters most; `*_sa` — X-13 through
`scripts/lib/x13.py` (log, Kazakh calendar) when the repository is there, otherwise a moving
seasonal filter (the report says which).

## Data

- Indices: BNS, Taldau index 703076 «Индекс потребительских цен», national, monthly, to the
  previous month and to December of the previous year, rounded to 0.1 — headline (term 4772381),
  fruit and vegetables (5259928), petrol (5259669), diesel (5259681), solid fuel (5259362),
  regulated utilities (4772564), CPI without fruit and vegetables (4772554), and the COICOP
  sub-indices of divisions 04 and 07. Kept in `taldau_cpi_cache.csv` (+ `_terms.csv`) in this folder; the
  script; `--refresh-taldau` re-downloads (16 requests) and is needed to add a month. The script
  checks the cache against `cpi_detail_mom/ytd.csv` and `bns/cpi_regulated_utilities.csv` and stops
  on a difference; today they are identical in every common month.
  Why not the repository files alone: they have no solid-fuel index after 2020, no petrol
  aggregate from 2026 (grades only), no December-based regulated-utilities index, and
  `frukty_i_ovoshchi` is missing for 2026-09 (Taldau: 95.7).
- Weights of divisions 04 and 07: `cpi_weights.csv` (BNS through the IMF, 2011–2019; BNS scheme
  2022), BNS brochures for 2020, 2021, 2023 (in `bns_cpi_weights_brochures.csv`, not yet in the
  repository), `cpi_weights_estimated.csv` for 2024–2026.
- BNS contributions to CPI growth: `cpi_contribution_ytd.csv` with `cpi_detail_ytd.csv` (2020 on).

## Weights by year, percent of the CPI basket

| year | fruit & veg | petrol | diesel | solid fuel | regulated utilities | excluded | market core | source |
|---|---|---|---|---|---|---|---|---|
| 2011 | 4.44 | 2.25 | 0.08 | 0.60 | 12.58 | 19.95 | 80.05 | R R D R R |
| 2012 | 3.48 | 2.56 | 0.10 | 0.70 | 12.88 | 19.71 | 80.29 | R R D R R |
| 2013 | 3.68 | 2.43 | 0.09 | 0.62 | 12.75 | 19.58 | 80.42 | R R D R R |
| 2014 | 4.53 | 2.83 | 0.11 | 0.96 | 10.73 | 19.15 | 80.85 | R R D R R |
| 2015 | 5.00 | 2.66 | 0.10 | 1.13 | 11.10 | 19.99 | 80.01 | R R D R R |
| 2016 | 6.21 | 2.63 | 0.10 | 1.30 | 10.56 | 20.80 | 79.20 | R R D R R |
| 2017 | 5.94 | 2.94 | 0.11 | 1.28 | 9.91 | 20.18 | 79.82 | O R D R R |
| 2018 | 5.87 | 3.17 | 0.12 | 1.57 | 9.87 | 20.60 | 79.40 | R R D R R |
| 2019 | 6.18 | 3.21 | 0.12 | 1.42 | 8.86 | 19.79 | 80.21 | O R D R R |
| 2020 | 6.00 | 3.10 | 0.12 | 1.70 | 8.60 | 19.51 | 80.49 | O C D C C |
| 2021 | 5.84 | 3.06 | 0.11 | 1.49 | 5.50 | 16.00 | 84.00 | O C D C C |
| 2022 | 6.14 | 2.50 | 0.09 | 1.60 | 5.77 | 16.10 | 83.90 | O C D C C |
| 2023 | 5.74 | 2.38 | 0.09 | 1.64 | 5.61 | 15.46 | 84.54 | O C D C C |
| 2024 | 6.27 | 2.39 | 0.09 | 1.39 | 5.17 | 15.31 | 84.69 | C C D C C |
| 2025 | 5.73 | 4.73 | 0.18 | 0.66 | 3.52 | 14.82 | 85.18 | C C D C C |
| 2026 | 5.66 | 3.40 | 0.13 | 0.78 | 3.86 | 13.83 | 86.17 | R C C C C |

Source letters, in column order:

- **O official** — BNS brochure «Индекс потребительских цен: вопросы и ответы», «Схема взвешивания
  для расчета ИПЦ» (fruit and vegetables only; BNS publishes no weight for petrol, diesel, coal or
  utilities in any year).
- **C implied by BNS contributions** — contribution of the item to CPI growth since December divided
  by the item's growth, `w = 100·Σc·d / Σd²`, `d = I_ytd − 100`; used when the rounding error is
  below 10 % of the weight. Regulated utilities = the sum of the six items. Where an official
  figure exists the method returns it: fruit and vegetables 6.02 / 5.83 / 6.13 / 5.74 against
  official 6.00 / 5.84 / 6.14 / 5.74 (2020–2023).
- **R regression** — non-negative least squares of a published aggregate on its complete set of
  published children, shares summing to one, December = 100, the twelve months of the year;
  residuals 0.04–0.10 index points, i.e. the rounding of the data. Fruit and vegetables: CPI on
  [CPI without fruit and vegetables, fruit and vegetables]. Petrol: division 07 → operation of
  personal transport → fuels and lubricants → petrol, times the official division weight. Solid
  fuel and regulated utilities: division 04 → [rent, maintenance, water and other services,
  energy] → their children, times the official division weight; for regulated utilities the mean
  of this and of a direct regression of division 04 on BNS's regulated-utilities index and the
  rest (2015, 2016: the first only, the second fits badly).
- **D** — diesel: the 2026 implied diesel/petrol ratio (0.038) times the petrol weight. Diesel is
  not identified by regression (0–0.5 %) and does not matter (see sensitivity).

`market_core_weights_detail.csv` has every alternative estimate per year and component.

## Validation

1. **Identity.** `H = (1−W)·core + Σ w_i·I_i` holds to 4·10⁻¹⁴ in the December form in every month.
   Rebuilt month on month from the published m/m indices (all rounded to 0.1) the headline m/m is
   reproduced within 0.14 pp in every month (0.04–0.14 by year).
2. **Weights.**
   - Regression against official, fruit and vegetables: 5.76 / 5.95 / 6.21 / 5.69 / 6.29 / 6.00
     against 5.94 / 6.18 / 6.00 / 5.84 / 6.14 / 5.74 (2017, 2019–2023): error up to 0.26.
   - Regression against contribution-implied, 2020–2026: petrol mean |error| 0.21 (0.09 without
     2026; 2026: 2.49 against 3.40 from a single month of contributions), solid fuel 0.13 (max
     0.27), regulated utilities 0.39 (max 1.33, in 2020).
   - Solid fuel + regulated utilities are 70–76 % of division 04 in 2011–2020 and 38–52 % from
     2021; petrol + diesel 29–41 % of division 07 (63 % in 2025).
   - CPI without fruit and vegetables against BNS's: m/m mean |difference| 0.04 pp, max 0.12.
     CPI without fruit and vegetables, petrol and solid fuel against BNS's core (без фруктов и
     овощей, бензина и угля): m/m mean |difference| 0.045 pp, max 0.21; 12-month rates mean
     |difference| 0.14, by year 0.02–0.19 except 2024 (0.46) and 2025 (0.33) — see the last section.
3. **Sensitivity** of 12-month market core inflation to a ±30 % change of one weight, mean / max
   over all months, pp: regulated utilities 0.19 / 0.60 (December 2019: −0.45 / +0.48 for −30 % / +30 %; 2022: −0.38 / +0.39),
   fruit and vegetables 0.12 / 0.44, petrol 0.08 / 0.21, solid fuel 0.02 / 0.07, diesel
   0.01 / 0.02. Table by December: `market_core_sensitivity.csv`.

## Limitations

- No official weight exists for four of the five components. Before 2020 all of them are
  regression estimates (fruit and vegetables: official in 2017 and 2019). For regulated utilities
  the two regressions differ by 0–1.8 pp of the basket (2011: 13.5 and 11.7); 2020 is 8.6 from
  contributions and 7.0–7.5 by regression, and the contributions of that year are not stable from
  month to month. `mkt_low` / `mkt_high` cover this.
- The regulated-utilities weight falls from 8.6 (2020) to 5.5 (2021) with the new BNS basket; both
  the contributions and the regressions show the fall.
- 2026 (COICOP 2018 basket): no contribution is published for fruit and vegetables (regression) and
  for petrol only January (3.40; the regression gives 2.49 with a poor fit). Weights of the current
  year are re-estimated on each refresh.
- "Coal" is BNS's «Твёрдое топливо» (coal and firewood; coal is about three quarters of it in
  2026), the item whose weight can be identified; BNS's core excludes «уголь».
- All inputs are rounded to 0.1: a monthly change of the index carries about ±0.05 pp, a 12-month
  rate about ±0.1 pp. The error does not accumulate inside a year (December-based indices).
- The brochure headed «используемая в 2016г.» carries the weights that the IMF series and the
  press give for 2017; it is used as 2017.

## Comparison with the previous file (no builder script)

The previous `mkt_base` reproduces within 0.03 pp in all 186 months as

    (BNS core ex F&V, petrol, coal, m/m rounded to 0.1 − u · regulated utilities m/m) / (1 − u)

with `u` = 0.0673 of the BNS core basket for 2011–2023, 0.0607 for 2024, 0.045 for 2025–2026
(6.0–6.1 %, 5.5 %, 4.1 % of the CPI); `mkt_low` / `mkt_high` use 0.7·u / 1.3·u. Diesel was not
excluded. It started in 2011-02 and ended in 2026-08.

Month on month, old − new, 2011-03 to 2026-08: mean −0.005, mean |·| 0.060, max 0.29 pp (2013-01);
by year mean |·| 0.03–0.09. Twelve-month rates: mean −0.06, mean |·| 0.26, max 0.74 pp (2013-03);
above 0.5 pp in 15 of 175 months. Level in 2026-08: old/new = 0.990.

| 12-month, % | headline | old | new | new low / high | BNS core ex 3 | BNS core ex 7 | old − new | of which starting index | utilities weight | diesel |
|---|---|---|---|---|---|---|---|---|---|---|
| 2015-12 | 13.6 | 14.35 | 14.16 | 14.02 / 14.31 | 13.9 | – | +0.19 | +0.42 | −0.20 | −0.03 |
| 2016-12 | 8.5 | 8.77 | 8.86 | 8.83 / 8.88 | 8.8 | – | −0.08 | −0.09 | −0.03 | +0.04 |
| 2017-12 | 7.1 | 6.24 | 6.31 | 6.38 / 6.23 | 6.5 | – | −0.07 | −0.20 | +0.09 | +0.04 |
| 2018-12 | 5.3 | 6.69 | 6.88 | 6.72 / 7.07 | 6.4 | – | −0.20 | −0.01 | −0.22 | +0.03 |
| 2019-12 | 5.4 | 6.84 | 7.16 | 6.71 / 7.64 | 5.9 | – | −0.33 | +0.16 | −0.48 | −0.01 |
| 2020-12 | 7.5 | 7.42 | 7.94 | 7.75 / 8.15 | 7.2 | – | −0.53 | −0.31 | −0.20 | −0.02 |
| 2021-12 | 8.4 | 8.03 | 8.05 | 7.97 / 8.13 | 7.9 | – | −0.01 | −0.09 | +0.03 | +0.05 |
| 2022-12 | 20.3 | 22.68 | 22.21 | 21.84 / 22.60 | 21.2 | 22.4 | +0.47 | +0.41 | +0.07 | −0.01 |
| 2023-12 | 9.8 | 8.76 | 9.02 | 9.24 / 8.79 | 9.4 | 8.8 | −0.26 | −0.20 | −0.06 | +0.01 |
| 2024-12 | 8.6 | 7.62 | 7.98 | 8.22 / 7.74 | 8.3 | 7.6 | −0.37 | −0.31 | −0.05 | −0.01 |
| 2025-12 | 12.3 | 12.91 | 12.72 | 12.63 / 12.81 | 12.4 | 12.7 | +0.19 | +0.14 | +0.04 | 0.00 |
| 2026-08 | 9.8 | 11.39 | 11.02 | 10.84 / 11.21 | 10.7 | 11.2 | +0.37 | +0.26 | +0.11 | 0.00 |
| 2026-10 | 9.3 | – | 9.93 | 9.93 / 9.93 | 10.0 | 10.0 | – | – | – | – |

(BNS core ex 3 = без фруктов и овощей, бензина и угля; ex 7 = also without housing and utility
services, rail transport, communications and diesel.)

Where the two differ:

- **Utilities weight, 2011–2020.** The old file holds regulated utilities at 6 % of the CPI. The
  official weight of division 04 was 14.3–17.8 % in those years and regulated utilities are
  59–72 % of it by the estimates here (8.6–12.9 % of the CPI); 6 % is the 2021–2023 level carried
  back. With the larger weight the tariff cut of 2019 (regulated utilities −6.9 %) lifts the core
  to 7.2 % instead of 6.8 %. From 2021 the two weights are close (6.05 against 5.5; 4.05 against
  3.5) and this term is below 0.1 pp. The new file is the better one here; its own uncertainty is
  the low/high band.
- **Starting index.** The old file chains BNS's core m/m, rounded to 0.1. Twelve of them differ
  from BNS's own year-on-year core by 0.09 pp on average and up to 0.32 (Decembers: +0.20 in 2015,
  −0.18 in 2020, +0.17 in 2025), and the error stays in the level. The new index is computed from
  December-based indices, where rounding does not accumulate within the year.
- **BNS core in 2023–2024.** BNS's core is below its own CPI without fruit and vegetables in
  December 2024 (108.3 against 108.5), although the two further exclusions are petrol (+0.8 %) and
  coal (+8.6 %) and can only raise it: exact arithmetic gives 108.7 (2023: 109.4 at BNS, 109.7
  here). The old file inherits this; the new one does not depend on BNS's core.
- **Diesel** is immaterial (weight about 0.1 %).

## Files

`market_core_index.csv` (the index; same columns as the previous file, plus the 2011-01 row),
`market_core_components.csv` (headline, components, weights, m/m of the core, the unchanged-weights
variant, the index without fruit and vegetables, petrol and solid fuel), `market_core_weights.csv`,
`market_core_weights_detail.csv`, `market_core_sensitivity.csv`, `market_core_old_vs_new_12m.csv`,
`market_core_old_vs_new_decomposition.csv`, `market_core_old_vs_new_mom_by_year.csv`,
`market_core_report.txt` (the full run log), `bns_cpi_weights_brochures.csv`.
