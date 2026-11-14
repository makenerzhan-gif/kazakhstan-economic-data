# Verification of the fixes to the inflation models (2026-11-13)

Read-only check. Code was run on a copy in `scratchpad/verify_fix/repo` (scripts, models, model_data, tools, config
copied; `data/` read through a symlink). Own recomputation scripts: `verify_fix/t_gdp.py`, `t_erpt.py`, `t_border.py`,
`t_shapiro.py`, `t_misc.py`, `alt/scripts/models/regional_noTRK.py`.

Note on the reference commit: while the check ran, the working-tree changes were committed as `e3a5aff3f`; the `ip`
change is the earlier commit `0dbbb0e30`. `git diff HEAD` is now empty; the diffs below are against `caa2a24ba`
(models) and `0dbbb0e30^` (model_data).

Summary: 1 WRONG (Shapiro contributions have a two-year hole), 5 PARTLY (ip, GDP extension, erpt_neer s.e. note,
README, tests), 4 CORRECT.

---

## 1. model_data `ip` — PARTLY (the fix is correct; one property of the level is not stated)

Correct:
- Own rebuild of the level (2014 from the m/m chain, later months = level a year earlier x y/y) equals
  `model_data/monthly.csv: ip` to 5e-7 for all 153 months 2014-01..2026-09; no missing month in either source.
- `ip_yoy` equals the published `ind_prod_monthly_yoy.csv` - 100 for all 141 months 2015-01..2026-09 (max diff 6e-15).
- Annual means against the official annual index (`ind_prod.csv`), built / official: 2015 98.37/98.4, 2016 98.85/98.9,
  2017 107.43/107.3, 2018 104.06/104.4, 2019 103.85/104.1, 2020 99.24/99.5, 2021 103.65/103.6, 2022 101.00/101.2,
  2023 104.27/104.4, 2024 102.81/103.2, 2025 107.54/107.7. Max gap 0.39 (2024). "Reproduces" holds to 0.4 point.
- Base: January 2014 = 100 (the 2014 mean is 111.85), not "2014 = 100". Harmless, but nowhere stated.
- Gaps: a period whose value a year earlier is missing stays missing, and stays missing in every later year (tested).
  Edge case not triggered by the data: `scripts/build_model_data.py:114` `chain(base.dropna()).iloc[:per_year]` takes
  the first 12 available observations, so a gap in the base year would be chained across and spill into the next year.
- Nothing else changed: against `0dbbb0e30^`, `monthly.csv` differs only in `ip`, `ip_sa`, `ip_yoy`, `ip_saar`;
  `quarterly.csv` is identical (same columns, same index).
- `ip_sa`: annual mean of SA/NSA 1.000-1.002; y/y of `ip_sa` against the published y/y: mean abs gap 0.78 pp, max 3.3.

Not stated, and matters for any user of the unadjusted level:
- Each calendar month is its own chain, so the within-year profile of `ip` is not the published one. Cumulative log
  growth 2014 -> 2026 by calendar month: January +13.9, February +47.5, March +52.6, April +49.5, October +9.8 (2025),
  the others +23..+37. The level therefore goes 167.7 (Dec 2025) -> 114.0 (Jan 2026) -> 160.6 -> 197.2 (Mar 2026):
  -32 % and +41 % month on month against the published m/m 78.5 and 124.5; March/January is 1.73 against 1.15 in 2014.
  X-13 absorbs this as moving seasonality (M7 0.45, Q 0.51), so `ip_sa` and `ip_yoy` are usable; the month-on-month
  change of the unadjusted `ip` is not.
- January 2026: published y/y 93.4 between 108.1 and 103.2. `ip_sa` falls 12.8 % and rebounds 15.4 %;
  `ip_saar` = -80.6 and +460.4. This is the source (X-13 marks AO2026.Jan), not the construction, and it sits inside
  the `fiscal_lp` sample (to 2026-06).

Correction: add to the `ip` note in `model_data/spec.yaml:72` (and VARIABLES.md): "January 2014 = 100. Use `ip_yoy`
and `ip_sa`; the month-on-month change of the unadjusted level is not the published one (each calendar month is a
separate y/y chain). January 2026 is an outlier in the source (y/y 93.4)."

## 2. FEVD shares — CORRECT

- `svar_v2.py:165-173`: per-draw share (sum over horizons 0..8 and over the group's shocks, divided by the draw's
  total), then mean over draws; assert on the sum. `bvar_sign.py:218`: mean over axis 0 (draws) of shares already
  normalised across shocks per draw. Both right.
- Row sums of `summary.csv`: 1.000, 1.000, 1.000, 0.999, 1.000, 1.001, 1.000. `fevd_infl_*.csv`: 99.9..100.1 (rounding
  to one decimal).
- Re-run in the same seed order reproduces v2: external 0.376, tenge 0.184, supply 0.168, demand 0.102, monetary
  0.081, tariffs 0.056, deficit 0.033.

## 3. `posterior_mean`, `mean_*.csv`, `hd_v2.png` — CORRECT

- Seven files; contributions + baseline - actual: max 0.002-0.003 (three-decimal rounding). Same index and same
  `actual` as `median_target_*.csv`.
- Legitimate: the means are over the same retained draws as every other output (`grp_y`, `base_y` from one loop);
  NaN occurs only in the first three quarters of every draw (4-quarter rolling mean), so `nanmean` equals `mean`
  elsewhere and those quarters are dropped. (It prints "Mean of empty slice" warnings; cosmetic.)
- 2024Q4 -> 2025Q4 from `mean_v2.csv`: tenge +2.26, demand +1.20, monetary +0.65, baseline +0.16, supply -0.52,
  external -0.13, tariffs -0.10, deficit -0.10 = +3.42 = actual. Group medians in `changes_v2.csv` sum to 2.64
  (miss 0.78), as the docstring says.
- `hd_v2.png` (inspected): title "апостериорные средние", legend "Бюджет (ненефтяной дефицит)", seven groups plus
  the line, no label lost or duplicated. `colour_of` rebuilds the dict with the key renamed and the order kept;
  with `None` nothing changes. `bvar_sign_ext.py` own call: `hd_cpi_ext.png` reproduces byte for byte.
- Worth knowing: mean and median-target differ a lot in 2026Q2 (tenge 0.74 vs 2.26, external -0.52 vs -1.46). The
  README says which to quote.

## 4. GDP extension in `svar_v2_data.py` — PARTLY

- Not triggered: `gdp_sa` reaches 2026Q2 (11 163 840, +6.50 % q/q); `ahead` is empty.
- The branch runs on truncated copies:

| truncated | 2026Q1 q/q | 2026Q2 q/q | published |
|---|---|---|---|
| gdp_sa and gdp_nsa without 2026Q2 | -1.22 | +4.76 | +6.50 |
| gdp_sa without 2026Q2, gdp_nsa complete | -1.22 | +7.90 | +6.50 |
| both without 2026Q1-Q2 | -0.04 | +2.25 | -1.22, +6.50 |
| gdp_sa without 2026Q1-Q2, gdp_nsa complete | -2.55 | +7.90 | -1.22, +6.50 |

  Plausible, and closer to BNS than the old rule (+2.7), but 1.3-1.8 pp from the published figure.
- The stated reason for the change does not distinguish the two series: the discrete y/y index misses the y/y of
  `gdp_nsa` by 1.52 pp on average (max 8.9; 2026Q2: 8.16 vs 5.18), the same as for `gdp_sa` (1.45 pp). The index is
  on another basis (production, tables 4439/4440) than the QNA. The extension is still a nowcast with an error of
  about 1.5 pp q/q.
- Stale text: `scripts/models/svar_v2_data.py:16-17` still says "gdp_sa 2026Q2: extended with the BNS discrete-quarter
  volume index (105.184 y/y) applied to the SA level of 2025Q2 -- assumes an unchanged seasonal factor", and the
  comment at `:139` "GDP SA 2026Q2 from the discrete y/y volume index".

Correction: replace lines 16-17 with "gdp_sa: quarters beyond BNS's adjusted series (none on 2026-11-13) get the q/q
growth of an X-13 adjustment of gdp_nsa extended by the discrete y/y index; the index misses the y/y of gdp_nsa by
1.5 pp on average, so such a quarter is a nowcast"; drop the comment at 139.

## 5. `erpt_border.py` — CORRECT

- Conversion: January = ln(I/100), other months ln(I_t/I_{t-1}); the within-year cumulative sum of my m/m equals
  ln(I/100) for IV, VI, XI, XII, XVI. No missing month in 2020-01..2026-07 (79 months); a missing month would give
  NaN in that month and the next (not in a following January).
- Own regressions reproduce `erpt_border.csv` to three decimals:

| | border<-USD (t) | border<-NEER (t) | retail<-import 6m (t) | n |
|---|---|---|---|---|
| Clothing (XI+XII) | 0.336 (1.17) | 0.253 (1.48) | -0.128 (-4.16) | 72 |
| Household goods (XVI) | 0.311 (3.94) | 0.217 (2.68) | 0.401 (3.06) | 72 |
| Food (IV) | 0.548 (2.29) | 0.650 (3.77) | 0.107 (2.78) | 72 |
| Health (VI) | 0.795 (5.43) | 0.457 (3.63) | 0.057 (0.96) | 72 |

  (Stage 1 has 78 observations; `n` is the stage-2 sample.)

## 6. `erpt_neer.py` `cumulative`, `cumulative_t` — CORRECT, with one caveat on the s.e.

- Recursion: c_h is the response of the m/m change at horizon h, the sum over h = 0..12 is the level. Equal to
  sum_k b_k * A(12-k), A = cumulated AR(2) impulse coefficients (checked to 1e-10).
- Delta method: analytic gradient (A(12-k) for b_k, central differences for r1, r2) with the HAC covariance gives the
  same t as the CSV for all 22 regressions (max diff 5e-4 = rounding).
- Recomputed rows: food USD 0.547 (t 1.39), lag sum 0.141 (2.28), long run 0.576; household goods USD 0.410 (1.02),
  lag sum 0.099, long run 0.459; weighted 0.276 / -0.020. All as in the file.
- Caveat: the response is non-linear in r1 + r2 (0.75-0.80), and a simulation from N(estimate, V) gives a wider
  spread than the delta method: food USD 0.58 against 0.39, household goods 0.76 against 0.40, clothing 0.19 against
  0.15. The t-statistics of the persistent divisions are upper bounds. It strengthens "not significant".

## 7. `shapiro_goods.py` — WRONG (new error: the contributions have holes)

What is right:
- `innovations`: price equation in m/m with 12 own lags, quantity y/y with 13 own lags, each with the other's lags,
  11 month dummies, constant — as the docstring says (37 regressors, 111 observations). Labels, the four
  `contributions*.csv` and `labels.csv` reproduce from the saved Taldau JSON with my own code (max diff 5e-4).
- Robust band: 1.4826 x MAD. Food 0.32 / 6.31 against plain s.d. 0.49 / 7.15; non-food 0.24 / 6.36 against
  0.27 / 10.16.
- Additivity: demand + supply + ambiguous = total and food + non-food = goods to 0.001.
- Ambiguous months: food 34.2 %, non-food 27.9 %, together 31.1 % (was 46 %).
- Weights: year Y of `cpi_weights.csv` (dated Y-12-31; BNS January release of year Y) is applied to the months of
  year Y. That is the right alignment. Sums are 100.

The error:
- `cpi_weights.csv` has FOOD/NONFOOD/SERVICES for 2014, 2016, 2017, 2019, 2020, 2022-2026 only. `official_weights()`
  (`shapiro_goods.py:102-108`) returns no row for 2015, 2018, 2021; line 145 puts NaN for those months; the 12-month
  sum is NaN for every window touching them and line 150 `dropna()` removes the rows.
- `contributions.csv` now has 54 rows: 2019-12..2020-12 and 2022-12..2026-04. Missing: 2018-01..2019-11 and
  2021-01..2022-11 — the whole rise of inflation in 2021-2022. Before the fix it had 100 rows (2018-01..2026-04).
  Same in `contributions_band0/band50` (54) and `lags7` (60).
- `shapiro_goods.png` draws the 54 rows side by side: the axis runs 2020, 2023, 2024 and the bars jump from 5.7 to
  14.5 between two adjacent columns.
- `tests/test_models_inflation.py:55-61` does not notice (it checks additivity on the rows that exist).

Correction, `shapiro_goods.py` after line 107:
```python
    t = t.reindex(range(int(t.index.min()), int(t.index.max()) + 1)).interpolate()   # 2015, 2018, 2021 are not published
    t = t.div(t.sum(axis=1), axis=0)
```
and say in the docstring that those three years are interpolated. With this the file has 100 rows again
(2018-01..2026-04): goods demand / supply / ambiguous / total = 2021-12 2.18 / 2.24 / 1.80 / 6.22; 2022-06
1.97 / 4.75 / 4.10 / 10.83; 2022-12 3.07 / 4.96 / 6.44 / 14.47 (unchanged); 2026-04 2.97 / 2.29 / 2.29 / 7.54
(unchanged). Goods + services against headline log y/y: mean -0.14, max 0.49 pp. Add to the test:
`assert len(c) >= 100` and that the index has no missing month. Then re-run and replace the CSVs and the PNG.
Also `models/README.md:27` says "2016–2026".

Is the new decomposition defensible: yes as an indicator, once the hole is closed. What remains weak:
- The quantity residual still carries base effects: non-food 2020-04 -76 log points, 2021-04 +30.8, 2022-04 +18.4;
  its correlation with itself 12 months earlier is -0.18 (food -0.07). The robust band only keeps these from
  widening the band; the labels of those months and of their echoes are not informative.
- 37 regressors on 111 observations (74 degrees of freedom) — more than the 27 the review objected to.
- Ambiguous months carry 37 % of the goods contribution on average and up to 68 % (2022-12: 6.44 of 14.47).
- Quantities are retail trade volumes by broad group, 2025-10 interpolated; services (about 0.30) unclassified.

## 8. Regenerated outputs — CORRECT

Re-run in the copy, compared byte for byte with the repository:
- `svar_v2.py` (75 s): all 39 CSVs and `hd_v2.png` identical.
- `bvar_sign.py`: all 12 CSVs and both PNGs identical.
- `fiscal_lp.py`: `lp.csv`, `nf_transfers_pct_gdp.csv` identical.
- `erpt_neer.py`, `erpt_border.py`: three CSVs identical.
- Also `bvar_sign_ext.py`, `bvar_market.py`, `regional_fiscal_lp.py`: all CSVs identical, `hd_cpi_ext.png` identical.
- `shapiro_goods.py` not re-run (live Taldau fetch); its CSVs reproduce from the saved JSON with my own code.

## 9. `models/README.md`, section of 2026-11-13 — PARTLY

Holds:
- FEVD v2: 37.6 / 18.4 / 16.8 / 10.2 / 8.1 / 5.6 / 3.3 — as in `summary.csv`.
- `mean_<variant>.csv` adds up; medians do not (2.64 against 3.42).
- Border, food from the NEER 0.65 (was 2.59). Food 12-month 0.55, lag sum 0.14. Non-food 2019: 0.298 / 0.410.
- Correlation of tariff steps with the regulated CPI (quarterly SAAR): 0.991.
- Root above one: 53.6 % of the retained v2 draws (median root 1.0005, 184 rejected); old_2011 66 %, old_2013 71 %.
  Median within-draw range of the baseline 5.4 pp (v2).
- USD without 2022-03..2023-06, headline: 12-month response 0.026 (t 0.65), lag sum 0.006 (t 0.43); full sample
  0.396 (t 1.23) and 0.076 (t 1.86). Food: 0.088 (USD) and 0.081 (NEER) without the episode.
- `fiscal_lp`: s.d. of the targeted transfer 0.132 % of GDP, so 1 % is 7.57 s.d. (maximum observed 0.575).
- Regional LP without Turkestan: h = 18 b = 0.0218, s.e. 0.0165, t = 1.32; no horizon above 1.96.
- GDP 2026Q2: +6.50 % q/q in BNS's adjusted series (second largest since 2011 after 2020Q3 +8.67).
- July 2017: 2 135.8 bn tenge removed.
- "svar_v2.py gives the same files on a second run": yes.

No longer holds / inexact:

| line | text | current value |
|---|---|---|
| 72 | "109 of 188 months are flagged" | 109 of 190 rows of `tariff_steps_monthly.csv` (2011-01..2026-10); 108 of the 189 months that have a change |
| 77-78 | split pieces "do not add up (0.16 pp on average, up to 0.5)" | 0.22 pp on average (median 0.24), up to 0.52, 55 quarters 2013Q1-2026Q3 |
| 82 | "No 12-month pass-through here is significant at 5 %" | false as written: alcohol and tobacco from the NEER -0.073, t = -2.01; in the joint regression transport USD -0.32 (t = -2.64) and NEER +0.39 (t = 2.54). True for: no positive single-rate pass-through (largest t is food USD 1.39) |
| 85 | "the one significant horizon" | with normal 5 % values two (h = 16 t = 2.04, h = 18 t = 2.23); one (h = 18) only with t(19) = 2.09; on the 90 % band the script writes, five (h = 14-18) |
| 74 | "its price response is negative" | the median is (-0.07..-0.10 at h = 2-12), every 68 % band includes zero (h = 4: [-0.32; +0.12]) |
| 64-65 | Shapiro "weights are the official BNS ones" | true, and it cut `contributions.csv` to 54 of 100 months (point 7) |
| 27 | "shapiro_goods/ ... 2016–2026" | 2019-12..2020-12 and 2022-12..2026-04 now; 2018-01..2026-04 after the fix |

Suggested wording: line 72 "109 of 190 months"; line 78 "(0.22 pp on average, up to 0.5)"; line 82 "No positive
12-month pass-through here is significant at 5 % (food: 0.55, t = 1.4); the delta-method t is if anything too
high"; line 85 "the horizons that are significant (h = 16 and 18 at 5 %) are not without Turkestan oblast
(h = 18: t = 1.3)"; line 74 "(the median price response is negative, the band includes zero)".

## 10. Tests — PARTLY

- Run in the copy: `tests/test_models_inflation.py` + `tests/test_model_data.py`: 15 passed.
- `test_chain_yoy_...`: tests the construction, that a bad second year of m/m is ignored, and the gap rule. Good.
- `test_industrial_production_level_...`: y/y to 0.05 over more than 120 months and the 2025 annual index to 0.5
  (actual gap 0.16). Good; only 2025 is checked (the largest gap is 0.39 in 2024, also inside 0.5).
- `test_fevd_shares_add_up_to_one`, `test_posterior_mean_...`: test the committed files, tolerances match rounding.
- `test_cumulative_pass_through_...`: right for r2 = 0; r2 and `cumulative_t` are not tested.
- `test_border_pass_through_is_within_reason`: a magnitude bound and a search for two strings in the source; it
  would pass with a wrong January rule. A direct test of the conversion on a synthetic index would be stronger.
- `test_shapiro_contributions_and_official_weights`: misses the hole of point 7 (no check on the number or
  continuity of rows).
- `test_shapiro_price_innovation_is_monthly`: tests that the price residual recovers a monthly shock (correlation
  above 0.85); the quantity equation is not tested.
- All but two of the six are checks of committed artefacts, not of the computation; they hold as long as the files
  are regenerated before commit.
