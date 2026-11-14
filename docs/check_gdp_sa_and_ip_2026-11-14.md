# Check of BNS seasonally adjusted GDP and of the monthly industrial production index (2026-11-14)

Question: are the +6.5 % q/q of real GDP in 2026 Q2 (`gdp` in model_data) and the monthly industrial
production level (`ip`) artefacts of the pipeline, or are they in the BNS sources? Both are in the sources.
Everything below is computed from the files in this repository unless marked «Taldau, fetched 2026-11-14»
(series the pipeline does not store). Marks: **[E]** established from the files, **[H]** hypothesis.

## 1. Seasonally adjusted real GDP

Source: BNS element 283161, sheet «6» «в ценах 2010 г., с исключением сезонного фактора»; method per the
workbook's metadata sheet: X-13ARIMA-SEATS in JDemetra+ 2.2.4, national calendar, each series adjusted
directly, no benchmarking to annual totals. The processed file equals the workbook in all 858 cells
(13 items x 66 quarters). **[E]**

| Quarter | GDP SA, mln KZT 2010 prices | q/q, % | Unadjusted y/y (QNA) | Table 4439 y/y |
|---|---|---|---|---|
| 2025 Q1 | 10 295 398.1 | 3.41 | 104.6 | 105.6 |
| 2025 Q2 | 10 347 636.8 | 0.51 | 108.9 | 107.0 |
| 2025 Q3 | 10 394 503.2 | 0.45 | 105.4 | 106.3 |
| 2025 Q4 | 10 611 584.2 | 2.09 | 107.0 | 106.8 |
| 2026 Q1 | 10 482 201.6 | -1.22 | 101.4 | 103.0 |
| 2026 Q2 | 11 163 843.2 | 6.50 | 108.2 | 105.2 |

- The swing is in the unadjusted accounts: our own X-13 of the unadjusted series gives -2.55 % and +7.90 %,
  the production-side SA GDP (element 283162, republished 2026-11-11) -2.56 % and +7.29 %. **[E]**
- It sits in mining. Same quarter a year earlier = 100: **[E]**

| | QNA section B | Table 4439 section B | Mining production index | Oil and condensate, tonnes |
|---|---|---|---|---|
| 2026 Q1 | 82.2 | 88.5 | 89.4 | 80.1 |
| 2026 Q2 | 118.7 | 101.8 | 103.3 | 102.8 |

  Mining alone explains 2.4 of the 3.0 points between 108.2 and 105.2 in Q2.
- Part of the rebound is real: oil output was 20 % below a year earlier in Q1 (January -32 %) and rose 31 %
  from Q1 to Q2. Extending the 2025 SA levels with table-4439 growth gives 10 604 260 (-0.1 % q/q) and
  10 884 058 (+2.6 % q/q). **[E]**
- Revisions: between the workbooks of 2026-09-23 and 2026-11-04 the unadjusted 2026 Q1 was cut by 2.5 %
  (y/y 104.1 -> 101.4). The 2026 columns carry no «preliminary» mark. **[E]**
- The adjusted expenditure table is not a decomposition of adjusted GDP: exports and inventories are the
  unadjusted values in all 54 quarters from 2013; components are adjusted directly and do not add up; the
  constant-price export row repeats seven values across fifteen quarters. **[E]**
- Why the accounts' mining volume departs from physical output is not documented by BNS; the profile looks
  like a deflation problem (nominal mining output about +46 % y/y in Q2 with volume +3 %, the accounts show
  nominal +37 % and real +19 %). **[H]**

Recommendation: keep `gdp` through 2025 Q4; treat 2026 Q1-Q2 as a first estimate (revision risk 2-3 % of the
level) -- end estimation at 2025 Q4 or run a sensitivity with the table-4439 extension. Registered as
`qna_2026_first_estimate` in `config/source_issues.yaml` (replaces `qna_production_2026_withdrawn`).

## 2. Monthly industrial production (Taldau index 701625)

The pipeline reads the right terms; all 153 months of the m/m and y/y series equal Taldau on 2026-11-14 and
did not change since the download of 2026-09-25. **[E]**

| January-September 2026 on a year earlier | |
|---|---|
| BNS bulletin, Taldau cumulative series (Taldau, fetched 2026-11-14) | 102.9 |
| Level chained from y/y (model_data `ip`) | 103.5 |
| Level chained from m/m | 152.6 |

| Year | Chained m/m | Chained y/y | Official annual |
|---|---|---|---|
| 2021 | 98.4 | 103.7 | 103.6 |
| 2022 | 101.1 | 101.0 | 101.2 |
| 2023 | 104.4 | 104.3 | 104.4 |
| 2024 | 107.5 | 102.8 | 103.2 |
| 2025 | 114.6 | 107.5 | 107.7 |

- Identity m/m(t) / m/m(t-12) = y/y(t) / y/y(t-1): it holds within 0.1-0.2 % in early 2024, breaks by +6.3 %
  in April 2024 (all sections) and by +2 to +15 % in every month of 2026 (January +5.4, February +2.0, March
  +7.7, April +4.8, May +15.4, June +6.4, July +5.1, August +8.8, September +3.3). In 2026 the bias is in
  manufacturing and in water supply; the mining m/m follows oil tonnes. **[E]**
- Chained m/m puts manufacturing in September 2026 at 255 % of December 2025; nominal manufacturing output
  is at 78 %, steel 72, ferroalloys 42, cement 111. **[E]** (Taldau section series, fetched 2026-11-14)
- "The y/y is revised, the m/m is not" -- the explanation recorded on 2026-11-13 -- is wrong: neither
  series is revised on Taldau. The monthly y/y is a first print as well: January and February 2026 (93.4,
  103.2) imply about 98.9 for January-February, the cumulative series has 96.9; the gap stays for the rest
  of the year (rebuilt minus published: 0.0, +2.0, +1.8, +1.4, +1.1, +0.8, +0.8, +0.7, +0.6). **[E]**
- Likely cause of the m/m defect: a ratio taken on a non-comparable set of enterprises or weights. **[H]**
- One outlier in the Taldau cumulative series: January-April 2017 = 112.3 (should be about 108.2). **[E]**

Recommendation: keep the y/y-chained `ip`, used only through `ip_yoy` and `ip_sa` (its unadjusted
month-to-month profile is not the published one); for quarterly growth the cumulative index is the measure
BNS revises -- it is not fetched by the pipeline yet (Taldau period 8, term 2695732). No seasonally adjusted
monthly index is published on the BNS industry pages.
