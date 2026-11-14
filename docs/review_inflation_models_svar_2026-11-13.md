# Review A — sign-restricted SVAR family (branch claude/inflation-svar-v2)

Method: read all code in scope; recomputed the data inputs from `data/processed` and `model_data`; re-ran `v2` and `old_2011` in a private copy (`review_A/repo`, inputs taken from the committed `models/svar_v2/inputs_quarterly.csv` because the vendored X-13 binary is a git-LFS pointer here) with per-draw diagnostics and three sensitivity runs. Committed outputs were read from `HEAD` (the worktree was being re-run during the review). Line numbers are file-relative. My re-run of `v2` with another seed reproduces the committed numbers to about ±0.1 pp (Monte-Carlo noise).

Counts: 3 ERROR, 8 DOUBT, 8 NOTE.

## Findings

### 1. ERROR — FEVD shares in `summary.csv` do not sum to 1 (they sum to 0.83–0.89); the sign-identified shocks are understated
`scripts/models/svar_v2.py:149-153` (`fevd_share`), same construction in `scripts/models/bvar_sign.py:216-224` (`fevd_infl`).

```python
return {NAMES[g]: float(np.median(irf[:, :, s].sum(axis=(1, 2)) / tot)) for g, s in o["groups"].items()}
```
The median over draws is taken share by share. The shares of sign-identified shocks are right-skewed, so the medians do not add up.

Evidence, row sums of the `FEVD8` columns in the committed `summary.csv`: old_2011 0.835, old_2013 0.847, v2 0.839, v2_split 0.835, v2_ma4 0.830, v2_market 0.845, v2_ma4_market 0.891. `models/bvar_sign/fevd_infl_base.csv` (HEAD): rows sum to 70.1 / 79.6 / 81.0 / 80.9 %.

Recomputation for v2 (1000 draws, own seed), median vs posterior mean share (means sum to 1):

| | external | deficit | tariff | demand | supply | monetary | tenge | sum |
|---|---|---|---|---|---|---|---|---|
| median (as in summary.csv) | 0.366 | 0.023 | 0.050 | 0.056 | 0.162 | 0.052 | 0.126 | 0.834 |
| mean | 0.371 | 0.031 | 0.064 | 0.095 | 0.187 | 0.084 | 0.168 | 1.000 |

The headline "external 37 %" survives (recursively identified, symmetric posterior). "Non-oil deficit 2.5 %" is 3.1 % as a mean share. Demand (5.9 → 9.5 %) and the policy-rate shock (4.6 → 8.4 %) are understated by about 40 %.

Fix: report posterior means (they add up), or the shares of the median-target draw; if medians are kept, say in the README that they do not sum to 1. Two smaller points for the same paragraph: (a) the object is q/q SAAR inflation, cumulated over h = 0..8, i.e. the 9-step forecast error; for the y/y measure used everywhere else the mean shares are external 0.39, deficit 0.027, tariff 0.07, demand 0.08, supply 0.18, monetary 0.09, tenge 0.17; (b) the variance is that of "normal" quarters — the s = 5 scaling of the seven turbulent quarters is excluded.

### 2. ERROR — the headline chart `hd_v2.png` labels the non-oil-deficit shock "Бюджет (госпотребление)"
`scripts/models/svar_v2.py:221`

```python
E.chart(mt.rename(columns={NAMES["fiscal"]: "Бюджет (госпотребление)"}), OUT / "hd_v2.png", ...)
```
The column is renamed to reuse the colour key of `bvar_sign_ext.chart`, so the legend of the v2 chart says government consumption while the series is the non-oil deficit shock (checked in the PNG). Fix: pass a colour/label map to `chart`, or add the key "Бюджет (ненефтяной дефицит)" to its `colors` dict.

### 3. ERROR — 2026Q2 real GDP: the discrete y/y index is applied to a series whose own y/y it does not track
`scripts/models/svar_v2_data.py:140-145`

```python
q.loc[p, "gdp_sa"] = q.loc[p - 4, "gdp_sa"] * gv[p] / 100
```
The docstring says this "assumes an unchanged seasonal factor". The real assumption is that the BNS production-side discrete index (`gva_volume_index_by_section_discrete`, GDP) equals the y/y growth of `gdp_sa` (QNA expenditure, 2010 prices, SA). In the data it does not:

| | y/y of `gdp_sa` | discrete index |
|---|---|---|
| 2025Q1 | 6.73 | 5.60 |
| 2025Q2 | 10.10 | 6.99 |
| 2025Q4 | 6.45 | 6.83 |
| 2026Q1 | 4.07 | 3.00 |

Over 2011Q2–2026Q1 the mean absolute gap is 1.43 pp (max 8.9 pp); the standard deviation of q/q growth of `gdp_sa` is 1.94 pp. The base quarter 2025Q2 is itself 3.1 pp above what the index implies, and that gap is carried into 2026Q2. Result: 2026Q2 = 10 925 737, q/q = +2.68 % (+10.7 % SAAR) after +0.02 % in 2026Q1. The alternative chain (2026Q1 level × last year's q/q × index acceleration) gives +3.7 %; the sample mean is +0.9 %. The last GDP observation is therefore uncertain by about ±1–1.5 pp q/q, and that observation alone decides the demand/supply/monetary split of the final quarter.

Sensitivity (v2 re-run, 2026Q2 q/q set to +0.9 %), change of contributions 2025Q4→2026Q2, medians: monetary −0.27 → −0.39; Σ demand+budget+policy −0.44/−0.49 → −0.62; supply +0.35/+0.40 → +0.44; Σ supply+tenge+tariffs −0.94/−0.90 → −0.79. The shifts are 0.1–0.2 pp, inside the 68 % bands, but the same size as several reported medians.

Fix: end the sample at 2026Q1 for anything quoted about GDP-identified shocks, or extend with the y/y of `gdp_nsa`'s own source when published; at minimum report the 2025Q4→2026Q2 column as conditional on a GDP nowcast and show it with the alternative.

### 4. DOUBT — "tariff steps" is the regulated-utilities CPI under another name
`scripts/models/svar_v2_data.py:105-115`

A month is flagged if any of eight items (incl. garbage collection and LPG) has a jump in `tariff_change_months.csv`; in a flagged month the whole aggregate m/m is taken. 109 of 188 months are flagged (58 %); steps carry 104.5 of the 111.4 log points of the cumulative rise; only 5.6 % of quarters 2013Q1–2026Q2 have a zero step. Quarterly 400·dln of `tariff_step_idx` vs plain `cpi_regulated` (NSA): correlation 0.993, s.d. 12.5 vs 12.9. So v2 does not replace "regulated CPI" by "identified administrative steps"; it replaces the X-13-adjusted regulated CPI by the unadjusted one. The docstring sentence "drift between steps stays in the other shocks" concerns 6.8 log points in 15 years. Fix: build the step from the flagged items only (item m/m × item weight), or describe the variable as regulated CPI, NSA.

### 5. DOUBT — the "baseline" of the historical decomposition drifts by about 5 pp and is known to ±2.3 pp
`scripts/models/svar_v2.py:79-82, 111-130`; `scripts/models/bvar.py:75, 121, 223`

Baseline = data − Σ shock contributions from the first sample quarter, i.e. constant + initial conditions. With the random-walk prior mean on every variable (`delta = np.ones(n)`, including inflation, the deficit ratio and tariff inflation), the sum-of-coefficients prior and `MAX_ROOT = 1.01`, 51.5 % of retained v2 draws have a largest root above 1 (median 1.000; 189 draws rejected). The y/y inflation baseline then moves from 4.3 % (2014Q2, median) to 8.5 % in 2026Q2, 16–84 % band 6.3–11.0; median within-draw range 5.0 pp. Restricting to `MAX_ROOT = 1.0` does not change this (range 5.2 pp).

Consequences: (a) `levels_*.csv`, `median_target_*.csv` and the charts decompose the deviation from a ~9 % baseline (v2 median-target draw: 9.07 % in 2025Q4, so shocks "explain" 2.7 pp of 11.8 %); the old_2011 median-target draw has a 7.0 % baseline, so the level contributions of the two variants are not comparable; (b) the baseline uncertainty passes one-for-one into the sum of level contributions. The `changes_*.csv` are much less affected (baseline change 0.06–0.3 pp). Fix: quote changes, not levels, as the result; or use a prior mean of 0 (or < 1) on the own lag of inflation, the deficit ratio and tariff inflation so that the deterministic path is a steady state, and report the baseline band next to the level chart.

### 6. DOUBT — pointwise medians of contributions do not add up to the data
`scripts/models/svar_v2.py:92-118` (`bands`, `levels`), same in `bvar_sign.py`, `bvar_sign_ext.py`.

`changes_v2.csv`, 2024Q4→2025Q4: the seven group medians sum to +2.52, baseline +0.14, total +2.66 against "Факт" +3.43 — 0.77 pp (22 %) of the rise is not allocated. In `levels_v2.csv` the sum of medians in 2024Q4 is −0.17 against −0.60 (actual − baseline) in the median-target draw. Each median comes from a different model (Fry–Pagan). The files are correct as percentiles, but a reader who adds the medians gets a wrong decomposition. Fix: add the median-target draw's changes to `changes_*.csv` as a column, or a row "sum of medians" next to "Факт".

### 7. DOUBT — Blanchard–Perotti ordering applied to a deficit ratio
`scripts/models/svar_v2.py:187` and docstring lines 7-10.

The BP zero (no within-quarter reaction to activity) is defended for discretionary spending. The non-oil deficit in % of GDP contains non-oil revenue (reacts to activity within the quarter) and GDP in the denominator. Ordering it before GDP assigns that endogenous movement to the "fiscal shock"; higher GDP lowers the ratio, which biases the GDP response of a "deficit shock" downward. The reported impact response of GDP to +1 pp is +0.11 [−0.02; +0.24] and the price-level response is negative (−0.10 at h = 4) — consistent with that bias, so "2.5–3 % of inflation variance" is a lower bound from a contaminated shock, not an estimate of fiscal effects. Fix: use non-oil primary expenditure (or the deficit with revenue cyclically adjusted with an outside elasticity, as BP do for taxes), scaled by lagged or trend GDP.

### 8. DOUBT — `v2_ma4`: a 4-quarter moving average in a VAR(2), ordered recursively
`scripts/models/svar_v2_data.py:101`; `scripts/models/svar_v2.py:188, 201`

The innovation of `nonoil_ma4` is (d_t − d_{t−4})/4. The term d_{t−4} is not in the information set of a VAR with two lags, so the "shock" contains the drop-out of the quarter a year earlier (and the seasonal pattern, since the NSA ratio is averaged); it is not a structural innovation, and the recursive argument does not apply to it. Also `nonoil_ma4` is the mean of four quarterly ratios, not Σ deficit / Σ GDP (differences 0.05–0.15 pp: 2026Q2 6.90 vs 7.02). Fix: use the annual-stance variable only with four lags of itself, or keep the quarterly SA ratio.

### 9. DOUBT — quasi-fiscal split: gross flows, and three separate seasonal adjustments
`scripts/models/svar_v2_data.py:89-99`

(a) `LOAN.DI + EQUITY.DI` are gross outlays of the republican budget; the deficit contains net lending (loans minus repayments) and the net balance of financial-asset operations of the state budget. `nonoil_core = nonoil_def − quasi_def` therefore still contains the repayments. (b) `nonoil_def`, `quasi_def` and `nonoil_core` are each adjusted by their own additive X-13 run, so the SA identity fails: |core + quasi − total| is 0.16 pp on average and up to 0.52 pp. The quasi series is lumpy (0.03–2.9 % of GDP), where a seasonal filter mainly spreads the lumps. Fix: adjust total and core only and define quasi_sa as the difference, or leave quasi unadjusted.

### 10. DOUBT — one rotation per reduced-form draw, whatever the size of the admissible set
`scripts/models/bvar_sign_ext.py:85-115`, `scripts/models/bvar_sign.py:74-123`

For every posterior draw rotations are tried until one is accepted (`TRIES = 3000`), so all 1000 draws are kept ("accepted = 1000" in `summary.csv` is not an acceptance rate). The probability that a single rotation is accepted varies across draws from 0.045 to 0.24 (mean 0.12; 200 draws × 200 rotations). In the Rubio-Ramírez–Waggoner–Zha algorithm reduced-form draws are kept in proportion to that probability; here they are weighted equally. This is a different (also defensible, conditionally uniform) prior, but it is not what the docstring cites, and it changes the bands. Fix: draw one rotation per reduced-form draw and discard the pair if it fails (with more Gibbs draws), or state the scheme; report the acceptance probability instead of "accepted".

### 11. DOUBT — market core: utilities removed with a weight that is constant for 2012–2023
`models/cpi_components/market_core_index.csv` (no builder script in the repository)

The weight implied by core_ex3 = (1 − w)·market + w·regulated (months with |Δ| > 1 pp) is exactly 0.067 in every year 2012–2023, 0.061 in 2024 and 0.045 in 2025–26. The docstring of `bvar_market.py` says "official BNS weights, 4.5–6.7 %". BNS weights change every year, and a fall from 6.7 to 4.5 % while tariffs rose by about 80 % needs checking. It moves the market-core y/y by a few tenths in 2023–25. I could not check it against the source.

### 12. NOTE — importance weights for zero + sign restrictions (Arias, Rubio-Ramírez, Waggoner 2018) are not applied
Same functions as in 10. The zero (tenge shock → GDP on impact) is imposed exactly (q with a zero first element in the rotated block; the other three columns from a QR of Gaussian vectors projected on the orthogonal complement). The draw is uniform conditional on the zero, without the volume-element weights. Because GDP is first in the rotated block of a Cholesky factor, the restricted set of Q does not depend on (B, Σ), so I expect the correction to be small, but I did not compute it. QR is used without sign normalisation; harmless here, because both signs of every column are tried and the three sign patterns are mutually exclusive and exhaustive.

### 13. NOTE — July 2017 Problem Loans Fund transfer removed as a residual, not as the known amount
`scripts/models/svar_v2_data.py:74-82`. July expenditure 2 991.9 bn minus the August–September average 856.1 bn gives 2 135.8 bn. The transfer was, from memory, 2 092.9 bn tenge (please verify); the difference of about 43 bn is 0.3 pp of 2017Q3 GDP (13.35 trn). Quarter and sign are right (2017Q3 NSA ratio 9.31 %). Fix: hard-code the published amount.

### 14. NOTE — nominal GDP 2026Q2 (denominator) extrapolated with the 2026Q1 SA q/q growth of +4.08 %
`scripts/models/svar_v2_data.py:62-71`. Gives 41.08 trn (+12.9 % y/y). With the 2026Q1 y/y (+15.4 %) the 2026Q2 ratio would be 8.60 instead of 8.79 % (NSA). Small.

### 15. NOTE — non-oil deficit: seasonally adjusted version barely matters
Re-run with the NSA ratio: fiscal contribution 2025Q4→2026Q2 +0.06 instead of +0.13/+0.16, GDP impact response +0.05 instead of +0.11. X-13 preserves the mean (8.69 both).

### 16. NOTE — the two-sided X-13 filter and full-sample hyperparameters
Seasonal factors, λ, μ and s are full-sample; the last quarters of the SA series will be revised. Standard, but the 2026Q1 deficit (NSA 3.79 → SA 6.06) depends on a Q1 factor of +1.24 ± 0.64 pp.

### 17. NOTE — sample labels
`svar_v2.py` docstring: "v2 ... 2013Q1–2026Q2", "old_2011 ... 2011Q2–2026Q1"; the estimation samples are 2013Q3– and 2011Q4– (two lags; `summary.csv` and the README have the right dates). `bvar_market.py`: the market index starts 2011-02, so 2011Q1 is incomplete and the sample silently starts one quarter later than the headline models.

### 18. NOTE — stale statements
`bvar_sign_ext.py:9` says the regulated CPI is "STL SA"; `model_data` is X-13 now. On current data `old_2011` and `bvar_sign_ext` "full" are the same model with the same seed, so `old_2011` reproduces rather than tests the old result; the README's "STL vintage" describes the committed `bvar_sign*/` and `bvar_market/` files only until they are re-run.

### 19. NOTE — units of the fiscal IRF
`svar_v2.py:133-146`: "+1 pp of GDP" is 1 % of one quarter's GDP (0.25 % of annual GDP). For `v2_ma4` the same normalisation is a 4 pp quarterly impulse. Worth a line in the table header.

## Checked and found correct
- Non-oil deficit ratio: YTD → discrete quarters (Q1 = March YTD, others differences; no missing quarter-ends 2013Q1–2026Q2), sign (deficit positive), units (mln KZT / mln KZT, same-quarter discrete nominal GDP). My recomputation matches `inputs_quarterly.csv` to 5e-5 (NSA ratio and MA4). The 2017 removal is in the right quarter. The FPK transfer is not in `EQUITY.DI`.
- 2026Q2 GDP arithmetic (10 387 261.75 × 1.05184) matches the file; the index is the discrete-quarter y/y, not cumulative.
- Transformations: 100 ln for levels, 400 Δln of quarterly means for inflation; the 4-quarter mean of SAAR rates equals the y/y log change of the quarterly-average index (2026Q2: 10.00 vs 100·ln(1.1054) = 10.02). No off-by-one in lags (`lagmat`) or in the alignment of `idx` with Y.
- Minnesota dummies (lag decay, cross-variable scaling, sum-of-coefficients, diffuse constant), the marginal-likelihood formula and its Jacobian for the crisis weights; hyperparameters are interior to the grid (v2: λ = 0.5, μ = 5, s = 5).
- Gibbs sampler: GLS for β | Σ with equation-specific regressor sets, inverse-Wishart for Σ | β (degrees of freedom and the sampler are right). Block exogeneity is exact in every draw (max |coefficient of domestic lags in external equations| = 0).
- Identification, per draw (1000 draws of v2): A0·A0′ = Σ to 2e-14; external variables do not respond on impact to any domestic shock; the first five columns are lower-triangular; fiscal and tariff rows are zero for the four rotated shocks; GDP ← tenge is exactly 0; all sign restrictions of the docstring table hold in 100 % of draws; shock signs are normalised.
- Historical decomposition: uses unweighted residuals (crisis quarters keep their large shocks); contributions + baseline = data by construction; every committed `median_target_*.csv` adds up to the rounding of the CSV (max error 0.002–0.003).
- `changes_*.csv` "Факт" equals the change of the model's y/y measure; `summary.csv` T, sample and λ agree with the re-run; my `v2` and `old_2011` re-runs reproduce the committed medians within Monte-Carlo noise.
- IRF scaling: price level = cumulated SAAR response / 4; fiscal IRFs normalised by the impact response of the fiscal variable.

## Could not check
- The X-13 step itself (`nonoil_def`, `quasi_def`, `nonoil_core`, market core): `tools/x13as/x13as_ascii` is a 132-byte LFS pointer in this environment. I used the committed SA series; `v2_split`, `v2_ma4` and the two market variants were not re-estimated (only their CSVs were checked for additivity and FEVD sums).
- Construction of `models/cpi_components/market_core_index.csv` and of `tariff_change_months.csv`, `rb_quasifiscal_ytd.csv`, `state_non_oil_deficit_ytd.csv`: builders/fetchers are outside the scope or absent; the Minfin definition of the non-oil deficit was taken as given.
- The committed `bvar_sign/`, `bvar_sign_ext/`, `bvar_market/` numbers cannot be reproduced from the current `model_data` (STL vintage); only internal consistency was checked.
- The exact size of the 2017 transfer (finding 13) against a primary source.
- The size of the Arias et al. importance-weight correction (finding 12).
