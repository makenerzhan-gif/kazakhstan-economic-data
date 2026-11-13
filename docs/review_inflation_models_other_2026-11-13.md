# Review B — ERPT (NEER, border), Shapiro goods, fiscal LP, regional fiscal LP and their inputs

Branch `claude/inflation-svar-v2`, HEAD `a88a3d05f`. Read-only review. All recomputations were run on a
copy in `/tmp/claude-0/-home-user-kazakhstan-economic-data/75b92fb2-b6fa-5dc2-bf44-15a6ab5a8c77/scratchpad/review_B/`
(scripts `chk_*.py`; committed outputs extracted from HEAD into `review_B/committed/`).

Severity: ERROR = a number is wrong; DOUBT = a questionable choice that changes results; NOTE = minor.

## Findings

### 1. ERROR — `erpt_border.py:32`: the import price index is "December of the previous year = 100", but is used as a month-on-month index. All of `erpt_border.csv` is wrong.

Code: `ipm = 100 * np.log(ip / 100)  # chain m/m, January = Jan/Dec by BNS convention`.

`config/dims.yaml:3723-3741` defines `IMPORT_PRICE_INDEX_BY_HS_SECTION` as "отчётный месяц к декабрю прошлого года",
unit "index, December of the previous year = 100", and its note gives the conversion: "Month-on-month = I(t)/I(t-1)
within a year, January = I(Jan)". The data confirm it is cumulative within the year (section IV: 2021-10 118.4,
2021-11 117.2, 2021-12 123.0, 2022-01 98.9). So the regressand of stage 1 and the regressor of stage 2 is the
year-to-date log change, not the monthly change (only January is right).

Recomputation with the correct m/m (`ln I(t) − ln I(t−1)` within the year, January = `ln I(Jan)/100`), everything
else as in the script (the as-coded column reproduces the committed CSV exactly):

| division (HS) | border←USD: committed → corrected (t) | border←NEER: committed → corrected (t) | retail←import 6m: committed → corrected (t) |
|---|---|---|---|
| Clothing & footwear (XI+XII) | 0.613 → 0.336 (1.17) | 0.025 → 0.253 (1.48) | −0.028 → −0.128 (−4.16) |
| Household goods (XVI) | 0.847 → 0.311 (3.94) | 1.146 → 0.217 (2.68) | 0.101 → 0.401 (3.06) |
| Food (IV) | 0.852 → 0.548 (2.29) | 2.593 → 0.650 (3.77) | 0.015 → 0.107 (2.78) |
| Health (VI) | 1.939 → 0.795 (5.43) | 2.022 → 0.457 (3.63) | 0.019 → 0.057 (0.96) |

The committed border pass-through above 1 (2.6 for food, 1.9–2.0 for health) is an artefact of the cumulation; the
retail-stage coefficients were 3–7 times too small. The qualitative conclusion "pass-through stops in retail" has to
be re-read from the corrected numbers.

Fix: `ly = np.log(ip/100); mm = ly.groupby(ip.index.year).diff(); mm[ip.index.month == 1] = ly[ip.index.month == 1]; ipm = 100*mm`.

### 2. ERROR — `model_data/monthly.csv` columns `ip`, `ip_sa`, `ip_yoy`, `ip_saar` are wrong from 2026-01 (and drift from 2024); used by `fiscal_lp.py:94`.

`ip` is chained from `IND_PROD_MONTHLY_MOM` (`model_data/spec.yaml:72`). The 2026 m/m values in the source
(78.5, 124.5, 116.2, 107.2, 109.0, 112.9, 93.9, 114.0) are not consistent with the published
`IND_PROD_MONTHLY_YOY` (93.4, 103.2, 104.3, 109.6, 104.7, 108.2, 100.1, 101.0):

- `ip` goes 143.95 (2026-01) → 294.09 (2026-08); `ip_yoy` 2026-08 = **+83.4 %** against the published **+1.0 %**.
- y/y implied by the chain minus the published y/y, mean by year: 2023 +0.2 pp, 2024 +4.7, 2025 +7.1, 2026 +43.4
  (max +82.4). X-13 flagged it itself: `LS2026.Jan, TC2026.Jan` in `VARIABLES.md:105`.

Effect on `models/fiscal_lp/lp.csv`, outcome `ip`, shock `targeted` (current code, current data): h=12 b = 21.5
(full sample) vs 8.2 when the LHS stops at 2025-12; h=18 27.7 vs 15.1; h=9 20.3 vs 12.2. The right panel of
`lp_fiscal.png` is driven by the bad 2026 levels.

Fix: check the 2026 `IND_PROD_MONTHLY_MOM` fetch (the values look like another base); until then build the IP level
from the published y/y (or cut the IP sample at 2025-12), and add a chain-vs-published-y/y consistency test to
`build_model_data.py`.

### 3. ERROR — `models/fiscal_lp/lp.csv` (and `lp_fiscal.png`) do not correspond to the committed code and inputs.

Running `scripts/models/fiscal_lp.py` unchanged on the branch's `model_data/` gives different numbers (same `n`
in every row; `nf_transfers_pct_gdp.csv` reproduces to 5e-5):

| shock / outcome | h | committed b (se) | rerun b (se) |
|---|---|---|---|
| targeted / cpi | 0 | −0.12 (0.26) | 0.07 (0.21) |
| targeted / cpi | 6 | −0.03 (1.49) | −0.31 (1.51) |
| targeted / cpi | 12 | 3.10 (1.64) | 2.97 (1.57) |
| targeted / cpi | 18 | 3.90 (2.72) | 3.17 (2.61) |
| targeted / ip | 6 | 21.53 (5.91) | 16.28 (4.66) |
| total_surprise / cpi | 6 | −0.30 (1.23) | −1.04 (1.10) |

Max |Δb| = 7.3 (ip), 0.74 (cpi). The docstring (`fiscal_lp.py:16`) still says "CPI (STL SA)": the CSV is from the
STL vintage of `model_data`, while the branch's `cpi_sa`/`ip_sa` are X-13. Fix: re-run and commit, correct the
docstring. (The other four models' committed CSVs reproduce exactly, see "Checked and correct".)

### 4. ERROR (mislabelled quantity) — `erpt_neer.py:62, 74-75`: "перенос 12м" = Σ b_k is not the 12-month pass-through of a model with AR(2) terms.

The specification has `y1`, `y2` on the right-hand side, so the cumulative response of the price level after 12
months is Σ_{j=0..12} ψ_j with ψ(L) = b(L)/(1 − r1 L − r2 L²), not Σ b_k. The AR sums are large (food 0.75,
clothing 0.80, household goods 0.79, health 0.76; headline 0.82), so the saved column understates the model's own
12-month pass-through by a factor of 3–5 for the divisions that matter:

| | Σ b_k (CSV "перенос 12м") | cumulative response at 12 m | long run Σb/(1−ρ) |
|---|---|---|---|
| Food, USD | 0.141 | 0.547 | 0.576 |
| Household goods, USD | 0.099 | 0.410 | 0.459 |
| Health, USD | 0.050 | 0.183 | 0.207 |
| Clothing, USD | 0.023 | 0.139 | 0.117 |
| basket-weighted, USD | 0.066 | 0.277 | 0.287 |
| basket-weighted, NEER | −0.016 | −0.020 | — |
| headline CPI (own regression), USD | 0.076 | 0.396 | 0.421 |

The long-run value is computed (`_lr`) but never written. The t-statistic in the CSV is the t of Σ b_k (correctly
computed with the full covariance), not of the pass-through. Fix: report the cumulative impulse response at 12
months (delta-method or bootstrap s.e.) or drop the AR terms and say so (without AR terms Σ b_k for USD: food 0.146,
weighted 0.071 — i.e. the AR terms are not what makes the number small; the 13-lag DL simply cannot hold the
persistence that the AR terms capture), and rename the column.

### 5. DOUBT — `erpt_neer.py` USD-vs-NEER result rests on March 2022 – mid 2023.

In March–June 2022 the tenge fell 14 % against the dollar while the consumer-import NEER (49 % rouble weight)
*appreciated* (rouble collapse), and prices jumped for reasons other than the exchange rate; then the rouble
rebounded (NEER depreciation +4.7, +4.1, +7.8, +6.3 in Apr–Jul 2022) while inflation was already slowing. Dropping
the observations 2022-03..2023-06 (lags built before dropping):

| Σ b_k (t) | full sample | without 2022-03..2023-06 |
|---|---|---|
| headline, USD | 0.076 (1.86) | 0.006 (0.43) |
| headline, NEER | −0.021 (−0.87) | 0.011 (0.65) |
| food, USD | 0.141 (2.28) | 0.040 (1.53) |
| food, NEER | −0.001 (−0.02) | 0.043 (1.44) |
| household goods, USD | 0.099 (1.59) | 0.007 (0.29) |
| household goods, NEER | 0.009 (0.20) | 0.033 (1.57) |

Outside the 2022 episode the dollar does not beat the NEER; the "USD matters, NEER does not" reading (and the ΔAIC of
+40 / +64 for food / household goods) is one episode. Starting the sample in 2017-01 (so that the August 2015 –
January 2016 devaluation is not in the lag window of the first 12 observations) leaves the USD result roughly as is
(food 0.196, weighted 0.055). Fix: report the sub-sample, or add 2022 war-shock controls (rouble rate separately,
global food prices).

### 6. ERROR (method claim) — `shapiro_goods.py:20-23, 115-118`: innovations of the y/y VAR are not the innovations of the monthly change; about 30 % of price-innovation signs differ.

The docstring claims that with 13 lags "the innovation in a y/y change equals the innovation in the m/m change …
so the sign test is the same as Shapiro's". It would hold only if Δln x(t−12) were spanned by the 13 lags of y/y
changes; it is not (y(t) − y(t−1) = Δln x(t) − Δln x(t−12), and Δln x(t−12) needs the whole history of y). Evidence:

- the y/y-VAR price residual correlates with the m/m inflation of 12 months earlier: −0.32 (food), −0.42 (non-food) —
  a true innovation would be uncorrelated with anything dated t−12 (base effect in the "innovation");
- sign of the y/y-VAR price residual vs the residual of a regression of m/m price change on 13 own lags, 13 lags of
  the quantity and month dummies: agreement 70 % (food), 72 % (non-food), correlation 0.72 / 0.63;
- quantities are worse: the five largest non-food quantity residuals are 2020-04 (−80 log points), 2021-04 (+32,
  the pure base effect of the lockdown), 2022-04, 2020-07, 2021-01. The residual s.d. used for the ±0.25 band
  (7.5 and 10.6 log points) is inflated by them (kurtosis of the non-food quantity residual 31), so the band is
  ±1.9 / ±2.7 pp of volume and 46 % of all months come out "ambiguous".

Also 27 parameters per equation on 111 observations. The demand/supply labels, hence `contributions*.csv`, are
therefore partly base-effect noise. Fix: for prices use the m/m change directly (it exists); for quantities build a
level by chaining the y/y index on a 12-month base (or fetch the "to previous month" volume index if Taldau has it)
and run the VAR in monthly log changes with month dummies; add COVID dummies (2020-03..2020-08 and their 12-month
echoes) or estimate the residual scale robustly (MAD).

### 7. ERROR (moderate) — `shapiro_goods.py:78-90, 123`: CPI group weights are estimated by a 12-observation regression although the official weights are in the repository; 2019 is off by 11 pp.

`cpi_group_weights_estimated.csv` vs `data/processed/dims/cpi_weights.csv` (FOOD/NONFOOD/SERVICES, BNS press
releases, 10 of the years 2014–2026):

| year | estimated food / non-food / services | official |
|---|---|---|
| 2019 | 0.340 / 0.410 / 0.250 | 0.388 / 0.298 / 0.314 |
| 2022 | 0.439 / 0.281 / 0.280 | 0.407 / 0.302 / 0.291 |
| 2023 | 0.418 / 0.264 / 0.318 | 0.418 / 0.296 / 0.286 |
| 2026 | 0.394 / 0.259 / 0.347 | 0.411 / 0.284 / 0.305 |

"Fit error ≤ 0.08 pp, i.e. rounding" (docstring) says nothing about the weights: with indices rounded to 0.1 and
collinear groups, weights are poorly identified. Effect: non-food contribution to y/y in 2019-12 is 2.01 in
`contributions.csv`, 1.46 with official weights (food 3.14 vs 3.59); `goods_total` differs by up to 0.34 pp
(2022-12: 14.81 vs 14.47; 2026-04: 7.35 vs 7.54). Fix: use `cpi_weights.csv` (interpolate 2015, 2018, 2021).

### 8. DOUBT — `fiscal_lp.py`: "shock" is the level of a persistent, pre-announced flow; the response is scaled to an out-of-sample impulse.

- `targeted` (lines 91, 55-59) is zero in 34 of the first 36 months and positive in every month but four of
  2021–2025 (autocorrelation 0.55 / 0.39 / 0.27 at lags 1–3); it is the budgeted transfer, not a surprise, so b_h
  is close to a "2021–25 vs 2018–20" contrast. With a post-2021 dummy or month dummies added the CPI path changes
  (h=18: 3.2 → 5.2 with month FE). No month dummies although the shock is not seasonally adjusted.
- The chart and README scale is "1 % of GDP in one month" (`fiscal_lp.py:121`); the s.d. of the monthly targeted
  transfer is 0.13 % of GDP and the maximum 0.58 %. Per one s.d. the rerun estimates are CPI +0.4 % at h=12 and IP
  +2.8 % (IP: see finding 2). A reader of "IP +21 %" is misled. Fix: scale to 1 s.d. or to 0.1 % of GDP.
- `total_surprise` (lines 86-90) is a full-sample residual from 24 parameters on 90 observations (look-ahead,
  generated regressor ignored in the s.e.); small.

### 9. DOUBT — `regional_fiscal_lp.py:64, 69`: 20 clusters with normal critical values; the only "significant" horizon depends on one region.

- Bands use 1.645 with 20 clusters; t(19) gives 1.729 (90 %) and 2.093 (95 %). At h=18, b = 0.0338, t = 2.23 —
  marginal at 5 % with t(19).
- Without Turkestan oblast (shock mean 9.2 %, s.d. 6.9 %, max 41.6 % of monthly GRP — twice the others) h=18 gives
  b = 0.0218, s.e. 0.0164 (t = 1.33).
- The shock is in % of *monthly* GRP (`:41`, `/(G/12)`); per 1 % of annual GRP the coefficients are 12 times larger
  (h=18: 0.41 %). Neither the CSV nor the README states the unit.
Fix: t(G−1) or wild-cluster bootstrap bands, a leave-one-region-out table, and the unit in the CSV header/README.

### 10. NOTE — `regional_fiscal_lp.py:34-42`: missing months are treated differently in the two shocks; border mismatch in Jan–May 2022.

- `budget = rep.add(loc, fill_value=0)`: a month with only one source reported counts the other as zero, but a month
  with neither is NaN and dropped (27 region-months); `shock_loc` is NaN whenever the local-budget row is missing
  (n = 1653 vs 1730). A missing row in Taldau 701827 most likely means zero investment. Regional `rep` rows sum to
  the national row in the median month but down to 0.32 of it in the worst.
- GRP in `GRP_NOMINAL_BY_REGION` is in new borders from 2021 (ALM 3.73 → 3.38 trn, VKO 4.61 → 3.23, new regions
  appear in 2021), so for 2022-01..2022-05 the old-border investment of Almaty and Karaganda oblasts is divided by
  new-border 2021 GRP (shock overstated by about 36 % and 23 %): 10 observations of 1730.

### 11. NOTE — `erpt_neer.py:27-31, 80`: the division weights are not "official BNS basket weights 2025" and exclude 6.8 % of the basket.

`W` (38.6, 1.7, 9.0, 13.2, 5.2, 8.8, 7.7, 3.3, 1.9, 2.4, 1.4; sum 93.2) matches neither the official weights in the
repository (latest 2022: health 5.85, housing 14.6, communication 4.28) nor exactly `cpi_weights_estimated.csv` for
2025 (38.4, 1.6, 9.2, 11.1, 5.3, 9.0, 7.9, 3.3, 1.9, 2.4, 1.4) — they look like an earlier vintage of the estimated
weights. Division 12 (miscellaneous, 8.6 %) is left out and the average is renormalised to 93.2. Only the printed
"weighted 12m pass-through" (0.066 / −0.016) and the `вес` column are affected.

### 12. NOTE — `erpt_border.py`: details that affect reading the table.

- `n` (72) is the stage-2 sample; stage 1 uses 78 observations.
- XI and XII are averaged unweighted (`:35`); XII (footwear) has monthly changes of −14.7 % … +9.9 % and dominates
  the pair.
- Stage 1 has no month dummies and no lagged dependent variable although import unit-value indices are seasonal;
  stage 2 has both.
- Section IV (prepared food, beverages, tobacco) stands for the whole food division; VI (all chemicals) for health.

### 13. NOTE — NEER weights jump between years (`data/processed/dims/neer_import_weights.csv`).

CNY weight 18.5 % (2023) → 37.9 % (2024, structure of 2023) → 27.4 % (2025) → 21.7 % (2026); RUB 42.5 → 27.3 →
34.9 → 39.3. Comtrade's 2023 consumer-goods partner structure looks like an outlier (or a reporting change), and it
drives the 2024 NEER. Coverage 87–91 %. The index itself is computed as documented (see below). USD weight is 3–4 %
by construction (partner-currency assignment, no invoicing currency) — which is the hypothesis the horse race tests,
but it should be said next to the result.

### 14. NOTE — outputs without code, and README details.

- `models/shapiro_goods/catering_contrib.csv` is written by no script in the branch (first rows empty).
- `models/cpi_components/*.csv` (market core index, division m/m, regional CPI, regional budget investment) have no
  generating script in the repository ("moved from a scratch folder"), so the README's "accounting with official BNS
  weights" cannot be reproduced. Implied weight of regulated utilities in the ex-3 basket behind `mkt_base` is a
  constant 6.7 % for 2012–2023, then 6.0 % (2024) and 4.5 % (2025–26) — a falling weight in the years when these
  tariffs rose 30 % y/y; worth a look by whoever has the source.
- README: `shapiro_goods/` "2016–2026" — the contributions run 2018-01..2026-04 (retail volumes end in 2026-04;
  2025-10 is interpolated, which touches the labels of that month and the VAR lags of the next 13).
- `division_mm.csv`: the column "Страхование и финансовые услуги" holds the old division 12 "Разные товары и услуги"
  for 2011-01..2025-12 and COICOP-2018 division 12 only from 2026-01 (not used by the scripts).
- `fiscal_lp.py:95` cuts the sample at 2026-06 before leads are built, so two available CPI months are unused.

## Checked and found correct

- **Reproduction.** `erpt_usd_vs_neer.csv`, `rate_correlations.csv`, `erpt_border.csv` (as coded), the four
  `shapiro_goods/contributions*.csv` (from the committed raw JSON; max diff 5e-4 = rounding),
  `regional_fiscal/lp_shock.csv` and `lp_shock_loc.csv`, `fiscal_lp/nf_transfers_pct_gdp.csv` reproduce from the
  committed code and inputs. Only `fiscal_lp/lp.csv` does not (finding 3).
- **Independent recomputation.** Regional LP rebuilt from the raw CSVs with my own code (Frisch–Waugh on the two sets
  of dummies, own cluster sandwich with the G/(G−1)·(n−1)/(n−k) correction): h = 0, 6, 12, 18 give b = −0.0050,
  −0.0023, 0.0128, 0.0338 and s.e. 0.0035, 0.0087, 0.0101, 0.0151 — equal to the CSV. ERPT regressions re-estimated
  with my own design matrix: identical Σ b_k and t. NEER_CONSUMER recomputed from `neer_import_weights.csv` and
  `exchange_rates_official_monthly.csv`: monthly log changes equal to 1e-4.
- **Exchange-rate direction.** `usd` = 100·Δln(KZT per USD), up = depreciation; `neer` = −100·Δln(NEER) with the
  NEER defined "up = appreciation", so up = depreciation; `rub` = Δln(KZT per RUB) (`rubusd` is RUB per USD, 83.2 in
  2026-08). Signs confirmed on 2015-09 (usd +23.1, neer +21.9, rub +21.0).
- **NEER construction.** Previous-year weights, geometric chain, renormalisation over currencies with rates in both
  months, 2020 = 100; monthly means on both sides (consistent with `usdkzt` monthly mean).
- **CPI by division.** `division_mm.csv` equals `cpi_detail_mom.csv` CP01–CP11 for all 188 months; no duplicates or
  gaps; `100·ln(index/100)` is the right m/m transformation.
- **Sum of lag coefficients.** The s.e. uses the full HAC covariance (`1' V 1`), in both ERPT scripts; samples for
  the USD and NEER regressions are identical (128 obs), so ΔAIC is comparable.
- **Shapiro.** Sign rule (same sign = demand, opposite = supply; ambiguous if either |z| < band); the three labels
  add up to `goods_total` (max discrepancy 0.001 = rounding) and food + non-food = goods; the three groups with the
  estimated weights add to headline log y/y within −0.07 pp on average (max 0.36); retail volume indices are
  month-on-same-month (the 2020-04 values 81.2 / 41.1 and 2021-04 echo rule out cumulative indices); food / non-food
  categories match between CPI and retail trade.
- **Fiscal LP.** YTD → monthly flows (January = YTD, within-year differences, within-year interpolation of the four
  missing months), units (million KZT over KZT/1e6), nominal GDP de-cumulation and trailing 12-month sum; annual
  sums 3.6–6.8 % of GDP are plausible. LHS is `ln X(t+h) − ln X(t−1)` at every horizon, horizon-specific samples
  (n = 98 … 80), HAC with h+1 lags, 68 % = ±1 s.e., 90 % = ±1.645 s.e.
- **Regional LP.** LHS cumulative from t−1 to t+h within region id; lags do not cross the June-2022 split; no
  interior gaps within any region id (the 5 missing East Kazakhstan months fall exactly at the split); month FE +
  region×calendar-month FE (the design is rank-deficient only among the dummies — the shock coefficient is
  identified); clustering on the 20 original regions; investment values are in tenge and monthly flows (2025:
  republican 1.84 + local 3.14 trn of 22.7 trn total); GRP of the previous year in million tenge.
- **Other model_data columns used.** `cpi_yoy` vs published `CPI_YOY`: mean abs diff 0.13 pp (as documented);
  `cpi_regulated` chain vs published y/y: 0.07 pp (the −11 % in 2025-10 is in the source).

## Could not check

- The Taldau retail-volume download (702041) and the content of `taldau_702041_raw.json` against the source — no
  live fetch; the JSON was taken as given.
- `models/cpi_components/market_core_index.csv` and `regional_budget_investment.csv` against their sources: no
  generating script and no raw files in the repository (only the internal-consistency checks above).
- Whether Taldau 701827 reports Jan–May 2022 investment of the split oblasts in old or new borders (finding 10).
- The cause of the wrong 2026 `IND_PROD_MONTHLY_MOM` values (fetcher vs source) — outside the five scripts.
- The PNG charts were not inspected.
